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


def test_desde_otro_equipo_no_se_puede_anular_sin_pin(cliente, carta, caja):
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


def test_con_el_pin_correcto_se_entra(cliente, carta, caja):
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


def test_desde_la_caja_no_se_pide_pin(cliente, carta, caja):
    """El cajero no tiene que escribir nada: 127.0.0.1 pasa directo."""
    assert cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).status_code == 200


def test_la_carta_se_abre_sin_pin_para_el_programa_de_las_pantallas(cliente, carta):
    """Es el ÚNICO contrato que queda entre la caja y las pantallas, que desde
    la 2.2 son otro programa. Si esto pidiera PIN, cada TV del local necesitaría
    que alguien lo escribiera, y un TV colgado en la pared no tiene teclado."""
    with remoto() as r:
        resp = r.get("/api/v1/carta")
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "*"
        assert "categorias" in resp.json()


def test_la_caja_ya_no_sirve_las_pantallas(cliente):
    """Se separaron a propósito: un almacén o una botillería no tienen
    televisores. Si alguien las vuelve a meter acá, que sea decidiéndolo."""
    assert cliente.get("/pantallas").status_code == 404
    assert cliente.get("/pantallas/simple").status_code == 404
    assert "pantallas_url" not in cliente.get("/api/v1/salud").json()


def test_la_pantalla_del_cajero_nunca_se_guarda_en_cache(cliente):
    """index.html es el único archivo sin `?v=` en su dirección, porque es el
    que LLEVA los `?v=` de todos los demás. Sin esta cabecera, el navegador
    puede quedarse con su copia sin preguntar: la caja se actualiza, el número
    de versión sube, y la pantalla sigue siendo la anterior porque el HTML viejo
    sigue pidiendo los archivos viejos. Pasó de verdad."""
    r = cliente.get("/")
    assert r.status_code == 200
    assert "no-store" in (r.headers.get("cache-control") or "")


def test_los_demas_archivos_si_se_pueden_guardar(cliente):
    """Y está bien que se guarden: cada uno lleva su `?v=` y cambia de dirección
    cuando cambia. Si tampoco se guardaran, cada arranque bajaría todo de nuevo."""
    r = cliente.get("/static/app.js")
    assert r.status_code == 200
    assert "no-store" not in (r.headers.get("cache-control") or "")
