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
        # De acá saca la carta el programa de las PANTALLAS DEL MENÚ, que desde
        # la 2.2 es una aplicación aparte: un almacén o una botillería no tienen
        # televisores y no tienen por qué cargar, actualizar ni arrancar ese
        # código. Esta dirección es el único contrato entre los dos programas.
        "carta_url": f"http://{ip}:{PUERTO}/api/v1/carta",
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
    return FileResponse(os.path.join(ESTATICOS, "index.html"))


