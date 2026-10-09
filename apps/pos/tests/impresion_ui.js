/* Ejecuta el flujo real de confirmarVenta y sus auxiliares de impresión. */
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
const plano = (v) => JSON.parse(JSON.stringify(v));
const tick = () => new Promise((resolve) => setImmediate(resolve));

function entorno(almacen = new Map()) {
  const nodos = new Map(), avisos = [], marcos = [], envios = [];
  const nodo = () => ({ value: '', checked: false, disabled: false, textContent: '',
    innerHTML: '', style: {}, remove() {}, addEventListener(tipo, fn) { this[tipo] = fn; },
    classList: { remove() { this.cerrada = true; } } });
  for (const id of ['cobroConfirmar', 'descuento', 'propina', 'pagaCon', 'capaCobro',
    ]) nodos.set('#' + id, nodo());
  const c = { console, Set, JSON, setTimeout() {},
    $: (id) => nodos.get(id), puedo: () => true,
    document: { getElementById: () => null, createElement: nodo,
      body: { appendChild: (n) => marcos.push(n) } },
    localStorage: { getItem: (k) => almacen.get(k) || null,
      setItem: (k, v) => almacen.set(k, v) },
    api: async (ruta, opciones) => {
      envios.push([ruta, opciones]);
      return { disponible: true, impresoras: [], detalle: 'Enviado a Windows' };
    },
    avisar: (...a) => avisos.push(a),
    carrito: [{ id: 9, cantidad: 1 }], medioPago: 'efectivo', mixto: false,
    lineasParaVenta: () => [{ producto_id: 9, cantidad: 1 }],
    olvidarAvisos() {}, pintarCarrito() {},
    cargarTurno() { c.turnos = (c.turnos || 0) + 1; },
    cargarCarta() { c.cartas = (c.cartas || 0) + 1; },
    AJUSTES: {}, MINUTOS_QUIETO: 3, usarInventario: () => true,
    bloqueBalanza: () => '', conectarBalanza() {}, estadoAfueraHTML: () => '',
    cargarAjustesDelLocal() {},
  };
  vm.createContext(c);
  vm.runInContext(fuente.slice(fuente.indexOf('const clp ='), fuente.indexOf('/* El mismo')), c);
  vm.runInContext(fuente.slice(fuente.indexOf('function leerImpresion()'),
    fuente.indexOf('/* ---------------- utilidades')), c);
  for (const nombre of ['confirmarVenta']) {
    vm.runInContext(funcion(nombre), c);
  }
  return { c, nodos, avisos, marcos, envios, almacen,
    preferencias: () => plano(vm.runInContext('IMPRESION', c)) };
}

(async () => {
  // Migración y corrupción: la preferencia vieja sigue funcionando; una rota
  // nunca impide abrir la pantalla ni prende la impresión por accidente.
  assert.equal(entorno(new Map([['pos.imprimir', '1']])).preferencias().automatica, true);
  assert.equal(entorno(new Map([['pos.impresion', '{"impresora":""}']])).preferencias().tipo, 'navegador');
  assert.equal(entorno(new Map([['pos.impresion', '{"impresora":"","tipo":null}']])).preferencias().tipo, null);
  for (const roto of ['{', '42', '"texto"', '{"automatica":"true","papel":60}']) {
    assert.deepEqual(entorno(new Map([['pos.impresion', roto]])).preferencias(),
      { automatica: false, impresora: '', papel: 80, tipo: null, puerto: '' });
  }
  let e = entorno();
  e.c.localStorage.getItem = () => { throw Error('Sin almacenamiento'); };
  assert.deepEqual(plano(e.c.leerImpresion()), { automatica: false, impresora: '', papel: 80, tipo: null, puerto: '' });

  const guardadas = new Map([['pos.impresion', JSON.stringify({
    automatica: true, impresora: 'Caja', papel: 58 })]]);
  // Un driver que no contesta no bloquea el siguiente cobro; doble clic de
  // impresión en la misma venta tampoco inicia otro envío pendiente.
  e = entorno(guardadas);
  let terminar;
  e.c.api = (ruta, opciones) => {
    e.envios.push([ruta, opciones]);
    return ruta === '/ventas' ? Promise.resolve({ id: 7, numero: 12 })
      : new Promise((resolve) => { terminar = resolve; });
  };
  await e.c.confirmarVenta();
  assert.equal(e.envios.filter(([r]) => r === '/ventas').length, 1);
  assert.deepEqual(JSON.parse(e.envios[0][1].body), {
    lineas: [{ producto_id: 9, cantidad: 1 }], medio_pago: 'efectivo', descuento: 0, propina: 0 });
  assert.equal(e.c.carrito.length, 0);
  assert.equal(e.nodos.get('#cobroConfirmar').disabled, false);
  assert(e.nodos.get('#capaCobro').classList.cerrada);
  assert.equal(e.c.ultimaVenta, 7);
  assert.equal(e.c.turnos, 1);
  assert.equal(e.c.cartas, 1);
  assert(e.avisos.some(([a]) => a === 'Venta #12 registrada'));
  await e.c.imprimir('/comprobante/7');
  assert.equal(e.envios.length, 2);
  assert.deepEqual(JSON.parse(e.envios[1][1].body), { impresora: 'Caja', papel: 58 });
  terminar({ ok: true });
  await tick();

  for (const falla of [() => Promise.reject(Error('Driver falló')), () => { throw Error('Sin red'); }]) {
    e = entorno(guardadas);
    e.c.api = (ruta, opciones) => {
      e.envios.push([ruta, opciones]);
      return ruta === '/ventas' ? Promise.resolve({ id: 7, numero: 12 }) : falla();
    };
    await e.c.confirmarVenta();
    await tick();
    assert.equal(e.envios.length, 2, 'no reintenta papel ni cobro');
    assert.equal(e.marcos.length, 0, 'no cae al navegador después de enviar a Windows');
    assert.equal(e.c.carrito.length, 0);
    assert.equal(e.nodos.get('#cobroConfirmar').disabled, false);
    assert(e.avisos.at(-1)[0].includes('La venta sigue registrada'));
  }

  e = entorno();
  e.c.api = async () => ({ id: 8, numero: 13 });
  await e.c.confirmarVenta();
  assert.equal(e.marcos.length, 0, 'apagado no imprime');
  await e.c.imprimir('/comprobante/8');
  assert.equal(e.marcos[0].src, '/comprobante/8?papel=80');
  e.c.document.createElement = () => { throw Error('Marco no disponible'); };
  await e.c.imprimir('/comprobante/9');
  assert(e.avisos.at(-1)[0].includes('La venta sigue registrada'));
  // Cada tipo elige su ruta, y los cierres conservan siempre el navegador.
  for (const tipo of ['termica', 'windows', 'navegador']) {
    e = entorno(new Map([['pos.impresion', JSON.stringify({
      automatica: true, impresora: 'Sewoo', papel: 80, tipo })]]));
    await e.c.imprimir('/comprobante/20');
    if (tipo === 'navegador') {
      assert.equal(e.envios.length, 0);
      assert.equal(e.marcos[0].src, '/comprobante/20?papel=80');
    } else {
      assert.equal(e.envios[0][0], `/impresion/${tipo === 'termica' ? 'crudo/' : ''}comprobante/20`);
    }
    const llamadas = e.envios.length;
    await e.c.imprimir('/cierre/4');
    assert.equal(e.envios.length, llamadas);
    assert.equal(e.marcos.at(-1).src, '/cierre/4?papel=80');
  }

  // El tipo se deduce del nombre y del puerto cuando el dueño no eligió uno (la pantalla de
  // Config lo guarda en config.js; la deducción se prueba en config_logica.cjs).
  assert.equal(entorno(new Map([['pos.impresion', JSON.stringify({ impresora: 'Caja', papel: 80, puerto: 'USB001' })]])).c.tipoImpresion(), 'termica');
  console.log('Impresión UI: tipos, instalación, persistencia y cobro aislado OK');
})().catch((e) => { console.error(e); process.exitCode = 1; });
