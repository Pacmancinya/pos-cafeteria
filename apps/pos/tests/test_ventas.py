"""Lo que tiene que cuadrar sí o sí: la plata."""
import pytest

from core.config import neto_iva


def test_total_cuadra_con_lineas(cliente, carta):
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


def test_vuelto(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "paga_con": 5000,
    }).json()
    assert v["cobrado"] == 3400
    assert v["vuelto"] == 1600


def test_vuelto_no_aplica_con_tarjeta(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "debito", "paga_con": 5000,
    }).json()
    assert v["vuelto"] is None


def test_el_precio_queda_congelado(cliente, carta):
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


def test_anulada_no_suma_al_resumen(cliente, carta):
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


def test_no_se_anula_dos_veces(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"}).json()
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"}).status_code == 200
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"}).status_code == 409


def test_numeros_correlativos(cliente, carta):
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


def test_resumen_descompone_el_iva(cliente, carta):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"})
    r = cliente.get("/api/v1/resumen").json()
    assert r["neto"] + r["iva"] == r["total"] == 3400
