# -*- coding: utf-8 -*-
"""Convierte kofe.svg en kofe.ico (el icono de la aplicación en Windows).

No usa Pillow ni nada externo: un .ico es una cabecera de 6 bytes, una entrada
de 16 bytes por tamaño, y los PNG pegados uno detrás del otro. Windows acepta
PNG dentro del .ico desde Vista.

Los PNG los dibuja Chrome, que ya está en la máquina y entiende SVG mejor que
cualquier conversor que pudiéramos instalar.

    .venv/Scripts/python despliegue/icono/hacer_icono.py
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(AQUI, "kofe.svg")
ICO = os.path.join(AQUI, "kofe.ico")

# 256 para el explorador en vista grande, 16 para la barra de tareas y la
# esquina de la ventana. Los del medio evitan que Windows escale a ojo.
TAMANOS = (256, 128, 64, 48, 32, 16)

CHROMES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def navegador() -> str:
    for c in CHROMES:
        if os.path.exists(c):
            return c
    raise SystemExit("No encontré Chrome ni Edge para dibujar el icono.")


def png_de(tam: int, carpeta: str, exe: str) -> bytes:
    destino = os.path.join(carpeta, f"{tam}.png")
    subprocess.run([
        exe, "--headless", "--disable-gpu", "--hide-scrollbars",
        # sin esto el PNG sale con fondo blanco y el icono queda dentro de un
        # cuadrado feo en la barra de tareas
        "--default-background-color=00000000",
        f"--window-size={tam},{tam}",
        f"--screenshot={destino}",
        "file:///" + SVG.replace("\\", "/"),
    ], capture_output=True, check=False)
    if not os.path.exists(destino):
        raise SystemExit(f"No se pudo dibujar el tamaño {tam}")
    with open(destino, "rb") as f:
        return f.read()


def escribir_ico(imagenes: list[tuple[int, bytes]], destino: str) -> None:
    # ICONDIR: reservado(0), tipo(1 = icono), cantidad
    cabecera = struct.pack("<HHH", 0, 1, len(imagenes))
    desplazamiento = len(cabecera) + 16 * len(imagenes)
    entradas, cuerpos = b"", b""
    for tam, datos in imagenes:
        # 256 se escribe como 0: el campo es de un byte y no le cabe
        ancho = alto = 0 if tam >= 256 else tam
        entradas += struct.pack(
            "<BBBBHHII", ancho, alto, 0, 0, 1, 32, len(datos), desplazamiento
        )
        cuerpos += datos
        desplazamiento += len(datos)
    with open(destino, "wb") as f:
        f.write(cabecera + entradas + cuerpos)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    exe = navegador()
    with tempfile.TemporaryDirectory() as tmp:
        imagenes = [(t, png_de(t, tmp, exe)) for t in TAMANOS]
    escribir_ico(imagenes, ICO)
    kb = os.path.getsize(ICO) / 1024
    print(f"  {ICO} · {len(TAMANOS)} tamaños · {kb:.1f} KB")
