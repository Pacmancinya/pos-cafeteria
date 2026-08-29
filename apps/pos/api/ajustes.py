"""Las preferencias del local.

Hoy hay una sola —el margen sugerido— y aun así vive en la base y no en el
navegador: cuánto le gana el local a lo que vende es una decisión del NEGOCIO.
En el localStorage se perdería al reinstalar y sería distinta abriendo la caja
desde un tablet.

La tabla es clave/valor en texto para que la próxima preferencia no obligue a
una migración. Quien lee sabe qué esperaba y convierte; si el texto quedó malo
—alguien editó la base a mano— se devuelve el valor por defecto en vez de
reventar: una preferencia rota no puede dejar al local sin poder cobrar.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.db.models import Ajuste
from apps.pos.db.session import get_session
from core.config import MARGEN_SUGERIDO, REDONDEO_PRECIO
from core.schemas import AjustesIn

router = APIRouter(prefix="/api/v1", tags=["ajustes"])

POR_DEFECTO = {"margen_sugerido": MARGEN_SUGERIDO}


def _leer(s: Session) -> dict:
    guardados = {a.clave: a.valor for a in s.exec(select(Ajuste)).all()}
    salida = {}
    for clave, defecto in POR_DEFECTO.items():
        crudo = guardados.get(clave)
        if crudo is None:
            salida[clave] = defecto
            continue
        try:
            salida[clave] = type(defecto)(crudo)
        except (TypeError, ValueError):
            salida[clave] = defecto
    return salida


@router.get("/ajustes")
def ver(s: Session = Depends(get_session),
        quien: dict = Depends(sesion.quien_es)):
    """Lo lee cualquiera que esté en la caja: el cajero también necesita el
    margen para que la pantalla le sugiera un precio."""
    datos = _leer(s)
    # El redondeo no se configura: va acá para que la pantalla no lo repita
    # escrito a mano y después queden dos números distintos.
    datos["redondeo_precio"] = REDONDEO_PRECIO
    return datos


@router.put("/ajustes")
def guardar(datos: AjustesIn, s: Session = Depends(get_session),
            quien: dict = Depends(sesion.exige("config"))):
    """Cambiarlas es del dueño: es cuánto gana el local, no una preferencia
    de pantalla."""
    for clave, valor in datos.model_dump().items():
        fila = s.get(Ajuste, clave)
        if fila:
            fila.valor = str(valor)
        else:
            fila = Ajuste(clave=clave, valor=str(valor))
        s.add(fila)
    s.commit()
    salida = _leer(s)
    salida["redondeo_precio"] = REDONDEO_PRECIO
    return salida
