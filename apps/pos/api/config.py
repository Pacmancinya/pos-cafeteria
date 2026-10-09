"""Config: el acceso con PIN y las dos cosas más delicadas de la caja (respaldos y restaurar).

Es el mismo patrón de Reportes (apps/pos/api/reportes.py):

  · Config muestra y cambia cómo funciona el local —precios sugeridos, formas de pago,
    quién entra, la impresora—, así que pide el PIN de nuevo y solo deja pasar a quien tenga
    el permiso «config». El PIN se verifica ACÁ, en el servidor, con la misma verificación del
    candado (`sesion.pin_calza`) y el mismo freno de intentos.
  · La respuesta deja una galleta firmada y de corta vida: vale 5 minutos y se renueva con
    cada uso. Sin uso, se acaba. Se vuelve a mirar el permiso en la base en cada petición,
    así que quitárselo a alguien tiene efecto al toque.
  · La galleta queda amarrada a la presencia de quien estaba en la caja cuando se escribió el
    PIN: si entra otra persona (otro PIN en el candado, el bloqueo, cambiar de usuario), esa
    galleta ya no sirve aunque el navegador la conserve.

Los endpoints que cambian el local (ajustes, personas, PIN de red, impresora, actualizar,
televisores, restaurar…) piden esta puerta además de la sesión. Los que lee cualquiera que esté
en la caja (GET /ajustes, el nombre del local) no.

`autoridad` es una variable del módulo y no una función fija a propósito: las pruebas viejas del
resto de la caja la reemplazan por una que mira solo la sesión (ver conftest.py), y las pruebas
de este archivo (test_config.py) usan la de verdad.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from apps.pos import freno, sesion
from apps.pos.db.models import Turno, Usuario, Venta
from apps.pos.db.session import engine, get_session
from core.config import NOMBRE_ROL, ahora, puede
from tools import respaldo as resp
from tools import restaurar as rest

router = APIRouter(prefix="/api/v1/config", tags=["config"])

GALLETA = "pos_config"
MINUTOS_DE_ACCESO = 5
PERMISO = "config"
_MENSAJE_SIN_PERMISO = "{nombre} no tiene permiso para esto. Lo puede hacer el dueño."


def _persona(u: Usuario | None) -> dict:
    if not u:
        return {"id": None, "nombre": "", "rol": "dueno", "rol_nombre": NOMBRE_ROL["dueno"],
                "color": ""}
    return {"id": u.id, "nombre": u.nombre, "rol": u.rol,
            "rol_nombre": NOMBRE_ROL.get(u.rol, u.rol), "color": u.color}


def _dar_acceso(respuesta: Response, usuario_id: int | None, presencia_id) -> None:
    # `k` distingue esta galleta de la de la sesión y de la de Reportes: son del mismo tipo y
    # la misma firma, y una no tiene que servir como otra.
    respuesta.set_cookie(
        GALLETA,
        sesion._firmar({"k": "cfg", "uid": usuario_id, "pre": presencia_id,
                        "t": sesion.ahora().isoformat()}),
        max_age=MINUTOS_DE_ACCESO * 60, httponly=True, samesite="lax")


def _mirar_acceso(request: Request, s: Session, quien: dict) -> tuple[bool, Usuario | None, str]:
    """(vale, usuario, motivo). No renueva nada: solo mira."""
    carga = sesion._abrir(request.cookies.get(GALLETA, ""))
    if not carga or carga.get("k") != "cfg":
        return False, None, "Config pide el PIN."
    try:
        emitida = datetime.fromisoformat(carga["t"])
    except (KeyError, ValueError):
        return False, None, "Config pide el PIN."
    if emitida.tzinfo is None:
        emitida = emitida.replace(tzinfo=timezone.utc)
    if sesion.ahora() - emitida > timedelta(minutes=MINUTOS_DE_ACCESO):
        return False, None, "Config se cerró sola tras 5 minutos sin uso. Pide el PIN de nuevo."
    if carga.get("pre") != quien.get("presencia_id"):
        # Entró otra persona a la caja después de escribir el PIN.
        return False, None, "Config pide el PIN."
    u = s.get(Usuario, carga.get("uid"))
    if not u or not u.activo:
        return False, None, "Esa persona ya no entra a la caja."
    if not puede(u.rol, PERMISO, u.permisos or ""):
        raise HTTPException(403, f"{u.nombre} no tiene permiso para cambiar los ajustes.")
    return True, u, ""


def autoridad_real(request: Request, respuesta: Response, s: Session, quien: dict) -> dict:
    """Quién manda en esta petición de Config: el dueño provisorio de una caja sin personas,
    o la persona cuyo PIN se escribió hace menos de 5 minutos. Renueva el acceso."""
    if quien.get("provisorio"):
        return quien
    if not quien.get("rol"):
        raise HTTPException(401, "Hay que entrar con el PIN para hacer esto.")
    vale, u, motivo = _mirar_acceso(request, s, quien)
    if not vale:
        # Sin permiso ni PIN reciente no hay nada que pedir: el permiso se pide al dueño.
        if not puede(quien["rol"], PERMISO, quien.get("permisos", "")):
            raise HTTPException(403, _MENSAJE_SIN_PERMISO.format(
                nombre=quien.get("nombre") or "Este usuario"))
        raise HTTPException(401, motivo)
    _dar_acceso(respuesta, u.id, quien.get("presencia_id"))
    return {"id": u.id, "nombre": u.nombre, "rol": u.rol, "permisos": u.permisos or "",
            "presencia_id": quien.get("presencia_id"), "provisorio": False}


def autoridad_de_sesion(request: Request, respuesta: Response, s: Session, quien: dict) -> dict:
    """La de las pruebas del resto de la caja: manda la sesión, sin PIN de Config."""
    if not quien.get("rol"):
        raise HTTPException(401, "Hay que entrar con el PIN para hacer esto.")
    return quien


autoridad = autoridad_real


def puerta(request: Request, respuesta: Response, s: Session = Depends(get_session),
           quien: dict = Depends(sesion.quien_es)) -> dict:
    """La puerta de los endpoints de Config: sesión, PIN reciente y permiso."""
    return autoridad(request, respuesta, s, quien)


def exige(*permisos: str):
    """Como `sesion.exige`, pero detrás del PIN de Config:

        @router.put("/ajustes", dependencies=[Depends(config.exige())])
        @router.post("/usuarios", ...Depends(config.exige("usuarios")))

    Sin argumentos pide el permiso «config» (que la puerta ya pide); con argumentos, esos.
    """
    pedidos = permisos or (PERMISO,)

    def guardia(quien: dict = Depends(puerta)) -> dict:
        for permiso in pedidos:
            if not puede(quien["rol"], permiso, quien.get("permisos", "")):
                raise HTTPException(403, _MENSAJE_SIN_PERMISO.format(
                    nombre=quien.get("nombre") or "Este usuario"))
        return quien
    return guardia


def exige_o_config(permiso: str):
    """Para lo que ya pedía otro permiso (los informes y el respaldo): sigue sirviendo con ese
    permiso, y también a quien está en Config con su PIN, que no tiene por qué tenerlo suelto."""
    def guardia(request: Request, respuesta: Response, s: Session = Depends(get_session),
                quien: dict = Depends(sesion.exige_entrar)) -> dict:
        if puede(quien["rol"], permiso, quien.get("permisos", "")):
            return quien
        a = autoridad(request, respuesta, s, quien)
        if not puede(a["rol"], PERMISO, a.get("permisos", "")):
            raise HTTPException(403, _MENSAJE_SIN_PERMISO.format(
                nombre=quien.get("nombre") or "Este usuario"))
        return a
    return guardia


# ---------------------------------------------------------------------------
# Entrar, salir, estado
# ---------------------------------------------------------------------------
class EntrarIn(BaseModel):
    pin: str = ""
    # Opcional: con él se prueba el PIN de UNA persona; sin él, el de cualquiera de los
    # usuarios activos (en la pantalla se escribe solo el PIN).
    usuario_id: int | None = None


@router.post("/entrar")
def entrar(datos: EntrarIn, respuesta: Response, request: Request,
           s: Session = Depends(get_session),
           quien: dict = Depends(sesion.exige_entrar)):
    """Verifica el PIN y abre Config por unos minutos."""
    if not sesion.hay_usuarios(s):
        if not puede(quien.get("rol", ""), PERMISO, quien.get("permisos", "")):
            raise HTTPException(403, "Este equipo no puede cambiar los ajustes.")
        _dar_acceso(respuesta, None, None)
        return {"ok": True, "usuario": _persona(None), "minutos": MINUTOS_DE_ACCESO}

    # El mismo freno que el candado: diez mil PIN de 4 dígitos no se prueban, y esta puerta no
    # puede ser el camino fácil para adivinar el de otra persona.
    llave = f"config:{request.client.host if request.client else '?'}"
    falta = freno.PIN.cuanto_falta(llave)
    if falta:
        raise HTTPException(429, freno.mensaje_de_espera(falta))

    activos = list(s.exec(select(Usuario).where(Usuario.activo == True)  # noqa: E712
                          .order_by(Usuario.orden, Usuario.id)).all())
    if datos.usuario_id is not None:
        activos = [u for u in activos if u.id == datos.usuario_id]
    coinciden = [u for u in activos if sesion.pin_calza(datos.pin or "", u.pin_hash)]
    if not coinciden:
        espera = freno.PIN.fallo(llave)
        if espera:
            raise HTTPException(429, freno.mensaje_de_espera(espera))
        raise HTTPException(401, "PIN incorrecto. Prueba otra vez.")
    freno.PIN.acierto(llave)

    con_permiso = [u for u in coinciden if puede(u.rol, PERMISO, u.permisos or "")]
    if not con_permiso:
        raise HTTPException(403, f"{coinciden[0].nombre} no tiene permiso para cambiar los ajustes.")
    u = con_permiso[0]
    _dar_acceso(respuesta, u.id, quien.get("presencia_id"))
    return {"ok": True, "usuario": _persona(u), "minutos": MINUTOS_DE_ACCESO}


@router.post("/salir")
def salir(respuesta: Response):
    respuesta.delete_cookie(GALLETA)
    return {"ok": True}


@router.get("/estado")
def estado(request: Request, respuesta: Response, s: Session = Depends(get_session),
           quien: dict = Depends(sesion.quien_es)):
    """¿Sigue abierto Config? Es también el «latido»: mientras la pantalla se usa, la pantalla
    pregunta esto cada rato y así el acceso no se acaba a la mitad de un cambio. Nunca da
    error: dice que no."""
    if not quien.get("rol"):
        return {"activo": False}
    if quien.get("provisorio"):
        return {"activo": puede(quien["rol"], PERMISO, quien.get("permisos", "")),
                "usuario": _persona(None), "minutos": MINUTOS_DE_ACCESO}
    try:
        vale, u, motivo = _mirar_acceso(request, s, quien)
    except HTTPException:
        return {"activo": False}
    if not vale:
        return {"activo": False, "motivo": motivo}
    _dar_acceso(respuesta, u.id, quien.get("presencia_id"))
    return {"activo": True, "usuario": _persona(u), "minutos": MINUTOS_DE_ACCESO}


# ---------------------------------------------------------------------------
# Respaldos y restaurar
# ---------------------------------------------------------------------------
NOMBRE_RESPALDO = re.compile(r"^(pos-\d{4}-\d{2}-\d{2}|antes-de-restaurar-[0-9_-]+)\.db$")
_cerrojo_restaurar = threading.Lock()


def _ventas_de_hoy(s: Session) -> int:
    return int(s.exec(select(func.count(Venta.id))).one())


def _caja_abierta(s: Session) -> dict | None:
    t = s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711
    if not t:
        return None
    u = s.get(Usuario, t.abierto_por_id) if t.abierto_por_id else None
    return {"id": t.id, "quien": (u.nombre if u else t.cajero) or ""}


def _ruta_del_respaldo(archivo: str) -> str:
    """El archivo de un respaldo de la carpeta de respaldos. Solo los nombres que la caja misma
    pone: nada de rutas ni de «..»."""
    if not NOMBRE_RESPALDO.fullmatch(archivo or ""):
        raise HTTPException(422, "Ese no es un respaldo de la caja.")
    ruta = os.path.join(resp.CARPETA, archivo)
    if not os.path.isfile(ruta):
        raise HTTPException(404, "Ese respaldo ya no está en la carpeta de respaldos.")
    return ruta


@router.get("/respaldos")
def listar_respaldos(s: Session = Depends(get_session),
                     quien: dict = Depends(exige())):
    """La lista de respaldos para elegir uno, y las ventas que tiene la caja hoy."""
    return {"carpeta": resp.CARPETA, "copias": resp.listar_detalle(),
            "ventas_hoy": _ventas_de_hoy(s), "caja_abierta": _caja_abierta(s)}


@router.post("/respaldar")
def respaldar_ahora(quien: dict = Depends(exige())):
    return resp.respaldar("config")


@router.get("/respaldos/{archivo}")
def revisar_respaldo(archivo: str, s: Session = Depends(get_session),
                     quien: dict = Depends(exige())):
    """Mira un respaldo ANTES de restaurarlo: si está sano, es de esta caja y cuántas ventas
    se perderían. No toca nada."""
    ruta = _ruta_del_respaldo(archivo)
    visto = rest.comprobar(ruta)
    hoy = _ventas_de_hoy(s)
    if not visto["ok"]:
        return {"ok": False, "detalle": visto["detalle"], "archivo": archivo, "ventas_hoy": hoy}
    return {"ok": True, "archivo": archivo, "ventas": visto["ventas"], "ventas_hoy": hoy,
            # Las que hay ahora y el respaldo no tiene. Si el respaldo tiene más (se recupera
            # algo que se perdió), no se pierde ninguna.
            "perderia": max(0, hoy - visto["ventas"]),
            "caja_abierta": _caja_abierta(s)}


class RestaurarIn(BaseModel):
    archivo: str = Field(max_length=120)
    # Cuántas ventas le mostró la pantalla a quien confirmó. Si en el intertanto cambió (se
    # cobró algo), la confirmación ya no vale: se tiene que volver a mirar.
    ventas_que_se_pierden: int = Field(ge=0)


def programar_reinicio() -> None:
    """La caja se cierra para volver a abrir con la base restaurada: el .bat o el lanzador la
    levantan de nuevo, igual que después de actualizar. Aparte para que las pruebas lo apaguen."""
    from apps.pos.api.actualizaciones import _cerrar_para_reiniciar
    threading.Timer(1.5, _cerrar_para_reiniciar).start()


@router.post("/restaurar")
def restaurar_respaldo(datos: RestaurarIn, s: Session = Depends(get_session),
                       quien: dict = Depends(exige())):
    """Vuelve la caja a como estaba en un respaldo.

    Antes de tocar nada: el respaldo se revisa entero y tiene que ser de ESTA caja (la regla de
    tools/restaurar.py), y lo que la persona confirmó tiene que ser lo que de verdad se pierde
    hoy. Después se guarda la base de ahora como `antes-de-restaurar-<fecha>.db` —que no se
    borra sola— y recién ahí se reemplaza, con la API de respaldo de SQLite y nunca copiando el
    archivo. La caja se reinicia sola al terminar.
    """
    ruta = _ruta_del_respaldo(datos.archivo)
    if not _cerrojo_restaurar.acquire(blocking=False):
        raise HTTPException(409, "Ya hay una restauración en curso.")
    try:
        visto = rest.comprobar(ruta)
        if not visto["ok"]:
            raise HTTPException(422, visto["detalle"])
        hoy = _ventas_de_hoy(s)
        perderia = max(0, hoy - visto["ventas"])
        if perderia != datos.ventas_que_se_pierden:
            raise HTTPException(
                409, f"Mientras mirabas esto cambió la caja: ahora se perderían {perderia} "
                     f"ventas, no {datos.ventas_que_se_pierden}. Vuelve a elegir el respaldo.")
        # Que no quede ninguna conexión abierta a la base que se va a reemplazar.
        s.rollback()
        s.close()
        engine.dispose()
        hecho = rest.restaurar(ruta)
        engine.dispose()
        if not hecho["ok"]:
            raise HTTPException(409, hecho["detalle"])
    finally:
        _cerrojo_restaurar.release()
    programar_reinicio()
    return {"ok": True, "ventas": hecho["ventas"], "ventas_perdidas": perderia,
            "guardada": os.path.basename(hecho["guardada"]) if hecho.get("guardada") else None,
            "reiniciando": True}
