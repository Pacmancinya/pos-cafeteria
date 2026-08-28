"""Arma el ZIP de ACTUALIZACIÓN.

Este es el paquete chico (~120 KB) que se publica en el canal de
actualizaciones: trae SOLO el programa, no el motor. Es lo que baja la caja
cuando el dueño aprieta "Actualizar ahora".

Para armar la aplicación completa que se instala la primera vez (Kofe.exe y sus
56 MB), es el otro: `despliegue/construir_exe.py`.

La idea es la misma de Gesfact: se entrega una carpeta **chica** (solo el
código y los documentos) y en el primer doble clic se convierte en la app
completa — crea su entorno, instala lo que necesita y siembra la carta.

Lo que NO va en el ZIP, y por qué:
  .venv/       se regenera solo y pesa cientos de MB
  pos.db       es la base del local; si viaja, el local hereda ventas ajenas
  respaldos/   copias de esa base
  __pycache__  basura de Python

    .venv/Scripts/python -m despliegue.empaquetar
"""
from __future__ import annotations

import os
import sys
import zipfile
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "despliegue")
NOMBRE = "Kofe-actualizacion"

INCLUIR = [
    "Kofe.py",              # el lanzador de la aplicación: también se actualiza
    "INICIAR-POS.bat",
    "requirements.txt",
    "conftest.py",
    "README.md",
    "LEEME.md",
    "VERSIONES.md",
]
CARPETAS = ["core", "apps", "tools", "docs"]
IGNORAR_DIR = {"__pycache__", ".pytest_cache", ".venv", "respaldos",
               "despliegue", "datos-ventana"}
IGNORAR_ARCH = {".pyc", ".pyo", ".db", ".log"}


def archivos() -> list[tuple[str, str]]:
    """(ruta real, ruta dentro del zip)"""
    salida = []
    for f in INCLUIR:
        p = os.path.join(RAIZ, f)
        if os.path.exists(p):
            salida.append((p, f))
    for carpeta in CARPETAS:
        base = os.path.join(RAIZ, carpeta)
        for raiz, dirs, nombres in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORAR_DIR]
            for n in nombres:
                if os.path.splitext(n)[1] in IGNORAR_ARCH:
                    continue
                p = os.path.join(raiz, n)
                salida.append((p, os.path.relpath(p, RAIZ).replace("\\", "/")))
    return salida


def empaquetar() -> str:
    os.makedirs(SALIDA, exist_ok=True)
    destino = os.path.join(SALIDA, f"{NOMBRE}.zip")
    lista = archivos()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for real, dentro in lista:
            z.write(real, f"{NOMBRE}/{dentro}")
    return destino, lista


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    destino, lista = empaquetar()
    kb = os.path.getsize(destino) / 1024
    print(f"\n  {os.path.basename(destino)} · {len(lista)} archivos · {kb:.0f} KB")
    print(f"  {destino}")
    print(f"  Armado el {datetime.now():%d-%m-%Y %H:%M}\n")
    print("  Esto es una ACTUALIZACIÓN: reemplaza el programa de una caja que ya")
    print("  está instalada. Para instalar de cero va Kofe-instalar.zip.\n")
