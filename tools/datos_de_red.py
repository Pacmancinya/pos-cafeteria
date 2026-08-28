"""Muestra en la ventana negra los datos que hacen falta para conectar todo.

Se corre desde INICIAR-POS.bat justo antes de levantar el servidor, para que el
dueño no tenga que buscar la IP del computador en ningún lado.

Ojo: la consola de Windows llega en cp1252 y revienta con acentos. Por eso lo
primero que hace este archivo es forzar UTF-8 en la salida.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.config import NOMBRE_LOCAL, PIN, PUERTO, ip_en_la_red  # noqa: E402

ip = ip_en_la_red()
raya = "=" * 62
print(f"""
{raya}
  CAJA DE {NOMBRE_LOCAL.upper()}

  En este computador ............ http://127.0.0.1:{PUERTO}
  Desde otro equipo del local ... http://{ip}:{PUERTO}
  PIN para otros equipos ........ {PIN}

  Para las pantallas del menú, pegar esta dirección:
      http://{ip}:{PUERTO}/api/v1/carta

  Para cerrar la caja: cierra esta ventana negra.
{raya}
""")
