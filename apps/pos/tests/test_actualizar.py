"""El actualizador toca código y NADA más.

Estos tests existen porque un actualizador mal hecho borra las ventas del local.
Cada uno cuida una lección concreta que ya se pagó en la Biblioteca Láser.
"""
import hashlib
import io
import json
import os
import zipfile

import pytest

from apps.pos import actualizar, firma, vuelta

# Desde la 2.19 la caja solo instala paquetes firmados. Las pruebas firman con
# esta llave de mentira y le enseñan a la caja a confiar en ella (ver `local`).
LLAVE_DE_PRUEBA = bytes(range(32))


def zip_falso(archivos: dict, prefijo: str = "Punto-de-venta/", version: str = "99.0",
              firmar: bool = True, llave: bytes = LLAVE_DE_PRUEBA) -> bytes:
    """Un paquete como el que se publica: todo colgando de una carpeta, con su
    manifiesto firmado. El manifiesto lista lo que la caja instalaría, igual que
    tools/firmar_version.py."""
    buf = io.BytesIO()
    huellas = {}
    with zipfile.ZipFile(buf, "w") as z:
        for ruta, contenido in archivos.items():
            datos = contenido.encode("utf-8") if isinstance(contenido, str) else contenido
            z.writestr(prefijo + ruta, datos)
            if actualizar.se_instala(ruta) and actualizar._ruta_segura(ruta):
                huellas[ruta] = hashlib.sha256(datos).hexdigest()
        if firmar:
            manifiesto = json.dumps({"version": version, "archivos": huellas},
                                    sort_keys=True).encode("utf-8")
            z.writestr(prefijo + actualizar.MANIFIESTO, manifiesto)
            z.writestr(prefijo + actualizar.FIRMA_ARCHIVO, firma.firmar(llave, manifiesto).hex())
    return buf.getvalue()


def reempaquetar(original: bytes, cambiar=None, agregar=None) -> bytes:
    """El mismo paquete, tocado DESPUÉS de firmar: lo que haría un atacante."""
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as viejo, zipfile.ZipFile(buf, "w") as z:
        for n in viejo.namelist():
            datos = viejo.read(n)
            for final, nuevo in (cambiar or {}).items():
                if n.endswith(final):
                    datos = nuevo
            z.writestr(n, datos)
        for n, datos in (agregar or {}).items():
            z.writestr(n, datos)
    return buf.getvalue()


@pytest.fixture()
def local(tmp_path, monkeypatch):
    """Una instalación de mentira, con datos del local adentro."""
    monkeypatch.setattr(actualizar, "RAIZ", str(tmp_path))
    monkeypatch.setattr(actualizar, "LLAVES_PUBLICAS", (firma.publica_de(LLAVE_DE_PRUEBA).hex(),))
    (tmp_path / "apps" / "pos" / "api").mkdir(parents=True)
    (tmp_path / "respaldos").mkdir()
    (tmp_path / "apps" / "pos" / "main.py").write_text("viejo", encoding="utf-8")
    (tmp_path / "pos.db").write_bytes(b"LAS VENTAS DEL LOCAL")
    (tmp_path / "respaldos" / "pos-2026-08-01.db").write_bytes(b"UNA COPIA")
    return tmp_path


def descargando(monkeypatch, datos: bytes):
    class Falso:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return datos if n is None or n < 0 else datos[:n]
    monkeypatch.setattr(actualizar.urllib.request, "urlopen", lambda *a, **k: Falso())


# ------------------------------------------------------------------ lo esencial
def test_nunca_toca_la_base_de_ventas(local, monkeypatch):
    """Si un día esto falla, el local pierde su historial. Es EL test."""
    descargando(monkeypatch, zip_falso({
        "apps/pos/main.py": "nuevo",
        "pos.db": "BASE DEL DESARROLLADOR",          # jamás debe pisar la del local
    }))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert (local / "pos.db").read_bytes() == b"LAS VENTAS DEL LOCAL"


def test_nunca_toca_los_respaldos(local, monkeypatch):
    descargando(monkeypatch, zip_falso({
        "apps/pos/main.py": "nuevo",
        "respaldos/pos-2026-08-01.db": "otra cosa",
    }))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert (local / "respaldos" / "pos-2026-08-01.db").read_bytes() == b"UNA COPIA"


def test_un_archivo_nuevo_en_una_subcarpeta_si_llega(local, monkeypatch):
    """La lección de la Biblioteca Láser: publicaron un módulo nuevo y no llegó,
    porque el actualizador solo miraba la raíz del paquete."""
    descargando(monkeypatch, zip_falso({
        "apps/pos/api/boletas.py": "modulo nuevo",
        "apps/pos/main.py": "nuevo",
    }))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert r["ok"]
    assert (local / "apps" / "pos" / "api" / "boletas.py").read_text(encoding="utf-8") == "modulo nuevo"


def test_guarda_la_version_anterior(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    copia = local / actualizar.RESPALDO / "apps" / "pos" / "main.py"
    assert copia.read_text(encoding="utf-8") == "viejo"
    assert (local / "apps" / "pos" / "main.py").read_text(encoding="utf-8") == "nuevo"


def test_no_reescribe_lo_que_ya_esta_igual(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "viejo"}))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert r["archivos"] == []
    assert r.get("sin_cambios")


def test_no_deja_escribir_fuera_de_la_carpeta(local, monkeypatch):
    """Un ZIP con ../ podría pisar archivos de todo el computador."""
    descargando(monkeypatch, zip_falso({"../../robado.py": "malicioso"}))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert not (local.parent / "robado.py").exists()


def test_ignora_archivos_que_no_son_del_programa(local, monkeypatch):
    descargando(monkeypatch, zip_falso({
        "apps/pos/main.py": "nuevo",
        "algo.exe": "binario",
        "foto.png": "imagen",
    }))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert r["archivos"] == ["apps/pos/main.py"]
    assert not (local / "algo.exe").exists()


def test_paquete_de_github_tambien_sirve(local, monkeypatch):
    """GitHub entrega el ZIP con la carpeta 'repo-main/' adentro."""
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "desde github"},
                                       prefijo="pos-cafeteria-main/"))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert (local / "apps" / "pos" / "main.py").read_text(encoding="utf-8") == "desde github"


def test_un_zip_roto_no_rompe_nada(local, monkeypatch):
    descargando(monkeypatch, b"esto no es un zip")
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert "error" in r
    assert (local / "apps" / "pos" / "main.py").read_text(encoding="utf-8") == "viejo"


def test_solo_descarga_por_https(local):
    assert "error" in actualizar.aplicar("http://sin-cifrar.cl/p.zip")
    assert "error" in actualizar.aplicar("file:///C:/algo.zip")
    assert "error" in actualizar.aplicar("http://192.168.1.50/p.zip")


def test_el_mismo_computador_si_puede_servir_una_prueba(local, monkeypatch):
    """Se permite para probar una actualización antes de publicarla."""
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "probando"}))
    assert actualizar.aplicar("http://127.0.0.1:9000/p.zip").get("ok")


# ------------------------------------------------------------------ versiones
@pytest.mark.parametrize("a,b", [("1.1", "1.0"), ("2.10", "2.9"), ("1.0.1", "1.0"), ("10.0", "9.9")])
def test_compara_versiones_por_numero_no_por_texto(a, b):
    """'2.10' es MAYOR que '2.9', aunque como texto vaya antes."""
    assert actualizar._tupla(a) > actualizar._tupla(b)


def test_revisar_avisa_si_no_hay_internet(monkeypatch):
    def revienta(*a, **k):
        raise OSError("sin red")
    monkeypatch.setattr(actualizar.urllib.request, "urlopen", revienta)
    r = actualizar.revisar()
    assert "internet" in r["error"].lower()


def test_revisar_detecta_que_hay_una_nueva(monkeypatch):
    import json

    class Falso:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1):
            return json.dumps({"version": "999.0", "nombre": "De prueba",
                               "novedades": "algo", "zip": "https://x/p.zip"}).encode()
    monkeypatch.setattr(actualizar.urllib.request, "urlopen", lambda *a, **k: Falso())
    r = actualizar.revisar()
    assert r["ok"] and r["hay_nueva"] and r["disponible"] == "999.0"


# ------------------------------------------------------------------ por la API
def test_la_api_informa_la_version(cliente):
    v = cliente.get("/api/v1/version").json()
    assert v["version"] and v["nombre"]


# ---------------------------------------------------------------------------
# Quién puede actualizar la caja, y desde dónde
# ---------------------------------------------------------------------------
"""Antes POST /actualizacion instalaba el zip de CUALQUIER dirección que viniera
en la petición, y no pedía sesión. Con el PIN de red, que viene igual en todas
las cajas, cualquiera en el Wi-Fi del local podía instalarle un programa ajeno."""


def _canal(monkeypatch, pedidas):
    """El canal oficial de mentira: dice que hay versión nueva y anota qué se
    mandó a instalar. `archivos` vacío para que la prueba no reinicie nada."""
    monkeypatch.setattr(actualizar, "revisar",
                        lambda: {"ok": True, "hay_nueva": True,
                                 "zip": "https://github.com/oficial/main.zip"})
    monkeypatch.setattr(actualizar, "aplicar",
                        lambda url, **k: pedidas.append(url) or {"ok": True, "archivos": []})


def test_la_caja_solo_se_actualiza_desde_el_canal_oficial(cliente, monkeypatch):
    pedidas = []
    _canal(monkeypatch, pedidas)
    r = cliente.post("/api/v1/actualizacion", json={"zip": "https://atacante.cl/malo.zip"})
    assert r.status_code == 200, r.text
    assert pedidas == ["https://github.com/oficial/main.zip"]


def test_un_cajero_no_puede_actualizar_la_caja(cliente, monkeypatch):
    pedidas = []
    _canal(monkeypatch, pedidas)
    ana = cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": ana["id"], "pin": "1234"})
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    assert cliente.post("/api/v1/actualizacion", json={}).status_code == 403
    assert pedidas == []


def test_el_dueno_si_puede_actualizar(cliente, monkeypatch):
    pedidas = []
    _canal(monkeypatch, pedidas)
    ana = cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": ana["id"], "pin": "1234"})
    assert cliente.post("/api/v1/actualizacion", json={}).status_code == 200
    assert pedidas == ["https://github.com/oficial/main.zip"]


# ---------------------------------------------------------------------------
# La firma (2.19)
# ---------------------------------------------------------------------------
"""Hasta la 2.18 la caja instalaba lo que publicara la cuenta de GitHub. Si esa
cuenta caía, cada local instalaba lo que el atacante quisiera, todos a la vez."""


def _main(local):
    return (local / "apps" / "pos" / "main.py").read_text(encoding="utf-8")


def test_un_paquete_sin_firma_no_se_instala(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}, firmar=False))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert "firmado" in r["error"]
    assert _main(local) == "viejo"


def test_un_paquete_firmado_con_otra_llave_no_se_instala(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}, llave=bytes(32)))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert "no es la de Caja Clara" in r["error"]
    assert _main(local) == "viejo"


def test_un_archivo_cambiado_despues_de_firmar_no_se_instala(local, monkeypatch):
    """Y no se instala NADA: se revisa todo antes de escribir el primer archivo."""
    bueno = zip_falso({"apps/pos/main.py": "nuevo", "apps/pos/api/x.py": "x"})
    descargando(monkeypatch, reempaquetar(bueno, cambiar={"api/x.py": b"malicioso"}))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert "no es el que se firmó" in r["error"]
    assert _main(local) == "viejo"
    assert not (local / "apps" / "pos" / "api" / "x.py").exists()


def test_un_archivo_agregado_sin_firmar_no_se_instala(local, monkeypatch):
    bueno = zip_falso({"apps/pos/main.py": "nuevo"})
    descargando(monkeypatch, reempaquetar(
        bueno, agregar={"Punto-de-venta/apps/pos/puerta.py": b"puerta trasera"}))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert "no se firmó" in r["error"]
    assert not (local / "apps" / "pos" / "puerta.py").exists()


def test_no_se_instala_una_version_vieja_aunque_venga_firmada(local, monkeypatch):
    """Un paquete viejo, firmado de verdad, serviría para volver a meter un
    error que ya se arregló."""
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}, version="1.0"))
    assert "no es más nueva" in actualizar.aplicar("https://ejemplo.cl/p.zip")["error"]
    assert _main(local) == "viejo"


def test_el_paquete_tiene_que_ser_la_version_anunciada(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}, version="99.0"))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip", version_esperada="98.0")
    assert "se esperaba" in r["error"]


def test_la_llave_de_verdad_esta_en_la_caja():
    """Si la tupla quedara vacía o con basura, ninguna caja aceptaría nada."""
    assert actualizar.LLAVES_PUBLICAS
    assert all(len(bytes.fromhex(k)) == 32 for k in actualizar.LLAVES_PUBLICAS)


def test_lo_que_empieza_con_punto_o_es_la_copia_anterior_no_se_instala():
    assert not actualizar.se_instala(".claude/launch.json")
    assert not actualizar.se_instala("_version_anterior/apps/pos/main.py")
    assert not actualizar.se_instala("../../robado.py")
    assert actualizar.se_instala("apps/pos/main.py")


# ---------------------------------------------------------------------------
# Volver a la versión anterior (2.19)
# ---------------------------------------------------------------------------
def test_se_puede_volver_a_la_version_anterior(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo",
                                        "apps/pos/api/boletas.py": "módulo nuevo"}))
    assert actualizar.aplicar("https://ejemplo.cl/p.zip")["ok"]
    assert actualizar.hay_vuelta()["disponible"]
    r = actualizar.volver_atras()
    assert r["ok"]
    assert _main(local) == "viejo"
    assert not (local / "apps" / "pos" / "api" / "boletas.py").exists()
    # Volver dos veces con la misma copia desharía la vuelta.
    assert not actualizar.hay_vuelta()["disponible"]


def test_la_copia_anterior_es_solo_de_la_ultima_actualizacion(local, monkeypatch):
    """Si se acumularan copias de varias actualizaciones, volver mezclaría versiones."""
    (local / "apps" / "pos" / "otro.py").write_text("otro viejo", encoding="utf-8")
    descargando(monkeypatch, zip_falso({"apps/pos/otro.py": "otro nuevo"}))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo",
                                        "apps/pos/otro.py": "otro nuevo"}))
    actualizar.aplicar("https://ejemplo.cl/p.zip")
    actualizar.volver_atras()
    assert (local / "apps" / "pos" / "otro.py").read_text(encoding="utf-8") == "otro nuevo"
    assert _main(local) == "viejo"


def test_volver_atras_es_del_dueno(cliente):
    ana = cliente.post("/api/v1/usuarios", json={"nombre": "Ana", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": ana["id"], "pin": "1234"})
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    assert cliente.post("/api/v1/actualizacion/volver").status_code == 403
    assert "disponible" in cliente.get("/api/v1/actualizacion/vuelta").json()


# ---------------------------------------------------------------------------
# Canales y clave de descarga (2.19)
# ---------------------------------------------------------------------------
def test_el_canal_piloto_lee_otro_archivo():
    assert actualizar.url_del_canal("piloto").endswith("version-piloto.json")
    assert actualizar.url_del_canal("estable").endswith("version.json")


def test_con_clave_de_descarga_se_baja_por_la_api(monkeypatch):
    """Para el día que el repositorio pase a privado: una clave por local."""
    pedidas = []

    class Falso:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return b"{}"

    def urlopen(req, timeout=None):
        pedidas.append((req.full_url, req.get_header("Authorization")))
        return Falso()

    monkeypatch.setattr(actualizar.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("POS_CLAVE_DESCARGA", "abc123")
    actualizar._pedir("https://github.com/Pacmancinya/pos-cafeteria/archive/refs/tags/v2.19.zip", 5)
    assert pedidas[-1] == ("https://api.github.com/repos/Pacmancinya/pos-cafeteria/zipball/refs/tags/v2.19",
                           "token abc123")
    actualizar._pedir("https://raw.githubusercontent.com/Pacmancinya/pos-cafeteria/main/version.json", 5)
    assert pedidas[-1][1] == "token abc123"
    monkeypatch.delenv("POS_CLAVE_DESCARGA")
    actualizar._pedir("https://github.com/x/y/archive/refs/tags/v1.zip", 5)
    assert pedidas[-1] == ("https://github.com/x/y/archive/refs/tags/v1.zip", None)


def _otro(local):
    return (local / "apps" / "pos" / "otro.py").read_text(encoding="utf-8")


def _falla_en_otro(real, error=OSError("disco lleno")):
    """Falla UNA vez al poner otro.py: un disco que se llenó y después se
    liberó un poco. Si fallara siempre, tampoco se podría volver atrás al tiro
    (eso lo cubre el reintento, más abajo)."""
    ya = []

    def reemplazar(origen, destino):
        if str(destino).endswith("otro.py") and not ya:
            ya.append(True)
            raise error
        return real(origen, destino)
    return reemplazar


def test_si_el_disco_falla_a_la_mitad_se_vuelve_atras_al_tiro(local, monkeypatch):
    """Lo encontró la revisión de Codex: a mitad de camino la caja quedaba con
    código de dos versiones."""
    (local / "apps" / "pos" / "otro.py").write_text("otro viejo", encoding="utf-8")
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo",
                                        "apps/pos/nuevo.py": "nuevo",
                                        "apps/pos/otro.py": "otro nuevo"}))
    monkeypatch.setattr(actualizar.os, "replace", _falla_en_otro(os.replace))
    r = actualizar.aplicar("https://ejemplo.cl/p.zip")
    assert "como estaba" in r["error"]
    assert _main(local) == "viejo" and _otro(local) == "otro viejo"
    assert not (local / "apps" / "pos" / "nuevo.py").exists()
    assert not list(local.rglob("*.kofe-nuevo"))


def test_si_se_corta_la_luz_a_la_mitad_la_caja_se_arregla_al_abrir(local, monkeypatch):
    (local / "apps" / "pos" / "otro.py").write_text("otro viejo", encoding="utf-8")
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo",
                                        "apps/pos/otro.py": "otro nuevo"}))

    class Corte(BaseException):
        """Un corte de luz: nada de lo que viene después alcanza a correr."""

    real = os.replace
    monkeypatch.setattr(actualizar.os, "replace", _falla_en_otro(real, Corte()))
    with pytest.raises(Corte):
        actualizar.aplicar("https://ejemplo.cl/p.zip")
    monkeypatch.setattr(actualizar.os, "replace", real)
    assert _main(local) == "nuevo"                     # quedó a medias
    r = vuelta.recuperar(str(local))                   # lo que corre al abrir
    assert r["ok"]
    assert _main(local) == "viejo" and _otro(local) == "otro viejo"
    assert not list(local.rglob("*.kofe-nuevo"))
    assert vuelta.recuperar(str(local)) is None        # y una sola vez


def test_una_actualizacion_completa_no_se_deshace_al_abrir(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}))
    assert actualizar.aplicar("https://ejemplo.cl/p.zip")["ok"]
    assert vuelta.recuperar(str(local)) is None
    assert _main(local) == "nuevo"
    assert actualizar.hay_vuelta()["disponible"]


def test_reintentar_una_instalacion_a_medias_no_pierde_los_originales(local, monkeypatch):
    """Lo encontró la revisión de Codex: al reintentar se borraba la copia, y lo
    que ya se había instalado se saltaba por estar «igual»: sus originales se
    perdían."""
    (local / "apps" / "pos" / "otro.py").write_text("otro viejo", encoding="utf-8")
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo",
                                        "apps/pos/otro.py": "otro nuevo"}))
    real_replace, real_volver = os.replace, vuelta.volver
    monkeypatch.setattr(actualizar.os, "replace", _falla_en_otro(real_replace))
    monkeypatch.setattr(vuelta, "volver", lambda raiz: {"error": "tampoco"})
    assert "ábrelo de nuevo" in actualizar.aplicar("https://ejemplo.cl/p.zip")["error"]
    assert _main(local) == "nuevo"                     # quedó a medias
    monkeypatch.setattr(actualizar.os, "replace", real_replace)
    monkeypatch.setattr(vuelta, "volver", real_volver)
    assert actualizar.aplicar("https://ejemplo.cl/p.zip")["ok"]
    assert actualizar.volver_atras()["ok"]
    assert _main(local) == "viejo" and _otro(local) == "otro viejo"


def test_reinstalar_lo_mismo_no_borra_la_vuelta_atras(local, monkeypatch):
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}))
    assert actualizar.aplicar("https://ejemplo.cl/p.zip")["ok"]
    assert actualizar.aplicar("https://ejemplo.cl/p.zip").get("sin_cambios")
    assert actualizar.volver_atras()["ok"]
    assert _main(local) == "viejo"


def test_un_paquete_gigante_se_rechaza_sin_abrirlo(local, monkeypatch):
    """Lo encontró la revisión de Codex: sin topes, un paquete sin firma podía
    reventar la memoria de la caja antes de que se revisara la firma."""
    monkeypatch.setattr(actualizar, "TOPE_EXPANDIDO", 10)
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "x" * 100}))
    assert "demasiado grande" in actualizar.aplicar("https://ejemplo.cl/p.zip")["error"]
    assert _main(local) == "viejo"


def test_una_descarga_gigante_se_corta(local, monkeypatch):
    monkeypatch.setattr(actualizar, "TOPE_DESCARGA", 10)
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}))
    assert "pesa más" in actualizar.aplicar("https://ejemplo.cl/p.zip")["error"]
    assert _main(local) == "viejo"


def test_la_caja_revisa_al_abrir_si_una_actualizacion_quedo_a_medias():
    import apps.pos
    assert "recuperar" in io.open(apps.pos.__file__, encoding="utf-8").read()
    assert apps.pos.RECUPERACION is None               # en este repositorio no hay nada a medias


def test_si_se_corta_la_luz_al_volver_atras_se_termina_al_abrir(local, monkeypatch):
    """Lo encontró la segunda revisión de Codex: la vuelta atrás escribía encima
    de cada archivo, y si se cortaba entre dos, la lista seguía diciendo
    «completa» y al abrir nadie terminaba la vuelta."""
    (local / "apps" / "pos" / "otro.py").write_text("otro viejo", encoding="utf-8")
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo",
                                        "apps/pos/otro.py": "otro nuevo"}))
    assert actualizar.aplicar("https://ejemplo.cl/p.zip")["ok"]

    class Corte(BaseException):
        """Un corte de luz: nada de lo que viene después alcanza a correr."""

    real = os.replace
    monkeypatch.setattr(vuelta.os, "replace", _falla_en_otro(real, Corte()))
    with pytest.raises(Corte):
        actualizar.volver_atras()
    monkeypatch.setattr(vuelta.os, "replace", real)
    assert _main(local) == "viejo" and _otro(local) == "otro nuevo"     # a medias
    assert vuelta.recuperar(str(local))["ok"]                         # al abrir
    assert _main(local) == "viejo" and _otro(local) == "otro viejo"
    assert not list(local.rglob("*.kofe-nuevo"))


def test_la_vuelta_atras_no_pone_una_copia_danada(local, monkeypatch):
    """Lo encontró la tercera revisión de Codex: la copia del original se
    guardaba sin asegurarla en el disco y se ponía de vuelta sin revisarla."""
    descargando(monkeypatch, zip_falso({"apps/pos/main.py": "nuevo"}))
    assert actualizar.aplicar("https://ejemplo.cl/p.zip")["ok"]
    (local / actualizar.RESPALDO / "apps" / "pos" / "main.py").write_bytes(b"")   # a medias
    r = actualizar.volver_atras()
    assert "dañada" in r["error"]
    assert _main(local) == "nuevo"                       # no se tocó nada
    assert actualizar.hay_vuelta()["disponible"]
