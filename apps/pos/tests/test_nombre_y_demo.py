"""2.31: el producto pasa a llamarse Caja Clara sin tocar el nombre de ningún local, y el
modo demo (MODO-DEMO.txt) siembra una caja de muestra sin poder tocar una de verdad."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, select

RAIZ = Path(__file__).resolve().parents[3]
DEMO = RAIZ / "despliegue" / "demo"


@pytest.fixture()
def base():
    import apps.pos.db.models  # noqa: F401  registra las tablas antes de crearlas
    from apps.pos.db.session import engine
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


def _un_producto(engine) -> None:
    from apps.pos.db.models import Categoria, Producto
    with Session(engine) as s:
        c = Categoria(nombre="Café", orden=0)
        s.add(c)
        s.commit()
        s.refresh(c)
        s.add(Producto(categoria_id=c.id, nombre="Espresso", precio=1900))
        s.commit()


# ---------------------------------------------------------------------------
# El nombre del local no cambia con el del producto
# ---------------------------------------------------------------------------
def test_una_caja_en_uso_sin_nombre_guardado_sigue_llamandose_kofe(base):
    # Hasta la 2.30 el nombre de fábrica era «Kofe», y es el nombre de un local real:
    # una caja que ya vende y nunca guardó su nombre tiene que seguir diciendo eso.
    from apps.pos import local
    from apps.pos.db.models import Ajuste
    from apps.pos.db.session import crear_tablas
    _un_producto(base)
    crear_tablas()
    assert local.nombre() == "Kofe"
    with Session(base) as s:
        assert s.get(Ajuste, "local_nombre").valor == "Kofe"


def test_una_caja_nueva_parte_como_mi_local_y_no_guarda_nada(base):
    from apps.pos import local
    from apps.pos.db.models import Ajuste
    from apps.pos.db.session import crear_tablas
    crear_tablas()
    assert local.nombre() == "Mi local"
    with Session(base) as s:
        assert s.get(Ajuste, "local_nombre") is None


def test_un_nombre_guardado_no_se_toca(base):
    from apps.pos import local
    from apps.pos.db.session import crear_tablas
    with Session(base) as s:
        local.guardar(s, local_nombre="Panadería Sol")
    _un_producto(base)
    crear_tablas()
    assert local.nombre() == "Panadería Sol"


def test_el_titulo_y_el_acceso_directo_de_las_cajas_instaladas_no_cambian():
    # Kofe.py congelado arma el título y el acceso directo con este valor.
    from core import config
    assert config.NOMBRE_LOCAL == "Kofe"


# ---------------------------------------------------------------------------
# El ejecutable nuevo (CajaClara.exe) y el de las cajas instaladas (Kofe.exe)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", ["CajaClara.exe", "Kofe.exe"])
def test_el_acceso_directo_apunta_al_exe_que_esta_corriendo(tmp_path, monkeypatch, nombre):
    from tools import acceso_directo
    exe = tmp_path / nombre
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert acceso_directo._destino() == (str(exe), "")


def test_sin_exe_conocido_busca_primero_cajaclara_en_la_carpeta(tmp_path, monkeypatch):
    from tools import acceso_directo
    for n in ("CajaClara.exe", "Kofe.exe"):
        (tmp_path / n).write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "otro.exe"))
    monkeypatch.setattr(acceso_directo, "RAIZ", str(tmp_path))
    assert acceso_directo._destino() == (str(tmp_path / "CajaClara.exe"), "")


@pytest.mark.parametrize("exe,esperado", [("CajaClara.exe", "Caja Clara"),
                                          ("Kofe.exe", "Kofe - Punto de venta")])
def test_el_acceso_directo_se_llama_como_siempre_salvo_en_instalaciones_nuevas(
        tmp_path, monkeypatch, exe, esperado):
    # Renombrar el de una caja instalada le dejaría dos iconos en el escritorio.
    from tools import acceso_directo
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / exe))
    assert acceso_directo._nombre() == esperado


def test_la_ventana_nueva_se_busca_con_el_mismo_titulo_con_que_se_crea():
    texto = (RAIZ / "Kofe.py").read_text(encoding="utf-8")
    assert texto.count("_titulo()") >= 2          # al crearla y al traerla al frente
    assert 'return "Caja Clara"' in texto


def test_el_instalador_nuevo_se_llama_caja_clara():
    texto = (RAIZ / "despliegue" / "construir_exe.py").read_text(encoding="utf-8")
    assert 'NOMBRE = "CajaClara"' in texto
    assert '"caja-clara.ico"' in texto
    assert (RAIZ / "despliegue" / "icono" / "caja-clara.svg").exists()


# ---------------------------------------------------------------------------
# Modo demo
# ---------------------------------------------------------------------------
def test_el_repositorio_nunca_trae_la_marca_de_demo_en_la_raiz():
    # La marca vive en despliegue/demo (que el actualizador no copia nunca);
    # en la raíz convertiría cualquier caja en demo.
    from core import config
    assert not (RAIZ / "MODO-DEMO.txt").exists()
    assert config.modo_demo() is False
    from apps.pos import actualizar
    assert "despliegue" in actualizar.CARPETAS_PROTEGIDAS


def test_sin_la_marca_no_se_siembra_nada(base, monkeypatch):
    from tools.demo import inicio
    monkeypatch.setattr(inicio, "modo_demo", lambda: False)
    assert inicio.preparar() is False
    assert inicio.base_vacia()


def test_con_la_marca_y_la_base_vacia_se_siembra_una_sola_vez(base, monkeypatch):
    from apps.pos import local, sesion
    from apps.pos.db.models import Producto, Turno, Usuario, Venta
    from tools.demo import inicio
    monkeypatch.setattr(inicio, "modo_demo", lambda: True)
    assert inicio.preparar() is True
    with Session(base) as s:
        assert s.exec(select(Producto)).first() is not None
        assert s.exec(select(Venta)).first() is not None
        gente = {u.nombre: u for u in s.exec(select(Usuario)).all()}
        assert set(gente) == {"Ana", "Luis"}
        assert gente["Ana"].rol == "dueno" and sesion.pin_calza("1111", gente["Ana"].pin_hash)
        assert gente["Luis"].rol == "cajero" and sesion.pin_calza("2222", gente["Luis"].pin_hash)
        # la caja de hoy queda abierta, lista para vender
        assert s.exec(select(Turno).where(Turno.cerrado_at == None)).first() is not None  # noqa: E711
    assert local.nombre() == "Café de ejemplo"
    assert not local.pin_es_de_fabrica()
    assert inicio.preparar() is False


def test_con_la_marca_no_siembra_sobre_datos_de_verdad(base, monkeypatch):
    from apps.pos.db.models import Producto
    from tools.demo import inicio
    _un_producto(base)
    monkeypatch.setattr(inicio, "modo_demo", lambda: True)
    assert inicio.preparar() is False
    with Session(base) as s:
        assert len(s.exec(select(Producto)).all()) == 1


def test_la_caja_muestra_demo_solo_en_modo_demo(cliente, monkeypatch):
    from apps.pos import main
    assert "marca-demo" not in cliente.get("/").text
    assert "__MARCA_DEMO__" not in cliente.get("/").text
    monkeypatch.setattr(main, "modo_demo", lambda: True)
    assert "marca-demo" in cliente.get("/").text


def test_el_comprobante_dice_demo_solo_en_modo_demo(cliente, carta, caja, monkeypatch):
    from apps.pos.api import impresion
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    assert "DEMO" not in cliente.get(f"/comprobante/{v['id']}").text
    monkeypatch.setattr(impresion, "modo_demo", lambda: True)
    assert "DEMO" in cliente.get(f"/comprobante/{v['id']}").text


def test_reiniciar_demo_se_niega_fuera_de_una_demo():
    bat = (DEMO / "REINICIAR-DEMO.bat").read_bytes()
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")   # CRLF: cmd y los goto
    texto = bat.decode("ascii")
    # Las dos comprobaciones van ANTES de cerrar la caja o borrar algo.
    primer_peligro = min(texto.index("taskkill"), texto.index("del /q"))
    assert texto.index('if not exist "MODO-DEMO.txt" goto no_es_demo') < primer_peligro
    assert texto.index('if not exist "CajaClara.exe" goto no_es_demo') < primer_peligro
    assert 'cd /d "%~dp0."' in texto


def test_el_paquete_de_demo_trae_sus_tres_archivos():
    for n in ("MODO-DEMO.txt", "REINICIAR-DEMO.bat", "LEEME-DEMO.txt"):
        assert (DEMO / n).exists(), n
    leeme = (DEMO / "LEEME-DEMO.txt").read_text(encoding="utf-8")
    assert "1111" in leeme and "2222" in leeme
    assert os.path.basename(str(DEMO)) == "demo"
