"""La carta: categorías y productos.

Incluye `GET /api/v1/carta`, que es lo que leen las pantallas del local.
Ese endpoint es la razón por la que el punto de venta es el dueño de los precios:
una sola lista, no dos.
"""
from __future__ import annotations
from apps.pos import local as datos_local

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from apps.pos.db.models import (Categoria, CodigoBarra, Insumo, Movimiento,
                                Producto, Receta)
from apps.pos import sesion
from apps.pos.balanza import plu_normalizado
from apps.pos.db.session import get_session
from core.codigos import normalizar, por_que_no_sirve
from core.planilla import sin_tildes
from core.config import AVISOS, NOMBRE_LOCAL, costo_de, mostrar_cantidad, puede
from core.schemas import CategoriaIn, ProductoIn

router = APIRouter(prefix="/api/v1", tags=["carta"])


def _productos_de(s: Session, cat_id: int, solo_activos: bool = True):
    q = select(Producto).where(Producto.categoria_id == cat_id)
    if solo_activos:
        q = q.where(Producto.activo == True)  # noqa: E712
    return s.exec(q.order_by(Producto.orden, Producto.id)).all()


@router.get("/carta")
def carta(respuesta: Response, s: Session = Depends(get_session)):
    """Formato exacto que esperan las pantallas de `menu-cafeteria`.

    CORS abierto a propósito: sin esto el navegador de la pantalla rechaza la
    respuesta y el menú se queda con la carta vieja. Es de solo lectura y solo
    expone precios que ya están a la vista del público.
    """
    respuesta.headers["Access-Control-Allow-Origin"] = "*"
    respuesta.headers["Cache-Control"] = "no-store"

    cats = s.exec(
        select(Categoria).where(Categoria.activa == True).order_by(Categoria.orden, Categoria.id)  # noqa: E712
    ).all()

    salida = []
    for c in cats:
        prods = [p for p in _productos_de(s, c.id) if p.en_tv]
        if not prods:
            continue  # una categoría vacía rompe la pantalla; mejor no mandarla
        destacado = next((p for p in prods if p.destacado), None)
        normales = [p for p in prods if not p.destacado] or prods

        def _p(p: Producto) -> dict:
            # Un producto que solo tiene precio por kilo salía en el televisor a $0.
            por_kilo = not p.precio and p.precio_kilo > 0
            return {
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "precio": p.precio_kilo if por_kilo else p.precio,
                "antes": p.antes,
                "etiqueta": p.etiqueta or ("Por kilo" if por_kilo else None),
                "dibujo": p.dibujo,
                "color": p.color or None,
                "en_tv": p.en_tv,
            }

        bloque = {"nombre": c.nombre, "productos": [_p(p) for p in normales]}
        if destacado:
            bloque["destacado"] = {
                **_p(destacado),
                "etiqueta": destacado.badge or "Recomendado de hoy",
            }
        salida.append(bloque)

    return {"local": datos_local.nombre(), "avisos": AVISOS, "categorias": salida}


@router.get("/categorias")
def listar_categorias(s: Session = Depends(get_session)):
    cats = s.exec(select(Categoria).order_by(Categoria.orden, Categoria.id)).all()

    # Cuántos quedan de cada producto que se vende TAL CUAL. Se manda para que
    # la pantalla no deje pedir 12 de algo que tiene 3.
    #
    # Va solo para los productos que SON su propio insumo. Un capuchino no tiene
    # "cuántos quedan": tiene leche y café, y cuántos capuchinos salen de eso es
    # una estimación, no un número que sirva para topear una venta.
    #
    # Una consulta para todos y no una por producto: con 800 productos, N+1
    # consultas acá son la diferencia entre abrir la caja y esperarla.
    # Solo los CONTADOS: el tope duro de la pantalla usa este número, y solo
    # bloquea lo que el dueño ya contó. Un producto que lleva cuenta pero que
    # todavía nadie contó llega con stock nulo y se vende como antes, hasta que
    # se cuente. Así "inventario obligatorio" no deja la carta entera invendible
    # el día que se actualiza.
    insumos_propios = s.exec(select(Insumo).where(Insumo.activo == True)).all()  # noqa: E712
    quedan = {i.producto_id: i.stock
              for i in s.exec(select(Insumo).where(
                  Insumo.producto_id != None,          # noqa: E711
                  Insumo.activo == True,               # noqa: E712
                  Insumo.contado == True)).all()}      # noqa: E712

    return [
        {
            "id": c.id, "nombre": c.nombre, "orden": c.orden, "activa": c.activa,
            "productos": [
                {
                    "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion,
                    "precio": p.precio, "activo": p.activo, "orden": p.orden,
                    "plu": p.plu, "precio_kilo": p.precio_kilo,
                    "en_tv": p.en_tv,
                    "destacado": p.destacado, "badge": p.badge, "antes": p.antes,
                    "etiqueta": p.etiqueta, "dibujo": p.dibujo, "color": p.color,
                    # None = no se lleva stock de esto. Distinto de 0, que es
                    # "se lleva y no queda ninguno".
                    "stock": quedan.get(p.id) if p.llevar_cuenta is not False else None,
                    "llevar_cuenta": p.llevar_cuenta if p.llevar_cuenta is not None else any(
                        i.producto_id == p.id and i.contado and i.unidad == "un"
                        for i in insumos_propios),
                }
                for p in _productos_de(s, c.id, solo_activos=False)
            ],
        }
        for c in cats
    ]


@router.post("/categorias")
def crear_categoria(datos: CategoriaIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    c = Categoria(**datos.model_dump())
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


@router.put("/categorias/{cat_id}")
def editar_categoria(cat_id: int, datos: CategoriaIn, s: Session = Depends(get_session),
                     quien: dict = Depends(sesion.exige("editar_carta"))):
    c = s.get(Categoria, cat_id)
    if not c:
        raise HTTPException(404, "No existe esa categoría")
    for k, v in datos.model_dump().items():
        setattr(c, k, v)
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


@router.delete("/categorias/{cat_id}")
def borrar_categoria(cat_id: int, s: Session = Depends(get_session),
                     quien: dict = Depends(sesion.exige("editar_carta"))):
    """Borra una categoría de verdad, PERO solo si está vacía.

    Un producto no puede quedarse sin categoría —`Producto.categoria_id` no
    acepta nulo— así que una categoría con productos adentro no se puede borrar
    sin dejar filas apuntando a la nada. Y SQLite no lo impediría solo: no tiene
    las llaves foráneas activadas, así que un borrado a lo bruto pasaría sin
    error y dejaría productos huérfanos, invisibles en la carta pero vivos en la
    base. Por eso la guarda es código y no confianza en la base.

    Se cuentan TODOS los productos, no solo los que están a la venta: uno
    apagado sigue apuntando a la categoría, y borrarla lo dejaría igual de
    huérfano. El mensaje dice cuántos hay y qué hacer, porque "no se puede" sin
    salida no le resuelve nada al dueño.
    """
    c = s.get(Categoria, cat_id)
    if not c:
        raise HTTPException(404, "No existe esa categoría")
    productos = _productos_de(s, cat_id, solo_activos=False)
    if productos:
        n = len(productos)
        raise HTTPException(
            409,
            f"«{c.nombre}» tiene {n} producto{'s' if n != 1 else ''} adentro. "
            "Muévelos a otra categoría o bórralos primero (cada producto se "
            "cambia de categoría en su ficha de Inventario).")
    s.delete(c)
    s.commit()
    return {"ok": True, "id": cat_id}


def _producto_repetido(s: Session, nombre: str, salvo_id: int | None) -> Producto | None:
    """El producto que ya se llama así, o None. Sin tildes ni mayúsculas.

    En la carta del local quedaron NUEVE productos llamados "Producto nuevo", y
    dos productos con el mismo nombre no son un detalle estético: el cajero no
    sabe cuál tocar, el informe de "lo más vendido" los cuenta por separado, y
    el stock de uno no dice nada del otro.

    Mira solo los ACTIVOS: uno sacado de la carta ya no se puede tocar ni
    vender, así que su nombre puede volver a usarse.
    """
    objetivo = sin_tildes(nombre)
    for otro in s.exec(select(Producto).where(Producto.activo == True)).all():  # noqa: E712
        if otro.id != salvo_id and sin_tildes(otro.nombre) == objetivo:
            return otro
    return None


# Lo que ProductoIn trae de más y no es columna de Producto: son las cosas que
# antes obligaban a ir a la Bodega a escribir todo de nuevo.
EXTRAS = {"codigo", "codigos", "codigos_quitar", "tal_cual", "costo", "stock_inicial", "minimo",
          "llevar_cuenta", "hay_ahora", "stock_esperado"}


def _receta_antigua(s: Session, p: Producto) -> bool:
    filas = s.exec(select(Receta).where(Receta.producto_id == p.id)).all()
    if not filas:
        return False
    i = s.get(Insumo, filas[0].insumo_id)
    return not (len(filas) == 1 and filas[0].cantidad == 1 and i
                and i.producto_id == p.id and i.unidad == "un")


@router.get("/inventario/productos")
def productos_inventario(s: Session = Depends(get_session),
                        quien: dict = Depends(sesion.exige_entrar)):
    if not any(puede(quien["rol"], permiso, quien.get("permisos", ""))
               for permiso in ("editar_carta", "inventario")):
        raise HTTPException(403, "No tienes permiso para ver Inventario")
    # Stock y costos son del inventario: quien solo edita la carta no los recibe.
    ve_stock = puede(quien["rol"], "inventario", quien.get("permisos", ""))
    insumos = s.exec(select(Insumo)).all()
    por_id = {i.id: i for i in insumos}
    propios = {i.producto_id: i for i in insumos if i.producto_id}
    recetas = {}
    for r in s.exec(select(Receta)).all():
        recetas.setdefault(r.producto_id, []).append(r)
    barras = {}
    for b in s.exec(select(CodigoBarra)).all():
        barras.setdefault(b.producto_id, []).append(
            {"codigo": b.codigo, "cuantos": b.cuantos, "nota": b.nota})
    filas = []
    for p in s.exec(select(Producto).order_by(Producto.orden, Producto.id)).all():
        i = propios.get(p.id)
        lineas = recetas.get(p.id, [])
        antigua = bool(lineas) and not (len(lineas) == 1 and lineas[0].cantidad == 1
                                        and i and i.unidad == "un" and lineas[0].insumo_id == i.id)
        cuenta = not antigua and p.llevar_cuenta is not False and bool(i and i.activo)
        if antigua:   # el costo de una receta antigua se calcula de sus ingredientes
            costo = sum(costo_de(r.cantidad, por_id[r.insumo_id].compra_costo,
                                 por_id[r.insumo_id].compra_contenido)
                        for r in lineas if r.insumo_id in por_id)
        else:
            costo = costo_de(1, i.compra_costo, i.compra_contenido) if i else p.costo_referencia
        fila = {**p.model_dump(), "codigos": barras.get(p.id, []),
                "receta_antigua": antigua, "cuenta": cuenta,
                "insumo_id": i.id if i else None,
                "stock": i.stock if i else 0, "contado": bool(i and i.contado),
                "minimo": i.minimo if i else 0,
                "compra_contenido": i.compra_contenido if i else 1,
                "formato": i.formato if i else "Unidad", "costo": costo}
        if not ve_stock:
            fila.update(insumo_id=None, stock=0, contado=False, minimo=0,
                        compra_contenido=1, formato="Unidad", costo=None)
        filas.append(fila)
    # Insumos que no son «el mismo» de un producto: ingredientes de recetas antiguas.
    ingredientes = [] if not ve_stock else [
        {"id": i.id, "nombre": i.nombre, "unidad": i.unidad, "stock": i.stock,
         "muestra": mostrar_cantidad(i.stock, i.unidad), "minimo": i.minimo,
         "minimo_muestra": mostrar_cantidad(i.minimo, i.unidad)}
        for i in sorted(insumos, key=lambda x: sin_tildes(x.nombre))
        if i.activo and (i.producto_id is None or i.unidad != "un")]
    return {"productos": filas, "ingredientes": ingredientes,
            "recetas_antiguas": any(p["receta_antigua"] for p in filas)}


def _permiso_stock(s: Session, p: Producto | None, datos: ProductoIn, quien: dict):
    def exigir(permiso):
        if not puede(quien["rol"], permiso, quien.get("permisos", "")):
            raise HTTPException(403, "No tienes permiso para cambiar el inventario del producto")
    if "llevar_cuenta" in datos.model_fields_set:
        anterior = p.llevar_cuenta if p else False
        if datos.llevar_cuenta != anterior:
            exigir("inventario")
            if p and _receta_antigua(s, p):
                raise HTTPException(409, "Este producto tiene una receta antigua: sigue funcionando sin cambios.")
            if datos.llevar_cuenta and datos.hay_ahora is None:
                # Prender la cuenta sin que nadie diga cuántos hay deja el producto
                # en cero y con el tope duro puesto: la caja dejaría de venderlo.
                propio = s.exec(select(Insumo).where(Insumo.producto_id == p.id)).first() if p else None
                if not (propio and propio.contado):
                    exigir("inventario_ajustar")
    if datos.tal_cual or "minimo" in datos.model_fields_set:
        exigir("inventario")
    if datos.hay_ahora is not None or datos.stock_inicial:
        exigir("inventario")
        exigir("inventario_ajustar")


def _guardar_codigos(s: Session, p: Producto, datos: ProductoIn):
    if datos.codigos is None and datos.codigos_quitar is None:
        return
    nuevos = {}
    for b in datos.codigos or []:
        problema = por_que_no_sirve(b.codigo)
        if problema:
            raise HTTPException(422, problema)
        limpio = normalizar(b.codigo)
        if limpio in nuevos:
            raise HTTPException(422, "El código está repetido en la ficha")
        ya = s.get(CodigoBarra, limpio)
        if ya and ya.producto_id != p.id:
            raise HTTPException(409, "Ese código ya pertenece a otro producto")
        nuevos[limpio] = b
    quitar = {normalizar(c) for c in datos.codigos_quitar} if datos.codigos_quitar is not None else None
    for b in s.exec(select(CodigoBarra).where(CodigoBarra.producto_id == p.id)).all():
        if b.codigo in nuevos:
            continue
        if quitar is None or b.codigo in quitar:
            s.delete(b)
    for codigo, b in nuevos.items():
        fila = s.get(CodigoBarra, codigo) or CodigoBarra(codigo=codigo, producto_id=p.id)
        fila.cuantos, fila.nota = b.cuantos, b.nota
        s.add(fila)


def _validar_plu(s: Session, plu: str, salvo_id: int | None = None) -> None:
    if not plu:
        return
    if any(c not in "0123456789" for c in plu):
        raise HTTPException(422, "El PLU debe tener solo números del 0 al 9.")
    numero = plu_normalizado(plu)
    # También se reserva en los inactivos: reactivar una ficha no debe dejar
    # dos precios distintos para el mismo PLU. No se convierte a int: un PLU
    # es un identificador, no una cantidad que haya que sumar.
    for otro in s.exec(select(Producto).where(Producto.plu != "")).all():
        if otro.id != salvo_id and plu_normalizado(otro.plu) == numero:
            raise HTTPException(409, f"El PLU {numero} ya es de «{otro.nombre}».")


def _a_la_bodega(s: Session, p: Producto, datos: ProductoIn, quien: dict) -> None:
    """Costo en el insumo propio o referencia sin stock; cantidades por el libro."""
    i = s.exec(select(Insumo).where(Insumo.producto_id == p.id)).first()
    if not i:
        if datos.hay_ahora is not None:
            raise HTTPException(422, "Activa el inventario antes de contar este producto")
        if "costo" in datos.model_fields_set:
            p.costo_referencia = datos.costo
        return
    if "costo" in datos.model_fields_set:
        if datos.costo * i.compra_contenido > 9223372036854775807:
            raise HTTPException(422, "El costo del envase es demasiado grande")
        i.compra_costo = datos.costo * i.compra_contenido
    if "minimo" in datos.model_fields_set:
        i.minimo = datos.minimo
    s.add(i)

    if datos.hay_ahora is not None:
        if not p.llevar_cuenta and p.llevar_cuenta is not None:
            raise HTTPException(422, "Activa el inventario antes de contar este producto")
        if datos.stock_esperado is None or i.stock != datos.stock_esperado:
            raise HTTPException(409, "La cantidad cambió. Vuelve a abrir la ficha y revisa cuánto hay.")
        tiene_historia = s.exec(select(Movimiento).where(Movimiento.insumo_id == i.id)).first()
        if datos.hay_ahora != i.stock or not i.contado or not tiene_historia:
            from apps.pos.api.inventario import anotar
            anotar(s, i, "ajuste" if tiene_historia else "carga", datos.hay_ahora - i.stock,
                   motivo="Cantidad contada en la ficha de Inventario", quien=quien)

    # «Inicial» quiere decir que no hay historia. El libro es la prueba: si el
    # insumo ya tiene movimientos, su saldo es real y sumarle una carga encima lo
    # dejaría contando de más. Así, guardar la ficha dos veces no duplica nada.
    if datos.stock_inicial and not s.exec(
            select(Movimiento).where(Movimiento.insumo_id == i.id)).first():
        from apps.pos.api.inventario import anotar
        anotar(s, i, "carga", datos.stock_inicial,
               motivo="Con lo que había al empezar", quien=quien)


@router.post("/productos")
def crear_producto(datos: ProductoIn, s: Session = Depends(get_session),
                   quien: dict = Depends(sesion.exige("editar_carta"))):
    """Crea el producto y, si se pide, TODO lo demás en la misma operación.

    Un producto que se compra y se vende tal cual —una botella, un alfajor, un
    pastel— necesita cuatro cosas: la ficha, un insumo con su saldo, la receta
    que los amarra y el código de barras. Antes eso eran tres pantallas y el
    nombre escrito dos veces, y el resultado está en la base del local: 148
    ventas y UN insumo cargado. Acá es un formulario.

    Va todo en la MISMA transacción a propósito: un producto a medio crear
    —ficha sí, insumo no— es peor que no haberlo creado, porque se vende y no
    descuenta y nadie se entera hasta el conteo.
    """
    from apps.pos.db.session import reservar_escritura
    reservar_escritura(s)
    _permiso_stock(s, None, datos, quien)
    _validar_plu(s, datos.plu)
    if not s.get(Categoria, datos.categoria_id):
        raise HTTPException(404, "No existe esa categoría")
    repetido = _producto_repetido(s, datos.nombre, None)
    if repetido:
        raise HTTPException(409, f"Ya hay un producto que se llama «{repetido.nombre}». "
                                 "Dos con el mismo nombre no se distinguen en la caja.")

    codigo = ""
    if datos.codigo:
        problema = por_que_no_sirve(datos.codigo)
        if problema:
            raise HTTPException(422, problema)
        codigo = normalizar(datos.codigo)
        ya = s.get(CodigoBarra, codigo)
        if ya:
            otro = s.get(Producto, ya.producto_id)
            raise HTTPException(409, f"Ese código ya es de «{otro.nombre if otro else '?'}».")

    p = Producto(**datos.model_dump(exclude=EXTRAS))
    p.llevar_cuenta = None if datos.tal_cual else datos.llevar_cuenta
    _un_solo_destacado(s, p)
    s.add(p)
    s.flush()

    if codigo:
        s.add(CodigoBarra(codigo=codigo, producto_id=p.id, cuantos=1))

    if datos.tal_cual:
        # El producto ES su propio insumo. Se ADOPTA un insumo huérfano del mismo
        # nombre en vez de crear otro: al borrar un producto su insumo queda sin
        # dueño (producto_id nulo) pero con su stock y su libro. Si se vuelve a
        # crear el mismo producto y acá se creara OTRO insumo, quedarían dos con
        # la mitad de la verdad cada uno — el bug de la decisión 14, entrando por
        # la puerta del borrado. Se amarra por id, nunca por nombre.
        from apps.pos.api.inventario import _insumo_repetido
        huerfano = _insumo_repetido(s, p.nombre, None)
        i = huerfano if (huerfano and not huerfano.producto_id) else None
        if i:
            i.producto_id = p.id
            i.activo = True
            if datos.costo:
                i.compra_costo = datos.costo
            if datos.minimo:
                i.minimo = datos.minimo
        else:
            i = Insumo(nombre=p.nombre, unidad="un", formato="Unidad",
                       compra_contenido=1, compra_costo=datos.costo,
                       minimo=datos.minimo, producto_id=p.id)
        s.add(i)
        s.flush()
        for vieja in s.exec(select(Receta).where(Receta.producto_id == p.id)).all():
            s.delete(vieja)                # el huérfano pudo traer una receta a sí mismo
        s.add(Receta(producto_id=p.id, insumo_id=i.id, cantidad=1))
        if datos.stock_inicial:
            from apps.pos.api.inventario import anotar
            anotar(s, i, "carga", datos.stock_inicial,
                   motivo="Con lo que había al empezar", quien=quien)

    if datos.llevar_cuenta:
        from apps.pos.api.inventario import habilitar_cuenta
        habilitar_cuenta(s, p)
        s.flush()
        _a_la_bodega(s, p, datos, quien)
    else:
        _a_la_bodega(s, p, datos, quien)
    _guardar_codigos(s, p, datos)
    s.commit()
    s.refresh(p)
    return p


@router.put("/productos/{prod_id}")
def editar_producto(prod_id: int, datos: ProductoIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    from apps.pos.db.session import reservar_escritura
    reservar_escritura(s)
    if "plu" in datos.model_fields_set:
        _validar_plu(s, datos.plu, prod_id)
    p = s.get(Producto, prod_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
    _permiso_stock(s, p, datos, quien)
    # OJO: solo si le están CAMBIANDO el nombre.
    #
    # En la carta del local hay nueve productos llamados "Producto nuevo" desde
    # antes de esta regla. Si acá se validara siempre, guardarle el precio a uno
    # de esos —sin tocarle el nombre— daría 409 y quedarían congelados: no se
    # podrían arreglar ni renombrar, que es justo lo que hay que hacer con
    # ellos. La regla es para no CREAR colisiones nuevas, no para castigar las
    # que ya están.
    if sin_tildes(datos.nombre) != sin_tildes(p.nombre):
        repetido = _producto_repetido(s, datos.nombre, prod_id)
        if repetido:
            raise HTTPException(409, f"Ya hay un producto que se llama «{repetido.nombre}». "
                                     "Dos con el mismo nombre no se distinguen en la caja.")

    antes = p.nombre
    if "llevar_cuenta" in datos.model_fields_set:
        from apps.pos.api.inventario import habilitar_cuenta
        if datos.llevar_cuenta:
            habilitar_cuenta(s, p)
            s.flush()
        else:
            p.llevar_cuenta = False
    for k, v in datos.model_dump(exclude=EXTRAS).items():
        # La pantalla actual no manda estos campos: omitirlos conserva la
        # configuracion de balanza; enviarlos vacios permite borrarla.
        if k in {"plu", "precio_kilo", "en_tv"} and k not in datos.model_fields_set:
            continue
        setattr(p, k, v)

    # El insumo de un producto que se vende TAL CUAL lleva su mismo nombre, y
    # tiene que seguirlo cuando se lo cambian. Si no, pasa lo que hay en la base
    # del local: un insumo llamado "Producto nuevo" amarrado a "redbul 550ml".
    # El dueño abre la bodega, no reconoce nada, y termina creando otro.
    if p.nombre != antes:
        suyo = s.exec(select(Insumo).where(Insumo.producto_id == p.id)).first()
        if suyo:
            suyo.nombre = p.nombre
            s.add(suyo)

    # Lo de Avanzado: el costo que se escribió para sacar el precio es el mismo
    # con el que la Bodega valoriza lo que queda. Si el producto tiene su insumo,
    # se guarda ahí; si no, no se guarda en ninguna parte y solo sirvió de cuenta.
    if {"costo", "stock_inicial", "minimo", "hay_ahora"} & datos.model_fields_set:
        _a_la_bodega(s, p, datos, quien)
    _guardar_codigos(s, p, datos)

    _un_solo_destacado(s, p)
    s.add(p)
    s.commit()
    s.refresh(p)
    return p


@router.delete("/productos/{prod_id}")
def borrar_producto(prod_id: int, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    """Borra el producto DE VERDAD. La historia de ventas queda intacta.

    Distinto de apagar «A la venta» (activo=False), que es reversible y es lo que
    usa el importador. Esto no se puede deshacer, y por eso hay que hacer bien
    dos cosas:

    1. No dejar NI UNA fila huérfana. SQLite recicla los id —el próximo producto
       toma el id que quedó libre— así que una receta o un código de barras que
       queden apuntando a un id borrado se le pegan solos al siguiente producto
       que se cree: su receta descontando insumos ajenos, ventas de octubre
       diciendo ser de un producto de diciembre. Por eso se limpia todo en la
       MISMA transacción, no a lo bruto.

    2. Tratar cada tabla que apunta al producto según lo que ES:
       · VentaLinea: se le SUELTA el vínculo (producto_id a nulo). La línea
         guarda nombre y precio copiados, así que la venta vieja no cambia. Nunca
         se borra una VentaLinea.
       · Insumo propio: se le suelta el vínculo pero el insumo SE QUEDA, con su
         stock y su libro. La mercadería sigue en la repisa aunque el producto ya
         no esté en la carta; borrar el insumo le cambiaría el valor al inventario
         y dejaría su libro de movimientos huérfano, y el libro no se toca.
       · Receta y CodigoBarra: esas filas SÍ se borran. Su `producto_id` no
         acepta nulo, así que no se les puede soltar el vínculo, y sin el producto
         no significan nada. Borrar el código además lo libera para reusarlo.
    """
    from apps.pos.db.models import VentaLinea

    p = s.get(Producto, prod_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")

    for linea in s.exec(select(VentaLinea).where(VentaLinea.producto_id == prod_id)).all():
        linea.producto_id = None
        s.add(linea)
    for insumo in s.exec(select(Insumo).where(Insumo.producto_id == prod_id)).all():
        insumo.producto_id = None          # deja de ser tal cual; su stock y libro quedan
        s.add(insumo)
    for receta in s.exec(select(Receta).where(Receta.producto_id == prod_id)).all():
        s.delete(receta)
    for codigo in s.exec(select(CodigoBarra).where(CodigoBarra.producto_id == prod_id)).all():
        s.delete(codigo)

    s.delete(p)
    s.commit()
    return {"ok": True, "id": prod_id, "borrado": True}


def _un_solo_destacado(s: Session, p: Producto) -> None:
    """La pantalla tiene un solo recuadro grande por categoría: si marcas otro,
    el anterior se desmarca solo. Evita el 'por qué no se ve mi destacado'."""
    if not p.destacado:
        return
    otros = s.exec(
        select(Producto).where(
            Producto.categoria_id == p.categoria_id,
            Producto.destacado == True,  # noqa: E712
        )
    ).all()
    for o in otros:
        if o.id != p.id:
            o.destacado = False
            s.add(o)
