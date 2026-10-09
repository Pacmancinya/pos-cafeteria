/* La caja usa el contrato de balanza aunque el servidor aún no esté disponible.
 * Los dobles guardan los cuerpos enviados, no recalculan precios por su cuenta. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const fuente = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
function funcion(nombre) {
  const inicio = fuente.search(new RegExp(`^(?:async )?function ${nombre}\\(`, 'm'));
  assert(inicio >= 0, nombre);
  return fuente.slice(inicio, fuente.indexOf('\n}', inicio) + 2);
}
const elementos = new Map();
const nodo = (extra = {}) => ({ value: '', innerHTML: '', textContent: '', checked: false,
  hidden: false, dataset: {}, oyentes: {}, classList: { add() {}, remove() {} },
  addEventListener(tipo, fn) { this.oyentes[tipo] = fn; }, ...extra });
const poner = (id, extra) => { const n = nodo(extra); elementos.set(id, n); return n; };
const avisos = [];
const almacen = new Map();
const c = { console, document: { activeElement: null },
  $: (id) => elementos.get(id) || null,
  localStorage: { getItem: (k) => almacen.get(k), setItem: (k, v) => almacen.set(k, v) },
  CATEGORIAS: [], AJUSTES: {}, MINUTOS_QUIETO: 5, IVA: 0.19,
  puedo: () => true, usarInventario: () => true, invEscanear: () => false,
  avisar: (...a) => avisos.push(a),
  dialogoProductoNuevoPorCodigo: () => assert.fail('No debe abrir producto nuevo'),
  pintarTalCual() {}, pintarCodigos() {}, selectorDeDibujo: () => '<input id="fDibujo">', colorParaGuardar: (p) => p.color || '',
  cargarCarta: async () => {}, estadoAfueraHTML: () => '', cargarAjustesDelLocal() {},
};
c.window = c;
vm.createContext(c);
vm.runInContext(fuente.slice(fuente.indexOf('const clp ='), fuente.indexOf('/* El mismo')), c);
const persistencia = fuente.slice(fuente.indexOf('let carrito ='), fuente.indexOf('let medioPago'));
vm.runInContext(persistencia.replace('let carrito', 'var carrito'), c);
vm.runInContext(fuente.match(/^const totalCarrito = .*;$/m)[0], c);
for (const nombre of ['alEscanear', 'agregarBalanza', 'pintarCarrito', 'lineasParaVenta',
  'sumarAlPedido', 'productoDeLaCarta', 'cambiarCantidad', 'quitarLineaDelPedido', 'confirmarVenta',
  'limpiarCarritoDeBorrados', 'costoConIva', 'bloqueSugerido']) {
  vm.runInContext(funcion(nombre), c);
}
for (const id of ['#lineas', '#total', '#btnCobrar']) poner(id);
const etiqueta = { codigo: '2500070002501', modo: 'plu_peso', nombre: 'Jamón pierna',
  detalle: '0,250 kg a $8.990/kg', precio: 2248, producto_id: 7, repetible: true };
const digi = { modo: 'ticket', prefijo: '25', codigo: [2, 6], valor: [6, 12], divisor_peso: 1000 };
const plano = (v) => JSON.parse(JSON.stringify(v));

(async () => {
  c.CATEGORIAS = [{ id: 1, productos: [{ id: 7, stock: 0 }] }];
  c.api = async () => ({ encontrado: false, de_balanza: true, balanza: etiqueta });
  await c.alEscanear(etiqueta.codigo);
  assert.equal(avisos.at(-1)[0], 'Jamón pierna · 0,250 kg');
  // La MISMA etiqueta leída dos veces no se cobra dos veces: se avisa y se usa el +.
  await c.alEscanear(etiqueta.codigo);
  assert.equal(c.carrito.length, 1);
  assert.equal(c.carrito[0].cantidad, 1);
  assert.deepEqual(avisos.at(-1), ['Esa etiqueta ya está en el pedido. Si son dos iguales, usa el +.', true]);
  c.cambiarCantidad(c.carrito[0].id, 1);
  assert.equal(c.carrito[0].cantidad, 2);
  assert(c.carrito[0].id < 0);
  assert(!('producto_id' in c.carrito[0]));
  assert(elementos.get('#lineas').innerHTML.includes(etiqueta.detalle));
  assert(!elementos.get('#lineas').innerHTML.includes('c/u'));
  assert.equal(elementos.get('#total').textContent, '$4.496');
  // El precio que se vio viaja para comparar, nunca como precio a cobrar.
  assert.deepEqual(plano(c.lineasParaVenta()),
    [{ codigo_balanza: etiqueta.codigo, cantidad: 2, precio_visto: 2248 }]);
  // Si al volver a escanear vale otra cosa, la línea toma el precio nuevo y lo dice.
  c.api = async () => ({ encontrado: false, de_balanza: true,
    balanza: { ...etiqueta, precio: 4748, detalle: '0,250 kg a $18.990/kg' } });
  await c.alEscanear(etiqueta.codigo);
  assert.equal(c.carrito[0].precio, 4748);
  assert.equal(c.carrito[0].cantidad, 2);
  assert.deepEqual(avisos.at(-1), ['Jamón pierna cambió de precio: ahora $4.748', true]);
  c.api = async () => ({ encontrado: false, de_balanza: true, balanza: etiqueta });
  c.carrito[0].precio = etiqueta.precio;
  c.cambiarCantidad(c.carrito[0].id, 1);
  assert.equal(c.carrito[0].cantidad, 3, 'no usa stock por unidad');
  c.carrito[0].cantidad = 999;
  await c.alEscanear(etiqueta.codigo);
  c.cambiarCantidad(c.carrito[0].id, 1);
  c.sumarAlPedido(c.carrito[0]);
  assert.equal(c.carrito[0].cantidad, 999);

  c.carrito = [];
  const ticket = { ...etiqueta, codigo: '2539760001975', modo: 'ticket',
    detalle: 'Ticket 3976', precio: 197, repetible: false };
  c.api = async () => ({ de_balanza: true, balanza: ticket });
  await c.alEscanear(ticket.codigo);
  await c.alEscanear(ticket.codigo);
  assert.equal(c.carrito[0].cantidad, 1);
  assert.equal(avisos.at(-1)[0], 'Ese ticket ya está en el pedido');
  c.cambiarCantidad(c.carrito[0].id, 1);
  assert.equal(c.carrito[0].cantidad, 1);
  assert.equal(avisos.at(-1)[0], 'Un ticket de la balanza se cobra una sola vez');
  c.carrito.push({ id: 999, nombre: 'Borrado', cantidad: 1, precio: 1 });
  c.limpiarCarritoDeBorrados();
  assert.equal(c.carrito.length, 1);
  assert(elementos.get('#lineas').innerHTML.includes('Ticket 3976'));
  // Se vuelve a ejecutar la carga real de localStorage, como al abrir la página.
  vm.runInContext(persistencia.slice(0, persistencia.indexOf('const guardarCarrito'))
    .replace('let carrito', 'carrito'), c);
  assert.equal(c.carrito[0].codigo, ticket.codigo);
  assert.equal(c.carrito[0].repetible, false);
  assert.deepEqual(plano(c.lineasParaVenta()),
    [{ codigo_balanza: ticket.codigo, cantidad: 1, precio_visto: 197 }]);
  // Un 409 conserva el pedido para que el cajero pueda corregirlo.
  for (const id of ['#cobroConfirmar', '#descuento', '#propina', '#pagaCon']) poner(id);
  c.medioPago = 'efectivo';
  c.mixto = false;
  c.api = async (ruta, opciones) => {
    assert.equal(ruta, '/ventas');
    assert.deepEqual(JSON.parse(opciones.body).lineas,
      [{ codigo_balanza: ticket.codigo, cantidad: 1, precio_visto: 197 }]);
    throw Error('Ese ticket ya fue cobrado');
  };
  await c.confirmarVenta();
  assert.equal(c.carrito.length, 1);
  assert.deepEqual(avisos.at(-1), ['Ese ticket ya fue cobrado', true]);
  assert.equal(elementos.get('#cobroConfirmar').disabled, false);
  c.cambiarCantidad(c.carrito[0].id, -1);
  assert.equal(c.carrito.length, 0);
  c.agregarBalanza(etiqueta);
  c.quitarLineaDelPedido(c.carrito[0].id);
  assert.equal(c.carrito.length, 0);
  c.api = async () => ({ de_balanza: true, se_puede_guardar: false, problema: 'PLU desconocido' });
  await c.alEscanear(etiqueta.codigo);
  assert.deepEqual(avisos.at(-1), ['PLU desconocido', true]);
  assert.equal(c.carrito.length, 0);

  // La ficha y sus precios por kilo se prueban en inventario_ui.cjs; el formato del código, en config_logica.cjs.
  // Un producto por kilo no entra tocando su azulejo a $0.
  const antesDelKilo = c.carrito.length;
  c.CATEGORIAS = [{ id: 1, productos: [{ id: 77, nombre: 'Queso laminado', precio: 0, precio_kilo: 12990 }] }];
  c.sumarAlPedido({ id: 77 });
  assert.equal(c.carrito.length, antesDelKilo);
  assert.deepEqual(avisos.at(-1), ['Queso laminado se vende por peso: escanea la etiqueta de la balanza.', true]);
  // La etiqueta de prueba de Config: el lector llena el campo de prueba y NO suma nada al pedido.
  const probadas = [];
  c.Config = { campoDePrueba: () => ({ value: '' }), probarEtiqueta: async () => { probadas.push(1); } };
  c.carrito = [];
  await c.alEscanear(etiqueta.codigo);
  assert.equal(c.carrito.length, 0);
  assert.equal(probadas.length, 1);
  c.Config.campoDePrueba = () => null;
  c.api = async () => ({ de_balanza: true, balanza: etiqueta });
  await c.alEscanear(etiqueta.codigo);
  assert.equal(c.carrito.length, 1, 'sin el campo de prueba a la vista, la etiqueta se vende');
  console.log('Balanza UI: carrito, ficha, formato y prueba de etiquetas OK');
})().catch((e) => { console.error(e); process.exitCode = 1; });
