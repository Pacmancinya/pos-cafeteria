"""Cobrar un monto a mano: la única línea cuyo precio no sale de la carta.

El dueño lo pidió porque en el local que viene «lo usan mucho»: en un mostrador siempre
aparece algo que no está en la carta. Y es, justamente por eso, la única línea por la que
alguien podría cobrar de más sin que se note después.

No se prohíbe: se pide permiso, queda firmada con quién la hizo y se ve sumada en el día.
Es el mismo criterio que ya usaba sacar plata del cajón — lo que la hace honesta no es un
permiso que se le quite a alguien, sino que quede escrito.
"""

from __future__ import annotations

import pytest


def _cobrar(cliente, lineas, medio="efectivo"):
    return cliente.post("/api/v1/ventas", json={"lineas": lineas, "medio_pago": medio})


# =============================================================================
# Cobrar a mano
# =============================================================================

def test_se_puede_cobrar_un_monto_a_mano(cliente, caja):
    r = _cobrar(cliente, [{"nombre": "Torta encargada", "precio": 12500}])
    assert r.status_code == 200
    v = r.json()
    assert v["total"] == 12500
    linea = v["lineas"][0]
    assert linea["nombre"] == "Torta encargada" and linea["precio_unitario"] == 12500


def test_sin_nombre_queda_como_varios(cliente, caja):
    v = _cobrar(cliente, [{"precio": 3000}]).json()
    assert v["lineas"][0]["nombre"] == "Varios"


def test_se_mezcla_con_productos_de_la_carta(cliente, caja, carta):
    """Es el caso real: un café de la carta y algo que no está."""
    v = _cobrar(cliente, [
        {"producto_id": carta["espresso"]["id"], "cantidad": 1},
        {"nombre": "Encargo", "precio": 5000},
    ]).json()
    assert len(v["lineas"]) == 2
    assert v["total"] == carta["espresso"]["precio"] + 5000


def test_cantidad_mayor_a_uno_multiplica(cliente, caja):
    v = _cobrar(cliente, [{"nombre": "Empanada", "precio": 2500, "cantidad": 3}]).json()
    assert v["total"] == 7500


def test_una_linea_sin_producto_y_sin_monto_se_rechaza(cliente, caja):
    """O es un producto de la carta, o es un monto. Sin ninguno no es nada."""
    assert _cobrar(cliente, [{"cantidad": 1}]).status_code == 422


def test_un_monto_absurdo_se_rechaza(cliente, caja):
    assert _cobrar(cliente, [{"nombre": "x", "precio": 999_000_000}]).status_code == 422
    assert _cobrar(cliente, [{"nombre": "x", "precio": -100}]).status_code == 422


def test_no_toca_el_inventario(cliente, caja):
    """Un cobro a mano no es ningún producto, así que no puede descontar stock de nada."""
    r = _cobrar(cliente, [{"nombre": "Lo que sea", "precio": 1000}])
    assert r.status_code == 200
    assert r.json()["lineas"][0].get("producto_id") in (None, 0)


# =============================================================================
# El permiso
# =============================================================================

def test_quien_no_tiene_el_permiso_no_puede(cliente, caja, carta):
    """Se le puede quitar a UNA persona sin quitárselo a todo el local."""
    duenno = cliente.post("/api/v1/usuarios",
                          json={"nombre": "Jefa", "pin": "1111", "rol": "dueno"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": duenno["id"], "pin": "1111"})
    solo_vende = cliente.post("/api/v1/usuarios", json={
        "nombre": "Javi", "pin": "2222", "rol": "cajero",
        "permisos": "vender,turno_abrir,turno_cerrar"}).json()

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": solo_vende["id"], "pin": "2222"})
    r = _cobrar(cliente, [{"nombre": "Algo", "precio": 1000}])
    assert r.status_code == 403
    assert "a mano" in r.json()["detail"]
    # Pero de la carta SÍ puede vender: lo que se le quitó es solo el cobro a mano.
    assert _cobrar(cliente, [
        {"producto_id": carta["espresso"]["id"], "cantidad": 1}]).status_code == 200


def test_viene_dado_por_defecto(cliente, caja):
    """Es una función normal de mostrador: quitársela a todos de golpe rompería locales."""
    from core.config import PERMISOS
    assert "cobrar_varios" in PERMISOS["cajero"] and "cobrar_varios" in PERMISOS["dueno"]


# =============================================================================
# Que se vea: es lo que lo hace honesto
# =============================================================================

def test_los_cobros_a_mano_salen_aparte_en_el_dia(cliente, caja, carta):
    _cobrar(cliente, [{"producto_id": carta["espresso"]["id"], "cantidad": 1}])
    _cobrar(cliente, [{"nombre": "Encargo", "precio": 5000}])
    _cobrar(cliente, [{"nombre": "Otro", "precio": 2000, "cantidad": 2}])

    d = cliente.get("/api/v1/resumen").json()["varios"]
    assert d["cantidad"] == 2
    assert d["total"] == 9000            # 5.000 + 2 x 2.000
    assert d["por_persona"][0]["total"] == 9000
    assert d["por_persona"][0]["nombre"]  # con nombre, no anónimo


def test_un_dia_sin_cobros_a_mano_no_muestra_nada(cliente, caja, carta):
    _cobrar(cliente, [{"producto_id": carta["espresso"]["id"], "cantidad": 1}])
    assert cliente.get("/api/v1/resumen").json()["varios"] == {
        "cantidad": 0, "total": 0, "por_persona": []}


def test_una_venta_anulada_no_cuenta(cliente, caja):
    v = _cobrar(cliente, [{"nombre": "Encargo", "precio": 5000}]).json()
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "se arrepintió"})
    assert cliente.get("/api/v1/resumen").json()["varios"]["cantidad"] == 0
