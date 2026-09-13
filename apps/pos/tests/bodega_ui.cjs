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
const elementos = new Map();
const pedidos = [];
let aviso = '';
const contexto = {
  console, Number, String, JSON, Math,
  $: (id) => elementos.get(id) || null,
  esc: (s) => String(s),
  soloNumeros: (s) => Number(s),
  usarInventario: () => true,
  avisar: (s) => { aviso = s; },
  cargarBodega: async () => {}, cargarCarta: async () => {},
  api: async (ruta, datos) => { pedidos.push([ruta, JSON.parse(datos.body)]); return { id: 4 }; },
  BODEGA: { productos: [
    { id: 1, nombre: 'Pastél de limón', stock: 12, codigos: ['7801234567894'] },
    { id: 2, nombre: 'Agua', stock: 3, codigos: [] },
  ] },
};
vm.createContext(contexto);
for (const nombre of ['filtrarBodega', 'pintarBodega', 'alEscanear',
    'cantidadBodegaValida', 'guardarCantidadBodega', 'editarCantidadBodega',
    'guardarProductoDelCodigo', 'pintarTalCual']) {
  vm.runInContext(funcion(nombre), contexto);
}
const nodo = (extra = {}) => ({ value: '', innerHTML: '', hidden: false,
  dataset: {}, style: {}, classList: { remove() {}, add() {} }, ...extra });
elementos.set('#buscarBodega', nodo());
elementos.set('#tablaInsumos', nodo());
elementos.set('.vista.is-on', nodo({ dataset: { vista: 'inventario' } }));

(async () => {
  for (const q of ['PASTEL', 'limón', '7801234567894']) {
    elementos.get('#buscarBodega').value = q;
    contexto.pintarBodega();
    assert(elementos.get('#tablaInsumos').innerHTML.includes('Pastél de limón'));
    assert(!elementos.get('#tablaInsumos').innerHTML.includes('>Agua<'));
  }
  await contexto.alEscanear('7801234567894');
  assert.equal(elementos.get('#buscarBodega').value, '7801234567894');
  assert.equal(pedidos.length, 0, 'escanear en Bodega no consulta ni agrega una venta');
  elementos.get('#buscarBodega').value = 'inexistente';
  contexto.pintarBodega();
  assert(elementos.get('#tablaInsumos').innerHTML.includes('No hay productos'));

  const td = nodo();
  const controles = [nodo(), nodo()];
  elementos.set('#editarCantidad1', nodo({ hidden: true,
    querySelector: () => td, querySelectorAll: () => controles }));
  elementos.set('#cantidadBodega1', nodo({ value: '8', focus() {}, select() {} }));
  elementos.set('#motivoBodega1', nodo());
  contexto.editarCantidadBodega(1);
  assert.equal(elementos.get('#editarCantidad1').hidden, false);
  assert(td.innerHTML.includes('data-paso-bodega="-1"'));
  assert(td.innerHTML.includes('data-paso-bodega="1"'));
  assert(td.innerHTML.includes('id="motivoBodega1" hidden'));
  assert(td.innerHTML.includes('data-razon="se perdio"'));
  await contexto.guardarCantidadBodega(1, 'se perdio');
  assert.deepEqual(pedidos.pop(), ['/bodega/1/cantidad', {
    cantidad: 8, stock_esperado: 12, motivo: 'se perdio',
  }]);
  for (const valor of ['', '-1', '1.5', 'Infinity']) {
    elementos.get('#cantidadBodega1').value = valor;
    assert.equal(contexto.cantidadBodegaValida(1), null);
  }

  elementos.set('#cdNombre', nodo({ value: 'Agua nueva' }));
  elementos.set('#cdPrecio', nodo({ value: '1500' }));
  elementos.set('#cdCat', nodo({ value: '2' }));
  elementos.set('#capaCodigo', nodo());
  await contexto.guardarProductoDelCodigo('');
  assert.equal(pedidos.at(-1)[1].llevar_cuenta, false);
  elementos.set('#cdCuenta', nodo({ checked: true }));
  await contexto.guardarProductoDelCodigo('');
  assert.equal(pedidos.at(-1)[1].llevar_cuenta, true);
  for (const campo of ['tal_cual', 'costo', 'stock_inicial', 'minimo']) {
    assert(!(campo in pedidos.at(-1)[1]));
  }
  elementos.set('#zonaTalCual', nodo());
  await contexto.pintarTalCual({ llevar_cuenta: false });
  assert(!elementos.get('#zonaTalCual').innerHTML.includes('checked'));
  await contexto.pintarTalCual({ llevar_cuenta: true });
  assert(elementos.get('#zonaTalCual').innerHTML.includes('checked'));
  console.log('Bodega UI: búsqueda, escáner, edición, motivo y casilla OK');
})().catch((e) => { console.error(e); process.exitCode = 1; });
