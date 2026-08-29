"""Sistema de actualizaciones.

Copiado del que ya funciona en la Biblioteca Láser, con las lecciones que
quedaron escritas en su `CONTEXTO-para-otro-agente.md`:

  · **Un archivo NUEVO tiene que llegar.** Allá el actualizador tomaba solo los
    archivos de la raíz del paquete, y un módulo nuevo nunca llegaba. Acá se
    copia el árbol completo (`apps/pos/api/...` incluido), porque este proyecto
    vive en subcarpetas.
  · **Nunca tocar los datos.** `pos.db`, `respaldos/` y `.venv/` quedan intactos:
    lo que se reemplaza es solo el código.
  · **Guardar la versión anterior** antes de pisar nada, por si hay que volver.
  · Los mensajes son para el dueño del local, no para un programador.

Después de actualizar hay que reiniciar el programa. Si se abrió con
INICIAR-POS.bat, se reinicia solo.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import urllib.request
import zipfile

from core.config import APP_NOMBRE, APP_VERSION, RAIZ, URL_VERSION

# Nunca se reemplazan: son del local, no del programa.
PROTEGIDOS = {"pos.db", "pos.db-wal", "pos.db-shm", ".env",
              # La llave que firma las sesiones es de ESTA caja: si se
              # reemplazara, todos tendrían que marcar su PIN de nuevo.
              ".secreto"}
CARPETAS_PROTEGIDAS = ("respaldos", "registros", ".venv", "__pycache__", ".git",
                       "despliegue",
                       # datos de la ventana (sesión del navegador incrustado)
                       "datos-ventana", "_internal")
EXTENSIONES = (".py", ".html", ".css", ".js", ".bat", ".md", ".txt", ".json")

RESPALDO = "_version_anterior"


def _tupla(v: str) -> tuple:
    """'2.10' es MAYOR que '2.9': hay que comparar por número, no por texto."""
    partes = []
    for t in str(v).split("."):
        try:
            partes.append(int(t))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def revisar() -> dict:
    """¿Hay una versión nueva publicada?"""
    if not URL_VERSION:
        return {"error": "Todavía no hay un canal de actualizaciones configurado."}
    try:
        req = urllib.request.Request(URL_VERSION, headers={"User-Agent": "PuntoDeVenta"})
        with urllib.request.urlopen(req, timeout=8) as r:
            info = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": "No pude conectarme para revisar. ¿Hay internet?", "detalle": str(e)}

    nueva = str(info.get("version", "0"))
    return {
        "ok": True,
        "actual": APP_VERSION,
        "actual_nombre": APP_NOMBRE,
        "disponible": nueva,
        "disponible_nombre": info.get("nombre", ""),
        "hay_nueva": _tupla(nueva) > _tupla(APP_VERSION),
        "novedades": info.get("novedades", ""),
        "zip": info.get("zip", ""),
    }


def _ruta_segura(rel: str) -> str | None:
    """Evita que un ZIP con '../' escriba fuera de la carpeta del programa."""
    destino = os.path.normpath(os.path.join(RAIZ, rel))
    if not destino.startswith(os.path.normpath(RAIZ) + os.sep):
        return None
    return destino


# Solo https: sin cifrar, cualquiera en la red del local podría meter código
# propio en la caja. La excepción es el mismo computador, que se usa para probar
# una actualización antes de publicarla (quien pueda servir ahí ya tiene la máquina).
def _origen_confiable(url: str) -> bool:
    if url.startswith("https://"):
        return True
    return url.startswith(("http://127.0.0.1", "http://localhost"))


def aplicar(url_zip: str) -> dict:
    """Descarga el paquete y reemplaza SOLO el código."""
    if not _origen_confiable(url_zip):
        return {"error": "La dirección de descarga no es segura (tiene que ser https)."}
    try:
        req = urllib.request.Request(url_zip, headers={"User-Agent": "PuntoDeVenta"})
        with urllib.request.urlopen(req, timeout=120) as r:
            crudo = r.read()
    except Exception as e:
        return {"error": f"No se pudo descargar la actualización: {e}"}

    respaldo = os.path.join(RAIZ, RESPALDO)
    cambiados: list[str] = []

    try:
        with zipfile.ZipFile(io.BytesIO(crudo)) as z:
            nombres = [n for n in z.namelist() if not n.endswith("/")]
            if not nombres:
                return {"error": "El paquete descargado venía vacío."}

            # Los ZIP traen todo colgando de una carpeta ("Punto-de-venta/" o
            # "pos-cafeteria-main/" si viene de GitHub). Se la sacamos.
            primeras = {n.split("/")[0] for n in nombres if "/" in n}
            prefijo = (primeras.pop() + "/") if len(primeras) == 1 else ""

            for n in nombres:
                rel = n[len(prefijo):] if prefijo and n.startswith(prefijo) else n
                if not rel:
                    continue
                partes = rel.split("/")
                if partes[0] in CARPETAS_PROTEGIDAS or partes[-1] in PROTEGIDOS:
                    continue
                if partes[-1].startswith("."):
                    continue
                if not rel.lower().endswith(EXTENSIONES):
                    continue

                destino = _ruta_segura(rel)
                if not destino:
                    continue

                datos = z.read(n)
                if os.path.exists(destino):
                    with open(destino, "rb") as f:
                        if f.read() == datos:
                            continue                      # ya está igual
                    copia = os.path.join(respaldo, rel)
                    os.makedirs(os.path.dirname(copia), exist_ok=True)
                    shutil.copy2(destino, copia)

                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "wb") as f:
                    f.write(datos)
                cambiados.append(rel)
    except zipfile.BadZipFile:
        return {"error": "El archivo descargado no es un paquete válido."}
    except Exception as e:
        return {"error": f"No se pudo instalar la actualización: {e}"}

    if not cambiados:
        return {"ok": True, "archivos": [], "sin_cambios": True,
                "aviso": "Ya tenías todos los archivos al día."}

    return {
        "ok": True,
        "archivos": cambiados,
        "aviso": "Listo. Hay que reiniciar el programa para usar la versión nueva.",
    }
