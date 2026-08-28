"""Ventas: registrar, listar, anular y el resumen del día."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.api import inventario
from apps.pos.db.models import Producto, Turno, Usuario, Venta, VentaLinea
from apps.pos.db.session import get_session
from core.config import (MEDIOS_PAGO, a_local, ahora, hoy_local, neto_iva, puede,
                         rango_utc_del_dia)
from core.schemas import AnularIn, VentaIn

router = APIRouter(prefix="/api/v1", tags=["ventas"])


def _turno_abierto(s: Session) -> Turno | None:
    return s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711


def _siguiente_numero(s: Session) -> int:
    ultimo = s.exec(select(Venta).order_by(Venta.numero.desc())).first()
    return (ultimo.numero + 1) if ultimo else 1


def _nombre(s: Session | None, usuario_id: int | None) -> str:
    """El nombre de quien hizo algo. Vacío en lo anterior al login: a esas
    ventas no se les inventa un autor."""
    if not s or not usuario_id:
        return ""
    u = s.get(Usuario, usuario_id)
    return u.nombre if u else ""


def _venta_dict(v: Venta, con_lineas: bool = False, s: Session | None = None) -> dict:
    d = {
        "id": v.id,
        "numero": v.numero,
        "creada_at": a_local(v.creada_at).isoformat(),
        "estado": v.estado,
        "total": v.total,
        "descuento": v.descuento,
        "cobrado": v.total - v.descuento,
        "propina": v.propina,
        "medio_pago": v.medio_pago,
        "nota": v.nota,
        "turno_id": v.turno_id,
        "usuario_id": v.usuario_id,
        "quien": _nombre(s, v.usuario_id),
    }
    if con_lineas:
        d["lineas"] = [
            {"nombre": l.nombre, "precio_unitario": l.precio_unitario,
             "cantidad": l.cantidad, "subtotal": l.subtotal}
            for l in v.lineas
        ]
        if v.estado == "anulada":
            d["anulada_motivo"] = v.anulada_motivo
    return d


@router.post("/ventas")
def registrar_venta(datos: VentaIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("vender"))):
    """Registra una venta YA COBRADA. El carrito vive en el navegador del cajero;
    acá llega recién cuando se cobró (ver CONTRATO, sección 2)."""
    lineas: list[VentaLinea] = []
    total = 0
    for item in datos.lineas:
        p = s.get(Producto, item.producto_id)
        if not p:
            raise HTTPException(404, f"No existe el producto {item.producto_id}")
        subtotal = p.precio * item.cantidad
        total += subtotal
        # nombre y precio COPIADOS: la venta de ayer no cambia si mañana sube el café
        lineas.append(VentaLinea(
            producto_id=p.id, nombre=p.nombre, precio_unitario=p.precio,
            cantidad=item.cantidad, subtotal=subtotal,
        ))

    # Un descuento mayor que la venta dejaría un cobro negativo: se recorta.
    descuento = min(datos.descuento, total)

    turno = _turno_abierto(s)
    venta = Venta(
        numero=_siguiente_numero(s),
        turno_id=turno.id if turno else None,
        total=total,
        descuento=descuento,
        propina=datos.propina,
        medio_pago=datos.medio_pago,
        nota=datos.nota,
        usuario_id=quien.get("id"),
    )
    venta.lineas = lineas
    s.add(venta)
    # flush y no commit: la venta necesita id para que los movimientos de stock
    # la puedan apuntar, pero las dos cosas tienen que entrar juntas. O queda
    # registrada la venta con su descuento de inventario, o no queda nada.
    s.flush()
    avisos = inventario.descontar_venta(s, venta, quien)
    s.commit()
    s.refresh(venta)

    cobrado = total - descuento + datos.propina
    vuelto = None
    if datos.medio_pago == "efectivo" and datos.paga_con is not None:
        vuelto = datos.paga_con - cobrado
        if vuelto < 0:
            # No bloqueamos la venta (ya se cobró), pero lo decimos.
            vuelto = None

    salida = _venta_dict(venta, con_lineas=True, s=s)
    salida["cobrado"] = cobrado
    salida["vuelto"] = vuelto
    # Avisa, no bloquea: la venta ya se cobró.
    salida["inventario"] = avisos
    return salida


@router.get("/ventas")
def listar_ventas(
    fecha: str | None = Query(default=None, description="AAAA-MM-DD, día local"),
    s: Session = Depends(get_session),
):
    dia = date.fromisoformat(fecha) if fecha else hoy_local()
    desde, hasta = rango_utc_del_dia(dia)
    ventas = s.exec(
        select(Venta)
        .where(Venta.creada_at >= desde, Venta.creada_at < hasta)
        .order_by(Venta.numero.desc())
    ).all()
    return {"fecha": dia.isoformat(),
            "ventas": [_venta_dict(v, s=s) for v in ventas]}


@router.get("/ventas/{venta_id}")
def ver_venta(venta_id: int, s: Session = Depends(get_session)):
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    return _venta_dict(v, con_lineas=True, s=s)


@router.post("/ventas/{venta_id}/anular")
def anular_venta(venta_id: int, datos: AnularIn, s: Session = Depends(get_session),
                 quien: dict = Depends(sesion.exige("anular"))):
    """Anular deja rastro. Editar montos del pasado, no: rompe el cuadre."""
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    if v.estado == "anulada":
        raise HTTPException(409, "Esa venta ya estaba anulada")

    # Anular una venta de un turno YA CERRADO cambia un cuadre que alguien ya
    # firmó e imprimió. Eso lo hace el dueño, no el cajero.
    de_turno_cerrado = False
    if v.turno_id:
        t = s.get(Turno, v.turno_id)
        de_turno_cerrado = bool(t and t.cerrado_at)
    if de_turno_cerrado and not puede(quien.get("rol", ""), "anular_pasado"):
        raise HTTPException(
            403, "Esa venta es de una caja que ya se cerró. Solo el dueño puede anularla.")

    v.estado = "anulada"
    v.anulada_at = ahora()
    v.anulada_motivo = datos.motivo
    v.anulada_por_id = quien.get("id")
    s.add(v)
    # Lo que la venta descontó del inventario vuelve, leído del libro.
    inventario.devolver_venta(s, v, quien)
    s.commit()
    s.refresh(v)
    return _venta_dict(v, con_lineas=True, s=s)


@router.get("/resumen")
def resumen(
    fecha: str | None = Query(default=None, description="un día suelto"),
    desde: str | None = Query(default=None, description="AAAA-MM-DD"),
    hasta: str | None = Query(default=None, description="AAAA-MM-DD, incluido"),
    s: Session = Depends(get_session),
):
    """Totales de un día o de un rango. Las anuladas se cuentan aparte, nunca se suman."""
    if desde:
        d1 = date.fromisoformat(desde)
        d2 = date.fromisoformat(hasta) if hasta else d1
    else:
        d1 = d2 = date.fromisoformat(fecha) if fecha else hoy_local()
    ini, _ = rango_utc_del_dia(d1)
    _, fin = rango_utc_del_dia(d2)
    ventas = s.exec(
        select(Venta).where(Venta.creada_at >= ini, Venta.creada_at < fin)
    ).all()
    dia = d1

    validas = [v for v in ventas if v.estado == "pagada"]
    anuladas = [v for v in ventas if v.estado == "anulada"]

    por_medio = {m: {"cantidad": 0, "total": 0} for m in MEDIOS_PAGO}
    total = propinas = descuentos = 0
    for v in validas:
        cobrado = v.total - v.descuento          # lo que realmente entró
        por_medio[v.medio_pago]["cantidad"] += 1
        por_medio[v.medio_pago]["total"] += cobrado
        total += cobrado
        descuentos += v.descuento
        propinas += v.propina

    neto, iva = neto_iva(total)
    vendidos: dict[str, dict] = {}
    for v in validas:
        for l in v.lineas:
            d = vendidos.setdefault(l.nombre, {"cantidad": 0, "total": 0})
            d["cantidad"] += l.cantidad
            d["total"] += l.subtotal

    top = sorted(vendidos.items(), key=lambda kv: kv[1]["cantidad"], reverse=True)[:10]
    dias = (d2 - d1).days + 1
    return {
        "fecha": dia.isoformat(),
        "desde": d1.isoformat(),
        "hasta": d2.isoformat(),
        "dias": dias,
        "promedio_diario": round(total / dias) if dias else 0,
        "ventas": len(validas),
        "total": total,
        "neto": neto,
        "iva": iva,
        "propinas": propinas,
        "descuentos": descuentos,
        "ticket_promedio": round(total / len(validas)) if validas else 0,
        "por_medio": por_medio,
        "anuladas": {"cantidad": len(anuladas),
                     "total": sum(v.total - v.descuento for v in anuladas)},
        "mas_vendidos": [{"nombre": n, **d} for n, d in top],
    }
