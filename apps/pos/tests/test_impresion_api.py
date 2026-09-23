"""Imprimir lee una venta terminada, sin volver a cobrar ni modificar la caja."""
import pytest

from apps.pos import impresion_windows as windows, sesion
from apps.pos.api.impresion import _lineas
from apps.pos.db.session import engine
from apps.pos.main import app


def estado_base():
    with engine.connect() as c:
        return tuple(c.connection.driver_connection.iterdump())


@pytest.mark.parametrize("crudo", [False, True])
def test_comprobante_y_prueba_sin_mutaciones(cliente, carta, caja, monkeypatch, crudo):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "descuento": 500,
        "pagos": [{"medio": "efectivo", "monto": 2000}, {"medio": "debito", "monto": 900}],
    }).json()
    envios = []

    def enviar(*args):
        envios.append(args)
        return {"ok": True, "detalle": "Enviado a la cola"}

    funcion = "imprimir_crudo" if crudo else "imprimir"
    prefijo = "crudo/" if crudo else ""
    monkeypatch.setattr(windows, funcion, enviar)
    antes = estado_base()
    datos = {"impresora": "Caja ñ", "papel": 58}
    ruta = f"/api/v1/impresion/{prefijo}comprobante/{v['id']}"
    assert cliente.post(ruta, json=datos).status_code == 200
    assert envios[-1][:2] == ("Caja ñ", 58)
    papel = "\n".join(envios[-1][2])
    for texto in ("NO ES BOLETA", "Latte", "TOTAL  $2.900", "Descuento  -$500",
                  "Pago Efectivo  $2.000", "Pago Débito  $900", "IVA 19%"):
        assert texto in papel
    assert "window.print" not in papel and "<td" not in papel
    assert cliente.post(ruta, json=datos).status_code == 200  # reimpresión, no venta
    assert cliente.post(f"/api/v1/impresion/{prefijo}prueba", json=datos).status_code == 200
    assert "Prueba sin venta ni cobro." in envios[-1][2]
    assert estado_base() == antes

    def fallar(*args):
        raise windows.ErrorImpresion("Windows no confirmó. No se reintentó.")

    monkeypatch.setattr(windows, funcion, fallar)
    r = cliente.post(ruta, json=datos)
    assert r.status_code == 503
    assert "No se reintentó" in r.json()["detail"]
    assert estado_base() == antes


def test_anulada_propina_y_papel_en_ambas_salidas(cliente, carta, caja, monkeypatch):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "propina": 340,
    }).json()
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "Prueba"})
    envios = []
    monkeypatch.setattr(windows, "imprimir", lambda *a: envios.append(a) or {"ok": True})
    for ancho in (58, 80):
        r = cliente.post(f"/api/v1/impresion/comprobante/{v['id']}",
                         json={"impresora": "Caja", "papel": ancho})
        assert r.status_code == 200
        assert envios[-1][1] == ancho
        texto = "\n".join(envios[-1][2])
        assert "VENTA ANULADA" in texto and "Propina  $340" in texto
        html = cliente.get(f"/comprobante/{v['id']}?papel={ancho}").text
        assert f"size:{ancho}mm" in html
        assert f"width:{ancho - 8}mm" in html
    assert cliente.get(f"/comprobante/{v['id']}?papel=60").status_code == 422


def test_validacion_y_venta_ausente_no_llegan_al_driver(cliente, monkeypatch):
    monkeypatch.setattr(windows, "imprimir", lambda *a: pytest.fail("No imprimir"))
    ruta = "/api/v1/impresion/comprobante/9999"
    datos = {"impresora": "Caja", "papel": 80}
    assert cliente.post(ruta, json=datos).status_code == 404
    for cambio in ({"papel": 60}, {"papel": "58"}, {"impresora": ""},
                   {"impresora": "x" * 257}, {"html": "texto arbitrario"}, {"ruta": "C:/"}):
        assert cliente.post("/api/v1/impresion/prueba", json={**datos, **cambio}).status_code == 422


def test_permisos_impresion(cliente, monkeypatch):
    llamadas = []
    monkeypatch.setattr(windows, "listar", lambda: llamadas.append("lista") or
                        {"disponible": True, "impresoras": []})
    monkeypatch.setattr(windows, "imprimir", lambda *a: llamadas.append("papel") or {"ok": True})
    monkeypatch.setattr(windows, "imprimir_crudo", lambda *a: llamadas.append("crudo") or {"ok": True})
    monkeypatch.setattr(windows, "puertos_sin_impresora", lambda: llamadas.append("puertos") or {"puertos": []})
    monkeypatch.setattr(windows, "instalar", lambda *a: llamadas.append("instalar") or {"ok": True})
    datos = {"impresora": "Caja", "papel": 80}
    try:
        for rol, permisos, codigo in (("", "", 401), ("cajero", "", 403), ("dueno", "vender", 403)):
            app.dependency_overrides[sesion.quien_es] = lambda: {
                "rol": rol, "permisos": permisos, "nombre": "Prueba"}
            assert cliente.get("/api/v1/impresion/impresoras").status_code == codigo
            assert cliente.post("/api/v1/impresion/prueba", json=datos).status_code == codigo
            assert cliente.post("/api/v1/impresion/crudo/prueba", json=datos).status_code == codigo
            assert cliente.get("/api/v1/impresion/puertos").status_code == codigo
            assert cliente.post("/api/v1/impresion/instalar", json={
                "puerto": "USB001", "nombre": "Kofe Tickets"}).status_code == codigo
        assert not llamadas
        app.dependency_overrides[sesion.quien_es] = lambda: {
            "rol": "dueno", "permisos": "config", "nombre": "Prueba"}
        assert cliente.get("/api/v1/impresion/impresoras").status_code == 200
        assert cliente.post("/api/v1/impresion/prueba", json=datos).status_code == 200
        assert cliente.post("/api/v1/impresion/crudo/prueba", json=datos).status_code == 200
        assert cliente.get("/api/v1/impresion/puertos").status_code == 200
        assert cliente.post("/api/v1/impresion/instalar", json={
            "puerto": "USB001", "nombre": "Kofe Tickets"}).status_code == 200
        assert cliente.post("/api/v1/impresion/comprobante/1", json=datos).status_code == 403
        assert cliente.post("/api/v1/impresion/crudo/comprobante/1", json=datos).status_code == 403
    finally:
        app.dependency_overrides.pop(sesion.quien_es, None)


def test_texto_escapado_se_imprime_como_texto():
    assert _lineas('<div>Café &amp; té</div><table><tr><td>&lt;script&gt;</td>'
                   '<td>$1.000</td></tr></table><div>NO ES BOLETA<br>Interno</div>') == [
        "Café & té", "<script>  $1.000", "NO ES BOLETA", "Interno"]


def test_instalacion_api_rechazo_y_validacion(cliente, monkeypatch):
    llamadas = []

    def instalar(*args):
        llamadas.append(args)
        raise windows.ErrorImpresion("Se canceló el permiso de Windows. No se instaló la impresora.", 409)

    monkeypatch.setattr(windows, "instalar", instalar)
    datos = {"puerto": "USB001", "nombre": "Kofe Tickets"}
    r = cliente.post("/api/v1/impresion/instalar", json=datos)
    assert r.status_code == 409
    assert "No se instaló" in r.json()["detail"]
    assert llamadas == [("USB001", "Kofe Tickets")]
    for campo, valor in (("nombre", "$(comando)"), ("nombre", "x" * 61), ("puerto", ""), ("script", "comando")):
        assert cliente.post("/api/v1/impresion/instalar", json={**datos, campo: valor}).status_code == 422
    assert len(llamadas) == 1
