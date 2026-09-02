"""Turnos de caja: abrir, cerrar y cuadrar el efectivo.

El cierre se hace por **arqueo**: se cuenta cuántos billetes y monedas de cada
denominación hay, y el total lo saca el programa. Es mucho más difícil
equivocarse contando billetes que escribiendo un total de memoria — y además
queda guardado DÓNDE estuvo el error, no solo cuánto faltó.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.db.models import Presencia, Turno, Usuario, Venta
from apps.pos.db.session import get_session
from core.config import (DENOMINACIONES, MEDIOS_PAGO, NOMBRE_MEDIO, a_local, ahora,
                         como_utc, hoy_local, puede, rango_utc_del_dia,
                         total_del_conteo)
from core.schemas import AbrirTurnoIn, CerrarTurnoIn

router = APIRouter(prefix="/api/v1/turnos", tags=["turnos"])


def turno_abierto(s: Session) -> Turno | None:
    return s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711


def _efectivo_del_turno(s: Session, turno: Turno) -> int:
    ventas = s.exec(
        select(Venta).where(
            Venta.turno_id == turno.id,
            Venta.estado == "pagada",
            Venta.medio_pago == "efectivo",
        )
    ).all()
    # Lo que quedó en el cajón: lo cobrado (ya con el descuento aplicado) más la propina.
    return sum(v.total - v.descuento + v.propina for v in ventas)


def _por_medio(s: Session, turno: Turno) -> dict:
    """Lo vendido en el turno, separado por forma de pago.

    `cobrado` incluye la propina y `ventas` no, y esa distinción es la que hace
    que el cuadre de tarjetas sirva: la máquina del banco le cobró al cliente el
    total CON propina, así que comparar contra `ventas` daría una diferencia
    falsa todos los días, exactamente del tamaño de las propinas.
    """
    ventas = s.exec(
        select(Venta).where(Venta.turno_id == turno.id, Venta.estado == "pagada")
    ).all()
    salida: dict[str, dict] = {}
    for v in ventas:
        d = salida.setdefault(v.medio_pago,
                              {"cantidad": 0, "ventas": 0, "propinas": 0, "total": 0})
        d["cantidad"] += 1
        d["ventas"] += v.total - v.descuento
        d["propinas"] += v.propina
        # `total` se mantiene con el nombre viejo por compatibilidad: es lo
        # vendido sin propina, que es lo que mira el informe del día.
        d["total"] += v.total - v.descuento
    for d in salida.values():
        d["cobrado"] = d["ventas"] + d["propinas"]
    return salida


def _cuadre_de_medios(s: Session, t: Turno) -> list[dict]:
    """Lo que dice el POS contra lo que dice el banco, medio por medio.

    El efectivo se cuenta y va aparte. Esto es para lo otro: el comprobante de
    cierre de la máquina y lo que muestra la app del banco. Si no lo escribieron,
    `declarado` y `diferencia` quedan en None — no se inventa un cuadre.
    """
    declarado = _conteo(t.conteo_medios)
    filas = []
    for medio, d in _por_medio(s, t).items():
        if medio == "efectivo":
            continue
        dicho = declarado.get(medio)
        try:
            dicho = int(dicho) if dicho is not None else None
        except (TypeError, ValueError):
            dicho = None
        filas.append({
            "medio": medio,
            "nombre": NOMBRE_MEDIO.get(medio, medio),
            "cantidad": d["cantidad"],
            "ventas": d["ventas"],
            "propinas": d["propinas"],
            "esperado": d["cobrado"],          # con propina: es lo que se cobró
            "declarado": dicho,
            "diferencia": None if dicho is None else dicho - d["cobrado"],
        })
    return sorted(filas, key=lambda f: -f["esperado"])


def _propinas(s: Session, t: Turno) -> dict:
    """Cuánta propina entró, y en qué forma.

    Importa separarlas: la propina en efectivo ya está en el cajón, y la de
    tarjeta se la quedó el banco y hay que pagársela al equipo aparte.
    """
    por = _por_medio(s, t)
    efectivo = por.get("efectivo", {}).get("propinas", 0)
    tarjeta = sum(d["propinas"] for m, d in por.items() if m != "efectivo")
    return {"efectivo": efectivo, "tarjeta": tarjeta, "total": efectivo + tarjeta}


def _conteo(texto: str) -> dict:
    try:
        return json.loads(texto) if texto else {}
    except ValueError:
        return {}


def _turno_dict(s: Session, t: Turno) -> dict:
    ventas_efectivo = _efectivo_del_turno(s, t)
    return {
        "id": t.id,
        "cajero": t.cajero,
        "abierto_at": a_local(t.abierto_at).isoformat(),
        "cerrado_at": a_local(t.cerrado_at).isoformat() if t.cerrado_at else None,
        "monto_inicial": t.monto_inicial,
        "ventas_efectivo": ventas_efectivo,
        "efectivo_esperado": t.monto_inicial + ventas_efectivo,
        "efectivo_contado": t.efectivo_contado,
        "diferencia": t.diferencia,
        "retiro": t.retiro,
        "fondo_siguiente": t.fondo_siguiente,
        "conteo_apertura": _conteo(t.conteo_apertura),
        "conteo_cierre": _conteo(t.conteo_cierre),
        "por_medio": _por_medio(s, t),
        "medios": _cuadre_de_medios(s, t),
        "propinas": _propinas(s, t),
        "nota": t.nota,
        "abrio": _nombre(s, t.abierto_por_id) or t.cajero,
        "cerro": _nombre(s, t.cerrado_por_id),
        # El ID y no solo el nombre: dos personas distintas pueden llamarse
        # igual (el chequeo de nombre repetido solo mira a los ACTIVOS, así que
        # un "Javi" que sacaron y un "Javi" nuevo conviven sin problema).
        "abierto_por_id": t.abierto_por_id,
        # Con cuánto se supone que partió el cajón, según el cierre anterior.
        # Es la primera sospecha cuando el arqueo no cuadra: si el fondo de la
        # mañana se contó de menos, el sobrante aparece recién en la noche y
        # parece salido de la nada.
        "fondo_anterior": _fondo_que_quedo(s, t),
        # Quiénes pasaron por la caja durante el turno. Es la respuesta a
        # "¿quién estuvo?", que no es lo mismo que "¿quién vendió?".
        "estuvieron": _estuvieron(s, t),
    }


def _nombre(s: Session, usuario_id: int | None) -> str:
    if not usuario_id:
        return ""
    u = s.get(Usuario, usuario_id)
    return u.nombre if u else ""


def _fondo_que_quedo(s: Session, t: Turno) -> int | None:
    """Cuánto dejó de fondo el turno cerrado justo antes de este. None si no hay.

    Sirve para una sola pregunta, que es la que más veces explica un descuadre:
    ¿el cajón de la mañana tenía lo que decía tener?
    """
    anterior = s.exec(
        select(Turno).where(Turno.cerrado_at != None, Turno.id != t.id)  # noqa: E711
        .order_by(Turno.cerrado_at.desc())
    ).first()
    return anterior.fondo_siguiente if anterior else None


def _quien_la_abrio(s: Session, t: Turno) -> tuple[int | None, str]:
    """(id, nombre) de quien abrió esta caja, o (None, "") si no la reclamó nadie.

    Devolver None NO es un detalle: es lo que hace que la regla no trabe cajas
    que ya existían. Hay tres formas legítimas de que un turno no tenga dueño:

      · se abrió antes de que existieran los usuarios (todos los turnos de la
        base del local están así, incluido el que está abierto ahora mismo);
      · se abrió en modo provisorio, cuando todavía no había nadie creado;
      · lo creó la carta de ejemplo.

    Y una cuarta, ilegítima pero posible: que la fila del usuario ya no exista
    porque alguien la borró a mano en SQLite. También cuenta como "sin dueño":
    una caja que nadie puede nombrar no puede ser una caja que nadie puede
    cerrar.
    """
    if not t.abierto_por_id:
        return None, ""
    u = s.get(Usuario, t.abierto_por_id)
    if not u:
        return None, ""
    return u.id, u.nombre


def _no_es_tuya(s: Session, t: Turno) -> str:
    """El 403 tiene que decirle al cajero QUÉ HACER, no solo que no puede.

    Un "no tienes permiso" a las diez de la noche, con el cajón contado y el
    local cerrando, no resuelve nada.
    """
    _, nombre = _quien_la_abrio(s, t)
    quien_abrio = nombre or t.cajero or "otra persona"
    u = s.get(Usuario, t.abierto_por_id) if t.abierto_por_id else None
    if u and not u.activo:
        return (f"Esta caja la abrió {quien_abrio}, que ya no entra a la caja. "
                "La tiene que cerrar el dueño.")
    return (f"Esta caja la abrió {quien_abrio}: la cierra {quien_abrio} o el dueño. "
            "Es para que el descuadre tenga a quién preguntarle.")


def _estuvieron(s: Session, t: Turno) -> list[dict]:
    filas = s.exec(select(Presencia).where(Presencia.turno_id == t.id)).all()
    fin = como_utc(t.cerrado_at) if t.cerrado_at else ahora()
    gente: dict[int, dict] = {}
    for p in filas:
        u = s.get(Usuario, p.usuario_id)
        d = gente.setdefault(p.usuario_id, {
            "usuario_id": p.usuario_id,
            "nombre": u.nombre if u else "(borrado)",
            "color": u.color if u else "",
            "minutos": 0,
        })
        hasta = como_utc(p.salio_at) if p.salio_at else fin
        d["minutos"] += max(0, int((hasta - como_utc(p.entro_at)).total_seconds() // 60))
    return sorted(gente.values(), key=lambda g: -g["minutos"])


@router.get("/denominaciones")
def denominaciones():
    """Los billetes y monedas con los que se cuenta la caja."""
    return {"denominaciones": list(DENOMINACIONES)}


@router.get("/actual")
def actual(s: Session = Depends(get_session)):
    t = turno_abierto(s)
    ultimo = s.exec(
        select(Turno).where(Turno.cerrado_at != None)          # noqa: E711
        .order_by(Turno.cerrado_at.desc())
    ).first()
    return {
        "abierto": bool(t),
        "turno": _turno_dict(s, t) if t else None,
        # Con cuánto quedó el cajón anoche. Va también con la caja CERRADA
        # porque es justo lo que hace falta al abrirla en la mañana: contar
        # contra un número, en vez de contar a ciegas y descubrir la diferencia
        # doce horas después, cuando ya no hay cómo saber de dónde salió.
        "fondo_anterior": ultimo.fondo_siguiente if ultimo else None,
    }


@router.get("")
def historial(
    desde: str | None = Query(default=None),
    hasta: str | None = Query(default=None),
    s: Session = Depends(get_session),
):
    """Los cierres de caja de un rango. Sin esto el dueño no puede revisar
    los descuadres de los días pasados, que es justo para lo que sirven."""
    d1 = date.fromisoformat(desde) if desde else hoy_local()
    d2 = date.fromisoformat(hasta) if hasta else d1
    ini, _ = rango_utc_del_dia(d1)
    _, fin = rango_utc_del_dia(d2)
    turnos = s.exec(
        select(Turno)
        .where(Turno.abierto_at >= ini, Turno.abierto_at < fin)
        .order_by(Turno.abierto_at.desc())
    ).all()
    return [_turno_dict(s, t) for t in turnos]


@router.post("/abrir")
def abrir(datos: AbrirTurnoIn, s: Session = Depends(get_session),
          quien: dict = Depends(sesion.exige("turno_abrir"))):
    if turno_abierto(s):
        raise HTTPException(409, "Ya hay un turno abierto; primero hay que cerrarlo")
    # Si contaron el fondo por denominación, ese total manda sobre el escrito.
    inicial = total_del_conteo(datos.conteo) if datos.conteo else datos.monto_inicial
    t = Turno(
        # El nombre queda COPIADO además del id: congela cómo se llamaba la
        # persona ese día, igual que VentaLinea congela el precio.
        cajero=datos.cajero or quien.get("nombre", ""),
        abierto_por_id=quien.get("id"),
        monto_inicial=inicial,
        conteo_apertura=json.dumps(datos.conteo) if datos.conteo else "",
    )
    s.add(t)
    s.commit()
    s.refresh(t)
    # La presencia que estaba abierta antes del turno pasa a contarse en él:
    # quien abrió la caja ya estaba adentro un rato antes.
    for p in s.exec(select(Presencia).where(
            Presencia.salio_at == None, Presencia.turno_id == None)).all():  # noqa: E711
        p.turno_id = t.id
        s.add(p)
    s.commit()
    return _turno_dict(s, t)


@router.get("/{turno_id}/ventas")
def ventas_del_turno(turno_id: int, s: Session = Depends(get_session),
                     quien: dict = Depends(sesion.exige("ver_dia"))):
    """Las ventas de un turno, una por una.

    Existe para BUSCAR UN DESCUADRE. Hasta ahora el cierre decía "sobran $1.450"
    y ahí quedaba: el dueño sabía que algo no calzaba y no tenía dónde mirar.

    El caso que se repite, y que lo dijo él: en tarjeta puede haber más en el
    sistema que en la vida real. Una venta se marcó como débito, la máquina la
    rechazó y nadie la anuló; o se cobró en efectivo y se registró como tarjeta.
    Con la lista al lado, esa venta se encuentra en diez segundos.
    """
    t = s.get(Turno, turno_id)
    if not t:
        raise HTTPException(404, "No existe ese turno")

    ventas = s.exec(
        select(Venta).where(Venta.turno_id == turno_id).order_by(Venta.creada_at.desc())
    ).all()
    return [{
        "id": v.id,
        "numero": v.numero,
        "hora": a_local(v.creada_at).strftime("%H:%M"),
        "medio_pago": v.medio_pago,
        "medio": NOMBRE_MEDIO.get(v.medio_pago, v.medio_pago),
        # Lo COBRADO, que es lo que la máquina o el cajón tienen que tener:
        # el descuento ya está descontado y la propina va incluida.
        "cobrado": v.total - v.descuento + v.propina,
        "propina": v.propina,
        "anulada": v.estado != "pagada",
    } for v in ventas]


@router.post("/cerrar")
def cerrar(datos: CerrarTurnoIn, s: Session = Depends(get_session),
           quien: dict = Depends(sesion.exige("turno_cerrar"))):
    """Guarda la diferencia AUNQUE DESCUADRE. Esconder el descuadre sería
    justamente lo contrario de para lo que sirve cuadrar la caja."""
    t = turno_abierto(s)
    if not t:
        raise HTTPException(409, "No hay ningún turno abierto")

    dueno_del_turno, _ = _quien_la_abrio(s, t)
    if dueno_del_turno and dueno_del_turno != quien.get("id")             and not puede(quien.get("rol", ""), "turno_cerrar_ajeno"):
        raise HTTPException(403, _no_es_tuya(s, t))

    esperado = t.monto_inicial + _efectivo_del_turno(s, t)
    contado = total_del_conteo(datos.conteo) if datos.conteo else datos.efectivo_contado

    t.efectivo_contado = contado
    t.diferencia = contado - esperado
    t.conteo_cierre = json.dumps(datos.conteo) if datos.conteo else ""
    # Lo que queda de fondo para mañana no puede ser más de lo que hay en el cajón.
    t.fondo_siguiente = min(datos.fondo_siguiente, contado)
    # El retiro es lo que se saca: si no lo dicen, es todo lo que no queda de fondo.
    t.retiro = datos.retiro if datos.retiro else max(0, contado - t.fondo_siguiente)
    t.nota = datos.nota
    # Solo se guardan los medios que existen: una clave inventada no entra.
    medios = {m: int(v) for m, v in (datos.medios or {}).items()
              if m in MEDIOS_PAGO and m != "efectivo" and str(v).strip() != ""}
    t.conteo_medios = json.dumps(medios) if medios else ""
    t.cerrado_at = ahora()
    t.cerrado_por_id = quien.get("id")
    s.add(t)
    s.commit()
    s.refresh(t)
    salida = _turno_dict(s, t)

    # Cerrar la caja es el otro momento natural para respaldar: el día ya está completo.
    try:
        from tools.respaldo import respaldar
        respaldar("cierre de caja")
    except Exception:
        pass

    # Y queda por escrito en un CSV que se abre con doble clic, sin depender de
    # que alguien se acuerde de exportar.
    try:
        from tools.registro import anotar_cierre
        salida["registro"] = anotar_cierre(salida)
    except Exception:
        pass
    return salida
