"""«Avanzado»: sacar el precio desde el costo, y con cuántos se empieza.

El dueño lo pidió después de que crear un producto pasara a abrir la ficha
completa: ahí se perdió el ayudante de precios, que hasta entonces vivía solo en
el formulario corto de escanear un código. Vuelve como un recuadro plegado —él
insistió en que fuera «una opción avanzada»— con tres cosas: cuánto te cuesta, si
ese precio ya trae IVA, y qué cobrar según lo que quieras ganar.

## Qué se guarda y qué no

El costo NO es una columna del producto y no se inventó una. La cuenta del
precio vive en el navegador y se recalcula con cada tecla; lo único que llega a
la base es el precio que la persona decidió.

La excepción es el producto que lleva su cuenta: ese SÍ tiene dónde guardar un
costo —su insumo, el mismo que la Bodega usa para valorizar lo que queda— y
entonces se guarda ahí. Escribirlo en la ficha es lo que evita crear el producto,
cerrarlo, entrar a la Bodega y escribir lo mismo de nuevo.

## La cantidad inicial

Se pregunta UNA vez: cuando se empieza a contar algo que no se contaba. El libro
de movimientos es la prueba de que es la primera vez — si el insumo ya tiene
historia, su saldo es real y una carga encima lo dejaría contando de más.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session, select

from apps.pos.db.models import Insumo, Movimiento
from apps.pos.db.session import engine

ESTATICOS = Path(__file__).resolve().parents[1] / "static"


# =============================================================================
# La pantalla
# =============================================================================

def test_la_pantalla_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    r = subprocess.run([node, str(Path(__file__).with_name("avanzado_ui.cjs"))],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_iva_de_la_pantalla_es_el_del_servidor():
    """Dos 19% en dos archivos distintos son un 19% y un futuro 18% olvidado."""
    from core.config import IVA

    js = (ESTATICOS / "app.js").read_text(encoding="utf-8")
    assert f"const IVA = {IVA};" in js


# =============================================================================
# El costo, cuando el producto tiene dónde guardarlo
# =============================================================================

def _insumo_de(producto_id: int):
    with Session(engine) as s:
        return s.exec(select(Insumo).where(Insumo.producto_id == producto_id)).first()


def _libro(insumo_id: int):
    with Session(engine) as s:
        return s.exec(select(Movimiento).where(
            Movimiento.insumo_id == insumo_id).order_by(Movimiento.id)).all()


def _crear(cliente, carta, **extra):
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["dulce"]["id"], "nombre": "Coca lata",
        "precio": 1500, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_al_crear_con_cuenta_el_costo_y_la_cantidad_llegan_a_la_bodega(cliente, carta):
    p = _crear(cliente, carta, llevar_cuenta=True, costo=900, stock_inicial=24)
    i = _insumo_de(p["id"])
    assert i.compra_costo == 900
    assert i.stock == 24
    mov, = _libro(i.id)
    assert mov.tipo == "carga" and mov.cantidad == 24
    assert mov.saldo_despues == 24


def test_sin_cuenta_el_costo_no_crea_nada(cliente, carta):
    """Es una calculadora: si no hay dónde guardarlo, no se guarda y ya está."""
    p = _crear(cliente, carta, costo=900, stock_inicial=24)
    assert _insumo_de(p["id"]) is None
    assert cliente.get("/api/v1/bodega").json()["insumos"] == []


def test_editar_actualiza_el_costo_sin_tocar_el_saldo(cliente, carta):
    p = _crear(cliente, carta, llevar_cuenta=True, costo=900, stock_inicial=24)
    r = cliente.put(f"/api/v1/productos/{p['id']}", json={**p, "costo": 1100})
    assert r.status_code == 200, r.text
    i = _insumo_de(p["id"])
    assert i.compra_costo == 1100
    assert i.stock == 24, "cambiar el costo no es contar"
    assert len(_libro(i.id)) == 1


def test_guardar_de_nuevo_no_vuelve_a_cargar(cliente, carta):
    """El bug que esto impide: entrar a corregir el precio y que suba el stock."""
    p = _crear(cliente, carta, llevar_cuenta=True, costo=900, stock_inicial=24)
    for _ in range(3):
        cliente.put(f"/api/v1/productos/{p['id']}",
                    json={**p, "costo": 900, "stock_inicial": 24})
    i = _insumo_de(p["id"])
    assert i.stock == 24
    assert len(_libro(i.id)) == 1


def test_empezar_a_contar_uno_que_ya_existia(cliente, carta):
    """Marcar la casilla en un producto viejo: se crea el insumo y se carga."""
    p = _crear(cliente, carta)
    assert _insumo_de(p["id"]) is None
    r = cliente.put(f"/api/v1/productos/{p['id']}", json={
        **p, "llevar_cuenta": True, "costo": 700, "stock_inicial": 6})
    assert r.status_code == 200, r.text
    i = _insumo_de(p["id"])
    assert (i.compra_costo, i.stock) == (700, 6)
    assert [m.tipo for m in _libro(i.id)] == ["carga"]


def test_no_carga_encima_de_un_saldo_que_ya_se_contó(cliente, carta):
    """Apagar y volver a prender la cuenta no puede duplicar lo que hay."""
    p = _crear(cliente, carta, llevar_cuenta=True, stock_inicial=10)
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, "llevar_cuenta": False})
    cliente.put(f"/api/v1/productos/{p['id']}", json={
        **p, "llevar_cuenta": True, "stock_inicial": 10})
    i = _insumo_de(p["id"])
    assert i.stock == 10
    assert len(_libro(i.id)) == 1


def test_un_producto_con_receta_de_verdad_no_acepta_un_costo(cliente, carta):
    """Un capuchino no tiene costo propio: tiene leche y café. Se ignora, no falla."""
    leche = cliente.post("/api/v1/inventario/insumos", json={
        "nombre": "Leche", "unidad": "ml", "formato": "Caja 1 L",
        "compra_contenido": 1000, "compra_costo": 1200}).json()
    cliente.put(f"/api/v1/productos/{carta['latte']['id']}/receta", json={
        "lineas": [{"insumo_id": leche["id"], "cantidad": 200}]})

    r = cliente.put(f"/api/v1/productos/{carta['latte']['id']}", json={
        **carta["latte"], "costo": 5000, "stock_inicial": 99})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(Insumo, leche["id"]).compra_costo == 1200
        assert s.get(Insumo, leche["id"]).stock == 0


# =============================================================================
# Que el número que llega sea el que se escribió
# =============================================================================

@pytest.mark.parametrize("costo", [0, -1, 10**12])
def test_un_costo_imposible_se_rechaza_o_se_ignora(cliente, carta, costo):
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["dulce"]["id"], "nombre": f"Raro {costo}",
        "precio": 1000, "llevar_cuenta": True, "costo": costo})
    if costo < 0:
        assert r.status_code == 422
        return
    assert r.status_code == 200, r.text
    i = _insumo_de(r.json()["id"])
    assert i.compra_costo == (costo if costo > 0 else 0)
