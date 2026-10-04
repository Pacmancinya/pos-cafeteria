"""Panes y bolsas: los dibujos existen, la caja los ofrece y los reconoce por el nombre."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core.planilla import adivinar_dibujo

ESTATICOS = Path(__file__).resolve().parents[1] / "static"
NUEVOS = ["pan-ciabatta", "pan-frica", "bolsa-cafe", "bolsa-cafe-roja", "bolsa-cafe-azul",
          "bolsa-cafe-negra", "bolsa-cafe-kraft", "bolsa-papel", "bolsa-papel-blanca"]


def _recetas() -> set[str]:
    texto = (ESTATICOS / "dibujos.js").read_text(encoding="utf-8")
    bloque = texto[texto.index("const RECETAS"):texto.index("/* En la caja el vapor")]
    return set(re.findall(r'^\s*"([\w-]+)":\s*\{', bloque, re.M))


def test_los_dibujos_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    r = subprocess.run([node, str(Path(__file__).with_name("dibujos_ui.cjs"))],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_las_recetas_nuevas_existen():
    assert set(NUEVOS) <= _recetas()


def test_todo_lo_que_ofrece_el_selector_tiene_receta():
    app = (ESTATICOS / "app.js").read_text(encoding="utf-8")
    grupos = app[app.index("const GRUPOS_DIBUJO"):app.index("const DIBUJOS =")]
    ofrecidos = set(re.findall(r'"([\w-]+)":\s*"', grupos))
    assert set(NUEVOS) <= ofrecidos
    assert ofrecidos - _recetas() == set()


def test_la_carta_de_ejemplo_solo_usa_dibujos_que_existen():
    from tools.demo.seed import CARTA
    usados = {p[3] for _, productos in CARTA for p in productos}
    assert usados - _recetas() == set()
    assert {"pan-ciabatta", "pan-frica", "bolsa-cafe"} <= usados


@pytest.mark.parametrize("nombre,esperado", [
    ("Ciabatta", "pan-ciabatta"),
    ("Marraqueta", "pan-marraqueta"),
    ("Hallulla", "pan-hallulla"),
    ("Baguette", "pan-baguette"),
    ("Pan amasado", "pan-amasado"),
    ("Pan integral", "pan-integral"),
    ("Frica", "pan-frica"),
    ("Frica con palta", "pan-frica"),
    ("Café en grano 250 g", "bolsa-cafe"),
    ("Bolsa de café", "bolsa-cafe"),
    ("Café molido 250 g", "bolsa-cafe"),
    ("Bolsa de papel", "bolsa-papel"),
    ("Pan", "pan-marraqueta"),
])
def test_el_nombre_se_reconoce(nombre, esperado):
    assert adivinar_dibujo(nombre) == esperado


@pytest.mark.parametrize("nombre,esperado", [
    ("Café de África", "mug"),          # «frica» no sale de «África»
    ("Capuchino", "mug"),
    ("Café", "mug"),
    ("Croissant", "croissant"),
    ("Latte", "mug"),
])
def test_lo_de_antes_se_reconoce_igual(nombre, esperado):
    assert adivinar_dibujo(nombre) == esperado


def test_una_categoria_de_pan_no_cambia_los_dulces():
    # El nombre de la categoría también cuenta, y «Pan» no puede tapar al croissant.
    assert adivinar_dibujo("Croissant", "Pan y pastelería") == "croissant"
    assert adivinar_dibujo("Brownie", "Pan y pastelería") == "brownie"
