"""Punto de venta para cafetería — aplicación FastAPI.

Se levanta con:  python -m uvicorn apps.pos.main:app --port 8090
o con doble clic en INICIAR-POS.bat
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from apps.pos import acceso, diagnostico, freno, local
from apps.pos.api import (actualizaciones, ajustes, catalogo, codigos, datos,
                          impresion, importar, inventario, turnos, usuarios,
                          ventas)
from apps.pos.api import diagnostico as api_diagnostico
from apps.pos.db.models import Turno
from apps.pos.db.session import crear_tablas, engine
from core.config import HOST, NOMBRE_LOCAL, PUERTO, VERSION, ip_en_la_red, modo_demo

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTATICOS = os.path.join(AQUI, "static")

# El registro de errores queda listo antes que nada: si algo falla al arrancar,
# justo eso es lo que hay que poder leer después.
diagnostico.preparar()

@asynccontextmanager
async def ciclo(app: FastAPI):
    crear_tablas()
    # Modo demo: sin la marca MODO-DEMO.txt no hace nada. Si fallara, la caja abre
    # igual: una demostración no puede dejar una caja sin arrancar.
    try:
        from tools.demo.inicio import preparar
        if preparar():
            diagnostico.log.info("Modo demo: base sembrada con datos de ejemplo")
    except Exception:
        diagnostico.log.exception("Modo demo: no se pudo sembrar")
    diagnostico.log.info("Arranca la caja v%s", VERSION)
    import apps.pos as paquete
    if paquete.RECUPERACION:
        # Una actualización había quedado a medias y se deshizo al abrir (vuelta.py).
        diagnostico.log.warning("Actualización a medias, deshecha al abrir: %s",
                                paquete.RECUPERACION)
    # Una copia al abrir en la mañana: si el disco muere durante el día,
    # se pierde el día, no el historial completo.
    try:
        from tools.respaldo import respaldar
        respaldar("arranque")
    except Exception:
        pass          # un respaldo que falla no puede impedir que la caja abra

    # Si el programa se cerró de golpe —corte de luz, alguien cerró la ventana—
    # quedaron presencias abiertas. Sin esto, el turno diría que esa persona
    # estuvo en la caja hasta que alguien vuelva a entrar, que pueden ser días.
    try:
        from sqlmodel import Session
        from apps.pos.sesion import cerrar_presencias_abiertas
        with Session(engine) as s:
            cerradas = cerrar_presencias_abiertas(s, None, "corte")
            if cerradas:
                print(f"  Se cerraron {cerradas} sesiones que quedaron abiertas.")
    except Exception:
        pass

    # El icono en el escritorio. Va acá y no en Kofe.py porque Kofe.py es el
    # guion congelado dentro del .exe y no viaja en las actualizaciones.
    try:
        from tools.acceso_directo import crear_si_falta
        hecho = crear_si_falta()
        if hecho:
            print("  " + hecho)
    except Exception:
        pass
    # También vive fuera del ejecutable: una actualización puede conectar
    # la pantalla completa nativa sin reconstruir Kofe.exe.
    try:
        from tools.ventana import iniciar
        iniciar()
    except Exception:
        diagnostico.log.warning("No se pudo preparar la ventana.", exc_info=True)
    yield


app = FastAPI(title=f"Punto de venta · {NOMBRE_LOCAL}", version=VERSION, lifespan=ciclo)

# El programa de las pantallas del menú corre APARTE, en otro puerto: para el
# navegador del televisor eso es otro origen. Sin CORS rechaza la carta y el menú
# se queda con los precios viejos. Esto no es opcional desde que los dos
# programas se separaron.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# El candado va DESPUÉS del CORS para que la carta siga saliendo libre.
app.middleware("http")(acceso.candado)


# Lo que tarda demasiado queda anotado. Un cobro que demora diez segundos en el
# local se ve como "la caja está lenta" y nada más; acá queda cuál fue y cuánto.
@app.middleware("http")
async def lo_que_tarda(request: Request, call_next):
    inicio = time.perf_counter()
    respuesta = await call_next(request)
    ms = (time.perf_counter() - inicio) * 1000
    if ms > 2000:
        diagnostico.log.warning("lento: %s %s -> %s en %d ms", request.method,
                                request.url.path, respuesta.status_code, ms)
    return respuesta


@app.exception_handler(Exception)
async def error_inesperado(request: Request, exc: Exception):
    """Un error que nadie esperaba: queda anotado con todo su detalle, y la
    pantalla recibe un mensaje que se entiende en vez de «Internal Server Error»."""
    diagnostico.log.error("error en %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        {"detail": "Algo falló en la caja. Quedó anotado en el registro para revisarlo."},
        status_code=500)

app.include_router(catalogo.router)
app.include_router(ventas.router)
app.include_router(turnos.router)
app.include_router(datos.router)
app.include_router(impresion.router)
app.include_router(actualizaciones.router)
app.include_router(usuarios.router)
app.include_router(inventario.router)
app.include_router(importar.router)
app.include_router(ajustes.router)
app.include_router(codigos.router)
app.include_router(api_diagnostico.router)


@app.get("/api/v1/salud")
def salud():
    with Session(engine) as s:
        t = s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711
    ip = ip_en_la_red() if HOST == "0.0.0.0" else "127.0.0.1"
    return {
        "ok": True, "version": VERSION, "local": local.nombre(),
        "demo": modo_demo(),
        "turno_abierto": bool(t),
        # Lo que hay que abrir en cada televisor del local.
        "carta_url": f"http://{ip}:{PUERTO}/api/v1/carta",
        "pantallas_url": f"http://{ip}:{PUERTO}/pantallas",
        "en_la_red": HOST == "0.0.0.0",
    }


@app.get("/entrar")
def entrar(request: Request):
    if acceso.es_local(request) or acceso.galleta_valida(request):
        return acceso.respuesta_con_acceso()
    return acceso.pagina_entrar(local.nombre())


@app.post("/entrar")
def entrar_post(request: Request, pin: str = Form(default="")):
    """El PIN de red, con freno: diez mil combinaciones no se prueban desde un celular."""
    llave = "red:" + acceso.ip(request)
    falta = freno.PIN.cuanto_falta(llave)
    if falta:
        return acceso.pagina_entrar(local.nombre(), freno.mensaje_de_espera(falta), 429)
    if acceso.pin_correcto(pin):
        freno.PIN.acierto(llave)
        return acceso.respuesta_con_acceso()
    espera = freno.PIN.fallo(llave)
    if espera:
        return acceso.pagina_entrar(local.nombre(), freno.mensaje_de_espera(espera), 429)
    return acceso.pagina_entrar(local.nombre(), "Ese PIN no es.", 401)


app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


def _html_con_version(nombre: str) -> HTMLResponse:
    """Sirve un HTML poniéndole la versión de la caja a cada archivo que pide.

    Los `?v=` se escribían a mano y en la 2.29 se olvidó subirlos: la caja se
    actualizó, el número subió y la pantalla siguió siendo la anterior, porque
    el navegador tenía guardado el `app.js?v=63` de la versión pasada. Ya había
    pasado con el teclado en pantalla de la 2.5. Ahora el número sale de
    APP_VERSION: cambia sola con cada versión y no hay nada que recordar.
    """
    ruta = os.path.join(ESTATICOS, nombre)
    with open(ruta, encoding="utf-8") as f:
        html = f.read().replace("__VERSION__", VERSION)
    html = html.replace("__MARCA_DEMO__", (
        '<span class="marca-demo" title="Datos de ejemplo">DEMO</span>'
        if modo_demo() else ""))
    return HTMLResponse(html, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/")
def caja():
    """La pantalla del cajero. NUNCA se guarda en la caché del navegador.

    Esto no es una precaución: era un bug que dejaba el local en una versión
    vieja para siempre. `index.html` es el único archivo sin `?v=` en su
    dirección —es el que LLEVA los `?v=` de todos los demás—, y se servía sin
    ninguna cabecera de caché. Con solo un ETag, el navegador puede decidir por
    su cuenta cuánto tiempo confiar en su copia sin siquiera preguntar.

    El síntoma es de los peores: la caja se actualiza, el número de versión sube,
    el dueño ve que subió... y la pantalla sigue siendo la anterior, porque el
    HTML viejo sigue pidiendo `app.js?v=28` en vez de `?v=29`. Pasó de verdad:
    el teclado en pantalla que se apagó en la 2.5 siguió apareciendo.

    Los demás archivos SÍ se guardan en caché, y está bien: cada uno lleva su
    `?v=` y cambia de dirección cuando cambia.
    """
    return _html_con_version("index.html")


@app.get("/pantallas")
def pantallas():
    """Las pantallas del menú del local, servidas por la propia caja.

    Cada TV abre una dirección de la red y la carta le llega del MISMO origen:
    no hay archivo que copiar, ni IP que escribir, ni CORS que pelear.

        http://<ip-de-la-caja>:8090/pantallas?p=1   → la vitrina
        http://<ip-de-la-caja>:8090/pantallas?p=2   → la carta con precios
        http://<ip-de-la-caja>:8090/pantallas?tv=1  → las dos turnándose

    Vivieron acá desde la 1.8, se sacaron a un programa aparte en la 2.2 y
    volvieron en la 2.8. La razón de sacarlas —que un almacén sin televisores no
    cargara este código— no aguantaba: son 184 KB de archivos estáticos que
    nadie pide si nadie los abre, y a cambio la cafetería tenía que dejar una
    ventana negra más abierta todo el día. Se cambió algo que costaba nada por
    algo que costaba todos los días.
    """
    return _html_con_version("pantallas.html")


@app.get("/pantallas/simple")
def pantallas_simple():
    """La misma carta, para el navegador que trae el televisor.

    El "Opera" de un smart TV es un Chromium congelado en el firmware: hay
    equipos en venta con uno de 2014. Esta versión no usa nada que ese navegador
    pueda no entender. `pantallas.html` manda para acá sola cuando se da cuenta.

        http://<ip-de-la-caja>:8090/pantallas/simple
        http://<ip-de-la-caja>:8090/pantallas/simple?diag=1
    """
    return FileResponse(os.path.join(ESTATICOS, "pantallas-simple.html"),
                        headers={"Cache-Control": "no-store"})
