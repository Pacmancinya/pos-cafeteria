"""Los errores de la pantalla, y el paquete de diagnóstico para el dueño."""
from __future__ import annotations

import re
import time
from collections import deque
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from apps.pos import diagnostico, local, sesion

router = APIRouter(prefix="/api/v1", tags=["diagnostico"])


class EventoIn(BaseModel):
    tipo: str = Field(default="error", max_length=40)
    mensaje: str = Field(max_length=500)
    detalle: str = Field(default="", max_length=2000)
    donde: str = Field(default="", max_length=200)


# Este endpoint lo pueden llamar también los televisores, que no tienen PIN de
# red (ver acceso.LIBRES). Por eso tiene tope: un TV con un error en un bucle, o
# alguien del Wi-Fi mandando basura, no puede llenar el disco de la caja.
_recientes: deque = deque()
TOPE_POR_MINUTO = 30


@router.post("/diagnostico/evento", status_code=204)
def evento(datos: EventoIn, request: Request):
    ahora = time.monotonic()
    while _recientes and ahora - _recientes[0] > 60:
        _recientes.popleft()
    if len(_recientes) >= TOPE_POR_MINUTO:
        return Response(status_code=204)
    _recientes.append(ahora)
    quien = request.client.host if request.client else "?"
    diagnostico.log.warning(
        "pantalla %s · %s · %s%s%s", quien, datos.tipo[:40], datos.mensaje[:500],
        f" · en {datos.donde[:200]}" if datos.donde else "",
        f" · {datos.detalle[:2000]}" if datos.detalle else "")
    return Response(status_code=204)


@router.get("/diagnostico")
def paquete(quien: dict = Depends(sesion.exige("config"))):
    """Un .zip con el registro y el estado de la caja, para mandarlo a soporte."""
    nombre_local = re.sub(r"[^a-z0-9]+", "-", local.nombre().lower()).strip("-") or "caja"
    nombre = f"diagnostico-{nombre_local}-{datetime.now():%Y-%m-%d-%H%M}.zip"
    return Response(diagnostico.armar_paquete(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
