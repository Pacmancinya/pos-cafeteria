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
    # Las pantallas son OTRO programa desde la 2.2: acá va su guía, para que el
    # dueño encuentre las dos cosas en el mismo lugar aunque sean dos programas.
    ("5 - Pantallas del menú", [
        ("apps/pos/static/pantallas.html", "Pantalla del local (respaldo).html"),
        ("apps/pos/static/pantallas-simple.html",
         "Pantalla para TV viejo (respaldo).html"),
    ]),
    ("6 - Para el que programa", [
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
      Se extrae y se abre Kofe.exe (o INICIAR-POS.bat si Windows bloquea
      el .exe). Queda un icono en el escritorio y de ahí en adelante se
      abre con ese icono, sin ventana negra al lado.

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

  5 - Pantallas del menú
      Los televisores que muestran la carta. Los sirve la propia caja:
      cada TV abre una dirección de la red y listo. Las direcciones
      salen en la pestaña Carta, con botón de copiar.
      Acá hay una copia de las dos pantallas, por si alguna vez hay que
      abrirlas a mano sin la caja.

  6 - Para el que programa
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


def ordenar() -> tuple[int, list[str], list[str], list[str]]:
    # Cada carpeta se rehace de cero, así que dos entradas con el mismo nombre
    # harían que la segunda borre lo de la primera. Mejor que reviente acá.
    nombres = [c for c, _ in PLAN]
    assert len(nombres) == len(set(nombres)), f"carpeta repetida en PLAN: {nombres}"

    os.makedirs(DESTINO, exist_ok=True)
    copiados, faltantes, intactas = 0, [], []

    for carpeta, archivos in PLAN:
        ruta = os.path.join(DESTINO, carpeta)

        # Si falta algo que iba a ir acá, esta carpeta NO se toca.
        #
        # Se rehace de cero cuando se puede, porque si una versión vieja dejó un
        # ZIP no puede quedar al lado del nuevo: nadie sabría cuál entregar.
        # Pero borrar primero y descubrir después que el archivo nuevo no existe
        # deja la carpeta VACÍA — y así se pierde el instalador de la versión
        # anterior, que era lo único que había para un local nuevo. Pasó de
        # verdad: basta con ordenar sin haber construido el .exe.
        sin_construir = [o for o, _ in archivos
                         if not os.path.exists(os.path.join(RAIZ, o))]
        if sin_construir:
            faltantes.extend(sin_construir)
            intactas.append(carpeta)
            continue

        if os.path.exists(ruta):
            shutil.rmtree(ruta, ignore_errors=True)
        os.makedirs(ruta, exist_ok=True)
        for origen, nombre in archivos:
            if copiar(origen, ruta, nombre):
                copiados += 1

    # Las carpetas que YA NO están en el PLAN se barren.
    #
    # Sin esto, renumerar una carpeta —lo que pasó al agregar «5 - Pantallas del
    # menú» y correr la de programación al 6— deja la vieja ahí para siempre, y el
    # dueño se encuentra con dos carpetas que dicen casi lo mismo.
    #
    # Solo se barren las que EMPIEZAN CON UN NÚMERO, que son las que pone este
    # programa. Si el dueño dejó una carpeta suya acá, no se toca: esta carpeta
    # también es de él.
    esperadas = {c for c, _ in PLAN} | {DEL_DUENO}
    barridas = []
    for nombre in sorted(os.listdir(DESTINO)):
        ruta_vieja = os.path.join(DESTINO, nombre)
        if not os.path.isdir(ruta_vieja) or nombre in esperadas:
            continue
        if not nombre[:1].isdigit():
            continue                      # no la puso este programa
        shutil.rmtree(ruta_vieja, ignore_errors=True)
        barridas.append(nombre)

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
    return copiados, faltantes, intactas, barridas


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    copiados, faltantes, intactas, barridas = ordenar()
    print(f"\n  {DESTINO}  ·  {copiados} archivos ordenados\n")
    for carpeta, _ in PLAN:
        print(f"    {carpeta}")
    print(f"    {DEL_DUENO}   (tuya, no se toca)")
    if barridas:
        print("\n  Carpetas viejas que ya no van, borradas:")
        for b in barridas:
            print("    -", b)
    if intactas:
        print("\n  Estas se dejaron COMO ESTABAN, porque falta construir algo")
        print("  de lo que iba adentro. Lo que ya había sigue ahí:")
        for c in intactas:
            print("    -", c)
    if faltantes:
        print("\n  No estaban (¿falta construir?):")
        for f in faltantes:
            print("    -", f)
    print()
