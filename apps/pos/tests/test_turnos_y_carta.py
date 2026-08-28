"""Cuadre de caja y la carta que consumen las pantallas del local."""


# ---------------------------------------------------------------- turnos
def test_cuadre_de_caja(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto", "monto_inicial": 20000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})                                   # 3400 al cajón
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "debito"})                                     # NO va al cajón

    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["efectivo_esperado"] == 23400

    cierre = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 23400, "nota": ""}).json()
    assert cierre["diferencia"] == 0


def test_el_descuadre_se_guarda_no_se_esconde(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 10000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    cierre = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 11000, "nota": "faltó"}).json()
    assert cierre["efectivo_esperado"] == 11900
    assert cierre["diferencia"] == -900


def test_la_propina_en_efectivo_va_al_cajon(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 0})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "propina": 500})
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["efectivo_esperado"] == 2400


def test_no_se_abren_dos_turnos(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 0})
    assert cliente.post("/api/v1/turnos/abrir", json={"cajero": "Otro", "monto_inicial": 0}).status_code == 409


def test_cerrar_sin_turno_abierto(cliente):
    assert cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0}).status_code == 409


# ---------------------------------------------------------------- carta
def test_formato_de_la_carta(cliente, carta):
    d = cliente.get("/api/v1/carta").json()
    assert set(d) >= {"avisos", "categorias"}
    cafe = next(c for c in d["categorias"] if c["nombre"] == "Café")
    assert cafe["destacado"]["nombre"] == "Mocha"
    assert cafe["destacado"]["etiqueta"] == "Hoy"
    # el destacado no se repite entre los productos normales
    assert "Mocha" not in [p["nombre"] for p in cafe["productos"]]
    p = cafe["productos"][0]
    assert set(p) == {"nombre", "descripcion", "precio", "antes", "etiqueta", "dibujo", "color"}


def test_la_carta_manda_cors(cliente, carta):
    """Sin esta cabecera el navegador de la pantalla rechaza la respuesta."""
    r = cliente.get("/api/v1/carta")
    assert r.headers.get("access-control-allow-origin") == "*"


def test_producto_apagado_no_sale_en_la_carta(cliente, carta):
    cliente.delete(f"/api/v1/productos/{carta['latte']['id']}")
    d = cliente.get("/api/v1/carta").json()
    cafe = next(c for c in d["categorias"] if c["nombre"] == "Café")
    assert "Latte" not in [p["nombre"] for p in cafe["productos"]]


def test_categoria_vacia_no_viaja(cliente, carta):
    """Una categoría sin productos rompe la pantalla: mejor no mandarla."""
    cliente.post("/api/v1/categorias", json={"nombre": "Vacía", "orden": 9})
    d = cliente.get("/api/v1/carta").json()
    assert "Vacía" not in [c["nombre"] for c in d["categorias"]]


def test_un_solo_destacado_por_categoria(cliente, carta):
    """Marcar otro destacado desmarca el anterior solo."""
    cliente.put(f"/api/v1/productos/{carta['latte']['id']}", json={
        **{k: v for k, v in carta["latte"].items() if k != "id"}, "destacado": True})
    d = cliente.get("/api/v1/carta").json()
    cafe = next(c for c in d["categorias"] if c["nombre"] == "Café")
    assert cafe["destacado"]["nombre"] == "Latte"
    cats = cliente.get("/api/v1/categorias").json()
    destacados = [p for c in cats for p in c["productos"] if p["destacado"]]
    assert len(destacados) == 1


def test_borrar_producto_es_logico(cliente, carta):
    """No se elimina: las ventas viejas tienen que seguir cuadrando."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"})
    cliente.delete(f"/api/v1/productos/{carta['latte']['id']}")
    assert cliente.get("/api/v1/resumen").json()["total"] == 3400
