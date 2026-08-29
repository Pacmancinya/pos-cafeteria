"""Candado de la caja.

Por qué existe: el punto de venta escucha en toda la red del local porque las
pantallas del menú viven en otro computador. Pero en una cafetería el wifi de
invitados está en la misma red — sin candado, un cliente podría abrir la caja
desde el celular y registrar o anular ventas.

La regla es proporcionada, no paranoica:

  · Desde el propio PC de la caja (127.0.0.1) → entra directo, sin PIN.
    El cajero no tiene ninguna fricción extra.
  · Desde cualquier otro equipo de la red → pide PIN una vez y deja una galleta.
  · La carta (`/api/v1/carta`) y la salud quedan siempre abiertas: son de solo
    lectura y muestran precios que ya están a la vista del público.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core.config import PIN, token_de_acceso

GALLETA = "pos_acceso"
# `/api/v1/carta` va libre porque es de solo lectura y muestra precios que ya
# están a la vista del público. Y porque es de donde el programa de las pantallas
# —que desde la 2.2 corre aparte— saca la carta: si pidiera el PIN de red, cada
# TV del local necesitaría que alguien lo escribiera, y un TV colgado en la pared
# no tiene teclado.
LIBRES = ("/api/v1/carta", "/api/v1/salud", "/static/",
          "/entrar", "/favicon.ico")
LOCALES = {"127.0.0.1", "::1", "localhost"}


def es_local(request: Request) -> bool:
    cliente = request.client.host if request.client else ""
    return cliente in LOCALES


def puede_pasar(request: Request) -> bool:
    ruta = request.url.path
    if any(ruta == l or ruta.startswith(l) for l in LIBRES):
        return True
    if es_local(request):
        return True
    return request.cookies.get(GALLETA) == token_de_acceso()


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
  <p>Estás entrando desde otro equipo de la red.<br>Escribe el PIN de la caja.</p>
  <input name="pin" type="password" inputmode="numeric" autocomplete="off" autofocus placeholder="••••">
  <button class="btn btn--cobrar" type="submit">Entrar</button>
  __ERROR__
</form>
</body></html>"""


def pagina_entrar(local: str, error: bool = False) -> HTMLResponse:
    html = PAGINA.replace("__LOCAL__", local).replace(
        "__ERROR__", '<p class="mal">Ese PIN no es.</p>' if error else ""
    )
    return HTMLResponse(html, status_code=401 if error else 200)


def respuesta_con_acceso(destino: str = "/") -> RedirectResponse:
    r = RedirectResponse(destino, status_code=303)
    # 180 días: el tablet del local no debería tener que reingresar el PIN cada rato.
    r.set_cookie(GALLETA, token_de_acceso(), max_age=60 * 60 * 24 * 180,
                 httponly=True, samesite="lax")
    return r


def pin_correcto(pin: str) -> bool:
    return bool(PIN) and pin.strip() == PIN
