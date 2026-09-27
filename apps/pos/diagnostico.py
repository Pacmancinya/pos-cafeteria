"""Lo que queda anotado cuando algo falla, y el paquete para mandarlo.

Hasta la 2.18 no quedaba nada. Los problemas llegaban como capturas por
WhatsApp: la caja que se quedaba pegada se diagnosticó leyendo código, porque
no había nada que mirar, y el `problema-ventana.txt` que se le pidió al local
en la 2.13 nunca llegó. Con un local eso se aguanta; con varios, no.

Ahora el servidor anota sus errores y lo que tarda demasiado, la pantalla le
avisa al servidor de los suyos, y el dueño baja todo en un solo archivo desde
Ayuda → Ajustes para mandarlo por WhatsApp.

El registro vive en `registros/`, que el actualizador nunca toca, y rota solo:
nunca pasa de unos 5 MB.
"""
from __future__ import annotations

import io
import json
import logging
import logging.handlers
import os
import platform
import sqlite3
import sys
import zipfile
from datetime import datetime

from core.config import APP_VERSION, DB_URL, RAIZ

CARPETA = os.getenv("POS_CARPETA_REGISTROS") or os.path.join(RAIZ, "registros")
ARCHIVO = os.path.join(CARPETA, "kofe.log")

log = logging.getLogger("kofe")


def preparar() -> None:
    """Deja el registro listo. Se puede llamar más de una vez."""
    if getattr(log, "_kofe_listo", False):
        return
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        os.makedirs(CARPETA, exist_ok=True)
        manejador = logging.handlers.RotatingFileHandler(
            ARCHIVO, maxBytes=1_000_000, backupCount=4, encoding="utf-8")
        manejador.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        log.addHandler(manejador)
    except OSError:
        pass          # sin disco escribible se sigue; lo que no se puede es no abrir
    log._kofe_listo = True


def _base() -> dict:
    ruta = DB_URL.split("///", 1)[-1] if DB_URL.startswith("sqlite") else ""
    if not ruta or not os.path.exists(ruta):
        return {"tipo": DB_URL.split(":", 1)[0]}
    salida: dict = {"archivo": os.path.basename(ruta),
                    "tamano_kb": round(os.path.getsize(ruta) / 1024)}
    try:
        c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=5)
        try:
            salida["modo"] = c.execute("PRAGMA journal_mode").fetchone()[0]
            salida["revision_rapida"] = c.execute("PRAGMA quick_check").fetchone()[0]
            for tabla in ("venta", "turno", "producto", "usuario", "retirocaja"):
                try:
                    salida[tabla] = c.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                except sqlite3.Error:
                    pass
            try:
                salida["ultima_venta"] = c.execute("SELECT MAX(creada_at) FROM venta").fetchone()[0]
            except sqlite3.Error:
                pass
        finally:
            c.close()
    except sqlite3.Error as e:
        salida["error"] = str(e)
    return salida


def resumen() -> dict:
    """Todo lo que ayuda a entender el problema, SIN los secretos del local:
    ni el PIN de red, ni la llave de las sesiones, ni la clave de descarga."""
    from apps.pos import local
    try:
        from tools.respaldo import estado_afuera, listar
        respaldos = listar()[:10]
        afuera = estado_afuera()
    except Exception as e:
        respaldos, afuera = [], {"error": str(e)}
    return {
        "version": APP_VERSION,
        "cuando": datetime.now().isoformat(timespec="seconds"),
        "local": local.nombre(),
        "sistema": platform.platform(),
        "python": sys.version.split()[0],
        "carpeta": RAIZ,
        "base": _base(),
        "respaldos": respaldos,
        "respaldo_afuera": afuera,
        "pin_de_red_de_fabrica": local.pin_es_de_fabrica(),
        "canal": local.canal(),
    }


def armar_paquete() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("resumen.json", json.dumps(resumen(), ensure_ascii=False, indent=2))
        if os.path.isdir(CARPETA):
            for nombre in sorted(os.listdir(CARPETA)):
                if nombre.startswith("kofe.log"):
                    z.write(os.path.join(CARPETA, nombre), "registro/" + nombre)
        # Lo que deja Kofe.py cuando no puede abrir la ventana (desde la 2.13).
        for carpeta in {RAIZ, os.path.dirname(os.path.abspath(sys.executable))}:
            apunte = os.path.join(carpeta, "problema-ventana.txt")
            if os.path.exists(apunte):
                z.write(apunte, "problema-ventana.txt")
                break
    return buf.getvalue()
