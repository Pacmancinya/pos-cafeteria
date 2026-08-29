"""Arma `D:\\Kofe`, la carpeta donde está todo lo del proyecto, ordenado.

    .venv/Scripts/python -m despliegue.ordenar_carpeta

El código vive en un repositorio y tiene la estructura que necesita un
programa, que no es la que necesita una persona buscando algo. Esta carpeta es
para lo segundo: entrar y encontrar el instalador, las guías o el registro de
cierres sin saber qué es `apps/pos/api`.

Se regenera cada vez que se publica una versión, así que **no se edita a mano**:
lo que se ponga acá se pierde en la próxima corrida. Lo único que se conserva es
`4 - Registros del local`, que es donde el dueño deja sus archivos.
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime

from core.config import APP_NOMBRE, APP_VERSION

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.getenv("KOFE_CARPETA", r"D:\Kofe")

# (carpeta, [(origen, nombre con el que se guarda)])
PLAN = [
    ("1 - Instalar en un local", [
        (f"despliegue/Kofe-instalar-v{APP_VERSION}.zip", None),
        ("docs/INSTALACION.md", "Cómo instalar, paso a paso.md"),
    ]),
    ("2 - Guías", [
        ("LEEME.md", "Cómo se usa la caja.md"),
        ("docs/SII.md", "Conectar la boleta del SII.md"),
        ("docs/PUBLICAR-ACTUALIZACIONES.md", "Cómo publico una versión nueva.md"),
    ]),
    ("3 - Actualizaciones", [
        (f"despliegue/Kofe-actualizacion-v{APP_VERSION}.zip", None),
        ("VERSIONES.md", "Qué cambió en cada versión.md"),
    ]),
    ("5 - Para el que programa", [
        ("README.md", "Cómo está hecho por dentro.md"),
        ("docs/CONTRATO.md", "Las decisiones que mandan.md"),
    ]),
]

# Esta NO se toca nunca: es del dueño.
DEL_DUENO = "4 - Registros del local"

LEEME = """KOFE — PUNTO DE VENTA
=====================

Versión {version} · "{nombre}"
Ordenado el {fecha}

Qué hay en cada carpeta
-----------------------

  1 - Instalar en un local
      El ZIP que se le pasa a un local nuevo, y la guía de instalación.
      Se extrae y se abre Kofe.exe. No necesita instalar nada más.

  2 - Guías
      Cómo se usa la caja, cómo conectar la boleta del SII, y cómo publico
      yo una versión nueva. Se abren con el Bloc de notas o con Word.

  3 - Actualizaciones
      El paquete chico (unos 160 KB) para una caja que YA está instalada,
      y el detalle de qué cambió en cada versión.

      Normalmente no hace falta: la caja se actualiza sola desde
      github.com/Pacmancinya/pos-cafeteria cuando hay algo nuevo.

  4 - Registros del local
      Acá van los CSV de cierres que genera la caja (los deja en su propia
      carpeta "registros"), y lo que se exporte para el contador.
      ESTA CARPETA ES TUYA: no se borra ni se reordena.

  5 - Para el que programa
      Cómo está construido y las decisiones que no se cambian sin pensar.

El código
---------

El programa vive en:
    {codigo}

Es un repositorio de git conectado a GitHub. No se mueve de ahí: si se
cambia de lugar, se rompen el repositorio y las rutas.

Esta carpeta se regenera con:
    .venv/Scripts/python -m despliegue.ordenar_carpeta
"""


def copiar(origen: str, carpeta: str, nombre: str | None) -> bool:
    ruta = os.path.join(RAIZ, origen)
    if not os.path.exists(ruta):
        return False
    destino = os.path.join(carpeta, nombre or os.path.basename(origen))
    shutil.copy2(ruta, destino)
    return True


def ordenar() -> tuple[int, list[str]]:
    os.makedirs(DESTINO, exist_ok=True)
    copiados, faltantes = 0, []

    for carpeta, archivos in PLAN:
        ruta = os.path.join(DESTINO, carpeta)
        # Se rehace de cero: si una versión vieja dejó un ZIP, no puede quedar
        # al lado del nuevo — nadie sabría cuál entregar.
        if os.path.exists(ruta):
            shutil.rmtree(ruta, ignore_errors=True)
        os.makedirs(ruta, exist_ok=True)
        for origen, nombre in archivos:
            if copiar(origen, ruta, nombre):
                copiados += 1
            else:
                faltantes.append(origen)

    # La del dueño se crea si falta y NO se toca si ya está.
    del_dueno = os.path.join(DESTINO, DEL_DUENO)
    os.makedirs(del_dueno, exist_ok=True)
    aviso = os.path.join(del_dueno, "Acá van tus registros.txt")
    if not os.path.exists(aviso):
        with open(aviso, "w", encoding="utf-8") as f:
            f.write(
                "Esta carpeta es tuya y no la toca nadie.\n\n"
                "La caja deja un CSV por mes con una fila por cada cierre, en la\n"
                "carpeta 'registros' que está al lado de Kofe.exe. Cópialos acá\n"
                "cuando quieras tenerlos juntos.\n\n"
                "También sirve para lo que exportes desde El día →\n"
                "'Descargar para el contador'.\n")

    with open(os.path.join(DESTINO, "LEEME PRIMERO.txt"), "w", encoding="utf-8") as f:
        f.write(LEEME.format(version=APP_VERSION, nombre=APP_NOMBRE,
                             fecha=f"{datetime.now():%d-%m-%Y}", codigo=RAIZ))
    return copiados, faltantes


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    copiados, faltantes = ordenar()
    print(f"\n  {DESTINO}  ·  {copiados} archivos ordenados\n")
    for carpeta, _ in PLAN:
        print(f"    {carpeta}")
    print(f"    {DEL_DUENO}   (tuya, no se toca)")
    if faltantes:
        print("\n  No estaban (¿falta construir?):")
        for f in faltantes:
            print("    -", f)
    print()
