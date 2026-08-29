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


def test_las_pantallas_se_abren_sin_pin_desde_la_red(cliente):
    """Un TV colgado en la pared no tiene teclado para escribir el PIN, y lo
    que muestra ya está a la vista del público."""
    with remoto() as r:
        resp = r.get("/pantallas")
        assert resp.status_code == 200
        assert "Pantallas Kofe" in resp.text


def test_las_pantallas_traen_su_direccion_en_salud(cliente):
    s = cliente.get("/api/v1/salud").json()
    assert s["pantallas_url"].endswith("/pantallas")


def test_la_pantalla_para_tv_viejo_tambien_se_abre_sin_pin(cliente):
    """Es la que se usa JUSTO cuando algo no funciona: pedirle un PIN a un
    televisor que ya se vio en blanco sería el peor momento posible."""
    with remoto() as r:
        resp = r.get("/pantallas/simple")
        assert resp.status_code == 200
        assert "/api/v1/carta" in resp.text


def test_la_pantalla_para_tv_viejo_no_usa_nada_moderno(cliente):
    """El navegador de un smart TV puede ser de 2015. Si alguien "moderniza"
    este archivo, deja de servir para lo único que existe.

    No es un test de estilo: cada cosa de esta lista es un motivo real por el
    que la página se vería en blanco en el televisor del local.
    """
    import re

    pagina = cliente.get("/pantallas/simple").text
    # Los comentarios se sacan primero: el archivo EXPLICA que no usa nada de
    # esto, y ese texto haría fallar el test por decir la verdad.
    pagina = re.sub(r"<!--.*?-->", "", pagina, flags=re.S)
    pagina = re.sub(r"/\*.*?\*/", "", pagina, flags=re.S)
    pagina = re.sub(r"(?m)^\s*//.*$", "", pagina)

    prohibido = {
        "var(--": "variables CSS",
        "display:grid": "CSS Grid",
        "display: grid": "CSS Grid",
        "@font-face": "fuentes incrustadas",
        "=>": "funciones flecha",
        "`": "template literals",
        "fetch(": "fetch()",
        "const ": "declaraciones const",
        "let ": "declaraciones let",
    }
    encontrados = [q for c, q in prohibido.items() if c in pagina]
    assert not encontrados, f"la pantalla simple usa: {sorted(set(encontrados))}"
