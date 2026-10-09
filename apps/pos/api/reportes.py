"""Reportes: lo que el dueño mira para entender el local (Ventas → Reportes).

Tres cosas distintas viven acá, y conviene no confundirlas:

  1. El ACCESO. Reportes muestra lo que gana el local, así que pide el PIN de nuevo y
     solo deja pasar a quien tenga el permiso «ver_reportes». El PIN se verifica AQUÍ,
     en el servidor, con la misma verificación del candado (`sesion.pin_calza` y el
     mismo freno de intentos). La respuesta deja una galleta firmada y de corta vida:
     vale 5 minutos y se renueva con cada uso; sin uso, se acaba. Todos los demás
     endpoints exigen esa galleta Y el permiso (se vuelve a mirar en la base en cada
     petición, así que quitárselo a alguien tiene efecto al toque).
  2. Los CÁLCULOS. Se hacen con consultas agregadas de SQL: al navegador nunca llegan
     las ventas, llegan las cifras. El día es el del local (America/Santiago), no el UTC,
     y las ventas anuladas no cuentan en nada (se informan aparte).
  3. La COMPARACIÓN. Cada período se compara con el equivalente anterior. Si el período
     sigue en curso (hoy, los últimos 7 días, este mes), el anterior se corta a la
     MISMA hora: comparar «hoy hasta las 14:22» contra «el lunes pasado entero» le diría
     al dueño, todas las mañanas, que va perdiendo.

Todos los montos son enteros en pesos chilenos.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import case, func, literal_column
from sqlmodel import Session, select

from apps.pos import freno, sesion
from apps.pos.api import datos as api_datos
from apps.pos.api import turnos as api_turnos
from apps.pos.db.models import (Categoria, Insumo, Pago, Producto, Receta, Turno,
                                Usuario, Venta, VentaLinea)
from apps.pos.db.session import engine, get_session
from core.config import (MEDIOS_PAGO, NOMBRE_MEDIO, NOMBRE_ROL, ZONA, a_local, ahora,
                         costo_de, puede)

router = APIRouter(prefix="/api/v1/reportes", tags=["reportes"])

# ---------------------------------------------------------------------------
# El acceso: PIN y cinco minutos
# ---------------------------------------------------------------------------
GALLETA = "pos_reportes"
MINUTOS_DE_ACCESO = 5

PERMISO = "ver_reportes"


class EntrarIn(BaseModel):
    pin: str = ""
    # Opcional: con él se prueba el PIN de UNA persona; sin él, el de cualquiera de
    # los usuarios activos (en la pantalla se escribe solo el PIN).
    usuario_id: int | None = None


def _persona(u: Usuario | None) -> dict:
    if not u:
        return {"id": None, "nombre": "", "rol": "dueno", "rol_nombre": NOMBRE_ROL["dueno"],
                "color": ""}
    return {"id": u.id, "nombre": u.nombre, "rol": u.rol,
            "rol_nombre": NOMBRE_ROL.get(u.rol, u.rol), "color": u.color}


def _dar_acceso(respuesta: Response, usuario_id: int | None) -> None:
    # `k` distingue esta galleta de la de la sesión: son del mismo tipo y la misma
    # firma, y una no tiene que servir como la otra.
    respuesta.set_cookie(
        GALLETA,
        sesion._firmar({"k": "rep", "uid": usuario_id, "t": sesion.ahora().isoformat()}),
        max_age=MINUTOS_DE_ACCESO * 60, httponly=True, samesite="lax")


def _quien_tiene_acceso(request: Request, s: Session) -> tuple[bool, Usuario | None, str]:
    """(vale, usuario, motivo). No renueva nada: solo mira."""
    carga = sesion._abrir(request.cookies.get(GALLETA, ""))
    if not carga or carga.get("k") != "rep":
        return False, None, "Reportes pide el PIN."
    try:
        emitida = datetime.fromisoformat(carga["t"])
    except (KeyError, ValueError):
        return False, None, "Reportes pide el PIN."
    if emitida.tzinfo is None:
        emitida = emitida.replace(tzinfo=timezone.utc)
    if sesion.ahora() - emitida > timedelta(minutes=MINUTOS_DE_ACCESO):
        return False, None, "Reportes se cerró solo tras 5 minutos sin uso. Pide el PIN de nuevo."
    uid = carga.get("uid")
    if uid is None:
        # Caja sin usuarios (modo provisorio): no hay PIN que pedir. Si mientras tanto
        # se creó el primer usuario, esta entrada ya no vale.
        if sesion.hay_usuarios(s):
            return False, None, "Reportes pide el PIN."
        return True, None, ""
    u = s.get(Usuario, uid)
    if not u or not u.activo:
        return False, None, "Esa persona ya no entra a la caja."
    if not puede(u.rol, PERMISO, u.permisos or ""):
        raise HTTPException(403, f"{u.nombre} no tiene permiso para ver reportes.")
    return True, u, ""


def exige_reportes(request: Request, respuesta: Response,
                   s: Session = Depends(get_session),
                   quien: dict = Depends(sesion.exige_entrar)) -> dict:
    """La puerta de todos los endpoints de reportes: sesión, PIN reciente y permiso."""
    vale, u, motivo = _quien_tiene_acceso(request, s)
    if not vale:
        raise HTTPException(401, motivo)
    _dar_acceso(respuesta, u.id if u else None)     # se renueva con cada uso
    return _persona(u)


@router.post("/entrar")
def entrar(datos: EntrarIn, respuesta: Response, request: Request,
           s: Session = Depends(get_session),
           quien: dict = Depends(sesion.exige_entrar)):
    """Verifica el PIN y abre Reportes por unos minutos."""
    if not sesion.hay_usuarios(s):
        if not puede(quien.get("rol", ""), PERMISO, quien.get("permisos", "")):
            raise HTTPException(403, "Este equipo no puede ver reportes.")
        _dar_acceso(respuesta, None)
        return {"ok": True, "usuario": _persona(None), "minutos": MINUTOS_DE_ACCESO}

    # El mismo freno que el candado: diez mil PIN de 4 dígitos no se prueban, y esta
    # puerta no puede ser el camino fácil para adivinar el de otra persona.
    llave = f"reportes:{request.client.host if request.client else '?'}"
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
        raise HTTPException(403, f"{coinciden[0].nombre} no tiene permiso para ver reportes.")
    u = con_permiso[0]
    _dar_acceso(respuesta, u.id)
    return {"ok": True, "usuario": _persona(u), "minutos": MINUTOS_DE_ACCESO}


@router.post("/salir")
def salir(respuesta: Response):
    respuesta.delete_cookie(GALLETA)
    return {"ok": True}


@router.get("/estado")
def estado(request: Request, respuesta: Response, s: Session = Depends(get_session),
           quien: dict = Depends(sesion.quien_es)):
    """¿Sigue abierto Reportes? Es también el «latido»: mientras la pantalla se usa,
    la pantalla pregunta esto cada rato y así el acceso no se acaba a la mitad de
    una lectura. Nunca da error: dice que no."""
    if not quien.get("rol"):
        return {"activo": False}
    try:
        vale, u, motivo = _quien_tiene_acceso(request, s)
    except HTTPException:
        return {"activo": False}
    if not vale:
        return {"activo": False, "motivo": motivo}
    _dar_acceso(respuesta, u.id if u else None)
    return {"activo": True, "usuario": _persona(u), "minutos": MINUTOS_DE_ACCESO}


# ---------------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------------
PERIODOS = ("hoy", "ayer", "7d", "mes", "mesp", "rango")
MAX_DIAS_DE_RANGO = 400
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")


def _dia0(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _utc(naive_local: datetime) -> datetime:
    """Un instante de reloj de pared del local, llevado a UTC (lo que guarda la base)."""
    return naive_local.replace(tzinfo=ZONA).astimezone(timezone.utc)


def _mes_mas(d: date, n: int) -> date:
    """El día 1 del mes que está `n` meses después (o antes) del de `d`."""
    indice = d.year * 12 + (d.month - 1) + n
    return date(indice // 12, indice % 12 + 1, 1)


def _fecha(texto: str | None, que: str) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise HTTPException(422, f"La fecha «{que}» no es válida (AAAA-MM-DD).")


def calcular_periodo(clave: str, desde: str | None = None, hasta: str | None = None,
                     ahora_utc: datetime | None = None) -> dict:
    """El rango pedido y su equivalente anterior, en hora local del negocio.

    Todos los rangos son [ini, fin) en hora de pared. Cuando el período sigue en curso,
    `fin` es AHORA y el período anterior se corta a la misma hora.
    """
    if clave not in PERIODOS:
        raise HTTPException(422, "Ese período no existe.")
    ahora_l = a_local(ahora_utc or ahora()).replace(tzinfo=None, microsecond=0)
    hoy = ahora_l.date()
    semana = timedelta(days=7)
    en_curso = True

    if clave == "hoy":
        ini, fin = _dia0(hoy), ahora_l
        pini, pfin = ini - semana, fin - semana
        etiqueta = "Hoy"
        vs = f"el {DIAS[pini.weekday()]} pasado, a esta misma hora"
    elif clave == "ayer":
        ini, fin = _dia0(hoy - timedelta(days=1)), _dia0(hoy)
        pini, pfin = ini - semana, fin - semana
        etiqueta, en_curso = "Ayer", False
        vs = f"el {DIAS[pini.weekday()]} anterior"
    elif clave == "7d":
        ini, fin = _dia0(hoy - timedelta(days=6)), ahora_l
        pini, pfin = ini - semana, fin - semana
        etiqueta = "Últimos 7 días"
        vs = "los 7 días anteriores"
    elif clave == "mes":
        primero = hoy.replace(day=1)
        anterior = _mes_mas(primero, -1)
        ini, fin = _dia0(primero), ahora_l
        pini = _dia0(anterior)
        dias_del_anterior = (primero - anterior).days
        if hoy.day > dias_del_anterior:         # 31 de marzo contra febrero: todo febrero
            pfin = _dia0(primero)
        else:
            pfin = datetime.combine(anterior.replace(day=hoy.day), ahora_l.time())
        etiqueta = "Este mes"
        vs = f"el mismo tramo de {MESES[anterior.month - 1]}"
    elif clave == "mesp":
        primero = hoy.replace(day=1)
        anterior = _mes_mas(primero, -1)
        ini, fin = _dia0(anterior), _dia0(primero)
        pini, pfin = _dia0(_mes_mas(anterior, -1)), ini
        etiqueta, en_curso = "Mes pasado", False
        vs = MESES[pini.month - 1]
    else:
        d1 = _fecha(desde, "desde") or hoy - timedelta(days=13)
        d2 = _fecha(hasta, "hasta") or hoy
        if d1 > d2:
            d1, d2 = d2, d1
        d2 = min(d2, hoy)                       # el futuro no tiene ventas
        d1 = min(d1, d2)
        n = (d2 - d1).days + 1
        if n > MAX_DIAS_DE_RANGO:
            raise HTTPException(422, f"El rango no puede pasar de {MAX_DIAS_DE_RANGO} días.")
        ini = _dia0(d1)
        en_curso = d2 == hoy
        fin = ahora_l if en_curso else _dia0(d2 + timedelta(days=1))
        pini, pfin = ini - timedelta(days=n), fin - timedelta(days=n)
        etiqueta = "Rango"
        vs = "el día anterior" if n == 1 else f"los {n} días anteriores"

    ultimo = max(ini.date(), (fin - timedelta(seconds=1)).date())
    dias = [ini.date() + timedelta(days=i) for i in range((ultimo - ini.date()).days + 1)]
    return {
        "clave": clave, "etiqueta": etiqueta, "vs": vs, "en_curso": en_curso,
        "ini": ini, "fin": fin, "pini": pini, "pfin": pfin, "dias": dias,
        "ini_utc": _utc(ini), "fin_utc": _utc(fin),
        "pini_utc": _utc(pini), "pfin_utc": _utc(pfin),
    }


def _periodo_de_la_peticion(periodo: str, desde: str | None, hasta: str | None) -> dict:
    return calcular_periodo(periodo, desde, hasta)


def _meta(s: Session, p: dict) -> dict:
    primera = s.exec(select(func.min(Venta.creada_at))).one()
    # Solo se compara si hay ventas de TODO el tramo anterior; compararlo a medias
    # (el local abrió a mitad de semana) diría que el local creció cuando solo empezó.
    hay_previo = bool(primera is not None and primera <= p["pini_utc"].replace(tzinfo=None))
    return {
        "periodo": p["clave"], "etiqueta": p["etiqueta"],
        "desde": p["dias"][0].isoformat(), "hasta": p["dias"][-1].isoformat(),
        "dias": len(p["dias"]), "un_dia": len(p["dias"]) == 1,
        "en_curso": p["en_curso"],
        "corte": p["fin"].strftime("%H:%M") if p["en_curso"] else None,
        "vs": p["vs"], "hay_previo": hay_previo,
        "previo_desde": p["pini"].date().isoformat(),
        "previo_hasta": max(p["pini"].date(),
                            (p["pfin"] - timedelta(seconds=1)).date()).isoformat(),
    }


# ---------------------------------------------------------------------------
# Consultas agregadas
# ---------------------------------------------------------------------------
COBRADO = Venta.total - Venta.descuento


def _donde(ini_utc: datetime, fin_utc: datetime) -> list:
    """Ventas pagadas del rango. Las anuladas no cuentan nunca."""
    return [Venta.estado == "pagada", Venta.creada_at >= ini_utc, Venta.creada_at < fin_utc]


def _hora_utc():
    """La hora UTC de cada venta, como texto «AAAA-MM-DD HH». Chile tiene siempre un
    desfase en horas enteras, así que de ahí sale la hora local sin error."""
    # El formato va como texto literal y no como parámetro: SELECT y GROUP BY tienen
    # que ser LA MISMA expresión para que la base agrupe por ella.
    if engine.dialect.name == "postgresql":
        return func.to_char(Venta.creada_at, literal_column("'YYYY-MM-DD HH24'"))
    return func.strftime(literal_column("'%Y-%m-%d %H'"), Venta.creada_at)


def _local_de_cubeta(cubeta: str) -> datetime:
    return a_local(datetime.strptime(cubeta, "%Y-%m-%d %H").replace(tzinfo=timezone.utc))


def _cubetas(s: Session, ini_utc: datetime, fin_utc: datetime) -> list[dict]:
    """Ventas agrupadas por hora LOCAL: [{fecha, hora, n, total, propinas}]."""
    h = _hora_utc()
    filas = s.exec(
        select(h, func.count(Venta.id), func.coalesce(func.sum(COBRADO), 0),
               func.coalesce(func.sum(Venta.propina), 0))
        .where(*_donde(ini_utc, fin_utc)).group_by(h)
    ).all()
    salida = []
    for cubeta, n, total, propinas in filas:
        loc = _local_de_cubeta(cubeta)
        salida.append({"fecha": loc.date(), "hora": loc.hour, "n": int(n),
                       "total": int(total), "propinas": int(propinas)})
    return salida


def costos_por_producto(s: Session) -> dict[int, int | None]:
    """Cuánto cuesta cada producto, por unidad. None = no tiene costo cargado.

    Es la misma cuenta de la ficha de Inventario: si el producto es su propio insumo
    (se vende tal cual), el costo de comprar UNA unidad; si tiene una receta de verdad,
    la suma de sus ingredientes; si no, el costo de referencia que escribió el dueño.
    Un costo en cero es un costo que nadie cargó, y no se cuenta como «ganancia
    total»: ver `_ganancia`.
    """
    insumos = s.exec(select(Insumo)).all()
    por_id = {i.id: i for i in insumos}
    propios = {i.producto_id: i for i in insumos if i.producto_id}
    recetas: dict[int, list] = {}
    for r in s.exec(select(Receta)).all():
        recetas.setdefault(r.producto_id, []).append(r)
    salida: dict[int, int | None] = {}
    for p in s.exec(select(Producto)).all():
        i = propios.get(p.id)
        lineas = recetas.get(p.id, [])
        antigua = bool(lineas) and not (len(lineas) == 1 and lineas[0].cantidad == 1
                                        and i and i.unidad == "un"
                                        and lineas[0].insumo_id == i.id)
        if antigua:
            costo = sum(costo_de(r.cantidad, por_id[r.insumo_id].compra_costo,
                                 por_id[r.insumo_id].compra_contenido)
                        for r in lineas if r.insumo_id in por_id)
        elif i:
            costo = costo_de(1, i.compra_costo, i.compra_contenido)
        else:
            costo = p.costo_referencia
        salida[p.id] = int(costo) if costo and costo > 0 else None
    return salida


def _neto_de_linea():
    """Lo que realmente entró por una línea: el descuento de la venta se reparte entre
    sus líneas en proporción a lo que valen. Sin esto, las categorías y la ganancia
    sumarían más que lo vendido cada vez que hubo un descuento."""
    return VentaLinea.subtotal * 1.0 * (Venta.total - Venta.descuento) / func.nullif(Venta.total, 0)


def _ganancia(s: Session, ini_utc: datetime, fin_utc: datetime, total: int,
              costos: dict[int, int | None]) -> dict:
    """Ganancia estimada = lo vendido − lo que costó, SOLO de los productos con costo.

    Las líneas de balanza (se cobran por peso: «una unidad» no existe) y los cobros a
    mano no tienen costo por unidad, igual que los productos sin costo cargado: no
    entran en la cuenta y se informan como `venta_sin_costo`.
    """
    neto = _neto_de_linea()
    normal = VentaLinea.codigo_balanza == ""
    filas = s.exec(
        select(VentaLinea.producto_id,
               func.coalesce(func.sum(case((normal, VentaLinea.cantidad), else_=0)), 0),
               func.coalesce(func.sum(case((normal, neto), else_=0.0)), 0.0))
        .join(Venta, Venta.id == VentaLinea.venta_id)
        .where(*_donde(ini_utc, fin_utc), VentaLinea.producto_id != None)  # noqa: E711
        .group_by(VentaLinea.producto_id)
    ).all()
    con_costo = 0.0
    costo_total = 0
    for pid, cantidad, venta in filas:
        costo = costos.get(pid)
        if costo is None:
            continue
        con_costo += float(venta)
        costo_total += costo * int(cantidad)
    con_costo_r = round(con_costo)
    return {"ganancia": con_costo_r - costo_total, "venta_con_costo": con_costo_r,
            "venta_sin_costo": max(0, total - con_costo_r)}


def _medir(s: Session, ini_utc: datetime, fin_utc: datetime,
           costos: dict[int, int | None]) -> dict:
    cubetas = _cubetas(s, ini_utc, fin_utc)
    total = sum(c["total"] for c in cubetas)
    n = sum(c["n"] for c in cubetas)
    propinas = sum(c["propinas"] for c in cubetas)
    anuladas = s.exec(
        select(func.count(Venta.id), func.coalesce(func.sum(COBRADO), 0))
        .where(Venta.estado == "anulada", Venta.creada_at >= ini_utc, Venta.creada_at < fin_utc)
    ).one()
    g = _ganancia(s, ini_utc, fin_utc, total, costos)
    return {
        "total": total, "n": n, "ticket": round(total / n) if n else 0,
        "propinas": propinas,
        "anuladas": {"n": int(anuladas[0]), "total": int(anuladas[1])},
        "margen": round(g["ganancia"] / g["venta_con_costo"] * 100) if g["venta_con_costo"] else 0,
        **g, "_cubetas": cubetas,
    }


def _limpio(m: dict) -> dict:
    return {k: v for k, v in m.items() if not k.startswith("_")}


def _por_medio(s: Session, ini_utc: datetime, fin_utc: datetime) -> dict:
    """Cuánto se pagó con cada medio, repartiendo el pago mixto por partes (igual que el
    cuadre de la caja). Una venta mixta cuenta 1 en cada medio que tocó."""
    medios = {m: {"n": 0, "total": 0} for m in MEDIOS_PAGO}
    for medio, n, total in s.exec(
            select(Venta.medio_pago, func.count(Venta.id), func.sum(COBRADO))
            .where(*_donde(ini_utc, fin_utc), Venta.medio_pago != "mixto")
            .group_by(Venta.medio_pago)).all():
        if medio in medios:
            medios[medio]["n"] += int(n)
            medios[medio]["total"] += int(total or 0)
    for medio, n, total in s.exec(
            select(Pago.medio, func.count(func.distinct(Pago.venta_id)), func.sum(Pago.monto))
            .join(Venta, Venta.id == Pago.venta_id)
            .where(*_donde(ini_utc, fin_utc), Venta.medio_pago == "mixto")
            .group_by(Pago.medio)).all():
        if medio in medios:
            medios[medio]["n"] += int(n)
            medios[medio]["total"] += int(total or 0)
    n_mixtas = s.exec(select(func.count(Venta.id))
                      .where(*_donde(ini_utc, fin_utc), Venta.medio_pago == "mixto")).one()
    propina_efectivo = s.exec(
        select(func.coalesce(func.sum(Venta.propina), 0))
        .where(*_donde(ini_utc, fin_utc), Venta.medio_pago == "efectivo")).one()
    propina_total = s.exec(
        select(func.coalesce(func.sum(Venta.propina), 0)).where(*_donde(ini_utc, fin_utc))).one()
    n_con_propina = s.exec(
        select(func.count(Venta.id)).where(*_donde(ini_utc, fin_utc), Venta.propina > 0)).one()
    return {
        "medios": [{"medio": m, "nombre": NOMBRE_MEDIO[m], **medios[m]} for m in MEDIOS_PAGO],
        "n_mixtas": int(n_mixtas),
        "propinas": {"total": int(propina_total), "efectivo": int(propina_efectivo),
                     "tarjeta": int(propina_total) - int(propina_efectivo),
                     "n": int(n_con_propina)},
    }


def _por_categoria(s: Session, ini_utc: datetime, fin_utc: datetime) -> list[dict]:
    filas = s.exec(
        select(Categoria.id, Categoria.nombre, func.coalesce(func.sum(_neto_de_linea()), 0.0))
        .select_from(VentaLinea)
        .join(Venta, Venta.id == VentaLinea.venta_id)
        .outerjoin(Producto, Producto.id == VentaLinea.producto_id)
        .outerjoin(Categoria, Categoria.id == Producto.categoria_id)
        .where(*_donde(ini_utc, fin_utc))
        .group_by(Categoria.id)
    ).all()
    salida = [{"id": cid, "nombre": nombre or "Sin categoría", "total": round(total)}
              for cid, nombre, total in filas]
    return sorted((f for f in salida if f["total"]), key=lambda f: -f["total"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
def _serie_por_dia(p: dict, cubetas: list[dict]) -> list[dict]:
    por_dia = {d: {"fecha": d.isoformat(), "total": 0, "n": 0} for d in p["dias"]}
    for c in cubetas:
        if c["fecha"] in por_dia:
            por_dia[c["fecha"]]["total"] += c["total"]
            por_dia[c["fecha"]]["n"] += c["n"]
    return [dict(f, fin_de_semana=date.fromisoformat(f["fecha"]).weekday() >= 5)
            for f in por_dia.values()]


def _rango_de_horas(cubetas: list[dict]) -> tuple[int, int]:
    """El tramo del día que se dibuja: de 8 a 20 como mínimo, más lo que haya vendido
    fuera de ese horario (una cafetería que abre a las 7 no puede perder esa hora)."""
    horas = [c["hora"] for c in cubetas if c["total"]]
    return min([8] + horas), max([20] + horas)


@router.get("/resumen")
def resumen(periodo: str = Query(default="7d"), desde: str | None = Query(default=None),
            hasta: str | None = Query(default=None), s: Session = Depends(get_session),
            quien: dict = Depends(exige_reportes)):
    """Los indicadores del período, su comparación y lo que se dibuja arriba."""
    p = _periodo_de_la_peticion(periodo, desde, hasta)
    costos = costos_por_producto(s)
    actual = _medir(s, p["ini_utc"], p["fin_utc"], costos)
    meta = _meta(s, p)
    previo = _medir(s, p["pini_utc"], p["pfin_utc"], costos) if meta["hay_previo"] else None
    cubetas = actual["_cubetas"]
    h0, h1 = _rango_de_horas(cubetas)
    por_hora = []
    if meta["un_dia"]:
        for h in range(h0, h1 + 1):
            fila = [c for c in cubetas if c["hora"] == h]
            por_hora.append({"hora": h, "total": sum(c["total"] for c in fila),
                             "n": sum(c["n"] for c in fila)})
    medios = _por_medio(s, p["ini_utc"], p["fin_utc"])
    productos_sin_costo = sum(1 for pr in s.exec(select(Producto).where(Producto.activo == True)  # noqa: E712
                                                 ).all() if costos.get(pr.id) is None)
    return {
        **meta,
        "actual": _limpio(actual),
        "previo": _limpio(previo) if previo else None,
        "productos_sin_costo": productos_sin_costo,
        "por_dia": _serie_por_dia(p, cubetas),
        "por_hora": por_hora,
        "por_medio": medios["medios"], "n_mixtas": medios["n_mixtas"],
        "propinas": medios["propinas"],
        "por_categoria": _por_categoria(s, p["ini_utc"], p["fin_utc"]),
    }


@router.get("/calor")
def calor(periodo: str = Query(default="7d"), desde: str | None = Query(default=None),
          hasta: str | None = Query(default=None), s: Session = Depends(get_session),
          quien: dict = Depends(exige_reportes)):
    """Mapa de calor: cuánto se vende, en promedio, cada día de la semana a cada hora.

    Es un PROMEDIO por día (no un total): un mes tiene cinco sábados y cuatro lunes, y
    sumar sin dividir haría que el sábado «ganara» solo por tener más días.
    Con menos de 14 días no hay patrón que ver: se usan las últimas 4 semanas.
    """
    p = _periodo_de_la_peticion(periodo, desde, hasta)
    ultimas_4 = len(p["dias"]) < 14
    if ultimas_4:
        ahora_l = a_local(ahora()).replace(tzinfo=None, microsecond=0)
        ini = _dia0(ahora_l.date() - timedelta(days=27))
        fin = ahora_l
        dias = [ini.date() + timedelta(days=i) for i in range((fin.date() - ini.date()).days + 1)]
        ini_utc, fin_utc = _utc(ini), _utc(fin)
    else:
        dias, ini_utc, fin_utc = p["dias"], p["ini_utc"], p["fin_utc"]
    cubetas = _cubetas(s, ini_utc, fin_utc)
    ocurrencias = [0] * 7
    for d in dias:
        ocurrencias[d.weekday()] += 1
    suma = [[0] * 24 for _ in range(7)]
    for c in cubetas:
        suma[c["fecha"].weekday()][c["hora"]] += c["total"]
    celdas = [[round(suma[d][h] / ocurrencias[d]) if ocurrencias[d] else 0 for h in range(24)]
              for d in range(7)]
    n_dias = max(1, sum(ocurrencias))
    todos = [round(sum(suma[d][h] for d in range(7)) / n_dias) for h in range(24)]
    h0, h1 = _rango_de_horas(cubetas)
    return {"ultimas_4_semanas": ultimas_4, "dias": len(dias), "hora_ini": h0, "hora_fin": h1,
            "celdas": celdas, "todos": todos, "ocurrencias": ocurrencias}


@router.get("/productos")
def productos(periodo: str = Query(default="7d"), desde: str | None = Query(default=None),
              hasta: str | None = Query(default=None), s: Session = Depends(get_session),
              quien: dict = Depends(exige_reportes)):
    """Qué se vendió (por cantidad y por plata) y qué NO se vendió en el período."""
    p = _periodo_de_la_peticion(periodo, desde, hasta)
    neto = _neto_de_linea()
    donde = _donde(p["ini_utc"], p["fin_utc"])
    categorias = {c.id: c.nombre for c in s.exec(select(Categoria)).all()}
    catalogo = {pr.id: pr for pr in s.exec(select(Producto)).all()}

    vendidos = []
    for pid, cantidad, total in s.exec(
            select(VentaLinea.producto_id, func.sum(VentaLinea.cantidad),
                   func.coalesce(func.sum(neto), 0.0))
            .join(Venta, Venta.id == VentaLinea.venta_id)
            .where(*donde, VentaLinea.producto_id != None)  # noqa: E711
            .group_by(VentaLinea.producto_id)).all():
        pr = catalogo.get(pid)
        vendidos.append({
            "id": pid, "nombre": pr.nombre if pr else "(producto borrado)",
            "categoria_id": pr.categoria_id if pr else None,
            "categoria": categorias.get(pr.categoria_id, "") if pr else "",
            "dibujo": pr.dibujo if pr else "", "color": pr.color if pr else "",
            "cantidad": int(cantidad), "total": round(total)})
    # Los cobros a mano no tienen producto: se juntan por el nombre que escribió el cajero.
    for nombre, cantidad, total in s.exec(
            select(VentaLinea.nombre, func.sum(VentaLinea.cantidad),
                   func.coalesce(func.sum(neto), 0.0))
            .join(Venta, Venta.id == VentaLinea.venta_id)
            .where(*donde, VentaLinea.producto_id == None)  # noqa: E711
            .group_by(VentaLinea.nombre)).all():
        vendidos.append({"id": None, "nombre": nombre, "categoria_id": None,
                         "categoria": "Cobros a mano", "dibujo": "", "color": "",
                         "cantidad": int(cantidad), "total": round(total)})

    ids_vendidos = {v["id"] for v in vendidos if v["id"]}
    ultima = {pid: fecha for pid, fecha in s.exec(
        select(VentaLinea.producto_id, func.max(Venta.creada_at))
        .join(Venta, Venta.id == VentaLinea.venta_id)
        .where(Venta.estado == "pagada", VentaLinea.producto_id != None)  # noqa: E711
        .group_by(VentaLinea.producto_id)).all()}
    sin_ventas = []
    for pr in catalogo.values():
        if not pr.activo or pr.id in ids_vendidos:
            continue
        u = ultima.get(pr.id)
        sin_ventas.append({
            "id": pr.id, "nombre": pr.nombre, "categoria_id": pr.categoria_id,
            "categoria": categorias.get(pr.categoria_id, ""), "dibujo": pr.dibujo,
            "color": pr.color,
            "ultima_venta": a_local(u).date().isoformat() if u else None})
    return {"vendidos": sorted(vendidos, key=lambda v: (-v["cantidad"], v["nombre"])),
            "sin_ventas": sin_ventas}


@router.get("/cajeros")
def cajeros(periodo: str = Query(default="7d"), desde: str | None = Query(default=None),
            hasta: str | None = Query(default=None), s: Session = Depends(get_session),
            quien: dict = Depends(exige_reportes)):
    """Cuánto vendió cada persona y cómo le salieron los arqueos del efectivo."""
    p = _periodo_de_la_peticion(periodo, desde, hasta)
    usuarios = {u.id: u for u in s.exec(select(Usuario)).all()}
    filas: dict[object, dict] = {}

    def fila(clave, nombre, color=""):
        return filas.setdefault(clave, {
            "usuario_id": clave if isinstance(clave, int) else None,
            "nombre": nombre, "color": color, "total": 0, "n": 0, "turnos": 0,
            "cerrados": 0, "con_diferencia": 0, "diferencia_total": 0, "diferencias": []})

    def de_usuario(uid):
        u = usuarios.get(uid)
        return fila(uid, u.nombre if u else "(borrado)", u.color if u else "")

    for uid, n, total in s.exec(
            select(Venta.usuario_id, func.count(Venta.id), func.coalesce(func.sum(COBRADO), 0))
            .where(*_donde(p["ini_utc"], p["fin_utc"])).group_by(Venta.usuario_id)).all():
        f = de_usuario(uid) if uid else fila("sin", "Sin nombre")
        f["total"] += int(total)
        f["n"] += int(n)

    turnos = s.exec(select(Turno).where(Turno.abierto_at >= p["ini_utc"],
                                        Turno.abierto_at < p["fin_utc"])
                    .order_by(Turno.abierto_at.desc())).all()
    for t in turnos:
        f = de_usuario(t.abierto_por_id) if t.abierto_por_id else fila(
            "n:" + (t.cajero or ""), t.cajero or "Sin nombre")
        f["turnos"] += 1
        if t.cerrado_at is not None and t.diferencia is not None:
            f["cerrados"] += 1
            f["diferencia_total"] += t.diferencia
            f["con_diferencia"] += 1 if t.diferencia else 0
            f["diferencias"].append({"turno_id": t.id, "diferencia": t.diferencia,
                                     "fecha": a_local(t.abierto_at).date().isoformat()})
    return sorted(filas.values(), key=lambda f: (-f["total"], f["nombre"]))


@router.get("/turnos")
def historial(periodo: str = Query(default="7d"), desde: str | None = Query(default=None),
              hasta: str | None = Query(default=None), s: Session = Depends(get_session),
              quien: dict = Depends(exige_reportes)):
    """Los turnos que se abrieron en el período, con lo vendido y cómo cuadró el efectivo."""
    p = _periodo_de_la_peticion(periodo, desde, hasta)
    turnos = s.exec(select(Turno).where(Turno.abierto_at >= p["ini_utc"],
                                        Turno.abierto_at < p["fin_utc"])
                    .order_by(Turno.abierto_at.desc())).all()
    vendido: dict[int, tuple[int, int]] = {}
    for trozo in api_turnos._en_trozos([t.id for t in turnos]):
        for tid, n, total in s.exec(
                select(Venta.turno_id, func.count(Venta.id),
                       func.coalesce(func.sum(COBRADO), 0))
                .where(Venta.estado == "pagada", Venta.turno_id.in_(trozo))
                .group_by(Venta.turno_id)).all():
            vendido[tid] = (int(n), int(total))
    usuarios = {u.id: u for u in s.exec(select(Usuario)).all()}
    salida = []
    for t in turnos:
        u = usuarios.get(t.abierto_por_id)
        fin = t.cerrado_at
        n, total = vendido.get(t.id, (0, 0))
        salida.append({
            "id": t.id,
            "abrio": u.nombre if u else (t.cajero or "—"),
            "color": u.color if u else "",
            "abierto_at": a_local(t.abierto_at).isoformat(),
            "cerrado_at": a_local(fin).isoformat() if fin else None,
            "abierto": fin is None,
            "vendido": total, "n": n,
            "contado": t.efectivo_contado, "diferencia": t.diferencia,
        })
    return salida


@router.get("/turnos/{turno_id}")
def corte(turno_id: int, s: Session = Depends(get_session),
          quien: dict = Depends(exige_reportes)):
    """El corte completo de un turno: el mismo resumen de «Mi turno», para leer."""
    t = s.get(Turno, turno_id)
    if not t:
        raise HTTPException(404, "No existe ese turno")
    return api_turnos.corte_del_turno(s, t)


@router.get("/exportar")
def exportar(tipo: str = Query(default="ventas"), periodo: str = Query(default="7d"),
             desde: str | None = Query(default=None), hasta: str | None = Query(default=None),
             s: Session = Depends(get_session), quien: dict = Depends(exige_reportes)):
    """El CSV para el contador de los días del período. Es el mismo archivo de
    siempre (`/exportar/ventas` y `/exportar/detalle`), con el período elegido y la
    puerta de Reportes en vez del permiso de informes."""
    if tipo not in ("ventas", "detalle"):
        raise HTTPException(422, "Ese archivo no existe.")
    p = _periodo_de_la_peticion(periodo, desde, hasta)
    d1, d2 = p["dias"][0].isoformat(), p["dias"][-1].isoformat()
    if tipo == "detalle":
        return api_datos.exportar_detalle(d1, d2, s)
    return api_datos.exportar_ventas(d1, d2, s)
