"""El teclado de teléfono y el multiplicador de la pantalla de venta."""
import shutil
import subprocess
from pathlib import Path

import pytest

ESTATICOS = Path(__file__).resolve().parents[1] / "static"


def test_el_teclado_y_el_multiplicador_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    r = subprocess.run([node, str(Path(__file__).with_name("teclado_ui.cjs"))],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_teclado_fijo_y_la_barra_escondible_estan_en_la_pagina():
    html = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    # El teclado fijo va en la zona central, abajo de la grilla (su propia franja): ya no
    # está en la columna del pedido.
    assert html.index('id="grilla"') < html.index('id="mult"') < html.index('class="pedido"')
    pedido = html[html.index('class="pedido"'):html.index('class="pedido__pie"')]
    assert 'id="mult"' not in pedido
    assert 'id="railLista"' not in html
    assert 'id="btnEsconderBarra"' in html and 'id="btnMostrarBarra"' in html
    # Sin archivos nuevos: todo vive en teclado.js, que ya se pide con ?v=__VERSION__.
    assert "/static/teclado.js?v=__VERSION__" in html
