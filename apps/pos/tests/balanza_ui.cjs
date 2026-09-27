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
  puedo: () => true, usarInventario: () => true,
  avisar: (...a) => avisos.push(a),
  dialogoProductoNuevoPorCodigo: () => assert.fail('No debe abrir producto nuevo'),
  pintarTalCual() {}, pintarCodigos() {}, selectorDeDibujo: () => '<input id="fDibujo">',
  cargarCarta: async () => {}, estadoAfueraHTML: () => '', cargarAjustesDelLocal() {},
};
vm.createContext(c);
vm.runInContext(fuente.slice(fuente.indexOf('const clp ='), fuente.indexOf('/* El mismo')), c);
const persistencia = fuente.slice(fuente.indexOf('let carrito ='), fuente.indexOf('let medioPago'));
vm.runInContext(persistencia.replace('let carrito', 'var carrito'), c);
vm.runInContext(fuente.match(/^const totalCarrito = .*;$/m)[0], c);
for (const nombre of ['alEscanear', 'agregarBalanza', 'pintarCarrito', 'lineasParaVenta',
  'sumarAlPedido', 'productoDeLaCarta', 'cambiarCantidad', 'quitarLineaDelPedido', 'confirmarVenta',
  'limpiarCarritoDeBorrados', 'abrirFichaProducto', 'costoConIva', 'bloqueSugerido',
  'dibujoFormatoBalanza', 'bloqueBalanza', 'leerFormatoBalanza', 'conectarBalanza',
  'guardarFormatoBalanza', 'probarEtiquetaBalanza', 'pintarAjustes']) {
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

  // Ejecutamos Guardar de la ficha completa, tanto al crear como al editar.
  const p = { id: 7, nombre: 'Jamón', precio: 1000, plu: '0007', precio_kilo: 8990 };
  c.CATEGORIAS = [{ id: 1, activa: true, productos: [p] }];
  c.PRODUCTO_EN_BLANCO = { nombre: '', precio: 0 };
  c.catActiva = 1;
  c.setTimeout = () => {};
  c.puedo = (permiso) => permiso !== 'inventario';
  const dialogo = poner('#dialogoProducto');
  // El doble crea los campos insertados; los valores que se escriben se ponen abajo.
  Object.defineProperty(dialogo, 'innerHTML', { get() { return this.html; }, set(html) {
    this.html = html;
    for (const [, id] of html.matchAll(/id="([^"]+)"/g)) poner('#' + id);
  } });
  poner('#capaProducto');
  const envios = [];
  c.api = async (ruta, opciones) => {
    envios.push([ruta, opciones.method, JSON.parse(opciones.body)]);
    return { id: 7 };
  };
  for (const nuevo of [false, true]) {
    c.abrirFichaProducto(nuevo ? null : 7, 1);
    assert.equal(/id="fBalanza" open/.test(dialogo.html), !nuevo);
    elementos.get('#fNombre').value = 'Jamón';
    elementos.get('#fPlu').value = '00x07';
    const plu = elementos.get('#fPlu');
    plu.oyentes.input({ target: plu });
    assert.equal(plu.value, '0007');
    elementos.get('#fPrecioKilo').value = '8.990';
    await elementos.get('#fGuardar').onclick();
    assert.equal(envios.at(-1)[1], nuevo ? 'POST' : 'PUT');
    assert.equal(envios.at(-1)[2].plu, '0007');
    assert.equal(envios.at(-1)[2].precio_kilo, 8990);
  }
  elementos.get('#fPlu').value = '';
  elementos.get('#fPrecioKilo').value = '';
  await elementos.get('#fGuardar').onclick();
  assert.equal(envios.at(-1)[2].plu, '');
  assert.equal(envios.at(-1)[2].precio_kilo, 0);
  c.api = async () => { throw Error('Ese PLU ya está en otro producto'); };
  await elementos.get('#fGuardar').onclick();
  assert.deepEqual(avisos.at(-1), ['Ese PLU ya está en otro producto', true]);

  assert.equal(c.dibujoFormatoBalanza(digi).split('\n')[1], 'PPNNNN$$$$$$V');
  // Un campo vacío o al revés no se dibuja como una superposición inventada.
  assert(c.dibujoFormatoBalanza({ ...digi, codigo: [null, 6] }).startsWith('Falta o está mal'));
  assert(c.dibujoFormatoBalanza({ ...digi, valor: [7, 3] }).includes('el valor'));
  assert(c.dibujoFormatoBalanza({ ...digi, prefijo: '78' }).includes('prefijo'));
  // Un producto por kilo no entra tocando su azulejo a $0.
  const antesDelKilo = c.carrito.length;
  c.CATEGORIAS = [{ id: 1, productos: [{ id: 77, nombre: 'Queso laminado', precio: 0, precio_kilo: 12990 }] }];
  c.sumarAlPedido({ id: 77 });
  assert.equal(c.carrito.length, antesDelKilo);
  assert.deepEqual(avisos.at(-1), ['Queso laminado se vende por peso: escanea la etiqueta de la balanza.', true]);
  assert(c.bloqueBalanza().includes('value="ticket" selected'));
  assert(c.bloqueBalanza().includes('value="25"'));
  assert(c.dibujoFormatoBalanza({ ...digi, codigo: [2, 7] }).includes('!'));
  for (const [id, valor] of Object.entries({ Modo: 'plu_peso', Prefijo: '25',
    CodigoDesde: '2', CodigoHasta: '6', ValorDesde: '6', ValorHasta: '12', Divisor: '1000' })) {
    poner('#ajBalanza' + id, { value: valor });
  }
  for (const id of ['#ajBalanza', '#ajBalanzaDibujo', '#ajBalanzaDivisorCampo',
    '#ajBalanzaGuardar', '#ajBalanzaProbar', '#ajBalanzaPrueba', '#ajBalanzaResultado',
    '#ajUsarBalanza', '#ajBalanzaCuerpo']) poner(id);
  // Viene apagada: la casilla prende la balanza en el servidor y muestra el resto.
  assert(!c.bloqueBalanza().includes('id="ajUsarBalanza" checked'));
  assert(/id="ajBalanzaCuerpo" hidden/.test(c.bloqueBalanza()));
  const guardados = [];
  c.guardarAjuste = async (cambios) => { guardados.push(cambios); };
  c.conectarBalanza();
  elementos.get('#ajUsarBalanza').checked = true;
  elementos.get('#ajUsarBalanza').oyentes.change({ target: elementos.get('#ajUsarBalanza'), stopPropagation() {} });
  assert.deepEqual(plano(guardados.at(-1)), { usar_balanza: 1 });
  assert.equal(elementos.get('#ajBalanzaCuerpo').hidden, false);
  c.AJUSTES.usar_balanza = 1;
  assert(c.bloqueBalanza().includes('id="ajUsarBalanza" checked'));
  elementos.get('#ajBalanza').oyentes.input();
  assert.equal(elementos.get('#ajBalanzaDivisorCampo').hidden, false);
  elementos.get('#ajBalanzaModo').value = 'ticket';
  elementos.get('#ajBalanza').oyentes.input();
  assert.equal(elementos.get('#ajBalanzaDivisorCampo').hidden, true);
  assert.equal(elementos.get('#ajBalanzaDibujo').textContent, c.dibujoFormatoBalanza(digi));
  c.api = async (ruta, opciones) => {
    assert.equal(ruta, '/ajustes');
    assert.equal(opciones.method, 'PUT');
    assert.deepEqual(JSON.parse(opciones.body), { formato_balanza: digi });
    return { formato_balanza: digi };
  };
  await elementos.get('#ajBalanzaGuardar').onclick();
  assert.deepEqual(plano(c.AJUSTES.formato_balanza), digi);
  c.api = async () => { throw Error('Las posiciones se solapan'); };
  await c.guardarFormatoBalanza();
  assert.equal(elementos.get('#ajBalanzaResultado').textContent, 'Las posiciones se solapan');
  assert.equal(elementos.get('#ajBalanzaPrefijo').value, '25');
  elementos.get('#ajBalanzaCodigoDesde').value = '';
  assert.equal(c.leerFormatoBalanza().codigo[0], null);

  // La prueba llama GET sin mandar el borrador del formato ni agregar al pedido.
  c.api = async (ruta, opciones) => {
    assert.equal(ruta, '/codigos/' + etiqueta.codigo);
    assert.equal(opciones, undefined);
    return { balanza: etiqueta };
  };
  c.document.activeElement = elementos.get('#ajBalanzaPrueba');
  await c.alEscanear(etiqueta.codigo);
  assert.equal(c.carrito.length, 0);
  assert.equal(elementos.get('#ajBalanzaResultado').textContent,
    'Jamón pierna · 0,250 kg a $8.990/kg · $2.248');
  c.api = async () => ({ problema: 'Ticket ya cobrado' });
  await c.probarEtiquetaBalanza();
  assert.equal(elementos.get('#ajBalanzaResultado').textContent, 'Ticket ya cobrado');
  c.puedo = () => false;
  c.api = () => assert.fail('Sin config no se prueba ni se guarda');
  await c.guardarFormatoBalanza();
  await c.probarEtiquetaBalanza();
  poner('#panelAjustes', { innerHTML: 'viejo' });
  c.pintarAjustes();
  assert.equal(elementos.get('#panelAjustes').innerHTML, '');
  console.log('Balanza UI: carrito, ficha, formato y prueba de etiquetas OK');
})().catch((e) => { console.error(e); process.exitCode = 1; });
