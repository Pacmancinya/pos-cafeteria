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
    'ajImprimirSiempre', 'ajImpresora', 'ajPapel', 'ajActualizarImpresoras',
    'ajImpresionEstado', 'ajProbarImpresion', 'panelAjustes']) nodos.set('#' + id, nodo());
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
  for (const nombre of ['confirmarVenta', 'bloqueImpresion', 'guardarImpresion',
    'cargarImpresoras', 'probarImpresion', 'conectarImpresion', 'pintarAjustes']) {
    vm.runInContext(funcion(nombre), c);
  }
  return { c, nodos, avisos, marcos, envios, almacen,
    preferencias: () => plano(vm.runInContext('IMPRESION', c)) };
}

(async () => {
  // Migración y corrupción: la preferencia vieja sigue funcionando; una rota
  // nunca impide abrir la pantalla ni prende la impresión por accidente.
  assert.equal(entorno(new Map([['pos.imprimir', '1']])).preferencias().automatica, true);
  for (const roto of ['{', '42', '"texto"', '{"automatica":"true","papel":60}']) {
    assert.deepEqual(entorno(new Map([['pos.impresion', roto]])).preferencias(),
      { automatica: false, impresora: '', papel: 80 });
  }
  let e = entorno();
  e.c.localStorage.getItem = () => { throw Error('Sin almacenamiento'); };
  assert.deepEqual(plano(e.c.leerImpresion()), { automatica: false, impresora: '', papel: 80 });

  e = entorno();
  e.c.pintarAjustes();
  assert(e.nodos.get('#panelAjustes').innerHTML.includes('Impresión de comprobantes'));
  assert(e.nodos.get('#panelAjustes').innerHTML.includes('58 mm'));
  assert(e.nodos.get('#panelAjustes').innerHTML.includes('80 mm'));
  await tick();
  e.nodos.get('#ajImprimirSiempre').checked = true;
  e.nodos.get('#ajImpresora').value = 'Caja ñ';
  e.nodos.get('#ajPapel').value = '58';
  e.nodos.get('#ajPapel').change();
  assert.deepEqual(entorno(e.almacen).preferencias(),
    { automatica: true, impresora: 'Caja ñ', papel: 58 });
  e.c.localStorage.setItem = () => { throw Error('Cuota'); };
  e.nodos.get('#ajPapel').value = '80';
  e.c.guardarImpresion();
  assert.equal(e.preferencias().papel, 58);
  assert.equal(e.nodos.get('#ajPapel').value, '58');

  // Lista vacía, impresora removida y fallo de Windows no borran la selección.
  e.c.api = async () => ({ disponible: true, impresoras: [] });
  await e.c.cargarImpresoras();
  assert(e.nodos.get('#ajImpresora').innerHTML.includes('no disponible'));
  assert.equal(e.nodos.get('#ajImpresora').value, 'Caja ñ');
  e.c.api = async () => { throw Error('Windows desconectado'); };
  await e.c.cargarImpresoras();
  assert(e.nodos.get('#ajImpresionEstado').textContent.includes('Se conserva'));
  assert.equal(e.nodos.get('#ajActualizarImpresoras').disabled, false);
  e.c.api = async () => ({ disponible: false, impresoras: [], detalle: 'Requiere Windows' });
  await e.c.cargarImpresoras();
  assert.equal(e.nodos.get('#ajImpresionEstado').textContent, 'Requiere Windows');
  e.c.api = async () => ({ disponible: true, impresoras: [
    { nombre: 'Caja <ñ>', disponible: true }, { nombre: 'PDF', disponible: false }] });
  await e.c.cargarImpresoras();
  assert(e.nodos.get('#ajImpresora').innerHTML.includes('Caja &lt;ñ>'));
  assert(e.nodos.get('#ajImpresora').innerHTML.includes('disabled>PDF'));

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

  // Prueba doble: un solo POST de prueba y ningún /ventas.
  e = entorno(guardadas);
  e.c.api = (ruta, opciones) => {
    e.envios.push([ruta, opciones]);
    return new Promise((resolve) => { terminar = resolve; });
  };
  const prueba = e.c.probarImpresion();
  await e.c.probarImpresion();
  assert.equal(e.envios.length, 1);
  assert.equal(e.envios[0][0], '/impresion/prueba');
  assert.equal(e.nodos.get('#ajProbarImpresion').disabled, true);
  terminar({ detalle: 'Enviado a la cola' });
  await prueba;
  assert.equal(e.nodos.get('#ajProbarImpresion').disabled, false);
  assert.equal(e.c.carrito.length, 1);
  e.c.puedo = () => false;
  await e.c.probarImpresion();
  await e.c.cargarImpresoras();
  assert.equal(e.envios.length, 1);

  e = entorno();
  e.c.api = async () => ({ id: 8, numero: 13 });
  await e.c.confirmarVenta();
  assert.equal(e.marcos.length, 0, 'apagado no imprime');
  await e.c.imprimir('/comprobante/8');
  assert.equal(e.marcos[0].src, '/comprobante/8?papel=80');
  e.c.document.createElement = () => { throw Error('Marco no disponible'); };
  await e.c.imprimir('/comprobante/9');
  assert(e.avisos.at(-1)[0].includes('La venta sigue registrada'));
  console.log('Impresión UI: configuración, persistencia y cobro aislado OK');
})().catch((e) => { console.error(e); process.exitCode = 1; });
