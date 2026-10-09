"""La pantalla de venta con barra de 4 pestañas, categorías en columna angosta y el
teclado de multiplicar en su propia franja.

Lo que se ve de verdad se midió con Playwright (`tools/pantallas/auditar.py`); acá se
cuida la estructura y la lógica que no se puede ver sin navegador.
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
JS = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
CSS = io.open(ESTATICOS / "styles.css", encoding="utf-8").read()
GUIAS = io.open(ESTATICOS / "guias.js", encoding="utf-8").read()


def _cuerpo_de(js: str, firma: str) -> str:
    ini = js.find(firma)
    assert ini != -1, f"se renombró {firma!r}: revisa esta prueba"
    return js[ini:js.find("\n}", ini)] + "\n}"


def test_la_barra_tiene_cuatro_pestañas_en_este_orden():
    barra = HTML[HTML.index('<nav class="tabs">'):HTML.index("</nav>", HTML.index('<nav class="tabs">'))]
    pestañas = re.findall(r'<button class="tab[^"]*" data-vista="(\w+)"[^>]*>([^<]*)</button>', barra)
    assert pestañas == [("caja", "Caja"), ("stock", "Inventario"),
                        ("dia", "Ventas"), ("guias", "Config")]


def test_inventario_tiene_una_lista_sin_selector_ni_pantallas_anteriores():
    assert 'id="subInventario"' not in HTML
    assert 'data-vista="carta"' not in HTML
    assert 'id="editorCarta"' not in HTML and 'id="tablaInsumos"' not in HTML
    assert 'id="vistaInventario"' in HTML
    assert 'id="btnConfigurar"' in HTML


def test_el_dia_ya_no_se_llama_asi_en_ninguna_guia_ni_aviso_de_la_pantalla():
    for texto in (GUIAS, JS):
        assert "<b>El día</b>" not in texto
        assert "Pestaña <b>Carta</b>" not in texto
        assert "Configurar →" not in texto


def test_la_pestana_inventario_y_las_direcciones_anteriores_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node")
    prueba = _cuerpo_de(JS, "function verVista(") + r"""
const assert = require('node:assert/strict');
const VISTAS = ['caja','dia','inventario','guias'];
const location = {}; const $$ = () => [];
let cargas = 0;
const cargarInventario = () => { cargas++; }, periodoQueCorresponde = () => {}, cargarDia = () => {}, pintarGuias = () => {};
for (const ruta of ['stock','carta','inventario']) { verVista(ruta); assert.equal(location.hash,'#/inventario'); }
assert.equal(cargas,3);
verVista('caja'); assert.equal(location.hash,'#/caja');
"""
    r = subprocess.run([node, "-e", prueba], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_icono_de_la_categoria_y_el_aviso_de_mas_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    prueba = "\n".join(_cuerpo_de(JS, f) for f in
                       ["function dibujoDeCategoria(", "function avisarRail(", "function verCategoriaActiva("])
    prueba += r"""
const assert = require('node:assert/strict');
const p = (dibujo, activo = true) => ({ dibujo, activo });
assert.equal(dibujoDeCategoria({ productos: [p('mug'), p('vaso'), p('vaso'), p('torta', false)] }), 'vaso',
  'el dibujo que más se repite');
assert.equal(dibujoDeCategoria({ productos: [p('mug'), p('vaso')] }), 'mug', 'el empate lo gana el primero');
assert.equal(dibujoDeCategoria({ productos: [p(''), p(null)] }), 'plato', 'sin dibujo asignado: genérico');
assert.equal(dibujoDeCategoria({ productos: [] }), 'plato');
assert.equal(dibujoDeCategoria({ dibujo: 'pan-baguette', productos: [p('mug')] }), 'pan-baguette',
  'el dibujo elegido manda sobre el automático');
assert.equal(dibujoDeCategoria({ dibujo: '', productos: [p('mug')] }), 'mug', 'vacío = automático');

const clases = new Set();
const rail = { scrollTop: 0, scrollHeight: 600, clientHeight: 400 };
const envoltura = { classList: { toggle: (c, on) => (on ? clases.add(c) : clases.delete(c)) } };
const $ = (s) => ({ '#rail': rail, '#railWrap': envoltura }[s]);
avisarRail();
assert(clases.has('hay-mas-abajo') && !clases.has('hay-mas-arriba'), 'arriba del todo: solo «más ▾»');
rail.scrollTop = 120; avisarRail();
assert(clases.has('hay-mas-abajo') && clases.has('hay-mas-arriba'), 'a medio camino: los dos');
rail.scrollTop = 200; avisarRail();
assert(!clases.has('hay-mas-abajo') && clases.has('hay-mas-arriba'), 'al fondo: solo «▴»');
rail.scrollHeight = 400; rail.scrollTop = 0; avisarRail();
assert(!clases.has('hay-mas-abajo') && !clases.has('hay-mas-arriba'), 'si caben todas, ningún aviso');

let pedido = null;
const activa = { scrollIntoView: (o) => { pedido = o; } };
rail.querySelector = (s) => (s === '.rail__cat.is-on' ? activa : null);
verCategoriaActiva();
assert.equal(pedido.behavior, 'smooth'); assert.equal(pedido.block, 'nearest');
console.log('Rail OK');
"""
    r = subprocess.run([node, "-e", prueba], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_la_columna_de_categorias_es_angosta_y_se_desplaza_con_avisos():
    assert re.search(r"\.rail-wrap\{[^}]*width:88px", CSS)
    assert re.search(r"\.rail\{[^}]*overflow-y:auto", CSS)
    assert ".rail-wrap.hay-mas-abajo .rail__mas--abajo" in CSS
    assert ".rail-wrap.hay-mas-arriba .rail__mas--arriba" in CSS
    assert "más ▾" in HTML and "▴" in HTML
    cargar = _cuerpo_de(JS, "async function cargarCarta(")
    assert 'class="rail__ico"' in cargar and 'class="rail__txt"' in cargar
    assert "title=" in cargar, "el nombre completo va en el title"
    assert "rail__n" not in cargar, "el conteo ya no cabe en la columna angosta"


def test_buscador_y_varios_van_en_una_sola_fila():
    fila = HTML[HTML.index('class="fila-busca"'):HTML.index('id="grilla"')]
    assert 'id="buscar"' in fila and 'id="btnVarios"' in fila
    assert fila.index('id="buscar"') < fila.index('id="btnVarios"')
    assert ">+ Varios<" in fila
    assert re.search(r"\.fila-busca\{[^}]*display:flex", CSS)


def test_el_teclado_esta_en_la_zona_central_y_solo_con_modo_tactil():
    central = HTML[HTML.index('class="productos"'):HTML.index("</section>", HTML.index('class="productos"'))]
    assert central.index('id="grilla"') < central.index('id="mult"')
    # Franja propia abajo a la derecha: la grilla (arriba) se desplaza sola.
    assert re.search(r"\.mult\{[^}]*align-self:flex-end", CSS)
    assert re.search(r"\.grilla\{[^}]*overflow:auto", CSS)
    # Sin modo táctil no hay teclado: teclado.js lo esconde y la grilla usa todo el área.
    teclado = io.open(ESTATICOS / "teclado.js", encoding="utf-8").read()
    assert "multCaja.hidden = !SE_USA" in teclado
    assert re.search(r"\.mult\[hidden\]\{display:none\}", CSS)


def test_vaciar_el_pedido_es_un_basurero_con_nombre_accesible():
    boton = HTML[HTML.index('id="btnLimpiar"') - 60:HTML.index("</button>", HTML.index('id="btnLimpiar"'))]
    assert 'aria-label="Vaciar pedido"' in boton and 'title="Vaciar pedido"' in boton
    assert "<svg" in boton and ">Limpiar<" not in boton
    # El clic cae en el dibujo, no en el botón: tiene que resolverse con closest().
    assert 'closest("#btnLimpiar")' in JS


def test_la_grilla_reparte_su_alto_en_al_menos_dos_filas_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    prueba = _cuerpo_de(JS, "function acomodarGrilla(")
    prueba += r"""
const assert = require('node:assert/strict');
const props = {};
const grilla = { clientHeight: 0, style: { setProperty: (k, v) => { props[k] = v; },
                                           removeProperty: (k) => { delete props[k]; } } };
const $ = () => grilla;
const getComputedStyle = () => ({ rowGap: '10px' });
let angosta = false;
const window = { matchMedia: () => ({ matches: angosta }) };
const fila = (h) => { grilla.clientHeight = h; acomodarGrilla(); return parseInt(props['--fila'], 10); };

assert.equal(fila(235), 112, 'con 235 px de alto caben dos filas de 112');
assert.equal(fila(315), 152);
for (const h of [235, 260, 315, 420, 700, 900]) {
  const f = fila(h), n = Math.floor((h + 10) / (f + 10));
  assert(n >= 2, `con ${h} px tienen que caber 2 filas (cupieron ${n}, de ${f} px)`);
  assert(f >= 100);
}
angosta = true; fila(500);
assert.equal(props['--fila'], undefined, 'en un celular la grilla no fija el alto');
console.log('Grilla OK');
"""
    r = subprocess.run([node, "-e", prueba], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_celular_sigue_con_las_categorias_en_fila_y_sin_teclado():
    assert re.search(r"max-width:760px\)\{\s*\.rail-wrap\{width:100%.*?flex-direction:row"
                     r".*?\.mult\{display:none !important\}", CSS, re.S)
