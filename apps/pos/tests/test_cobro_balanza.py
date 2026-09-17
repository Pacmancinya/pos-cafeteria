"""El papel no fija el precio por kilo: cobrar vuelve a consultar al servidor.

Los tickets identifican un cobro; dos paquetes iguales, en cambio, pueden traer
la misma etiqueta. Estas pruebas pasan por la API, igual que el escáner, y miran
también el libro, el papel y lo que recibe el contador.
"""
from __future__ import annotations

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlmodel import Session, select

from apps.pos.db.models import CodigoBarra, Insumo, Movimiento, Venta, VentaLinea
from apps.pos.db.session import engine
from core.codigos import digito_verificador
from core.config import a_local, ahora


def _ean(base):
    assert len(base) == 12
    return base + str(digito_verificador(base))


def _etiqueta(valor=197, identificador=3976, prefijo="25"):
    return _ean(f"{prefijo}{identificador:04d}{valor:06d}")


def _formato(cliente, modo="plu_peso", **extra):
    formato = {"modo": modo, "prefijo": "25", "codigo": [2, 6],
               "valor": [6, 12], "divisor_peso": 1000, **extra}
    r = cliente.put("/api/v1/ajustes", json={"formato_balanza": formato})
    assert r.status_code == 200, r.text
    return formato


@pytest.fixture(autouse=True)
def _balanza_prendida(cliente):
    """Todas las pruebas de este archivo son de un local CON balanza."""
    r = cliente.put("/api/v1/ajustes", json={"usar_balanza": 1})
    assert r.status_code == 200, r.text
    assert r.json()["usar_balanza"] == 1


def test_viene_apagada_y_apagada_no_cobra(cliente, caja):
    """Un café sin balanza no puede cobrar un código 25... inventado: sería un cobro
    a mano sin el permiso de cobro a mano."""
    cliente.put("/api/v1/ajustes", json={"usar_balanza": 0})
    codigo = _ean("2539760001970"[:12])
    r = _escanear(cliente, codigo)
    assert "balanza" not in r
    assert r["problema"]              # se niega como siempre: lo imprimió una balanza
    assert _cobrar(cliente, codigo).status_code == 409
    from apps.pos.api.ajustes import POR_DEFECTO
    assert POR_DEFECTO["usar_balanza"] == 0


def _jamon(cliente, carta, **extra):
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Jamón pierna",
        "plu": "00123", "precio_kilo": 8990, "precio": 900, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _cobrar(cliente, codigo, **extra):
    return cliente.post("/api/v1/ventas", json={
        "lineas": [{"codigo_balanza": codigo, **extra}]})


def _escanear(cliente, codigo):
    r = cliente.get(f"/api/v1/codigos/{codigo}")
    assert r.status_code == 200
    return r.json()


def test_ticket_se_cobra_por_el_total_y_guarda_el_codigo_limpio(cliente, caja):
    codigo = _etiqueta()
    vista = _escanear(cliente, codigo)
    assert vista == {
        "encontrado": False, "codigo": codigo, "de_balanza": True,
        "se_puede_guardar": False,
        # Solo para pantallas de antes de la 2.26; la nueva mira `balanza` primero.
        "problema": "Recarga la pantalla (F5) para cobrar etiquetas de balanza.",
        "balanza": {"codigo": codigo, "modo": "ticket", "nombre": "Balanza",
                    "detalle": "Ticket 3976", "precio": 197,
                    "producto_id": None, "repetible": False}}
    r = _cobrar(cliente, f" {codigo[:6]}-{codigo[6:]}\r\n")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["total"] == 197
    assert v["lineas"][0]["detalle"] == "Ticket 3976"
    with Session(engine) as s:
        l = s.exec(select(VentaLinea).where(VentaLinea.venta_id == v["id"])).one()
        assert (l.codigo_balanza, l.producto_id, l.peso_g, l.modo_balanza) == (
            codigo, None, 0, "ticket")


@pytest.mark.parametrize("kilo,gramos,total", [(8990, 250, 2248), (10, 250, 3),
                                                (2, 250, 1), (100, 145, 15)])
def test_peso_redondea_con_decimal_half_up(cliente, caja, carta, kilo, gramos, total):
    # 100 * float('0.145') da 14.499999999999998: aun queriendo redondear
    # mitades hacia arriba, un float cobraría 14 en lugar de los 15 correctos.
    _formato(cliente)
    p = _jamon(cliente, carta, precio_kilo=kilo)
    codigo = _etiqueta(gramos, 123)
    vista = _escanear(cliente, codigo)["balanza"]
    assert vista["precio"] == total
    assert vista["producto_id"] == p["id"] and vista["repetible"] is True
    r = _cobrar(cliente, codigo)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == total
    with Session(engine) as s:
        l = s.exec(select(VentaLinea)).one()
        assert l.peso_g == gramos and l.nombre == "Jamón pierna"


def test_plu_precio_y_dos_paquetes_iguales(cliente, caja, carta):
    _formato(cliente, "plu_precio")
    p = _jamon(cliente, carta, plu="123", precio_kilo=0)
    codigo = _etiqueta(3141, 123)
    assert _escanear(cliente, codigo)["balanza"] == {
        "codigo": codigo, "modo": "plu_precio", "nombre": "Jamón pierna",
        "detalle": "PLU 123", "precio": 3141, "producto_id": p["id"], "repetible": True}
    r = cliente.post("/api/v1/ventas", json={"lineas": [
        {"codigo_balanza": codigo}, {"codigo_balanza": codigo, "cantidad": 2}]})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3141 * 3
    assert _cobrar(cliente, codigo).status_code == 200


def test_dos_jamones_del_mismo_peso_se_pueden_repetir(cliente, caja, carta):
    _formato(cliente)
    _jamon(cliente, carta)
    codigo = _etiqueta(250, 123)
    r = cliente.post("/api/v1/ventas", json={"lineas": [
        {"codigo_balanza": codigo}, {"codigo_balanza": codigo}]})
    assert r.status_code == 200
    assert r.json()["total"] == 4496
    assert _cobrar(cliente, codigo, cantidad=2).json()["total"] == 4496


@pytest.mark.parametrize("extra", [{"precio": 1}, {"producto_id": 1},
                                    {"precio": None}, {"producto_id": None}])
def test_pantalla_no_puede_mandar_precio_ni_producto(cliente, caja, extra):
    assert _cobrar(cliente, _etiqueta(), **extra).status_code == 422


def test_ticket_repetido_en_una_venta_no_guarda_nada(cliente, caja):
    codigo = _etiqueta()
    r = cliente.post("/api/v1/ventas", json={"lineas": [
        {"codigo_balanza": codigo}, {"codigo_balanza": f" {codigo}\n"}]})
    assert r.status_code == 409
    assert "dos veces" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(Venta)).all() == []
    assert _cobrar(cliente, codigo).status_code == 200


def test_ticket_cobrado_avisa_con_hora_y_numero_y_se_libera_al_anular(cliente, caja):
    codigo = _etiqueta()
    v = _cobrar(cliente, codigo).json()
    with Session(engine) as s:
        hora = a_local(s.get(Venta, v["id"]).creada_at).strftime("%H:%M")
    mensaje = (f"El ticket 3976 de la balanza ya se cobró a las {hora}, en la venta "
               f"{v['numero']}. Si hay que cobrarlo de nuevo, anula esa venta primero.")
    vista = _escanear(cliente, codigo)
    assert "balanza" not in vista and vista["problema"] == mensaje
    assert vista["de_balanza"] and not vista["se_puede_guardar"]
    r = _cobrar(cliente, codigo)
    assert r.status_code == 409 and r.json()["detail"] == mensaje
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "Rehacer"}).status_code == 200
    assert "balanza" in _escanear(cliente, codigo)
    assert _cobrar(cliente, codigo).status_code == 200


def test_ticket_exige_cantidad_uno(cliente, caja):
    assert _cobrar(cliente, _etiqueta(), cantidad=2).status_code == 422


def test_ticket_se_recicla_despues_de_24_horas_y_compara_codigo_completo(cliente, caja):
    codigo = _etiqueta()
    v = _cobrar(cliente, codigo).json()
    assert _cobrar(cliente, _etiqueta(198)).status_code == 200
    with Session(engine) as s:
        venta = s.get(Venta, v["id"])
        venta.creada_at = ahora() - timedelta(hours=24, seconds=1)
        s.add(venta)
        s.commit()
    assert "balanza" in _escanear(cliente, codigo)
    assert _cobrar(cliente, codigo).status_code == 200


@pytest.mark.parametrize("modo,valor,kilo,activo,texto", [
    ("plu_peso", 250, 8990, False, "ningún producto"),
    ("plu_peso", 250, 0, True, "precio por kilo"),
    ("plu_peso", 0, 8990, True, "peso 0"),
    ("plu_peso", 1, 1, True, "$0"),
    ("plu_precio", 0, 8990, True, "$0"),
    ("ticket", 0, 8990, True, "$0"),
    ("plu_peso", 999999, 9223372036854775807, True, "$99.000.000"),
])
def test_no_cobrables_dan_el_mismo_problema(cliente, caja, carta, modo, valor, kilo, activo, texto):
    _formato(cliente, modo)
    _jamon(cliente, carta, precio_kilo=kilo, activo=activo)
    codigo = _etiqueta(valor, 123)
    vista = _escanear(cliente, codigo)
    assert "balanza" not in vista
    assert texto in vista["problema"]
    r = _cobrar(cliente, codigo)
    assert r.status_code == 409 and r.json()["detail"] == vista["problema"]


def test_plu_desconocido(cliente, caja):
    _formato(cliente)
    codigo = _etiqueta(250, 123)
    mensaje = ("La balanza mandó el PLU 123 y ningún producto de la carta lo tiene. "
               "Pónselo en la ficha del producto.")
    assert _escanear(cliente, codigo)["problema"] == mensaje
    assert _cobrar(cliente, codigo).json()["detail"] == mensaje


def test_total_impreso_sobre_el_tope(cliente, caja):
    _formato(cliente, "ticket", codigo=[2, 3], valor=[3, 12])
    codigo = _ean("251099000001")
    assert "$99.000.000" in _escanear(cliente, codigo)["problema"]
    assert _cobrar(cliente, codigo).status_code == 409
    assert _cobrar(cliente, _ean("251099000000")).json()["total"] == 99_000_000


def test_verificador_malo_no_se_reconoce(cliente, caja):
    codigo = _etiqueta()
    malo = codigo[:-1] + str((int(codigo[-1]) + 1) % 10)
    assert "balanza" not in _escanear(cliente, malo)
    assert _cobrar(cliente, malo).status_code == 409


def test_formato_y_precio_actuales_mandan_al_cobrar(cliente, caja, carta):
    codigo = _etiqueta(250, 123)
    assert _escanear(cliente, codigo)["balanza"]["modo"] == "ticket"
    p = _jamon(cliente, carta)
    _formato(cliente)
    assert _escanear(cliente, codigo)["balanza"]["precio"] == 2248
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={
        "categoria_id": p["categoria_id"], "nombre": p["nombre"], "precio_kilo": 10000,
    }).status_code == 200
    assert _cobrar(cliente, codigo).json()["total"] == 2500
    _formato(cliente, prefijo="29")
    assert "balanza" not in _escanear(cliente, codigo)
    assert _cobrar(cliente, codigo).status_code == 409


def test_codigo_conocido_se_busca_antes_que_balanza(cliente, carta):
    codigo = _etiqueta()
    with Session(engine) as s:
        s.add(CodigoBarra(codigo=codigo, producto_id=carta["espresso"]["id"]))
        s.commit()
    vista = _escanear(cliente, codigo)
    assert vista["encontrado"] and "balanza" not in vista
    assert vista["producto"]["id"] == carta["espresso"]["id"]


def test_no_topea_ni_descuenta_inventario_y_anular_no_inventa_stock(cliente, caja, carta):
    _formato(cliente)
    p = _jamon(cliente, carta, llevar_cuenta=True, stock_inicial=1)
    with Session(engine) as s:
        i = s.exec(select(Insumo).where(Insumo.producto_id == p["id"])).one()
        i.stock, i.contado = 0, True
        s.add(i)
        s.commit()
        insumo_id = i.id
        movimientos = len(s.exec(select(Movimiento)).all())
    r = _cobrar(cliente, _etiqueta(250, 123), cantidad=2)
    assert r.status_code == 200, r.text
    assert r.json()["inventario"] == []
    assert cliente.post(f"/api/v1/ventas/{r.json()['id']}/anular", json={}).status_code == 200
    with Session(engine) as s:
        assert s.get(Insumo, insumo_id).stock == 0
        assert len(s.exec(select(Movimiento)).all()) == movimientos


def test_resumen_separa_balanza_y_no_reinterpreta_el_pasado(cliente, caja, carta):
    ticket = _cobrar(cliente, _etiqueta()).json()
    _formato(cliente)
    p = _jamon(cliente, carta)
    _cobrar(cliente, _etiqueta(250, 123), cantidad=2)
    cliente.post("/api/v1/ventas", json={"lineas": [{"precio": 700}]})
    resumen = cliente.get("/api/v1/resumen").json()
    assert resumen["varios"]["total"] == 700 and resumen["varios"]["cantidad"] == 1
    por_persona = resumen["balanza"].pop("por_persona")
    assert resumen["balanza"] == {"cantidad": 2, "total": 4693, "tickets": 1}
    assert sum(p["total"] for p in por_persona) == 4693
    nombres = [m["nombre"] for m in resumen["mas_vendidos"]]
    assert "Jamón pierna (balanza)" in nombres and "Balanza" in nombres
    # Borrar el producto suelta producto_id, pero no convierte paquetes en
    # tickets ni cobros a mano. Tampoco debe influir el formato actual.
    assert cliente.delete(f"/api/v1/productos/{p['id']}").status_code == 200
    _formato(cliente, "ticket")
    otra = cliente.get("/api/v1/resumen").json()["balanza"]
    otra.pop("por_persona")
    assert otra == resumen["balanza"]
    cliente.post(f"/api/v1/ventas/{ticket['id']}/anular", json={})
    resumen = cliente.get("/api/v1/resumen").json()
    assert {k: v for k, v in resumen["balanza"].items() if k != "por_persona"} == {
        "cantidad": 1, "total": 4496, "tickets": 0}
    assert resumen["varios"]["total"] == 700


def test_detalle_en_venta_comprobante_y_ultima_columna_csv(cliente, caja, carta):
    _formato(cliente)
    _jamon(cliente, carta)
    v = _cobrar(cliente, _etiqueta(250, 123)).json()
    detalle = "0,250 kg a $8.990/kg"
    assert v["lineas"][0]["detalle"] == detalle
    assert cliente.get(f"/api/v1/ventas/{v['id']}").json()["lineas"][0]["detalle"] == detalle
    assert f"1 x Jamón pierna {detalle}" in cliente.get(f"/comprobante/{v['id']}").text
    filas = list(csv.reader(io.StringIO(cliente.get("/api/v1/exportar/detalle").text.lstrip("\ufeff")), delimiter=";"))
    assert filas[0] == ["Fecha", "Hora", "N° venta", "Producto", "Cantidad", "Precio",
                         "Subtotal", "Medio de pago", "Detalle"]
    assert filas[1][-1] == detalle and filas[1][3] == "Jamón pierna"


@pytest.mark.parametrize("plu", ["123", "00123", "00000123"])
def test_plu_repetido_al_crear_y_editar(cliente, carta, plu):
    _jamon(cliente, carta)
    cuerpo = {"categoria_id": carta["cafe"]["id"], "nombre": "Otro jamón", "plu": plu}
    for r in (cliente.post("/api/v1/productos", json=cuerpo),
              cliente.put(f"/api/v1/productos/{carta['espresso']['id']}", json=cuerpo)):
        assert r.status_code == 409
        assert r.json()["detail"] == "El PLU 123 ya es de «Jamón pierna»."


@pytest.mark.parametrize("plu", ["12a", " 123", "١٢٣", "12.3"])
def test_plu_solo_digitos_ascii(cliente, carta, plu):
    cuerpo = {"categoria_id": carta["cafe"]["id"], "nombre": "Jamón", "plu": plu}
    assert cliente.post("/api/v1/productos", json=cuerpo).status_code == 422
    assert cliente.put(f"/api/v1/productos/{carta['espresso']['id']}", json=cuerpo).status_code == 422


def test_plu_propio_se_conserva_o_se_borra_y_categorias_lo_expone(cliente, carta):
    p = _jamon(cliente, carta)
    cuerpo = {"categoria_id": p["categoria_id"], "nombre": p["nombre"]}
    url = f"/api/v1/productos/{p['id']}"
    assert cliente.put(url, json={**cuerpo, "plu": "123"}).status_code == 200
    assert cliente.put(url, json=cuerpo).json()["plu"] == "123"
    productos = [p for cat in cliente.get("/api/v1/categorias").json() for p in cat["productos"]]
    guardado = next(x for x in productos if x["id"] == p["id"])
    assert guardado["plu"] == "123" and guardado["precio_kilo"] == 8990
    assert cliente.put(url, json={**cuerpo, "plu": ""}).json()["plu"] == ""
    assert cliente.post("/api/v1/productos", json={**cuerpo, "nombre": "Otro", "plu": "123"}).status_code == 200


def test_dos_solicitudes_simultaneas_no_cobran_el_mismo_ticket(cliente, caja):
    salida = Barrier(2)

    def cobrar():
        salida.wait(timeout=10)
        return _cobrar(cliente, _etiqueta()).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: cobrar(), range(2)))
    assert sorted(resultados) == [200, 409]


def test_ticket_no_pide_permiso_de_cobro_a_mano(cliente, caja):
    jefa = cliente.post("/api/v1/usuarios", json={
        "nombre": "Jefa", "pin": "1111", "rol": "dueno"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": jefa["id"], "pin": "1111"})
    cajero = cliente.post("/api/v1/usuarios", json={
        "nombre": "Caja", "pin": "2222", "rol": "cajero", "permisos": "vender"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": cajero["id"], "pin": "2222"})
    assert cliente.post("/api/v1/ventas", json={"lineas": [{"precio": 197}]}).status_code == 403
    assert _cobrar(cliente, _etiqueta()).status_code == 200


def test_plu_inactivo_tambien_se_reserva_al_guardar(cliente, carta):
    _jamon(cliente, carta, activo=False)
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Otro", "plu": "123"})
    assert r.status_code == 409
    assert r.json()["detail"] == "El PLU 123 ya es de «Jamón pierna»."


def test_resumen_vacio_y_codigo_demasiado_largo(cliente, caja):
    assert cliente.get("/api/v1/resumen").json()["balanza"] == {
        "cantidad": 0, "total": 0, "tickets": 0, "por_persona": []}
    assert _cobrar(cliente, "2" * 65).status_code == 422


def test_limite_de_24_horas_es_inclusivo(cliente, caja, monkeypatch):
    from apps.pos import balanza

    instante = ahora()
    monkeypatch.setattr(balanza, "ahora", lambda: instante)
    codigo = _etiqueta()
    v = _cobrar(cliente, codigo).json()
    with Session(engine) as s:
        venta = s.get(Venta, v["id"])
        venta.creada_at = instante - timedelta(hours=24)
        s.add(venta)
        s.commit()
    assert _cobrar(cliente, codigo).status_code == 409
    monkeypatch.setattr(balanza, "ahora", lambda: instante + timedelta(microseconds=1))
    assert _cobrar(cliente, codigo).status_code == 200


def test_migracion_conserva_ventas_anteriores_y_agrega_defaults(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    from apps.pos.db import migraciones
    from apps.pos.db.models import Categoria, Producto, Receta

    anterior = create_engine(f"sqlite:///{tmp_path / 'anterior.db'}")
    monkeypatch.setattr(migraciones, "engine", anterior)
    try:
        with anterior.begin() as con:
            con.execute(text("""CREATE TABLE ventalinea (
                id INTEGER PRIMARY KEY, venta_id INTEGER NOT NULL, producto_id INTEGER,
                nombre TEXT NOT NULL, precio_unitario INTEGER NOT NULL,
                cantidad INTEGER NOT NULL DEFAULT 1, subtotal INTEGER NOT NULL DEFAULT 0)
            """))
            con.execute(text("INSERT INTO ventalinea VALUES (1, 1, NULL, 'Varios', 1500, 2, 3000)"))
        for modelo in (Categoria, Producto, Insumo, Receta):
            modelo.__table__.create(anterior)
        assert set(migraciones.poner_al_dia()) == {
            "ventalinea.detalle", "ventalinea.codigo_balanza", "ventalinea.peso_g", "ventalinea.modo_balanza"}
        with Session(anterior) as s:
            l = s.get(VentaLinea, 1)
            assert (l.nombre, l.precio_unitario, l.cantidad, l.subtotal) == ("Varios", 1500, 2, 3000)
            assert (l.detalle, l.codigo_balanza, l.peso_g, l.modo_balanza) == ("", "", 0, "")
        assert "ix_ventalinea_codigo_balanza" in {i["name"] for i in inspect(anterior).get_indexes("ventalinea")}
        assert migraciones.poner_al_dia() == []
    finally:
        anterior.dispose()


# =============================================================================
# Lo que encontró la revisión adversarial (2.26)
# =============================================================================

def test_si_el_precio_cambio_desde_que_se_escaneo_no_se_cobra_otro_en_silencio(cliente, caja, carta):
    """El cajero cobró en la máquina $4.495 porque eso decía la pantalla; si el dueño
    subió el precio por kilo entremedio, registrar $9.495 le cargaba el descuadre."""
    _formato(cliente)
    p = _jamon(cliente, carta)
    codigo = _etiqueta(500, 123)
    visto = _escanear(cliente, codigo)["balanza"]["precio"]
    assert visto == 4495
    r = cliente.put(f"/api/v1/productos/{p['id']}", json={**p, "precio_kilo": 18990})
    assert r.status_code == 200, r.text
    r = _cobrar(cliente, codigo, precio_visto=visto)
    assert r.status_code == 409
    assert "$9.495" in r.json()["detail"] and "$4.495" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(Venta)).all() == []
    # Con lo que dice ahora, sí.
    assert _cobrar(cliente, codigo, precio_visto=9495).status_code == 200


def test_precio_visto_no_va_sin_etiqueta(cliente, caja, carta):
    r = cliente.post("/api/v1/ventas", json={"lineas": [
        {"producto_id": carta["espresso"]["id"], "precio_visto": 1}]})
    assert r.status_code == 422


def test_formato_guardado_roto_no_cobra_con_el_de_fabrica(cliente, caja, carta):
    """Antes caía al DIGI de fábrica: 250 g de jamón ($2.248) se cobraban como el
    «ticket 123» por $250."""
    from apps.pos.db.models import Ajuste
    _formato(cliente)
    _jamon(cliente, carta)
    codigo = _etiqueta(250, 123)
    assert _escanear(cliente, codigo)["balanza"]["precio"] == 2248
    with Session(engine) as s:
        fila = s.get(Ajuste, "formato_balanza")
        fila.valor = fila.valor.replace('"divisor_peso": 1000', '"divisor_peso": 0')
        s.add(fila)
        s.commit()
    ajustes = cliente.get("/api/v1/ajustes").json()
    assert ajustes["formato_balanza_roto"] is True
    vista = _escanear(cliente, codigo)
    assert "balanza" not in vista and "no se entiende" in vista["problema"]
    r = _cobrar(cliente, codigo)
    assert r.status_code == 409 and "no se entiende" in r.json()["detail"]


def test_formato_nunca_guardado_no_esta_roto(cliente):
    assert cliente.get("/api/v1/ajustes").json()["formato_balanza_roto"] is False


@pytest.mark.parametrize("prefijo", ["780", "1", "02"])
def test_el_prefijo_tiene_que_ser_de_balanza(cliente, prefijo):
    """Con 780 —el de Chile— los productos de verdad se cobraban como tickets."""
    r = cliente.put("/api/v1/ajustes", json={"formato_balanza": {
        "modo": "ticket", "prefijo": prefijo, "codigo": [3, 7], "valor": [7, 12],
        "divisor_peso": 1000}})
    assert r.status_code == 422


def test_un_codigo_de_la_carta_no_se_cobra_como_etiqueta(cliente, caja, carta):
    from apps.pos.db.models import CodigoBarra
    codigo = _etiqueta(3400, 1)
    with Session(engine) as s:
        s.add(CodigoBarra(codigo=codigo, producto_id=carta["latte"]["id"], cuantos=1))
        s.commit()
    assert _cobrar(cliente, codigo).status_code == 409


def test_un_producto_por_kilo_no_se_vende_tocandolo_a_cero(cliente, caja, carta):
    p = _jamon(cliente, carta, precio=0)
    r = cliente.post("/api/v1/ventas", json={"lineas": [{"producto_id": p["id"]}]})
    assert r.status_code == 409 and "se vende por peso" in r.json()["detail"]
    # Y en el televisor no sale a $0: sale su precio por kilo, rotulado.
    carta_tv = cliente.get("/api/v1/carta").json()
    jamon = next(x for c in carta_tv["categorias"] for x in
                 c["productos"] + ([c["destacado"]] if c.get("destacado") else [])
                 if x["nombre"] == "Jamón pierna")
    assert jamon["precio"] == 8990 and jamon["etiqueta"] == "Por kilo"


def test_con_precio_por_unidad_si_se_vende_tocandolo(cliente, caja, carta):
    p = _jamon(cliente, carta)            # precio 900 y precio_kilo 8990
    r = cliente.post("/api/v1/ventas", json={"lineas": [{"producto_id": p["id"]}]})
    assert r.status_code == 200 and r.json()["total"] == 900


def test_balanza_apagada_explica_que_hacer(cliente, caja):
    cliente.put("/api/v1/ajustes", json={"usar_balanza": 0})
    codigo = _etiqueta()
    assert "Ayuda → Ajustes" in _escanear(cliente, codigo)["problema"]
    r = _cobrar(cliente, codigo)
    assert r.status_code == 409 and "apagada" in r.json()["detail"]
