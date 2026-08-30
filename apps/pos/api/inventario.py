"""Inventario: insumos, recetas y el libro de movimientos.

La idea de fondo, en una frase: **el libro es la verdad y el saldo es una copia
rápida**. `Insumo.stock` existe para que cobrar una venta sea un UPDATE y no un
SUM sobre todo el historial de la leche, pero si alguna vez los dos no
coinciden, el que manda es el libro y hay un `/recalcular` que lo reconstruye.

La segunda idea: **el stock nunca bloquea una venta**. Hay cola en el mostrador
y el cliente muchas veces ya pagó en la máquina del banco; si el POS se negara,
el cajero solo podría mentirle al cliente o anotar la venta en un papel. Además
el número siempre está algo equivocado, porque sale de recetas que son
estimaciones. Un saldo negativo no es un error: es el sistema avisando que hay
una compra que nadie registró.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.db.models import Insumo, Movimiento, Producto, Receta
from apps.pos.db.session import get_session
from core.config import (a_local, costo_de, hoy_local, mostrar_cantidad,
                         rango_utc_del_dia)
from core.planilla import sin_tildes
from core.schemas import (CompraIn, ConteoIn, InsumoIn, MermaIn, RecetaIn, TalCualIn)

router = APIRouter(prefix="/api/v1", tags=["inventario"])


# ---------------------------------------------------------------------------
# Escribir en el libro
# ---------------------------------------------------------------------------
def anotar(s: Session, insumo: Insumo, tipo: str, cantidad: int, *,
           motivo: str = "", venta_id: int | None = None,
           turno_id: int | None = None, quien: dict | None = None) -> Movimiento:
    """Agrega UNA fila al libro y mueve el saldo. Es el único camino.

    No hace commit: quien llama decide cuándo. Así el descuento de stock de una
    venta entra en la MISMA transacción que la venta — o entran las dos cosas,
    o no entra ninguna.
    """
    insumo.stock = int(insumo.stock) + int(cantidad)
    m = Movimiento(
        insumo_id=insumo.id,
        tipo=tipo,
        cantidad=int(cantidad),
        saldo_despues=insumo.stock,
        # El costo se congela igual que el precio en VentaLinea: "cuánto costó
        # la merma de julio" no puede depender de lo que vale la leche hoy.
        costo=costo_de(abs(int(cantidad)), insumo.compra_costo, insumo.compra_contenido),
        motivo=motivo,
        venta_id=venta_id,
        turno_id=turno_id,
        usuario_id=(quien or {}).get("id"),
        hecho_por=(quien or {}).get("nombre", ""),
    )
    s.add(insumo)
    s.add(m)
    return m


def descontar_venta(s: Session, venta, quien: dict | None = None) -> list[dict]:
    """Descuenta del stock lo que consumió una venta.

    Devuelve los insumos que quedaron bajo cero o bajo el mínimo, para que la
    caja pueda AVISAR. Nunca lanza: una venta ya cobrada no se puede rechazar
    porque los papeles del inventario digan otra cosa.
    """
    avisos: list[dict] = []
    for linea in venta.lineas:
        if not linea.producto_id:
            continue
        recetas = s.exec(
            select(Receta).where(Receta.producto_id == linea.producto_id)
        ).all()
        for r in recetas:                      # sin receta, este for no corre
            insumo = s.get(Insumo, r.insumo_id)
            if not insumo or not insumo.activo:
                continue
            gasto = r.cantidad * linea.cantidad
            anotar(s, insumo, "venta", -gasto,
                   motivo=f"Venta #{venta.numero}", venta_id=venta.id,
                   turno_id=venta.turno_id, quien=quien)
            if insumo.stock <= 0 or (insumo.minimo and insumo.stock < insumo.minimo):
                avisos.append({
                    "insumo": insumo.nombre,
                    "queda": mostrar_cantidad(insumo.stock, insumo.unidad),
                    "bajo_cero": insumo.stock < 0,
                })
    return avisos


def devolver_venta(s: Session, venta, quien: dict | None = None) -> int:
    """Le devuelve al stock lo que esa venta había descontado.

    Lee los movimientos que la venta escribió, NO recalcula desde la receta: si
    entremedio alguien cambió el latte de 200 a 180 ml de leche, recalcular
    devolvería 180 y se perderían 20 ml para siempre sin que nadie lo note. Es
    el mismo principio por el que VentaLinea congela el precio.

    De regalo: una venta anterior a que existiera la receta no escribió
    movimientos, así que no devuelve nada, sin ningún caso especial.
    """
    hechos = s.exec(
        select(Movimiento).where(
            Movimiento.venta_id == venta.id, Movimiento.tipo == "venta")
    ).all()
    # Si ya se devolvió, no se devuelve dos veces.
    ya = {m.insumo_id for m in s.exec(
        select(Movimiento).where(
            Movimiento.venta_id == venta.id, Movimiento.tipo == "devolucion")
    ).all()}

    devueltos = 0
    for m in hechos:
        if m.insumo_id in ya:
            continue
        insumo = s.get(Insumo, m.insumo_id)
        if not insumo:
            continue
        anotar(s, insumo, "devolucion", -m.cantidad,
               motivo=f"Anulada la venta #{venta.numero}", venta_id=venta.id,
               turno_id=venta.turno_id, quien=quien)
        devueltos += 1
    return devueltos


# ---------------------------------------------------------------------------
# Mirar el inventario
# ---------------------------------------------------------------------------
def _insumo_repetido(s: Session, nombre: str, salvo_id: int | None) -> Insumo | None:
    """El insumo que ya se llama así, o None. Compara SIN tildes ni mayúsculas.

    Existe porque crear un insumo no revisaba nada y se creaban dos iguales en
    silencio: el dueño escribía "Leche" dos veces y quedaban dos saldos, cada
    uno con la mitad de la verdad.

    Compara normalizado y no con `==` porque el `==` crudo es exactamente lo que
    fallaba: "Coca-Cola 1.5 L" y "Coca Cola 1.5L" son la misma botella para
    cualquier persona y dos cosas distintas para un `==`.

    Y mira TODOS los insumos, no solo los activos —al revés que los usuarios—
    porque un insumo sacado de la bodega conserva su libro de movimientos. Dejar
    que otro le tome el nombre deja dos historias mezcladas para siempre.
    """
    objetivo = sin_tildes(nombre)
    for otro in s.exec(select(Insumo)).all():
        if otro.id != salvo_id and sin_tildes(otro.nombre) == objetivo:
            return otro
    return None


def _insumo_dict(i: Insumo) -> dict:
    valor = costo_de(max(0, i.stock), i.compra_costo, i.compra_contenido)
    return {
        "id": i.id, "nombre": i.nombre, "unidad": i.unidad,
        "stock": i.stock, "muestra": mostrar_cantidad(i.stock, i.unidad),
        "minimo": i.minimo, "minimo_muestra": mostrar_cantidad(i.minimo, i.unidad),
        "bajo_minimo": bool(i.minimo) and i.stock < i.minimo,
        "bajo_cero": i.stock < 0,
        "formato": i.formato, "compra_contenido": i.compra_contenido,
        "compra_costo": i.compra_costo, "valor": valor,
        "activo": i.activo, "orden": i.orden,
        # De qué producto es "el mismo". Vacío en un insumo de verdad.
        "producto_id": i.producto_id,
    }


@router.get("/inventario")
def ver_inventario(s: Session = Depends(get_session)):
    insumos = s.exec(
        select(Insumo).where(Insumo.activo == True)  # noqa: E712
        .order_by(Insumo.orden, Insumo.nombre)
    ).all()
    filas = [_insumo_dict(i) for i in insumos]
    productos = s.exec(select(Producto).where(Producto.activo == True)).all()  # noqa: E712
    con_receta = {r.producto_id for r in s.exec(select(Receta)).all()}
    return {
        "insumos": filas,
        "valor_total": sum(f["valor"] for f in filas),
        "por_comprar": [f for f in filas if f["bajo_minimo"] or f["bajo_cero"]],
        # No es un reproche: es para que se vea que el inventario se puede ir
        # cargando de a poco y ya sirve.
        "productos_con_receta": len([p for p in productos if p.id in con_receta]),
        "productos_totales": len(productos),
    }


@router.get("/inventario/alertas")
def alertas(s: Session = Depends(get_session)):
    insumos = s.exec(select(Insumo).where(Insumo.activo == True)).all()  # noqa: E712
    faltan = [_insumo_dict(i) for i in insumos
              if (i.minimo and i.stock < i.minimo) or i.stock < 0]
    return {"por_comprar": sorted(faltan, key=lambda f: f["stock"]),
            "cuantos": len(faltan)}


@router.get("/inventario/insumos/{insumo_id}/movimientos")
def movimientos(insumo_id: int,
                desde: str | None = Query(default=None, description="AAAA-MM-DD"),
                hasta: str | None = Query(default=None),
                s: Session = Depends(get_session)):
    """El libro de un insumo. Esta es la pantalla que contesta
    "¿por qué me faltan 3 litros de leche?"."""
    i = s.get(Insumo, insumo_id)
    if not i:
        raise HTTPException(404, "No existe ese insumo")
    consulta = select(Movimiento).where(Movimiento.insumo_id == insumo_id)
    if desde:
        ini, _ = rango_utc_del_dia(date.fromisoformat(desde))
        consulta = consulta.where(Movimiento.creado_at >= ini)
    if hasta:
        _, fin = rango_utc_del_dia(date.fromisoformat(hasta))
        consulta = consulta.where(Movimiento.creado_at < fin)
    filas = s.exec(consulta.order_by(Movimiento.creado_at.desc(), Movimiento.id.desc())).all()
    return {
        "insumo": _insumo_dict(i),
        "movimientos": [{
            "id": m.id,
            "fecha": a_local(m.creado_at).isoformat(),
            "tipo": m.tipo,
            "cantidad": m.cantidad,
            "muestra": ("+" if m.cantidad > 0 else "") + mostrar_cantidad(m.cantidad, i.unidad),
            "saldo_despues": m.saldo_despues,
            "saldo_muestra": mostrar_cantidad(m.saldo_despues, i.unidad),
            "costo": m.costo,
            "motivo": m.motivo,
            "quien": m.hecho_por,
            "venta_id": m.venta_id,
        } for m in filas],
    }


# ---------------------------------------------------------------------------
# Mantener los insumos
# ---------------------------------------------------------------------------
@router.post("/inventario/insumos")
def crear_insumo(datos: InsumoIn, s: Session = Depends(get_session),
                 quien: dict = Depends(sesion.exige("inventario"))):
    repetido = _insumo_repetido(s, datos.nombre, None)
    if repetido:
        raise HTTPException(409, f"Ya hay algo que se llama {repetido.nombre} en la bodega."
                            + ("" if repetido.activo else " Está sacado de la bodega:"
                               " ábrelo y devuélvelo en vez de crear otro."))
    i = Insumo(**datos.model_dump(exclude={"stock_inicial"}), stock=0)
    s.add(i)
    s.commit()
    s.refresh(i)
    if datos.stock_inicial:
        anotar(s, i, "carga", datos.stock_inicial,
               motivo="Con lo que había al empezar", quien=quien)
        s.commit()
        s.refresh(i)
    return _insumo_dict(i)


@router.put("/inventario/insumos/{insumo_id}")
def editar_insumo(insumo_id: int, datos: InsumoIn, s: Session = Depends(get_session),
                  quien: dict = Depends(sesion.exige("inventario"))):
    i = s.get(Insumo, insumo_id)
    if not i:
        raise HTTPException(404, "No existe ese insumo")
    repetido = _insumo_repetido(s, datos.nombre, insumo_id)
    if repetido:
        raise HTTPException(409, f"Ya hay algo que se llama {repetido.nombre} en la bodega.")
    # El stock NO se toca por acá a propósito: para cambiarlo está el conteo o
    # el ajuste, que dejan una fila en el libro diciendo quién y por qué.
    for campo, valor in datos.model_dump(exclude={"stock_inicial"}).items():
        setattr(i, campo, valor)
    s.add(i)
    s.commit()
    s.refresh(i)
    return _insumo_dict(i)


@router.delete("/inventario/insumos/{insumo_id}")
def sacar_insumo(insumo_id: int, s: Session = Depends(get_session),
                 quien: dict = Depends(sesion.exige("inventario"))):
    i = s.get(Insumo, insumo_id)
    if not i:
        raise HTTPException(404, "No existe ese insumo")
    i.activo = False                # borrado lógico: el libro lo referencia
    s.add(i)
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Lo que mueve el stock
# ---------------------------------------------------------------------------
@router.post("/inventario/compras")
def registrar_compra(datos: CompraIn, s: Session = Depends(get_session),
                     quien: dict = Depends(sesion.exige("inventario"))):
    """Llegó mercadería. Se registra en envases, que es como se compra."""
    i = s.get(Insumo, datos.insumo_id)
    if not i:
        raise HTTPException(404, "No existe ese insumo")
    if datos.compra_costo is not None and datos.compra_costo != i.compra_costo:
        # El último costo pasa a ser EL costo. Un promedio ponderado sería más
        # exacto y nadie en una cafetería lo entendería ni lo revisaría.
        i.compra_costo = datos.compra_costo
    cantidad = datos.envases * i.compra_contenido
    m = anotar(s, i, "compra", cantidad,
               motivo=datos.motivo or f"Llegaron {datos.envases} × {i.formato or 'envase'}",
               quien=quien)
    s.commit()
    s.refresh(i)
    return {"ok": True, "movimiento_id": m.id, **_insumo_dict(i)}


@router.post("/inventario/mermas")
def registrar_merma(datos: MermaIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("inventario"))):
    """Se perdió algo. El motivo es obligatorio: una merma sin motivo no se
    distingue de un faltante."""
    i = s.get(Insumo, datos.insumo_id)
    if not i:
        raise HTTPException(404, "No existe ese insumo")
    m = anotar(s, i, "merma", -datos.cantidad, motivo=datos.motivo, quien=quien)
    s.commit()
    s.refresh(i)
    return {"ok": True, "movimiento_id": m.id, "costo": m.costo, **_insumo_dict(i)}


@router.post("/inventario/conteo")
def conteo_fisico(datos: ConteoIn, s: Session = Depends(get_session),
                  quien: dict = Depends(sesion.exige("inventario_ajustar"))):
    """Se contó la bodega de verdad. Ajusta lo que no calzaba.

    Igual que el arqueo de caja: se cuenta a ciegas y la diferencia aparece
    recién ahora. Los insumos que calzan no generan ninguna fila — un
    movimiento existe cuando algo pasó.
    """
    diferencias, sin_cambios = [], 0
    for clave, contado in (datos.conteos or {}).items():
        try:
            i = s.get(Insumo, int(clave))
        except (TypeError, ValueError):
            continue
        if not i:
            continue
        ajuste = int(contado) - i.stock
        if ajuste == 0:
            sin_cambios += 1
            continue
        esperado = i.stock
        m = anotar(s, i, "ajuste", ajuste,
                   motivo=datos.nota or "Conteo de la bodega", quien=quien)
        diferencias.append({
            "insumo": i.nombre,
            "esperado": esperado,
            "esperado_muestra": mostrar_cantidad(esperado, i.unidad),
            "contado": int(contado),
            "contado_muestra": mostrar_cantidad(int(contado), i.unidad),
            "diferencia": ajuste,
            "diferencia_muestra": ("+" if ajuste > 0 else "") + mostrar_cantidad(ajuste, i.unidad),
            "costo": m.costo if ajuste > 0 else -m.costo,
        })
    s.commit()
    return {
        "ajustados": len(diferencias),
        "sin_cambios": sin_cambios,
        "diferencias": diferencias,
        "costo_del_descuadre": sum(d["costo"] for d in diferencias),
    }


@router.post("/inventario/recalcular")
def recalcular(s: Session = Depends(get_session),
               quien: dict = Depends(sesion.exige("inventario_ajustar"))):
    """Reconstruye el saldo de cada insumo sumando el libro.

    Informa lo que no cuadraba en vez de arreglarlo calladamente, igual que
    `poner_al_dia()` devuelve lo que hizo: un descuadre entre el libro y la
    copia es una noticia, no un trámite.
    """
    corregidos = []
    for i in s.exec(select(Insumo)).all():
        real = sum(m.cantidad for m in s.exec(
            select(Movimiento).where(Movimiento.insumo_id == i.id)).all())
        if real != i.stock:
            corregidos.append({
                "insumo": i.nombre, "decia": i.stock, "es": real,
                "diferencia": real - i.stock,
            })
            i.stock = real
            s.add(i)
    s.commit()
    return {"revisados": len(s.exec(select(Insumo)).all()), "corregidos": corregidos}


# ---------------------------------------------------------------------------
# Recetas
# ---------------------------------------------------------------------------
def _receta_dict(s: Session, producto: Producto) -> dict:
    lineas = s.exec(select(Receta).where(Receta.producto_id == producto.id)).all()
    salida, costo_total, alcanza = [], 0, None
    for r in lineas:
        i = s.get(Insumo, r.insumo_id)
        if not i:
            continue
        costo = costo_de(r.cantidad, i.compra_costo, i.compra_contenido)
        costo_total += costo
        salida.append({
            "insumo_id": i.id, "nombre": i.nombre, "unidad": i.unidad,
            "cantidad": r.cantidad,
            "muestra": mostrar_cantidad(r.cantidad, i.unidad),
            "costo": costo,
            "stock": i.stock,
            # Lo que QUEDA en bodega, no lo que lleva la receta: son dos números
            # distintos y confundirlos hace que la ficha mienta.
            "stock_muestra": mostrar_cantidad(i.stock, i.unidad),
        })
        # Con lo que hay en bodega, ¿para cuántos alcanza?
        posibles = i.stock // r.cantidad if r.cantidad > 0 else 0
        alcanza = posibles if alcanza is None else min(alcanza, posibles)
    return {
        "producto_id": producto.id,
        "nombre": producto.nombre,
        "precio": producto.precio,
        "lineas": salida,
        "costo_total": costo_total,
        "margen": producto.precio - costo_total,
        "margen_pct": round((producto.precio - costo_total) * 100 / producto.precio)
        if producto.precio else 0,
        "alcanza_para": max(0, alcanza) if alcanza is not None else None,
    }


@router.get("/productos/{producto_id}/receta")
def ver_receta(producto_id: int, s: Session = Depends(get_session)):
    p = s.get(Producto, producto_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
    return _receta_dict(s, p)


@router.put("/productos/{producto_id}/receta")
def guardar_receta(producto_id: int, datos: RecetaIn, s: Session = Depends(get_session),
                   quien: dict = Depends(sesion.exige("inventario"))):
    """Reemplaza la receta completa.

    Las ventas viejas NO se recalculan: sus movimientos ya están escritos y
    congelados en el libro.
    """
    p = s.get(Producto, producto_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
    for vieja in s.exec(select(Receta).where(Receta.producto_id == producto_id)).all():
        s.delete(vieja)
    for linea in datos.lineas:
        if not s.get(Insumo, linea.insumo_id):
            raise HTTPException(404, f"No existe el insumo {linea.insumo_id}")
        s.add(Receta(producto_id=producto_id, insumo_id=linea.insumo_id,
                     cantidad=linea.cantidad))
    s.commit()
    return _receta_dict(s, p)


@router.delete("/productos/{producto_id}/receta")
def borrar_receta(producto_id: int, s: Session = Depends(get_session),
                  quien: dict = Depends(sesion.exige("inventario"))):
    """El producto vuelve a no mover stock. No es un error: es un estado."""
    for vieja in s.exec(select(Receta).where(Receta.producto_id == producto_id)).all():
        s.delete(vieja)
    s.commit()
    return {"ok": True}


@router.post("/productos/{producto_id}/receta/tal-cual")
def receta_tal_cual(producto_id: int, datos: TalCualIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("inventario"))):
    """El atajo del día 1: el producto se vende tal cual y es su propio insumo.

    Un toque y el alfajor tiene stock, sin que nadie tenga que entender la
    palabra "insumo" ni escribir una receta.
    """
    p = s.get(Producto, producto_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")

    # Se busca por ID, no por nombre. Antes se comparaba `Insumo.nombre ==
    # p.nombre` y eso tenía tres formas de fallar, las tres vistas en la base
    # del local: (a) el `==` distingue tildes y espacios, así que "Coca-Cola
    # 1.5 L" y "Coca Cola 1.5L" creaban DOS insumos y el stock del primero
    # quedaba huérfano; (b) si al producto le cambiaban el nombre después, el
    # insumo se quedaba con el viejo — en la base real quedó un insumo llamado
    # "Producto nuevo" apuntando a "redbul 550ml"; (c) no filtraba `activo`, así
    # que podía enganchar la receta a un insumo SACADO de la bodega, y entonces
    # la venta no descontaba nada y no daba ningún error.
    i = s.exec(select(Insumo).where(Insumo.producto_id == producto_id)).first()
    if not i:
        # Sin dueño todavía: se acepta uno que se llame igual, normalizado, y se
        # adopta. Es el caso de las bodegas cargadas a mano antes de esto.
        candidato = _insumo_repetido(s, p.nombre, None)
        i = candidato if candidato and not candidato.producto_id else None

    if i:
        # Ya existía: se ACTUALIZA en vez de ignorarlo. Antes, si el insumo ya
        # estaba, el costo y el mínimo que el dueño acababa de escribir se
        # descartaban en silencio y la API igual contestaba que sí.
        i.producto_id = producto_id
        i.nombre = p.nombre           # el nombre lo manda la carta, no la bodega
        i.activo = True               # si estaba sacado, vuelve
        if datos.compra_costo:
            i.compra_costo = datos.compra_costo
        if datos.minimo:
            i.minimo = datos.minimo
    else:
        i = Insumo(nombre=p.nombre, unidad="un", minimo=datos.minimo,
                   formato="Unidad", compra_contenido=1,
                   compra_costo=datos.compra_costo, producto_id=producto_id)
    s.add(i)
    s.commit()
    s.refresh(i)

    for vieja in s.exec(select(Receta).where(Receta.producto_id == producto_id)).all():
        s.delete(vieja)
    s.add(Receta(producto_id=producto_id, insumo_id=i.id, cantidad=1))
    if datos.stock_inicial:
        anotar(s, i, "carga", datos.stock_inicial,
               motivo="Con lo que había al empezar", quien=quien)
    s.commit()
    s.refresh(p)
    return _receta_dict(s, p)
