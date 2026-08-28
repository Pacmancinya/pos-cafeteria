"""Respaldo, exportación para el contador y los papeles imprimibles."""
import os


def test_respaldo_deja_una_copia(cliente, carta, tmp_path, monkeypatch):
    from tools import respaldo
    monkeypatch.setattr(respaldo, "CARPETA", str(tmp_path))
    r = cliente.post("/api/v1/respaldo").json()
    assert r["ok"] is True
    assert os.path.exists(os.path.join(str(tmp_path), r["archivo"]))


def test_el_respaldo_se_puede_abrir_y_tiene_los_datos(cliente, carta, tmp_path, monkeypatch):
    """Una copia que no se puede abrir no es un respaldo."""
    import sqlite3

    from tools import respaldo
    monkeypatch.setattr(respaldo, "CARPETA", str(tmp_path))
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], "medio_pago": "efectivo"})

    r = cliente.post("/api/v1/respaldo").json()
    con = sqlite3.connect(os.path.join(str(tmp_path), r["archivo"]))
    try:
        total = con.execute("select total from venta").fetchone()[0]
    finally:
        con.close()
    assert total == 3400


def test_exportar_ventas_sale_para_excel(cliente, carta):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}], "medio_pago": "efectivo"})
    r = cliente.get("/api/v1/exportar/ventas")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    texto = r.content.decode("utf-8-sig")
    assert texto.startswith("Fecha;Hora;")          # separador ; para el Excel en español
    assert r.content.startswith(b"\xef\xbb\xbf")    # BOM: si no, los acentos salen mal
    assert "6800" in texto


def test_exportar_detalle_lista_los_productos(cliente, carta):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 3}], "medio_pago": "efectivo"})
    texto = cliente.get("/api/v1/exportar/detalle").content.decode("utf-8-sig")
    assert "Espresso;3;1900;5700" in texto


def test_la_exportacion_no_incluye_las_anuladas_en_el_detalle(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "prueba"})
    assert "Espresso" not in cliente.get("/api/v1/exportar/detalle").content.decode("utf-8-sig")


def test_comprobante_dice_que_no_es_boleta(cliente, carta):
    """Si pareciera una boleta sin serlo, el local queda expuesto."""
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    html = cliente.get(f"/comprobante/{v['id']}").text
    assert "NO ES BOLETA" in html
    assert "$3.400" in html
    assert "Latte" in html


def test_comprobante_de_venta_anulada_lo_dice(cliente, carta):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"})
    assert "VENTA ANULADA" in cliente.get(f"/comprobante/{v['id']}").text


def test_cierre_imprimible_muestra_el_descuadre(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 10000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}], "medio_pago": "efectivo"})
    t = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 11000, "nota": ""}).json()
    html = cliente.get(f"/cierre/{t['id']}").text
    assert "CIERRE DE CAJA" in html
    assert "FALTA" in html
    assert "$900" in html


def test_papeles_de_algo_que_no_existe(cliente):
    assert cliente.get("/comprobante/999").status_code == 404
    assert cliente.get("/cierre/999").status_code == 404
