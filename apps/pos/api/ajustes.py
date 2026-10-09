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

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from apps.pos import acceso, local, sesion
from apps.pos.api import config as puerta_config
from apps.pos.db.models import Ajuste
from apps.pos.db.session import get_session
from core.codigos import FORMATO_BALANZA_POR_DEFECTO, validar_formato_balanza
from core.config import (BLOQUEO_MINUTOS, DESCUENTOS_RAPIDOS, MARGEN_SUGERIDO, MEDIOS_PAGO,
                         MENSAJE_TICKET, REDONDEO_PRECIO, REDONDEOS_PRECIO,
                         TECLADO_EN_PANTALLA, puede)
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
    # Apagada de fábrica. Con el formato de la balanza prendido, un código que
    # empieza con 25 se COBRA por el monto que trae adentro, y el dígito
    # verificador se calcula con lápiz: en un local sin balanza eso sería un
    # cobro a mano sin permiso de cobro a mano. Solo la prende quien la tiene.
    "usar_balanza": 0,
    # ---- Config → Mi local / Cobro (2.33) ----
    # Cada valor de fábrica es lo que la caja hacía antes de poder elegirlo: una
    # caja que se actualiza sigue cobrando y imprimiendo igual hasta que el dueño
    # decida otra cosa. Las listas se guardan como texto separado por comas (la
    # tabla es de texto) y se leen de vuelta como listas.
    "mensaje_ticket": MENSAJE_TICKET,
    "medios_pago": ",".join(MEDIOS_PAGO),
    "pago_mixto": 1,
    "propinas": 1,
    "propina_sugerida": "",
    "propina_solo_tarjeta": 0,
    "descuentos_rapidos": ",".join(str(n) for n in DESCUENTOS_RAPIDOS),
    "redondeo_precio": REDONDEO_PRECIO,
}

LISTAS = ("medios_pago", "propina_sugerida", "descuentos_rapidos")


def _porcentajes(crudo: str) -> list[int]:
    """'10,15,20' → [10, 15, 20]. Lo que no sea un porcentaje entre 1 y 100 se ignora:
    una base editada a mano no puede dejar botones imposibles en el cobro."""
    salida = []
    for trozo in str(crudo).split(","):
        trozo = trozo.strip()
        if trozo.isdigit() and 1 <= int(trozo) <= 100 and int(trozo) not in salida:
            salida.append(int(trozo))
    return sorted(salida)[:6]


def _leer(s: Session) -> dict:
    guardados = {a.clave: a.valor for a in s.exec(select(Ajuste)).all()}
    salida = {}
    for clave, defecto in POR_DEFECTO.items():
        crudo = guardados.get(clave)
        if clave in LISTAS:
            crudo = defecto if crudo is None else crudo
            if clave == "medios_pago":
                lista = [m for m in MEDIOS_PAGO if m in str(crudo).split(",")]
                # Sin ninguna forma de pago no se podría cobrar: una lista rota o vacía
                # vuelve a las cuatro de siempre.
                salida[clave] = lista or list(MEDIOS_PAGO)
            else:
                salida[clave] = _porcentajes(crudo)
            continue
        if clave == "mensaje_ticket":
            salida[clave] = " ".join(str(crudo if crudo is not None else defecto).split()) or defecto
            continue
        if clave == "formato_balanza":
            try:
                salida[clave] = validar_formato_balanza(json.loads(crudo))
                salida["formato_balanza_roto"] = False
            except (TypeError, ValueError, RecursionError):
                salida[clave] = validar_formato_balanza(defecto)
                # Nunca guardado es una cosa; guardado y roto es otra. Si se leyera
                # con el de fábrica, 250 g de jamón ($2.248) se cobrarían como el
                # «ticket 123» por $250. Se muestra el de fábrica, pero no se cobra.
                salida["formato_balanza_roto"] = crudo is not None
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
    if salida["usar_balanza"] not in (0, 1):
        salida["usar_balanza"] = 0
    for clave in ("pago_mixto", "propinas", "propina_solo_tarjeta"):
        # Una base editada a mano no puede dejar esto en un valor raro: lo que no es
        # 0 se lee como el valor de fábrica (mixto y propinas prendidos; solo-tarjeta, no).
        if salida[clave] not in (0, 1):
            salida[clave] = POR_DEFECTO[clave]
    if salida["redondeo_precio"] not in REDONDEOS_PRECIO:
        salida["redondeo_precio"] = REDONDEO_PRECIO
    salida["margen_sugerido"] = min(max(salida.get("margen_sugerido", 0), 0), 95)
    salida["bloqueo_minutos"] = min(max(salida.get("bloqueo_minutos", BLOQUEO_MINUTOS), 1), 30)
    if salida["canal_actualizaciones"] not in local.CANALES:
        salida["canal_actualizaciones"] = "estable"
    return salida


def _completo(s: Session) -> dict:
    datos = _leer(s)
    # Desde la 2.33 el redondeo del precio sugerido se elige en Config → Cobro; el
    # servidor sigue siendo quien lo dice, así la pantalla nunca lo repite escrito a mano.
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
def guardar(datos: AjustesIn, request: Request, respuesta: Response,
            s: Session = Depends(get_session),
            quien: dict = Depends(sesion.exige_entrar)):
    """Cambiarlas es del dueño: es cuánto gana el local, no una preferencia
    de pantalla."""
    # `exclude_unset` NO es un detalle: sin él, pydantic rellena las claves que
    # NO vinieron con su valor por defecto, y este bucle las escribe todas. O
    # sea que mover el margen sugerido —que manda una sola clave— apagaba de
    # paso el teclado en pantalla, en silencio.
    cambios = datos.model_dump(exclude_unset=True)
    if set(cambios) <= {"margen_sugerido"}:
        # El margen también se mueve desde la ficha de un producto, sin pasar por
        # Config: ahí basta con tener el permiso, como siempre.
        if not puede(quien["rol"], "config", quien.get("permisos", "")):
            raise HTTPException(
                403, f"{quien['nombre'] or 'Este usuario'} no tiene permiso para esto. "
                     "Lo puede hacer el dueño.")
    else:
        # El resto es de Config: pide el PIN reciente de alguien con el permiso.
        quien = puerta_config.autoridad(request, respuesta, s, quien)
        if not puede(quien["rol"], "config", quien.get("permisos", "")):
            raise HTTPException(
                403, f"{quien['nombre'] or 'Este usuario'} no tiene permiso para esto. "
                     "Lo puede hacer el dueño.")
    carpeta = (cambios.get("respaldo_afuera") or "").strip()
    if carpeta:
        problema = _carpeta_usable(carpeta)
        if problema:
            raise HTTPException(422, problema)
        cambios["respaldo_afuera"] = carpeta
    for clave, valor in cambios.items():
        if clave == "formato_balanza":
            texto = json.dumps(valor)
        elif clave in LISTAS:
            texto = ",".join(str(n) for n in valor)
        else:
            texto = str(valor)
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
                  quien: dict = Depends(puerta_config.exige())):
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
def ver_red(quien: dict = Depends(puerta_config.exige())):
    """El PIN que piden los tablets y otros computadores del local. Solo el
    dueño lo ve: es la llave de la caja desde la red."""
    return {"pin": local.pin_de_red(), "de_fabrica": local.pin_es_de_fabrica(),
            "fijo": local.pin_por_variable()}


@router.post("/red/pin")
def cambiar_pin(datos: PinRedIn, respuesta: Response, s: Session = Depends(get_session),
                quien: dict = Depends(puerta_config.exige())):
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
def lugares(quien: dict = Depends(puerta_config.exige())):
    """Las carpetas de este computador que se sincronizan con la nube, y los
    pendrives conectados: los lugares que tienen sentido para la segunda copia."""
    from tools.respaldo import lugares_sugeridos
    return lugares_sugeridos()
