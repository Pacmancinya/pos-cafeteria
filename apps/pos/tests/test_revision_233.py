"""Hallazgos de la revisión adversarial previa a la 2.33.

Cada prueba reproduce un problema real que pudo afectar a un local que actualiza.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session

from apps.pos.db.models import Usuario
from apps.pos.db.session import engine


def _dueno(cliente, nombre="Ruperto", pin="1234"):
    u = cliente.post("/api/v1/usuarios", json={"nombre": nombre, "pin": pin}).json()
    r = cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": pin})
    assert r.status_code == 200
    return u


def _cajero(cliente, nombre="Ana", pin="2222", permisos=""):
    r = cliente.post("/api/v1/usuarios", json={
        "nombre": nombre, "pin": pin, "rol": "cajero", "permisos": permisos})
    assert r.status_code == 200, r.text
    return r.json()


def _sesion_de(cliente, u, pin):
    r = cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": pin})
    assert r.status_code == 200, r.text


def test_reportes_abierto_por_el_dueno_no_lo_hereda_el_cajero_que_entra_despues(cliente):
    """El dueño abre Reportes (ganancia, ventas por cajero) y otra persona entra a la caja
    dentro de los 5 minutos: la galleta de Reportes tiene que quedar amarrada a la presencia
    de quien escribió el PIN, como la de Config."""
    _dueno(cliente)
    ana = _cajero(cliente)
    assert cliente.post("/api/v1/reportes/entrar", json={"pin": "1234"}).status_code == 200
    assert cliente.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 200
    _sesion_de(cliente, ana, "2222")          # entra la cajera, el navegador conserva la galleta
    assert cliente.get("/api/v1/reportes/resumen?periodo=hoy").status_code in (401, 403)
    assert cliente.get("/api/v1/reportes/estado").json()["activo"] is False


def test_quien_administraba_el_equipo_con_permisos_propios_no_queda_sin_config(cliente):
    """Hasta la 2.32 «usuarios» bastaba para editar personas (y para darse «config»). Desde la
    2.33 Equipo pide también «config»: una lista propia con «usuarios» y sin «config» dejaba a
    esa persona sin poder entrar a Equipo y sin nadie que le devolviera el permiso. La
    migración (una sola vez) le agrega «config»."""
    from apps.pos.db.migraciones import _dar_config_a_quien_administraba_el_equipo
    from apps.pos.db.models import Ajuste

    _dueno(cliente)
    jefa = cliente.post("/api/v1/usuarios", json={
        "nombre": "Jefa", "pin": "5555", "rol": "dueno",
        "permisos": "vender,ver_dia,usuarios"}).json()
    solo = cliente.post("/api/v1/usuarios", json={
        "nombre": "Solo", "pin": "6666", "rol": "dueno", "permisos": "vender"}).json()
    de_rol = cliente.post("/api/v1/usuarios", json={
        "nombre": "DeRol", "pin": "7777", "rol": "dueno"}).json()
    with Session(engine) as s:
        s.delete(s.get(Ajuste, "migracion.config_con_usuarios"))     # como en una caja que se actualiza
        s.commit()
    assert _dar_config_a_quien_administraba_el_equipo() == [f"usuario {jefa['id']}: + config"]
    with Session(engine) as s:
        assert s.get(Usuario, jefa["id"]).permisos == "vender,ver_dia,usuarios,config"
        assert s.get(Usuario, solo["id"]).permisos == "vender"
        assert s.get(Usuario, de_rol["id"]).permisos == ""
    # Una sola vez: si el dueño se lo quita a propósito, el próximo arranque no se lo devuelve.
    with Session(engine) as s:
        u = s.get(Usuario, jefa["id"])
        u.permisos = "vender,ver_dia,usuarios"
        s.add(u)
        s.commit()
    assert _dar_config_a_quien_administraba_el_equipo() == []


def test_el_dia_a_dia_del_cajero_no_pide_el_pin_de_config(cliente, carta, config_real):
    """Abrir, vender, imprimir el comprobante, sacar plata, ver su turno, escanear y cerrar:
    nada de eso puede haberse mudado detrás del PIN de Config."""
    _dueno(cliente)
    assert cliente.post("/api/v1/config/entrar", json={"pin": "1234"}).status_code == 200
    ana = _cajero(cliente)
    _sesion_de(cliente, ana, "2222")
    r = cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 10000})
    assert r.status_code == 200, r.text
    turno_id = r.json().get("id") or r.json().get("turno", {}).get("id")
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}],
        "medio_pago": "efectivo", "propina": 100, "paga_con": 10000})
    assert v.status_code == 200, v.text
    vid = v.json()["id"]
    assert cliente.get(f"/comprobante/{vid}").status_code == 200
    assert cliente.get("/api/v1/ventas").status_code == 200
    assert cliente.get("/api/v1/ajustes").status_code == 200
    assert cliente.get("/api/v1/local").status_code == 200
    assert cliente.get("/api/v1/carta").status_code == 200
    assert cliente.get("/api/v1/actualizacion").status_code == 200
    assert cliente.get("/api/v1/actualizacion/vuelta").status_code == 200
    assert cliente.get("/api/v1/turnos/actual").status_code == 200
    assert cliente.get(f"/api/v1/turnos/{turno_id}/corte").status_code == 200
    assert cliente.get("/api/v1/categorias").status_code == 200
    # El margen sugerido lo mueve cualquiera con «config»; el cajero no, y no es un error 500.
    assert cliente.put("/api/v1/ajustes", json={"margen_sugerido": 40}).status_code == 403
    rr = cliente.post("/api/v1/turnos/retiro", json={"monto": 500, "motivo": "pan"})
    assert rr.status_code == 200, rr.text
    c = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 10000 + 3400 * 2 + 100 - 500})
    assert c.status_code == 200, c.text
    assert cliente.get(f"/cierre/{turno_id}").status_code == 200


def test_el_dueno_cambia_el_margen_desde_la_ficha_sin_pin_de_config(cliente, config_real):
    """La ficha de un producto mueve el margen sugerido sin pasar por Config (app.js,
    elegirMargen). Con una clave sola se acepta con el permiso; con otras, pide el PIN."""
    _dueno(cliente)
    assert cliente.put("/api/v1/ajustes", json={"margen_sugerido": 40}).status_code == 200
    assert cliente.put("/api/v1/ajustes", json={"margen_sugerido": 40, "bloqueo_minutos": 5}).status_code == 401


def test_la_carta_responde_aunque_el_televisor_simple_arme_mal_su_direccion(cliente, carta):
    """pantallas-simple pide `/api/v1/carta?t=<su número>` y le agregaba otro `?t=<hora>`:
    la caja recibía `t=1?t=1699…` y respondía 422, así que el televisor viejo (ES5) de un
    local que copió el enlace de Config se quedaba sin carta. La carta nunca debe caerse por
    un parámetro de más."""
    for t in ("1?t=1699999999999", "abc", "", "1699999999999", "1"):
        r = cliente.get("/api/v1/carta", params={"t": t})
        assert r.status_code == 200, (t, r.text)
    assert cliente.get("/api/v1/carta?t=1?t=1699999999999").status_code == 200


def test_el_televisor_simple_no_pega_dos_veces_el_signo_de_pregunta():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "static" / "pantallas-simple.html").read_text(encoding="utf-8")
    assert 'donde() + "?t="' not in html


def test_salir_de_la_caja_cierra_reportes_y_config(cliente, config_real):
    _dueno(cliente)
    assert cliente.post("/api/v1/reportes/entrar", json={"pin": "1234"}).status_code == 200
    assert cliente.post("/api/v1/config/entrar", json={"pin": "1234"}).status_code == 200
    cliente.post("/api/v1/sesion/salir", json={})
    assert cliente.get("/api/v1/reportes/resumen?periodo=hoy").status_code in (401, 403)
