"""El actualizador toca código y NADA más.

Estos tests existen porque un actualizador mal hecho borra las ventas del local.
Cada uno cuida una lección concreta que ya se pagó en la Biblioteca Láser.
"""
import io
import os
import zipfile

import pytest

from apps.pos import actualizar


def zip_falso(archivos: dict) -> bytes:
    """Un paquete como el que se publica: todo colgando de una carpeta."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for ruta, contenido in archivos.items():
            z.writestr("Punto-de-venta/" + ruta, contenido)
    return buf.getvalue()


@pytest.fixture()
def local(tmp_path, monkeypatch):
    """Una instalación de mentira, con datos del local adentro."""
    monkeypatch.setattr(actualizar, "RAIZ", str(tmp_path))
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
        def read(self): return datos
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Punto-de-venta/../../robado.py", "malicioso")
    descargando(monkeypatch, buf.getvalue())
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pos-cafeteria-main/apps/pos/main.py", "desde github")
    descargando(monkeypatch, buf.getvalue())
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
        def read(self):
            return json.dumps({"version": "999.0", "nombre": "De prueba",
                               "novedades": "algo", "zip": "https://x/p.zip"}).encode()
    monkeypatch.setattr(actualizar.urllib.request, "urlopen", lambda *a, **k: Falso())
    r = actualizar.revisar()
    assert r["ok"] and r["hay_nueva"] and r["disponible"] == "999.0"


# ------------------------------------------------------------------ por la API
def test_la_api_informa_la_version(cliente):
    v = cliente.get("/api/v1/version").json()
    assert v["version"] and v["nombre"]
