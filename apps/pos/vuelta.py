"""Volver atrás una actualización. Solo biblioteca estándar, y a propósito.

`apps/pos/__init__.py` llama a `recuperar` ANTES de que se importe cualquier
otra cosa del programa. Si una actualización quedó a medias —se cortó la luz
mientras se reemplazaban los archivos—, la caja tiene código de dos versiones,
y lo primero que se importe puede reventar. Acá no hay nada que pueda haber
quedado a medias: solo json, os y shutil.

La lista `_cambios.json` dice qué pisó la actualización (`cambiados`, con su
original guardado al lado), qué agregó (`nuevos`) y si terminó (`completo`).
La escribe `actualizar._instalar` ANTES de reemplazar el primer archivo.

Volver atrás sigue las mismas reglas: antes de tocar nada deja la lista
«a medias», y cada archivo se reemplaza de una vez —temporal, a disco,
renombrar—, nunca se escribe encima. Así un corte de luz a mitad de la vuelta
no deja ni código mezclado ni este mismo archivo roto: al abrir, la vuelta se
termina (lo encontró la revisión de Codex).
"""
from __future__ import annotations

import hashlib
import json
import os

RESPALDO = "_version_anterior"
CAMBIOS = "_cambios.json"
TEMPORAL = ".kofe-nuevo"


def ruta_segura(raiz: str, rel: str) -> str | None:
    """Evita que una ruta con '../' apunte fuera de la carpeta del programa."""
    destino = os.path.normpath(os.path.join(raiz, rel))
    if not destino.startswith(os.path.normpath(raiz) + os.sep):
        return None
    return destino


def leer(raiz: str) -> dict | None:
    try:
        with open(os.path.join(raiz, RESPALDO, CAMBIOS), encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def escribir(ruta: str, datos: bytes) -> None:
    """Escribe y se asegura de que quedó en el disco, no en la memoria de
    Windows: sin eso, tras un corte de luz el archivo puede aparecer vacío."""
    with open(ruta, "wb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())


def _poner(origen: str, destino: str) -> None:
    """Pone una copia de `origen` en `destino` sin dejarlo nunca a medio escribir."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(origen, "rb") as f:
        datos = f.read()
    temporal = destino + TEMPORAL
    escribir(temporal, datos)
    os.replace(temporal, destino)


def anotar(raiz: str, datos: dict) -> None:
    """La lista se escribe de una vez: en un temporal que después reemplaza a la
    de verdad. Una lista escrita a medias sería peor que ninguna."""
    carpeta = os.path.join(raiz, RESPALDO)
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, CAMBIOS)
    temporal = ruta + ".nuevo"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporal, ruta)


def volver(raiz: str) -> dict:
    datos = leer(raiz)
    if not datos:
        return {"error": "No hay una versión anterior guardada para volver."}
    respaldo = os.path.join(raiz, RESPALDO)
    cambiados = list(datos.get("cambiados", []))
    nuevos = list(datos.get("nuevos", []))
    tocados: list[str] = []
    # Cada original se revisa ANTES de tocar nada: poner una copia dañada
    # dejaría la caja sin arrancar (lo encontró la revisión de Codex). Las
    # listas escritas antes de esa revisión no traen huellas.
    for rel, esperada in (datos.get("originales") or {}).items():
        try:
            with open(os.path.join(respaldo, rel), "rb") as f:
                sana = hashlib.sha256(f.read()).hexdigest() == esperada
        except OSError:
            sana = False
        if not sana:
            return {"error": f"La copia guardada de {rel} está dañada: no se tocó nada. "
                             "Avísale a soporte."}
    if datos.get("completo", True):
        # Antes de tocar el primer archivo: «a medias». Si se corta la luz entre
        # dos archivos, al abrir se termina la vuelta en vez de dejarla mezclada.
        try:
            anotar(raiz, dict(datos, completo=False))
        except Exception as e:
            return {"error": f"No se pudo volver atrás: {e}. No se cambió nada."}
    try:
        # Lo que un corte de luz dejó a medio escribir no sirve para nada.
        for rel in cambiados + nuevos:
            destino = ruta_segura(raiz, rel)
            if destino and os.path.exists(destino + TEMPORAL):
                os.remove(destino + TEMPORAL)
        for rel in cambiados:
            copia = os.path.join(respaldo, rel)
            destino = ruta_segura(raiz, rel)
            if destino and os.path.exists(copia):
                _poner(copia, destino)
                tocados.append(rel)
        for rel in nuevos:
            destino = ruta_segura(raiz, rel)
            if destino and os.path.exists(destino):
                os.remove(destino)
                tocados.append(rel)
    except Exception as e:
        # La lista queda: al abrir de nuevo se intenta otra vez.
        return {"error": f"No se pudo volver atrás: {e}"}
    # Se borra la lista: volver dos veces con la misma copia desharía la vuelta.
    try:
        os.remove(os.path.join(respaldo, CAMBIOS))
    except OSError:
        pass
    return {"ok": True, "archivos": tocados, "version": datos.get("desde", "")}


def recuperar(raiz: str) -> dict | None:
    """Si la última actualización quedó a medias, la deshace. None si no hacía falta.

    Deshacer y no terminar: el paquete ya no está, y los originales sí. Con
    ellos la caja vuelve entera a la versión que tenía, y el dueño puede
    actualizar de nuevo."""
    datos = leer(raiz)
    if not datos or datos.get("completo", True):
        return None
    r = volver(raiz)
    r["hacia"] = datos.get("hacia", "")
    return r
