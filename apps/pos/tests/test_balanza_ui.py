"""La pantalla de balanza se prueba con el contrato falso, sin depender del servidor."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_la_pantalla_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    r = subprocess.run([node, str(Path(__file__).with_name("balanza_ui.cjs"))],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
