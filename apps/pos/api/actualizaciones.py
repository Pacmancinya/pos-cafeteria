"""Revisar e instalar actualizaciones desde la propia caja."""
from __future__ import annotations

import os
import threading

from fastapi import APIRouter
from pydantic import BaseModel

from apps.pos import actualizar
from core.config import APP_NOMBRE, APP_VERSION

router = APIRouter(prefix="/api/v1", tags=["actualizaciones"])

# Código con el que salimos para pedirle a INICIAR-POS.bat que nos vuelva a
# levantar. Cualquier otro código significa "se cerró de verdad".
SALIDA_REINICIO = 3

# Quién nos vuelve a abrir después de actualizar.
#
#   · Abierto con INICIAR-POS.bat: nadie. El .bat mira el código de salida 3 y
#     vuelve a levantar el servidor solo.
#   · Abierto con Kofe.exe: no hay .bat que mire nada, así que el lanzador deja
#     acá una función que lanza una copia nueva antes de que esta se muera.
#
# Se asigna desde Kofe.py. Si vale None, estamos en el mundo del .bat.
reiniciador = None


class InstalarIn(BaseModel):
    zip: str = ""


@router.get("/version")
def version():
    return {"version": APP_VERSION, "nombre": APP_NOMBRE}


@router.get("/novedades")
def novedades():
    """El historial de versiones, leído de VERSIONES.md.

    Se lee del archivo y no de una lista en el código para que no haya dos
    lugares donde decir lo mismo: VERSIONES.md ya es la fuente de verdad y se
    actualiza al publicar.
    """
    import os
    import re

    from core.config import RAIZ
    ruta = os.path.join(RAIZ, "VERSIONES.md")
    filas = []
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                # Las filas de la tabla: | 1.4 | Nombre | fecha | qué trae |
                if not linea.startswith("|"):
                    continue
                partes = [c.strip() for c in linea.strip().strip("|").split("|")]
                if len(partes) < 4 or partes[0] in ("Versión", "---"):
                    continue
                if not re.match(r"^\d", partes[0]):
                    continue
                filas.append({"version": partes[0], "nombre": partes[1],
                              "fecha": partes[2], "novedades": partes[3]})
    except OSError:
        pass
    filas.reverse()          # lo más nuevo primero, que es lo que se quiere ver
    return {"actual": APP_VERSION, "versiones": filas}


@router.get("/actualizacion")
def revisar():
    return actualizar.revisar()


@router.post("/actualizacion")
def instalar(datos: InstalarIn):
    """Instala la versión nueva y, si se puede, reinicia el programa solo."""
    url = datos.zip
    if not url:
        info = actualizar.revisar()
        if not info.get("ok"):
            return info
        if not info.get("hay_nueva"):
            return {"ok": True, "sin_cambios": True, "aviso": "Ya estás al día."}
        url = info.get("zip", "")

    resultado = actualizar.aplicar(url)
    if resultado.get("ok") and resultado.get("archivos"):
        resultado["reiniciando"] = True
        threading.Timer(1.5, _cerrar_para_reiniciar).start()
    return resultado


def _cerrar_para_reiniciar() -> None:
    """Se cierra para volver con la versión nueva.

    El orden importa: primero se lanza el reemplazo (que espera a que este
    proceso muera) y recién después nos morimos. Al revés, la copia nueva
    chocaría con el cerrojo de instancia única de la vieja.
    """
    if reiniciador:
        try:
            reiniciador()
        except Exception:
            pass          # si el relanzamiento falla, igual hay que cerrarse:
                          # el código viejo ya no está en disco
    os._exit(SALIDA_REINICIO)
