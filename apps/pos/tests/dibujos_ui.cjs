/* Los dibujos nuevos (panes y bolsas) y el selector de color de la bolsa.
 * Corre dibujos.js y los trozos de app.js que lo usan en un entorno falso, sin navegador. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const estaticos = path.join(__dirname, '../static');
const dibujosJs = fs.readFileSync(path.join(estaticos, 'dibujos.js'), 'utf8');
const appJs = fs.readFileSync(path.join(estaticos, 'app.js'), 'utf8');

const c = { console, window: {} };
vm.createContext(c);
vm.runInContext(dibujosJs, c);
const dibujo = c.window.dibujo;
assert.equal(typeof dibujo, 'function');

/* Un SVG bien armado: abre y cierra cada etiqueta y no tiene nada pegado de afuera. */
function svgValido(svg, nombre) {
  assert(svg.startsWith('<svg') && svg.endsWith('</svg>'), nombre);
  const pila = [];
  for (const m of svg.matchAll(/<(\/?)([a-zA-Z]+)([^>]*?)(\/?)>/g)) {
    const [, cierra, etiqueta, , auto] = m;
    if (auto) continue;
    if (cierra) assert.equal(pila.pop(), etiqueta, `${nombre}: </${etiqueta}> sin abrir`);
    else pila.push(etiqueta);
  }
  assert.equal(pila.length, 0, `${nombre}: quedó abierto ${pila.join(',')}`);
  assert(!/NaN|undefined|\[object/.test(svg), `${nombre}: trae NaN/undefined`);
  assert(!/<script|onerror|onload/i.test(svg), nombre);
  const ids = [...svg.matchAll(/ id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length, `${nombre}: ids repetidos`);
}

const PANES = ['pan-marraqueta', 'pan-hallulla', 'pan-amasado', 'pan-baguette',
  'pan-ciabatta', 'pan-integral', 'pan-frica'];
const BOLSAS = ['bolsa-cafe', 'bolsa-cafe-roja', 'bolsa-cafe-azul', 'bolsa-cafe-negra',
  'bolsa-cafe-kraft', 'bolsa-papel', 'bolsa-papel-blanca'];
const porDefecto = dibujo({ k: '__no_existe__' });      // lo que sale cuando no se conoce la clave

for (const k of [...PANES, ...BOLSAS]) {
  const svg = dibujo({ k });
  svgValido(svg, k);
  assert.notEqual(svg, porDefecto, `${k} se cae al dibujo por defecto`);
}
/* Cada pan se distingue de los demás: ninguno repite el dibujo de otro. */
assert.equal(new Set(PANES.map((k) => dibujo({ k }))).size, PANES.length);

/* El color de la bolsa se aplica, en cualquier tono. */
const verde = dibujo({ k: 'bolsa-cafe', col: '#123456' });
assert(verde.includes('#123456'));
assert(!verde.includes('#2e5e4e'), 'el color elegido manda sobre el de la receta');
assert(dibujo({ k: 'bolsa-cafe', col: '#abc' }).includes('#aabbcc'));
for (const col of ['#000000', '#ffffff', '#ff0000', '#E8C547']) {
  svgValido(dibujo({ k: 'bolsa-cafe', col }), `bolsa ${col}`);
  svgValido(dibujo({ k: 'bolsa-papel', col }), `bolsa papel ${col}`);
}
assert.notEqual(dibujo({ k: 'bolsa-cafe', col: '#111111' }), dibujo({ k: 'bolsa-cafe', col: '#eeeeee' }));
/* Un color que no es #hex no se pega en el SVG: es dato de la base, no se confía. */
const sucio = dibujo({ k: 'bolsa-cafe', col: '"/><script>alert(1)</script>' });
assert(!sucio.includes('script'));
assert(sucio.includes('#2e5e4e'));
assert(dibujo({ k: 'bolsa-cafe', col: 'red' }).includes('#2e5e4e'));
/* Kraft: por clave y por opción, y con un color elegido deja de ser kraft. */
assert(dibujo({ k: 'bolsa-cafe-kraft' }).includes('#b98b5e'));
assert(dibujo({ k: 'bolsa-cafe', kraft: 1 }).includes('#b98b5e'));
assert(!dibujo({ k: 'bolsa-cafe', kraft: 1 }).includes('#2e5e4e'));
assert(dibujo({ k: 'bolsa-cafe', kraft: 1, col: '#123456' }).includes('#123456'));
/* Lo de antes sigue igual: la taza y el color de siempre. */
svgValido(dibujo({ k: 'mug', col: '#3A1B0C' }), 'mug');

/* ---- el selector de la ficha del producto ---- */
const inicio = appJs.indexOf('const GRUPOS_DIBUJO');
const fin = appJs.indexOf('function categoriasPlegadasGuardadas');
assert(inicio > 0 && fin > inicio);
const campos = new Map();
const e = {
  console, dibujo,
  esc: (s) => String(s).replace(/[&<>"']/g, ''),
  sinTildes: (s) => String(s).toLowerCase(),
  $: (id) => campos.get(id) || null,
  $$: () => [],
};
vm.createContext(e);
vm.runInContext(appJs.slice(inicio, fin), e);

const claves = JSON.parse(JSON.stringify(Object.keys(vm.runInContext('DIBUJOS', e))));
for (const k of [...PANES, ...BOLSAS]) assert(claves.includes(k), `el selector no ofrece ${k}`);
for (const k of claves.filter((x) => x !== 'mug')) assert.notEqual(dibujo({ k }), porDefecto, `el selector ofrece ${k} pero no existe`);

const conBolsa = vm.runInContext('selectorDeDibujo("bolsa-cafe", "#112233")', e);
assert(/id="filaColorBolsa"\s*>/.test(conBolsa), 'la fila de color se ve con una bolsa');
assert(conBolsa.includes('id="fColor" value="#112233"'));
assert(conBolsa.includes('#112233'));
const conMug = vm.runInContext('selectorDeDibujo("mug", "#112233")', e);
assert(/id="filaColorBolsa"\s+hidden/.test(conMug), 'la fila de color se esconde si no es bolsa');
assert(conMug.includes('id="fColor" value=""'), 'el color de otro dibujo no tiñe una bolsa');
assert(vm.runInContext('selectorDeDibujo("bolsa-cafe", "azul")', e).includes('id="fColor" value=""'));

/* Qué color queda guardado. */
campos.set('#fDibujo', { value: 'bolsa-cafe' });
campos.set('#fColor', { value: '#2F5D8A' });
assert.equal(vm.runInContext('colorParaGuardar({ dibujo: "mug", color: "" })', e), '#2F5D8A');
campos.get('#fColor').value = 'basura';
assert.equal(vm.runInContext('colorParaGuardar({ dibujo: "mug", color: "" })', e), '');
campos.get('#fDibujo').value = 'mug';
campos.get('#fColor').value = '#2F5D8A';
assert.equal(vm.runInContext('colorParaGuardar({ dibujo: "mug", color: "#3A1B0C" })', e), '#3A1B0C');
assert.equal(vm.runInContext('colorParaGuardar({ dibujo: "bolsa-cafe", color: "#2F5D8A" })', e), '');
campos.delete('#fColor');
campos.get('#fDibujo').value = 'bolsa-cafe';
assert.equal(vm.runInContext('colorParaGuardar({ dibujo: "bolsa-cafe", color: "#2F5D8A" })', e), '');

console.log('dibujos_ui: ok');
