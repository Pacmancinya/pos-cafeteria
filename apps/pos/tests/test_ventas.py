"""Lo que tiene que cuadrar sí o sí: la plata."""
import pytest

from core.config import neto_iva


def test_total_cuadra_con_lineas(cliente, carta, caja):
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [
            {"producto_id": carta["espresso"]["id"], "cantidad": 2},
            {"producto_id": carta["alfajor"]["id"], "cantidad": 1},
        ],
        "medio_pago": "efectivo",
    })
    assert r.status_code == 200
    v = r.json()
    assert v["total"] == 1900 * 2 + 1900
    assert v["total"] == sum(l["subtotal"] for l in v["lineas"])


def test_vuelto(cliente, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "paga_con": 5000,
    }).json()
    assert v["cobrado"] == 3400
    assert v["vuelto"] == 1600


def test_vuelto_no_aplica_con_tarjeta(cliente, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "debito", "paga_con": 5000,
    }).json()
    assert v["vuelto"] is None


def test_el_precio_queda_congelado(cliente, carta, caja):
    """Si mañana sube el café, la venta de ayer NO cambia."""
    venta = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo",
    }).json()

    cliente.put(f"/api/v1/productos/{carta['espresso']['id']}", json={
        **{k: v for k, v in carta["espresso"].items() if k != "id"},
        "precio": 2500,
    })

    de_nuevo = cliente.get(f"/api/v1/ventas/{venta['id']}").json()
    assert de_nuevo["total"] == 1900
    assert de_nuevo["lineas"][0]["precio_unitario"] == 1900


def test_venta_sin_productos_se_rechaza(cliente, carta):
    assert cliente.post("/api/v1/ventas", json={"lineas": [], "medio_pago": "efectivo"}).status_code == 422


def test_medio_de_pago_inventado_se_rechaza(cliente, carta):
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "bitcoin",
    })
    assert r.status_code == 422


def test_anulada_no_suma_al_resumen(cliente, carta, caja):
    a = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"}).json()
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["alfajor"]["id"], "cantidad": 1}], "medio_pago": "efectivo"})

    cliente.post(f"/api/v1/ventas/{a['id']}/anular", json={"motivo": "se equivocó el cajero"})

    r = cliente.get("/api/v1/resumen").json()
    assert r["ventas"] == 1
    assert r["total"] == 1900
    assert r["anuladas"]["cantidad"] == 1
    assert r["anuladas"]["total"] == 3400


def test_no_se_anula_dos_veces(cliente, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"}).json()
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"}).status_code == 200
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"}).status_code == 409


def test_numeros_correlativos(cliente, carta, caja):
    numeros = [
        cliente.post("/api/v1/ventas", json={
            "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
            "medio_pago": "efectivo"}).json()["numero"]
        for _ in range(3)
    ]
    assert numeros == [1, 2, 3]


@pytest.mark.parametrize("bruto", [0, 1, 999, 1900, 3400, 123457, 1000000])
def test_neto_mas_iva_siempre_da_el_bruto(bruto):
    """Nunca se pierde ni se gana un peso al descomponer el IVA."""
    neto, iva = neto_iva(bruto)
    assert neto + iva == bruto
    assert neto >= 0 and iva >= 0


def test_resumen_descompone_el_iva(cliente, carta, caja):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"})
    r = cliente.get("/api/v1/resumen").json()
    assert r["neto"] + r["iva"] == r["total"] == 3400


# ------------------------------------------- sin caja abierta no se vende
def test_sin_caja_abierta_no_se_vende(cliente, carta):
    """Antes se aceptaba y la venta quedaba sin turno: no entraba en ningún
    cuadre, no aparecía en ningún cierre, y nadie se enteraba hasta que el
    efectivo del cajón no calzaba con nada. Plata sin dueño."""
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]})
    assert r.status_code == 409
    assert "caja está cerrada" in r.json()["detail"]


def test_al_abrir_la_caja_se_puede_vender(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    assert cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).status_code == 200


def test_al_cerrar_la_caja_deja_de_venderse(cliente, carta, caja):
    """El caso de las 20:00: se cierra la caja y alguien intenta cobrar uno más.
    Esa venta iría a un turno ya firmado y le movería el cuadre a alguien."""
    cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0})
    assert cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).status_code == 409


def test_toda_venta_queda_con_su_turno(cliente, carta, caja):
    """Es la consecuencia útil: ya no puede existir una venta huérfana."""
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()
    assert v["turno_id"] is not None


# ------------------------------------------------- los ajustes de la caja
def test_guardar_un_ajuste_no_pisa_los_otros(cliente):
    """El bug: la pantalla manda UNA clave, pero pydantic rellenaba las que
    faltaban con su valor por defecto y se escribían todas. O sea que mover el
    margen sugerido apagaba de paso el teclado en pantalla, en silencio."""
    cliente.put("/api/v1/ajustes", json={"teclado_en_pantalla": 1})
    assert cliente.get("/api/v1/ajustes").json()["teclado_en_pantalla"] == 1

    cliente.put("/api/v1/ajustes", json={"margen_sugerido": 65})
    quedo = cliente.get("/api/v1/ajustes").json()
    assert quedo["margen_sugerido"] == 65
    assert quedo["teclado_en_pantalla"] == 1, "mover el margen no puede apagar el teclado"


def test_un_valor_fuera_de_rango_guardado_a_mano_no_manda(cliente):
    """El `le=1` del schema solo corre al ESCRIBIR. Un 2 metido a mano en la
    tabla pasaba entero, y `!!2` prendía el teclado igual."""
    from sqlmodel import Session

    from apps.pos.db.models import Ajuste
    from apps.pos.db.session import engine
    with Session(engine) as s:
        s.add(Ajuste(clave="teclado_en_pantalla", valor="2"))
        s.commit()
    assert cliente.get("/api/v1/ajustes").json()["teclado_en_pantalla"] == 1


# ---------------------------------------------------------------------------
# Pago mixto (2.12)
# ---------------------------------------------------------------------------
"""Una parte en efectivo y otra en tarjeta. Se guarda cada parte, y el cuadre la
lee: el efectivo al cajón, la tarjeta contra la máquina. Una venta de un solo
medio no pasa por acá y sigue igual que siempre."""


def test_pago_mixto_reparte_al_cajon_y_a_la_tarjeta(cliente, carta, caja):
    # Latte 3400 + espresso 1900 = 5300. Pago 3000 efectivo + 2300 débito.
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1},
                   {"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "pagos": [{"medio": "efectivo", "monto": 3000},
                  {"medio": "debito", "monto": 2300}]}).json()
    assert v["medio_pago"] == "mixto"
    assert {p["medio"]: p["monto"] for p in v["pagos"]} == {"efectivo": 3000, "debito": 2300}

    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["ventas_efectivo"] == 3000                 # solo la parte en efectivo va al cajón
    debito = [m for m in t["medios"] if m["medio"] == "debito"][0]
    assert debito["esperado"] == 2300                   # la máquina cobró 2300


def test_las_partes_del_pago_mixto_tienen_que_sumar_lo_cobrado(cliente, carta, caja):
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "pagos": [{"medio": "efectivo", "monto": 1000},
                  {"medio": "debito", "monto": 1000}]})                      # suma 2000 != 3400
    assert r.status_code == 422
    assert "suman" in r.json()["detail"].lower()


def test_el_pago_mixto_respeta_el_descuento(cliente, carta, caja):
    # Latte 3400 con 400 de descuento = 3000 a cobrar.
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "descuento": 400,
        "pagos": [{"medio": "efectivo", "monto": 2000},
                  {"medio": "transferencia", "monto": 1000}]})
    assert v.status_code == 200, v.text


def test_una_venta_de_un_solo_medio_no_escribe_pagos(cliente, carta, caja):
    """Compatibilidad: sin `pagos`, todo sigue igual y no hay filas de Pago."""
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "debito"}).json()
    assert v["medio_pago"] == "debito"
    assert "pagos" not in v                             # una venta simple no trae split
    from apps.pos.db.session import engine
    from apps.pos.db.models import Pago
    from sqlmodel import Session, select
    with Session(engine) as s:
        assert s.exec(select(Pago)).first() is None


def test_anular_una_venta_mixta_la_saca_del_cuadre(cliente, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "pagos": [{"medio": "efectivo", "monto": 2000},
                  {"medio": "debito", "monto": 1400}]}).json()
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "se arrepintió"})
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["ventas_efectivo"] == 0                    # ya no cuenta
    assert t["por_medio"] == {}


def test_el_cierre_cuadra_con_una_venta_mixta(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi", "monto_inicial": 5000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "pagos": [{"medio": "efectivo", "monto": 2400},
                  {"medio": "debito", "monto": 1000}]})
    # En el cajón: 5000 fondo + 2400 efectivo = 7400.
    cierre = cliente.post("/api/v1/turnos/cerrar", json={
        "efectivo_contado": 7400, "fondo_siguiente": 0}).json()
    assert cierre["diferencia"] == 0


# ---------------------------------------------------------------------------
# El dia: pago mixto y plata sacada de la caja (2.15)
# ---------------------------------------------------------------------------
"""Dos cosas que el local vio en el mostrador.

La grave: UNA venta con pago mixto reventaba la pantalla entera de El dia. El
resumen repartia con `por_medio[v.medio_pago]` y desde la 2.12 ese campo puede
valer "mixto", que no es una de las claves: KeyError y el dueno se quedaba sin
informe del dia.

La reportada: "no se resta de lo que saco, o que tenga un cuadro del dinero
sacado". Los retiros ya se restaban en el CIERRE, pero en El dia no aparecian, y
el efectivo del informe no calzaba con lo que quedaba en el cajon."""


def test_una_venta_mixta_no_rompe_el_dia(cliente, carta, caja):
    """La regresion que importa: antes esto era un KeyError y se caia la pagina."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "pagos": [{"medio": "efectivo", "monto": 2000},
                  {"medio": "debito", "monto": 1400}]})
    r = cliente.get("/api/v1/resumen")
    assert r.status_code == 200, "una venta mixta no puede tumbar El dia"
    j = r.json()
    assert j["total"] == 3400


def test_el_dia_reparte_el_pago_mixto_por_medio(cliente, carta, caja):
    """La parte en efectivo tiene que sumar en Efectivo, y la de tarjeta en
    Tarjetas. Antes la venta entera caia en una sola clave (o reventaba)."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "medio_pago": "efectivo"})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "pagos": [{"medio": "efectivo", "monto": 2000},
                  {"medio": "debito", "monto": 1400}]})
    j = cliente.get("/api/v1/resumen").json()
    assert j["por_medio"]["efectivo"]["total"] == 5400      # 3400 + 2000
    assert j["por_medio"]["debito"]["total"] == 1400        # la otra parte
    assert j["total"] == 6800


def test_el_dia_muestra_la_plata_sacada_de_la_caja(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi", "monto_inicial": 20000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "medio_pago": "efectivo"})
    cliente.post("/api/v1/turnos/retiro", json={"monto": 5000, "motivo": "gas"})
    cliente.post("/api/v1/turnos/ingreso", json={"monto": 1000, "motivo": "traje cambio"})

    j = cliente.get("/api/v1/resumen").json()
    assert j["sacado"] == 5000
    assert j["metido"] == 1000
    # Lo que el dueno esperaba ver: el efectivo del dia ya con lo sacado restado.
    assert j["efectivo_neto"] == 3400 - 5000 + 1000
    # Y el cuadro, con motivo y quien.
    motivos = {m["motivo"]: m for m in j["movimientos_caja"]}
    assert motivos["gas"]["tipo"] == "retiro"
    assert motivos["traje cambio"]["tipo"] == "ingreso"


def test_un_retiro_anulado_no_sale_en_el_dia(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi", "monto_inicial": 20000})
    r = cliente.post("/api/v1/turnos/retiro", json={"monto": 5000, "motivo": "error"}).json()
    cliente.post(f"/api/v1/turnos/retiro/{r['retiros'][0]['id']}/anular")
    j = cliente.get("/api/v1/resumen").json()
    assert j["sacado"] == 0
    assert j["movimientos_caja"] == []


def test_sin_movimientos_el_dia_no_inventa_el_cuadro(cliente, carta, caja):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    j = cliente.get("/api/v1/resumen").json()
    assert j["sacado"] == 0 and j["metido"] == 0
    assert j["movimientos_caja"] == []
    assert j["efectivo_neto"] == j["por_medio"]["efectivo"]["total"]


# ══════════ El dia mirado por TURNO (2.16) ══════════
# El local lo dijo asi: "tiene la caja abierta y no ha vendido nada, y aun asi
# salen venta de hoy con dinero, ticket promedio, efectivo... lo ideal sea que
# el elija el turno y vea las metricas del turno". Los numeros eran del rango de
# fechas y estaban bien; el problema es que al lado de un cajon vacio se leen
# como si fueran de ahora.


def _abrir(cliente, cajero, fondo):
    return cliente.post("/api/v1/turnos/abrir",
                        json={"cajero": cajero, "monto_inicial": fondo}).json()


def _cerrar(cliente, contado):
    # En monedas de $100, que si es una denominacion real: las que no estan en
    # la lista se ignoran y el conteo daria 0.
    return cliente.post("/api/v1/turnos/cerrar",
                        json={"conteo": {"100": contado // 100}}).json()


def test_el_resumen_de_un_turno_solo_cuenta_ese_turno(cliente, carta):
    """Dos cajas el mismo dia. Lo de la manana no es lo de la tarde."""
    manana = _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "medio_pago": "efectivo"})
    _cerrar(cliente, 13400)

    tarde = _abrir(cliente, "Pau", 5000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["alfajor"]["id"], "cantidad": 1}],  # 1900
        "medio_pago": "efectivo"})

    del_dia = cliente.get("/api/v1/resumen").json()
    assert del_dia["total"] == 5300 and del_dia["turno"] is None

    m = cliente.get(f"/api/v1/resumen?turno_id={manana['id']}").json()
    assert m["total"] == 3400 and m["ventas"] == 1
    t = cliente.get(f"/api/v1/resumen?turno_id={tarde['id']}").json()
    assert t["total"] == 1900 and t["ventas"] == 1


def test_una_caja_recien_abierta_no_muestra_la_plata_de_antes(cliente, carta):
    """EL reclamo, tal cual: caja abierta sin vender, y cifras igual.

    El dia entero tiene ventas; el turno nuevo, ninguna. Pedido por turno, todo
    tiene que dar cero — incluido el ticket promedio, que es el que mas engana
    porque un promedio con cara de dato hace pensar que hubo ventas.
    """
    _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    _cerrar(cliente, 13400)

    nuevo = _abrir(cliente, "Pau", 13400)
    j = cliente.get(f"/api/v1/resumen?turno_id={nuevo['id']}").json()
    assert j["total"] == 0
    assert j["ventas"] == 0
    assert j["ticket_promedio"] == 0
    assert j["por_medio"]["efectivo"]["total"] == 0
    assert j["mas_vendidos"] == []
    # Lo unico que si tiene plata es el cajon, porque el fondo esta ahi.
    assert j["efectivo_en_caja"] == 13400


def test_lo_que_hay_en_el_cajon_es_el_mismo_numero_del_cierre(cliente, carta):
    """El dia y el cierre no pueden discrepar: sale de la misma funcion."""
    _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "medio_pago": "efectivo"})
    cliente.post("/api/v1/turnos/retiro", json={"monto": 5000, "motivo": "gas"})
    cliente.post("/api/v1/turnos/ingreso", json={"monto": 2000, "motivo": "cambio"})

    actual = cliente.get("/api/v1/turnos/actual").json()["turno"]
    j = cliente.get(f"/api/v1/resumen?turno_id={actual['id']}").json()
    assert j["efectivo_en_caja"] == actual["efectivo_esperado"] == 10400


def test_la_cuenta_del_cajon_se_puede_seguir_a_mano(cliente, carta):
    """Lo que reclamaron fue "aparece lo sacado, pero no se resta".

    Se restaba, pero en ningun lado se VEIA restarse. La pantalla dibuja la
    cuenta entera con estos campos, asi que tienen que cerrar exacto.
    """
    _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "medio_pago": "efectivo", "propina": 500})
    cliente.post("/api/v1/turnos/retiro", json={"monto": 5000, "motivo": "gas"})
    cliente.post("/api/v1/turnos/ingreso", json={"monto": 2000, "motivo": "cambio"})

    actual = cliente.get("/api/v1/turnos/actual").json()["turno"]
    j = cliente.get(f"/api/v1/resumen?turno_id={actual['id']}").json()
    t = j["turno"]
    cuenta = (t["monto_inicial"] + t["efectivo_de_ventas"]
              - t["propinas_pagadas"] - j["sacado"] + j["metido"])
    assert cuenta == j["efectivo_en_caja"]
    # La propina en billetes tambien quedo en el cajon: por eso no alcanza con
    # `por_medio.efectivo`, que son solo las ventas.
    assert t["efectivo_de_ventas"] == 3400 + 500
    assert j["por_medio"]["efectivo"]["total"] == 3400


def test_el_retiro_de_otro_turno_no_le_cuenta_al_de_ahora(cliente, carta):
    """Sumarselo al que llego despues le inventa un faltante que no es suyo."""
    _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/turnos/retiro", json={"monto": 5000, "motivo": "gas"})
    _cerrar(cliente, 5000)

    tarde = _abrir(cliente, "Pau", 5000)
    j = cliente.get(f"/api/v1/resumen?turno_id={tarde['id']}").json()
    assert j["sacado"] == 0
    assert j["movimientos_caja"] == []
    # El del dia si los ve los dos: son del dia.
    assert cliente.get("/api/v1/resumen").json()["sacado"] == 5000


def test_las_ventas_tambien_se_piden_por_turno(cliente, carta):
    """La lista de al lado tiene que ser del mismo turno que las cifras."""
    manana = _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    _cerrar(cliente, 13400)
    tarde = _abrir(cliente, "Pau", 5000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["alfajor"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})

    assert len(cliente.get("/api/v1/ventas").json()["ventas"]) == 2
    assert len(cliente.get(f"/api/v1/ventas?turno_id={manana['id']}").json()["ventas"]) == 1
    tj = cliente.get(f"/api/v1/ventas?turno_id={tarde['id']}").json()
    assert [v["total"] for v in tj["ventas"]] == [1900]


def test_un_turno_que_no_existe_no_devuelve_cifras_en_cero(cliente):
    """Cero no es "no hay": un 404 evita que la pantalla muestre un turno falso."""
    assert cliente.get("/api/v1/resumen?turno_id=999").status_code == 404
    assert cliente.get("/api/v1/ventas?turno_id=999").status_code == 404


def test_sin_turno_el_resumen_sigue_siendo_del_rango(cliente, carta, caja):
    """Lo de siempre no cambia: el dueno sigue mirando dias, semanas y meses."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    j = cliente.get("/api/v1/resumen").json()
    assert j["turno"] is None
    # `efectivo_en_caja` no existe fuera de un turno: son varios cajones.
    assert j["efectivo_en_caja"] is None
    assert j["total"] == 3400


def test_un_turno_cerrado_muestra_lo_que_se_conto(cliente, carta):
    """Mirando un turno viejo se ve el descuadre sin abrir el cierre."""
    _abrir(cliente, "Javi", 10000)
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "medio_pago": "efectivo"})
    t = _cerrar(cliente, 13000)                 # faltan 400

    j = cliente.get(f"/api/v1/resumen?turno_id={t['id']}").json()
    assert j["turno"]["abierto"] is False
    assert j["turno"]["efectivo_contado"] == 13000
    assert j["turno"]["diferencia"] == -400
    assert j["efectivo_en_caja"] == 13400
