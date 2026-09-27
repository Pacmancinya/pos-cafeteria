"""Vuelve la base del local a un respaldo. Para soporte, con el programa CERRADO.

    .venv/Scripts/python tools/restaurar.py respaldos/pos-2026-09-10.db

Antes de pisar nada revisa que el respaldo esté sano y guarda la base actual en
`respaldos/antes-de-restaurar-<fecha>.db`: restaurar el respaldo equivocado no
puede costar las ventas de hoy. Esa copia no se borra sola (solo se podan las
`pos-*.db`).

Si esta caja ya tiene ventas, solo le pone encima un respaldo que se pueda
comprobar que es suyo: desde la 2.19 cada caja anota su identidad en la base
(ver respaldo._identidad), y cada respaldo la lleva. Con la carpeta de afuera
compartida entre sucursales, el respaldo de la otra está a un clic. Un respaldo
sin identidad —de antes de la 2.19— tampoco se pone encima sin preguntar. Para
hacerlo igual: `--sin-revisar-local`.

Copia con la API de respaldo de SQLite y no con un copiar-pegar del archivo,
por lo mismo que `respaldo.py`: es la única forma de que la copia salga entera.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from tools.respaldo import CARPETA, ruta_de_la_base  # noqa: E402


def _copiar(origen: str, destino: str) -> None:
    src = sqlite3.connect(origen)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _uno(base: str, consulta: str):
    try:
        c = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
        try:
            fila = c.execute(consulta).fetchone()
        finally:
            c.close()
        return fila[0] if fila else None
    except sqlite3.Error:
        return None


_IDENTIDAD = "SELECT valor FROM ajuste WHERE clave = 'instalacion_id'"


def restaurar(respaldo: str, sin_revisar_local: bool = False) -> dict:
    if not os.path.exists(respaldo):
        return {"ok": False, "detalle": f"No existe {respaldo}."}
    try:
        c = sqlite3.connect(f"file:{respaldo}?mode=ro", uri=True)
        try:
            sano = c.execute("PRAGMA integrity_check").fetchone()[0]
            ventas = c.execute("SELECT COUNT(*) FROM venta").fetchone()[0]
        finally:
            c.close()
    except sqlite3.Error as e:
        return {"ok": False, "detalle": f"Ese archivo no es una base de la caja: {e}"}
    if sano != "ok":
        return {"ok": False, "detalle": "Ese respaldo está dañado. Prueba con uno anterior."}

    base = ruta_de_la_base()
    if not base:
        return {"ok": False, "detalle": "La base no es SQLite: esto no aplica."}
    # None es «no se pudo contar»: una base dañada no se da por vacía (lo
    # encontró la revisión de Codex).
    ventas_aca = _uno(base, "SELECT COUNT(*) FROM venta") if os.path.exists(base) else 0
    if ventas_aca != 0 and not sin_revisar_local:
        # Una caja recién instalada —la que reemplaza a un computador que se
        # murió— no tiene ventas, y ahí restaurar es justo lo que hay que hacer.
        # Una que ya vende, o que no se puede leer, solo recibe un respaldo que
        # se sepa que es suyo: una base dañada con SU respaldo sí se arregla.
        suya, mia = _uno(respaldo, _IDENTIDAD), _uno(base, _IDENTIDAD)
        if not suya or not mia or suya != mia:
            if suya and mia:
                motivo = "es de otro local"
            elif not suya:
                motivo = "no trae con qué comprobar que sea de este local (es de antes de la 2.19)"
            else:
                motivo = "no se puede comparar con esta caja, que no tiene identidad"
            estado = (f"ya tiene {ventas_aca} ventas" if ventas_aca
                      else "tiene una base que no se pudo leer")
            return {"ok": False, "detalle": (
                f"Ese respaldo {motivo}, y esta caja {estado}. Si estás seguro de que es el "
                "correcto, repite con --sin-revisar-local.")}
    guardada = None
    if os.path.exists(base):
        os.makedirs(CARPETA, exist_ok=True)
        guardada = os.path.join(CARPETA, f"antes-de-restaurar-{datetime.now():%Y-%m-%d_%H%M%S}.db")
        _copiar(base, guardada)
    _copiar(respaldo, base)
    return {"ok": True, "ventas": ventas, "guardada": guardada}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    argumentos = [x for x in sys.argv[1:] if x != "--sin-revisar-local"]
    if len(argumentos) != 1:
        print("  Uso: .venv/Scripts/python tools/restaurar.py <respaldo.db> [--sin-revisar-local]")
        print("  Cierra el programa de la caja antes de correrlo.")
        sys.exit(2)
    r = restaurar(argumentos[0], sin_revisar_local="--sin-revisar-local" in sys.argv[1:])
    if not r["ok"]:
        print("  " + r["detalle"])
        sys.exit(1)
    print(f"  Listo: la base quedó como en el respaldo ({r['ventas']} ventas).")
    if r["guardada"]:
        print(f"  La base de antes quedó en {r['guardada']}")
