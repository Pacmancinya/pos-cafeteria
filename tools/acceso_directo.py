"""Deja el icono de la caja en el escritorio.

## Por qué vive acá y no en `Kofe.py`

Porque `Kofe.py` **no viaja en las actualizaciones**. Es el guion de entrada que
PyInstaller compila DENTRO de `Kofe.exe`, así que el ejecutable siempre corre su
copia congelada y el `Kofe.py` suelto que está al lado no lo abre nadie.
Cambiarlo ahí obligaría a reconstruir y volver a bajar los 29 MB.

Este archivo, en cambio, es código suelto: lo reemplaza el actualizador como
cualquier otro, y lo llama `apps/pos/main.py` al arrancar.

Se hace UNA sola vez y queda la marca. Si el dueño después borra el acceso
directo es porque no lo quiere, y volver a crearlo cada mañana sería pelear con
él.
"""
from __future__ import annotations

import os
import subprocess
import sys

from core.config import NOMBRE_LOCAL, RAIZ

MARCA = os.path.join(RAIZ, ".acceso-directo")
NOMBRE = f"{NOMBRE_LOCAL} - Punto de venta"


def crear_si_falta() -> str:
    """Devuelve lo que hizo, para poder mirarlo. Nunca lanza."""
    if sys.platform != "win32":
        return ""
    ejecutable = os.path.join(RAIZ, "Kofe.exe")
    if not os.path.exists(ejecutable):
        # Corriendo desde el código, sin empaquetar: no hay a qué apuntar.
        return ""
    if os.path.exists(MARCA):
        return ""

    try:
        with open(MARCA, "w", encoding="utf-8") as f:
            f.write("El acceso directo del escritorio ya se creó una vez.\n"
                    "Borra este archivo si quieres que se vuelva a crear.\n")
    except OSError:
        return ""

    icono = os.path.join(RAIZ, "despliegue", "icono", "kofe.ico")
    if not os.path.exists(icono):
        icono = ejecutable

    # Se arma con el propio Windows (WScript.Shell): un .lnk es un formato
    # binario y no vale la pena escribirlo a mano ni agregar una dependencia.
    orden = (
        "$e=[Environment]::GetFolderPath('Desktop');"
        f"$d=Join-Path $e '{NOMBRE}.lnk';"
        "if(-not (Test-Path $d)){"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($d);"
        f"$s.TargetPath='{ejecutable}';"
        f"$s.WorkingDirectory='{RAIZ}';"
        f"$s.IconLocation='{icono}';"
        "$s.Description='Punto de venta de la cafeteria';"
        "$s.Save()}"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", orden],
            capture_output=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return f"Acceso directo «{NOMBRE}» dejado en el escritorio."
    except Exception:
        return ""      # un acceso directo que no se pudo crear no impide vender
