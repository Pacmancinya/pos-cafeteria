"""Si esta caja se mudó desde una carpeta vieja, para avisárselo al dueño."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from apps.pos import acceso, mudanza

router = APIRouter(prefix="/api/v1", tags=["mudanza"])


class DescartarIn(BaseModel):
    confirmar: bool = False


@router.get("/mudanza")
def ver():
    """El estado de la mudanza: ninguna, hecha (completa o no), error (pendiente) o no_hecha."""
    return mudanza.estado()


@router.post("/mudanza/visto")
def visto():
    """El dueño cerró el aviso: no se vuelve a mostrar."""
    mudanza.marcar_visto()
    return {"ok": True}


@router.post("/mudanza/reintentar")
def reintentar():
    """Vuelve a intentar la mudanza (o la copia de lo que faltó). Acá ya estamos
    escuchando en el puerto, así que no se revisa. Una sola operación a la vez: si hay
    otra en curso (reintentar o descartar), responde 409."""
    try:
        with mudanza.operacion():
            _soltar_la_base()
            mudanza.ejecutar(puerto=None)
            _abrir_la_base_si_corresponde()
            return mudanza.estado()
    except mudanza.MudanzaEnCurso as e:
        raise HTTPException(409, str(e))


def _soltar_la_base() -> None:
    """Si la base se va a reemplazar, que no quede ninguna conexión abierta a la vieja."""
    from apps.pos.db.session import engine
    engine.dispose()


def _abrir_la_base_si_corresponde() -> None:
    """Mientras la mudanza estaba pendiente el arranque no tocó la base: ahora que se
    resolvió, se hace lo que el arranque habría hecho (crear tablas y migraciones)."""
    if not mudanza.pendiente() and not mudanza.bloqueada():
        from apps.pos.db.session import crear_tablas, engine
        engine.dispose()
        crear_tablas()


@router.post("/mudanza/descartar")
def descartar(datos: DescartarIn, request: Request):
    """«Esta caja es nueva, no traer nada». Pide confirmación y solo desde este computador.
    Todo —incluido crear las tablas— ocurre dentro del mismo bloqueo que reintentar."""
    if not acceso.es_local(request):
        raise HTTPException(403, "Esto solo se hace desde el computador de la caja.")
    if not datos.confirmar:
        raise HTTPException(422, "Falta confirmar.")
    try:
        with mudanza.operacion():
            resultado = mudanza.descartar()
            _abrir_la_base_si_corresponde()
            return resultado
    except mudanza.MudanzaEnCurso as e:
        raise HTTPException(409, str(e))
