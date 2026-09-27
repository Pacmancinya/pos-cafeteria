"""Pantalla completa de la ventana propia, también en cajas ya instaladas.

Kofe.py está congelado dentro del ejecutable. Este módulo sí viaja en las
actualizaciones y conecta la interfaz con la ventana que crea ese lanzador.
El servidor usado desde un navegador no importa ni necesita pywebview.
"""
from __future__ import annotations

import logging
import math
import sys
import time
from threading import Lock, Thread


_ESPERA_VENTANA = 30.0
_INTERVALO = 0.05
_iniciado = False
_cerrojo_inicio = Lock()
_log = logging.getLogger(__name__)


def necesita_maximizar(ancho, alto, ancho_disponible, alto_disponible) -> bool:
    """Compara dimensiones lógicas. Kofe.py mantiene su propia copia congelada."""
    return ancho > ancho_disponible or alto > alto_disponible


def _escala_formulario(form):
    # _scale es propio de pywebview reciente; DeviceDpi también sirve con un
    # ejecutable antiguo. No usamos Screen.scale: relaciona Bounds con la
    # resolución del monitor y puede dar 1 aunque Windows esté al 125%.
    for atributo, divisor in (("_scale", 1), ("DeviceDpi", 96)):
        try:
            escala = float(getattr(form, atributo)) / divisor
            if math.isfinite(escala) and escala > 0:
                return escala
        except Exception:
            pass
    grafico = form.CreateGraphics()
    try:
        escala = float(grafico.DpiX) / 96
        if not math.isfinite(escala) or escala <= 0:
            raise ValueError("DPI de la ventana inválido")
        return escala
    finally:
        grafico.Dispose()


def _area_trabajo(webview, ventana, form, Screen):
    actual = Screen.FromControl(form)
    # window.screen es la pantalla elegida al crear, no necesariamente donde
    # está ahora. Sólo usamos un frame de pywebview si corresponde a la actual.
    try:
        pantallas = [getattr(ventana, "screen", None)]
        pantallas.extend(getattr(webview, "screens", ()) or ())
        for pantalla in pantallas:
            frame = getattr(pantalla, "frame", None)
            if frame is not None and actual.Bounds.Contains(frame):
                return frame
    except Exception:
        _log.warning("No se pudo leer la pantalla de pywebview; se usará WinForms.",
                     exc_info=True)
    return actual.WorkingArea


def _ajustar_a_pantalla(webview, ventana) -> None:
    """Corrige sólo una ventana que no cabe; nunca interrumpe el arranque."""
    try:
        # .NET se carga sólo con la ventana lista, nunca al importar en servidor.
        from System import Func, Type
        from System.Drawing import Point, Size
        from System.Windows.Forms import Form, FormWindowState, Screen

        form = getattr(ventana, "native", None)
        if not isinstance(form, Form):
            raise TypeError("La ventana nativa no es un Form de WinForms")

        def ajustar():
            try:
                escala = _escala_formulario(form)
                area = _area_trabajo(webview, ventana, form, Screen)
                # Size y WorkingArea/frame son coordenadas nativas de WinForms
                # (físicas con el DPI awareness de pywebview). Dividimos AMBAS
                # por el DPI del Form para comparar en lógicos, sin redondear.
                ancho, alto = area.Width / escala, area.Height / escala
                maximizada = form.WindowState == FormWindowState.Maximized
                normal = form.RestoreBounds if maximizada else form.Size
                if necesita_maximizar(normal.Width / escala,
                                      normal.Height / escala, ancho, alto):
                    # Notebook 1366x768 al 125%: el mínimo viejo 1024x680
                    # termina en 1280x850 físicos y ni maximizado cabe.
                    # Primero bajamos el mínimo lógico y lo convertimos una
                    # sola vez a físicos; recién después Windows maximiza.
                    form.MinimumSize = Size(int(min(800, ancho) * escala),
                                            int(min(500, alto) * escala))
                    # RestoreBounds es de sólo lectura. Corregimos el tamaño
                    # normal en el mismo Invoke, sin ceder el hilo de interfaz
                    # entre restaurar y maximizar. No alternamos si ya cabe.
                    form.WindowState = FormWindowState.Normal
                    w = min(form.Size.Width, area.Width)
                    h = min(form.Size.Height, area.Height)
                    form.Size = Size(w, h)
                    form.Location = Point(area.X + (area.Width - w) // 2,
                                          area.Y + (area.Height - h) // 2)
                    form.WindowState = FormWindowState.Maximized
            except Exception:
                _log.warning("No se pudo ajustar la ventana al área de trabajo.",
                             exc_info=True)

        # Igual que winforms.py: incluso la lectura de Size ocurre en el hilo
        # de interfaz. No llamamos window.maximize(), que haría otro Invoke.
        form.Invoke(Func[Type](ajustar))
    except Exception:
        _log.warning("No se pudo preparar el ajuste de la ventana a la pantalla.",
                     exc_info=True)


def _ajustar_al_mostrar(webview, ventana) -> None:
    try:
        limite = time.monotonic() + _ESPERA_VENTANA
        while time.monotonic() < limite:
            mostrada = getattr(getattr(ventana, "events", None), "shown", None)
            consultar = getattr(mostrada, "is_set", None)
            form = getattr(ventana, "native", False)
            # native se asigna al principio del constructor de WinForms: no
            # basta con que exista, hay que esperar a que termine de mostrarse.
            lista = consultar() if callable(consultar) else (
                form is not None and getattr(form, "IsHandleCreated", True)
                and getattr(form, "Visible", True)
            )
            if lista:
                _ajustar_a_pantalla(webview, ventana)
                return
            time.sleep(_INTERVALO)
        _log.warning("La ventana no llegó a mostrarse para ajustar su tamaño.")
    except Exception:
        _log.warning("No se pudo esperar la ventana para ajustar su tamaño.",
                     exc_info=True)


def _crear_control(ventana):
    # Window.fullscreen sólo indica cómo se abrió la ventana: pywebview no lo
    # cambia al alternar. Conservamos el estado acá, incluso al recargar la web.
    completa = bool(getattr(ventana, "fullscreen", False))
    cerrojo = Lock()

    def pantalla_completa(activar: bool | None = None) -> bool:
        """Consulta sin argumento; un booleano establece el estado deseado."""
        nonlocal completa
        if activar is not None and not isinstance(activar, bool):
            raise ValueError("El estado de pantalla completa debe ser un booleano.")
        # El puente atiende cada llamada en un hilo distinto. Dos clics rápidos
        # pidiendo entrar deben producir una sola transición de ventana.
        with cerrojo:
            if activar is not None and activar != completa:
                ventana.toggle_fullscreen()
                completa = activar
            return completa

    return pantalla_completa


def _esperar_ventana(webview) -> None:
    limite = time.monotonic() + _ESPERA_VENTANA
    try:
        while time.monotonic() < limite:
            ventanas = getattr(webview, "windows", ())
            if ventanas:
                ventana = ventanas[0]
                # expose conserva esta función al recargar e instala el puente
                # tanto antes como después de cargar el documento.
                try:
                    ventana.expose(_crear_control(ventana))
                except Exception:
                    _log.warning("No se pudo conectar el control de pantalla completa.",
                                 exc_info=True)
                _ajustar_al_mostrar(webview, ventana)
                return
            time.sleep(_INTERVALO)
    except Exception:
        _log.warning("No se pudo preparar la pantalla completa de la ventana.",
                     exc_info=True)


def iniciar() -> None:
    """Conecta una sola vez, sin demorar el arranque del servidor."""
    global _iniciado
    # El lanzador importa webview antes de arrancar FastAPI, pero crea la
    # ventana después. En el servidor normal no abrimos ninguna ventana.
    webview = sys.modules.get("webview")
    if webview is None:
        return
    with _cerrojo_inicio:
        if _iniciado:
            return
        hilo = Thread(target=_esperar_ventana, args=(webview,),
                      name="pantalla-completa", daemon=True)
        hilo.start()
        _iniciado = True
