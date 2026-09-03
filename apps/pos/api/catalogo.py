"""La carta: categorías y productos.

Incluye `GET /api/v1/carta`, que es lo que leen las pantallas del local.
Ese endpoint es la razón por la que el punto de venta es el dueño de los precios:
una sola lista, no dos.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from apps.pos.db.models import Categoria, CodigoBarra, Insumo, Producto, Receta
from apps.pos import sesion
from apps.pos.db.session import get_session
from core.codigos import normalizar, por_que_no_sirve
from core.planilla import sin_tildes
from core.config import AVISOS, NOMBRE_LOCAL
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
        prods = _productos_de(s, c.id)
        if not prods:
            continue  # una categoría vacía rompe la pantalla; mejor no mandarla
        destacado = next((p for p in prods if p.destacado), None)
        normales = [p for p in prods if not p.destacado] or prods

        def _p(p: Producto) -> dict:
            return {
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "precio": p.precio,
                "antes": p.antes,
                "etiqueta": p.etiqueta or None,
                "dibujo": p.dibujo,
                "color": p.color or None,
            }

        bloque = {"nombre": c.nombre, "productos": [_p(p) for p in normales]}
        if destacado:
            bloque["destacado"] = {
                **_p(destacado),
                "etiqueta": destacado.badge or "Recomendado de hoy",
            }
        salida.append(bloque)

    return {"local": NOMBRE_LOCAL, "avisos": AVISOS, "categorias": salida}


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
    quedan = {i.producto_id: i.stock
              for i in s.exec(select(Insumo).where(
                  Insumo.producto_id != None,          # noqa: E711
                  Insumo.activo == True)).all()}       # noqa: E712

    return [
        {
            "id": c.id, "nombre": c.nombre, "orden": c.orden, "activa": c.activa,
            "productos": [
                {
                    "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion,
                    "precio": p.precio, "activo": p.activo, "orden": p.orden,
                    "destacado": p.destacado, "badge": p.badge, "antes": p.antes,
                    "etiqueta": p.etiqueta, "dibujo": p.dibujo, "color": p.color,
                    # None = no se lleva stock de esto. Distinto de 0, que es
                    # "se lleva y no queda ninguno".
                    "stock": quedan.get(p.id),
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
EXTRAS = {"codigo", "tal_cual", "costo", "stock_inicial", "minimo"}


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
    _un_solo_destacado(s, p)
    s.add(p)
    s.commit()
    s.refresh(p)

    if codigo:
        s.add(CodigoBarra(codigo=codigo, producto_id=p.id, cuantos=1))

    if datos.tal_cual:
        # El producto ES su propio insumo. Se amarra por id y no por nombre:
        # comparar nombres es lo que dejó un insumo llamado "Producto nuevo"
        # apuntando a un producto llamado "redbul 550ml" en la base real.
        i = Insumo(nombre=p.nombre, unidad="un", formato="Unidad",
                   compra_contenido=1, compra_costo=datos.costo,
                   minimo=datos.minimo, producto_id=p.id)
        s.add(i)
        s.commit()
        s.refresh(i)
        s.add(Receta(producto_id=p.id, insumo_id=i.id, cantidad=1))
        if datos.stock_inicial:
            from apps.pos.api.inventario import anotar
            anotar(s, i, "carga", datos.stock_inicial,
                   motivo="Con lo que había al empezar", quien=quien)

    s.commit()
    s.refresh(p)
    return p


@router.put("/productos/{prod_id}")
def editar_producto(prod_id: int, datos: ProductoIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    p = s.get(Producto, prod_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
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
    for k, v in datos.model_dump(exclude=EXTRAS).items():
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

    _un_solo_destacado(s, p)
    s.add(p)
    s.commit()
    s.refresh(p)
    return p


@router.delete("/productos/{prod_id}")
def borrar_producto(prod_id: int, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    """Borrado lógico: las ventas viejas tienen que seguir cuadrando."""
    p = s.get(Producto, prod_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
    p.activo = False
    s.add(p)
    s.commit()
    return {"ok": True, "id": prod_id, "activo": False}


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
