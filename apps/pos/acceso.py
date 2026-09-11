"""Candado de la RED de la caja.

Por qué existe: el punto de venta escucha en toda la red del local porque las
pantallas del menú viven en otro computador. Pero en una cafetería el wifi de
invitados suele estar en la misma red — sin candado, un cliente podría abrir la
caja desde el celular y registrar o anular ventas.

La regla es proporcionada, no paranoica:

  · Desde el propio PC de la caja (127.0.0.1) → entra directo, sin PIN.
    El cajero no tiene ninguna fricción extra.
  · Desde cualquier otro equipo de la red → pide el PIN de red una vez y deja
    una galleta firmada con la llave de ESTA caja.
  · La carta, la salud y el aviso de errores de las pantallas quedan abiertos:
    los televisores no tienen teclado para escribir un PIN.

Desde la 2.19 el PIN de red lo elige cada local (`local.py`), la galleta va
firmada, y hay freno de intentos (`freno.py`).
"""
from __future__ import annotations

import hashlib
import hmac
from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from apps.pos import local

GALLETA = "pos_acceso"
# `/api/v1/carta` va libre porque es de solo lectura y muestra precios que ya
# están a la vista del público, y porque de ahí la sacan los televisores: si
# pidiera el PIN de red, cada TV necesitaría que alguien lo escribiera, y un TV
# colgado en la pared no tiene teclado. Por lo mismo va libre el aviso de
# errores de las pantallas, que tiene su propio tope (api/diagnostico.py).
LIBRES = ("/api/v1/carta", "/api/v1/salud", "/api/v1/diagnostico/evento",
          "/pantallas", "/static/", "/entrar", "/favicon.ico")
LOCALES = {"127.0.0.1", "::1", "localhost"}


def ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def es_local(request: Request) -> bool:
    return ip(request) in LOCALES


def token_de_acceso() -> str:
    """La galleta que deja pasar a un equipo de la red.

    Hasta la 2.18 era sha256("pos-cafeteria:" + PIN): SIN ningún secreto de la
    caja. Quien leyera el código público podía calcularla con el PIN de fábrica
    —o probar las diez mil de un PIN de 4 dígitos— sin escribir nunca el PIN en
    la pantalla de entrada, así que el freno de intentos no habría servido de
    nada. Ahora va firmada con la llave de ESTA caja (`.secreto`, la misma de
    las sesiones): sin esa llave no hay galleta que sirva. Y cambiar el PIN deja
    fuera a los equipos que entraron con el viejo, que es lo que se espera de
    cambiar un PIN.
    """
    from apps.pos.sesion import _secreto
    return hmac.new(_secreto().encode(), ("acceso:" + local.pin_de_red()).encode(),
                    hashlib.sha256).hexdigest()[:32]


def galleta_valida(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(GALLETA, "").encode("utf-8"),
                               token_de_acceso().encode())


def puede_pasar(request: Request) -> bool:
    ruta = request.url.path
    if any(ruta == l or ruta.startswith(l) for l in LIBRES):
        return True
    if es_local(request):
        return True
    return galleta_valida(request)


async def candado(request: Request, call_next):
    if puede_pasar(request):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": "Necesitas el PIN de la caja para hacer esto desde este equipo."},
            status_code=401,
        )
    return RedirectResponse("/entrar", status_code=303)


PAGINA = """<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar a la caja</title>
<link rel="stylesheet" href="/static/styles.css?v=10">
<style>
  body{display:grid;place-items:center;padding:24px}
  form{background:var(--tarjeta);border:1px solid var(--linea);border-radius:16px;
       padding:26px 28px;width:min(360px,100%);box-shadow:var(--sombra);text-align:center}
  h1{font-size:21px;margin-bottom:6px}
  p{color:var(--suave);font-size:14px;line-height:1.5;margin-bottom:20px}
  input{width:100%;font-size:30px;text-align:center;letter-spacing:.3em;
        padding:14px;border:1px solid var(--linea);border-radius:11px;
        background:var(--papel);color:var(--tinta);font-family:inherit}
  input:focus{outline:2px solid var(--clay);outline-offset:1px}
  button{margin-top:16px;width:100%}
  .mal{color:var(--rojo);font-size:14px;margin-top:12px;font-weight:600}
</style></head>
<body>
<form method="post" action="/entrar">
  <h1>Caja de __LOCAL__</h1>
  <p>Estás entrando desde otro equipo de la red.<br>Escribe el PIN de red de la caja.</p>
  <input name="pin" type="password" inputmode="numeric" autocomplete="off" autofocus placeholder="••••••">
  <button class="btn btn--cobrar" type="submit">Entrar</button>
  __ERROR__
</form>
</body></html>"""


def pagina_entrar(nombre_local: str, aviso: str = "", estado: int = 200) -> HTMLResponse:
    html = PAGINA.replace("__LOCAL__", escape(nombre_local)).replace(
        "__ERROR__", f'<p class="mal">{escape(aviso)}</p>' if aviso else "")
    return HTMLResponse(html, status_code=estado)


def renovar_galleta(respuesta) -> None:
    # 180 días: el tablet del local no debería tener que reingresar el PIN cada rato.
    respuesta.set_cookie(GALLETA, token_de_acceso(), max_age=60 * 60 * 24 * 180,
                         httponly=True, samesite="lax")


def respuesta_con_acceso(destino: str = "/") -> RedirectResponse:
    r = RedirectResponse(destino, status_code=303)
    renovar_galleta(r)
    return r


def pin_correcto(pin: str) -> bool:
    escrito = (pin or "").strip()
    return bool(escrito) and hmac.compare_digest(escrito.encode("utf-8"),
                                                 local.pin_de_red().encode())
