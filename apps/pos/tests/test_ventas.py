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
