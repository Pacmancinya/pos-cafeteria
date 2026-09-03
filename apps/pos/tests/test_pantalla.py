"""Que el JavaScript de la caja se pueda leer.

## Por qué existe este archivo

Las 242 pruebas que había antes prueban el servidor: cobrar, el stock, el
cierre, los permisos. Ninguna miraba `app.js`, y `app.js` ES la caja — lo que
ve el cajero, el carrito, el botón de cobrar.

Se escapó así: quedó un salto de línea CRUDO adentro de unas comillas dobles.

    confirm("llevan, empezando en cero.
    Después anota...")            <-- eso no es un texto, es un error

Un solo error de sintaxis no rompe una función: el navegador NO CARGA EL
ARCHIVO ENTERO. La caja quedaba en la pantalla del PIN, sin pestañas, sin
carrito, sin nada. Y del lado del servidor todo pasaba en verde, porque el
servidor no tiene nada que ver.

Costó encontrarlo porque el síntoma no dice qué pasó: la pantalla simplemente
no responde.

## Qué revisa y qué no

No hay un intérprete de JavaScript en esta máquina, así que esto no es un
compilador y no lo pretende. Es un lector de comillas: recorre el archivo
sabiendo dónde empieza y termina cada texto, cada comentario y cada expresión
regular, y avisa si un texto de comillas simples o dobles llega al final de la
línea sin cerrarse.

Eso es poco, y es exactamente el error que se cometió. Un archivo puede pasar
esta prueba y estar mal de otra forma; ninguno puede fallarla y funcionar.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

ESTATICOS = Path(__file__).resolve().parents[1] / "static"

# Los backticks sí pueden abarcar varias líneas: son plantillas y el código
# está lleno de HTML escrito así. Solo las comillas simples y dobles no pueden.
DE_UNA_LINEA = ("'", '"')


def archivos_js() -> list[Path]:
    return sorted(ESTATICOS.glob("*.js"))


def _antes_va_un_valor(texto: str, i: int) -> bool:
    """¿La `/` en la posición i divide, o abre una expresión regular?

    Se mira el último carácter que importa: si ahí terminaba un valor —un
    nombre, un número, un paréntesis o corchete cerrado— entonces la barra
    divide. Si no, abre una regex. Es la regla que usa cualquier resaltador de
    sintaxis, y basta: confundirse solo puede hacer que la prueba se pierda un
    error, nunca que invente uno.
    """
    j = i - 1
    while j >= 0 and texto[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return False
    return texto[j].isalnum() or texto[j] in ")]}_$"


def comillas_sin_cerrar(codigo: str) -> list[tuple[int, str]]:
    """Devuelve (línea, comilla) por cada texto que no cierra en su línea."""
    fallas: list[tuple[int, str]] = []
    i, linea, largo = 0, 1, len(codigo)

    while i < largo:
        c = codigo[i]

        if c == "\n":
            linea += 1
            i += 1
            continue

        if c == "/" and i + 1 < largo:
            if codigo[i + 1] == "/":
                while i < largo and codigo[i] != "\n":
                    i += 1
                continue
            if codigo[i + 1] == "*":
                fin = codigo.find("*/", i + 2)
                fin = largo if fin == -1 else fin + 2
                linea += codigo.count("\n", i, fin)
                i = fin
                continue
            if not _antes_va_un_valor(codigo, i):
                # Una regex tampoco puede cruzar de línea, pero si estuviera mal
                # no es lo que se está buscando acá: se salta y ya.
                i += 1
                while i < largo and codigo[i] not in "\n":
                    if codigo[i] == "\\":
                        i += 2
                        continue
                    if codigo[i] == "/":
                        i += 1
                        break
                    i += 1
                continue

        if c == "`":
            # Plantilla: puede cruzar líneas. Los `${...}` de adentro pueden
            # traer comillas y hasta otra plantilla, así que se cuentan llaves.
            i += 1
            while i < largo:
                if codigo[i] == "\\":
                    i += 2
                    continue
                if codigo[i] == "\n":
                    linea += 1
                    i += 1
                    continue
                if codigo[i] == "`":
                    i += 1
                    break
                if codigo[i] == "$" and i + 1 < largo and codigo[i + 1] == "{":
                    hondo, i = 1, i + 2
                    while i < largo and hondo:
                        if codigo[i] == "{":
                            hondo += 1
                        elif codigo[i] == "}":
                            hondo -= 1
                        elif codigo[i] == "\n":
                            linea += 1
                        i += 1
                    continue
                i += 1
            continue

        if c in DE_UNA_LINEA:
            abre, empezo = c, linea
            i += 1
            cerrada = False
            while i < largo:
                if codigo[i] == "\\":
                    # Un `\` al final de la línea sí continúa el texto: es raro,
                    # pero es JavaScript válido y no hay que acusarlo.
                    if i + 1 < largo and codigo[i + 1] == "\n":
                        linea += 1
                    i += 2
                    continue
                if codigo[i] == "\n":
                    break                      # se acabó la línea y sigue abierta
                if codigo[i] == abre:
                    cerrada = True
                    i += 1
                    break
                i += 1
            if not cerrada:
                fallas.append((empezo, abre))
            continue

        i += 1

    return fallas


@pytest.mark.parametrize("js", archivos_js(), ids=lambda p: p.name)
def test_ningun_texto_queda_abierto_al_final_de_su_linea(js: Path):
    codigo = io.open(js, encoding="utf-8").read()
    fallas = comillas_sin_cerrar(codigo)
    assert not fallas, "\n".join(
        f"{js.name}:{n} abre {q} y no lo cierra en esa línea. "
        "El navegador no carga NADA del archivo: la caja queda muerta."
        for n, q in fallas)


def test_el_lector_de_comillas_de_verdad_encuentra_el_error_que_paso():
    """La prueba de la prueba, con el código exacto que rompió la caja."""
    roto = 'if (!confirm("llevan, empezando en cero.\n\nDespués anota")) return;'
    # Dos, y las dos son de verdad: la comilla de la linea 1 se queda abierta,
    # y la de la linea 3 —la que el ojo lee como cierre— abre otro texto que
    # tampoco cierra. Asi se ve un salto de linea suelto adentro de comillas.
    assert comillas_sin_cerrar(roto) == [(1, '"'), (3, '"')]

    bueno = 'if (!confirm("llevan, empezando en cero.\\n\\nDespués anota")) return;'
    assert comillas_sin_cerrar(bueno) == []


def test_el_lector_no_se_asusta_con_lo_que_sí_es_válido():
    sano = "\n".join([
        "const s = `una plantilla",
        "  que cruza lineas ${ x ? \"si\" : 'no' } y sigue`;",
        "const r = /['\"]+/g;              // una regex con comillas adentro",
        "const d = total / 2;              // esto divide, no es regex",
        "/* un comentario \"con comillas\"",
        "   y varias lineas */",
        "const apostrofe = \"no's\";       // apostrofe adentro de dobles",
        "const cortado = 'sigue \\",
        "en la otra linea';",
    ])
    assert comillas_sin_cerrar(sano) == []


def test_todos_los_js_de_la_caja_estan_en_la_lista():
    """Si mañana se agrega otro .js, esta prueba lo agarra sola."""
    nombres = {p.name for p in archivos_js()}
    assert {"app.js", "escaner.js", "teclado.js"} <= nombres


def test_index_pide_todos_los_js_que_existen():
    """Un archivo que nadie carga es peor que uno que falta: parece que anda."""
    index = io.open(ESTATICOS / "index.html", encoding="utf-8").read()
    for js in archivos_js():
        assert js.name in index, f"{js.name} está en static/ y nadie lo carga"
