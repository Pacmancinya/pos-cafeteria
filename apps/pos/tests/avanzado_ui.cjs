/* La sección «Avanzado» de la ficha del producto: el costo, el IVA y qué cobrar.
 *
 * Se prueba acá y no en Python porque la cuenta vive en el navegador: el costo
 * no se guarda en ninguna columna del producto, es una sugerencia que se
 * recalcula con cada tecla. Lo único que llega al servidor es el precio que la
 * persona decidió y, si el producto lleva cuenta, el costo para la Bodega.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const fuente = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');

function funcion(nombre) {
  const inicio = fuente.search(new RegExp(`^(?:async )?function ${nombre}\\(`, 'm'));
  assert(inicio >= 0, nombre);
  return fuente.slice(inicio, fuente.indexOf('\n}', inicio) + 2);
}

const contexto = {
  console, Number, String, JSON, Math,
  AJUSTES: { margen_sugerido: 50, redondeo_precio: 50 },
  IVA: 0.19,
};
vm.createContext(contexto);
for (const nombre of ['costoConIva', 'precioSugerido', 'bloqueSugerido']) {
  vm.runInContext(funcion(nombre), contexto);
}
const { costoConIva, precioSugerido, bloqueSugerido } = contexto;

// ---------------------------------------------------------------- el IVA
assert.equal(costoConIva(1190, true), 1190, 'con IVA se deja tal cual');
assert.equal(costoConIva(1000, false), 1190, 'sin IVA se le suma el 19%');
assert.equal(costoConIva(0, false), 0);
assert.equal(costoConIva(-50, true), 0, 'un costo negativo no existe');
assert.equal(costoConIva('', true), 0);

/* La razón de ser de la casilla: comprando con factura, el precio neto marcado
 * como si trajera IVA daría un margen que no queda. Con la casilla apagada, el
 * margen pedido es el margen que de verdad se lleva el dueño. */
const NETO = 1000;
for (const margen of [40, 50, 60, 75]) {
  const malo = precioSugerido(NETO, margen);                    // creyéndolo bruto
  const bueno = precioSugerido(costoConIva(NETO, false), margen);
  assert(bueno > malo, 'tratar un neto como bruto siempre cobra de menos');
  // Lo que le queda al dueño después de enterar el IVA de la venta, sobre el neto.
  const real = (bueno / 1.19 - NETO) / (bueno / 1.19) * 100;
  assert(Math.abs(real - margen) <= 2.5, `margen real ${real} vs pedido ${margen}`);
}

// ---------------------------------------------------------------- el recuadro
assert.equal(bloqueSugerido(0, 'fPrecio'), '', 'sin costo no se dibuja nada');
const html = bloqueSugerido(1190, 'fPrecio');
assert(html.includes('data-costo="1190"'));
assert(html.includes('data-destino="fPrecio"'), 'el precio que pisa es el de la ficha');
assert(html.includes('data-usar-sugerido'));

// ------------------------------------------------- que la ficha lo tenga puesto
const desde = fuente.indexOf('function abrirFichaProducto(');
const hasta = fuente.indexOf('\nfunction nuevoProducto(', desde);
assert(desde >= 0 && hasta > desde, 'no encuentro la ficha del producto');
const ficha = fuente.slice(desde, hasta);
for (const trozo of ['id="fAvanzado"', 'id="fCosto"', 'id="fCostoConIva"',
                     'id="fSugerido"', 'bloqueSugerido(costoReal(), "fPrecio")']) {
  assert(ficha.includes(trozo), `falta ${trozo} en la ficha`);
}
assert(ficha.includes('<details'), 'el cuadro tiene que venir plegado');
assert(!ficha.includes('fAvanzado").open = true'),
  'no se abre solo: el dueño pidió que fuera una opción avanzada');

// La cantidad inicial solo se manda cuando la cuenta EMPIEZA. Si ya se llevaba,
// el número vive en la Bodega y mandarlo otra vez lo sumaría encima.
assert(/stock_inicial:[^]*?\$\("#fStockInicial"\)/.test(ficha));
assert(ficha.includes('$("#fCuenta").checked && !p.llevar_cuenta'));

// ------------------------------------------------- la casilla y su cantidad
const elementos = new Map();
const nodo = (extra = {}) => ({ value: '', innerHTML: '', hidden: false, checked: false,
  dataset: {}, style: {}, oyentes: {},
  addEventListener(q, f) { this.oyentes[q] = f; }, ...extra });
contexto.$ = (id) => elementos.get(id) || null;
contexto.usarInventario = () => true;
vm.runInContext(funcion('pintarTalCual'), contexto);

(async () => {
  // Producto que todavía no se cuenta: la pregunta existe, pero escondida.
  elementos.set('#zonaTalCual', nodo());
  await contexto.pintarTalCual({ llevar_cuenta: false });
  const zona = elementos.get('#zonaTalCual');
  assert(zona.innerHTML.includes('id="fCuantosHay"'));
  assert(zona.innerHTML.includes('id="fStockInicial"'));
  assert(/id="fCuantosHay"[^>]*hidden/.test(zona.innerHTML), 'parte escondida');

  // Al marcarla, aparece.
  const casilla = nodo();
  const caja = nodo({ hidden: true });
  elementos.set('#fCuenta', casilla);
  elementos.set('#fCuantosHay', caja);
  await contexto.pintarTalCual({ llevar_cuenta: false });
  casilla.checked = true;
  casilla.oyentes.change();
  assert.equal(caja.hidden, false, 'marcarla muestra la cantidad');
  casilla.checked = false;
  casilla.oyentes.change();
  assert.equal(caja.hidden, true, 'desmarcarla la vuelve a esconder');

  // Producto que YA se cuenta: no se pregunta. Su cantidad está en la Bodega.
  await contexto.pintarTalCual({ llevar_cuenta: true });
  assert(zona.innerHTML.includes('checked'));
  assert(!zona.innerHTML.includes('fStockInicial'),
    'volver a preguntar la cantidad de algo ya contado la sumaría dos veces');

  console.log('Avanzado UI: IVA, sugerido, plegado y cantidad inicial OK');
})().catch((e) => { console.error(e); process.exitCode = 1; });
