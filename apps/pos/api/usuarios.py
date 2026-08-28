"""Usuarios y sesión: quién entra a la caja y quién estuvo en cada turno."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.db.models import Presencia, Turno, Usuario
from apps.pos.db.session import get_session
from core.config import NOMBRE_ROL, PERMISOS, a_local, ahora, como_utc
from core.schemas import EntrarIn, SalirIn, UsuarioIn

router = APIRouter(prefix="/api/v1", tags=["usuarios"])

# Colores de las tarjetas del candado. Se reparten solos para que el dueño no
# tenga que elegir uno: en la pantalla táctil lo que importa es distinguirlas
# de un vistazo, no que sean bonitas.
COLORES = ("#C9552B", "#4E7C5B", "#3E6E8E", "#B5892E", "#8C4A6B", "#8A5A34")


def _usuario_dict(u: Usuario, con_rol: bool = True) -> dict:
    d = {"id": u.id, "nombre": u.nombre, "color": u.color, "orden": u.orden}
    if con_rol:
        d["rol"] = u.rol
        d["rol_nombre"] = NOMBRE_ROL.get(u.rol, u.rol)
        d["activo"] = u.activo
        d["ultimo_ingreso"] = (
            a_local(u.ultimo_ingreso_at).isoformat() if u.ultimo_ingreso_at else None
        )
    return d


def _activos(s: Session) -> list[Usuario]:
    return list(s.exec(
        select(Usuario).where(Usuario.activo == True)  # noqa: E712
        .order_by(Usuario.orden, Usuario.id)
    ).all())


# ---------------------------------------------------------------------------
# La pantalla de candado
# ---------------------------------------------------------------------------
@router.get("/candado")
def candado(s: Session = Depends(get_session)):
    """Lo que necesita la pantalla de entrada. No pide sesión, obviamente.

    Devuelve los nombres, nunca los PIN. Que los nombres se vean es a propósito:
    en un local de tres personas, escribir el nombre además del PIN es fricción
    pura y termina en que dejan la sesión abierta todo el día.
    """
    gente = _activos(s)
    return {
        "primer_arranque": not gente,
        "usuarios": [_usuario_dict(u, con_rol=False) for u in gente],
    }


@router.get("/sesion")
def mi_sesion(quien: dict = Depends(sesion.quien_es)):
    """Quién soy y qué puedo hacer. La pantalla apaga botones con esto."""
    return {
        "entrado": bool(quien.get("rol")),
        "provisorio": quien.get("provisorio", False),
        "id": quien.get("id"),
        "nombre": quien.get("nombre"),
        "rol": quien.get("rol"),
        "rol_nombre": NOMBRE_ROL.get(quien.get("rol", ""), ""),
        "permisos": list(PERMISOS.get(quien.get("rol", ""), ())),
    }


@router.post("/sesion/entrar")
def entrar(datos: EntrarIn, respuesta: Response, s: Session = Depends(get_session)):
    u = s.get(Usuario, datos.usuario_id)
    if not u or not u.activo:
        raise HTTPException(404, "Ese usuario ya no está en la caja")
    if not sesion.pin_calza(datos.pin, u.pin_hash):
        # A propósito no decimos si el usuario existe o si el PIN estaba malo:
        # en una pantalla que muestra los nombres, eso solo ayudaría a adivinar.
        raise HTTPException(401, "Ese PIN no es")

    p = sesion.entrar(s, u)
    respuesta.set_cookie(
        sesion.GALLETA, sesion.galleta_de(u, p.id),
        max_age=60 * 60 * sesion.HORAS_DE_SESION, httponly=True, samesite="lax",
    )
    return {"ok": True, **_usuario_dict(u), "permisos": list(PERMISOS.get(u.rol, ()))}


@router.post("/sesion/salir")
def salir(datos: SalirIn, respuesta: Response,
          quien: dict = Depends(sesion.quien_es),
          s: Session = Depends(get_session)):
    if quien.get("id"):
        sesion.cerrar_presencias_abiertas(s, quien["id"], datos.por or "salir")
    respuesta.delete_cookie(sesion.GALLETA)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Administrar la gente
# ---------------------------------------------------------------------------
@router.get("/usuarios")
def listar(s: Session = Depends(get_session),
           quien: dict = Depends(sesion.exige("usuarios"))):
    gente = s.exec(select(Usuario).order_by(Usuario.orden, Usuario.id)).all()
    return [_usuario_dict(u) for u in gente]


@router.post("/usuarios")
def crear(datos: UsuarioIn, s: Session = Depends(get_session),
          quien: dict = Depends(sesion.quien_es)):
    """Crea a alguien.

    El primer usuario lo puede crear cualquiera, porque todavía no hay nadie que
    pueda dar permiso. Del segundo en adelante hace falta el permiso `usuarios`,
    y como el primero se crea siempre como dueño, esa puerta se cierra sola.
    """
    primero = not sesion.hay_usuarios(s)
    if not primero and not _puede_usuarios(quien):
        raise HTTPException(403, "Solo el dueño puede crear usuarios.")
    if not datos.pin:
        raise HTTPException(422, "Ponle un PIN de 4 números.")
    if _nombre_repetido(s, datos.nombre, None):
        raise HTTPException(409, f"Ya hay alguien que se llama {datos.nombre}.")

    u = Usuario(
        nombre=datos.nombre,
        # El primero es SIEMPRE dueño: si se pudiera crear un cajero primero,
        # el local quedaría sin nadie que pueda crear usuarios.
        rol="dueno" if primero else datos.rol,
        pin_hash=sesion.cifrar_pin(datos.pin),
        activo=datos.activo,
        color=datos.color or COLORES[len(_activos(s)) % len(COLORES)],
        orden=datos.orden,
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return _usuario_dict(u)


@router.put("/usuarios/{usuario_id}")
def editar(usuario_id: int, datos: UsuarioIn, s: Session = Depends(get_session),
           quien: dict = Depends(sesion.exige("usuarios"))):
    u = s.get(Usuario, usuario_id)
    if not u:
        raise HTTPException(404, "No existe ese usuario")
    if _nombre_repetido(s, datos.nombre, usuario_id):
        raise HTTPException(409, f"Ya hay alguien que se llama {datos.nombre}.")
    if u.rol == "dueno" and datos.rol != "dueno" and _ultimo_dueno(s, usuario_id):
        raise HTTPException(409, "Es el único dueño: si lo bajas a cajero, nadie "
                                 "podría volver a crear usuarios.")

    u.nombre, u.rol = datos.nombre, datos.rol
    u.activo, u.orden = datos.activo, datos.orden
    if datos.color:
        u.color = datos.color
    if datos.pin:
        u.pin_hash = sesion.cifrar_pin(datos.pin)
    s.add(u)
    s.commit()
    s.refresh(u)
    return _usuario_dict(u)


@router.delete("/usuarios/{usuario_id}")
def sacar(usuario_id: int, s: Session = Depends(get_session),
          quien: dict = Depends(sesion.exige("usuarios"))):
    """Lo saca de la caja. No lo borra: sus ventas tienen que seguir cuadrando."""
    u = s.get(Usuario, usuario_id)
    if not u:
        raise HTTPException(404, "No existe ese usuario")
    if _ultimo_dueno(s, usuario_id):
        raise HTTPException(409, "Es el único dueño. Nombra a otro antes de sacarlo.")
    u.activo = False
    sesion.cerrar_presencias_abiertas(s, u.id, "salir")
    s.add(u)
    s.commit()
    return {"ok": True, "aviso": f"{u.nombre} ya no entra a la caja."}


def _puede_usuarios(quien: dict) -> bool:
    return "usuarios" in PERMISOS.get(quien.get("rol", ""), ())


def _nombre_repetido(s: Session, nombre: str, salvo_id: int | None) -> bool:
    otro = s.exec(
        select(Usuario).where(Usuario.nombre == nombre, Usuario.activo == True)  # noqa: E712
    ).first()
    return bool(otro and otro.id != salvo_id)


def _ultimo_dueno(s: Session, usuario_id: int) -> bool:
    duenos = s.exec(
        select(Usuario).where(Usuario.rol == "dueno", Usuario.activo == True)  # noqa: E712
    ).all()
    return len(duenos) == 1 and duenos[0].id == usuario_id


# ---------------------------------------------------------------------------
# Quién estuvo
# ---------------------------------------------------------------------------
@router.get("/turnos/{turno_id}/presencias")
def presencias_del_turno(turno_id: int, s: Session = Depends(get_session)):
    """Quién estuvo en la caja durante ese turno, y cuánto rato.

    Esta es la pregunta que originó todo el sistema de usuarios. Con solo el
    autor de cada venta, alguien que atendió dos horas sin cobrar nada no
    aparecería en ninguna parte.
    """
    t = s.get(Turno, turno_id)
    if not t:
        raise HTTPException(404, "No existe ese turno")

    filas = s.exec(
        select(Presencia).where(Presencia.turno_id == turno_id)
        .order_by(Presencia.entro_at)
    ).all()

    fin_del_turno = como_utc(t.cerrado_at) if t.cerrado_at else ahora()
    gente: dict[int, dict] = {}
    for p in filas:
        u = s.get(Usuario, p.usuario_id)
        d = gente.setdefault(p.usuario_id, {
            "usuario_id": p.usuario_id,
            "nombre": u.nombre if u else "(borrado)",
            "color": u.color if u else "",
            "minutos": 0,
            "tramos": [],
        })
        hasta = como_utc(p.salio_at) if p.salio_at else fin_del_turno
        minutos = max(0, int((hasta - como_utc(p.entro_at)).total_seconds() // 60))
        d["minutos"] += minutos
        d["tramos"].append({
            "desde": a_local(p.entro_at).strftime("%H:%M"),
            "hasta": a_local(hasta).strftime("%H:%M") if p.salio_at else None,
            "minutos": minutos,
            "salida_por": p.salida_por,
        })

    return {
        "turno_id": turno_id,
        "abrio": _nombre_de(s, t.abierto_por_id) or t.cajero,
        "cerro": _nombre_de(s, t.cerrado_por_id),
        "estuvieron": sorted(gente.values(), key=lambda g: -g["minutos"]),
    }


def _nombre_de(s: Session, usuario_id: int | None) -> str:
    if not usuario_id:
        return ""
    u = s.get(Usuario, usuario_id)
    return u.nombre if u else ""
