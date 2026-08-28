"""Descuentos: lo cobrado, el cuadre y el IVA tienen que seguir cuadrando."""


def test_el_descuento_baja_lo_cobrado(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "descuento": 400, "paga_con": 5000,
    }).json()
    assert v["total"] == 3400          # lo pedido, a precio de lista
    assert v["descuento"] == 400
    assert v["cobrado"] == 3000        # lo que pagó
    assert v["vuelto"] == 2000


def test_no_se_puede_descontar_mas_que_la_venta(cliente, carta):
    """Un descuento gigante dejaría un cobro negativo."""
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "descuento": 99999,
    }).json()
    assert v["descuento"] == 1900
    assert v["cobrado"] == 0


def test_el_resumen_cuenta_lo_cobrado_no_lo_listado(cliente, carta):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "descuento": 400})
    r = cliente.get("/api/v1/resumen").json()
    assert r["total"] == 3000
    assert r["descuentos"] == 400
    assert r["neto"] + r["iva"] == 3000     # el IVA se calcula sobre lo cobrado


def test_el_cuadre_de_caja_descuenta(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 0})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "descuento": 400, "propina": 200})
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["efectivo_esperado"] == 3200      # 3400 - 400 + 200


def test_el_comprobante_muestra_el_descuento(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "descuento": 400}).json()
    html = cliente.get(f"/comprobante/{v['id']}").text
    assert "Descuento" in html and "-$400" in html
    assert "$3.000" in html


def test_el_csv_trae_bruto_descuento_y_cobrado(cliente, carta):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "descuento": 400})
    texto = cliente.get("/api/v1/exportar/ventas").content.decode("utf-8-sig")
    assert "Bruto;Descuento;Cobrado" in texto
    assert ";3400;400;3000;" in texto


def test_sin_descuento_todo_sigue_igual(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    assert v["descuento"] == 0 and v["cobrado"] == v["total"] == 3400
