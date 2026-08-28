"""Quién está frente a la pantalla.

Esto es un candado distinto al de `acceso.py`, y por eso son dos archivos:

  · `acceso.py` cuida la RED: qué equipo puede hablarle a la caja. Desde el
    propio PC de la caja deja pasar libre.
  · esto cuida la IDENTIDAD: quién es la persona. Desde el propio PC de la caja
    NO deja pasar libre — es justamente ahí donde hay que saber quién vendió.

Son reglas opuestas para la misma dirección IP, así que no pueden ser la misma
función por más que las dos se llamen "candado".

## La regla del arranque en frío

Si en la base no hay ningún usuario activo, el punto de venta **funciona igual**
y todo el mundo entra como dueño. Es a propósito, por dos razones:

  1. La caja del local ya está vendiendo con una base sin usuarios. Si esta
     actualización exigiera login, el lunes en la mañana nadie podría cobrar.
  2. Un sistema de usuarios que se puede dejar a medio configurar y deja la caja
     inutilizable es peor que no tener usuarios.

Al crear el primer usuario esa puerta se cierra sola y ya no se vuelve a abrir
mientras quede alguien activo.

## La sesión

Una galleta firmada con HMAC, no una tabla de sesiones: la caja es un solo
computador y no vale la pena escribir en SQLite en cada clic. Lo que SÍ va a la
base es la presencia (quién estuvo y hasta cuándo), que es el dato que el dueño
pidió y que tiene que sobrevivir a que se cierre el navegador.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from apps.pos.db.models import Presencia, Usuario
from apps.pos.db.session import get_session
from core.config import RAIZ, SECRETO, ahora, puede

GALLETA = "pos_sesion"

# Cuánto vale la galleta antes de exigir el PIN de nuevo. Un turno largo con
# horas extra cabe holgado; un computador que quedó prendido el fin de semana,
# no. El bloqueo por inactividad es otra cosa y lo maneja la pantalla.
HORAS_DE_SESION = 20

ITERACIONES = 180_000


# ---------------------------------------------------------------------------
# El PIN
# ---------------------------------------------------------------------------
def cifrar_pin(pin: str) -> str:
    """PBKDF2-HMAC-SHA256 con sal. Solo biblioteca estándar: meter una
    dependencia nueva para esto obligaría a bajarla en el local."""
    sal = secrets.token_bytes(16)
    clave = hashlib.pbkdf2_hmac("sha256", pin.encode(), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal.hex()}${clave.hex()}"


def pin_calza(pin: str, guardado: str) -> bool:
    try:
        _, iteraciones, sal_hex, esperado = guardado.split("$")
        clave = hashlib.pbkdf2_hmac(
            "sha256", pin.encode(), bytes.fromhex(sal_hex), int(iteraciones)
        )
    except (ValueError, AttributeError):
        return False
    # compare_digest y no ==: comparar en tiempo constante para no filtrar
    # cuántos caracteres iban bien.
    return hmac.compare_digest(clave.hex(), esperado)


# ---------------------------------------------------------------------------
# La firma de la galleta
# ---------------------------------------------------------------------------
_secreto_en_memoria = ""


def _secreto() -> str:
    """La clave con la que se firman las sesiones de ESTA caja.

    Se guarda en un archivo suelto y no en la base para que un respaldo de
    `pos.db` que alguien mande por correo no venga con la llave adentro. El
    archivo empieza con punto: el actualizador nunca lo pisa.
    """
    global _secreto_en_memoria
    if SECRETO:
        return SECRETO
    if _secreto_en_memoria:
        return _secreto_en_memoria
    ruta = os.path.join(RAIZ, ".secreto")
    try:
        with open(ruta, encoding="utf-8") as f:
            _secreto_en_memoria = f.read().strip()
    except OSError:
        _secreto_en_memoria = ""
    if not _secreto_en_memoria:
        _secreto_en_memoria = secrets.token_hex(32)
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(_secreto_en_memoria)
        except OSError:
            pass          # sin disco escribible seguimos, pero la sesión durará lo que el proceso
    return _secreto_en_memoria


def _firmar(carga: dict) -> str:
    crudo = json.dumps(carga, separators=(",", ":"), sort_keys=True).encode()
    cuerpo = base64.urlsafe_b64encode(crudo).decode().rstrip("=")
    firma = hmac.new(_secreto().encode(), cuerpo.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{cuerpo}.{firma}"


def _abrir(galleta: str) -> Optional[dict]:
    try:
        cuerpo, firma = galleta.split(".")
    except (ValueError, AttributeError):
        return None
    esperada = hmac.new(_secreto().encode(), cuerpo.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(firma, esperada):
        return None
    try:
        relleno = "=" * (-len(cuerpo) % 4)
        carga = json.loads(base64.urlsafe_b64decode(cuerpo + relleno))
    except (ValueError, TypeError):
        return None
    try:
        emitida = datetime.fromisoformat(carga["t"])
    except (KeyError, ValueError):
        return None
    if emitida.tzinfo is None:
        emitida = emitida.replace(tzinfo=timezone.utc)
    if ahora() - emitida > timedelta(hours=HORAS_DE_SESION):
        return None
    return carga


def galleta_de(u: Usuario, presencia_id: Optional[int]) -> str:
    return _firmar({
        "uid": u.id, "nombre": u.nombre, "rol": u.rol,
        "pre": presencia_id, "t": ahora().isoformat(),
    })


# ---------------------------------------------------------------------------
# Quién entra
# ---------------------------------------------------------------------------
def hay_usuarios(s: Session) -> bool:
    return s.exec(select(Usuario).where(Usuario.activo == True)).first() is not None  # noqa: E712


# El dueño de mentira del arranque en frío. No existe en la base y no puede
# vender bajo su nombre: en cuanto se crea el primer usuario, desaparece.
PROVISORIO = {"id": None, "nombre": "", "rol": "dueno", "presencia_id": None,
              "provisorio": True}


def quien_es(request: Request, s: Session = Depends(get_session)) -> dict:
    """El usuario de esta petición. Nunca lanza: dice quién es o dice que nadie."""
    if not hay_usuarios(s):
        return dict(PROVISORIO)
    carga = _abrir(request.cookies.get(GALLETA, ""))
    if not carga:
        return {"id": None, "nombre": "", "rol": "", "presencia_id": None,
                "provisorio": False}
    u = s.get(Usuario, carga.get("uid"))
    if not u or not u.activo:
        return {"id": None, "nombre": "", "rol": "", "presencia_id": None,
                "provisorio": False}
    # El rol se lee de la base y no de la galleta: si al cajero lo ascienden o
    # lo bajan, tiene efecto al toque y no cuando venza la galleta.
    return {"id": u.id, "nombre": u.nombre, "rol": u.rol,
            "presencia_id": carga.get("pre"), "provisorio": False}


def exige_entrar(quien: dict = Depends(quien_es)) -> dict:
    if not quien.get("rol"):
        raise HTTPException(401, "Hay que entrar con el PIN para hacer esto.")
    return quien


def exige(permiso: str):
    """Dependencia que pide un permiso concreto.

        @router.post("/productos", dependencies=[Depends(exige("editar_carta"))])
    """
    def guardia(quien: dict = Depends(exige_entrar)) -> dict:
        if not puede(quien["rol"], permiso):
            raise HTTPException(
                403, f"{quien['nombre'] or 'Este usuario'} no tiene permiso para esto. "
                     "Lo puede hacer el dueño.")
        return quien
    return guardia


# ---------------------------------------------------------------------------
# La presencia
# ---------------------------------------------------------------------------
def turno_abierto_id(s: Session) -> Optional[int]:
    from apps.pos.db.models import Turno
    t = s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711
    return t.id if t else None


def entrar(s: Session, u: Usuario) -> Presencia:
    """Deja anotado que esta persona está en la caja desde ahora."""
    cerrar_presencias_abiertas(s, u.id, "cambio")
    p = Presencia(usuario_id=u.id, turno_id=turno_abierto_id(s))
    u.ultimo_ingreso_at = ahora()
    s.add(p)
    s.add(u)
    s.commit()
    s.refresh(p)
    return p


def cerrar_presencias_abiertas(s: Session, usuario_id: Optional[int], por: str) -> int:
    """Cierra las presencias que quedaron abiertas de esa persona.

    Pasa más seguido de lo que uno cree: se corta la luz, se cierra la ventana
    de golpe, se reinicia el computador. Una presencia que nunca cierra diría
    que alguien estuvo trabajando tres días seguidos.
    """
    consulta = select(Presencia).where(Presencia.salio_at == None)  # noqa: E711
    if usuario_id is not None:
        consulta = consulta.where(Presencia.usuario_id == usuario_id)
    abiertas = s.exec(consulta).all()
    for p in abiertas:
        p.salio_at = ahora()
        p.salida_por = por
        s.add(p)
    if abiertas:
        s.commit()
    return len(abiertas)
