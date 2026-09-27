"""Muestra en la consola los datos para conectar el resto del local.

Ojo dónde se usa: **solo en el plan B**, cuando falta la librería de la ventana
propia y la caja se abre en el navegador. Ese es el único camino que todavía
deja una consola abierta. En el arranque normal no se corre, porque el lanzador
suelta la caja y su ventana se cierra sola — y porque la misma información, con
botón de copiar, está dentro de la app, en la pestaña Carta.

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

  Para las pantallas del menú, abrir en cada TV:
      http://{ip}:{PUERTO}/pantallas?p=1     (vitrina)
      http://{ip}:{PUERTO}/pantallas?p=2     (carta con precios)

  Para cerrar la caja: cierra la ventana del navegador Y esta ventana negra.
{raya}
""")
