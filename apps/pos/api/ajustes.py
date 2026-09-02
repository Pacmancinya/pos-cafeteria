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
from core.config import MARGEN_SUGERIDO, REDONDEO_PRECIO, TECLADO_EN_PANTALLA
from core.schemas import AjustesIn

router = APIRouter(prefix="/api/v1", tags=["ajustes"])

POR_DEFECTO = {
    "margen_sugerido": MARGEN_SUGERIDO,
    # Se guarda como 0/1 y no como booleano: la tabla es de texto.
    "teclado_en_pantalla": int(TECLADO_EN_PANTALLA),
}


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
    # Lo que se guardó alguna vez fuera de rango no puede seguir mandando: el
    # `le=1` del schema solo se aplica al ESCRIBIR, así que un 2 en la tabla
    # pasaba entero y `!!2` prendía el teclado igual.
    salida["teclado_en_pantalla"] = 1 if salida.get("teclado_en_pantalla") else 0
    salida["margen_sugerido"] = min(max(salida.get("margen_sugerido", 0), 0), 95)
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
    # `exclude_unset` NO es un detalle: sin él, pydantic rellena las claves que
    # NO vinieron con su valor por defecto, y este bucle las escribe todas. O
    # sea que mover el margen sugerido —que manda una sola clave— apagaba de
    # paso el teclado en pantalla, en silencio. Hoy no se nota porque el defecto
    # coincide; el día que alguien lo prenda para una pantalla táctil, tocar el
    # margen se lo apaga y no hay forma de saber por qué.
    for clave, valor in datos.model_dump(exclude_unset=True).items():
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
