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
from apps.pos.db.models import Presencia, RetiroCaja, Turno, Usuario, Venta
from apps.pos.db.session import get_session
from core.config import (DENOMINACIONES, MEDIOS_PAGO, NOMBRE_MEDIO, a_local, ahora,
                         como_utc, hoy_local, puede, rango_utc_del_dia,
                         total_del_conteo)
from core.schemas import AbrirTurnoIn, CerrarTurnoIn, RetiroCajaIn

router = APIRouter(prefix="/api/v1/turnos", tags=["turnos"])


def _clp(n: int) -> str:
    """$1.234, para los mensajes que ve el cajero. En impresion.py está el mismo
    con otro nombre, pero importarlo de allá sería un import circular."""
    return "$" + f"{int(n):,}".replace(",", ".")


def turno_abierto(s: Session) -> Turno | None:
    return s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711


def _pagos_de(s: Session, v: Venta) -> list[tuple[str, int]]:
    """Cómo se pagó una venta: [(medio, monto), ...], con el monto SIN propina.

    Si la venta tiene filas de Pago (pago mixto), esas mandan. Si no —una venta
    de un solo medio, o cualquiera anterior a que esto existiera— es un solo pago
    con su `medio_pago` y lo cobrado sin propina. La propina se suma aparte, al
    `medio_pago` de la venta, y por eso el pago mixto va sin propina.
    """
    from apps.pos.db.models import Pago
    filas = s.exec(select(Pago).where(Pago.venta_id == v.id)).all()
    if filas:
        return [(p.medio, p.monto) for p in filas]
    return [(v.medio_pago, v.total - v.descuento)]


def _efectivo_del_turno(s: Session, turno: Turno) -> int:
    """Lo que quedó en el cajón por las ventas: la parte pagada en efectivo, con
    su propina si la propina fue en efectivo. Recorre TODAS las ventas pagadas,
    no solo las de medio_pago efectivo, porque un pago mixto tiene una parte en
    efectivo aunque su medio_pago sea 'mixto'."""
    ventas = s.exec(
        select(Venta).where(Venta.turno_id == turno.id, Venta.estado == "pagada")
    ).all()
    total = 0
    for v in ventas:
        for medio, monto in _pagos_de(s, v):
            if medio == "efectivo":
                total += monto
        if v.propina and v.medio_pago == "efectivo":
            total += v.propina
    return total


def _movimientos_caja(s: Session, turno: Turno, tipo: str) -> int:
    """Suma la plata que se movió a mano en el turno, de un tipo (retiro/ingreso).

    Los anulados no cuentan: quedan en el libro para que se vea que existieron,
    pero no se movieron de verdad, así que no tocan el efectivo.
    """
    filas = s.exec(
        select(RetiroCaja).where(
            RetiroCaja.turno_id == turno.id,
            RetiroCaja.tipo == tipo,
            RetiroCaja.anulado == False,          # noqa: E712
        )
    ).all()
    return sum(r.monto for r in filas)


def _retiros_del_turno(s: Session, turno: Turno) -> int:
    return _movimientos_caja(s, turno, "retiro")


def _ingresos_del_turno(s: Session, turno: Turno) -> int:
    return _movimientos_caja(s, turno, "ingreso")


def _efectivo_esperado(s: Session, turno: Turno) -> int:
    """Lo que DEBERÍA haber en el cajón, en un solo lugar.

    Es fondo + lo que entró en efectivo − lo que salió + lo que se metió a mano.
    "Salió" son dos cosas: las propinas de tarjeta pagadas en efectivo (el banco
    no las depositó todavía) y los retiros de medio turno (el pan, el gas). "Se
    metió" son los ingresos: plata que se repone al cajón. Sin esto, esa plata
    aparece en la noche como un faltante (o un sobrante) que no existe.

    Existe como función y no como cuentas sueltas a propósito: antes el cierre,
    la pantalla y el papel de 80 mm la calculaban por separado, y no siempre
    daban lo mismo. Ahora es una.
    """
    return (turno.monto_inicial + _efectivo_del_turno(s, turno)
            - turno.propinas_pagadas
            - _retiros_del_turno(s, turno) + _ingresos_del_turno(s, turno))


def _retiros_dict(s: Session, turno: Turno) -> list[dict]:
    """Los movimientos de plata del turno (retiros e ingresos), uno por uno."""
    filas = s.exec(
        select(RetiroCaja).where(RetiroCaja.turno_id == turno.id)
        .order_by(RetiroCaja.creado_at.desc())
    ).all()
    return [{
        "id": r.id,
        "tipo": r.tipo,
        "monto": r.monto,
        "motivo": r.motivo,
        "hora": a_local(r.creado_at).strftime("%H:%M"),
        "hecho_por": r.hecho_por,
        "anulado": r.anulado,
        "anulado_por": r.anulado_por,
    } for r in filas]


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

    def _fila(medio):
        return salida.setdefault(medio,
                                 {"cantidad": 0, "ventas": 0, "propinas": 0, "total": 0})

    for v in ventas:
        pagos = _pagos_de(s, v)
        # `cantidad` cuenta ventas, no pagos: una venta mixta es UNA venta. Se le
        # suma al medio de su primer pago para no contarla dos veces.
        primero = True
        for medio, monto in pagos:
            d = _fila(medio)
            if primero:
                d["cantidad"] += 1
                primero = False
            d["ventas"] += monto
            d["total"] += monto        # nombre viejo: lo vendido sin propina
        # La propina va al medio_pago de la venta. En un pago mixto la venta va
        # sin propina (medio_pago = "mixto"), así que esto no la toca.
        if v.propina:
            _fila(v.medio_pago)["propinas"] += v.propina

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
    propinas_dichas = _conteo(t.propinas_medios)
    por_medio = _por_medio(s, t)

    # Qué medios llevan fila: los que la caja REGISTRÓ, más los que el cajero
    # DECLARÓ aunque la caja no registrara ninguno.
    #
    # Ese segundo caso no es un borde raro: es la máquina diciendo que hubo un
    # débito que acá quedó cobrado como efectivo, o que no quedó. Es el descuadre
    # más grande que puede haber, y hasta ahora era el único invisible — el
    # cierre armaba las filas recorriendo las ventas, así que un medio sin
    # ventas no tenía fila, y lo que el cajero escribió se guardaba en la base
    # sin aparecer nunca ni en el cierre ni en el papel de 80 mm.
    medios = [m for m in por_medio if m != "efectivo"]
    # Se mira también `propinas_dichas`: alguien puede escribir solo la propina
    # de la máquina sin escribir el total, y esa fila tiene que existir igual.
    escritos = list(declarado) + [m for m in propinas_dichas if m not in declarado]
    medios += [m for m in escritos
               if m in MEDIOS_PAGO and m != "efectivo" and m not in por_medio]

    filas = []
    for medio in medios:
        d = por_medio.get(medio, {"cantidad": 0, "ventas": 0, "propinas": 0, "cobrado": 0})
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
            # La propina según la MÁQUINA, que puede no ser la que registró la
            # caja: el cliente la deja en el pinpad y el cajero no siempre la
            # anota.
            "propina_dicha": propinas_dichas.get(medio),
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
        "efectivo_esperado": _efectivo_esperado(s, t),
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
        # Propinas de tarjeta pagadas en efectivo del cajón: salieron de ahí, así
        # que el cajón tiene que tener menos.
        "propinas_pagadas": t.propinas_pagadas,
        # La plata que se movió a mano en el turno (retiros e ingresos), una por
        # una y sumada por tipo. Ya está aplicada al efectivo esperado de arriba.
        "retiros": _retiros_dict(s, t),
        "retiros_total": _retiros_del_turno(s, t),
        "ingresos_total": _ingresos_del_turno(s, t),
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


@router.post("/retiro")
def sacar_plata(datos: RetiroCajaIn, s: Session = Depends(get_session),
                quien: dict = Depends(sesion.exige("caja_retirar"))):
    """Saca plata del cajón EN MEDIO del turno, para ir a comprar cosas.

    No cierra la caja. Deja una fila firmada —quién, cuánto, cuándo, para qué— y
    el cuadre de la noche la resta sola del efectivo esperado, así que la plata
    que se fue a comprar pan no aparece como un faltante.

    NO se puede sacar más de lo que hay en el cajón. Sacar plata que no está es
    imposible de verdad —no es como el stock, donde la repisa puede tener más de
    lo que dice el papel—: acá el cajón tiene lo que tiene. Si se pidiera de más,
    el efectivo esperado quedaría negativo, que no significa nada.
    """
    t = turno_abierto(s)
    if not t:
        raise HTTPException(409, "La caja está cerrada. Ábrela antes de sacar plata.")
    hay = _efectivo_esperado(s, t)
    if datos.monto > hay:
        raise HTTPException(
            409,
            f"En el cajón hay {_clp(hay)}. No puedes sacar {_clp(datos.monto)}: "
            "no se puede sacar plata que no está.")
    r = RetiroCaja(
        turno_id=t.id, tipo="retiro",
        monto=datos.monto, motivo=datos.motivo,
        usuario_id=quien.get("id"), hecho_por=quien.get("nombre", ""),
    )
    s.add(r)
    s.commit()
    return _turno_dict(s, t)


@router.post("/ingreso")
def meter_plata(datos: RetiroCajaIn, s: Session = Depends(get_session),
                quien: dict = Depends(sesion.exige("caja_retirar"))):
    """Mete plata al cajón EN MEDIO del turno: un vuelto que se repone, cambio
    que se trae de otro lado. El cuadre lo suma al efectivo esperado, o esa plata
    aparecería en la noche como un sobrante que no existe.

    Un ingreso no tiene tope: siempre se puede agregar plata. Queda firmado
    igual que un retiro, y se corrige anulando.
    """
    t = turno_abierto(s)
    if not t:
        raise HTTPException(409, "La caja está cerrada. Ábrela antes de meter plata.")
    r = RetiroCaja(
        turno_id=t.id, tipo="ingreso",
        monto=datos.monto, motivo=datos.motivo,
        usuario_id=quien.get("id"), hecho_por=quien.get("nombre", ""),
    )
    s.add(r)
    s.commit()
    return _turno_dict(s, t)


@router.post("/retiro/{retiro_id}/anular")
def anular_retiro(retiro_id: int, s: Session = Depends(get_session),
                  quien: dict = Depends(sesion.exige("caja_retirar"))):
    """Deja sin efecto un retiro mal anotado.

    No lo borra: la fila se queda, marcada, con quién la anuló. El libro no
    esconde que hubo un movimiento; dice que ese no salió de verdad. Un retiro ya
    anulado no se vuelve a anular.
    """
    r = s.get(RetiroCaja, retiro_id)
    if not r:
        raise HTTPException(404, "No existe ese retiro")
    if r.anulado:
        raise HTTPException(409, "Ese retiro ya estaba anulado")
    r.anulado = True
    r.anulado_at = ahora()
    r.anulado_por = quien.get("nombre", "")
    s.add(r)
    s.commit()
    t = s.get(Turno, r.turno_id)
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

    # Las propinas de tarjeta que se pagaron al equipo EN EFECTIVO salieron del
    # cajón, y el banco todavía no las deposita. Sin restarlas, esa plata
    # aparece como un faltante que no existe — y es plata que se reparte casi
    # todas las noches.
    pagadas = min(datos.propinas_pagadas, _propinas(s, t)["tarjeta"])
    t.propinas_pagadas = pagadas

    # La misma fórmula que ve la pantalla y que imprime el papel: fondo + lo que
    # entró en efectivo − propinas pagadas − retiros del turno. Se calcula DESPUÉS
    # de guardar propinas_pagadas, porque el helper lo lee del turno.
    esperado = _efectivo_esperado(s, t)
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
    propinas = {m: int(v) for m, v in (datos.propinas_medios or {}).items()
                if m in MEDIOS_PAGO and m != "efectivo" and str(v).strip() != ""}
    t.propinas_medios = json.dumps(propinas) if propinas else ""
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
