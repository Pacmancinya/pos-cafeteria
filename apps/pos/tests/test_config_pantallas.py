"""Config → Pantallas del local: los televisores con nombre y los textos de las pantallas.

Lo importante es que NADA cambie para un televisor que ya está colgado: las direcciones de
siempre (`?p=1`, `?p=2`, `?tv=1`, `/pantallas/simple`) siguen sirviendo la misma página, y sin
nada guardado el televisor se queda con lo suyo.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from apps.pos import pantallas
from apps.pos.main import app


def _tv(cliente, **extra):
    r = cliente.post("/api/v1/config/televisores", json={"nombre": "TV de la vitrina", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_un_televisor_nuevo_parte_con_lo_de_siempre(cliente):
    tv = _tv(cliente)
    assert tv["id"] == 1 and tv["nombre"] == "TV de la vitrina"
    assert tv["modo"] == "turnar" and tv["orient"] == "horizontal"
    assert tv["t"] == {"vitrina": 20, "cat": 14, "reco": 12}        # los tiempos que ya traía la pantalla
    assert tv["fiestas"] == "auto" and tv["suave"] is False
    assert tv["margen"] == 0 and tv["simple"] is False
    assert tv["visto_hace_s"] is None


def test_la_direccion_de_siempre_sigue_sirviendo_la_misma_pagina(cliente):
    for ruta in ("/pantallas?p=1", "/pantallas?p=2", "/pantallas?tv=1", "/pantallas?p=1&t=3",
                 "/pantallas/simple", "/pantallas/simple?t=3"):
        assert cliente.get(ruta).status_code == 200, ruta


def test_el_televisor_lee_su_config_sin_pin_desde_otro_equipo(cliente):
    tv = _tv(cliente, nombre="TV de la carta", modo="menu", orient="vertical")
    cliente.put("/api/v1/config/pantallas", json={"kicker": "Café del Barrio"})
    with TestClient(app, client=("192.168.1.50", 5000)) as tele:
        # Sin PIN de red, como la carta: un televisor no tiene teclado.
        r = tele.get(f"/api/v1/pantallas/config?t={tv['id']}")
        assert r.status_code == 200
        out = r.json()
        assert out["tv"]["modo"] == "menu" and out["tv"]["orient"] == "vertical"
        assert out["textos"] == {"kicker": "Café del Barrio"}, "lo que no se escribió no pisa nada"
        # Pero cambiar algo sí pide PIN/sesión.
        assert tele.put("/api/v1/config/pantallas", json={"kicker": "Hackeado"}).status_code == 401
        assert tele.post("/api/v1/config/televisores", json={"nombre": "X"}).status_code == 401


def test_sin_numero_o_con_uno_que_ya_no_existe_solo_vienen_los_textos(cliente):
    cliente.put("/api/v1/config/pantallas", json={"pieSug": "Pídelo en la barra"})
    for q in ("", "?t=999"):
        out = cliente.get("/api/v1/pantallas/config" + q).json()
        assert out["tv"] is None and out["textos"] == {"pieSug": "Pídelo en la barra"}
    assert cliente.get("/api/v1/pantallas/config?t=abc").status_code == 422


def test_visto_hace_se_anota_al_pedir_la_config_o_la_carta(cliente):
    tv = _tv(cliente)
    assert cliente.get("/api/v1/config/televisores").json()["televisores"][0]["visto_hace_s"] is None
    cliente.get(f"/api/v1/carta?t={tv['id']}")
    visto = cliente.get("/api/v1/config/televisores").json()["televisores"][0]["visto_hace_s"]
    assert visto is not None and visto < 5
    otro = _tv(cliente, nombre="Otro")
    cliente.get(f"/api/v1/pantallas/config?t={otro['id']}")
    assert cliente.get("/api/v1/config/televisores").json()["televisores"][1]["visto_hace_s"] is not None
    # Un número inventado no ensucia nada.
    cliente.get("/api/v1/carta?t=777")
    assert pantallas.visto_hace(777) is None


def test_cambiar_un_televisor_solo_cambia_lo_que_viene(cliente):
    tv = _tv(cliente, orient="vertical", margen=3)
    r = cliente.put(f"/api/v1/config/televisores/{tv['id']}", json={"nombre": "TV nueva", "t": {"reco": 40}})
    assert r.status_code == 200
    out = r.json()
    assert out["nombre"] == "TV nueva" and out["orient"] == "vertical" and out["margen"] == 3
    assert out["t"] == {"vitrina": 20, "cat": 14, "reco": 40}
    assert cliente.put("/api/v1/config/televisores/99", json={"nombre": "x"}).status_code == 404


@pytest.mark.parametrize("malo", [
    {"nombre": ""}, {"nombre": "x" * 31}, {"modo": "todo"}, {"orient": "diagonal"},
    {"fiestas": "a veces"}, {"margen": 16}, {"margen": -1},
    {"t": {"vitrina": 4, "cat": 14, "reco": 12}}, {"t": {"vitrina": 20, "cat": 181, "reco": 12}},
])
def test_el_servidor_rechaza_un_televisor_que_no_sirve(cliente, malo):
    cuerpo = {"nombre": "TV", **malo}
    assert cliente.post("/api/v1/config/televisores", json=cuerpo).status_code == 422
    assert cliente.get("/api/v1/config/televisores").json()["televisores"] == []


def test_quitar_un_televisor_no_reusa_su_numero(cliente):
    a = _tv(cliente, nombre="A")
    b = _tv(cliente, nombre="B")
    assert cliente.delete(f"/api/v1/config/televisores/{a['id']}").status_code == 200
    assert cliente.delete(f"/api/v1/config/televisores/{a['id']}").status_code == 404
    c = _tv(cliente, nombre="C")
    assert c["id"] == b["id"] + 1, "un televisor viejo con t=1 no puede heredar al nuevo"
    assert [t["nombre"] for t in cliente.get("/api/v1/config/televisores").json()["televisores"]] == ["B", "C"]


def test_los_textos_se_limpian_y_los_avisos_alimentan_la_carta(cliente):
    # Sin nada escrito, la carta lleva los avisos de siempre.
    from core.config import AVISOS
    assert cliente.get("/api/v1/carta").json()["avisos"] == AVISOS
    r = cliente.put("/api/v1/config/pantallas", json={
        "kicker": "  Café   de especialidad ", "cinta": ["Lunes a sábado", "", "  Wi-Fi: Clave  "],
        "fuente_url": "ftp://malo", "fuente_cada": 15})
    assert r.status_code == 200
    t = r.json()["textos"]
    assert t["kicker"] == "Café de especialidad"
    assert t["cinta"] == ["Lunes a sábado", "Wi-Fi: Clave"]
    assert t["fuente_url"] == "", "solo http o https"
    assert cliente.get("/api/v1/carta").json()["avisos"] == ["Lunes a sábado", "Wi-Fi: Clave"]
    # Vaciar los avisos devuelve los de siempre.
    cliente.put("/api/v1/config/pantallas", json={"cinta": []})
    assert cliente.get("/api/v1/carta").json()["avisos"] == AVISOS


@pytest.mark.parametrize("malo", [
    {"kicker": "x" * 71}, {"cinta": ["a"] * 13}, {"fuente_cada": 0}, {"fuente_cada": 241},
])
def test_el_servidor_rechaza_textos_que_no_caben(cliente, malo):
    assert cliente.put("/api/v1/config/pantallas", json=malo).status_code == 422


def test_la_carta_desde_otra_direccion_viaja_al_televisor(cliente):
    cliente.put("/api/v1/config/pantallas", json={
        "fuente_url": "https://mi-sistema.cl/carta.json", "fuente_cada": 5})
    out = cliente.get("/api/v1/pantallas/config").json()["textos"]
    assert out["fuente_url"] == "https://mi-sistema.cl/carta.json" and out["fuente_cada"] == 5


def test_volver_a_los_datos_de_ejemplo_borra_textos_pero_no_televisores(cliente):
    _tv(cliente)
    cliente.put("/api/v1/config/pantallas", json={"kicker": "Algo", "cinta": ["Aviso"]})
    r = cliente.post("/api/v1/config/pantallas/ejemplo")
    assert r.status_code == 200 and r.json()["textos"]["kicker"] == "" and r.json()["textos"]["cinta"] == []
    assert len(cliente.get("/api/v1/config/televisores").json()["televisores"]) == 1


def test_respaldo_de_las_pantallas_baja_y_vuelve_a_cargar(cliente):
    _tv(cliente, nombre="Vitrina", modo="vitrina", orient="vertical")
    _tv(cliente, nombre="Carta", modo="menu")
    cliente.put("/api/v1/config/pantallas", json={"kicker": "Mi café", "cinta": ["Wi-Fi"]})
    bajado = cliente.get("/api/v1/config/pantallas/respaldo")
    assert bajado.status_code == 200 and "attachment" in bajado.headers["content-disposition"]
    copia = json.loads(bajado.content)
    assert copia["gespoint"] == "pantallas" and len(copia["televisores"]) == 2
    # Se estropea todo y se carga la copia.
    cliente.post("/api/v1/config/pantallas/ejemplo")
    cliente.delete("/api/v1/config/televisores/1")
    cliente.delete("/api/v1/config/televisores/2")
    r = cliente.put("/api/v1/config/pantallas/respaldo", json=copia)
    assert r.status_code == 200, r.text
    assert [t["nombre"] for t in cliente.get("/api/v1/config/televisores").json()["televisores"]] \
        == ["Vitrina", "Carta"]
    assert cliente.get("/api/v1/config/pantallas").json()["textos"]["kicker"] == "Mi café"


@pytest.mark.parametrize("archivo", [{}, {"gespoint": "otra cosa"},
                                     {"gespoint": "pantallas", "textos": {}},
                                     {"gespoint": "pantallas", "textos": [], "televisores": []}])
def test_un_respaldo_de_pantallas_que_no_es_se_rechaza_sin_tocar_nada(cliente, archivo):
    _tv(cliente)
    cliente.put("/api/v1/config/pantallas", json={"kicker": "Se queda"})
    assert cliente.put("/api/v1/config/pantallas/respaldo", json=archivo).status_code == 422
    assert cliente.get("/api/v1/config/pantallas").json()["textos"]["kicker"] == "Se queda"
    assert len(cliente.get("/api/v1/config/televisores").json()["televisores"]) == 1


def test_probar_la_conexion_de_la_carta(cliente, monkeypatch):
    import urllib.request
    p = "/api/v1/config/pantallas/probar"
    assert cliente.post(p, json={"url": ""}).json()["vacia"] is True
    assert cliente.post(p, json={"url": "ftp://x"}).json()["ok"] is False

    class Respuesta:
        def __init__(self, cuerpo):
            self.cuerpo = cuerpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return self.cuerpo

    buena = {"categorias": [{"nombre": "Café", "productos": [{"nombre": "Latte"}, {"nombre": "Mocha"}]}]}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: Respuesta(json.dumps(buena).encode()))
    r = cliente.post(p, json={"url": "https://x.cl/carta.json"}).json()
    assert r["ok"] and r["productos"] == 2
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Respuesta(b'{"nada": 1}'))
    assert cliente.post(p, json={"url": "https://x.cl/carta.json"}).json()["ok"] is False

    def caida(*a, **k):
        raise OSError("sin red")
    monkeypatch.setattr(urllib.request, "urlopen", caida)
    out = cliente.post(p, json={"url": "https://x.cl/carta.json"}).json()
    assert out["ok"] is False and "no contestó" in out["detalle"]


def test_una_base_con_basura_en_los_televisores_no_rompe_la_pantalla(cliente):
    from sqlmodel import Session
    from apps.pos.db.models import Ajuste
    from apps.pos.db.session import engine
    with Session(engine) as s:
        s.add(Ajuste(clave="televisores", valor="{no es json"))
        s.add(Ajuste(clave="pantallas_textos", valor='["raro"]'))
        s.commit()
    assert cliente.get("/api/v1/pantallas/config?t=1").json() == {"textos": {}, "tv": None}
    assert cliente.get("/api/v1/config/televisores").json()["televisores"] == []
