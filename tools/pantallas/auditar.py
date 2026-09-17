"""Recorre la caja en varias resoluciones y mide lo que queda fuera de la pantalla.

Nació en la 2.25: en un monitor de 1024x768, o un notebook de 1366x768 con Windows al
125%, la caja se trataba como celular y el botón Cobrar quedaba fuera de la pantalla.
Esto abre las pantallas y diálogos de todos los días en diez resoluciones reales y
avisa, por ejemplo, si Cobrar no se ve o si los botones de abajo de un diálogo quedan
bajo el corte. Deja capturas para mirarlas.

NO es parte de la caja ni de las pruebas: necesita Playwright, que no va en
requirements.txt. Usa el Edge del computador (no baja navegadores):

    python -m venv pw && pw/Scripts/pip install playwright
    pw/Scripts/python tools/pantallas/auditar.py http://127.0.0.1:8791/ antes

Contra una caja de PRUEBA (abre un turno y agrega productos al pedido): nunca contra
la de un local. La consola de versiones levanta una.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
ETIQUETA = sys.argv[2] if len(sys.argv) > 2 else "antes"
AQUI = Path.cwd() / "auditoria-pantallas"
CAPTURAS = AQUI / "capturas" / ETIQUETA

# (nombre, ancho, alto) — el alto es el ÚTIL: pantalla menos barra de tareas
# (40) y barra de título de la ventana (31), con la ventana maximizada.
RESOLUCIONES = [
    ("1024x768", 1024, 697),
    ("1366x768@125", 1093, 543),
    ("1280x720", 1280, 649),
    ("1366x768", 1366, 697),
    ("1920x1080@125", 1536, 793),
    ("1280x1024", 1280, 953),
    ("1920x1080", 1920, 1009),
    ("800x600", 800, 529),
    ("tablet-parado", 768, 1024),
    ("celular", 390, 844),
]

MEDIR = r"""
(estado) => {
  const vw = innerWidth, vh = innerHeight;
  const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect();
    return {x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width),
            h: Math.round(b.height), b: Math.round(b.bottom), r: Math.round(b.right)}; };
  const visible = (el) => el && el.offsetParent !== null && getComputedStyle(el).visibility !== 'hidden';
  const fuera = (b) => b && (b.y < -1 || b.b > vh + 1 || b.x < -1 || b.r > vw + 1);
  const out = {estado, vw, vh, problemas: []};
  const P = (s) => out.problemas.push(s);

  const docW = document.documentElement.scrollWidth, docH = document.documentElement.scrollHeight;
  if (docW > vw + 1) P(`la página se sale a lo ancho: ${docW} > ${vw}`);
  const bodyOv = getComputedStyle(document.body).overflow;
  if (docH > vh + 1 && bodyOv === 'hidden') P(`contenido más alto que la pantalla con body overflow:hidden: ${docH} > ${vh}`);

  const barra = document.querySelector('.barra');
  out.barra = r(barra);
  if (barra && barra.scrollWidth > barra.clientWidth + 1) P(`la barra de arriba se sale a lo ancho (${barra.scrollWidth} > ${barra.clientWidth})`);
  const tabs = [...document.querySelectorAll('.tab')].filter(visible).map(r);
  if (tabs.length && new Set(tabs.map(t => t.y)).size > 1) P('las pestañas se doblan en dos filas');
  for (const el of document.querySelectorAll('.barra__der > *')) {
    if (visible(el) && fuera(r(el))) P(`en la barra, «${(el.textContent||el.id).trim().slice(0,20)}» queda fuera de la pantalla`);
  }

  const capa = [...document.querySelectorAll('.capa.is-on')].pop();
  if (capa) {
    const d = capa.querySelector('.dialogo');
    const bd = r(d);
    out.dialogo = {id: d && d.id || capa.id, rect: bd, scrollH: d && d.scrollHeight, clientH: d && d.clientHeight};
    if (bd && (bd.y < -1 || bd.x < -1 || bd.r > vw + 1)) P(`el diálogo ${out.dialogo.id} se sale de la pantalla ${JSON.stringify(bd)}`);
    if (d && d.scrollHeight > d.clientHeight + 2) P(`el diálogo ${out.dialogo.id} necesita scroll: ${d.scrollHeight} de contenido en ${d.clientHeight} visibles`);
    const pie = d && d.querySelector('.dialogo__pie');
    if (pie) {
      const bp = r(pie);
      out.dialogo.pie = bp;
      // El pie tiene que verse SIN hacer scroll: ahí están Guardar y Confirmar.
      const dentro = bp.y >= bd.y - 1 && bp.b <= Math.min(bd.b, vh) + 1;
      if (!dentro) P(`los botones de abajo de ${out.dialogo.id} no se ven sin scroll (pie ${bp.y}-${bp.b}, diálogo hasta ${Math.min(bd.b, vh)})`);
    }
    // Campos o botones más angostos que su texto (cortados).
    for (const el of d ? d.querySelectorAll('button, .medio, .chip, label.marca') : []) {
      if (!visible(el)) continue;
      if (el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflow !== 'visible')
        P(`texto cortado en «${el.textContent.trim().slice(0,30)}»`);
    }
  } else {
    const vista = document.querySelector('.vista.is-on');
    out.vista = vista && vista.dataset.vista;
    if (out.vista === 'caja') {
      const cobrar = document.querySelector('#btnCobrar');
      out.cobrar = r(cobrar);
      if (fuera(out.cobrar)) P(`el botón Cobrar queda fuera de la pantalla ${JSON.stringify(out.cobrar)}`);
      const lineas = document.querySelector('#lineas');
      out.lineas = r(lineas);
      const hayLineas = document.querySelectorAll('#lineas .linea').length > 0;
      if (hayLineas && out.lineas && out.lineas.h < 120) P(`al pedido le quedan solo ${out.lineas.h}px para las líneas`);
      const tiles = [...document.querySelectorAll('#grilla .prod')].filter(visible).map(r);
      out.azulejos = tiles.length ? {n: tiles.length, w: tiles[0].w, h: tiles[0].h,
        porFila: tiles.filter(t => t.y === tiles[0].y).length} : null;
      const rail = document.querySelector('#rail');
      out.rail = r(rail);
      const productos = document.querySelector('.productos');
      out.productos = r(productos);
      if (out.productos && out.productos.w < 320) P(`la zona de productos quedó en ${out.productos.w}px de ancho`);
    }
    if (vista) {
      // Lo que se sale a lo ancho DENTRO de la vista (tablas, barras de botones).
      for (const el of vista.querySelectorAll('.barra-dia, .kpis, .dos-col, .panel, .ayuda-cuerpo, .bodega, .carta-editor, .tabla-wrap')) {
        if (!visible(el)) continue;
        const ov = getComputedStyle(el).overflowX;
        if (el.scrollWidth > el.clientWidth + 2 && ov !== 'auto' && ov !== 'scroll')
          P(`${el.className.split(' ')[0]} se sale a lo ancho (${el.scrollWidth} > ${el.clientWidth})`);
      }
      const b = r(vista);
      if (b && b.b > vh + 1) P(`la vista ${out.vista} mide ${b.b}px y la pantalla ${vh}`);
    }
  }
  return out;
}
"""


def main() -> None:
    # Adentro y no arriba: el módulo se puede importar sin Playwright instalado.
    from playwright.sync_api import sync_playwright

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    resultados = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="msedge", headless=True)
        for nombre, ancho, alto in RESOLUCIONES:
            ctx = nav.new_context(viewport={"width": ancho, "height": alto},
                                  device_scale_factor=1)
            pagina = ctx.new_page()
            errores = []
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.goto(URL, wait_until="networkidle")
            pagina.wait_for_timeout(800)

            # Caja abierta para poder vender (sesión provisoria: sin usuarios).
            pagina.evaluate("""async () => {
              const t = await (await fetch('/api/v1/turnos/actual')).json().catch(() => ({}));
              if (!t || !t.abierto) await fetch('/api/v1/turnos/abrir', {method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({cajero: 'Prueba', monto_inicial: 20000})});
            }""")
            pagina.reload(wait_until="networkidle")
            pagina.wait_for_timeout(800)

            def paso(estado: str, js: str | None = None, espera: int = 500) -> None:
                try:
                    if js:
                        pagina.evaluate(js)
                        pagina.wait_for_timeout(espera)
                    m = pagina.evaluate(MEDIR, estado)
                    m["resolucion"] = nombre
                    resultados.append(m)
                    pagina.screenshot(path=str(CAPTURAS / f"{nombre}__{estado}.png"))
                except Exception as e:  # un paso roto no tapa los otros
                    resultados.append({"resolucion": nombre, "estado": estado,
                                       "problemas": [f"NO SE PUDO MEDIR: {e}"[:300]]})

            cerrar = "document.querySelectorAll('.capa.is-on').forEach(c => c.classList.remove('is-on'))"

            paso("caja_vacia", "verVista('caja')")
            paso("caja_con_pedido", """(() => {
              const ps = CATEGORIAS.flatMap(c => c.productos).filter(p => p.activo).slice(0, 6);
              ps.forEach(p => agregarPorId(p)); agregarPorId(ps[0]);
            })()""")
            paso("cobrar", "abrirCobro()")
            paso("cobrar_mixto", "(() => { const m = document.querySelector('#pagoMixto'); m.click(); })()")
            paso("varios", cerrar + "; dialogoVarios()")
            paso("el_dia", cerrar + "; verVista('dia')", 1500)
            paso("carta", "verVista('carta')", 1000)
            paso("ficha_editar", """(() => {
              const p = CATEGORIAS.flatMap(c => c.productos)[1];
              abrirFichaProducto(p.id);
            })()""", 800)
            paso("ficha_avanzado", """(() => {
              document.querySelector('#fAvanzado').open = true;
              const c = document.querySelector('#fCosto'); c.value = '1200';
              c.dispatchEvent(new Event('input', {bubbles: true}));
            })()""", 500)
            paso("ficha_nuevo", cerrar + "; nuevoProducto()", 800)
            paso("bodega", cerrar + "; verVista('inventario')", 1200)
            paso("ayuda", "verVista('guias')", 1000)
            paso("cierre_de_caja", "verVista('caja'); dialogoTurno()", 1500)
            paso("equipo", cerrar + "; dialogoEquipo()", 1200)
            paso("version", cerrar + "; dialogoVersion()", 1200)

            if errores:
                resultados.append({"resolucion": nombre, "estado": "errores_js",
                                   "problemas": errores[:5]})
            ctx.close()
        nav.close()

    (AQUI / f"auditoria-{ETIQUETA}.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in resultados:
        if m.get("problemas"):
            print(f"\n[{m['resolucion']}] {m['estado']}")
            for p in m["problemas"]:
                print("   -", p)
    total = sum(len(m.get("problemas", [])) for m in resultados)
    print(f"\n{total} problemas en {len(resultados)} mediciones")


if __name__ == "__main__":
    main()
