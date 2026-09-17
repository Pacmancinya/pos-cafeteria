"""Que la caja no vuelva a tratar un computador chico como un celular.

## Lo que pasó

Un monitor de 1024x768, o un notebook de 1366x768 con Windows al 125% (que para la
página son 1093 px de ancho), caían en la regla de «pantalla angosta» que se había
puesto en 1100 px. Esa regla apila la caja como en un celular: categorías en fila,
productos gigantes, y el pedido con el botón Cobrar ABAJO de todos los productos,
fuera de la pantalla. El dueño lo vio en el computador de un local: «se ve como el
pico».

Y los diálogos más altos que la pantalla —la ficha del producto, el cierre de caja,
el cobro en dos formas— dejaban Guardar, Confirmar venta y Ver si cuadra abajo del
corte, sin nada que avisara que había que desplazarse.

## Qué cuida esta prueba y qué no

No hay navegador en las pruebas, así que esto lee la hoja de estilos. Cuida las dos
decisiones que arreglaron lo de arriba, para que nadie las deshaga sin darse cuenta.
Lo que se ve de verdad se midió con Playwright en diez resoluciones:
`tools/pantallas/auditar.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

HOJA = (Path(__file__).resolve().parents[1] / "static" / "styles.css").read_text(encoding="utf-8")

# Lo que convierte la caja en una columna de celular. Si aparece, tiene que ser SOLO
# para pantallas de celular o tablet parado.
APILAR = [
    re.compile(r'\.vista\[data-vista="caja"\]\{[^}]*flex-direction:column'),
    re.compile(r'\.vista\[data-vista="caja"\]\{[^}]*flex-wrap:wrap'),
    re.compile(r'\.rail\{[^}]*flex-direction:row'),
    re.compile(r'\.pedido\{[^}]*order:'),
]


def _bloques_media(css: str):
    """(condición, contenido) de cada @media de primer nivel, contando llaves."""
    for m in re.finditer(r"@media([^{]*)\{", css):
        nivel, i = 1, m.end()
        while nivel and i < len(css):
            nivel += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        yield m.group(1).strip(), css[m.end():i - 1]


def _sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def test_la_caja_solo_se_apila_en_pantallas_de_celular():
    hoja = _sin_comentarios(HOJA)
    encontrados = 0
    for condicion, contenido in _bloques_media(hoja):
        if not any(p.search(contenido) for p in APILAR):
            continue
        encontrados += 1
        anchos = [int(x) for x in re.findall(r"max-width:\s*(\d+)px", condicion)]
        assert anchos and max(anchos) <= 760, (
            f"@media {condicion} apila la caja: con eso un monitor de 1024x768 o un "
            "notebook al 125% deja el botón Cobrar fuera de la pantalla")
    assert encontrados, "no encontré las reglas del celular: ¿cambió la hoja?"


def test_fuera_de_un_media_la_caja_no_se_apila():
    hoja = _sin_comentarios(HOJA)
    suelta = hoja
    for condicion, contenido in _bloques_media(hoja):
        suelta = suelta.replace(contenido, "")
    for patron in APILAR:
        assert not patron.search(suelta), patron.pattern


def test_los_botones_de_abajo_de_un_dialogo_quedan_pegados_a_la_vista():
    hoja = _sin_comentarios(HOJA)
    pie = re.search(r"\.dialogo\s*>\s*\.dialogo__pie\{([^}]*)\}", hoja)
    assert pie, "falta la regla del pie pegajoso de los diálogos"
    assert "position:sticky" in pie.group(1)
    assert "bottom:" in pie.group(1)
    # Y sin esto el pie tapa el campo al que se llega con Tab, contando billetes.
    assert re.search(r"\.capa\{[^}]*scroll-padding-bottom", hoja)


def test_la_capa_sigue_siendo_la_que_se_desplaza():
    """Si se desplazara el diálogo en vez de la capa, uno centrado que no cabe se
    corta arriba y abajo y no hay forma de llegar al pie. Ya pasó (ver .capa)."""
    hoja = _sin_comentarios(HOJA)
    capa = re.search(r"\n\.capa\{([^}]*)\}", hoja)
    assert capa and "overflow-y:auto" in capa.group(1)
