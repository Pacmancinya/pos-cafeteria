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
import json
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


# ---------------------------------------------------------------------------
# La caja no se puede quedar pegada detrás de un candado que no aparece
# ---------------------------------------------------------------------------
"""El local contó que la caja, al rato sin uso, «se queda pegada y hay que
cerrarla». A los 3 minutos la caja se bloquea sola; para dibujar el candado
esperaba al servidor, y si el servidor no contestaba el candado nunca aparecía:
sin sesión no se podía vender, y no había por dónde volver a entrar."""


def test_el_candado_se_dibuja_sin_esperar_al_servidor():
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function salirDeLaCaja(")
    assert cuerpo.index("mostrarCandado(") < cuerpo.index('"/sesion/salir"'), (
        "salirDeLaCaja vuelve a esperar al servidor antes de mostrar el candado")


def test_si_el_servidor_no_contesta_igual_hay_candado():
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function mostrarCandado(")
    assert "catch" in cuerpo and "candadoSinConexion(" in cuerpo


def test_las_lecturas_tienen_plazo_y_los_cobros_no():
    """Un cobro cortado a la mitad que el servidor sí guardó se cobraría dos veces."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function api(")
    assert "AbortController" in cuerpo
    assert 'metodo === "GET" ? ESPERA_LECTURA : 0' in cuerpo


def test_una_sesion_perdida_vuelve_al_candado():
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function api(")
    assert "sesionPerdida()" in cuerpo and '"/sesion/entrar"' in cuerpo, (
        "un 401 ya no lleva al candado (o el PIN malo también lo haría)")


# ---------------------------------------------------------------------------
# Cada televisor sabe qué muestra, y se entera solo de las actualizaciones
# ---------------------------------------------------------------------------
"""El local tenía un TV para la vitrina y otro para la carta, y los dos se iban
turnando. Y cada cambio a las pantallas obligaba a recargar los TV a mano."""


def test_cada_televisor_elige_que_muestra_y_la_direccion_manda():
    html = io.open(PANTALLAS, encoding="utf-8").read()
    cuerpo = _cuerpo_de(html, "function aplicarModoTv()")
    assert "PANTALLA_POR_DIRECCION || MODO_A_PANTALLA[CFG.modoTv]" in cuerpo


def test_el_televisor_se_recarga_solo_cuando_la_caja_se_actualiza():
    html = io.open(PANTALLAS, encoding="utf-8").read()
    cuerpo = _cuerpo_de(html, "async function vigilarVersion()")
    assert "location.reload()" in cuerpo
    assert "is-open" in cuerpo, "no puede recargarse con el panel Configurar abierto"
    assert "setInterval(vigilarVersion" in html


def test_el_candado_tapa_la_caja_antes_de_preguntarle_al_servidor():
    """Tapar recién cuando el servidor contesta era el hueco: si no contestaba,
    la caja quedaba a la vista sin sesión."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function mostrarCandado(")
    assert cuerpo.index('$("#candado").hidden = false') < cuerpo.index('api("/candado"')


# ---------------------------------------------------------------------------
# 2.19: listo para el segundo local
# ---------------------------------------------------------------------------
def test_el_bloqueo_usa_el_ajuste_del_dueno():
    """Hasta la 2.18 había dos verdades: 90 s en la configuración, sin usarse, y
    3 minutos fijos en la pantalla."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    assert "AJUSTES.bloqueo_minutos" in _cuerpo_de(js, "function reiniciarInactividad(")


def test_el_primer_arranque_guarda_el_local_y_el_pin_antes_que_el_usuario():
    """Apenas existe el primer usuario la caja deja de ser «de todos»: si los
    datos del local fueran después, no se podrían guardar."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    cuerpo = _cuerpo_de(js, "async function crearPrimerUsuario(")
    assert cuerpo.index('"/local"') < cuerpo.index('"/usuarios"')
    assert cuerpo.index('"/red/pin"') < cuerpo.index('"/usuarios"')


def test_la_pantalla_anota_lo_que_el_servidor_no_ve():
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    assert "reportar(" in _cuerpo_de(js, "async function api(")
    assert 'window.addEventListener("error"' in js


def test_los_televisores_usan_el_nombre_del_local():
    html = io.open(PANTALLAS, encoding="utf-8").read()
    assert "carta.local" in _cuerpo_de(html, "function aplicarCarta(")


def test_ningun_script_tiene_errores_de_sintaxis(tmp_path):
    """Un error de sintaxis deja la caja en el PIN, o los televisores en blanco.
    Desde que hay Node en el computador, se revisa de verdad."""
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("no hay Node en este computador")
    for js in archivos_js():
        r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
        assert r.returncode == 0, f"{js.name}: {r.stderr[:400]}"
    for pagina in ("pantallas.html", "pantallas-simple.html"):
        html = io.open(ESTATICOS / pagina, encoding="utf-8").read()
        scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
        archivo = tmp_path / (pagina + ".js")
        archivo.write_text("\n;\n".join(scripts), encoding="utf-8")
        r = subprocess.run([node, "--check", str(archivo)], capture_output=True, text=True)
        assert r.returncode == 0, f"{pagina}: {r.stderr[:400]}"


def test_una_caja_recien_instalada_abre_con_el_asistente():
    """En la 2.19 el asistente del primer arranque no aparecía nunca: sin gente
    la sesión es provisoria, y la caja abría directo sin pasar por el candado."""
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    ini = js.find("if (!SESION.entrado) await mostrarCandado();")
    assert ini != -1, "se movió el arranque: revisa esta prueba"
    assert "instalacion_nueva" in js[ini:ini + 800]


def test_el_nombre_nuevo_del_local_llega_a_los_televisores(tmp_path):
    """Lo encontró la revisión de Codex: el nombre que ponía la caja quedaba
    como si alguien lo hubiera escrito a mano, y si el local se cambiaba de
    nombre los televisores seguían con el viejo."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("no hay Node en este computador")
    html = io.open(PANTALLAS, encoding="utf-8").read()
    prueba = _cuerpo_de(html, "function ponerNombreEnLaTv(") + "\n}\n" + """
const CONFIG = { marca: "Kofe", marcaTxt: "Kofe", kicker: "Tostado en Graneros", bajada: "Del grano" };
const copia = (o) => JSON.parse(JSON.stringify(o));
let CFG = copia(CONFIG);
let pintadas = 0;
function pintarVitrina() { pintadas++; }
const r = [];
ponerNombreEnLaTv("Kofe"); r.push(CFG.kicker, pintadas);        // el primer local, intacto
ponerNombreEnLaTv("Cafe Tito"); r.push(CFG.marca, CFG.kicker);
ponerNombreEnLaTv("Cafe Tita"); r.push(CFG.marca);              // se cambio de nombre
CFG = copia(CFG);                                                // lo guarda y lo vuelve a leer
CFG.marcaTxt = "Tito a mano";                                    // escrito en Configurar
ponerNombreEnLaTv("Cafe Toto"); r.push(CFG.marca, CFG.marcaTxt);
const antes = pintadas;
ponerNombreEnLaTv("Cafe Toto"); r.push(pintadas - antes);       // nada que repintar
console.log(JSON.stringify(r));
"""
    archivo = tmp_path / "nombre.js"
    archivo.write_text(prueba, encoding="utf-8")
    salida = subprocess.run([node, str(archivo)], capture_output=True, text=True, encoding="utf-8")
    assert salida.returncode == 0, salida.stderr[:400]
    assert json.loads(salida.stdout) == [
        "Tostado en Graneros", 0,
        "Cafe Tito", "",
        "Cafe Tita",
        "Cafe Toto", "Tito a mano",
        0,
    ]


def test_el_modo_sin_inventario_llega_al_carrito_los_formularios_y_la_ayuda(tmp_path):
    """Ejecuta las funciones de la caja: ocultar campos no basta si el + sigue
    topando el pedido o el alta manda ceros que nadie escribió."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("no hay Node en este computador")
    js = io.open(ESTATICOS / "app.js", encoding="utf-8").read()
    funciones = ["function usarInventario(", "function sumarAlPedido(",
                 "function cambiarCantidad(", "function productoDeLaCarta(",
                 "async function dialogoProductoNuevoPorCodigo(",
                 "async function guardarProductoDelCodigo(", "async function pintarTalCual(",
                 "function pintarGuias(", "function verVista(", "function aplicarInventario("]
    prueba = "\n".join(_cuerpo_de(js, firma) + "\n}" for firma in funciones)
    prueba += "\nconst window = {};\n" + io.open(ESTATICOS / "guias.js", encoding="utf-8").read()
    prueba += r"""
const assert = require('node:assert/strict');
const esc = (s) => String(s);
const soloNumeros = (s) => parseInt(String(s).replace(/\D/g, ''), 10) || 0;
const setTimeout = () => {};
const avisar = () => {};
const pintarCarrito = () => {};
const cargarCarta = async () => {};
const datos = new Map();
function elemento() {
  return { innerHTML: '', style: {}, dataset: {}, hidden: false,
    classList: { add() {}, remove() {}, toggle() {} }, querySelectorAll() { return []; } };
}
const $ = (s) => datos.get(s) || null;
const $$ = () => [];
for (const id of ['#dialogoCodigo', '#capaCodigo', '#zonaTalCual', '#listaGuias',
                  '#textoGuia', '#capaBodega', '#capaInsumo', '#ajInventario',
                  ".tab[data-vista='inventario']"]) datos.set(id, elemento());
let AJUSTES = {};
let carrito = [];
let guiaAbierta = null;
const p = { id: 1, nombre: 'Queso', precio: 1500, stock: 0 };
const CATEGORIAS = [{ id: 1, nombre: 'Fiambres', activa: true, productos: [p] }];
let catActiva = 1;
const VISTAS = ['caja', 'inventario', 'guias'];
const location = {};
let pedidos = [];
let cargarBodega = () => { throw Error('No debe cargar Bodega'); };
let api = async (ruta, opciones) => { pedidos.push([ruta, JSON.parse(opciones.body)]); return p; };
(async () => {
  sumarAlPedido(p);
  assert.equal(carrito.length, 0, 'sin ajuste guardado mantiene el tope');
  AJUSTES.usar_inventario = 0;
  sumarAlPedido(p); cambiarCantidad(1, 1);
  assert.equal(carrito[0].cantidad, 2);
  AJUSTES.usar_inventario = 1;
  cambiarCantidad(1, 1);
  assert.equal(carrito[0].cantidad, 2, 'al reactivar vuelve el tope');

  for (const usar of [0, 1]) {
    AJUSTES.usar_inventario = usar;
    await dialogoProductoNuevoPorCodigo('', 1);
    const html = $('#dialogoCodigo').innerHTML;
    assert.equal(html.includes('id="cdCosto"'), !!usar);
    assert.equal(html.includes('id="cdStock"'), !!usar);
    datos.set('#cdNombre', { value: 'Queso' });
    datos.set('#cdPrecio', { value: '1500' });
    datos.set('#cdCat', { value: '1' });
    if (usar) {
      datos.set('#cdCosto', { value: '800' });
      datos.set('#cdStock', { value: '10' });
    } else {
      datos.delete('#cdCosto'); datos.delete('#cdStock');
    }
    await guardarProductoDelCodigo('');
    const cuerpo = pedidos.at(-1)[1];
    assert.equal(cuerpo.nombre, 'Queso');
    if (usar) {
      assert.equal(cuerpo.tal_cual, true);
      assert.equal(cuerpo.costo, 800);
      assert.equal(cuerpo.stock_inicial, 10);
    } else {
      for (const clave of ['tal_cual', 'costo', 'stock_inicial', 'minimo']) {
        assert.equal(clave in cuerpo, false);
      }
    }
  }
  AJUSTES.usar_inventario = 0;
  api = async () => { throw Error('No debe consultar inventario'); };
  const zona = $('#zonaTalCual');
  zona.innerHTML = 'Bodega';
  await pintarTalCual(p);
  assert.equal(zona.innerHTML, '');
  assert.equal(zona.style.display, 'none');
  pintarGuias('descuento-automatico');
  assert.equal($('#listaGuias').innerHTML.includes('data-guia="descuento-automatico"'), false);
  assert.equal($('#listaGuias').innerHTML.includes('data-guia="compre-pasteles"'), false);
  assert.equal($('#textoGuia').innerHTML.includes('Por comprar'), false);
  aplicarInventario();
  assert.equal($(".tab[data-vista='inventario']").hidden, true);
  verVista('inventario');
  assert.equal(location.hash, '#/caja');
  AJUSTES.usar_inventario = 1;
  aplicarInventario();
  assert.equal($(".tab[data-vista='inventario']").hidden, false);
  assert.equal($('#listaGuias').innerHTML.includes('data-guia="descuento-automatico"'), true);
})().catch((e) => { console.error(e); process.exitCode = 1; });
"""
    archivo = tmp_path / "inventario.js"
    archivo.write_text(prueba, encoding="utf-8")
    salida = subprocess.run([node, str(archivo)], capture_output=True, text=True, encoding="utf-8")
    assert salida.returncode == 0, salida.stderr


def test_un_local_sin_productos_igual_se_ve_con_su_nombre():
    """Un local recién instalado todavía no tiene carta: la caja contesta sin
    categorías y la pantalla lo toma como error. El nombre se perdía con ese
    error y los televisores seguían diciendo «Kofe»."""
    html = io.open(PANTALLAS, encoding="utf-8").read()
    cuerpo = _cuerpo_de(html, "async function traerPV(")
    assert cuerpo.index("ponerNombreEnLaTv") < cuerpo.index("desdePV(")


def test_un_nombre_largo_cabe_en_el_logo():
    """«Café Tito» salía cortado en los dos bordes del televisor parado: el
    tamaño del logo se pensó para las cuatro letras de «Kofe». Y el nombre va
    escapado: «Pan & Café» no puede romper el dibujo."""
    html = io.open(PANTALLAS, encoding="utf-8").read()
    cuerpo = _cuerpo_de(html, "function pintarPalabra(")
    assert "anchoDelTexto(" in cuerpo and "anchoVisible(" in cuerpo
    assert "pintarPalabra(" in _cuerpo_de(html, "function setOrientacion(")
    assert "esc(texto)" in cuerpo and ">${texto}<" not in cuerpo
