# -*- coding: utf-8 -*-
"""Kofe — la aplicación de escritorio del punto de venta.

Esto es lo que se congela con PyInstaller y queda como `Kofe.exe`. El .exe trae
adentro Python y las librerías (fastapi, uvicorn, sqlmodel, pywebview…), pero
**no** trae el código del punto de venta: ese sigue viviendo en archivos .py
sueltos al lado del .exe.

Por qué esa división, que es la decisión de fondo de todo este archivo:

  · El actualizador (`apps/pos/actualizar.py`) baja un ZIP y reemplaza .py, .js,
    .css y .html sueltos. Una actualización pesa 90 KB. Si el código viajara
    dentro del .exe, cada arreglo de una coma obligaría a bajar 40 MB y a
    reemplazar el ejecutable mientras se está ejecutando — que en Windows no se
    puede.
  · Al revés, si el .exe no trajera las librerías, el notebook del local tendría
    que instalar Python, que es exactamente lo que estamos sacando.

O sea: **el .exe es el motor, la carpeta es el programa.** Lo que cambia seguido
va afuera; lo que no cambia nunca va adentro.

⚠️ **ESTE ARCHIVO NO VIAJA EN LAS ACTUALIZACIONES.** Es el guion de entrada que
PyInstaller compila DENTRO del .exe, así que el ejecutable siempre corre su copia
congelada y el `Kofe.py` suelto que queda al lado no lo abre nadie. Cambiar algo
acá obliga a reconstruir el .exe y a que el local baje los 29 MB otra vez. Si lo
que quieres agregar puede vivir en `apps/` o en `tools/`, ponlo ahí: eso sí se
actualiza. (El acceso directo del escritorio empezó acá y hubo que moverlo a
`tools/acceso_directo.py` justamente por esto.)

Se ejecuta igual sin congelar, para probar:

    .venv/Scripts/python Kofe.py
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# 1. Dónde estamos parados
# ---------------------------------------------------------------------------
# Congelado, `sys.executable` es Kofe.exe y su carpeta es la carpeta del
# programa. Sin congelar, es este mismo archivo. En los dos casos hay que
# meter esa carpeta en sys.path a mano: PyInstaller pone primero su bodega
# interna (_MEIPASS), donde el código del POS no está.
if getattr(sys, "frozen", False):
    CARPETA = os.path.dirname(os.path.abspath(sys.executable))
else:
    CARPETA = os.path.dirname(os.path.abspath(__file__))

os.chdir(CARPETA)
if CARPETA not in sys.path:
    sys.path.insert(0, CARPETA)


# ---------------------------------------------------------------------------
# 1b. Quitarle a los archivos la marca de "bajado de internet"
# ---------------------------------------------------------------------------
def quitar_marca_de_descarga(carpeta: str) -> int:
    """Windows le pega una marca a TODO lo que sale de un ZIP descargado.

    La marca es un flujo alternativo NTFS llamado `Zone.Identifier` con
    `ZoneId=3` (internet). Le queda pegada a cada archivo extraído — en el
    paquete entregado eran **1.615** — y **.NET se niega a cargar una DLL
    marcada así**. El síntoma es que la ventana no abre nunca y el error dice:

        Failed to resolve Python.Runtime.Loader.Initialize

    Es exactamente el botón "Desbloquear" de las propiedades del archivo, pero
    hecho solo, porque nadie tiene por qué saber que ese botón existe. Se
    ejecuta ANTES de importar pywebview, que es quien dispara la carga de .NET.

    Pasó de verdad, con el paquete ya en el notebook del local.
    """
    quitadas = 0
    for raiz, _, nombres in os.walk(carpeta):
        for n in nombres:
            try:
                os.remove(os.path.join(raiz, n) + ":Zone.Identifier")
                quitadas += 1
            except OSError:
                pass          # lo normal: ese archivo no venía marcado
    return quitadas


def hace_falta_desbloquear() -> bool:
    """El propio ejecutable sirve de señal.

    Si el paquete se bajó, Windows marcó TODO, el .exe incluido. Y si el .exe
    no está marcado, no hay nada que revisar: recorrer los 1.600 archivos igual
    costaría 200 ms en cada arranque para no hacer nada.
    """
    yo = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.exists(os.path.abspath(yo) + ":Zone.Identifier")


if sys.platform == "win32" and hace_falta_desbloquear():
    quitar_marca_de_descarga(CARPETA)

# ---------------------------------------------------------------------------
# 2. Librerías que hay que meter DENTRO del .exe
# ---------------------------------------------------------------------------
# Se ven sin uso y no lo están: PyInstaller decide qué empaqueta leyendo los
# `import` de este archivo. El código del POS queda afuera y él nunca lo mira,
# así que si estas líneas no estuvieran, el .exe saldría sin fastapi adentro y
# reventaría en el local. NO BORRAR aunque el editor las marque en gris.
import fastapi              # noqa: F401,E402
import pydantic             # noqa: F401,E402
import python_multipart     # noqa: F401,E402  (los formularios del PIN)
import sqlmodel             # noqa: F401,E402
import tzdata               # noqa: F401,E402  (Windows no trae zonas horarias)
import uvicorn              # noqa: E402
import webview              # noqa: E402

NOMBRE_VENTANA_BASE = "Caja"
# Sin esto, Windows agrupa la ventana bajo "Python" y le pone su icono en la
# barra de tareas, aunque el .exe tenga el nuestro.
ID_EN_LA_BARRA = "Kofe.PuntoDeVenta"
ICONO = os.path.join(CARPETA, "despliegue", "icono", "kofe.ico")
CERROJO = "Kofe-punto-de-venta-8090"     # nombre del mutex de instancia única
ESPERA_MAXIMA = 25                        # segundos que le damos al servidor


# ---------------------------------------------------------------------------
# 3. Instancia única
# ---------------------------------------------------------------------------
def tomar_el_cerrojo() -> bool:
    """True si somos la primera copia; False si ya hay otra caja abierta.

    Un mutex con nombre y no "¿está ocupado el puerto 8090?": el puerto se
    libera con retraso cuando el proceso muere feo, y ahí el dueño se queda sin
    poder abrir su propia caja. El mutex lo suelta Windows al morir el proceso,
    siempre, incluso si lo matan desde el administrador de tareas.
    """
    ERROR_ALREADY_EXISTS = 183
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    # Se guarda en un global para que el handle viva lo mismo que el proceso:
    # si el recolector de basura se lo lleva, el cerrojo se suelta solo.
    global _handle_cerrojo
    _handle_cerrojo = k32.CreateMutexW(None, False, CERROJO)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


_handle_cerrojo = None


def traer_al_frente() -> None:
    """Si ya había una caja abierta, la mostramos en vez de abrir otra.

    Al dueño le da lo mismo por qué no se abrió una segunda ventana: lo que
    espera del segundo doble clic es ver su caja.
    """
    u32 = ctypes.windll.user32
    ventana = u32.FindWindowW(None, ctypes.c_wchar_p(_titulo()))
    if not ventana:
        return
    SW_RESTORE = 9
    u32.ShowWindow(ventana, SW_RESTORE)
    u32.SetForegroundWindow(ventana)


def esperar_a_que_muera(pid: int, segundos: int = 20) -> None:
    """Espera a que se apague la copia anterior (la que se acaba de actualizar)."""
    SYNCHRONIZE = 0x00100000
    k32 = ctypes.windll.kernel32
    limite = time.time() + segundos
    while time.time() < limite:
        h = k32.OpenProcess(SYNCHRONIZE, False, pid)
        if not h:
            return                     # ya no existe: podemos seguir
        k32.CloseHandle(h)
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# 4. El servidor
# ---------------------------------------------------------------------------
def _titulo() -> str:
    from core.config import NOMBRE_LOCAL
    return f"{NOMBRE_VENTANA_BASE} de {NOMBRE_LOCAL}"


def puerto_libre(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            s.bind(("0.0.0.0", puerto))
            return True
        except OSError:
            return False


def esperar_al_servidor(puerto: int) -> bool:
    """No abrimos la ventana hasta que el servidor conteste.

    Si no, el dueño ve una pantalla de error del navegador el primer segundo y
    cree que el programa está malo.
    """
    limite = time.time() + ESPERA_MAXIMA
    while time.time() < limite:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", puerto)) == 0:
                return True
        time.sleep(0.2)
    return False


def aviso(texto: str, titulo: str = "Punto de venta") -> None:
    """Un cartel de Windows. Es la única forma de hablarle al dueño cuando
    todavía no hay ventana donde escribir."""
    ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x40)   # MB_ICONINFORMATION


def relanzar() -> None:
    """Se vuelve a abrir sola después de instalar una actualización.

    Con el .bat esto lo hacía el .bat: el programa salía con código 3 y el bucle
    lo levantaba de nuevo. Acá no hay .bat, así que la copia vieja lanza una
    copia nueva, desprendida, que espera a que la vieja termine de morir (si no,
    chocaría con el cerrojo de instancia única) y recién ahí arranca.
    """
    if getattr(sys, "frozen", False):
        orden = [sys.executable, "--esperar", str(os.getpid())]
    else:
        orden = [sys.executable, os.path.abspath(__file__), "--esperar", str(os.getpid())]
    subprocess.Popen(
        orden,
        cwd=CARPETA,
        close_fds=True,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def marcar_identidad() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_EN_LA_BARRA)
    except Exception:
        pass          # es cosmético: si falla, la caja abre igual


def main() -> int:
    marcar_identidad()
    # Si venimos de una actualización, esperamos a que la copia vieja suelte el
    # cerrojo antes de intentar tomarlo nosotros.
    if "--esperar" in sys.argv:
        try:
            esperar_a_que_muera(int(sys.argv[sys.argv.index("--esperar") + 1]))
        except (ValueError, IndexError):
            time.sleep(2)

    if not tomar_el_cerrojo():
        traer_al_frente()
        return 0

    from core.config import NOMBRE_LOCAL, PUERTO   # después de armar sys.path

    if not puerto_libre(PUERTO):
        aviso(
            f"Hay otro programa ocupando el puerto {PUERTO} de este computador.\n\n"
            "Cierra el otro programa y vuelve a abrir la caja.",
        )
        return 1

    from apps.pos.api import actualizaciones
    from apps.pos.main import app

    # El actualizador necesita saber cómo volver a abrirnos. Con el .bat bastaba
    # con salir con código 3; acá le dejamos la función.
    actualizaciones.reiniciador = relanzar

    servidor = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",       # las pantallas del menú viven en otro computador
            port=PUERTO,
            log_level="warning",
            access_log=False,
        )
    )
    # Hilo aparte porque pywebview exige el hilo principal para la ventana.
    # uvicorn sabe que está fuera del hilo principal y no intenta instalar
    # manejadores de señales (que ahí revientan).
    hilo = threading.Thread(target=servidor.run, name="uvicorn", daemon=True)
    hilo.start()

    if not esperar_al_servidor(PUERTO):
        aviso("El punto de venta no alcanzó a partir. Vuelve a abrirlo.")
        return 1

    # Sin esto la ventana olvida las preferencias del cajero (imprimir siempre,
    # etc.) cada vez que se cierra: pywebview arranca en modo privado y borra
    # el localStorage al salir.
    datos_ventana = os.path.join(CARPETA, "datos-ventana")

    webview.settings["ALLOW_DOWNLOADS"] = True              # exportar CSV al contador
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True

    webview.create_window(
        f"{NOMBRE_VENTANA_BASE} de {NOMBRE_LOCAL}",
        f"http://127.0.0.1:{PUERTO}/",
        width=1360,
        height=860,
        min_size=(1024, 680),
        text_select=False,        # es una caja táctil: seleccionar texto estorba
        confirm_close=False,
    )
    try:
        webview.start(
            gui="edgechromium",
            # private_mode=False es obligatorio: en modo privado pywebview borra
            # el localStorage al cerrar, y ahí viven el pedido a medio armar y
            # las preferencias del cajero.
            private_mode=False,
            storage_path=datos_ventana,
            icon=ICONO if os.path.exists(ICONO) else None,
        )
    except Exception as e:
        # RED DE SEGURIDAD. La ventana incrustada depende de pywebview, de
        # pythonnet y del runtime de WebView2: tres cosas que pueden fallar en
        # un computador ajeno. Ya pasó una vez, con el paquete entregado.
        #
        # Que falle la ventana NO puede significar que el local no pueda cobrar.
        # Si no se puede abrir, se abre el navegador contra el mismo servidor,
        # que es exactamente lo que hacía INICIAR-POS.bat.
        esperar_en_el_navegador(e, PUERTO)

    # Se cerró la ventana: apagamos el servidor. Se le pide por las buenas y se
    # espera poco — lo que queda vivo es un hilo daemon, así que si se demora,
    # el proceso muere igual y no queda nada colgado en el administrador
    # de tareas ni el puerto 8090 tomado.
    servidor.should_exit = True
    hilo.join(timeout=4)
    return 0


def esperar_en_el_navegador(motivo: Exception, puerto: int) -> None:
    """Plan B: la caja se abre en el navegador y este proceso queda de guardia.

    El aviso es un cartel de Windows porque no hay dónde más escribirle al
    dueño, y queda abierto a propósito: mientras esté ahí, el servidor sigue
    vivo. Cerrarlo apaga la caja, igual que cerrar la ventana normal.
    """
    import webbrowser

    apunte = os.path.join(CARPETA, "problema-ventana.txt")
    try:
        with open(apunte, "w", encoding="utf-8") as f:
            f.write("No se pudo abrir la ventana de la aplicación:\n\n"
                    f"{type(motivo).__name__}: {motivo}\n\n"
                    "La caja se abrió en el navegador. Funciona igual.\n")
    except OSError:
        pass

    webbrowser.open(f"http://127.0.0.1:{puerto}/")
    aviso(
        "La caja se abrió en el navegador en vez de en su propia ventana.\n\n"
        "Funciona exactamente igual: puedes vender y cerrar caja sin problema.\n\n"
        "IMPORTANTE: no cierres este mensaje hasta que termines de usar la caja.\n"
        "Al cerrarlo se apaga el punto de venta.",
        "Punto de venta",
    )


if __name__ == "__main__":
    sys.exit(main())
