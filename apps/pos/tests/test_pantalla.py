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


# ---------------------------------------------------------------------------
# La puerta de la caja no puede tapar el arqueo
# ---------------------------------------------------------------------------
"""El cliente apretaba «Abrir caja» y no pasaba nada.

Pasaba de verdad: el diálogo del arqueo se armaba entero, pero la puerta
(`#cajaCerrada`, z-index 80, fondo opaco) lo tapaba porque los diálogos van en
z-index 20. Y como la puerta ocupa la pantalla completa, no quedaba ni por
dónde salir: el único otro botón es «Salir de mi cuenta», que devuelve al PIN y
después a la misma puerta.

No se vio antes porque un local SIN usuarios creados entra en modo provisorio y
la puerta nunca aparece. Solo se encerraban los que sí crearon usuarios.
"""


def _z_index(css: str, regla: str) -> int | None:
    """El z-index de un selector, leyendo su bloque `{...}`."""
    i = css.find(regla + "{")
    if i == -1:
        return None
    bloque = css[i:css.find("}", i)]
    j = bloque.find("z-index:")
    if j == -1:
        return None
    return int(bloque[j + 8:].split(";")[0].strip())


def test_la_puerta_de_la_caja_se_corre_para_dejar_ver_el_arqueo():
    css = io.open(ESTATICOS / "styles.css", encoding="utf-8").read()
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()

    puerta = _z_index(css, ".candado")      # #cajaCerrada y #candado
    dialogo = _z_index(css, ".capa")        # #capaTurno
    assert puerta is not None and dialogo is not None

    if dialogo > puerta:
        return          # si algún día el diálogo va arriba, no hace falta correr nada

    # Está abajo: entonces la puerta TIENE que esconderse mientras el arqueo
    # está abierto, o el cajero queda encerrado.
    ini = js.find("function pintarPuertaDeLaCaja")
    assert ini != -1, "se renombró pintarPuertaDeLaCaja: revisa esta prueba"
    cuerpo = js[ini:js.find("\n}", ini)]
    assert "capaTurno" in cuerpo, (
        f"La puerta va en z-index {puerta} y el arqueo en {dialogo}: la puerta lo "
        "tapa. pintarPuertaDeLaCaja tiene que mirar si #capaTurno está abierta y "
        "esconderse. Sin eso, «Abrir caja» no hace nada y no hay cómo salir.")


def test_al_abrir_el_arqueo_se_repinta_la_puerta():
    """Esconderla no sirve si nadie vuelve a mirarla justo cuando se abre."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    ini = js.find("async function dialogoTurno")
    assert ini != -1
    cuerpo = js[ini:js.find("\n}", ini)]
    assert "pintarPuertaDeLaCaja" in cuerpo, (
        "dialogoTurno abre #capaTurno pero no repinta la puerta: se queda tapando.")


def test_al_cerrar_el_arqueo_la_puerta_vuelve():
    """Y al revés: cancelar el arqueo no puede dejar el programa usable con la
    caja cerrada, que es lo único que la puerta existe para impedir."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    ini = js.find('cerca("data-cerrar-capa")')
    assert ini != -1
    assert "pintarPuertaDeLaCaja" in js[ini:ini + 400], (
        "al cerrar las capas nadie repinta la puerta: queda escondida y se puede "
        "vender con la caja cerrada.")


def test_el_aviso_se_ve_por_encima_de_las_pantallas_que_tapan_todo():
    """Un «PIN incorrecto» que se dibuja detrás del candado no lo lee nadie."""
    css = io.open(ESTATICOS / "styles.css", encoding="utf-8").read()
    assert _z_index(css, ".aviso") > _z_index(css, ".candado")


# ---------------------------------------------------------------------------
# El día no puede mostrar cifras que no son del momento que se está mirando
# ---------------------------------------------------------------------------
"""El local lo contó así: tenían la caja recién abierta y sin vender nada, y El
día —que había quedado en «Mes»— igual mostraba «Vendido hoy» con plata, ticket
promedio y efectivo. Los números eran del mes y eran ciertos. El problema era el
rótulo y la falta de un modo que mirara SOLO el turno.

Esto no se ve en ninguna prueba de API: el servidor devolvía lo que le pidieron.
La mentira estaba en app.js.
"""


def _cuerpo_de(js: str, firma: str) -> str:
    ini = js.find(firma)
    assert ini != -1, f"se renombró {firma!r}: revisa esta prueba"
    return js[ini:js.find("\n}", ini)]


def test_el_dia_no_dice_hoy_cuando_esta_mirando_el_mes():
    """El rótulo tiene que salir del período, no estar escrito a mano."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function cargarDia()")
    assert "<span>Vendido hoy</span>" not in cuerpo, (
        "El rótulo del total vuelve a decir «Vendido hoy» siempre. Mirando el mes, "
        "esa palabra hace leer un total de 30 días como la venta del día.")
    for palabra in ("Vendido en la semana", "Vendido en el mes", "Vendido en el turno"):
        assert palabra in cuerpo, f"falta el rótulo {palabra!r}"


def test_sin_turno_elegido_el_dia_no_dibuja_ni_un_numero():
    """Un «$0» al lado de «Ticket promedio» también se lee como un dato.

    Con la caja cerrada y sin turno elegido no se muestra nada: es lo que pidió
    el local con estas palabras, «cuando la caja esté cerrada que no se muestre».
    """
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function cargarDia()")
    assert "if (!turnoElegido) return nadaQueMirar" in cuerpo, (
        "cargarDia sigue pidiendo el resumen sin turno elegido: va a pintar ceros "
        "con cara de dato.")


def test_el_selector_de_turno_no_se_para_solo_en_uno_cerrado():
    """Elegirle uno cerrado es volver a mostrar cifras que no son de ahora."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "function pintarSelectorDeTurnos")
    assert "!t.cerrado_at" in cuerpo, (
        "el selector ya no busca el turno ABIERTO para pararse ahí; si cae en uno "
        "cerrado, El día vuelve a mostrar plata de otro rato.")
    assert "Elegí un turno" in cuerpo, (
        "sin turno abierto tiene que quedar en un texto que no elige nada.")


def test_la_cuenta_del_cajon_se_dibuja_entera_y_no_solo_los_retiros():
    """«Aparece lo sacado, pero no se resta», dijeron. Se restaba; no se veía.

    Mirando un turno, la tabla muestra la cuenta completa —fondo, lo que entró,
    cada retiro— para que el total se pueda seguir con el dedo.
    """
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "function pintarLaPlataDelCajon")
    for pedazo in ("Fondo con que se abrió", "Lo que entró en efectivo",
                   "efectivo_en_caja"):
        assert pedazo in cuerpo, f"falta {pedazo!r} en la cuenta del cajón"


# ---------------------------------------------------------------------------
# La vitrina de los televisores no puede tener botones
# ---------------------------------------------------------------------------
"""En el local la vitrina tenía «¿Qué te tinca hoy?» y cuatro botones. Los
clientes iban y los apretaban, y el televisor NO ES TÁCTIL: quedaban tocando
una pantalla que no contesta. Se reemplazó por un combo café + sándwich que
arma el programa solo. Estas pruebas cuidan que no vuelva un botón, y que el
precio del combo sea la suma, que es lo que después cobra la caja.
"""

PANTALLAS = ESTATICOS / "pantallas.html"


def _vitrina_html() -> str:
    html = io.open(PANTALLAS, encoding="utf-8").read()
    ini = html.find('id="pantalla1"')
    assert ini != -1, "se renombró #pantalla1: revisa esta prueba"
    return html[ini:html.find("</section>", ini)]


def test_la_vitrina_no_tiene_botones():
    """Un botón en un televisor que no es táctil es una promesa rota."""
    assert "<button" not in _vitrina_html(), (
        "Volvió un <button> a la vitrina. El televisor no es táctil: la gente lo "
        "aprieta y no pasa nada, que es exactamente el reclamo del local.")


def test_el_combo_no_se_arma_con_botones():
    """La ficha se arma en JS, así que ahí también tiene que ser un cartel."""
    html = io.open(PANTALLAS, encoding="utf-8").read()
    cuerpo = _cuerpo_de(html, "function pintarCombo()")
    assert "<button" not in cuerpo and "onclick" not in cuerpo
    assert "<article" in cuerpo


def test_el_precio_del_combo_es_la_suma_de_los_dos():
    """En la caja no existe un producto «combo»: se cobran los dos por separado.
    Si la pantalla mostrara un descuento, el cliente llegaría a pedir un precio
    que la caja no le puede cobrar."""
    html = io.open(PANTALLAS, encoding="utf-8").read()
    cuerpo = _cuerpo_de(html, "function pintarCombo()")
    assert "reduce((s, p) => s + (+p.p || 0), 0)" in cuerpo, (
        "el total del combo ya no es la suma de los dos precios")
    assert ".antes" not in cuerpo, (
        "el combo muestra un precio «antes»: promete un descuento que la caja no hace")


def test_el_combo_sale_de_la_carta_y_no_de_una_lista_fija():
    """Los cuatro botones viejos mostraban productos escritos a mano que el
    local ni vendía, porque aplicarCarta() nunca los tocaba."""
    html = io.open(PANTALLAS, encoding="utf-8").read()
    assert "CFG.animos" not in html
    cuerpo = _cuerpo_de(html, "function aplicarCarta(")
    assert "pintarCombo()" in cuerpo and "pasoCombo()" in cuerpo, (
        "aplicarCarta ya no repinta el combo: se va a quedar con los productos de ejemplo")


def test_servida_por_la_caja_el_combo_espera_la_carta_del_local():
    """La carta de ejemplo trae productos y precios inventados. Un TV recién
    instalado, sin copia guardada, no puede mostrar un combo con ellos: el local
    capaz ni los vende, y la caja no cobra ese precio."""
    html = io.open(PANTALLAS, encoding="utf-8").read()
    assert "esperandoLaCarta()" in _cuerpo_de(html, "function pintarCombo()")
    assert "cartaDelLocal = true" in _cuerpo_de(html, "function aplicarCarta(")
