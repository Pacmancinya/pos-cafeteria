"""Pantalla completa de la ventana propia, también en cajas ya instaladas.

Kofe.py está congelado dentro del ejecutable. Este módulo sí viaja en las
actualizaciones y conecta la interfaz con la ventana que crea ese lanzador.
El servidor usado desde un navegador no importa ni necesita pywebview.
"""
from __future__ import annotations

import logging
import sys
import time
from threading import Lock, Thread


_ESPERA_VENTANA = 30.0
_INTERVALO = 0.05
_iniciado = False
_cerrojo_inicio = Lock()
_log = logging.getLogger(__name__)


def _crear_control(ventana):
    # Window.fullscreen sólo indica cómo se abrió la ventana: pywebview no lo
    # cambia al alternar. Conservamos el estado acá, incluso al recargar la web.
    completa = bool(ventana.fullscreen)
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
            if webview.windows:
                ventana = webview.windows[0]
                # expose conserva esta función al recargar e instala el puente
                # tanto antes como después de cargar el documento.
                ventana.expose(_crear_control(ventana))
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
