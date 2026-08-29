"""Deja el icono de la caja en el escritorio, y lo CORRIGE si quedó mal.

## Por qué vive acá y no en `Kofe.py`

Porque `Kofe.py` **no viaja en las actualizaciones**. Es el guion de entrada que
PyInstaller compila DENTRO de `Kofe.exe`, así que el ejecutable siempre corre su
copia congelada y el `Kofe.py` suelto que está al lado no lo abre nadie.
Cambiarlo ahí obligaría a reconstruir y volver a bajar los 29 MB.

Este archivo, en cambio, es código suelto: lo reemplaza el actualizador como
cualquier otro, y lo llama `apps/pos/main.py` al arrancar.

## Por qué la marca es una libreta y no una bandera

Antes era una bandera: existía el archivo `.acceso-directo` y no se hacía nada
más, nunca. Eso funcionó hasta que el acceso directo quedó apuntando al lugar
equivocado — a `INICIAR-POS.bat`, que abre una ventana negra de consola que se
queda al lado de la caja toda la jornada. Con una bandera no había forma de
arreglarlo desde una actualización.

Ahora la marca guarda **a qué apuntaba y con qué receta**. Si la receta cambió,
se reescribe una sola vez. Si el dueño borró el acceso directo, no se vuelve a
crear nunca: pelearle cada mañana sería peor que no tener icono.

El nombre empieza con punto a propósito: `apps/pos/actualizar.py` descarta todo
archivo que empiece con punto, así que la libreta sobrevive a las
actualizaciones. Si se le cambia el nombre, hay que dejarle el punto.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from core.config import NOMBRE_LOCAL, RAIZ

MARCA = os.path.join(RAIZ, ".acceso-directo")
NOMBRE = f"{NOMBRE_LOCAL} - Punto de venta"

# Sube de número cuando cambia A QUÉ apunta el acceso directo. Es lo único que
# hace que una caja ya instalada corrija su icono: si no cambia, no se toca nada.
#   1 · apuntaba al lanzador que se estaba usando (Kofe.exe o INICIAR-POS.bat)
#   2 · sin congelar apunta a pythonw.exe + Kofe.py, para que no haya consola
RECETA = 2


def _destino() -> tuple[str, str]:
    """(a qué apunta, con qué argumentos). Cadena vacía si no hay a qué apuntar.

    Se deriva de `sys.executable`, o sea del intérprete que ESTÁ CORRIENDO ahora
    mismo. Es la única fuente honesta: si la caja está abierta, ese ejecutable
    sirve en este computador. Adivinar la ruta y escribirla sin comprobarla
    dejaría un icono que no abre nada, que es peor que no tener icono.
    """
    if getattr(sys, "frozen", False):
        exe = os.path.join(RAIZ, "Kofe.exe")
        return (exe, "") if os.path.exists(exe) else ("", "")

    # Sin congelar, el que da la ventana sin consola es pythonw.exe. Si estamos
    # corriendo bajo python.exe (probando desde la terminal), se usa su hermano.
    yo = os.path.abspath(sys.executable)
    candidato = yo
    if os.path.basename(yo).lower() == "python.exe":
        hermano = os.path.join(os.path.dirname(yo), "pythonw.exe")
        if os.path.exists(hermano):
            candidato = hermano

    guion = os.path.join(RAIZ, "Kofe.py")
    if (os.path.basename(candidato).lower() == "pythonw.exe"
            and os.path.exists(candidato) and os.path.exists(guion)):
        # Kofe.py va relativo porque el acceso directo lleva WorkingDirectory:
        # así el argumento no necesita comillas dentro de las comillas.
        return candidato, "Kofe.py"

    # Último recurso: el lanzador de siempre. Abre consola, pero abre.
    bat = os.path.join(RAIZ, "INICIAR-POS.bat")
    return (bat, "") if os.path.exists(bat) else ("", "")


def _donde_puede_estar() -> list[str]:
    """Las dos carpetas donde puede vivir el .lnk.

    La de Inicio también, porque `docs/INSTALACION.md` le dice al dueño que
    ARRASTRE el acceso directo a `shell:startup` para que la caja se abra sola.
    Arrastrar MUEVE: el del escritorio desaparece. Si solo mirásemos el
    escritorio, concluiríamos que lo borró y no corregiríamos nunca el único
    acceso que el local usa de verdad.
    """
    carpetas = []
    for var, cola in (("USERPROFILE", "Desktop"),
                      ("APPDATA", r"Microsoft\Windows\Start Menu\Programs\Startup")):
        base = os.environ.get(var)
        if base:
            carpetas.append(os.path.join(base, cola))
    return [os.path.join(c, NOMBRE + ".lnk") for c in carpetas]


def _libreta() -> dict:
    try:
        with open(MARCA, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        # No existe, o es la marca vieja (texto suelto de la versión 1). Las dos
        # cosas significan lo mismo: no sabemos a qué apunta.
        return {}


def _anotar(lnk: str, destino: str, args: str) -> None:
    try:
        with open(MARCA, "w", encoding="utf-8") as f:
            json.dump({"receta": RECETA, "lnk": lnk, "destino": destino,
                       "args": args,
                       "_": "Borra este archivo si quieres que el acceso directo "
                            "se vuelva a crear."}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _ps(valor: str) -> str:
    """Un literal para PowerShell, entre comillas SIMPLES.

    Tienen que ser simples: la orden completa viaja como un solo elemento de la
    lista de subprocess, que la envuelve en comillas dobles. Una comilla doble
    adentro rompería el envoltorio, y además PowerShell empezaría a expandir
    `$`. Dentro de comillas simples, la única que hay que escapar es ella misma,
    duplicándola.
    """
    return "'" + str(valor).replace("'", "''") + "'"


def _escribir(lnk: str, destino: str, args: str) -> bool:
    """Crea o REESCRIBE el .lnk. True si el comando corrió sin reventar.

    Se arma con el propio Windows (WScript.Shell): un .lnk es un formato binario
    y no vale la pena escribirlo a mano ni agregar una dependencia. CreateShortcut
    sobre uno que ya existe lo abre con sus propiedades y `.Save()` lo pisa, así
    que no hay que borrarlo antes.
    """
    icono = os.path.join(RAIZ, "despliegue", "icono", "kofe.ico")
    if not os.path.exists(icono):
        icono = destino

    orden = (
        f"$d={_ps(lnk)};"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($d);"
        f"$s.TargetPath={_ps(destino)};"
        f"$s.Arguments={_ps(args)};"
        f"$s.WorkingDirectory={_ps(RAIZ)};"
        f"$s.IconLocation={_ps(icono + ',0')};"
        "$s.Description='Punto de venta de la cafeteria';"
        "$s.WindowStyle=1;"
        "$s.Save()"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", orden],
            capture_output=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False          # un acceso directo que no se pudo crear no impide vender


def crear_si_falta() -> str:
    """Devuelve lo que hizo, para poder mirarlo. Nunca lanza."""
    if sys.platform != "win32":
        return ""

    destino, args = _destino()
    if not destino:
        return ""

    libreta = _libreta()
    existentes = [p for p in _donde_puede_estar() if os.path.exists(p)]

    # Primera vez: se crea en el escritorio y se anota.
    if not libreta:
        # Puede haber un .lnk de la versión 1, cuando la marca era texto suelto
        # y no decía dónde. Si está, se corrige; si no, se crea.
        lnk = existentes[0] if existentes else _donde_puede_estar()[0]
        if not _escribir(lnk, destino, args):
            return ""
        _anotar(lnk, destino, args)
        return f"Acceso directo «{NOMBRE}» dejado en el escritorio."

    # Lo borró el dueño. No se vuelve a crear: pelearle cada mañana es peor que
    # no tener icono.
    if not existentes:
        return ""

    # Ya está y apunta a donde corresponde.
    if libreta.get("receta") == RECETA and libreta.get("destino") == destino:
        return ""

    # Está, pero quedó apuntando a otra cosa. Se corrige UNA vez: al anotar la
    # receta nueva, la condición de arriba deja de cumplirse.
    lnk = libreta.get("lnk") if libreta.get("lnk") in existentes else existentes[0]
    if not _escribir(lnk, destino, args):
        return ""
    _anotar(lnk, destino, args)
    return f"Acceso directo «{NOMBRE}» corregido: ahora abre la caja sin ventana negra."
