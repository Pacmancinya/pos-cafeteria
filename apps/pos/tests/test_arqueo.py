"""Arqueo de caja: contar por denominación.

Reemplaza a la planilla de Excel que usaban. Las diferencias que importan:
el total lo saca el programa (no una fórmula que alguien puede pisar) y lo que
DEBERÍA haber lo sabe la caja, no se escribe a mano.
"""
import pytest

from core.config import DENOMINACIONES, total_del_conteo


# ------------------------------------------------------------------ el conteo
def test_las_denominaciones_son_las_chilenas():
    assert DENOMINACIONES == (20000, 10000, 5000, 2000, 1000, 500, 100, 50, 10)


@pytest.mark.parametrize("conteo,total", [
    ({}, 0),
    ({"20000": 2}, 40000),
    ({"1000": 4, "500": 3}, 5500),
    ({"20000": 1, "10000": 1, "5000": 1, "2000": 1, "1000": 1,
      "500": 1, "100": 1, "50": 1, "10": 1}, 38660),
])
def test_suma_del_conteo(conteo, total):
    assert total_del_conteo(conteo) == total


def test_el_conteo_ignora_lo_que_no_es_plata_chilena():
    """Un 7 no existe como billete: no puede sumar."""
    assert total_del_conteo({"20000": 1, "7": 99, "abc": 3, "500": -4}) == 20000


# ------------------------------------------------------------------ apertura
def test_abrir_contando_el_fondo(cliente):
    t = cliente.post("/api/v1/turnos/abrir", json={
        "cajero": "Javi", "conteo": {"10000": 1, "1000": 4, "500": 6}}).json()
    assert t["monto_inicial"] == 17000
    assert t["conteo_apertura"] == {"10000": 1, "1000": 4, "500": 6}


def test_el_conteo_manda_sobre_el_monto_escrito(cliente):
    """Si alguien escribe 50.000 pero cuenta 17.000, vale lo contado."""
    t = cliente.post("/api/v1/turnos/abrir", json={
        "cajero": "Javi", "monto_inicial": 50000,
        "conteo": {"10000": 1, "1000": 4, "500": 6}}).json()
    assert t["monto_inicial"] == 17000


def test_se_puede_abrir_sin_fondo(cliente):
    t = cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi"}).json()
    assert t["monto_inicial"] == 0


# ------------------------------------------------------------------ cierre
def _turno_con_ventas(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={
        "cajero": "Javi", "conteo": {"10000": 1, "1000": 4, "500": 6}})   # 17.000
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})                                        # +3.400
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "debito"})                                          # no va al cajón
    return 17000 + 3400


def test_cuadra_cuando_el_conteo_calza(cliente, carta):
    esperado = _turno_con_ventas(cliente, carta)
    assert cliente.get("/api/v1/turnos/actual").json()["turno"]["efectivo_esperado"] == esperado
    # 2 x 10.000 + 400 en monedas = 20.400
    r = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 2, "100": 4}}).json()
    assert r["efectivo_contado"] == 20400
    assert r["diferencia"] == 0


def test_el_faltante_queda_guardado_con_su_detalle(cliente, carta):
    _turno_con_ventas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 2},                     # 20.000: faltan 400
        "nota": "le di mal el vuelto a alguien"}).json()
    assert r["diferencia"] == -400
    assert r["conteo_cierre"] == {"10000": 2}       # se puede revisar DÓNDE faltó
    assert r["nota"]


def test_lo_que_sobra_tambien_se_guarda(cliente, carta):
    _turno_con_ventas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={"conteo": {"10000": 2, "1000": 1}}).json()
    assert r["diferencia"] == 600


def test_el_fondo_de_manana_y_el_retiro(cliente, carta):
    _turno_con_ventas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 2, "100": 4}, "fondo_siguiente": 15000}).json()
    assert r["fondo_siguiente"] == 15000
    assert r["retiro"] == 20400 - 15000


def test_no_se_puede_dejar_de_fondo_mas_de_lo_que_hay(cliente, carta):
    _turno_con_ventas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 2, "100": 4}, "fondo_siguiente": 999999}).json()
    assert r["fondo_siguiente"] == 20400
    assert r["retiro"] == 0


def test_sin_conteo_todavia_se_puede_escribir_el_total(cliente, carta):
    """Compatibilidad: si alguien manda solo el número, sigue funcionando."""
    esperado = _turno_con_ventas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": esperado}).json()
    assert r["diferencia"] == 0


def test_el_turno_informa_lo_vendido_por_medio_de_pago(cliente, carta):
    """La tarjeta no se cuenta a mano: en la planilla vieja sí, y eso era un
    error gratis esperando a pasar."""
    _turno_con_ventas(cliente, carta)
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["por_medio"]["efectivo"]["total"] == 3400
    assert t["por_medio"]["debito"]["total"] == 3400
    assert t["ventas_efectivo"] == 3400


def test_el_cierre_impreso_trae_el_arqueo(cliente, carta):
    _turno_con_ventas(cliente, carta)
    t = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 2, "100": 4}, "fondo_siguiente": 15000}).json()
    html = cliente.get(f"/cierre/{t['id']}").text
    assert "ARQUEO DEL CAJON" in html
    assert "$10.000 x 2" in html
    assert "$100 x 4" in html
    assert "Queda de fondo" in html and "Se retira" in html


def test_las_denominaciones_se_pueden_pedir(cliente):
    assert cliente.get("/api/v1/turnos/denominaciones").json()["denominaciones"][0] == 20000


# =========================================================================
# Lo que NO es efectivo
# =========================================================================
# El efectivo se cuenta; las tarjetas se copian del comprobante de cierre de la
# máquina. Son dos cuadres distintos y el segundo no existía.
def _turno_con_tarjetas(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi", "conteo": {"10000": 1}})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "propina": 500})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}],
        "medio_pago": "debito", "propina": 1000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["alfajor"]["id"], "cantidad": 1}],
        "medio_pago": "transferencia"})


def test_lo_esperado_de_la_tarjeta_incluye_la_propina(cliente, carta):
    """La máquina le cobró al cliente el total CON propina. Compararlo contra lo
    vendido a secas daría una diferencia falsa todos los días, exactamente del
    tamaño de las propinas."""
    _turno_con_tarjetas(cliente, carta)
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    debito = [m for m in t["medios"] if m["medio"] == "debito"][0]
    assert debito["ventas"] == 6800            # 2 lattes
    assert debito["propinas"] == 1000
    assert debito["esperado"] == 7800          # esto es lo que cobró la máquina


def test_el_efectivo_no_aparece_en_el_cuadre_de_tarjetas(cliente, carta):
    _turno_con_tarjetas(cliente, carta)
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert "efectivo" not in [m["medio"] for m in t["medios"]]


def test_sin_escribir_lo_del_banco_no_se_inventa_un_cuadre(cliente, carta):
    _turno_con_tarjetas(cliente, carta)
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert all(m["declarado"] is None and m["diferencia"] is None for m in t["medios"])


def test_el_descuadre_de_la_tarjeta_queda_guardado(cliente, carta):
    _turno_con_tarjetas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 1, "1000": 4},
        "medios": {"debito": 7500, "transferencia": 1900}}).json()
    porque = {m["medio"]: m for m in r["medios"]}
    assert porque["debito"]["declarado"] == 7500
    assert porque["debito"]["diferencia"] == -300      # faltan $300 en la máquina
    assert porque["transferencia"]["diferencia"] == 0


def test_cerrar_sin_escribir_las_tarjetas_sigue_funcionando(cliente, carta):
    """Es opcional a propósito: nadie se puede quedar sin cerrar la caja porque
    no encuentra el comprobante de la máquina."""
    _turno_con_tarjetas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={"conteo": {"10000": 1}})
    assert r.status_code == 200
    assert all(m["declarado"] is None for m in r.json()["medios"])


def test_un_medio_inventado_no_entra(cliente, carta):
    _turno_con_tarjetas(cliente, carta)
    r = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 1}, "medios": {"bitcoin": 999, "debito": 7800}}).json()
    assert [m["medio"] for m in r["medios"] if m["declarado"] is not None] == ["debito"]


def test_las_propinas_se_separan_por_forma_de_pago(cliente, carta):
    """La de efectivo ya está en el cajón; la de tarjeta la depositó el banco y
    hay que pagársela al equipo aparte. Sin separarlas, o se reparte dos veces
    o no se reparte nunca."""
    _turno_con_tarjetas(cliente, carta)
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["propinas"] == {"efectivo": 500, "tarjeta": 1000, "total": 1500}


def test_la_propina_en_efectivo_sigue_estando_en_el_cajon(cliente, carta):
    """La propina de tarjeta NO puede sumar al efectivo esperado: no está ahí."""
    _turno_con_tarjetas(cliente, carta)
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    # fondo 10.000 + latte 3.400 + propina 500 = 13.900
    assert t["efectivo_esperado"] == 13900


def test_el_cierre_impreso_trae_las_tarjetas_y_las_propinas(cliente, carta):
    _turno_con_tarjetas(cliente, carta)
    t = cliente.post("/api/v1/turnos/cerrar", json={
        "conteo": {"10000": 1, "1000": 3, "500": 1, "100": 4},
        "medios": {"debito": 7800}}).json()
    html = cliente.get(f"/cierre/{t['id']}").text
    assert "TARJETAS Y TRANSFERENCIAS" in html
    assert "segun el banco" in html
    assert "PROPINAS" in html
    assert "Por tarjeta" in html
