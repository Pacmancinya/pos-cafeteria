// La lógica de la pestaña Ventas que no necesita pantalla (apps/pos/static/ventas-logica.js).
// Se corre con:  node apps/pos/tests/ventas_logica.cjs   (pytest lo llama solo).
const assert = require("node:assert/strict");
const path = require("node:path");
const V = require(path.join(__dirname, "..", "static", "ventas-logica.js"));

// ---------------------------------------------------------------- buscar sin tildes ni mayúsculas
assert.equal(V.sinTildes("Café MÁS Ñandú"), "cafe mas nandu");
const venta = (o) => ({ numero: 4512, cobrado: 3400, medio_pago: "debito", medio: "Débito", anulada: false,
  pagos: [{ medio: "debito", monto: 3400 }], productos: [{ nombre: "Café Latte", cantidad: 2 }, { nombre: "Alfajor", cantidad: 1 }], ...o });
assert(V.ventaCalza(venta(), ""), "sin texto calzan todas");
assert(V.ventaCalza(venta(), "CAFE"), "producto, sin tildes ni mayúsculas");
assert(V.ventaCalza(venta(), "alfa"), "cualquier producto de la venta");
assert(V.ventaCalza(venta(), "4512") && V.ventaCalza(venta(), "n° 4512"), "número de venta");
assert(V.ventaCalza(venta(), "3.400") && V.ventaCalza(venta(), "$3400"), "monto, con o sin puntos");
assert(V.ventaCalza(venta(), "debito") && V.ventaCalza(venta(), "Débito"), "forma de pago");
assert(!V.ventaCalza(venta(), "brownie") && !V.ventaCalza(venta(), "9999"));
assert(V.ventaCalza(venta({ anulada: true }), "anul"), "las anuladas se buscan por 'anulada'");
assert(!V.ventaCalza(venta(), "anul"));
const mixta = venta({ medio_pago: "mixto", medio: "Pago mixto", pagos: [{ medio: "efectivo", monto: 1500 }, { medio: "debito", monto: 1900 }] });
assert(V.ventaCalza(mixta, "efectivo") && V.ventaCalza(mixta, "debito") && V.ventaCalza(mixta, "mixto"),
  "una venta mixta se encuentra por las dos formas de pago");

const turno = (o) => ({ id: 1, abrio: "Ana", abierto: false, abierto_at: "2026-10-01T09:00:00-03:00", diferencia: 0, ...o });
assert(V.turnoCalza(turno(), "ANA") && V.turnoCalza(turno(), "jue 1 oct") && V.turnoCalza(turno(), "1/10"));
assert(V.turnoCalza(turno(), "cuadra") && !V.turnoCalza(turno(), "falta"));
assert(V.turnoCalza(turno({ diferencia: -300 }), "falta") && V.turnoCalza(turno({ diferencia: 300 }), "sobro"));
assert(V.turnoCalza(turno({ abierto: true, diferencia: null }), "en curso"));
assert(!V.turnoCalza(turno(), "", true), "«Solo con diferencia» esconde los que cuadraron");
assert(V.turnoCalza(turno({ diferencia: -300 }), "", true));
assert(!V.turnoCalza(turno({ abierto: true, diferencia: null }), "", true), "uno en curso no tiene diferencia");
assert(!V.turnoCalza(turno(), "luis"));

const datos = {
  vendidos: [{ nombre: "Latte", categoria: "Café", cantidad: 5, total: 17000 }, { nombre: "Brownie", categoria: "Dulce", cantidad: 9, total: 22500 },
    { nombre: "Alfajor", categoria: "Dulce", cantidad: 9, total: 17100 }],
  sin_ventas: [{ nombre: "Té", categoria: "Café", ultima_venta: "2026-09-20" }, { nombre: "Agua", categoria: "Bebidas", ultima_venta: null },
    { nombre: "Jugo", categoria: "Bebidas", ultima_venta: "2026-10-01" }],
};
assert.deepEqual(V.listaProductos(datos, "cant", "").filas.map((p) => p.nombre), ["Alfajor", "Brownie", "Latte"], "por cantidad, el empate por nombre");
assert.deepEqual(V.listaProductos(datos, "plata", "").filas.map((p) => p.nombre), ["Brownie", "Alfajor", "Latte"]);
assert.deepEqual(V.listaProductos(datos, "sin", "").filas.map((p) => p.nombre), ["Agua", "Té", "Jugo"], "primero los que nunca se vendieron");
assert.deepEqual(V.listaProductos(datos, "cant", "DULCE").filas.map((p) => p.nombre), ["Alfajor", "Brownie"], "también por categoría");
assert.deepEqual(V.listaProductos(datos, "cant", "cafe").filas.map((p) => p.nombre), ["Latte"]);
assert.equal(V.listaProductos(datos, "cant", "zzz").todas, 3);

// ---------------------------------------------------------------- comparar con el período anterior
assert.deepEqual(V.delta(120, 100, true), { clase: "up", texto: "▲ +20%" });
assert.deepEqual(V.delta(80, 100, true), { clase: "down", texto: "▼ −20%" });
assert.deepEqual(V.delta(100, 100, true), { clase: "eq", texto: "= igual" });
assert.deepEqual(V.delta(100, 100, false), { clase: "na", texto: "sin comparar" }, "sin historia no se compara");
assert.deepEqual(V.delta(100, null, true), { clase: "na", texto: "sin comparar" });
assert.deepEqual(V.delta(100, 0, true), { clase: "na", texto: "sin comparar" }, "contra cero no hay porcentaje");
assert.deepEqual(V.delta(0, 0, true), { clase: "eq", texto: "= igual" });

// ---------------------------------------------------------------- fechas del local, leídas del texto
const iso = "2026-10-08T14:22:00-03:00";
assert.equal(V.hhmm(iso), "14:22");
assert.equal(V.fechaCorta(iso), "jue 8 oct");
assert.equal(V.fechaLarga(iso), "jueves 8 de octubre");
assert.equal(V.fechaCorta("2026-10-04"), "dom 4 oct");
assert.equal(V.diaMes("2026-10-08"), "8/10");
assert.equal(V.cuandoAbrio("2026-10-08T08:30:00-03:00", "2026-10-08"), "hoy 08:30");
assert.equal(V.cuandoAbrio("2026-10-05T08:30:00-03:00", "2026-10-08"), "lun 5 oct 08:30");
assert.equal(V.rangoTexto("2026-10-08", "2026-10-08"), "jueves 8 de octubre");
assert.equal(V.rangoTexto("2026-10-02", "2026-10-08"), "Del 2 al 8 de octubre");
assert.equal(V.rangoTexto("2026-09-20", "2026-10-08"), "Del 20 de sep al 8 de oct");
assert.equal(V.duracion(0), "0 min");
assert.equal(V.duracion(59), "59 min");
assert.equal(V.duracion(60), "1 h");
assert.equal(V.duracion(352), "5 h 52 min");
assert.equal(V.minutosEntre("2026-10-08T08:30:00-03:00", "2026-10-08T14:22:00-03:00", 0), 352);
assert.equal(V.minutosEntre("2026-10-08T08:30:00-03:00", null, Date.parse("2026-10-08T08:45:00-03:00")), 15);

// ---------------------------------------------------------------- el arqueo
assert.equal(V.claseDif(0), "ok"); assert.equal(V.claseDif(5), "mas"); assert.equal(V.claseDif(-5), "menos");
assert.equal(V.textoDif(0), "Cuadra exacto");
assert.equal(V.textoDif(1500), "Sobran $1.500");
assert.equal(V.textoDif(-300), "Faltan $300");
assert.equal(V.textoDifCorto(-300), "Falta $300");
assert.equal(V.conSigno(-300), "−$300");
assert.equal(V.conSigno(300), "+$300");

// ---------------------------------------------------------------- gráficos
assert.deepEqual(V.escalaBonita(0), { paso: 1, n: 1 });
{
  const e = V.escalaBonita(11800); // 11.800 / 4 = 2.950 → paso de 5.000
  assert.equal(e.paso, 5000); assert.equal(e.n, 3);
  assert(e.paso * e.n >= 11800, "el eje llega hasta la barra más alta");
  for (const max of [1, 37, 950, 1234, 56000, 987654, 4300000]) {
    const x = V.escalaBonita(max);
    assert(x.paso * x.n >= max && x.n <= 5, `eje para ${max}`);
  }
}
assert.equal(V.ejeY(0), "$0");
assert.equal(V.ejeY(5000), "$5 mil");
assert.equal(V.ejeY(2500), "$2,5 mil");
assert.equal(V.ejeY(1500000), "$1,5 M");
{
  const items = [{ etq: "1", total: 1000, fin: false }, { etq: "2", total: 4000, fin: false }, { etq: "3", total: 0, fin: true }];
  const g = V.geometriaBarras(items, 600, 230, null, true);
  assert.equal(g.sel, 1, "sin selección, la barra más alta");
  assert.equal(g.barras.length, 3);
  assert(g.barras[1].h > g.barras[0].h && g.barras[2].h === 0);
  assert(g.barras[2].fin && g.barras[1].sel && !g.barras[0].sel);
  assert(g.barras.every((b) => b.y + b.h <= g.mt + g.ph + 0.001), "las barras no pasan del piso");
  assert(g.promedio && g.promedio.y < g.mt + g.ph, "hay línea de promedio");
  assert.equal(V.geometriaBarras(items, 600, 230, 0, false).sel, 0, "la selección manda");
  assert.equal(V.geometriaBarras(items, 600, 230, 0, false).promedio, null);
  assert.equal(V.geometriaBarras(items, 100, 230, 9, false).W, 280, "ancho mínimo");
  assert.equal(V.geometriaBarras([], 600, 230, null, true).barras.length, 0, "sin datos no revienta");
  const muchas = Array.from({ length: 31 }, (_, i) => ({ etq: String(i + 1), total: 1000 * (i + 1), fin: false }));
  const gm = V.geometriaBarras(muchas, 500, 230, 30, false);
  assert(gm.barras.filter((b) => b.verEtq).length < 31, "con 31 días no se rotulan todos");
  assert(gm.barras[30].verEtq, "pero la seleccionada sí");
}
{
  const arcos = V.arcosDona([{ medio: "efectivo", total: 750 }, { medio: "debito", total: 250 }, { medio: "credito", total: 0 }], 46);
  assert.equal(arcos.length, 2, "un medio sin plata no lleva arco");
  const L = 2 * Math.PI * 46;
  assert(Math.abs(arcos[0].largo - L * 0.75) < 1e-9 && Math.abs(arcos[1].largo - L * 0.25) < 1e-9);
  assert(Math.abs(arcos[0].largo + arcos[0].resto - L) < 1e-9);
  assert(Math.abs(arcos[1].desde + arcos[0].largo) < 1e-9, "el segundo arco parte donde termina el primero");
  assert.deepEqual(V.arcosDona([], 46), []);
}
assert.equal(V.pct(1, 4), 25); assert.equal(V.pct(1, 0), 0);

// ---------------------------------------------------------------- el mapa de calor
{
  const celdas = Array.from({ length: 7 }, () => new Array(24).fill(0));
  celdas[5][9] = 8000; celdas[5][10] = 6000; celdas[5][17] = 7000; celdas[1][18] = 2000;
  const todos = new Array(24).fill(0);
  todos[9] = 1500; todos[10] = 1200; todos[17] = 1400; todos[18] = 300;
  const c = { hora_ini: 8, hora_fin: 20, celdas, todos, ultimas_4_semanas: false };
  assert.deepEqual(V.celdaMejor(c), { d: 5, h: 9, v: 8000 });
  assert.equal(V.fraseCalor(c), "Se vende más a las <b>9 h</b> y a las <b>17 h</b>. El día más fuerte es el <b>sábado</b>.",
    "la segunda hora es la mejor que no esté pegada a la primera");
  assert.equal(V.fraseCelda(c, { d: 5, h: 9 }), "Un sábado entre las <b>9</b> y las <b>10 h</b>: en promedio <b>$8.000</b> ese día.");
  assert.equal(V.fraseCelda(c, { d: 7, h: 9 }), "Todos los días entre las <b>9</b> y las <b>10 h</b>: en promedio <b>$1.500</b> por día.");
  assert.deepEqual(V.horasDelCalor({ hora_ini: 7, hora_fin: 9 }), [7, 8, 9]);
  const vacio = { hora_ini: 8, hora_fin: 20, celdas: Array.from({ length: 7 }, () => new Array(24).fill(0)), todos: new Array(24).fill(0) };
  assert.match(V.fraseCalor(vacio), /Todavía no hay ventas/);
  const unaHora = { ...vacio, todos: Object.assign(new Array(24).fill(0), { 12: 500 }) };
  unaHora.celdas[2][12] = 500;
  assert.equal(V.fraseCalor(unaHora), "Se vende más a las <b>12 h</b>. El día más fuerte es el <b>miércoles</b>.");
  assert.equal(V.intensidad(0, 100), 0); assert.equal(V.intensidad(100, 100), 100); assert.equal(V.intensidad(50, 100), 55);
  assert.equal(V.intensidad(5, 0), 0);
}

// ---------------------------------------------------------------- el teclado numérico de los diálogos
assert.equal(V.teclear("", "5"), "5");
assert.equal(V.teclear("5", "0"), "50");
assert.equal(V.teclear("1.500", "0"), "15.000");
assert.equal(V.teclear("15.000", "x"), "1.500");
assert.equal(V.teclear("15.000", "c"), "");
assert.equal(V.teclear("", "0"), "", "no se escribe un cero a la izquierda");
assert.equal(V.teclear("123456789", "1"), "123.456.789", "tope de 9 dígitos");
assert.equal(V.conPuntos(1234567), "1.234.567");
assert.equal(V.conPuntos(""), "");

console.log("Ventas (lógica) OK");
