"""Ventas: registrar, listar, anular y el resumen del día."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.api import ajustes, inventario
from apps.pos.balanza import resolver
from apps.pos.db.models import Producto, Turno, Usuario, Venta, VentaLinea
from apps.pos.db.session import get_session
from core.config import (MEDIOS_PAGO, a_local, ahora, hoy_local, neto_iva, puede,
                         rango_utc_del_dia)
from core.schemas import AnularIn, VentaIn

router = APIRouter(prefix="/api/v1", tags=["ventas"])


def _lo_que_no_alcanza(s: Session, lineas: list) -> str:
    """Mira si el stock alcanza para todo el pedido. Devuelve el mensaje del
    primer producto que no alcance, o "" si todo alcanza.

    Solo mira los productos que son su propio insumo (tal cual): a ésos el
    `stock` es "cuántos quedan" y se puede comparar. Los de receta de verdad no
    tienen un número así y no se topean. Suma las cantidades del mismo producto,
    por si vinieran en dos líneas.
    """
    from apps.pos.db.models import Insumo

    pedido: dict[int, int] = {}
    for l in lineas:
        if l.producto_id and not l.codigo_balanza:
            pedido[l.producto_id] = pedido.get(l.producto_id, 0) + l.cantidad

    for producto_id, cantidad in pedido.items():
        producto = s.get(Producto, producto_id)
        if producto and producto.llevar_cuenta is False:
            continue
        insumo = s.exec(
            select(Insumo).where(
                Insumo.producto_id == producto_id,
                Insumo.activo == True,          # noqa: E712
            )
        ).first()
        if not insumo:
            continue                             # no lleva cuenta como tal cual: no se topea
        if not insumo.contado:
            continue                             # todavía nadie dijo cuántos hay: no se topea
        if cantidad > insumo.stock:
            p = s.get(Producto, producto_id)
            nombre = p.nombre if p else "ese producto"
            quedan = insumo.stock
            if quedan <= 0:
                return (f"«{nombre}» está en cero. Anota la mercadería que llegó en "
                        "Bodega y vuelve a cobrar.")
            return (f"De «{nombre}» quedan {quedan}. Estás vendiendo {cantidad}. "
                    "Si llegó más, actualiza la cantidad en Bodega.")
    return ""


def _plata(n: int) -> str:
    return "$" + f"{n:,}".replace(",", ".")


def _turno_abierto(s: Session) -> Turno | None:
    return s.exec(select(Turno).where(Turno.cerrado_at == None)).first()  # noqa: E711


def _siguiente_numero(s: Session) -> int:
    ultimo = s.exec(select(Venta).order_by(Venta.numero.desc())).first()
    return (ultimo.numero + 1) if ultimo else 1


def _nombre(s: Session | None, usuario_id: int | None) -> str:
    """El nombre de quien hizo algo. Vacío en lo anterior al login: a esas
    ventas no se les inventa un autor."""
    if not s or not usuario_id:
        return ""
    u = s.get(Usuario, usuario_id)
    return u.nombre if u else ""


def _venta_dict(v: Venta, con_lineas: bool = False, s: Session | None = None) -> dict:
    d = {
        "id": v.id,
        "numero": v.numero,
        "creada_at": a_local(v.creada_at).isoformat(),
        "estado": v.estado,
        "total": v.total,
        "descuento": v.descuento,
        "cobrado": v.total - v.descuento,
        "propina": v.propina,
        "medio_pago": v.medio_pago,
        "nota": v.nota,
        "turno_id": v.turno_id,
        "usuario_id": v.usuario_id,
        "quien": _nombre(s, v.usuario_id),
    }
    # Si fue pago mixto, el detalle de cada parte, para que El día lo muestre.
    if s is not None and v.medio_pago == "mixto":
        from apps.pos.db.models import Pago
        d["pagos"] = [
            {"medio": p.medio, "monto": p.monto}
            for p in s.exec(select(Pago).where(Pago.venta_id == v.id)).all()
        ]
    if con_lineas:
        d["lineas"] = [
            {"nombre": l.nombre, "precio_unitario": l.precio_unitario,
             "cantidad": l.cantidad, "subtotal": l.subtotal, "detalle": l.detalle}
            for l in v.lineas
        ]
        if v.estado == "anulada":
            d["anulada_motivo"] = v.anulada_motivo
    return d


@router.post("/ventas")
def registrar_venta(datos: VentaIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("vender"))):
    """Registra una venta YA COBRADA. El carrito vive en el navegador del cajero;
    acá llega recién cuando se cobró (ver CONTRATO, sección 2)."""
    if any(item.codigo_balanza is not None for item in datos.lineas):
        # Dos cajas pueden cobrar el mismo papel al mismo tiempo. Reservar la
        # escritura ANTES de consultar evita que ambas lo vean como libre.
        # La reserva dura hasta commit (o rollback si se rechaza la venta).
        from apps.pos.db.session import reservar_escritura
        reservar_escritura(s)
    lineas: list[VentaLinea] = []
    tickets: set[str] = set()
    total = 0
    for item in datos.lineas:
        if item.codigo_balanza is not None:
            cobro = resolver(s, item.codigo_balanza)
            if cobro is None:
                if not ajustes._leer(s)["usar_balanza"]:
                    raise HTTPException(409, "La balanza de este local está apagada, así que "
                                             "esa etiqueta no se puede cobrar. Quítala del pedido "
                                             "(o prende la balanza en Ayuda → Ajustes).")
                raise HTTPException(409, "Esa etiqueta ya no calza con el formato guardado de la "
                                         "balanza. Quítala del pedido y vuelve a escanearla.")
            if cobro.modo == "ticket" and item.cantidad != 1:
                raise HTTPException(422, "Un ticket de balanza se cobra de a uno: la cantidad debe ser 1.")
            if cobro.problema:
                raise HTTPException(409, cobro.problema)
            if item.precio_visto is not None and item.precio_visto != cobro.precio:
                raise HTTPException(
                    409, f"La etiqueta de {cobro.nombre} ({cobro.detalle}) ahora vale "
                         f"{_plata(cobro.precio)} y en la pantalla decía "
                         f"{_plata(item.precio_visto)}. Quítala del pedido y vuelve a escanearla.")
            if cobro.modo == "ticket":
                if cobro.codigo in tickets:
                    raise HTTPException(409, f"El {cobro.detalle.lower()} de la balanza está "
                                             "dos veces en esta venta. Deja una sola línea.")
                tickets.add(cobro.codigo)
            subtotal = cobro.precio * item.cantidad
            total += subtotal
            lineas.append(VentaLinea(
                producto_id=cobro.producto_id, nombre=cobro.nombre, detalle=cobro.detalle,
                precio_unitario=cobro.precio, cantidad=item.cantidad, subtotal=subtotal,
                codigo_balanza=cobro.codigo, peso_g=cobro.peso_g, modo_balanza=cobro.modo,
            ))
            continue
        if item.producto_id is None:
            # Cobro a mano. Es la única línea cuyo precio no sale del catálogo, así que es
            # también la única por la que alguien podría cobrar de más sin que se note. No
            # se prohíbe —en un mostrador siempre aparece algo que no está en la carta—:
            # se pide permiso y queda firmada, igual que sacar plata del cajón.
            if not puede(quien.get("rol", ""), "cobrar_varios", quien.get("permisos", "")):
                raise HTTPException(
                    403, f"{quien.get('nombre') or 'Este usuario'} no puede cobrar montos "
                         "a mano. Se lo puede dar el dueño en Equipo.")
            precio = item.precio or 0
            subtotal = precio * item.cantidad
            total += subtotal
            lineas.append(VentaLinea(
                producto_id=None, nombre=(item.nombre.strip() or "Varios"),
                precio_unitario=precio, cantidad=item.cantidad, subtotal=subtotal,
            ))
            continue
        p = s.get(Producto, item.producto_id)
        if not p:
            raise HTTPException(404, f"No existe el producto {item.producto_id}")
        if p.precio == 0 and p.precio_kilo > 0:
            # Tocar su azulejo lo cobraba a $0: su precio es por kilo y sale de la
            # etiqueta. Si el dueño le pone también un precio por unidad, sí se vende así.
            raise HTTPException(409, f"«{p.nombre}» se vende por peso: escanea la etiqueta "
                                     "de la balanza.")
        subtotal = p.precio * item.cantidad
        total += subtotal
        # nombre y precio COPIADOS: la venta de ayer no cambia si mañana sube el café
        lineas.append(VentaLinea(
            producto_id=p.id, nombre=p.nombre, precio_unitario=p.precio,
            cantidad=item.cantidad, subtotal=subtotal,
        ))

    # Un descuento mayor que la venta dejaría un cobro negativo: se recorta.
    descuento = min(datos.descuento, total)

    # SIN CAJA ABIERTA NO SE VENDE.
    #
    # Antes se aceptaba y la venta quedaba con `turno_id` en nulo: no entraba en
    # ningún cuadre, no aparecía en ningún cierre, y nadie se enteraba hasta que
    # el efectivo del cajón no calzaba con nada. Una venta que no pertenece a
    # ningún turno es plata sin dueño.
    #
    # Se rechaza en el SERVIDOR y no solo en la pantalla, porque la pantalla se
    # puede recargar, abrir en otro aparato, o quedar con una copia vieja.
    turno = _turno_abierto(s)
    if not turno:
        raise HTTPException(409, "La caja está cerrada. Ábrela antes de vender, "
                                 "contando el fondo con el que parte el cajón.")

    # TOPE DURO: no se vende lo que no hay.
    #
    # Solo topea lo que se vende TAL CUAL —el producto que ES su propio insumo—,
    # que es donde el saldo es un número comparable. Un capuchino se hace con
    # leche y café y puede quedar en negativo a propósito (ver CONTRATO): a ése
    # no se le pone tope, se le descuenta.
    #
    # Va en el SERVIDOR y no solo en la pantalla porque hay tablets y dos
    # pestañas abriendo la misma caja: las dos ven "queda 1", las dos lo agregan,
    # y lo único que puede impedir vender dos veces el mismo es esto. La pantalla
    # topea antes para que no se llegue a intentar; el servidor es el que cumple.
    #
    # Se chequea ANTES de escribir un solo Movimiento: una venta rechazada a la
    # mitad dejaría el libro con unos insumos descontados y otros no.
    usar_inventario = ajustes._leer(s)["usar_inventario"] == 1
    faltan = _lo_que_no_alcanza(s, lineas) if usar_inventario else ""
    if faltan:
        raise HTTPException(409, faltan)

    # PAGO MIXTO: parte en efectivo, parte en otra forma.
    #
    # Si vienen `pagos`, la suma tiene que dar EXACTO lo cobrado (total menos
    # descuento): no se puede cobrar de más ni de menos repartiendo. La venta
    # queda con medio_pago "mixto" y sin propina —repartir una propina por medio
    # es una combinación rara que no vale la pena—, y cada parte se guarda como
    # una fila de Pago. Una venta de un solo medio no pasa por acá y no escribe
    # ninguna fila de Pago: sigue igual que siempre.
    medio_pago = datos.medio_pago
    propina = datos.propina
    if datos.pagos:
        suma = sum(p.monto for p in datos.pagos)
        if suma != total - descuento:
            raise HTTPException(
                422, f"Las partes suman {suma} y el total a cobrar es {total - descuento}. "
                     "Tienen que dar lo mismo.")
        medio_pago = "mixto"
        propina = 0

    venta = Venta(
        numero=_siguiente_numero(s),
        turno_id=turno.id,
        total=total,
        descuento=descuento,
        propina=propina,
        medio_pago=medio_pago,
        nota=datos.nota,
        usuario_id=quien.get("id"),
    )
    venta.lineas = lineas
    s.add(venta)
    # flush y no commit: la venta necesita id para que los movimientos de stock
    # la puedan apuntar, pero las dos cosas tienen que entrar juntas. O queda
    # registrada la venta con su descuento de inventario, o no queda nada.
    s.flush()
    if datos.pagos:
        from apps.pos.db.models import Pago
        for p in datos.pagos:
            s.add(Pago(venta_id=venta.id, medio=p.medio, monto=p.monto))
    avisos = inventario.descontar_venta(s, venta, quien) if usar_inventario else []
    s.commit()
    s.refresh(venta)

    cobrado = total - descuento + datos.propina
    vuelto = None
    if datos.medio_pago == "efectivo" and datos.paga_con is not None:
        vuelto = datos.paga_con - cobrado
        if vuelto < 0:
            # No bloqueamos la venta (ya se cobró), pero lo decimos.
            vuelto = None

    salida = _venta_dict(venta, con_lineas=True, s=s)
    salida["cobrado"] = cobrado
    salida["vuelto"] = vuelto
    # Avisa, no bloquea: la venta ya se cobró.
    salida["inventario"] = avisos
    return salida


@router.get("/ventas")
def listar_ventas(
    fecha: str | None = Query(default=None, description="AAAA-MM-DD, día local"),
    turno_id: int | None = Query(default=None,
                                 description="un turno; si viene, manda sobre la fecha"),
    s: Session = Depends(get_session),
):
    """Las ventas de un día, o las de un turno.

    Por turno hace falta porque un día puede tener dos, y la lista de "las
    ventas de hoy" al lado de las cifras de UN turno no calza: se ven ventas de
    la mañana bajo el total de la tarde.
    """
    if turno_id is not None:
        t = s.get(Turno, turno_id)
        if not t:
            raise HTTPException(404, "No existe ese turno")
        ventas = s.exec(
            select(Venta).where(Venta.turno_id == turno_id).order_by(Venta.numero.desc())
        ).all()
        return {"fecha": a_local(t.abierto_at).date().isoformat(),
                "turno_id": turno_id,
                "ventas": [_venta_dict(v, s=s) for v in ventas]}

    dia = date.fromisoformat(fecha) if fecha else hoy_local()
    desde, hasta = rango_utc_del_dia(dia)
    ventas = s.exec(
        select(Venta)
        .where(Venta.creada_at >= desde, Venta.creada_at < hasta)
        .order_by(Venta.numero.desc())
    ).all()
    return {"fecha": dia.isoformat(), "turno_id": None,
            "ventas": [_venta_dict(v, s=s) for v in ventas]}


@router.get("/ventas/{venta_id}")
def ver_venta(venta_id: int, s: Session = Depends(get_session)):
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    return _venta_dict(v, con_lineas=True, s=s)


@router.post("/ventas/{venta_id}/anular")
def anular_venta(venta_id: int, datos: AnularIn, s: Session = Depends(get_session),
                 quien: dict = Depends(sesion.exige("anular"))):
    """Anular deja rastro. Editar montos del pasado, no: rompe el cuadre."""
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    if v.estado == "anulada":
        raise HTTPException(409, "Esa venta ya estaba anulada")

    # Anular una venta de un turno YA CERRADO cambia un cuadre que alguien ya
    # firmó e imprimió. Eso lo hace el dueño, no el cajero.
    de_turno_cerrado = False
    if v.turno_id:
        t = s.get(Turno, v.turno_id)
        de_turno_cerrado = bool(t and t.cerrado_at)
    if de_turno_cerrado and not puede(quien.get("rol", ""), "anular_pasado", quien.get("permisos", "")):
        raise HTTPException(
            403, "Esa venta es de una caja que ya se cerró. Solo el dueño puede anularla.")

    v.estado = "anulada"
    v.anulada_at = ahora()
    v.anulada_motivo = datos.motivo
    v.anulada_por_id = quien.get("id")
    s.add(v)
    # Lo que la venta descontó del inventario vuelve, leído del libro.
    inventario.devolver_venta(s, v, quien)
    s.commit()
    s.refresh(v)
    return _venta_dict(v, con_lineas=True, s=s)


def _cobros_a_mano(s: Session, ventas) -> dict:
    """Cuántas líneas se cobraron a mano y por cuánto, con quién las hizo.

    Una línea sin `producto_id` ni etiqueta es un cobro a mano: su precio lo
    escribió alguien en el mostrador. Los tickets también carecen de producto,
    pero su monto viene impreso por la balanza y se informa por separado.
    """
    from apps.pos.db.models import VentaLinea

    ids = [v.id for v in ventas if v.estado == "pagada"]
    if not ids:
        return {"cantidad": 0, "total": 0, "por_persona": []}
    lineas = s.exec(select(VentaLinea).where(
        VentaLinea.venta_id.in_(ids), VentaLinea.producto_id == None,  # noqa: E711
        VentaLinea.codigo_balanza == "")).all()
    if not lineas:
        return {"cantidad": 0, "total": 0, "por_persona": []}
    de_venta = {v.id: v for v in ventas}
    por_persona: dict[str, dict] = {}
    for l in lineas:
        v = de_venta.get(l.venta_id)
        quien = _nombre(s, v.usuario_id) if v else ""
        d = por_persona.setdefault(quien or "—", {"nombre": quien or "—",
                                                  "cantidad": 0, "total": 0})
        d["cantidad"] += 1
        d["total"] += l.subtotal
    return {
        "cantidad": len(lineas),
        "total": sum(l.subtotal for l in lineas),
        "por_persona": sorted(por_persona.values(), key=lambda d: -d["total"]),
    }


@router.get("/resumen",
            dependencies=[Depends(sesion.exige("ver_dia"))])
def resumen(
    fecha: str | None = Query(default=None, description="un día suelto"),
    desde: str | None = Query(default=None, description="AAAA-MM-DD"),
    hasta: str | None = Query(default=None, description="AAAA-MM-DD, incluido"),
    turno_id: int | None = Query(default=None,
                                 description="un turno; si viene, manda sobre las fechas"),
    s: Session = Depends(get_session),
):
    """Totales de un día, de un rango de días, o de UN TURNO.

    Mirar por turno lo pidió el local, y tenían toda la razón: la caja recién
    abierta, sin una sola venta, y El día —que había quedado en "Mes"— igual
    mostraba plata vendida, ticket promedio y efectivo. Los números eran del mes
    y estaban bien, pero al lado de un cajón vacío se leen como si fueran de
    ahora, y el que está en la caja no sabe cuál creer. Con `turno_id` las cifras
    son las de ESE turno y de nada más, que es justo la pregunta que se hace el
    que está atendiendo: cómo va MI turno.

    Las anuladas se cuentan aparte, nunca se suman.
    """
    from apps.pos.api.turnos import (_efectivo_del_turno, _efectivo_esperado,
                                     _nombre, _pagos_de)
    from apps.pos.db.models import RetiroCaja

    turno = None
    if turno_id is not None:
        turno = s.get(Turno, turno_id)
        if not turno:
            raise HTTPException(404, "No existe ese turno")
        d1 = d2 = a_local(turno.abierto_at).date()
        ventas = s.exec(select(Venta).where(Venta.turno_id == turno.id)).all()
        # Los movimientos del turno son los del TURNO, no los del día: si hubo
        # dos turnos, el retiro de la mañana no es del que está abierto ahora, y
        # sumárselo le inventa un faltante al que llegó en la tarde.
        movs = s.exec(
            select(RetiroCaja).where(
                RetiroCaja.turno_id == turno.id,
                RetiroCaja.anulado == False,          # noqa: E712
            ).order_by(RetiroCaja.creado_at.desc())
        ).all()
    else:
        if desde:
            d1 = date.fromisoformat(desde)
            d2 = date.fromisoformat(hasta) if hasta else d1
        else:
            d1 = d2 = date.fromisoformat(fecha) if fecha else hoy_local()
        ini, _ = rango_utc_del_dia(d1)
        _, fin = rango_utc_del_dia(d2)
        ventas = s.exec(
            select(Venta).where(Venta.creada_at >= ini, Venta.creada_at < fin)
        ).all()
        # La plata que se movió a mano en el rango. El local lo pidió con estas
        # palabras: "no se resta de lo que sacó, o que tenga un cuadro del dinero
        # sacado". Los retiros ya se restaban en el CIERRE, pero en El día no
        # aparecían por ninguna parte, así que el efectivo del informe no calzaba
        # con lo que quedaba en el cajón y no había dónde mirar por qué.
        movs = s.exec(
            select(RetiroCaja).where(
                RetiroCaja.creado_at >= ini, RetiroCaja.creado_at < fin,
                RetiroCaja.anulado == False,          # noqa: E712
            ).order_by(RetiroCaja.creado_at.desc())
        ).all()
    dia = d1

    validas = [v for v in ventas if v.estado == "pagada"]
    anuladas = [v for v in ventas if v.estado == "anulada"]

    por_medio = {m: {"cantidad": 0, "total": 0} for m in MEDIOS_PAGO}
    total = propinas = descuentos = 0
    for v in validas:
        cobrado = v.total - v.descuento          # lo que realmente entró
        # Se reparte por medio de pago con el mismo criterio que el cierre. Antes
        # acá se hacía `por_medio[v.medio_pago]`, y desde que existe el pago mixto
        # ese campo puede valer "mixto", que no es una de las claves: UNA sola
        # venta mixta reventaba la pantalla entera de El día con un KeyError y el
        # dueño se quedaba sin informe del día. Repartiendo por partes, además,
        # la mitad en efectivo de un pago mixto aparece donde tiene que aparecer.
        for medio, monto in _pagos_de(s, v):
            if medio not in por_medio:
                continue
            # La venta se cuenta en CADA medio que tocó. Una mixta suma 1 en
            # efectivo y 1 en débito: la pregunta que contesta esta columna es
            # "cuántas ventas pasaron por acá", y por la máquina pasó una.
            # Contándola en uno solo, el otro quedaba mostrando plata con "0
            # ventas" al lado, que no se entiende.
            por_medio[medio]["cantidad"] += 1
            por_medio[medio]["total"] += monto
        total += cobrado
        descuentos += v.descuento
        propinas += v.propina

    neto, iva = neto_iva(total)
    vendidos: dict[str, dict] = {}
    balanza = {"cantidad": 0, "total": 0, "tickets": 0, "por_persona": []}
    balanza_por_persona: dict[str, dict] = {}
    for v in validas:
        for l in v.lineas:
            nombre = l.nombre
            if l.codigo_balanza:
                balanza["cantidad"] += 1
                balanza["total"] += l.subtotal
                balanza["tickets"] += int(l.modo_balanza == "ticket")
                # Un ticket trae su monto impreso en el papel: es la otra línea que
                # nadie puede contrastar contra la carta. Por eso, como los cobros a
                # mano, se ve quién la cobró.
                quien = _nombre(s, v.usuario_id) or "—"
                pp = balanza_por_persona.setdefault(quien, {"nombre": quien, "cantidad": 0, "total": 0})
                pp["cantidad"] += 1
                pp["total"] += l.subtotal
                # «9 Croissant» mezclaba unidades con etiquetas de 0,456 kg.
                if l.modo_balanza != "ticket":
                    nombre = f"{l.nombre} (balanza)"
            d = vendidos.setdefault(nombre, {"cantidad": 0, "total": 0})
            d["cantidad"] += l.cantidad
            d["total"] += l.subtotal

    top = sorted(vendidos.items(), key=lambda kv: kv[1]["cantidad"], reverse=True)[:10]
    dias = (d2 - d1).days + 1

    sacado = sum(r.monto for r in movs if r.tipo == "retiro")
    metido = sum(r.monto for r in movs if r.tipo == "ingreso")

    # Cuánta plata en efectivo hay son DOS preguntas distintas, y confundirlas es
    # lo que tenía al local mirando el "quedan" de un mes entero como si fuera lo
    # que había en el cajón:
    #   · efectivo_neto    — de lo vendido en efectivo, cuánto queda después de
    #     lo que se sacó. Sirve para cualquier rango, incluso un mes.
    #   · efectivo_en_caja — cuánta plata tiene que haber AHORA en el cajón. Solo
    #     existe mirando UN turno, porque necesita el fondo con que se abrió, y
    #     sale de la misma función que el cierre, así que da el mismo número.
    efectivo_neto = por_medio["efectivo"]["total"] - sacado + metido

    salida = {
        "fecha": dia.isoformat(),
        "desde": d1.isoformat(),
        "hasta": d2.isoformat(),
        "dias": dias,
        "promedio_diario": round(total / dias) if dias else 0,
        "ventas": len(validas),
        "total": total,
        "neto": neto,
        "iva": iva,
        "propinas": propinas,
        "descuentos": descuentos,
        "ticket_promedio": round(total / len(validas)) if validas else 0,
        "por_medio": por_medio,
        "anuladas": {"cantidad": len(anuladas),
                     "total": sum(v.total - v.descuento for v in anuladas)},
        "mas_vendidos": [{"nombre": n, **d} for n, d in top],
        # Lo que salió y entró del cajón a mano, y el detalle de cada uno.
        "sacado": sacado,
        "metido": metido,
        "efectivo_neto": efectivo_neto,
        "movimientos_caja": [{
            "tipo": r.tipo,
            "monto": r.monto,
            "motivo": r.motivo,
            "hora": a_local(r.creado_at).strftime("%H:%M"),
            "hecho_por": r.hecho_por,
        } for r in movs],
        # Los cobros a mano y la balanza, aparte: un monto escrito por la caja
        # y un total impreso en un ticket no se contrastan contra la carta.
        # Separarlos permite al dueño revisar de dónde salió cada cobro.
        "varios": _cobros_a_mano(s, ventas),
        "balanza": {**balanza, "por_persona": sorted(
            balanza_por_persona.values(), key=lambda d: -d["total"])},
        # Solo cuando se pidió un turno. `None` es la señal de que lo de arriba
        # es de un rango de días y no de una caja abierta ahora.
        "turno": None,
        "efectivo_en_caja": None,
    }

    if turno:
        salida["turno"] = {
            "id": turno.id,
            "abierto": turno.cerrado_at is None,
            "abrio": _nombre(s, turno.abierto_por_id) or turno.cajero,
            "cerro": _nombre(s, turno.cerrado_por_id),
            "abierto_at": a_local(turno.abierto_at).isoformat(),
            "cerrado_at": a_local(turno.cerrado_at).isoformat() if turno.cerrado_at else None,
            "monto_inicial": turno.monto_inicial,
            # Lo que entró al cajón por ventas, CON las propinas que se dejaron
            # en efectivo. No es lo mismo que `por_medio.efectivo`, que son solo
            # las ventas: la propina en billetes también quedó en el cajón. Va
            # aparte para que la cuenta de la pantalla dé exacto lo mismo que el
            # cierre, sin que nadie tenga que rehacerla.
            "efectivo_de_ventas": _efectivo_del_turno(s, turno),
            "propinas_pagadas": turno.propinas_pagadas,
            "efectivo_contado": turno.efectivo_contado,
            "diferencia": turno.diferencia,
        }
        salida["efectivo_en_caja"] = _efectivo_esperado(s, turno)
    return salida
