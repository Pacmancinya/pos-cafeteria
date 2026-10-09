/* Requiere el Playwright del entorno de auditoría, nunca una dependencia de la caja.
   node tools/pantallas/auditar_inventario.cjs http://127.0.0.1:8794
   Solo contra una caja de PRUEBA: crea un producto y anota movimientos. */
const { chromium } = require('playwright');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const base = process.argv[2] || 'http://127.0.0.1:8794';
const carpeta = path.resolve('auditoria-pantallas/inventario'); fs.mkdirSync(carpeta, { recursive: true });
const medidas = [[1024,697],[1093,543],[1280,649],[1366,697],[1536,793],[800,529],[768,1024],[390,844]];
const resultados = [], errores = [];
async function medir(p, estado, w, h) {
  const r = await p.evaluate(() => {
    const d = document.querySelector('.capa.is-on .inv-dialogo'), pie = d?.querySelector('.dialogo__pie');
    const rect = (e) => e ? { x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,b:e.getBoundingClientRect().bottom,r:e.getBoundingClientRect().right } : null;
    return { ancho:innerWidth,alto:innerHeight,docW:document.documentElement.scrollWidth,
      dialogo:rect(d),pie:rect(pie),scrollInterior:!!d && d.querySelector('.inv-interior').scrollHeight > d.querySelector('.inv-interior').clientHeight };
  });
  const problemas = [];
  if(r.docW>r.ancho+1) problemas.push('desbordamiento horizontal');
  for(const [nombre,rect] of [['dialogo',r.dialogo],['pie',r.pie]]) if(rect && (rect.x<0||rect.y<0||rect.b>r.alto+1||rect.r>r.ancho+1)) problemas.push(nombre+' fuera del alto útil');
  resultados.push({estado,w,h,...r,problemas});
  await p.screenshot({path:path.join(carpeta,`${w}x${h}-${estado}.png`)});
}
(async () => {
  const nav = await chromium.launch({channel:'msedge',headless:true});
  try {
    for(const [w,h] of medidas) {
      const contexto = await nav.newContext({viewport:{width:w,height:h}}), p = await contexto.newPage();
      p.on('pageerror',e => errores.push(String(e)));
      await p.goto(base+'/#/inventario');
      await p.locator('#invNuevo').waitFor(); await medir(p,'lista',w,h);
      await p.locator('#invNuevo').click();
      assert.equal(await p.locator('#invEliminar').isVisible(),false);
      assert.equal(await p.locator('#invSaldo').isVisible(),false);
      await medir(p,'ficha',w,h);
      await p.locator('#fCuenta').check(); await medir(p,'ficha-stock',w,h);
      await p.locator('#invModo').selectOption('peso'); await medir(p,'ficha-peso',w,h);
      await p.locator('#capaProducto [data-cerrar-capa]').click();
      for(const tipo of ['entrada','conteo','merma']) {
        await p.locator(`[data-inv-operacion="${tipo}"]`).click();
        await p.locator('#invBuscarMovimiento').waitFor(); await medir(p,tipo,w,h);
        await p.locator('#capaBodega [data-cerrar-capa]').click();
      }
      await p.locator('#invCategorias').click(); await medir(p,'categorias',w,h);
      await contexto.close();
    }
    // Prueba de ida y vuelta, usando formularios reales y la API del demo.
    const p = await nav.newPage({viewport:{width:1093,height:543}});
    p.on('pageerror',e => errores.push(String(e)));
    await p.goto(base+'/#/inventario'); await p.locator('#invNuevo').click();
    const nombre = 'Producto visual '+Date.now();
    const baseCodigo = '199'+String(Date.now()).slice(-9);
    const suma = [...baseCodigo].reduce((s,n,i)=>s+Number(n)*(i%2?3:1),0);
    const codigo = baseCodigo+String((10-suma%10)%10);
    await p.locator('#fNombre').fill(nombre); await p.locator('#invCosto').fill('1200');
    await p.locator('#invGanancia').fill('50'); assert.equal(await p.locator('#fPrecio').inputValue(),'1800');
    await p.locator('#invSugerido').click(); assert.equal(await p.locator('#fPrecio').inputValue(),'2400');
    await p.locator('#fCuenta').check(); await p.locator('#invHay').fill('5'); await p.locator('#invMinimo').fill('6');
    await p.locator('#fCodigo').fill(codigo); await p.locator('#invOtroCodigo').click();
    await p.locator('#fTv').uncheck(); await p.locator('#fGuardar').click();
    await p.locator('#capaProducto').waitFor({state:'hidden'});
    await p.locator('#invBuscar').fill(codigo); await p.locator('#invBuscar').press('Enter');
    await p.locator('#fNombre').waitFor(); assert.equal(await p.locator('#fNombre').inputValue(),nombre);
    assert.equal(await p.locator('#invHay').inputValue(),'5');
    await p.locator('#capaProducto [data-cerrar-capa]').click();
    await p.locator('#invFilas tr').first().locator('td').nth(2).click();
    assert.equal(await p.locator('#fNombre').inputValue(),nombre);
    await p.locator('#capaProducto [data-cerrar-capa]').click();
    await p.locator('[data-inv-operacion="entrada"]').click();
    await p.locator('#invBuscarMovimiento').fill(codigo); await p.locator('#invBuscarMovimiento').press('Enter');
    await p.locator('#invCantidad').fill('3'); await p.locator('#invAgregarEntrada').click(); await p.locator('#invGuardarMovimiento').click();
    await p.locator('#capaBodega').waitFor({state:'hidden'});
    await p.locator('[data-inv-operacion="conteo"]').click(); await p.locator('#invBuscarMovimiento').fill(codigo); await p.locator('#invBuscarMovimiento').press('Enter');
    await p.locator('[data-inv-contado]:focus').fill('7');
    await p.locator('#invGuardarMovimiento').click(); await p.locator('#capaBodega').waitFor({state:'hidden'});
    await p.locator('[data-inv-operacion="merma"]').click(); await p.locator('#invBuscarMovimiento').fill(codigo); await p.locator('#invBuscarMovimiento').press('Enter');
    await p.locator('#invCantidad').fill('1'); await p.locator('#invMotivo').selectOption({label:'Roto'});
    await p.locator('#invGuardarMovimiento').click(); await p.locator('#capaBodega').waitFor({state:'hidden'});
    const dato = await p.evaluate(async nombre => (await (await fetch('/api/v1/inventario/productos')).json()).productos.find(x => x.nombre === nombre),nombre);
    assert.equal(dato.stock,6); assert.equal(dato.en_tv,false); assert.equal(dato.costo,1200);
    await p.locator('#invCategorias').click();
    for(let i=0;i<3;i++) {
      await p.locator('#invCatNueva').fill('Categoría visual '+i+' '+Date.now());
      await p.locator('#invCatCrear').click();
      await p.waitForFunction(()=>document.querySelector('#invCatNueva').value==='');
    }
    await p.locator('#capaBodega [data-cerrar-capa]').click();
    await p.locator('#invNuevo').click();
    await p.locator('#invCategoriaBuscar').fill('categoria visual');
    assert((await p.locator('#fCategoria option').count())>=3);
    await p.locator('#capaProducto [data-cerrar-capa]').click();
    await p.close();
  } finally { await nav.close(); }
  fs.writeFileSync(path.join(carpeta,'resultados.json'),JSON.stringify({resultados,errores},null,2));
  console.log(JSON.stringify({mediciones:resultados.length,problemas:resultados.filter(r=>r.problemas.length),errores}));
  assert.equal(errores.length,0); assert(!resultados.some(r=>r.problemas.length));
})().catch(e=>{console.error(e);process.exitCode=1;});
