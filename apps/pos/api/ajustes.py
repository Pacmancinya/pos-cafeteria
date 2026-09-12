"""Las preferencias del local, sus datos y el PIN de red.

Viven en la base y no en el navegador: cuánto le gana el local a lo que vende,
cómo se llama, su RUT o su PIN de red son decisiones del NEGOCIO. En el
localStorage se perderían al reinstalar y serían distintas abriendo la caja
desde un tablet.

La tabla es clave/valor en texto para que la próxima preferencia no obligue a
una migración. Quien lee sabe qué esperaba y convierte; si el texto quedó malo
—alguien editó la base a mano— se devuelve el valor por defecto en vez de
reventar: una preferencia rota no puede dejar al local sin poder cobrar.
"""
from __future__ import annotations

import json
import os
import re
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from apps.pos import acceso, local, sesion
from apps.pos.db.models import Ajuste
from apps.pos.db.session import get_session
from core.codigos import FORMATO_BALANZA_POR_DEFECTO, validar_formato_balanza
from core.config import BLOQUEO_MINUTOS, MARGEN_SUGERIDO, REDONDEO_PRECIO, TECLADO_EN_PANTALLA
from core.schemas import AjustesIn

router = APIRouter(prefix="/api/v1", tags=["ajustes"])

POR_DEFECTO = {
    "usar_inventario": 1,
    "margen_sugerido": MARGEN_SUGERIDO,
    # Se guarda como 0/1 y no como booleano: la tabla es de texto.
    "teclado_en_pantalla": int(TECLADO_EN_PANTALLA),
    "bloqueo_minutos": BLOQUEO_MINUTOS,
    "canal_actualizaciones": "estable",
    "respaldo_afuera": "",
    "formato_balanza": FORMATO_BALANZA_POR_DEFECTO,
}


def _leer(s: Session) -> dict:
    guardados = {a.clave: a.valor for a in s.exec(select(Ajuste)).all()}
    salida = {}
    for clave, defecto in POR_DEFECTO.items():
        crudo = guardados.get(clave)
        if clave == "formato_balanza":
            try:
                salida[clave] = validar_formato_balanza(json.loads(crudo))
            except (TypeError, ValueError, RecursionError):
                salida[clave] = validar_formato_balanza(defecto)
            continue
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
    if salida["usar_inventario"] not in (0, 1):
        salida["usar_inventario"] = 1
    salida["margen_sugerido"] = min(max(salida.get("margen_sugerido", 0), 0), 95)
    salida["bloqueo_minutos"] = min(max(salida.get("bloqueo_minutos", BLOQUEO_MINUTOS), 1), 30)
    if salida["canal_actualizaciones"] not in local.CANALES:
        salida["canal_actualizaciones"] = "estable"
    return salida


def _completo(s: Session) -> dict:
    datos = _leer(s)
    # El redondeo no se configura: va acá para que la pantalla no lo repita
    # escrito a mano y después queden dos números distintos.
    datos["redondeo_precio"] = REDONDEO_PRECIO
    try:
        from tools.respaldo import estado_afuera
        datos["respaldo_afuera_estado"] = estado_afuera()
    except Exception:
        datos["respaldo_afuera_estado"] = {}
    return datos


def _carpeta_usable(ruta: str) -> str | None:
    """None si sirve; si no, qué le pasa, dicho para el dueño."""
    if not os.path.isdir(ruta):
        return "Esa carpeta no existe en este computador."
    try:
        with tempfile.NamedTemporaryFile(dir=ruta, prefix=".kofe-prueba-"):
            pass
    except OSError:
        return "En esa carpeta no se puede escribir."
    return None


@router.get("/ajustes")
def ver(s: Session = Depends(get_session),
        quien: dict = Depends(sesion.quien_es)):
    """Lo lee cualquiera que esté en la caja: el cajero también necesita el
    margen para que la pantalla le sugiera un precio, y el tiempo de bloqueo.
    Los secretos (el PIN de red) NO van acá: van en /red, solo para el dueño."""
    return _completo(s)


@router.put("/ajustes")
def guardar(datos: AjustesIn, s: Session = Depends(get_session),
            quien: dict = Depends(sesion.exige("config"))):
    """Cambiarlas es del dueño: es cuánto gana el local, no una preferencia
    de pantalla."""
    # `exclude_unset` NO es un detalle: sin él, pydantic rellena las claves que
    # NO vinieron con su valor por defecto, y este bucle las escribe todas. O
    # sea que mover el margen sugerido —que manda una sola clave— apagaba de
    # paso el teclado en pantalla, en silencio.
    cambios = datos.model_dump(exclude_unset=True)
    carpeta = (cambios.get("respaldo_afuera") or "").strip()
    if carpeta:
        problema = _carpeta_usable(carpeta)
        if problema:
            raise HTTPException(422, problema)
        cambios["respaldo_afuera"] = carpeta
    for clave, valor in cambios.items():
        texto = json.dumps(valor) if clave == "formato_balanza" else str(valor)
        fila = s.get(Ajuste, clave)
        if fila:
            fila.valor = texto
        else:
            fila = Ajuste(clave=clave, valor=texto)
        s.add(fila)
    s.commit()
    return _completo(s)


# ---------------------------------------------------------------------------
# Los datos del local
# ---------------------------------------------------------------------------
class LocalIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)
    rut: str = Field(default="", max_length=14)
    direccion: str = Field(default="", max_length=80)


@router.get("/local")
def ver_local():
    """Cómo se llama el local, su RUT y su dirección. Lo que ve el público."""
    return local.datos()


@router.put("/local")
def guardar_local(datos: LocalIn, s: Session = Depends(get_session),
                  quien: dict = Depends(sesion.exige("config"))):
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(422, "El local necesita un nombre.")
    rut = ""
    if datos.rut.strip():
        rut = local.rut_normalizado(datos.rut)
        if not rut:
            raise HTTPException(422, "Ese RUT no es válido: revisa el dígito verificador.")
    local.guardar(s, local_nombre=nombre, local_rut=rut,
                  local_direccion=datos.direccion.strip())
    return local.datos()


# ---------------------------------------------------------------------------
# El PIN de red
# ---------------------------------------------------------------------------
class PinRedIn(BaseModel):
    pin: str = Field(default="", max_length=8)


@router.get("/red")
def ver_red(quien: dict = Depends(sesion.exige("config"))):
    """El PIN que piden los tablets y otros computadores del local. Solo el
    dueño lo ve: es la llave de la caja desde la red."""
    return {"pin": local.pin_de_red(), "de_fabrica": local.pin_es_de_fabrica(),
            "fijo": local.pin_por_variable()}


@router.post("/red/pin")
def cambiar_pin(datos: PinRedIn, respuesta: Response, s: Session = Depends(get_session),
                quien: dict = Depends(sesion.exige("config"))):
    """Cambia el PIN de red. Sin PIN en el pedido, inventa uno de 6 dígitos.
    Los equipos que ya habían entrado tienen que escribir el nuevo."""
    if local.pin_por_variable():
        raise HTTPException(409, "El PIN de red lo fijó la instalación (POS_PIN) "
                                 "y no se cambia desde la caja.")
    pin = (datos.pin or "").strip() or local.pin_nuevo()
    if not re.fullmatch(r"\d{4,8}", pin):
        raise HTTPException(422, "El PIN de red son de 4 a 8 números.")
    if pin == local.PIN_DE_FABRICA:
        raise HTTPException(422, "Ese es el PIN de fábrica, el mismo de todas las cajas. Elige otro.")
    local.guardar(s, pin_red=pin)
    # Quien lo cambió desde un tablet entró con el PIN viejo, y su galleta dejó
    # de valer en este mismo instante. Se le renueva: si no, el dueño quedaría
    # afuera de la caja por cambiar el PIN, y un primer arranque hecho desde un
    # tablet no podría terminar (lo encontró la revisión de Codex).
    acceso.renovar_galleta(respuesta)
    return {"pin": pin, "de_fabrica": False, "fijo": False}


# ---------------------------------------------------------------------------
# Dónde dejar la copia de afuera
# ---------------------------------------------------------------------------
@router.get("/respaldo/lugares")
def lugares(quien: dict = Depends(sesion.exige("config"))):
    """Las carpetas de este computador que se sincronizan con la nube, y los
    pendrives conectados: los lugares que tienen sentido para la segunda copia."""
    from tools.respaldo import lugares_sugeridos
    return lugares_sugeridos()
