"""La 2.19: lo que hacía falta antes de vender Kofe a un segundo local.

Cada bloque cuida un punto del informe «Kofe antes del segundo local»: los PIN
y la red, los datos de cada local, el respaldo de afuera, el registro de
errores, la base en modo WAL y el archivo del contador.
"""
import csv
import hashlib
import io
import json
import os
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from apps.pos import firma, local
from apps.pos.freno import Freno
from apps.pos.main import app


def remoto():
    """Un equipo cualquiera de la red del local (o del wifi de invitados)."""
    return TestClient(app, client=("192.168.1.99", 5000))


def _dueno(cliente, nombre="Ana", pin="1234"):
    u = cliente.post("/api/v1/usuarios", json={"nombre": nombre, "pin": pin}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": pin})
    return u


def _cajero(cliente, nombre="Javi", pin="4321"):
    u = cliente.post("/api/v1/usuarios",
                     json={"nombre": nombre, "pin": pin, "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": pin})
    return u


# ---------------------------------------------------------------------------
# El freno de intentos
# ---------------------------------------------------------------------------
"""Un PIN de 4 dígitos son diez mil combinaciones, y hasta la 2.18 nada frenaba
probarlas todas, desde la caja o desde el Wi-Fi de clientes."""


def test_el_freno_perdona_cuatro_y_frena_al_quinto():
    t = [0.0]
    f = Freno(reloj=lambda: t[0])
    for _ in range(4):
        assert f.fallo("x") == 0
    assert f.fallo("x") == 30
    assert f.cuanto_falta("x") == 30
    t[0] = 31
    assert f.cuanto_falta("x") == 0
    assert f.fallo("x") == 60            # cada fallo nuevo dobla la espera
    f.acierto("x")
    assert f.cuanto_falta("x") == 0 and f.fallo("x") == 0


def test_la_espera_tiene_tope():
    f = Freno(reloj=lambda: 0.0)
    espera = 0
    for _ in range(30):
        espera = f.fallo("x")
    assert espera == 900


def test_el_pin_de_una_persona_tiene_freno(cliente):
    u = cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "1234"}).json()
    codigos = [cliente.post("/api/v1/sesion/entrar",
                            json={"usuario_id": u["id"], "pin": "0000"}).status_code
               for _ in range(5)]
    assert codigos == [401, 401, 401, 401, 429]
    # Mientras dura la espera, ni el PIN bueno entra.
    r = cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": "1234"})
    assert r.status_code == 429 and "Espera" in r.json()["detail"]


def test_el_pin_de_red_tiene_freno(cliente):
    with remoto() as r:
        codigos = [r.post("/entrar", data={"pin": "0000"}, follow_redirects=False).status_code
                   for _ in range(5)]
        assert codigos == [401, 401, 401, 401, 429]
        bueno = r.post("/entrar", data={"pin": local.PIN_DE_FABRICA}, follow_redirects=False)
        assert bueno.status_code == 429


# ---------------------------------------------------------------------------
# La galleta de la red
# ---------------------------------------------------------------------------
def test_la_galleta_vieja_de_la_red_ya_no_sirve(cliente):
    """Hasta la 2.18 era sha256 del PIN, sin ningún secreto de la caja: se podía
    calcular desde el código público sin escribir nunca el PIN."""
    vieja = hashlib.sha256(("pos-cafeteria:" + local.PIN_DE_FABRICA).encode()).hexdigest()[:32]
    with remoto() as r:
        r.cookies.set("pos_acceso", vieja)
        assert r.get("/api/v1/turnos/actual").status_code == 401


def test_cambiar_el_pin_de_red_deja_afuera_a_los_que_entraron_con_el_viejo(cliente):
    with remoto() as r:
        assert r.post("/entrar", data={"pin": local.PIN_DE_FABRICA},
                      follow_redirects=False).status_code == 303
        assert r.get("/api/v1/turnos/actual").status_code == 200
        nuevo = cliente.post("/api/v1/red/pin", json={}).json()["pin"]
        assert r.get("/api/v1/turnos/actual").status_code == 401
        assert r.post("/entrar", data={"pin": nuevo}, follow_redirects=False).status_code == 303
        assert r.get("/api/v1/turnos/actual").status_code == 200


# ---------------------------------------------------------------------------
# El PIN de red de cada local
# ---------------------------------------------------------------------------
def test_el_pin_de_red_es_de_fabrica_hasta_que_el_dueno_lo_cambia(cliente):
    r = cliente.get("/api/v1/red").json()
    assert r == {"pin": local.PIN_DE_FABRICA, "de_fabrica": True, "fijo": False}
    nuevo = cliente.post("/api/v1/red/pin", json={}).json()["pin"]
    assert len(nuevo) == 6 and nuevo.isdigit()
    assert cliente.get("/api/v1/red").json() == {"pin": nuevo, "de_fabrica": False, "fijo": False}


def test_no_se_puede_volver_al_pin_de_fabrica(cliente):
    assert cliente.post("/api/v1/red/pin", json={"pin": local.PIN_DE_FABRICA}).status_code == 422
    assert cliente.post("/api/v1/red/pin", json={"pin": "12ab"}).status_code == 422
    assert cliente.post("/api/v1/red/pin", json={"pin": "55667788"}).status_code == 200


def test_el_pin_de_red_solo_lo_ve_el_dueno(cliente):
    _dueno(cliente)
    _cajero(cliente)
    assert cliente.get("/api/v1/red").status_code == 403
    ajustes = cliente.get("/api/v1/ajustes")
    assert ajustes.status_code == 200
    assert "pin_red" not in ajustes.json()
    assert local.pin_de_red() not in ajustes.text


def test_si_la_instalacion_fijo_el_pin_la_caja_no_lo_cambia(cliente, monkeypatch):
    monkeypatch.setenv("POS_PIN", "770011")
    assert local.pin_de_red() == "770011"
    assert cliente.get("/api/v1/red").json()["fijo"] is True
    assert cliente.post("/api/v1/red/pin", json={}).status_code == 409


# ---------------------------------------------------------------------------
# Los datos del local
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("escrito,queda", [
    ("12345678-5", "12.345.678-5"), ("12.345.678-5", "12.345.678-5"),
    ("123456785", "12.345.678-5"), ("11111111-1", "11.111.111-1")])
def test_el_rut_queda_escrito_como_se_escribe_en_chile(escrito, queda):
    assert local.rut_normalizado(escrito) == queda


@pytest.mark.parametrize("malo", ["12345678-4", "11111111-2", "abc", "", "1-"])
def test_un_rut_con_el_digito_malo_no_pasa(malo):
    assert local.rut_normalizado(malo) is None


def test_sin_datos_la_caja_se_llama_como_siempre(cliente):
    assert cliente.get("/api/v1/local").json()["nombre"] == local.NOMBRE_POR_DEFECTO


def test_el_nombre_del_local_llega_a_todas_partes(cliente, carta, caja):
    """Hasta la 2.18 una cafetería nueva aparecía como «Kofe» en la caja, en el
    comprobante y en sus televisores."""
    r = cliente.put("/api/v1/local", json={"nombre": "Café Tito", "rut": "11.111.111-1",
                                           "direccion": "Av. Siempre Viva 742"})
    assert r.status_code == 200 and r.json()["rut"] == "11.111.111-1"
    assert cliente.get("/api/v1/carta").json()["local"] == "Café Tito"
    assert cliente.get("/api/v1/salud").json()["local"] == "Café Tito"
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    papel = cliente.get(f"/comprobante/{v['id']}").text
    assert "Café Tito" in papel and "RUT 11.111.111-1" in papel
    assert "Av. Siempre Viva 742" in papel


def test_un_rut_malo_no_se_guarda(cliente):
    assert cliente.put("/api/v1/local", json={"nombre": "X", "rut": "11111111-2"}).status_code == 422


def test_los_datos_del_local_los_cambia_el_dueno(cliente):
    _dueno(cliente)
    _cajero(cliente)
    assert cliente.put("/api/v1/local", json={"nombre": "Otro"}).status_code == 403


# ---------------------------------------------------------------------------
# Ajustes nuevos
# ---------------------------------------------------------------------------
def test_el_bloqueo_se_ajusta_entre_1_y_30_minutos(cliente):
    assert cliente.get("/api/v1/ajustes").json()["bloqueo_minutos"] == 3
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 45}).status_code == 422
    assert cliente.put("/api/v1/ajustes", json={"bloqueo_minutos": 5}).json()["bloqueo_minutos"] == 5


def test_el_canal_es_estable_o_piloto(cliente):
    assert cliente.get("/api/v1/ajustes").json()["canal_actualizaciones"] == "estable"
    assert cliente.put("/api/v1/ajustes", json={"canal_actualizaciones": "beta"}).status_code == 422
    assert cliente.put("/api/v1/ajustes", json={"canal_actualizaciones": "piloto"}).status_code == 200
    assert local.canal() == "piloto"


def test_una_carpeta_de_respaldo_que_no_existe_no_se_acepta(cliente, tmp_path):
    r = cliente.put("/api/v1/ajustes", json={"respaldo_afuera": str(tmp_path / "no-existe")})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# El respaldo de afuera
# ---------------------------------------------------------------------------
def test_el_respaldo_se_copia_afuera_y_se_revisa(cliente, carta, caja, tmp_path):
    """Hasta la 2.18 las 30 copias vivían en el mismo disco que la base."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    assert cliente.put("/api/v1/ajustes", json={"respaldo_afuera": str(tmp_path)}).status_code == 200
    r = cliente.post("/api/v1/respaldo").json()
    assert r["ok"] and r["afuera"]["ok"], r
    assert r["afuera"]["ventas"] == 1
    copias = list(tmp_path.rglob("pos-*.db"))
    assert len(copias) == 1 and "Kofe-respaldos" in str(copias[0])
    estado = cliente.get("/api/v1/ajustes").json()["respaldo_afuera_estado"]
    assert estado["ok"] and estado["carpeta"] == str(tmp_path)


def test_sin_carpeta_de_afuera_el_respaldo_lo_dice(cliente):
    r = cliente.post("/api/v1/respaldo").json()
    assert r["ok"] and r["afuera"] == {"configurado": False}


def test_restaurar_guarda_primero_lo_que_habia(tmp_path, monkeypatch):
    from tools import restaurar

    def contar(ruta):
        c = sqlite3.connect(ruta)
        try:
            return c.execute("SELECT COUNT(*) FROM venta").fetchone()[0]
        finally:
            c.close()

    actual, respaldo = tmp_path / "pos.db", tmp_path / "pos-2026-09-01.db"
    _base_de(str(actual), 5, "aaaa1111")
    _base_de(str(respaldo), 3, "aaaa1111")          # un respaldo de esta misma caja
    monkeypatch.setattr(restaurar, "ruta_de_la_base", lambda: str(actual))
    monkeypatch.setattr(restaurar, "CARPETA", str(tmp_path / "respaldos"))
    r = restaurar.restaurar(str(respaldo))
    assert r["ok"] and r["ventas"] == 3
    assert contar(str(actual)) == 3
    assert contar(r["guardada"]) == 5          # lo de antes no se perdió


def test_no_se_restaura_un_archivo_que_no_es_una_base(tmp_path):
    from tools import restaurar
    malo = tmp_path / "x.db"
    malo.write_bytes(b"no soy una base")
    assert restaurar.restaurar(str(malo))["ok"] is False


# ---------------------------------------------------------------------------
# El registro de errores
# ---------------------------------------------------------------------------
def _registro() -> str:
    from apps.pos import diagnostico
    for h in diagnostico.log.handlers:
        h.flush()
    try:
        with open(diagnostico.ARCHIVO, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def test_un_error_de_la_pantalla_queda_anotado(cliente):
    from apps.pos.api import diagnostico as api_diag
    api_diag._recientes.clear()
    r = cliente.post("/api/v1/diagnostico/evento",
                     json={"tipo": "error", "mensaje": "se cayó el cobro zq81", "donde": "app.js"})
    assert r.status_code == 204
    assert "se cayó el cobro zq81" in _registro()


def test_los_televisores_avisan_sin_pin(cliente):
    from apps.pos.api import diagnostico as api_diag
    api_diag._recientes.clear()
    with remoto() as r:
        assert r.post("/api/v1/diagnostico/evento",
                      json={"mensaje": "tv en blanco k27"}).status_code == 204
    assert "tv en blanco k27" in _registro()


def test_los_avisos_tienen_tope(cliente):
    """Un TV con un error en bucle no puede llenar el disco de la caja."""
    from apps.pos.api import diagnostico as api_diag
    api_diag._recientes.clear()
    for i in range(api_diag.TOPE_POR_MINUTO + 5):
        cliente.post("/api/v1/diagnostico/evento", json={"mensaje": f"inundacion-{i:03d}-w9"})
    assert _registro().count("-w9") == api_diag.TOPE_POR_MINUTO


def test_el_dueno_baja_el_diagnostico_sin_secretos(cliente):
    r = cliente.get("/api/v1/diagnostico")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        resumen = json.loads(z.read("resumen.json"))
    assert resumen["version"] and "base" in resumen
    assert local.pin_de_red() not in json.dumps(resumen)


def test_el_diagnostico_es_solo_del_dueno(cliente):
    _dueno(cliente)
    _cajero(cliente)
    assert cliente.get("/api/v1/diagnostico").status_code == 403


# ---------------------------------------------------------------------------
# La base
# ---------------------------------------------------------------------------
def test_la_base_trabaja_en_modo_wal(cliente):
    """Sin WAL, un informe largo frenaba los cobros hasta «database is locked»."""
    from apps.pos.db.session import engine
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"


# ---------------------------------------------------------------------------
# El archivo del contador
# ---------------------------------------------------------------------------
def test_el_archivo_del_contador_desglosa_el_pago_mixto(cliente, carta, caja):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],   # 3400
        "pagos": [{"medio": "efectivo", "monto": 2000}, {"medio": "debito", "monto": 1400}]})
    texto = cliente.get("/api/v1/exportar/ventas").content.decode("utf-8-sig")
    filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    cabecera, fila = filas[0], filas[1]
    assert fila[cabecera.index("Efectivo")] == "2000"
    assert fila[cabecera.index("Débito")] == "1400"
    assert fila[cabecera.index("Crédito")] == "0"


# ---------------------------------------------------------------------------
# La firma
# ---------------------------------------------------------------------------
def test_la_firma_da_lo_mismo_que_el_rfc_8032():
    s1 = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert firma.publica_de(s1).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert firma.firmar(s1, b"").hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    pub2 = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
    sig2 = bytes.fromhex(
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
    assert firma.verificar(pub2, b"\x72", sig2)
    assert not firma.verificar(pub2, b"\x73", sig2)


def test_una_firma_rota_no_revienta():
    assert firma.verificar(b"corta", b"x", b"y") is False
    assert firma.verificar(bytes(32), b"x", bytes(64)) is False


# ---------------------------------------------------------------------------
# Lo que encontró la revisión de Codex, y el asistente del primer arranque
# ---------------------------------------------------------------------------
def test_quien_cambia_el_pin_desde_un_tablet_no_queda_afuera(cliente):
    ana = _dueno(cliente)
    with remoto() as r:
        r.post("/entrar", data={"pin": local.PIN_DE_FABRICA}, follow_redirects=False)
        r.post("/api/v1/sesion/entrar", json={"usuario_id": ana["id"], "pin": "1234"})
        assert r.post("/api/v1/red/pin", json={}).status_code == 200
        assert r.get("/api/v1/turnos/actual").status_code == 200    # su galleta se renovó


def test_cambiar_de_carpeta_no_hereda_la_copia_de_la_otra(cliente, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    cliente.put("/api/v1/ajustes", json={"respaldo_afuera": str(a)})
    assert cliente.post("/api/v1/respaldo").json()["afuera"]["ok"]
    cliente.put("/api/v1/ajustes", json={"respaldo_afuera": str(b)})
    assert cliente.get("/api/v1/ajustes").json()["respaldo_afuera_estado"] == {"carpeta": str(b)}


def test_una_instalacion_nueva_abre_con_el_asistente(cliente):
    assert cliente.get("/api/v1/candado").json()["instalacion_nueva"] is True
    cliente.put("/api/v1/local", json={"nombre": "Café Tito"})
    assert cliente.get("/api/v1/candado").json()["instalacion_nueva"] is False


def test_una_caja_que_ya_vende_sin_usuarios_no_ve_el_asistente(cliente, carta, caja):
    """El lunes en la mañana tiene que poder cobrar, como siempre."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    assert cliente.get("/api/v1/candado").json()["instalacion_nueva"] is False


def test_desde_el_wifi_no_se_crea_el_primer_dueno(cliente):
    """Lo encontró la revisión de Codex: en una caja recién instalada el PIN de
    red es el de fábrica, el mismo en todas. Cualquiera en el Wi-Fi creaba el
    primer dueño con un PIN suyo y se quedaba con la caja."""
    with remoto() as r:
        r.post("/entrar", data={"pin": local.PIN_DE_FABRICA}, follow_redirects=False)
        assert r.post("/api/v1/usuarios", json={"nombre": "Intruso", "pin": "6666"}).status_code == 403
        assert r.post("/api/v1/red/pin", json={}).status_code == 403
        assert r.put("/api/v1/local", json={"nombre": "Otro"}).status_code == 403
        assert r.get("/api/v1/candado").json()["instalacion_nueva"] is False
        yo = r.get("/api/v1/sesion").json()
        assert yo["provisorio"] is True and yo["rol"] == "cajero"     # vende, no configura
    assert cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "1234"}).status_code == 200


def test_dos_locales_con_el_mismo_nombre_no_se_pisan_los_respaldos(cliente, tmp_path):
    """Lo encontró la revisión de Codex: dos sucursales que se llaman igual y
    comparten carpeta terminaban en el mismo archivo."""
    from tools import respaldo
    cliente.put("/api/v1/ajustes", json={"respaldo_afuera": str(tmp_path)})
    uno = cliente.post("/api/v1/respaldo").json()["afuera"]
    respaldo._guardar_ajuste("instalacion_id", "0000abcd")      # la otra sucursal
    otro = cliente.post("/api/v1/respaldo").json()["afuera"]
    assert uno["ok"] and otro["ok"]
    assert len(list(tmp_path.rglob("pos-*.db"))) == 2


def test_si_la_copia_de_afuera_falla_la_anterior_queda_entera(cliente, tmp_path, monkeypatch):
    """Lo encontró la revisión de Codex: la copia nueva se escribía encima de la
    buena, y un pendrive que se desconectaba a la mitad dejaba las dos rotas."""
    from tools import respaldo
    cliente.put("/api/v1/ajustes", json={"respaldo_afuera": str(tmp_path)})
    assert cliente.post("/api/v1/respaldo").json()["afuera"]["ok"]
    [copia] = list(tmp_path.rglob("pos-*.db"))
    antes = copia.read_bytes()

    def a_medias(origen, destino, *a, **k):
        with open(destino, "wb") as f:
            f.write(b"medio archivo")
        raise OSError("se desconecto el pendrive")

    monkeypatch.setattr(respaldo.shutil, "copy2", a_medias)
    assert cliente.post("/api/v1/respaldo").json()["afuera"]["ok"] is False
    assert copia.read_bytes() == antes
    assert not list(tmp_path.rglob("*kofe-parcial*"))


def _base_de(ruta, ventas, identidad):
    c = sqlite3.connect(ruta)
    c.execute("CREATE TABLE venta (id INTEGER)")
    c.execute("CREATE TABLE ajuste (clave TEXT PRIMARY KEY, valor TEXT)")
    c.executemany("INSERT INTO venta VALUES (?)", [(i,) for i in range(ventas)])
    c.execute("INSERT INTO ajuste VALUES ('instalacion_id', ?)", (identidad,))
    c.commit()
    c.close()


def test_no_se_restaura_encima_el_respaldo_de_otro_local(tmp_path, monkeypatch):
    from tools import restaurar
    actual, ajeno = tmp_path / "pos.db", tmp_path / "pos-2026-09-01.db"
    _base_de(str(actual), 5, "aaaa1111")
    _base_de(str(ajeno), 3, "bbbb2222")
    monkeypatch.setattr(restaurar, "ruta_de_la_base", lambda: str(actual))
    monkeypatch.setattr(restaurar, "CARPETA", str(tmp_path / "respaldos"))
    r = restaurar.restaurar(str(ajeno))
    assert r["ok"] is False and "otro local" in r["detalle"]
    assert restaurar.restaurar(str(ajeno), sin_revisar_local=True)["ok"]


def test_en_un_computador_nuevo_si_se_restaura(tmp_path, monkeypatch):
    """Se murió el computador y se instaló uno nuevo: tiene otra identidad, pero
    ni una venta. Restaurar ahí es justo para lo que existe esto."""
    from tools import restaurar
    actual, suyo = tmp_path / "pos.db", tmp_path / "pos-2026-09-01.db"
    _base_de(str(actual), 0, "aaaa1111")
    _base_de(str(suyo), 3, "bbbb2222")
    monkeypatch.setattr(restaurar, "ruta_de_la_base", lambda: str(actual))
    monkeypatch.setattr(restaurar, "CARPETA", str(tmp_path / "respaldos"))
    assert restaurar.restaurar(str(suyo))["ok"]


def test_un_respaldo_sin_identidad_no_se_pone_encima_de_una_caja_que_vende(tmp_path, monkeypatch):
    """Lo encontró la segunda revisión de Codex: sin identidad en el respaldo,
    la revisión dejaba pasar cualquiera."""
    from tools import restaurar
    actual, viejo = tmp_path / "pos.db", tmp_path / "pos-2026-08-01.db"
    _base_de(str(actual), 5, "aaaa1111")
    c = sqlite3.connect(str(viejo))
    c.execute("CREATE TABLE venta (id INTEGER)")
    c.commit()
    c.close()
    monkeypatch.setattr(restaurar, "ruta_de_la_base", lambda: str(actual))
    monkeypatch.setattr(restaurar, "CARPETA", str(tmp_path / "respaldos"))
    r = restaurar.restaurar(str(viejo))
    assert r["ok"] is False and "antes de la 2.19" in r["detalle"]
    assert restaurar.restaurar(str(viejo), sin_revisar_local=True)["ok"]


def test_hasta_el_primer_respaldo_lleva_la_identidad_de_su_caja(cliente):
    """Lo encontró la segunda revisión de Codex: la identidad se creaba al
    copiar afuera, DESPUÉS de sacar el respaldo, y sin carpeta de afuera no se
    creaba nunca."""
    from tools import respaldo
    r = cliente.post("/api/v1/respaldo").json()
    c = sqlite3.connect(os.path.join(respaldo.CARPETA, r["archivo"]))
    try:
        fila = c.execute("SELECT valor FROM ajuste WHERE clave = 'instalacion_id'").fetchone()
    finally:
        c.close()
    assert fila and len(fila[0]) == 8


def test_una_base_que_no_se_puede_contar_no_se_da_por_vacia(tmp_path, monkeypatch):
    """Lo encontró la tercera revisión de Codex: si contar las ventas fallaba,
    la caja se daba por vacía y se saltaba la revisión de identidad."""
    from tools import restaurar
    actual = tmp_path / "pos.db"
    c = sqlite3.connect(str(actual))
    c.execute("CREATE TABLE ajuste (clave TEXT PRIMARY KEY, valor TEXT)")   # sin tabla de ventas
    c.execute("INSERT INTO ajuste VALUES ('instalacion_id', 'aaaa1111')")
    c.commit()
    c.close()
    ajeno, suyo = tmp_path / "pos-ajeno.db", tmp_path / "pos-suyo.db"
    _base_de(str(ajeno), 3, "bbbb2222")
    _base_de(str(suyo), 3, "aaaa1111")
    monkeypatch.setattr(restaurar, "ruta_de_la_base", lambda: str(actual))
    monkeypatch.setattr(restaurar, "CARPETA", str(tmp_path / "respaldos"))
    r = restaurar.restaurar(str(ajeno))
    assert r["ok"] is False and "no se pudo leer" in r["detalle"]
    assert restaurar.restaurar(str(suyo))["ok"]          # su propio respaldo la arregla
