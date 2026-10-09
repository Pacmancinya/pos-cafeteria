"""La pestaña Config: lo que se puede comprobar sin navegador.

La lógica sin pantalla (buscador de ajustes sin tildes, vista previa del ticket, direcciones de los
televisores, filtro de respaldos…) corre con Node. Lo que se ve de verdad se midió con
tools/pantallas/auditar.py.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ESTATICOS = Path(__file__).resolve().parents[1] / "static"
HTML = io.open(ESTATICOS / "index.html", encoding="utf-8").read()
JS = io.open(ESTATICOS / "config.js", encoding="utf-8").read()
APP = io.open(ESTATICOS / "app.js", encoding="utf-8").read()


def test_la_logica_de_config_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node")
    r = subprocess.run([node, str(Path(__file__).with_name("config_logica.cjs"))],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_los_archivos_nuevos_se_piden_con_la_version():
    """Sin el ?v= la caja se actualiza y sigue mostrando la pantalla vieja (pasó en la 2.29)."""
    for archivo in ("config.css", "config-logica.js", "config.js"):
        assert f'/static/{archivo}?v=__VERSION__' in HTML, archivo
    assert HTML.index("config-logica.js") < HTML.index("config.js?v=")


def test_la_pestana_config_reemplaza_a_ajustes_equipo_y_pantallas_del_local():
    for viejo in ('id="panelAjustes"', 'id="pantallasLocal"', 'id="versionAyuda"', 'id="dialogoEquipo"'):
        assert viejo not in HTML, viejo
    assert 'id="vistaConfig"' in HTML and 'id="capaConfig"' in HTML
    for fn in ("pintarAjustes", "dialogoEquipo", "pintarConectar", "bloqueImpresion", "bloqueBalanza"):
        assert f"function {fn}(" not in APP, fn


def test_los_atributos_de_config_no_chocan_con_el_manejador_global_de_app_js():
    """app.js tiene UN manejador de clics para toda la página: lo de Config usa data-c-…"""
    usados = set(re.findall(r'data-(?!c-)([a-z-]+)=', JS))
    de_app = set(re.findall(r'cerca\("data-([a-z-]+)"\)', APP))
    # data-aj y data-v son de Config pero no los mira ningún manejador de app.js.
    assert not (usados & de_app), usados & de_app


def test_las_siete_secciones_y_las_guias_estan_en_el_menu():
    for sec in ("local", "equipo", "cobro", "impresora", "pantallas", "caja", "respaldos"):
        assert f"{sec}:" in JS or f'"{sec}"' in JS
    assert "Guías y ayuda" in JS


def test_el_boton_equipo_de_la_barra_lleva_a_config():
    assert 'Config.irA("equipo")' in APP


def test_los_endpoints_que_usa_config_existen():
    """Cada ruta que config.js llama existe en el servidor (no se escribió una a medias)."""
    from apps.pos.main import app
    from apps.pos.api import (actualizaciones, ajustes, catalogo, codigos, config, datos,
                              diagnostico, impresion, mudanza, pantallas, usuarios)
    rutas = set()
    for modulo in (actualizaciones, ajustes, catalogo, codigos, config, datos, diagnostico,
                   impresion, mudanza, pantallas, usuarios):
        for r in modulo.router.routes:
            rutas.add(re.sub(r"\{[^}]+\}", "X", r.path))
    rutas.add("/api/v1/salud")
    llamadas = set(re.findall(r'capi\(\s*[`"](/[A-Za-z0-9_/-]+)', JS))
    llamadas |= set(re.findall(r'capi\(\s*`(/[A-Za-z0-9_/-]+)\$', JS))
    assert len(llamadas) > 20
    for ruta in llamadas:
        base = "/api/v1" + ruta.rstrip("/")
        assert any(r == base or r.startswith(base + "/") for r in rutas), ruta
    assert app
