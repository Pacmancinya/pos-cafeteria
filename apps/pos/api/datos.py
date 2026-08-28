"""Respaldo de la base y exportación para el contador."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlmodel import Session, select

from apps.pos.db.models import Venta
from apps.pos import sesion
from apps.pos.db.session import get_session
from core.config import a_local, hoy_local, neto_iva, rango_utc_del_dia
from tools import respaldo as resp

router = APIRouter(prefix="/api/v1", tags=["datos"])


@router.post("/respaldo")
def hacer_respaldo(quien: dict = Depends(sesion.exige("ver_informes"))):
    return resp.respaldar("botón")


@router.get("/respaldos")
def ver_respaldos(quien: dict = Depends(sesion.exige("ver_informes"))):
    return {"carpeta": resp.CARPETA, "copias": resp.listar()}


def _csv(filas: list[list], cabecera: list[str], nombre: str) -> Response:
    """CSV pensado para que se abra bien en el Excel de acá.

    · separador `;`  → el Excel en español lo abre en columnas de una
    · `utf-8-sig`    → si no, los acentos salen como símbolos raros
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(cabecera)
    escritor.writerows(filas)
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


def _ventas_entre(s: Session, desde: date, hasta: date) -> list[Venta]:
    ini, _ = rango_utc_del_dia(desde)
    _, fin = rango_utc_del_dia(hasta)
    return s.exec(
        select(Venta).where(Venta.creada_at >= ini, Venta.creada_at < fin).order_by(Venta.numero)
    ).all()


@router.get("/exportar/ventas")
def exportar_ventas(
    desde: str | None = Query(default=None),
    hasta: str | None = Query(default=None),
    s: Session = Depends(get_session),
):
    d = date.fromisoformat(desde) if desde else hoy_local()
    h = date.fromisoformat(hasta) if hasta else d
    filas = []
    for v in _ventas_entre(s, d, h):
        local = a_local(v.creada_at)
        cobrado = v.total - v.descuento
        neto, iva = neto_iva(cobrado) if v.estado == "pagada" else (0, 0)
        filas.append([
            local.strftime("%d-%m-%Y"), local.strftime("%H:%M"), v.numero, v.estado,
            v.medio_pago, v.total, v.descuento, cobrado, neto, iva, v.propina,
        ])
    return _csv(
        filas,
        ["Fecha", "Hora", "N°", "Estado", "Medio de pago", "Bruto", "Descuento",
         "Cobrado", "Neto", "IVA", "Propina"],
        f"ventas_{d.isoformat()}_a_{h.isoformat()}.csv",
    )


@router.get("/exportar/detalle")
def exportar_detalle(
    desde: str | None = Query(default=None),
    hasta: str | None = Query(default=None),
    s: Session = Depends(get_session),
):
    """Una fila por producto vendido: sirve para ver qué se vende y para inventario."""
    d = date.fromisoformat(desde) if desde else hoy_local()
    h = date.fromisoformat(hasta) if hasta else d
    filas = []
    for v in _ventas_entre(s, d, h):
        if v.estado != "pagada":
            continue
        local = a_local(v.creada_at)
        for l in v.lineas:
            filas.append([
                local.strftime("%d-%m-%Y"), local.strftime("%H:%M"), v.numero,
                l.nombre, l.cantidad, l.precio_unitario, l.subtotal, v.medio_pago,
            ])
    return _csv(
        filas,
        ["Fecha", "Hora", "N° venta", "Producto", "Cantidad", "Precio", "Subtotal", "Medio de pago"],
        f"detalle_{d.isoformat()}_a_{h.isoformat()}.csv",
    )
