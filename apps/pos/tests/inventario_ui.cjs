const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const IL = require('../static/inventario-logica.js');
const fuente = fs.readFileSync(path.join(__dirname, '../static/inventario.js'), 'utf8');
const nodos = new Map(), avisos = [], envios = [], oyentes = {};
const nodo = (extra = {}) => ({ value: '', checked: false, disabled: false, hidden: false, dataset: {},
  validity: { valid: true }, previousElementSibling: { textContent: 'Campo' },
  classList: { add() {}, remove() {} }, focus() { this.enfocado = true; }, scrollIntoView() {},
  closest() { return null; }, ...extra });
const poner = (id, extra) => { const n = nodo(extra); nodos.set(id, n); return n; };
const c = { console, window: { InventarioLogica: IL },
  document: { addEventListener: (tipo, fn) => { oyentes[tipo] = fn; } },
  $: (id) => nodos.get(id) || null, $$: () => [],
  esc: (s) => String(s ?? '').replace(/"/g, '&quot;'), clp: (n) => '$' + n,
  dibujo: () => '<svg></svg>', selectorDeDibujo: () => '<input id="fDibujo"><input id="fColor">',
  colorBolsaOk: () => false, puedo: () => true, usarInventario: () => true,
  AJUSTES: { margen_sugerido: 50, redondeo_precio: 50 },
  CATEGORIAS: [{ id: 1, nombre: 'Café', productos: [] }],
  cargarCarta: async () => {}, avisar: (...a) => avisos.push(a),
  api: async (ruta, op) => { if (op) envios.push([ruta, op.method, JSON.parse(op.body)]); return { productos: [], recetas_antiguas: false }; }
};
vm.createContext(c); vm.runInContext(fuente, c);
const dialogo = poner('#dialogoProducto');
Object.defineProperty(dialogo, 'innerHTML', { get() { return this.html; }, set(html) {
  this.html = html;
  for (const key of [...nodos.keys()]) if (!['#dialogoProducto', '#capaProducto', '#capaBodega'].includes(key)) nodos.delete(key);
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) poner('#' + id);
} });
poner('#capaProducto'); poner('#capaBodega');
const valor = (id, v) => { nodos.get('#' + id).value = String(v); };
function campos(peso = false) {
  valor('fNombre', 'Café de prueba'); valor('fCategoria', 1); valor('fPrecio', peso ? 8990 : 1500);
  valor('invCosto', 700); valor('invModo', peso ? 'peso' : 'unidad');
  valor('fPlu', '0007'); valor('fDibujo', 'mug'); valor('fColor', '');
  nodos.get('#fActivo').checked = true; nodos.get('#fTv').checked = true;
  if (nodos.has('#fCuenta')) { valor('invHay', 5); valor('invMinimo', 2); }
}
(async () => {
  await c.abrirFichaProducto(null); assert.equal(envios.length, 0, 'abrir no escribe');
  campos(true); nodos.get('#fCuenta').checked = true;
  c.invAgregarCodigo('036000291452'); c.invAgregarCodigo('0036000291452');
  await c.invGuardarFicha();
  const [ruta, method, cuerpo] = envios.at(-1);
  assert.equal(ruta, '/productos'); assert.equal(method, 'POST');
  assert.equal(cuerpo.precio, 0); assert.equal(cuerpo.precio_kilo, 8990); assert.equal(cuerpo.plu, '0007');
  assert.equal(cuerpo.codigos.length, 1); assert.equal(cuerpo.codigos[0].codigo, '0036000291452');
  assert.equal(cuerpo.hay_ahora, 5); assert.equal(cuerpo.stock_esperado, 0);
  vm.runInContext(`INV.productos = [{id:7,nombre:'Antiguo',categoria_id:1,precio:1500,costo:700,
    cuenta:true,llevar_cuenta:null,stock:5,contado:true,minimo:2,activo:true,en_tv:false,
    codigos:[{codigo:'0036000291452',cuantos:6,nota:'Pack'}]}]`, c);
  await c.abrirFichaProducto(7); campos(); nodos.get('#fCuenta').checked = true;
  await c.invGuardarFicha();
  const antiguo = envios.at(-1)[2];
  assert(!('llevar_cuenta' in antiguo)); assert(!('hay_ahora' in antiguo)); assert(!('costo' in antiguo));
  // Solo viaja lo que esta ficha cambió: el pack de 6 no se reenvía ni se pierde.
  assert.deepEqual(antiguo.codigos, []); assert.deepEqual(antiguo.codigos_quitar, []);
  const producto7 = `INV.productos = [{id:7,nombre:'Antiguo',categoria_id:1,precio:1500,costo:700,
    cuenta:true,llevar_cuenta:null,stock:5,contado:true,minimo:2,activo:true,en_tv:false,
    codigos:[{codigo:'0036000291452',cuantos:6,nota:'Pack'}]}]`;
  vm.runInContext(producto7, c);
  await c.abrirFichaProducto(7); campos(); c.invAgregarCodigo('7801234567894');
  c.invAgregarCodigo('0036000291452'); vm.runInContext('invCodigos.splice(0, 1)', c);
  await c.invGuardarFicha();
  const quitado = envios.at(-1)[2];
  assert.deepEqual(quitado.codigos.map((b) => b.codigo), ['7801234567894']);
  assert.deepEqual(quitado.codigos_quitar, ['0036000291452']);
  vm.runInContext(producto7, c); vm.runInContext(`INV.productos[0].cuenta = false; INV.productos[0].llevar_cuenta = false`, c);
  await c.abrirFichaProducto(7); campos(); nodos.get('#fCuenta').checked = true; valor('invHay', '');
  const antesHay = envios.length; await c.invGuardarFicha();
  assert.equal(envios.length, antesHay, 'prender inventario exige escribir cuántos hay');
  assert(/cuántos hay ahora/.test(avisos.at(-1)[0]));
  assert(dialogo.html.includes('¿Cuántos hay ahora?') && !/id="invHay"[^>]*value="[^"]/.test(dialogo.html));
  valor('invHay', 0); await c.invGuardarFicha();
  assert.equal(envios.at(-1)[2].hay_ahora, 0); assert.equal(envios.at(-1)[2].llevar_cuenta, true);
  valor('fCategoria', ''); const antesCat = envios.length; await c.invGuardarFicha();
  assert.equal(envios.length, antesCat, 'sin categoría válida no se guarda');
  vm.runInContext(`INV.productos = [{id:10,nombre:'Sin contar antiguo',categoria_id:1,precio:1500,
    costo:700,llevar_cuenta:null,cuenta:true,stock:-1,contado:false,minimo:0,codigos:[]}]`,c);
  await c.abrirFichaProducto(10); campos(); valor('invHay',-1); nodos.get('#fCuenta').checked=true;
  nodos.get('#invHay').validity.valid=false;
  await c.invGuardarFicha();
  assert(!('hay_ahora' in envios.at(-1)[2]),'editar nombre no cuenta un saldo legado ni activa el tope');
  assert(!('llevar_cuenta' in envios.at(-1)[2]));
  vm.runInContext(`INV.productos = [{id:9,nombre:'Unidad y balanza',categoria_id:1,precio:1500,
    precio_kilo:8990,plu:'0007',costo:700,llevar_cuenta:false,cuenta:false,codigos:[]}]`,c);
  await c.abrirFichaProducto(9); campos(); await c.invGuardarFicha();
  assert.equal(envios.at(-1)[2].precio_kilo,8990);
  assert.equal(envios.at(-1)[2].plu,'0007');
  c.puedo = (p) => p !== 'inventario'; await c.abrirFichaProducto(null);
  assert(!dialogo.html.includes('id="fCuenta"')); campos(); await c.invGuardarFicha();
  for (const campo of ['llevar_cuenta', 'hay_ahora', 'minimo']) assert(!(campo in envios.at(-1)[2]));
  c.puedo = () => true; c.usarInventario = () => false; await c.abrirFichaProducto(null);
  assert(!dialogo.html.includes('id="fCuenta"')); c.usarInventario = () => true;
  c.api = async () => { throw Error('Código ajeno'); }; campos(); await c.invGuardarFicha();
  assert.equal(avisos.at(-1)[0], 'Código ajeno'); assert.equal(nodos.get('#fGuardar').disabled, false);
  vm.runInContext(`INV.productos = [{id:8,nombre:'Receta',categoria_id:1,precio:2000,costo:0,
    receta_antigua:true,llevar_cuenta:null,cuenta:false,stock:0,codigos:[]}]`, c);
  await c.abrirFichaProducto(8); assert(!dialogo.html.includes('id="fCuenta"'));
  assert(dialogo.html.includes('receta antigua'));
  assert(dialogo.html.includes('Costo calculado por receta antigua') && /id="invCosto"[^>]*disabled/.test(dialogo.html));
  c.api = async (ruta, op) => { if (op) envios.push([ruta, op.method, JSON.parse(op.body)]); return { productos: [], recetas_antiguas: false }; };
  campos(); await c.invGuardarFicha(); assert(!('costo' in envios.at(-1)[2]), 'el costo de receta antigua no se guarda');
  vm.runInContext(`INV.productos = [{id:6,nombre:'Sin costo visible',categoria_id:1,precio:900,costo:null,
    cuenta:false,llevar_cuenta:false,stock:0,codigos:[]}]`, c);
  await c.abrirFichaProducto(6); assert(/id="invCosto"[^>]*disabled/.test(dialogo.html));
  campos(); await c.invGuardarFicha(); assert(!('costo' in envios.at(-1)[2]), 'sin permiso no se manda costo');
  // Ingredientes de recetas antiguas: mismos diálogos, solo esos insumos.
  vm.runInContext(`INV.ingredientes = [{id:3,nombre:'Leche',unidad:'ml',stock:5000,muestra:'5 L',minimo:0,minimo_muestra:'0'}]`, c);
  vm.runInContext(`invOperacion = {tipo:'entrada', producto:null, ingredientes:true}`, c);
  const pool = vm.runInContext('invPool()', c);
  assert.equal(pool.length, 1); assert.equal(pool[0].insumo_id, 3); assert.equal(pool[0].unidad, 'ml');
  // Ambos TV filtran la misma respuesta y limpian una carta completamente oculta.
  const carpeta = path.join(__dirname, '../static');
  const moderno = fs.readFileSync(path.join(carpeta, 'pantallas.html'), 'utf8');
  const simple = fs.readFileSync(path.join(carpeta, 'pantallas-simple.html'), 'utf8');
  const tv = { clonar: x => ({...x}) };
  vm.createContext(tv);
  const a = moderno.indexOf('function desdePV(');
  vm.runInContext(moderno.slice(a, moderno.indexOf('\n}',a)+2), tv);
  const dato = {local:'Prueba',categorias:[{nombre:'Café',productos:[
    {nombre:'Oculto',precio:1000,en_tv:false},{nombre:'Visible',precio:2000,en_tv:true}],
    destacado:{nombre:'Oculto destacado',precio:3000,en_tv:false}}]};
  const convertido = tv.desdePV(dato);
  assert.equal(convertido.categorias[0].items.length,1);
  assert.equal(convertido.categorias[0].destacado.n,'Visible');
  assert.equal(tv.desdePV({categorias:[]}).categorias.length,0);
  const b = simple.indexOf('function filtrarTv(');
  vm.runInContext(simple.slice(b,simple.indexOf('\n  }',b)+4),tv);
  const filtrado = tv.filtrarTv(JSON.parse(JSON.stringify(dato)));
  assert.equal(filtrado.categorias[0].productos.length,1);
  assert.equal(filtrado.categorias[0].destacado,undefined);
  assert.equal(tv.filtrarTv({categorias:[{productos:[{en_tv:false}]}]}).categorias.length,0);
  console.log('Ficha, códigos, peso, permisos y legado: OK');
})().catch(e => { console.error(e); process.exitCode = 1; });
