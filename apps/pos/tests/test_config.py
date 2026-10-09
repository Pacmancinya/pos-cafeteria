"""Config: el PIN verificado en el servidor, los ajustes nuevos y restaurar un respaldo.

Lo que se prueba acá no es que «la pantalla se vea bien» (eso se mide con tools/pantallas/auditar.py)
sino lo que no puede fallar:

  · Config no se abre sin el PIN de alguien con el permiso, y se cierra sola a los 5 minutos.
  · Cada ajuste nuevo parte con lo que la caja hacía antes de poder elegirlo.
  · El servidor —no la pantalla— rechaza una forma de pago que el local desactivó.
  · Restaurar un respaldo guarda antes la base de hoy, cuenta bien lo que se perdería y nunca
    deja la base dañada con un archivo malo.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import timedelta

import pytest

from apps.pos import sesion
from apps.pos.api import config as api_config
from apps.pos.db.session import engine
from tools import respaldo as resp


# ------------------------------------------------------------------ ayudas
def _dueno(cliente, nombre="Ruperto", pin="1234"):
    u = cliente.post("/api/v1/usuarios", json={"nombre": nombre, "pin": pin}).json()
    r = cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": pin})
    assert r.status_code == 200
    return u


def _entrar_a_config(cliente, pin="1234"):
    r = cliente.post("/api/v1/config/entrar", json={"pin": pin})
    assert r.status_code == 200, r.text
    return r.json()


def _cajero(cliente, nombre="Ana", pin="2222", permisos=""):
    r = cliente.post("/api/v1/usuarios", json={
        "nombre": nombre, "pin": pin, "rol": "cajero", "permisos": permisos})
    assert r.status_code == 200, r.text
    return r.json()


def _sesion_de(cliente, u, pin):
    r = cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": pin})
    assert r.status_code == 200, r.text


class Reloj:
    """Un reloj que se adelanta a mano, para no esperar 5 minutos de verdad."""

    def __init__(self, monkeypatch):
        self.real = sesion.ahora
        self.salto = timedelta(0)
        monkeypatch.setattr(sesion, "ahora", lambda: self.real() + self.salto)

    def avanzar(self, **kw):
        self.salto += timedelta(**kw)


# =========================================================== el PIN de Config
def test_sin_pin_de_config_no_se_cambia_nada_aunque_el_dueno_este_en_la_caja(cliente, config_real):
    _dueno(cliente)
    # Leer los ajustes lo puede cualquiera que esté en la caja (el margen, el bloqueo)…
    assert cliente.get("/api/v1/ajustes").status_code == 200
    # …cambiarlos pide el PIN de nuevo.
    r = cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 5})
    assert r.status_code == 401 and "PIN" in r.json()["detail"]
    assert cliente.put("/api/v1/local", json={"nombre": "Otro"}).status_code == 401
    assert cliente.get("/api/v1/red").status_code == 401
    assert cliente.get("/api/v1/usuarios").status_code == 401
    assert cliente.get("/api/v1/impresion/impresoras").status_code == 401
    assert cliente.post("/api/v1/actualizacion/volver").status_code == 401
    assert cliente.get("/api/v1/diagnostico").status_code == 401
    assert cliente.get("/api/v1/config/estado").json()["activo"] is False


def test_con_el_pin_correcto_config_se_abre(cliente, config_real):
    u = _dueno(cliente)
    r = _entrar_a_config(cliente)
    assert r["usuario"]["id"] == u["id"] and r["minutos"] == 5
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 5}).status_code == 200
    assert cliente.get("/api/v1/ajustes").json()["bloqueo_minutos"] == 5
    assert cliente.get("/api/v1/config/estado").json()["activo"] is True
    # Salir cierra: el mismo navegador ya no puede cambiar nada.
    cliente.post("/api/v1/config/salir")
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 3}).status_code == 401


def test_pin_malo_no_abre_y_tiene_freno(cliente, config_real):
    _dueno(cliente)
    r = cliente.post("/api/v1/config/entrar", json={"pin": "9999"})
    assert r.status_code == 401 and "incorrecto" in r.json()["detail"].lower()
    codigos = {cliente.post("/api/v1/config/entrar", json={"pin": f"{i:04d}"}).status_code
               for i in range(1000, 1015)}
    assert 429 in codigos, "diez mil PIN de 4 dígitos no se pueden probar de corrido"
    # Con el freno puesto ni el PIN bueno entra hasta que pase la espera.
    assert cliente.post("/api/v1/config/entrar", json={"pin": "1234"}).status_code == 429


def test_alguien_sin_el_permiso_de_configurar_no_entra_ni_con_su_pin(cliente, config_real):
    _dueno(cliente)
    _entrar_a_config(cliente)
    _cajero(cliente)
    r = cliente.post("/api/v1/config/entrar", json={"pin": "2222"})
    assert r.status_code == 403 and "Ana" in r.json()["detail"]
    assert cliente.get("/api/v1/config/estado").json()["activo"] is True      # sigue la de antes


def test_un_cajero_en_la_caja_no_cambia_ajustes_aunque_antes_estuvo_el_dueno(cliente, config_real):
    """El acceso queda amarrado a la persona que estaba en la caja cuando se escribió el PIN: si
    entra otra, esa galleta —que el navegador todavía guarda— ya no sirve."""
    _dueno(cliente)
    _entrar_a_config(cliente)
    ana = _cajero(cliente)
    _sesion_de(cliente, ana, "2222")
    r = cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 10})
    assert r.status_code == 403
    assert cliente.get("/api/v1/ajustes").json()["bloqueo_minutos"] == 3
    assert cliente.get("/api/v1/config/estado").json()["activo"] is False


def test_el_dueno_puede_escribir_su_pin_en_la_sesion_de_un_cajero(cliente, config_real):
    """Es el patrón de Reportes: el PIN de alguien con permiso abre Config aunque la caja la esté
    usando otra persona."""
    _dueno(cliente)
    _entrar_a_config(cliente)
    ana = _cajero(cliente)
    _sesion_de(cliente, ana, "2222")
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 10}).status_code == 403
    r = _entrar_a_config(cliente, "1234")
    assert r["usuario"]["nombre"] == "Ruperto"
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 10}).status_code == 200


def test_el_acceso_se_cierra_a_los_cinco_minutos_sin_uso_y_se_renueva_con_el_uso(
        cliente, config_real, monkeypatch):
    reloj = Reloj(monkeypatch)
    _dueno(cliente)
    _entrar_a_config(cliente)
    reloj.avanzar(minutes=4)
    assert cliente.get("/api/v1/config/estado").json()["activo"] is True       # renueva
    reloj.avanzar(minutes=4)                                                    # 8 en total, 4 sin uso
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 5}).status_code == 200
    reloj.avanzar(minutes=6)                                                    # 6 sin uso
    r = cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 10})
    assert r.status_code == 401 and "5 minutos" in r.json()["detail"]
    assert cliente.get("/api/v1/ajustes").json()["bloqueo_minutos"] == 5


def test_quitarle_el_permiso_al_que_abrio_config_cierra_al_toque(cliente, config_real):
    dueno = _dueno(cliente)
    _entrar_a_config(cliente)
    gerente = _cajero(cliente, "Gema", "3333", permisos="config,usuarios,vender")
    _sesion_de(cliente, gerente, "3333")
    assert _entrar_a_config(cliente, "3333")["usuario"]["nombre"] == "Gema"
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 5}).status_code == 200
    # El dueño (en otro navegador) le quita el permiso.
    from sqlmodel import Session
    from apps.pos.db.models import Usuario
    with Session(engine) as s:
        g = s.get(Usuario, gerente["id"])
        g.permisos = "vender"
        s.add(g)
        s.commit()
    r = cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 10})
    assert r.status_code in (401, 403)
    assert cliente.get("/api/v1/ajustes").json()["bloqueo_minutos"] == 5
    del dueno


def test_el_margen_se_sigue_moviendo_desde_la_ficha_del_producto_sin_pasar_por_config(
        cliente, config_real):
    _dueno(cliente)
    r = cliente.put("/api/v1/ajustes", json={"margen_sugerido": 60})
    assert r.status_code == 200 and r.json()["margen_sugerido"] == 60
    # Pero solo el margen: cualquier otra cosa pide el PIN.
    assert cliente.put("/api/v1/ajustes", json={"margen_sugerido": 60, "propinas": 0}).status_code == 401


def test_una_caja_sin_personas_se_configura_sin_pin(cliente, config_real):
    """Mientras no hay nadie registrado la caja ya está en manos de quien la instala."""
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 5}).status_code == 200
    assert cliente.put("/api/v1/local", json={"nombre": "Café nuevo"}).status_code == 200
    assert cliente.get("/api/v1/config/estado").json()["activo"] is True


def test_crear_personas_pide_el_pin_de_config_desde_la_segunda(cliente, config_real):
    _dueno(cliente)
    r = cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "2222"})
    assert r.status_code == 401
    _entrar_a_config(cliente)
    assert cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "2222"}).status_code == 200


def test_ninguna_ruta_de_config_se_olvida_de_la_puerta(cliente, config_real):
    """Si alguien agrega un endpoint a /api/v1/config sin pedir el PIN, esta prueba lo caza."""
    from apps.pos.api import pantallas as api_pantallas
    _dueno(cliente)
    libres = {"/api/v1/config/entrar", "/api/v1/config/salir", "/api/v1/config/estado"}
    revisadas = []
    for ruta in list(api_config.router.routes) + list(api_pantallas.router.routes):
        path = getattr(ruta, "path", "")
        if not path.startswith("/api/v1/config") or path in libres:
            continue
        for metodo in ruta.methods - {"HEAD", "OPTIONS"}:
            destino = path.replace("{archivo}", "pos-2026-01-01.db").replace("{id_}", "1")
            r = cliente.request(metodo, destino, json={})
            assert r.status_code == 401, f"{metodo} {path} no pidió el PIN de Config ({r.status_code})"
            revisadas.append((metodo, path))
    assert len(revisadas) >= 14, revisadas


# ================================================ los ajustes nuevos: valores de fábrica
NUEVOS_DE_FABRICA = {
    "mensaje_ticket": "¡Gracias!",
    "medios_pago": ["efectivo", "debito", "credito", "transferencia"],
    "pago_mixto": 1,
    "propinas": 1,
    "propina_sugerida": [],
    "propina_solo_tarjeta": 0,
    "descuentos_rapidos": [10, 15, 20],
    "redondeo_precio": 50,
}


def test_una_base_vieja_sigue_cobrando_e_imprimiendo_igual(cliente):
    """Una caja que se actualiza trae la tabla de ajustes con lo de antes y NADA de lo nuevo."""
    from sqlmodel import Session
    from apps.pos.db.models import Ajuste
    with Session(engine) as s:
        for clave, valor in (("margen_sugerido", "55"), ("bloqueo_minutos", "5"),
                             ("local_nombre", "Café viejo")):
            s.add(Ajuste(clave=clave, valor=valor))
        s.commit()
    a = cliente.get("/api/v1/ajustes").json()
    for clave, esperado in NUEVOS_DE_FABRICA.items():
        assert a[clave] == esperado, clave
    assert a["margen_sugerido"] == 55 and a["bloqueo_minutos"] == 5          # lo de antes no se toca


def test_un_valor_roto_en_la_base_vuelve_al_de_fabrica(cliente):
    from sqlmodel import Session
    from apps.pos.db.models import Ajuste
    with Session(engine) as s:
        for clave, valor in (("medios_pago", "inventado,otro"), ("descuentos_rapidos", "0,500,x,10"),
                             ("redondeo_precio", "33"), ("pago_mixto", "7"), ("propinas", "x"),
                             ("propina_sugerida", "abc"), ("mensaje_ticket", "   ")):
            s.add(Ajuste(clave=clave, valor=valor))
        s.commit()
    a = cliente.get("/api/v1/ajustes").json()
    assert a["medios_pago"] == NUEVOS_DE_FABRICA["medios_pago"], "sin ninguna forma de pago no se cobra"
    assert a["descuentos_rapidos"] == [10]            # lo que sirve se conserva, lo imposible se ignora
    assert a["redondeo_precio"] == 50 and a["pago_mixto"] == 1 and a["propinas"] == 1
    assert a["propina_sugerida"] == [] and a["mensaje_ticket"] == "¡Gracias!"


def test_los_ajustes_nuevos_se_guardan_y_se_leen_de_vuelta(cliente):
    cuerpo = {"mensaje_ticket": "  ¡Vuelve   pronto!  ", "medios_pago": ["transferencia", "efectivo"],
              "pago_mixto": 0, "propinas": 1, "propina_sugerida": [15, 5, 10, 10],
              "propina_solo_tarjeta": 1, "descuentos_rapidos": [20, 5], "redondeo_precio": 100}
    r = cliente.put("/api/v1/ajustes", json=cuerpo)
    assert r.status_code == 200, r.text
    a = cliente.get("/api/v1/ajustes").json()
    assert a["mensaje_ticket"] == "¡Vuelve pronto!"
    assert a["medios_pago"] == ["efectivo", "transferencia"]        # en el orden de siempre
    assert a["pago_mixto"] == 0 and a["propina_solo_tarjeta"] == 1
    assert a["propina_sugerida"] == [5, 10, 15] and a["descuentos_rapidos"] == [5, 20]
    assert a["redondeo_precio"] == 100
    # Mover una sola cosa no toca las demás.
    cliente.put("/api/v1/ajustes", json={"redondeo_precio": 10})
    b = cliente.get("/api/v1/ajustes").json()
    assert b["redondeo_precio"] == 10 and b["medios_pago"] == ["efectivo", "transferencia"]


@pytest.mark.parametrize("malo", [
    {"medios_pago": []},
    {"medios_pago": ["bitcoin"]},
    {"redondeo_precio": 25},
    {"redondeo_precio": 0},
    {"descuentos_rapidos": [0]},
    {"descuentos_rapidos": [101]},
    {"descuentos_rapidos": [10, 15, 20, 25, 30, 35, 40]},
    {"propina_sugerida": [-5]},
    {"propina_sugerida": [True]},
    {"mensaje_ticket": "x" * 61},
    {"mensaje_ticket": "linea\x07rara"},
    {"pago_mixto": 2},
    {"propinas": -1},
])
def test_el_servidor_rechaza_ajustes_que_no_sirven(cliente, malo):
    r = cliente.put("/api/v1/ajustes", json=malo)
    assert r.status_code == 422, (malo, r.text)
    a = cliente.get("/api/v1/ajustes").json()
    for clave, esperado in NUEVOS_DE_FABRICA.items():
        assert a[clave] == esperado, "un rechazo no puede dejar nada a medias"


def test_un_mensaje_vacio_vuelve_al_de_siempre(cliente):
    cliente.put("/api/v1/ajustes", json={"mensaje_ticket": "Hasta mañana"})
    assert cliente.get("/api/v1/ajustes").json()["mensaje_ticket"] == "Hasta mañana"
    cliente.put("/api/v1/ajustes", json={"mensaje_ticket": ""})
    assert cliente.get("/api/v1/ajustes").json()["mensaje_ticket"] == "¡Gracias!"


# ================================================ el servidor valida las formas de cobro
def _vender(cliente, carta, **extra):
    cuerpo = {"lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}], **extra}
    return cliente.post("/api/v1/ventas", json=cuerpo)


def test_por_defecto_se_cobra_con_las_cuatro_formas_en_dos_partes_y_con_propina(cliente, carta, caja):
    for medio in ("efectivo", "debito", "credito", "transferencia"):
        assert _vender(cliente, carta, medio_pago=medio, propina=200).status_code == 200
    r = _vender(cliente, carta, pagos=[{"medio": "efectivo", "monto": 1400},
                                       {"medio": "debito", "monto": 2000}])
    assert r.status_code == 200 and r.json()["medio_pago"] == "mixto"


def test_una_forma_de_pago_desactivada_no_se_puede_registrar(cliente, carta, caja):
    cliente.put("/api/v1/ajustes", json={"medios_pago": ["efectivo", "debito"]})
    assert _vender(cliente, carta, medio_pago="efectivo").status_code == 200
    assert _vender(cliente, carta, medio_pago="debito").status_code == 200
    for medio in ("credito", "transferencia"):
        r = _vender(cliente, carta, medio_pago=medio)
        assert r.status_code == 409 and "desactivado" in r.json()["detail"]
    # Tampoco escondida en una de las partes de un pago en dos formas.
    r = _vender(cliente, carta, pagos=[{"medio": "efectivo", "monto": 1400},
                                       {"medio": "credito", "monto": 2000}])
    assert r.status_code == 409
    # Y no quedó ninguna venta a medias.
    assert len(cliente.get("/api/v1/ventas").json()["ventas"]) == 2


def test_pago_en_dos_formas_apagado(cliente, carta, caja):
    cliente.put("/api/v1/ajustes", json={"pago_mixto": 0})
    r = _vender(cliente, carta, pagos=[{"medio": "efectivo", "monto": 1400},
                                       {"medio": "debito", "monto": 2000}])
    assert r.status_code == 409 and "dos formas" in r.json()["detail"]
    assert _vender(cliente, carta, medio_pago="debito").status_code == 200


def test_propinas_apagadas_y_propina_solo_con_tarjeta(cliente, carta, caja):
    cliente.put("/api/v1/ajustes", json={"propinas": 0})
    assert _vender(cliente, carta, medio_pago="debito", propina=300).status_code == 409
    assert _vender(cliente, carta, medio_pago="debito").status_code == 200       # sin propina, normal
    cliente.put("/api/v1/ajustes", json={"propinas": 1, "propina_solo_tarjeta": 1})
    assert _vender(cliente, carta, medio_pago="efectivo", propina=300).status_code == 409
    assert _vender(cliente, carta, medio_pago="transferencia", propina=300).status_code == 409
    assert _vender(cliente, carta, medio_pago="debito", propina=300).status_code == 200
    assert _vender(cliente, carta, medio_pago="credito", propina=300).status_code == 200
    assert _vender(cliente, carta, medio_pago="efectivo").status_code == 200


# ================================================ el mensaje al pie del ticket
def _envios_de_impresion(cliente, monkeypatch, venta_id, papel, crudo):
    from apps.pos import impresion_windows as windows
    envios = []
    funcion = "imprimir_crudo" if crudo else "imprimir"
    monkeypatch.setattr(windows, funcion,
                        lambda *a, **k: envios.append(a) or {"ok": True, "detalle": "ok"})
    prefijo = "crudo/" if crudo else ""
    r = cliente.post(f"/api/v1/impresion/{prefijo}comprobante/{venta_id}",
                     json={"impresora": "Caja", "papel": papel})
    assert r.status_code == 200, r.text
    return envios[-1][2]


def test_el_comprobante_del_navegador_dice_el_mensaje_y_lo_escapa(cliente, carta, caja):
    v = _vender(cliente, carta).json()
    assert "¡Gracias!" in cliente.get(f"/comprobante/{v['id']}").text
    cliente.put("/api/v1/ajustes", json={"mensaje_ticket": "Café & té <b>hoy</b>"})
    html = cliente.get(f"/comprobante/{v['id']}").text
    assert "Café &amp; té &lt;b&gt;hoy&lt;/b&gt;" in html and "<b>hoy</b>" not in html


@pytest.mark.parametrize("papel,ancho", [(58, 32), (80, 48)])
def test_el_mensaje_largo_se_parte_entre_palabras_al_ancho_del_rollo(
        cliente, carta, caja, monkeypatch, papel, ancho):
    from apps.pos import impresion_windows as windows
    mensaje = "¡Gracias por venir! Te esperamos mañana con café fresco"
    cliente.put("/api/v1/ajustes", json={"mensaje_ticket": mensaje})
    v = _vender(cliente, carta).json()
    bloques = _envios_de_impresion(cliente, monkeypatch, v["id"], papel, crudo=True)
    final = bloques[-1]
    assert final["texto"] == mensaje and final.get("envolver")
    crudo = windows._bytes_escpos(papel, [final], cortar=False)
    cuerpo = crudo.split(b"\x1ba\x01", 1)[1].split(b"\x1d!\x00")[0]
    filas = [f for f in cuerpo.decode("cp850").split("\n") if f]
    assert len(filas) >= 2
    assert all(len(f) <= ancho for f in filas), filas
    assert " ".join(filas) == mensaje, "no se come ni parte ninguna palabra"
    assert "¡".encode("cp850") in cuerpo and "ñ".encode("cp850") in cuerpo      # CP850: tildes y ñ


def test_una_palabra_mas_larga_que_el_rollo_se_corta_y_no_se_pierde():
    from apps.pos import impresion_windows as windows
    filas = windows._envolver("a " + "x" * 40 + " b", 32)
    assert all(len(f) <= 32 for f in filas)
    assert "".join(filas).replace(" ", "") == "a" + "x" * 40 + "b"
    assert windows._envolver("", 32) == [""]


def test_con_el_mensaje_de_fabrica_el_papel_sale_como_siempre(cliente, carta, caja, monkeypatch):
    v = _vender(cliente, carta).json()
    bloques = _envios_de_impresion(cliente, monkeypatch, v["id"], 58, crudo=True)
    assert bloques[-1]["texto"] == "¡Gracias!"
    lineas = _envios_de_impresion(cliente, monkeypatch, v["id"], 80, crudo=False)
    assert "¡Gracias!" in lineas


def test_la_prueba_de_impresion_muestra_el_mensaje(cliente, monkeypatch):
    from apps.pos import impresion_windows as windows
    envios = []
    monkeypatch.setattr(windows, "imprimir_crudo", lambda *a, **k: envios.append(a) or {"ok": True})
    cliente.put("/api/v1/ajustes", json={"mensaje_ticket": "Hasta pronto"})
    assert cliente.post("/api/v1/impresion/crudo/prueba",
                        json={"impresora": "Caja", "papel": 58}).status_code == 200
    assert envios[-1][2][-1]["texto"] == "Hasta pronto"


# ================================================ el color de cada persona
def test_el_color_de_la_persona_se_guarda_y_solo_acepta_colores(cliente):
    _dueno(cliente)
    ana = cliente.post("/api/v1/usuarios", json={
        "nombre": "Ana", "pin": "2222", "color": "#3E6E8E"}).json()
    assert ana["color"] == "#3E6E8E"
    r = cliente.put(f"/api/v1/usuarios/{ana['id']}", json={"nombre": "Ana", "color": "#8C4A6B"})
    assert r.json()["color"] == "#8C4A6B"
    assert cliente.put(f"/api/v1/usuarios/{ana['id']}",
                       json={"nombre": "Ana", "color": "rojo"}).status_code == 422
    meta = cliente.get("/api/v1/usuarios/permisos").json()
    assert "#C9552B" in meta["colores"]
    # Sin color escrito, la caja le reparte uno y editar el nombre no se lo borra.
    sin = cliente.post("/api/v1/usuarios", json={"nombre": "Luis", "pin": "3333"}).json()
    assert sin["color"] in meta["colores"]
    assert cliente.put(f"/api/v1/usuarios/{sin['id']}", json={"nombre": "Luisa"}).json()["color"] == sin["color"]


def test_ver_reportes_se_da_y_se_quita_por_persona(cliente):
    """Viene solo con el rol dueño; en Equipo se le puede dar a un cajero y quitar a un dueño."""
    _dueno(cliente)
    meta = cliente.get("/api/v1/usuarios/permisos").json()
    claves = {p["clave"]: p["nombre"] for p in meta["catalogo"]}
    assert claves["ver_reportes"] == "Ver reportes"
    assert "ver_reportes" in meta["roles"]["dueno"] and "ver_reportes" not in meta["roles"]["cajero"]
    ana = cliente.post("/api/v1/usuarios", json={
        "nombre": "Ana", "pin": "2222", "permisos": "vender,turno_abrir,turno_cerrar,ver_reportes"}).json()
    assert "ver_reportes" in ana["permisos"]
    _sesion_de(cliente, ana, "2222")
    assert cliente.post("/api/v1/reportes/entrar", json={"pin": "2222"}).status_code == 200


# ================================================ restaurar un respaldo
def _ventas_en(ruta: str) -> int:
    c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        return c.execute("SELECT COUNT(*) FROM venta").fetchone()[0]
    finally:
        c.close()


def _base() -> str:
    return resp.ruta_de_la_base()


@pytest.fixture()
def con_respaldo(cliente, carta, caja, config_real, monkeypatch):
    """Un dueño con Config abierto, 3 ventas, un respaldo de ese momento y 2 ventas más."""
    reinicios = []
    monkeypatch.setattr(api_config, "programar_reinicio", lambda: reinicios.append(1))
    # Cada prueba parte de una carpeta de respaldos vacía.
    if os.path.isdir(resp.CARPETA):
        for f in os.listdir(resp.CARPETA):
            os.remove(os.path.join(resp.CARPETA, f))
    _dueno(cliente)
    _entrar_a_config(cliente)
    for _ in range(3):
        assert _vender(cliente, carta).status_code == 200
    r = resp.respaldar("prueba")
    assert r["ok"]
    for _ in range(2):
        assert _vender(cliente, carta).status_code == 200
    return {"cliente": cliente, "archivo": r["archivo"], "reinicios": reinicios, "carta": carta}


def test_la_lista_de_respaldos_cuenta_las_ventas_de_cada_uno(con_respaldo):
    c = con_respaldo["cliente"]
    r = c.get("/api/v1/config/respaldos").json()
    assert r["ventas_hoy"] == 5
    mio = next(x for x in r["copias"] if x["archivo"] == con_respaldo["archivo"])
    assert mio["ventas"] == 3 and mio["abre"] and mio["tipo"] == "diario"
    assert r["caja_abierta"]["quien"]


def test_revisar_un_respaldo_dice_cuantas_ventas_se_perderian(con_respaldo):
    c = con_respaldo["cliente"]
    r = c.get(f"/api/v1/config/respaldos/{con_respaldo['archivo']}").json()
    assert r["ok"] and r["ventas"] == 3 and r["ventas_hoy"] == 5 and r["perderia"] == 2


def test_restaurar_guarda_antes_la_base_de_hoy_y_deja_la_del_respaldo(con_respaldo):
    c = con_respaldo["cliente"]
    r = c.post("/api/v1/config/restaurar", json={
        "archivo": con_respaldo["archivo"], "ventas_que_se_pierden": 2})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] and out["ventas"] == 3 and out["ventas_perdidas"] == 2 and out["reiniciando"]
    assert con_respaldo["reinicios"] == [1], "la caja se reinicia sola al terminar"
    # La base de hoy (5 ventas) quedó guardada, entera y en un solo archivo…
    guardada = os.path.join(resp.CARPETA, out["guardada"])
    assert out["guardada"].startswith("antes-de-restaurar-") and _ventas_en(guardada) == 5
    assert not os.path.exists(guardada + "-wal")
    # …y la caja quedó como en el respaldo.
    assert _ventas_en(_base()) == 3
    # Con la copia guardada se puede deshacer: sale en la lista como «antes de restaurar».
    lista = c.get("/api/v1/config/respaldos").json()["copias"]
    assert any(x["archivo"] == out["guardada"] and x["tipo"] == "antes" for x in lista)


def test_restaurar_pide_que_se_confirme_el_numero_exacto_de_ventas_que_se_pierden(con_respaldo):
    c = con_respaldo["cliente"]
    r = c.post("/api/v1/config/restaurar", json={
        "archivo": con_respaldo["archivo"], "ventas_que_se_pierden": 0})
    assert r.status_code == 409 and "2 ventas" in r.json()["detail"]
    # Se cobró algo mientras tanto: lo que la persona vio ya no es lo que pasaría.
    assert _vender(c, con_respaldo["carta"]).status_code == 200
    r = c.post("/api/v1/config/restaurar", json={
        "archivo": con_respaldo["archivo"], "ventas_que_se_pierden": 2})
    assert r.status_code == 409 and "3 ventas" in r.json()["detail"]
    assert _ventas_en(_base()) == 6 and con_respaldo["reinicios"] == []


def test_volver_a_la_copia_de_antes_de_restaurar_no_pierde_ninguna_venta(con_respaldo):
    """Restaurar se puede deshacer: la base de hoy quedó guardada y tiene MÁS ventas que la
    caja de ahora, así que ponerla de vuelta no pierde nada."""
    c = con_respaldo["cliente"]
    r = c.post("/api/v1/config/restaurar", json={
        "archivo": con_respaldo["archivo"], "ventas_que_se_pierden": 2}).json()
    previa = r["guardada"]
    visto = c.get(f"/api/v1/config/respaldos/{previa}").json()
    assert visto["ok"] and visto["ventas"] == 5 and visto["perderia"] == 0
    r2 = c.post("/api/v1/config/restaurar", json={"archivo": previa, "ventas_que_se_pierden": 0})
    assert r2.status_code == 200, r2.text
    assert _ventas_en(_base()) == 5


def test_un_archivo_danado_se_rechaza_sin_tocar_la_base(con_respaldo):
    c = con_respaldo["cliente"]
    malo = os.path.join(resp.CARPETA, "pos-2020-02-02.db")
    with open(malo, "wb") as f:
        f.write(b"esto no es una base de datos" * 200)
    r = c.get("/api/v1/config/respaldos/pos-2020-02-02.db").json()
    assert r["ok"] is False and r["detalle"]
    antes = _ventas_en(_base())
    r = c.post("/api/v1/config/restaurar", json={"archivo": "pos-2020-02-02.db",
                                                  "ventas_que_se_pierden": 0})
    assert r.status_code == 422
    assert _ventas_en(_base()) == antes == 5
    assert con_respaldo["reinicios"] == []
    # La lista lo muestra, pero marcado como que no abre.
    copia = next(x for x in c.get("/api/v1/config/respaldos").json()["copias"]
                 if x["archivo"] == "pos-2020-02-02.db")
    assert copia["abre"] is False
    assert [f for f in os.listdir(resp.CARPETA) if f.startswith("antes-de-restaurar")] == [], \
        "un respaldo malo no debe dejar copias sueltas"
    # La caja sigue vendiendo.
    assert _vender(c, con_respaldo["carta"]).status_code == 200


def test_un_respaldo_de_otro_local_no_se_pone_encima(con_respaldo):
    c = con_respaldo["cliente"]
    ruta = os.path.join(resp.CARPETA, con_respaldo["archivo"])
    k = sqlite3.connect(ruta)
    k.execute("UPDATE ajuste SET valor = 'deadbeef' WHERE clave = 'instalacion_id'")
    k.commit()
    k.close()
    r = c.post("/api/v1/config/restaurar", json={"archivo": con_respaldo["archivo"],
                                                  "ventas_que_se_pierden": 2})
    assert r.status_code == 422 and "otro local" in r.json()["detail"]
    assert _ventas_en(_base()) == 5 and con_respaldo["reinicios"] == []


@pytest.mark.parametrize("nombre", ["../pos.db", "pos-2026-01-01.db/../../x", "pos.db",
                                    "C:\\pos-2026-01-01.db", "pos-2026-1-1.db", ""])
def test_solo_se_restauran_archivos_de_la_carpeta_de_respaldos(con_respaldo, nombre):
    c = con_respaldo["cliente"]
    r = c.post("/api/v1/config/restaurar", json={"archivo": nombre, "ventas_que_se_pierden": 0})
    assert r.status_code in (404, 422), (nombre, r.status_code)
    assert _ventas_en(_base()) == 5


def test_un_respaldo_que_ya_no_esta_da_404(con_respaldo):
    c = con_respaldo["cliente"]
    r = c.post("/api/v1/config/restaurar", json={"archivo": "pos-2031-12-31.db",
                                                  "ventas_que_se_pierden": 0})
    assert r.status_code == 404


def test_restaurar_exige_permiso_y_pin_de_config(con_respaldo):
    c = con_respaldo["cliente"]
    # Sin el acceso de Config (se cerró) no se restaura.
    c.post("/api/v1/config/salir")
    r = c.post("/api/v1/config/restaurar", json={"archivo": con_respaldo["archivo"],
                                                  "ventas_que_se_pierden": 2})
    assert r.status_code == 401
    # Un cajero tampoco, ni abriendo la lista.
    _entrar_a_config(c)
    ana = _cajero(c)
    _sesion_de(c, ana, "2222")
    for ruta, metodo in (("/api/v1/config/respaldos", "get"),
                         ("/api/v1/config/restaurar", "post")):
        r = getattr(c, metodo)(ruta, **({"json": {"archivo": con_respaldo["archivo"],
                                                    "ventas_que_se_pierden": 2}}
                                        if metodo == "post" else {}))
        assert r.status_code == 403, ruta
    assert _ventas_en(_base()) == 5


def test_respaldar_ahora_desde_config(con_respaldo):
    c = con_respaldo["cliente"]
    r = c.post("/api/v1/config/respaldar")
    assert r.status_code == 200 and r.json()["ok"]


def test_exportar_para_el_contador_sirve_con_el_pin_de_config(cliente, config_real):
    """La persona que está en Config puede bajar las planillas aunque su permiso suelto no
    incluya «ver informes» (y el dueño sigue pudiendo sin pasar por Config)."""
    _dueno(cliente)
    assert cliente.get("/api/v1/exportar/ventas").status_code == 200
    _entrar_a_config(cliente)
    gema = _cajero(cliente, "Gema", "3333", permisos="config,vender")
    _sesion_de(cliente, gema, "3333")
    # Suelto no tiene el permiso: la caja le pide el PIN de Config (tiene «config»).
    assert cliente.get("/api/v1/exportar/ventas").status_code == 401
    _entrar_a_config(cliente, "3333")
    assert cliente.get("/api/v1/exportar/ventas").status_code == 200
    assert cliente.get("/api/v1/exportar/detalle").status_code == 200


# ===================================================== nunca sin quien administre
def test_el_dueno_no_puede_quitarse_el_permiso_de_config(cliente, config_real):
    """Config se administra desde Config: si el único que entra se lo quita, nadie vuelve."""
    u = _dueno(cliente)
    _entrar_a_config(cliente)
    r = cliente.put(f"/api/v1/usuarios/{u['id']}", json={
        "nombre": "Ruperto", "rol": "dueno", "permisos": "vender,usuarios"})
    assert r.status_code == 409 and "Config" in r.json()["detail"]
    assert cliente.post("/api/v1/config/salir").status_code == 200
    _entrar_a_config(cliente)                     # sigue pudiendo entrar


def test_el_unico_dueno_no_se_desactiva_por_la_edicion(cliente, config_real):
    u = _dueno(cliente)
    _entrar_a_config(cliente)
    r = cliente.put(f"/api/v1/usuarios/{u['id']}", json={
        "nombre": "Ruperto", "rol": "dueno", "activo": False})
    assert r.status_code == 409


def test_si_otro_puede_administrar_si_se_puede_quitar(cliente, config_real):
    u = _dueno(cliente)
    _entrar_a_config(cliente)
    _cajero(cliente, permisos="vender,usuarios,config")
    r = cliente.put(f"/api/v1/usuarios/{u['id']}", json={
        "nombre": "Ruperto", "rol": "dueno", "permisos": "vender,usuarios"})
    assert r.status_code == 200, r.text


def test_no_se_saca_a_la_unica_persona_que_administra(cliente, config_real):
    """Un segundo dueño sin «config» no cuenta como alguien que pueda volver a Config."""
    _dueno(cliente)
    _entrar_a_config(cliente)
    otro = cliente.post("/api/v1/usuarios", json={
        "nombre": "Socio", "pin": "3333", "rol": "dueno", "permisos": "vender"}).json()
    cajera = _cajero(cliente, permisos="vender,usuarios,config")
    # Con Ruperto todavía puede: sacar a la cajera está bien.
    assert cliente.delete(f"/api/v1/usuarios/{cajera['id']}").status_code == 200
    assert otro["rol"] == "dueno"
