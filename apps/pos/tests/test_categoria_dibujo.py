"""El ícono de cada categoría en la columna de la caja es editable.

`dibujo` vacío = automático (el que más se repite entre sus productos), como antes.
"""
from sqlalchemy import create_engine, inspect, text
from sqlmodel import Session

from apps.pos.db import migraciones
from apps.pos.db.models import Categoria, Insumo, Producto, Receta

API = "/api/v1/categorias"


def test_una_base_vieja_gana_las_columnas_sin_perder_la_categoria(tmp_path, monkeypatch):
    viejo = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    monkeypatch.setattr(migraciones, "engine", viejo)
    try:
        with viejo.begin() as con:
            con.execute(text("""CREATE TABLE categoria (
                id INTEGER PRIMARY KEY, nombre VARCHAR NOT NULL,
                orden INTEGER NOT NULL DEFAULT 0, activa BOOLEAN NOT NULL DEFAULT 1)"""))
            con.execute(text("INSERT INTO categoria VALUES (1, 'Panadería', 3, 1)"))
        for tabla in (Producto.__table__, Insumo.__table__, Receta.__table__):
            tabla.create(viejo)      # las que la migración consulta; categoría sigue siendo la vieja
        hechos = migraciones.poner_al_dia()
        assert {"categoria.dibujo", "categoria.color"} <= set(hechos)
        with Session(viejo) as s:
            c = s.get(Categoria, 1)
            assert (c.nombre, c.orden, c.activa) == ("Panadería", 3, True)
            assert (c.dibujo, c.color) == ("", "")      # sigue en automático
        assert {"dibujo", "color"} <= {x["name"] for x in inspect(viejo).get_columns("categoria")}
    finally:
        viejo.dispose()


def test_se_guarda_y_se_devuelve_el_dibujo(cliente):
    c = cliente.post(API, json={"nombre": "Panes"}).json()
    assert c["dibujo"] == "" and c["color"] == ""
    r = cliente.put(f"{API}/{c['id']}", json={"nombre": "Panes", "dibujo": "pan-baguette"})
    assert r.status_code == 200
    lista = {x["id"]: x for x in cliente.get(API).json()}
    assert lista[c["id"]]["dibujo"] == "pan-baguette"


def test_editar_solo_el_nombre_no_borra_el_dibujo(cliente):
    c = cliente.post(API, json={"nombre": "Panes", "dibujo": "croissant"}).json()
    cliente.put(f"{API}/{c['id']}", json={"nombre": "Masas", "orden": 2, "activa": True})
    lista = {x["id"]: x for x in cliente.get(API).json()}
    assert lista[c["id"]]["nombre"] == "Masas"
    assert lista[c["id"]]["dibujo"] == "croissant"


def test_vacio_vuelve_al_automatico_y_suelta_el_color(cliente):
    c = cliente.post(API, json={"nombre": "Cafés en grano"}).json()
    cliente.put(f"{API}/{c['id']}", json={"nombre": "Cafés en grano", "dibujo": "bolsa-cafe", "color": "#A8382F"})
    x = {y["id"]: y for y in cliente.get(API).json()}[c["id"]]
    assert (x["dibujo"], x["color"]) == ("bolsa-cafe", "#A8382F")
    cliente.put(f"{API}/{c['id']}", json={"nombre": "Cafés en grano", "dibujo": ""})
    x = {y["id"]: y for y in cliente.get(API).json()}[c["id"]]
    assert (x["dibujo"], x["color"]) == ("", "")


def test_un_dibujo_que_no_existe_se_rechaza(cliente):
    c = cliente.post(API, json={"nombre": "Panes"}).json()
    for malo in ("no-existe", "../x", "MUG", "<script>"):
        r = cliente.put(f"{API}/{c['id']}", json={"nombre": "Panes", "dibujo": malo})
        assert r.status_code == 422, malo
    assert cliente.post(API, json={"nombre": "Otra", "dibujo": "no-existe"}).status_code == 422
    assert cliente.put(f"{API}/{c['id']}", json={"nombre": "Panes", "dibujo": "mug", "color": "rojo"}).status_code == 422


def test_todos_los_dibujos_del_selector_son_validos(cliente):
    from apps.pos.api.catalogo import _dibujos_validos
    validos = _dibujos_validos()
    assert {"mug", "plato", "bolsa-cafe", "cerveza-lata", "pan-baguette"} <= validos
    assert len(validos) > 80


def test_un_cajero_no_puede_cambiar_el_icono(cliente):
    c = cliente.post(API, json={"nombre": "Panes"}).json()
    ana = cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": ana["id"], "pin": "1234"})
    javi = cliente.post("/api/v1/usuarios", json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    r = cliente.put(f"{API}/{c['id']}", json={"nombre": "Panes", "dibujo": "croissant"})
    assert r.status_code == 403
