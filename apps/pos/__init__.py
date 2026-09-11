"""El punto de venta.

Lo primero que corre, antes que cualquier otra cosa del programa: si la última
actualización quedó a medias —se cortó la luz mientras se reemplazaban los
archivos—, se deshace acá (ver vuelta.py). Más adelante, cualquier import
podría toparse con código de dos versiones y reventar.
"""
import os as _os

RECUPERACION = None
try:
    from . import vuelta as _vuelta
    RECUPERACION = _vuelta.recuperar(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
except Exception as _e:        # abrir la caja importa más que esto
    RECUPERACION = {"error": f"No se pudo revisar la última actualización: {_e}"}
