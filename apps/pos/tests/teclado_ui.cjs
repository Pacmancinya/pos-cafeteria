/* El teclado de teléfono (1-9, ✱, 0, ⌫) y el multiplicador de la pantalla de venta.
 * Corre teclado.js y los trozos de app.js que lo usan en un entorno falso, sin navegador. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const estaticos = path.join(__dirname, '../static');
const tecladoJs = fs.readFileSync(path.join(estaticos, 'teclado.js'), 'utf8');
const appJs = fs.readFileSync(path.join(estaticos, 'app.js'), 'utf8');

/* ---- teclado.js ---- */
const window = { addEventListener() {} };
const documento = { body: null, addEventListener() {}, getElementById: () => null };
const ctx = { console, window, document: documento };
vm.createContext(ctx);
vm.runInContext(tecladoJs, ctx);
const T = window.Teclado;
assert(T, 'teclado.js no publicó window.Teclado');
const m = T.multiplicador;
const estado = () => JSON.parse(JSON.stringify({ buf: m.buf, armado: m.armado, visor: m.visor() }));
const tocar = (...ks) => ks.forEach((k) => m.tecla(k));

/* La grilla es la de un teléfono y no tiene Listo ni C. */
for (const modo of [null, 'monto', 'entero', 'pin']) {
  const t = T.teclasDe(modo);
  assert.equal(t.map((x) => x.tecla).join(','),
    '1,2,3,4,5,6,7,8,9,extra,0,borrar', `orden (${modo})`);
  const borrar = t[11];
  assert.equal(borrar.rotulo, '⌫');
  assert.equal(borrar.etiqueta, 'Borrar');
  const html = T.grillaHTML(modo);
  assert(!/Listo/i.test(html), 'no hay botón Listo');
  assert(!/>C</.test(html), 'no hay botón C');
  assert(!/>#</.test(html), 'la tecla de borrar es ⌫, no #');
  assert(html.includes('data-tecla="borrar" tabindex="-1" aria-label="Borrar"'), 'aria-label Borrar');
}
/* ✱ del panel de campos: «000» solo en montos; en los demás modos está apagada. */
assert.equal(T.teclasDe('monto')[9].rotulo, '000');
assert(!T.teclasDe('monto')[9].apagada);
for (const modo of ['entero', 'pin']) {
  assert.equal(T.teclasDe(modo)[9].rotulo, '✱');
  assert(T.teclasDe(modo)[9].apagada, `✱ apagada en ${modo}`);
  assert(/data-tecla="extra"[^>]*disabled/.test(T.grillaHTML(modo)));
}
/* En el teclado de multiplicar es ✱ de verdad. */
assert.equal(T.teclasDe(null)[9].rotulo, '✱');
assert(!T.teclasDe(null)[9].apagada);

/* Con el modo táctil apagado el multiplicador no existe: siempre 1. */
tocar('2', 'extra');
assert.equal(m.tomar(), 1);
assert.deepEqual(estado(), { buf: '', armado: false, visor: '' });

T.encender(true);

/* 2 ✱ y un producto → 2 unidades; después se limpia. */
tocar('2');
assert.equal(estado().visor, '2');
tocar('extra');
assert.equal(estado().visor, '2 ×');
assert.equal(m.tomar(), 2);
assert.deepEqual(estado(), { buf: '', armado: false, visor: '' });
assert.equal(m.tomar(), 1, 'sin nada armado entra 1');

/* Números sin ✱ no multiplican: al tocar el producto se limpian y entra 1. */
tocar('5', '3');
assert.equal(estado().visor, '53');
assert.equal(m.tomar(), 1);
assert.equal(estado().visor, '');

/* Máximo 2 dígitos; un 0 inicial no entra; mínimo 1. */
tocar('1', '2', '3');
assert.equal(estado().buf, '12');
m.tecla('limpiar');
tocar('0');
assert.equal(estado().buf, '');
tocar('extra');                              // sin número, ✱ no arma nada
assert.equal(estado().armado, false);
tocar('1', '0', 'extra');
assert.equal(m.tomar(), 10);

/* ⌫ borra el último dígito; con ✱ armado, primero lo desarma. */
tocar('1', '2', 'borrar');
assert.equal(estado().buf, '1');
tocar('extra', 'borrar');
assert.deepEqual(estado(), { buf: '1', armado: false, visor: '1' });
tocar('borrar', 'borrar');                   // ya no quedan dígitos: no falla
assert.equal(estado().buf, '');

/* Un dígito nuevo con ✱ armado empieza otra cantidad. */
tocar('2', 'extra', '4');
assert.deepEqual(estado(), { buf: '4', armado: false, visor: '4' });
m.tecla('limpiar');

/* Apagar el modo táctil deja el multiplicador limpio. */
tocar('7', 'extra');
T.encender(false);
assert.deepEqual(estado(), { buf: '', armado: false, visor: '' });

/* ---- app.js: la cantidad entra de una vez, y la balanza la ignora ---- */
function funcion(nombre) {
  const inicio = appJs.search(new RegExp(`^(?:async )?function ${nombre}\\(`, 'm'));
  assert(inicio >= 0, nombre);
  return appJs.slice(inicio, appJs.indexOf('\n}', inicio) + 2);
}
const avisos = [];
const app = { console, avisar: (...a) => avisos.push(a), pintarCarrito() {},
  usarInventario: () => true, agregarBalanza: (p) => { app.balanzas.push(p); },
  balanzas: [], clp: (n) => '$' + n };
vm.createContext(app);
vm.runInContext('var carrito = []; var CATEGORIAS = [];', app);
for (const nombre of ['agregar', 'sumarAlPedido', 'productoDeLaCarta']) vm.runInContext(funcion(nombre), app);
const carro = () => JSON.parse(vm.runInContext('JSON.stringify(carrito)', app));
vm.runInContext(`CATEGORIAS = [{ id: 1, productos: [
  { id: 7, nombre: 'Latte', precio: 3000, stock: null },
  { id: 8, nombre: 'Muffin', precio: 1500, stock: 3 },
  { id: 9, nombre: 'Jamón', precio: 0, precio_kilo: 9000 },
  { id: 10, nombre: 'Ticket', precio: 500, balanza: true } ] }];`, app);

app.agregar(7, 2);
assert.equal(carro()[0].cantidad, 2, '2 ✱ Latte → 2 en el pedido');
assert.equal(carro()[0].precio, 3000, 'el precio es el de la carta, no se recalcula');
app.agregar(7, 3);
assert.equal(carro()[0].cantidad, 5, 'suma a la línea que ya estaba');
app.agregar(7);
assert.equal(carro()[0].cantidad, 6, 'sin multiplicador entra 1');

avisos.length = 0;
app.agregar(8, 5);                           // quedan 3: el tope sigue mandando
assert.equal(carro().length, 1, 'no entra si no alcanza el saldo');
assert(avisos.length && avisos[0][1] === true);
app.agregar(8, 3);
assert.equal(carro()[1].cantidad, 3);

app.agregar(9, 4);                           // por peso: no se vende por unidad
assert.equal(carro().length, 2);
app.agregar(10, 4);                          // balanza: el multiplicador se descarta
assert.equal(app.balanzas.length, 1);
assert.equal(carro().length, 2);

console.log('teclado_ui ok');
