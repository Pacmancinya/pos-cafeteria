// La lógica de la pestaña Config que no necesita pantalla (apps/pos/static/config-logica.js).
// Se corre con:  node apps/pos/tests/config_logica.cjs   (pytest lo llama solo).
const assert = require("node:assert/strict");
const path = require("node:path");
const L = require(path.join(__dirname, "..", "static", "config-logica.js"));

// ------------------------------------------------ el buscador de ajustes, sin tildes ni mayúsculas
const ids = (q) => L.buscarAjustes(q).hits.map((h) => h[0]);
assert(ids("CODIGO").includes("b-codigo") && ids("código").includes("b-codigo"), "«codigo» encuentra «código» sin la tilde");
assert(ids("impresora").includes("i-prueba") && ids("IMPRESORA").includes("i-papel"));
assert(ids("propina").includes("c-propina"));
assert(ids("debito").includes("c-medios") && ids("DÉBITO").includes("c-medios"), "palabras clave sin tilde");
assert(ids("pin").includes("k-pinred") && ids("pin").includes("e-lista"));
assert(ids("pin red").includes("k-pinred") && !ids("pin red").includes("e-lista"), "todas las palabras tienen que calzar");
assert(ids("tv vertical").includes("p-tvs"));
assert(ids("categoría").includes("p-tvs") === true);
assert.deepEqual(ids("zzzz"), [], "sin resultados");
assert.deepEqual(ids("   "), [], "vacío no busca");
assert(ids("restaurar")[0] === "r-restaurar", "lo que calza en el título va primero");
assert(L.buscarAjustes("o").hits.length <= 8, "no más de 8 resultados");
// Cada resultado lleva su sección, y cada sección existe en el menú.
for (const [, sec] of L.INDICE) assert(L.SECCIONES.some((s) => s[0] === sec), sec);
assert.equal(L.SECCIONES.length, 7, "las siete secciones del boceto");
assert.deepEqual(L.SECCIONES.map((s) => s[1]), ["Mi local", "Equipo", "Cobro", "Impresora y balanza",
  "Pantallas del local", "Esta caja", "Respaldos y actualizaciones"]);

// ------------------------------------------------ resaltar lo buscado (con tildes en el texto)
assert.equal(L.resaltar("Imprimir prueba", ["impr"]), "<mark>Impr</mark>imir prueba");
assert.equal(L.resaltar("Impresión", ["impresion"]), "<mark>Impresión</mark>");
assert.equal(L.resaltar("A & <b>", []), "A &amp; &lt;b&gt;", "el texto se escapa");
assert.equal(L.resaltar("Nada", ["zz"]), "Nada");

// ------------------------------------------------ el ticket de ejemplo, 32 y 48 columnas
const local = { nombre: "Café del Barrio", rut: "76.123.456-0", direccion: "Av. Los Aromos 1450, local 3, Graneros",
  mensaje: "¡Gracias por venir! Te esperamos mañana con café fresco" };
for (const ancho of [32, 48]) {
  const t = L.ticketTxt(local, ancho).split("\n");
  assert(t.every((l) => l.length <= ancho), `ninguna línea pasa de ${ancho}`);
  assert(t.some((l) => l.includes("NO ES BOLETA")));
  assert.equal(t.filter((l) => l.trim() === "-".repeat(ancho)).length, 4);
  assert.equal(t.slice(-3 - (ancho === 32 ? 0 : -1)).join(" ").replace(/\s+/g, " ").includes("Gracias"), true);
}
const t58 = L.ticketTxt(local, 32).split("\n"), t80 = L.ticketTxt(local, 48).split("\n");
assert(t58.length > t80.length, "el rollo angosto parte el mensaje en más líneas");
assert.equal(L.ticketTxt({ nombre: "X" }, 32).split("\n").pop().trim(), "¡Gracias!", "sin mensaje, el de siempre");
assert(L.ticketTxt({ nombre: "X", mensaje: "a".repeat(80) }, 32).split("\n").every((l) => l.length <= 32), "una palabra larguísima se corta");

// ------------------------------------------------ el RUT
assert.equal(L.rutDV("76123456"), "0");
assert.equal(L.rutFormato("761234560"), "76.123.456-0");
assert.equal(L.rutFormato("76.123.456-0"), "76.123.456-0");
assert.equal(L.rutFormato("12345678-5"), "12.345.678-5");
assert.equal(L.rutFormato("76.123.456-1"), null, "dígito verificador malo");
assert.equal(L.rutFormato("abc"), null);
assert.equal(L.rutFormato(""), null);

// ------------------------------------------------ precio sugerido (la cuenta de siempre)
assert.equal(L.precioSugerido(1300, 50, 50), 2600);
assert.equal(L.precioSugerido(1300, 50, 100), 2600);
assert.equal(L.precioSugerido(1301, 50, 50), 2650, "hacia ARRIBA: el margen es un piso");
assert.equal(L.precioSugerido(1301, 50, 10), 2610);
assert.equal(L.precioSugerido(0, 50, 50), 0);
assert.equal(L.precioSugerido(1000, 200, 50), 20000, "el margen se topa en 95");
assert(L.ejemploMargen(50, 50).includes("$2.600"));

// ------------------------------------------------ el formato de la balanza
const digi = { modo: "ticket", prefijo: "25", codigo: [2, 6], valor: [6, 12], divisor_peso: 1000 };
assert.equal(L.dibujoFormatoBalanza(digi).split("\n")[1], "PPNNNN$$$$$$V");
assert(L.dibujoFormatoBalanza({ ...digi, codigo: [null, 6] }).startsWith("Falta o está mal"));
assert(L.dibujoFormatoBalanza({ ...digi, valor: [7, 3] }).includes("el valor"));
assert(L.dibujoFormatoBalanza({ ...digi, prefijo: "78" }).includes("prefijo"));
assert(L.dibujoFormatoBalanza({ ...digi, codigo: [2, 7] }).split("\n")[1].includes("!"));
assert(L.formatoBalanzaValido(digi));
assert(!L.formatoBalanzaValido({ ...digi, codigo: [2, 7] }), "partes superpuestas: no se guarda");
assert(!L.formatoBalanzaValido({ ...digi, prefijo: "" }));

// ------------------------------------------------ las direcciones de los televisores
const base = "http://192.168.1.20:8090";
const tv = (o) => ({ id: 3, modo: "turnar", simple: false, ...o });
assert.equal(L.urlTv(tv({ modo: "vitrina" }), base), base + "/pantallas?p=1&t=3", "?p=1 sigue siendo la vitrina");
assert.equal(L.urlTv(tv({ modo: "menu" }), base), base + "/pantallas?p=2&t=3", "?p=2 sigue siendo la carta");
assert.equal(L.urlTv(tv({}), base), base + "/pantallas?tv=1&t=3", "?tv=1 sigue siendo las dos turnándose");
assert.equal(L.urlTv(tv({ simple: true }), base + "/"), base + "/pantallas/simple?t=3", "la versión simple");
assert.equal(L.textoVisto(null).activo, false);
assert.equal(L.textoVisto(30).texto, "Conectado · visto hace un momento");
assert.equal(L.textoVisto(180).texto, "Conectado · visto hace 3 min");
assert(L.textoVisto(3600).texto.startsWith("Sin señal") && !L.textoVisto(3600).activo);

// ------------------------------------------------ la lista de respaldos y su buscador
const copia = (o) => ({ archivo: "pos-2026-09-27.db", tipo: "diario", fecha: "2026-09-27", hora: "02:00", ventas: 10, abre: true, ...o });
assert.equal(L.etiquetaRespaldo(copia()), "domingo 27 de septiembre · 02:00");
assert(L.etiquetaRespaldo(copia({ tipo: "antes", fecha: "2026-10-08", hora: "14:22", archivo: "antes-de-restaurar-2026-10-08_142233.db" }))
  .startsWith("Antes de restaurar · jueves 8 de octubre"));
for (const q of ["domingo", "DOMINGO", "27 de septiembre", "09-27", "2026-09-27", "27/9", "septiembre", "pos-2026", "27-9"]) {
  assert(L.respaldoCalza(copia(), q), q);
}
for (const q of ["lunes", "octubre", "09-28", "xyz"]) assert(!L.respaldoCalza(copia(), q), q);
assert(L.respaldoCalza(copia(), ""), "vacío calza todo");
assert(L.respaldoCalza(copia({ tipo: "antes" }), "antes de restaurar"));
assert.equal(L.fraseConfirmarRestaurar(2), "Entiendo que esas 2 ventas no van a estar en la caja.");
assert.equal(L.fraseConfirmarRestaurar(1), "Entiendo que esas 1 venta no van a estar en la caja.");
assert(L.fraseConfirmarRestaurar(1284).includes("1.284"));
assert(L.fraseConfirmarRestaurar(0).includes("como estaba"));

// ------------------------------------------------ impresoras
let r = L.resumenImpresoras({ disponible: true, impresoras: [{ nombre: "Caja <ñ>", disponible: true }, { nombre: "PDF", disponible: false }] }, "Caja <ñ>");
assert.equal(r.opciones[1].valor, "Caja <ñ>");
assert(r.opciones[2].deshabilitada && r.opciones[2].texto.includes("requiere diálogo"));
assert.equal(r.hayPapel, true);
assert(r.estado.startsWith("Lista actualizada"));
r = L.resumenImpresoras({ disponible: true, impresoras: [] }, "Caja ñ");
assert(r.opciones.some((o) => o.valor === "Caja ñ" && o.texto.includes("no disponible")), "se conserva la guardada");
assert(r.estado.includes("No hay impresoras"));
assert.equal(L.resumenImpresoras({ disponible: false, impresoras: [], detalle: "Requiere Windows" }, "").estado, "Requiere Windows");
assert(L.resumenImpresoras({ disponible: true, impresoras: [{ nombre: "PDF", disponible: false }] }, "").hayPapel === false);
assert(L.resumenImpresoras({ disponible: true, impresoras: [{ nombre: "A", disponible: false }] }, "A").estado.includes("no está disponible"));
assert.deepEqual(L.puertosUtiles([{ nombre: "COM3" }, { nombre: "FILE:" }, { nombre: "USB001" }, { nombre: "PORTPROMPT:" }]).map((p) => p.nombre), ["USB001", "COM3"]);
assert.equal(L.deducirTipo("", ""), "navegador");
assert.equal(L.deducirTipo("Caja", "USB001"), "termica");
assert.equal(L.deducirTipo("Brother HL", "LPT1"), "windows");
assert.equal(L.deducirTipo("POS-58", ""), "termica");

// ------------------------------------------------ los permisos de una persona
const catalogo = [["vender", "Vender"], ["anular", "Anular una venta del día"], ["anular_pasado", "Anular ventas de cajas ya cerradas"],
  ["turno_abrir", "Abrir la caja"], ["turno_cerrar", "Cerrar su caja"], ["turno_cerrar_ajeno", "Cerrar la caja de otro"],
  ["caja_retirar", "Sacar plata del cajón"], ["cobrar_varios", "Cobrar un monto a mano"], ["ver_dia", "Ver Ventas"],
  ["ver_reportes", "Ver reportes"], ["ver_informes", "Ver los informes"], ["editar_carta", "Editar la carta y los precios"],
  ["inventario", "Ver Inventario y mover mercadería"], ["inventario_ajustar", "Corregir el stock"],
  ["usuarios", "Crear y editar personas"], ["config", "Cambiar los ajustes"]].map(([clave, nombre]) => ({ clave, nombre }));
let g = L.permisosAgrupados(catalogo, "");
assert.equal(g.reduce((n, [, cs]) => n + cs.length, 0), 16, "no se pierde ningún permiso");
assert.deepEqual(g.find(([n]) => n === "Mirar")[1].map((p) => p.clave), ["ver_dia", "ver_reportes", "ver_informes"], "«Ver reportes» se da por persona");
assert.deepEqual(L.permisosAgrupados(catalogo, "REPORTES").flatMap(([, cs]) => cs.map((p) => p.clave)), ["ver_reportes"]);
assert.deepEqual(L.permisosAgrupados(catalogo, "cajon").flatMap(([, cs]) => cs.map((p) => p.clave)), ["caja_retirar"], "sin tildes");
assert.deepEqual(L.permisosAgrupados(catalogo, "zzz"), []);
g = L.permisosAgrupados(catalogo.concat([{ clave: "nuevo_permiso", nombre: "Algo nuevo" }]), "");
assert.equal(g[g.length - 1][0], "Otros", "un permiso que el servidor agregue no se esconde");
assert.deepEqual(L.SOLO_VENDER, ["vender", "turno_abrir", "turno_cerrar"]);

// ------------------------------------------------ porcentajes de los botones
assert.equal(L.porcentajeValido("15"), 15);
assert.equal(L.porcentajeValido("15 %"), 15);
assert.equal(L.porcentajeValido("0"), null);
assert.equal(L.porcentajeValido("101"), null);
assert.equal(L.porcentajeValido(""), null);
assert.deepEqual(L.alternarPorcentaje([10, 20], 15), [10, 15, 20]);
assert.deepEqual(L.alternarPorcentaje([10, 15, 20], 15), [10, 20]);
assert.deepEqual(L.alternarPorcentaje([1, 2, 3, 4, 5, 6], 7), [1, 2, 3, 4, 5, 6], "como máximo seis");
assert.equal(L.minutosTxt(1), "1 minuto");
assert.equal(L.minutosTxt(5), "5 minutos");
console.log("Config lógica: buscador sin tildes, ticket 32/48, RUT, balanza, televisores, respaldos y permisos OK");
