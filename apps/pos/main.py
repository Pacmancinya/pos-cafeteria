"""Punto de venta para cafetería — aplicación FastAPI.

Se levanta con:  python -m uvicorn apps.pos.main:app --port 8090
o con doble clic en INICIAR-POS.bat
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from apps.pos import acceso
from apps.pos.api import (actualizaciones, ajustes, catalogo, codigos, datos,
                          impresion, importar, inventario, turnos, usuarios,
                          ventas)
from apps.pos.db.models import Turno
from apps.pos.db.session import crear_tablas, engine
from core.config import HOST, NOMBRE_LOCAL, PIN, PUERTO, VERSION, ip_en_la_red

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTATICOS = os.path.join(AQUI, "static")

@asynccontextmanager
async def ciclo(app: FastAPI):
    crear_tablas()
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


@app.get("/api/v1/salud")
def salud():
    with Session(engine) as s:
        t = s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711
    ip = ip_en_la_red() if HOST == "0.0.0.0" else "127.0.0.1"
    return {
        "ok": True, "version": VERSION, "local": NOMBRE_LOCAL,
        "turno_abierto": bool(t),
        # Lo que hay que abrir en cada televisor del local.
        "carta_url": f"http://{ip}:{PUERTO}/api/v1/carta",
        "pantallas_url": f"http://{ip}:{PUERTO}/pantallas",
        "en_la_red": HOST == "0.0.0.0",
    }


@app.get("/entrar")
def entrar(request: Request):
    if acceso.es_local(request) or request.cookies.get(acceso.GALLETA) == acceso.token_de_acceso():
        return acceso.respuesta_con_acceso()
    return acceso.pagina_entrar(NOMBRE_LOCAL)


@app.post("/entrar")
def entrar_post(pin: str = Form(default="")):
    if acceso.pin_correcto(pin):
        return acceso.respuesta_con_acceso()
    return acceso.pagina_entrar(NOMBRE_LOCAL, error=True)


app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


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
    return FileResponse(os.path.join(ESTATICOS, "index.html"),
                        headers={"Cache-Control": "no-store, must-revalidate"})


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
    return FileResponse(os.path.join(ESTATICOS, "pantallas.html"),
                        headers={"Cache-Control": "no-store"})


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


