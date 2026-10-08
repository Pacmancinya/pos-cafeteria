"""Arma Gespoint-Instalar-vX.Y.exe, el instalador de Windows.

    .venv/Scripts/python -m despliegue.construir_exe          # primero la carpeta
    .venv/Scripts/python -m despliegue.construir_instalador   # despues el instalador

Toma la misma carpeta que `construir_exe.py` deja en `despliegue/Gespoint/` (la que
tambien va dentro del zip de instalacion) y la envuelve con Inno Setup 6
(`despliegue/instalador/gespoint.iss`). El .exe queda en `despliegue/`, junto a los zips.

Inno Setup es gratis. Si falta: `winget install --id JRSoftware.InnoSetup -e`.
Tambien se puede indicar donde esta con la variable GESPOINT_ISCC (siguen valiendo las
viejas CAJATERSA_ISCC y CAJACLARA_ISCC).

El instalador instala por usuario, sin pedir administrador, y NO toca los datos del
local al instalar encima ni al desinstalar (ver el .iss).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime

from core.config import APP_VERSION

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "despliegue")
ORIGEN = os.path.join(SALIDA, "Gespoint")
SCRIPT = os.path.join(SALIDA, "instalador", "gespoint.iss")


def encontrar_iscc() -> str | None:
    """El compilador de Inno Setup, o None si no esta en este computador."""
    explicito = (os.environ.get("GESPOINT_ISCC") or os.environ.get("CAJATERSA_ISCC")
                 or os.environ.get("CAJACLARA_ISCC"))
    if explicito and os.path.isfile(explicito):
        return explicito
    en_path = shutil.which("ISCC")
    if en_path:
        return en_path
    candidatos = []
    for variable, subcarpeta in (("LOCALAPPDATA", "Programs"),
                                 ("ProgramFiles(x86)", ""),
                                 ("ProgramFiles", "")):
        base = os.environ.get(variable)
        if base:
            candidatos.append(os.path.join(base, subcarpeta, "Inno Setup 6", "ISCC.exe"))
    return next((c for c in candidatos if os.path.isfile(c)), None)


def ordenes(iscc: str, version: str = APP_VERSION, origen: str = ORIGEN,
            salida: str = SALIDA) -> list[str]:
    """La linea de comandos de ISCC. Aparte para poder probarla sin Inno Setup."""
    return [iscc, "/Q",
            f"/DVersionApp={version}",
            f"/DOrigen={origen}",
            f"/DSalida={salida}",
            SCRIPT]


def construir() -> str:
    if not os.path.isfile(os.path.join(ORIGEN, "Gespoint.exe")):
        raise SystemExit(
            "  Falta construir la aplicacion primero (no existe "
            f"{os.path.join(ORIGEN, 'Gespoint.exe')}).\n"
            "  Corre:  .venv/Scripts/python -m despliegue.construir_exe")
    iscc = encontrar_iscc()
    if not iscc:
        raise SystemExit(
            "  No encuentro Inno Setup 6 (ISCC.exe).\n"
            "  Instalalo con:  winget install --id JRSoftware.InnoSetup -e\n"
            "  o indica donde esta con la variable GESPOINT_ISCC.")
    r = subprocess.run(ordenes(iscc), cwd=RAIZ, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit("  Inno Setup fallo al armar el instalador")
    destino = os.path.join(SALIDA, f"Gespoint-Instalar-v{APP_VERSION}.exe")
    if not os.path.isfile(destino):
        raise SystemExit(f"  Inno Setup termino bien pero no dejo {destino}")
    return destino


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("\n  Gespoint · armando el instalador\n")
    exe = construir()
    print(f"  {exe}  ·  {os.path.getsize(exe) / (1024 * 1024):.0f} MB")
    print(f"  Armado el {datetime.now():%d-%m-%Y %H:%M}\n")
    print("  Se entrega este .exe: doble clic y Siguiente. Instala sin pedir")
    print("  administrador y no toca las ventas de un local que ya lo tenga.\n")
