"""El candado de la red: la caja abierta al wifi de invitados sería un agujero."""
from fastapi.testclient import TestClient

from apps.pos.main import app
from core.config import PIN


def remoto():
    """Un equipo cualquiera de la red del local (o del wifi de invitados)."""
    return TestClient(app, client=("192.168.1.99", 5000))


def test_la_carta_es_publica(cliente, carta):
    """Las pantallas del menú viven en otro PC y tienen que poder leerla."""
    with remoto() as r:
        assert r.get("/api/v1/carta").status_code == 200


def test_la_salud_es_publica(cliente):
    with remoto() as r:
        assert r.get("/api/v1/salud").status_code == 200


def test_desde_otro_equipo_no_se_puede_vender_sin_pin(cliente, carta):
    with remoto() as r:
        resp = r.post("/api/v1/ventas", json={
            "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
            "medio_pago": "efectivo"})
        assert resp.status_code == 401


def test_desde_otro_equipo_no_se_puede_anular_sin_pin(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    with remoto() as r:
        assert r.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"}).status_code == 401


def test_la_caja_redirige_a_pedir_pin(cliente):
    with remoto() as r:
        resp = r.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/entrar"


def test_con_el_pin_correcto_se_entra(cliente, carta):
    with remoto() as r:
        assert r.post("/entrar", data={"pin": PIN}, follow_redirects=False).status_code == 303
        # la galleta quedó puesta: ahora sí puede vender
        assert r.post("/api/v1/ventas", json={
            "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
            "medio_pago": "efectivo"}).status_code == 200


def test_con_el_pin_malo_no_se_entra(cliente):
    with remoto() as r:
        resp = r.post("/entrar", data={"pin": "0000"}, follow_redirects=False)
        assert resp.status_code == 401
        assert "Ese PIN no es" in resp.text


def test_desde_la_caja_no_se_pide_pin(cliente, carta):
    """El cajero no tiene que escribir nada: 127.0.0.1 pasa directo."""
    assert cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).status_code == 200
