"""Arma Kofe.exe y el paquete que se le entrega al local.

    .venv/Scripts/python -m despliegue.construir_exe

## La decisión de fondo

El .exe trae adentro Python y las librerías (fastapi, uvicorn, sqlmodel,
pywebview…), pero **no** trae el código del punto de venta: ese viaja como
archivos .py sueltos al lado del .exe, y `Kofe.py` los carga metiendo su propia
carpeta en `sys.path`.

    el .exe es el motor · la carpeta es el programa

Por qué así, y no congelando todo:

  · El actualizador reemplaza .py, .js, .css y .html sueltos. Una actualización
    pesa ~100 KB. Si el código viviera dentro del .exe, cada arreglo de una coma
    obligaría a bajar 40 MB — y a reemplazar el ejecutable mientras corre, que
    en Windows no se puede.
  · Si el .exe no trajera las librerías, el notebook del local tendría que
    instalar Python. Eso ya falló una vez en la vida real y es justamente lo
    que estamos sacando de en medio.

Se probó: se congeló un lanzador así, se editó un .py suelto SIN recompilar
nada, y el .exe tomó el cambio.

## Lo que sale

    despliegue/Kofe/            ← la carpeta que se le pasa al local (~45 MB)
      Kofe.exe                  ← doble clic acá
      _internal/                ← Python y las librerías. No se toca.
      apps/ core/ tools/        ← el programa. Esto es lo que se actualiza.
      docs/  LEEME.md
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

from core.config import APP_VERSION

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "despliegue")
TRABAJO = os.path.join(SALIDA, "_construccion")
DESTINO = os.path.join(SALIDA, "Kofe")
ICONO = os.path.join(SALIDA, "icono", "kofe.ico")

# Estas librerías van ADENTRO del .exe. PyInstaller no las encuentra solo
# porque el código que las usa se carga desde archivos sueltos que él no mira.
LIBRERIAS = ["fastapi", "uvicorn", "sqlmodel", "pydantic", "sqlalchemy",
             "tzdata", "webview", "python_multipart", "anyio", "starlette",
             # pythonnet y clr_loader van SÍ O SÍ acá y no basta con que
             # PyInstaller los detecte solo: clr_loader lee sus propios .py en
             # tiempo de ejecución (netfx.py, util/…) y sin ellos el .exe abre
             # con "Failed to resolve Python.Runtime.Loader.Initialize".
             # Pasó de verdad en el notebook, con el paquete ya entregado.
             "pythonnet", "clr_loader"]

# El programa: lo que viaja suelto y lo que el actualizador reemplaza.
CARPETAS = ["core", "apps", "tools", "docs"]
ARCHIVOS = ["LEEME.md", "README.md", "requirements.txt", "conftest.py",
            "INICIAR-POS.bat", "Kofe.py"]
IGNORAR_DIR = {"__pycache__", ".pytest_cache", ".venv", "respaldos",
               "registros", "despliegue", "datos-ventana"}
IGNORAR_ARCH = {".pyc", ".pyo", ".db", ".log"}


def construir_exe() -> None:
    orden = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir",              # onefile se descomprime en %TEMP% cada vez que
                                 # se abre: más lento y más sospechoso para el
                                 # antivirus, sin ninguna ventaja acá
        "--windowed",            # sin ventana negra detrás
        "--name", "Kofe",
        "--distpath", os.path.join(TRABAJO, "dist"),
        "--workpath", os.path.join(TRABAJO, "build"),
        "--specpath", TRABAJO,
    ]
    for lib in LIBRERIAS:
        orden += ["--collect-all", lib]
    # El código del POS NO se congela: viaja suelto para poder actualizarlo.
    for modulo in ("apps", "core", "tools"):
        orden += ["--exclude-module", modulo]
    if os.path.exists(ICONO):
        orden += ["--icon", ICONO]
    orden.append(os.path.join(RAIZ, "Kofe.py"))

    print("  Congelando el motor (esto demora un par de minutos)...")
    r = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit("PyInstaller falló")


def copiar_el_programa() -> int:
    """Los .py sueltos, al lado del .exe."""
    copiados = 0
    for archivo in ARCHIVOS:
        origen = os.path.join(RAIZ, archivo)
        if os.path.exists(origen):
            shutil.copy2(origen, os.path.join(DESTINO, archivo))
            copiados += 1
    for carpeta in CARPETAS:
        base = os.path.join(RAIZ, carpeta)
        for raiz, dirs, nombres in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORAR_DIR]
            for n in nombres:
                if os.path.splitext(n)[1] in IGNORAR_ARCH:
                    continue
                origen = os.path.join(raiz, n)
                rel = os.path.relpath(origen, RAIZ)
                destino = os.path.join(DESTINO, rel)
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copy2(origen, destino)
                copiados += 1
    # El icono viaja aparte: `despliegue/` no se copia entero.
    if os.path.exists(ICONO):
        d = os.path.join(DESTINO, "despliegue", "icono")
        os.makedirs(d, exist_ok=True)
        shutil.copy2(ICONO, os.path.join(d, "kofe.ico"))
        copiados += 1
    return copiados


def pesar(carpeta: str) -> float:
    total = 0
    for raiz, _, nombres in os.walk(carpeta):
        total += sum(os.path.getsize(os.path.join(raiz, n)) for n in nombres)
    return total / (1024 * 1024)


def comprimir() -> str:
    destino = os.path.join(SALIDA, f"Kofe-instalar-v{APP_VERSION}.zip")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, _, nombres in os.walk(DESTINO):
            for n in nombres:
                p = os.path.join(raiz, n)
                z.write(p, os.path.join("Kofe", os.path.relpath(p, DESTINO)))
    return destino


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("\n  Kofe · construyendo la aplicación\n")
    if os.path.exists(TRABAJO):
        shutil.rmtree(TRABAJO, ignore_errors=True)
    if os.path.exists(DESTINO):
        shutil.rmtree(DESTINO, ignore_errors=True)

    construir_exe()
    shutil.move(os.path.join(TRABAJO, "dist", "Kofe"), DESTINO)
    n = copiar_el_programa()
    print(f"  {n} archivos del programa, sueltos al lado del .exe")

    shutil.rmtree(TRABAJO, ignore_errors=True)
    zip_final = comprimir()

    print(f"\n  {DESTINO}  ·  {pesar(DESTINO):.0f} MB")
    print(f"  {zip_final}  ·  {os.path.getsize(zip_final) / (1024*1024):.0f} MB")
    print(f"  Armado el {datetime.now():%d-%m-%Y %H:%M}\n")
    print("  Se entrega el ZIP. Se extrae y se abre Kofe.exe. No necesita")
    print("  instalar Python ni nada más.\n")
