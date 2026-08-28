"""Respaldo de la base.

Un local que vende todos los días no puede tener su historial en un solo archivo
de un solo computador. Esto saca una copia en tres momentos naturales:

  · al abrir el programa en la mañana,
  · al cerrar la caja en la noche,
  · cuando alguien aprieta el botón.

Usa la API de respaldo de SQLite (`Connection.backup`), no una copia del archivo:
copiar el .db mientras está en uso puede dejar una copia corrupta justo cuando
más se necesita.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from core.config import DB_URL, RAIZ, ZONA

CARPETA = os.path.join(RAIZ, "respaldos")
CUANTOS_GUARDAR = 30


def ruta_de_la_base() -> str | None:
    """El archivo .db, o None si la base no es SQLite (ej. Postgres)."""
    if not DB_URL.startswith("sqlite"):
        return None
    return DB_URL.split("///", 1)[-1]


def respaldar(motivo: str = "manual") -> dict:
    origen = ruta_de_la_base()
    if not origen:
        return {"ok": False, "detalle": "La base no es SQLite; el respaldo lo maneja el servidor."}
    if not os.path.exists(origen):
        return {"ok": False, "detalle": "Todavía no hay base que respaldar."}

    os.makedirs(CARPETA, exist_ok=True)
    hoy = datetime.now(ZONA).strftime("%Y-%m-%d")
    destino = os.path.join(CARPETA, f"pos-{hoy}.db")

    src = sqlite3.connect(origen)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)          # copia consistente aunque la caja esté vendiendo
    finally:
        dst.close()
        src.close()

    borrados = _podar()
    return {
        "ok": True,
        "archivo": os.path.basename(destino),
        "carpeta": CARPETA,
        "tamano_kb": round(os.path.getsize(destino) / 1024),
        "motivo": motivo,
        "borrados": borrados,
    }


def _podar() -> int:
    """Deja solo los últimos respaldos: si no, la carpeta crece para siempre."""
    copias = sorted(
        (f for f in os.listdir(CARPETA) if f.startswith("pos-") and f.endswith(".db")),
        reverse=True,
    )
    borrados = 0
    for viejo in copias[CUANTOS_GUARDAR:]:
        try:
            os.remove(os.path.join(CARPETA, viejo))
            borrados += 1
        except OSError:
            pass
    return borrados


def listar() -> list[dict]:
    if not os.path.isdir(CARPETA):
        return []
    salida = []
    for f in sorted(os.listdir(CARPETA), reverse=True):
        if not (f.startswith("pos-") and f.endswith(".db")):
            continue
        ruta = os.path.join(CARPETA, f)
        salida.append({
            "archivo": f,
            "tamano_kb": round(os.path.getsize(ruta) / 1024),
            "fecha": f[4:-3],
        })
    return salida


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = respaldar("manual")
    print(f"  {r}")
