/* ==========================================================
   Punto de venta — lógica de la caja
   Sin framework ni build, igual que el panel de Gesfact.
   El carrito vive acá, en el navegador: a la base llega recién
   cuando se cobró (ver docs/CONTRATO.md).
   ========================================================== */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const clp = (n) => "$" + (Number(n) || 0).toLocaleString("es-CL");
const soloNumeros = (t) => parseInt(String(t).replace(/\D/g, ""), 10) || 0;
const esc = (t) => String(t == null ? "" : t)
  .replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/* El mismo 19% que usa el servidor (core/config.py). Acá se usa para una sola
   cosa: cuando el dueño compra con factura, el precio de la factura viene SIN
   IVA, y sugerirle un precio sobre ese número le daría un margen que no existe
   —el 19% que falta se lo come el IVA al vender. Hay una prueba que compara
   este número con el del servidor. */
const IVA = 0.19;

let CATEGORIAS = [];
let catActiva = null;
// El carrito vive en el navegador, pero guardado: si al cajero se le cierra la
// pestaña con un pedido a medias, no tiene que preguntarle de nuevo al cliente.
let carrito = (() => {
  try { return JSON.parse(localStorage.getItem("pos.carrito") || "[]"); }
  catch (e) { return []; }
})();
const guardarCarrito = () => {
  try { localStorage.setItem("pos.carrito", JSON.stringify(carrito)); } catch (e) {}
};
let medioPago = "efectivo";
let ultimaVenta = null;
let NOMBRE_DEL_LOCAL = "la caja";
// Cada navegador recuerda su impresora de la caja. Se conserva la preferencia
// antigua al abrir por primera vez esta configuración.
function leerImpresion() {
  try {
    const d = JSON.parse(localStorage.getItem("pos.impresion") || "null");
    return {
      automatica: d ? d.automatica === true : localStorage.getItem("pos.imprimir") === "1",
      impresora: d && typeof d.impresora === "string" && d.impresora.length <= 256 ? d.impresora : "",
      papel: d && d.papel === 58 ? 58 : 80,
      puerto: d && typeof d.puerto === "string" ? d.puerto : "",
      // null significa que el dueño aún no eligió el tipo. Una elección
      // explícita, incluso navegador, siempre gana sobre la detección.
      tipo: d && ["termica", "windows", "navegador"].includes(d.tipo) ? d.tipo
        : d && d.tipo === undefined && d.impresora === "" ? "navegador" : null,
    };
  } catch (e) { return { automatica: false, impresora: "", papel: 80, puerto: "", tipo: null }; }
}
let IMPRESION = leerImpresion();
let imprimirSiempre = IMPRESION.automatica;
const impresionesPendientes = new Set();
let probandoImpresion = false;
let instalandoImpresora = false;
let impresorasWindows = [];
let puertosImpresion = [];

function tipoImpresion(nombre = IMPRESION.impresora) {
  if (IMPRESION.tipo) return IMPRESION.tipo;
  if (!nombre) return "navegador";
  const p = impresorasWindows.find((p) => p.nombre === nombre);
  return /sewoo|slk[- ]?ts|t[eé]rmica|thermal|receipt|tickets?|esc[ /-]?pos|\bpos\b|epson.*tm[- ]|usb\d+/i
    .test(`${nombre} ${p?.puerto || (nombre === IMPRESION.impresora ? IMPRESION.puerto : "") || ""}`)
    ? "termica" : "windows";
}

/* El comprobante se imprime desde un marco escondido, no desde una ventana
   aparte. Es obligatorio: dentro de la ventana de la aplicación (WebView2)
   window.open devuelve null y no se imprimía nada — probado. De paso el
   cajero nunca sale de la caja, que era la intención original.

   La página del comprobante se manda a imprimir sola al cargar, así que acá
   solo hay que ponerla y sacarla después. */
function imprimirEnNavegador(ruta) {
  const anterior = document.getElementById("marcoImpresion");
  if (anterior) anterior.remove();
  const marco = document.createElement("iframe");
  marco.id = "marcoImpresion";
  marco.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  marco.src = `${ruta}?papel=${IMPRESION.papel}`;
  document.body.appendChild(marco);
  // 60 s: lo que puede demorar alguien en decidir en el diálogo de impresión.
  setTimeout(() => marco.remove(), 60000);
}

// confirmarVenta sigue su curso sin esperar al papel. Ningún error de aquí
// puede convertirse en un error del cobro ni volver a mandar /ventas.
async function imprimir(ruta) {
  if (impresionesPendientes.has(ruta)) return;
  impresionesPendientes.add(ruta);
  try {
    const comprobante = /^\/comprobante\/(\d+)$/.exec(ruta);
    const tipo = tipoImpresion();
    if (tipo !== "navegador" && comprobante) {
      if (!IMPRESION.impresora) throw Error("Elige una impresora en Configurar.");
      const prefijo = tipo === "termica" ? "crudo/" : "";
      await api(`/impresion/${prefijo}comprobante/${comprobante[1]}`, { method: "POST",
        body: JSON.stringify({ impresora: IMPRESION.impresora, papel: IMPRESION.papel }),
        espera: 25000 });
    } else {
      imprimirEnNavegador(ruta);
    }
  } catch (e) {
    // Nunca probar otro camino: Windows puede haber aceptado el trabajo antes
    // de perderse la respuesta. El aviso distingue el papel de la venta.
    avisar("Impresión: " + e.message + " La venta sigue registrada. "
      + "Revisa la cola antes de volver a imprimir.", true);
  } finally {
    impresionesPendientes.delete(ruta);
  }
}

/* ---------------- utilidades ---------------- */
/* Ninguna lectura puede dejar la caja esperando para siempre.

   Así se quedaba "pegada": al rato sin uso la caja se bloquea sola, y para
   dibujar el candado le pedía cosas al servidor. Si una respuesta no llegaba,
   el candado nunca aparecía, la sesión ya estaba cerrada, y la caja quedaba a
   la vista sin dejar vender ni volver a entrar. Había que cerrar el programa.

   Las LECTURAS tienen plazo: pasado el plazo se dan por fallidas y quien las
   pidió decide qué hacer. Las ESCRITURAS (cobrar, cerrar la caja) NO: cortar a
   la mitad un cobro que el servidor sí guardó haría que el cajero lo cobre dos
   veces. Esas esperan como siempre, salvo que quien llama pida un plazo. */
const ESPERA_LECTURA = 15000;

async function api(ruta, opciones = {}) {
  const { espera, ...resto } = opciones;
  const metodo = (resto.method || "GET").toUpperCase();
  const plazo = espera !== undefined ? espera : (metodo === "GET" ? ESPERA_LECTURA : 0);
  const corte = plazo ? new AbortController() : null;
  const reloj = corte ? setTimeout(() => corte.abort(), plazo) : null;
  let r;
  try {
    r = await fetch("/api/v1" + ruta, {
      headers: { "Content-Type": "application/json" },
      ...resto,
      ...(corte ? { signal: corte.signal } : {}),
    });
  } catch (e) {
    const mensaje = e && e.name === "AbortError"
      ? "La caja no respondió a tiempo" : "No se pudo conectar con la caja";
    // El servidor no puede anotar lo que no le llegó: lo anota la pantalla.
    reportar("red", mensaje, metodo + " " + ruta);
    throw new Error(mensaje);
  } finally {
    clearTimeout(reloj);
  }
  if (!r.ok) {
    let detalle = "Error " + r.status;
    try { detalle = (await r.json()).detail || detalle; } catch (e) {}
    // Una sesión que el servidor ya no reconoce —se reinició, o se cerró por
    // otro lado— no puede seguir mostrando una caja que no deja hacer nada: se
    // vuelve al candado. El PIN malo también es 401, pero ése lo maneja el
    // mismo candado.
    if (r.status === 401 && ruta !== "/sesion/entrar") sesionPerdida();
    // Los 422 de validación llegan como una lista de objetos. Mostrar el JSON crudo
    // («[{"type":"value_error","loc":...}]») no le dice nada a quien está configurando.
    if (Array.isArray(detalle)) {
      detalle = detalle.map((d) => String((d && d.msg) || "")
        .replace(/^Value error, /, "")).filter(Boolean).join(" ") || "Hay un dato que no sirve";
    }
    throw new Error(typeof detalle === "string" ? detalle : JSON.stringify(detalle));
  }
  return r.status === 204 ? null : r.json();
}

/* Los errores de esta pantalla quedan anotados en la caja (desde la 2.19), en
   el mismo registro que el dueño baja con «Descargar diagnóstico». Si el
   problema es justo que la caja no contesta, se guardan y se mandan cuando
   vuelva: es cuando más importa que queden. */
const AVISOS_PENDIENTES = [];
let ultimoReporte = "";

function reportar(tipo, mensaje, donde = "", detalle = "") {
  const clave = tipo + "|" + mensaje + "|" + donde;
  if (clave === ultimoReporte) return;          // el mismo error en bucle va una vez
  ultimoReporte = clave;
  const evento = { tipo: String(tipo).slice(0, 40), mensaje: String(mensaje).slice(0, 500),
                   donde: String(donde).slice(0, 200), detalle: String(detalle).slice(0, 2000) };
  fetch("/api/v1/diagnostico/evento", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(evento) })
    .catch(() => { if (AVISOS_PENDIENTES.length < 20) AVISOS_PENDIENTES.push(evento); });
}

function enviarPendientes() {
  while (AVISOS_PENDIENTES.length) {
    const evento = AVISOS_PENDIENTES.shift();
    fetch("/api/v1/diagnostico/evento", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(evento) }).catch(() => {});
  }
}

window.addEventListener("error", (e) => reportar("error", e.message || "error",
  `${e.filename || ""}:${e.lineno || ""}`, (e.error && e.error.stack) || ""));
window.addEventListener("unhandledrejection", (e) => reportar("promesa",
  (e.reason && e.reason.message) || String(e.reason), "", (e.reason && e.reason.stack) || ""));

let tAviso;
function avisar(texto, malo = false) {
  const a = $("#aviso");
  a.textContent = texto;
  a.classList.toggle("malo", malo);
  a.classList.add("is-on");
  clearTimeout(tAviso);
  tAviso = setTimeout(() => a.classList.remove("is-on"), 3200);
}

/* ---------------- carta y grilla ----------------
   Paleta cálida y apagada: le da estructura visual a la carta sin que la caja
   parezca un juego. Cada categoría toma un color y lo arrastra a sus azulejos. */
const COLORES = ["#C9552B", "#8A5A34", "#4E7C5B", "#B5892E", "#8C4A6B", "#3E6E8E", "#A0522D"];
const colorDeCat = (id) => {
  const i = CATEGORIAS.findIndex((c) => c.id === id);
  return COLORES[(i < 0 ? 0 : i) % COLORES.length];
};

let busqueda = "";

/* La categoría se recuerda en este equipo: si se corta la luz o se cierra sin
   querer, el cajero vuelve donde estaba. Con ?cat=3 se puede abrir fija en una,
   que sirve si algún día ponen un tablet solo para la vitrina de pasteles. */
function categoriaGuardada() {
  const url = +new URLSearchParams(location.search).get("cat");
  if (url) return url;
  try { return +localStorage.getItem("pos.categoria") || null; } catch (e) { return null; }
}

async function cargarCarta() {
  CATEGORIAS = await api("/categorias");
  const conProductos = CATEGORIAS.filter((c) => c.activa && c.productos.some((p) => p.activo));
  if (!catActiva) catActiva = categoriaGuardada();
  if (!catActiva || !conProductos.find((c) => c.id === catActiva)) {
    catActiva = conProductos.length ? conProductos[0].id : null;
  }
  $("#rail").innerHTML = conProductos.map((c) => {
    const n = c.productos.filter((p) => p.activo).length;
    return `<button class="rail__cat${c.id === catActiva && !busqueda ? " is-on" : ""}"
              data-cat="${c.id}" style="--c:${colorDeCat(c.id)}">
              <span class="rail__punto"></span>${esc(c.nombre)}<span class="rail__n">${n}</span>
            </button>`;
  }).join("");
  pintarGrilla();
  pintarEditorCarta();
  limpiarCarritoDeBorrados();
}

/* Un producto borrado no puede quedar en un pedido a medio armar: al cobrar, el
   servidor daría 404 y se caería la venta ENTERA, no la línea, con el cliente
   esperando. El carrito vive en el navegador y puede tener adentro algo que el
   dueño borró desde otra pantalla, así que se limpia cada vez que llega la carta. */
function limpiarCarritoDeBorrados() {
  if (!carrito.length) return;
  const vivos = new Set();
  CATEGORIAS.forEach((c) => c.productos.forEach((p) => vivos.add(p.id)));
  const antes = carrito.length;
  const sacados = carrito.filter((l) => !l.manual && !l.balanza && !vivos.has(l.id)).map((l) => l.nombre);
  if (!sacados.length) return;
  carrito = carrito.filter((l) => l.manual || l.balanza || vivos.has(l.id));
  pintarCarrito();
  if (antes !== carrito.length) {
    avisar(`Saqué del pedido ${sacados.length === 1 ? "un producto que ya no existe"
      : "productos que ya no existen"}: ${sacados.join(", ")}`, true);
  }
}

/* Un azulejo: el dibujo manda, el precio se lee de reojo. */
function azulejo(p, catId, conCategoria = false) {
  const color = p.color || colorDeCat(catId);
  const cat = CATEGORIAS.find((c) => c.id === catId);
  return `
    <button class="prod" data-prod="${p.id}" style="--c:${colorDeCat(catId)}">
      ${p.etiqueta ? `<span class="prod__tag">${esc(p.etiqueta)}</span>` : ""}
      <span class="prod__art">${dibujo({ k: p.dibujo || "mug", col: p.color || undefined })}</span>
      <span class="prod__pie">
        ${conCategoria && cat ? `<span class="prod__cat">${esc(cat.nombre)}</span>` : ""}
        <span class="prod__nombre">${esc(p.nombre)}</span>
        <span class="prod__precio">${!p.precio && p.precio_kilo > 0 ? `${clp(p.precio_kilo)}/kg` : clp(p.precio)}</span>
      </span>
    </button>`;
}

/* Buscar ignora tildes y mayúsculas: nadie escribe "Frappé" con acento a las 9 AM. */
const sinTildes = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function pintarGrilla() {
  const grilla = $("#grilla");

  if (busqueda) {
    const q = sinTildes(busqueda);
    const hallados = [];
    CATEGORIAS.forEach((c) => c.productos.forEach((p) => {
      if (!p.activo) return;
      if (sinTildes(p.nombre).includes(q) || sinTildes(p.descripcion).includes(q)) {
        hallados.push([p, c.id]);
      }
    }));
    grilla.innerHTML = hallados.length
      ? hallados.map(([p, cid]) => azulejo(p, cid, true)).join("")
      : `<p class="sin-resultados">No hay ningún producto que se llame así.<br>
         Revisa cómo está escrito, o agrégalo en la pestaña <b>Carta</b>.</p>`;
    return;
  }

  const c = CATEGORIAS.find((x) => x.id === catActiva);
  const prods = c ? c.productos.filter((p) => p.activo) : [];
  grilla.innerHTML = prods.length
    ? prods.map((p) => azulejo(p, c.id)).join("")
    : `<p class="sin-resultados">Esta categoría todavía no tiene productos a la venta.</p>`;
}

function buscar(texto) {
  busqueda = texto.trim();
  $("#limpiarBuscar").hidden = !busqueda;
  document.querySelectorAll(".rail__cat").forEach((b) =>
    b.classList.toggle("is-on", !busqueda && +b.dataset.cat === catActiva));
  pintarGrilla();
}

/* ---------------- carrito ---------------- */
function dialogoVarios() {
  if (!puedo("cobrar_varios")) return;
  $("#dialogoCodigo").innerHTML = `
    <h2>Productos varios</h2>
    <label class="campo">Monto por unidad (obligatorio)
      <input id="variosMonto" type="text" inputmode="numeric" data-teclado="monto"
             placeholder="Ej. 1500" autocomplete="off" required></label>
    <label class="campo">Descripción (opcional)
      <input id="variosNombre" type="text" maxlength="60" placeholder="Varios"></label>
    <div class="dialogo__pie">
      <button type="button" class="btn" data-cerrar-capa>Cancelar</button>
      <button type="button" class="btn btn--cobrar" id="agregarVarios">Agregar al pedido</button>
    </div>`;
  $("#capaCodigo").classList.add("is-on");
  $("#variosMonto").focus();
}

function agregarVarios() {
  if (!puedo("cobrar_varios")) return avisar("No tienes permiso para cobrar productos varios.", true);
  const texto = $("#variosMonto").value.trim();
  const precio = Number(texto.replace(/\./g, ""));
  if (!/^(\d+|\d{1,3}(\.\d{3})+)$/.test(texto)
      || !Number.isSafeInteger(precio) || precio <= 0 || precio > 99000000) {
    return avisar("Escribe un monto entre $1 y $99.000.000, sin decimales.", true);
  }
  const nombre = $("#variosNombre").value.trim() || "Varios";
  if (nombre.length > 60) return avisar("La descripción puede tener hasta 60 caracteres.", true);
  // IDs locales negativos: no se confunden con los productos ni viajan al servidor.
  const id = carrito.reduce((menor, l) => Math.min(menor, l.id), 0) - 1;
  carrito.push({ id, manual: true, nombre, precio, cantidad: 1 });
  pintarCarrito();
  $("#capaCodigo").classList.remove("is-on");
}

function lineasParaVenta() {
  // El monto de la etiqueta se muestra acá, pero lo calcula de nuevo el servidor.
  return carrito.map((l) => l.balanza
    // precio_visto no fija el precio: si el servidor calcula otro, rechaza la venta
    // en vez de registrar un monto distinto del que se cobró en la máquina.
    ? { codigo_balanza: l.codigo, cantidad: l.cantidad, precio_visto: l.precio }
    : l.manual
    ? { nombre: l.nombre, precio: l.precio, cantidad: l.cantidad }
    : { producto_id: l.id, cantidad: l.cantidad });
}

/* ---------------- agregar al pedido ----------------
   Con TOPE en lo que queda. Antes se podía poner 12 de algo que tenía 3, y el
   inventario quedaba en −9 sin que nadie lo notara hasta el conteo.

   El tope es DURO: no se vende lo que no hay. Si el saldo no alcanza, el
   producto no entra al pedido y se dice cuántos quedan y qué hacer —anotar la
   mercadería en Bodega—. Antes era un aviso que se iba solo en tres segundos y
   el toque siguiente pasaba igual: así se vendieron 27 de algo que estaba en
   cero. Ahora el muro no se cruza desde la caja; para vender más hay que anotar
   que llegó. El servidor lo rechaza igual, porque hay tablets y dos pestañas.

   Solo topea lo que se vende TAL CUAL. Un capuchino no tiene "cuántos quedan":
   tiene leche y café, y ése se descuenta, no se topea (`stock` viene nulo). */
const olvidarAvisos = () => {};

function agregar(id) {
  const cat = CATEGORIAS.find((c) => c.productos.some((p) => p.id === id));
  const p = cat && cat.productos.find((x) => x.id === id);
  if (!p) return;
  sumarAlPedido(p);
}

function sumarAlPedido(p) {
  if (p.balanza) return agregarBalanza(p);
  const deLaCarta = productoDeLaCarta(p.id) || p;
  if (!deLaCarta.precio && deLaCarta.precio_kilo > 0) {
    return avisar(`${deLaCarta.nombre} se vende por peso: escanea la etiqueta de la balanza.`, true);
  }
  const ya = carrito.find((l) => l.id === p.id);
  const pide = (ya ? ya.cantidad : 0) + 1;

  // El saldo lo manda la carta (p.stock), que se refresca después de cada venta.
  // `null` = no lleva cuenta como tal cual (o es de receta): no se topea.
  const tope = productoDeLaCarta(p.id);
  const stock = tope ? tope.stock : p.stock;
  if (usarInventario() && stock != null && pide > stock) {
    avisar(stock > 0
      ? `Solo quedan ${stock} de ${p.nombre}. Si llegó más, anótalo en Bodega.`
      : `${p.nombre} está en cero. Anota la mercadería en Bodega para venderlo.`, true);
    return;
  }

  if (ya) ya.cantidad += 1;
  else carrito.push({ id: p.id, nombre: p.nombre, precio: p.precio,
                      cantidad: 1, stock: stock });
  pintarCarrito();
}



function cambiarCantidad(id, delta) {
  const l = carrito.find((x) => x.id === id);
  if (!l) return;

  // El + del pedido tiene que respetar el mismo tope que el azulejo. No lo
  // hacía: sumaba directo. Así se llegaba a 30 de algo que tenía 0, tocando +
  // treinta veces sin que nada dijera nada — el aviso solo salía al tocar el
  // producto en la grilla.
  if (delta > 0 && l.balanza && !l.repetible) {
    return avisar("Un ticket de la balanza se cobra una sola vez", true);
  }
  if (delta > 0 && !l.manual && !l.balanza) {
    const p = productoDeLaCarta(id) || l;
    return sumarAlPedido(p);
  }

  if ((l.manual || l.balanza) && l.cantidad + delta > 999) return avisar("El máximo es 999 unidades por línea.", true);
  l.cantidad += delta;
  if (l.cantidad <= 0) carrito = carrito.filter((x) => x.id !== id);
  pintarCarrito();
}

function quitarLineaDelPedido(id) {
  carrito = carrito.filter((l) => l.id !== id);
  pintarCarrito();
}

/* El producto como está en la carta, con su saldo al día. Lo del carrito trae
   una copia del saldo de cuando se agregó. */
function productoDeLaCarta(id) {
  for (const c of CATEGORIAS) {
    const p = c.productos.find((x) => x.id === id);
    if (p) return p;
  }
  return null;
}

const totalCarrito = () => carrito.reduce((s, l) => s + l.precio * l.cantidad, 0);

/* ---------------- el lector de códigos ----------------
   escaner.js detecta la ráfaga de teclas y llama acá con el número. Todo lo de
   arriba —que no cobre la venta, que no intente un PIN— ya pasó allá; acá solo
   queda decidir qué hacer con el código.

   La regla de oro: escanear NUNCA puede interrumpir una venta. Si el código no
   se conoce, se ofrece guardarlo, pero el pedido que estaba armado se queda
   donde está. */
async function alEscanear(codigo) {
  // El lector restaura el campo antes de avisarnos: se repone para probarlo,
  // sin que una etiqueta de prueba termine sumada al pedido.
  const prueba = $("#ajBalanzaPrueba");
  const cuerpo = $("#ajBalanzaCuerpo");
  const probando = prueba && puedo("config") && (document.activeElement === prueba
    // Con el bloque de la balanza a la vista en Ayuda, el lector es para probar
    // aunque el foco haya quedado en un botón: si no, la etiqueta de prueba entraba
    // al pedido y se cobraba con el cliente siguiente.
    || ($(".vista.is-on")?.dataset.vista === "guias" && cuerpo && !cuerpo.hidden));
  if (probando) {
    prueba.value = codigo;
    return probarEtiquetaBalanza();
  }
  if ($(".vista.is-on")?.dataset.vista === "inventario" && usarInventario()) {
    $("#buscarBodega").value = codigo;
    pintarBodega();
    return;
  }
  // Con un diálogo abierto que no sea el de la carta, el escaneo no es para
  // vender: puede ser el dueño pegándole un código a un producto.
  const ficha = $("#capaProducto.is-on") && $("#fCodigo");
  if (ficha) return ponerCodigoEnFicha(codigo);

  if (!puedo("vender")) return;

  let r;
  try { r = await api("/codigos/" + encodeURIComponent(codigo)); }
  catch (e) { return avisar(e.message, true); }

  if (r.balanza) return agregarBalanza(r.balanza);
  if (r.de_balanza) return avisar(r.problema || "No se puede cobrar esa etiqueta", true);

  if (r.encontrado) {
    // El `cuantos` es lo que hace que el pack de 6 descuente seis: el código
    // del pack entrega seis unidades del mismo producto.
    for (let k = 0; k < (r.cuantos || 1); k++) agregarPorId(r.producto);
    avisar(`${r.producto.nombre}${r.cuantos > 1 ? ` × ${r.cuantos}` : ""}`);
    return;
  }

  if (r.problema && !r.se_puede_guardar) return avisar(r.problema, true);
  if (!puedo("editar_carta")) {
    return avisar("Ese código no está en la carta. Lo tiene que agregar el dueño.", true);
  }
  dialogoProductoNuevoPorCodigo(r.codigo);
}

function agregarBalanza(b) {
  const ya = carrito.find((l) => l.balanza && l.codigo === b.codigo);
  if (ya) {
    if (!ya.repetible) return avisar("Ese ticket ya está en el pedido", true);
    if (ya.precio !== b.precio) {
      // Cambió el precio por kilo o el formato desde que se escaneó: la línea toma
      // lo que vale ahora, que es lo que el servidor va a cobrar.
      Object.assign(ya, { nombre: b.nombre, detalle: b.detalle, precio: b.precio, modo: b.modo });
      pintarCarrito();
      return avisar(`${b.nombre} cambió de precio: ahora ${clp(b.precio)}`, true);
    }
    // Dos trozos pesados al gramo casi nunca dan el mismo código: si se repite, lo
    // normal es que el lector leyó dos veces la misma etiqueta. Sumarlo solo cobraba
    // dos veces el mismo jamón. Para dos paquetes iguales está el +.
    return avisar("Esa etiqueta ya está en el pedido. Si son dos iguales, usa el +.", true);
  } else {
    // Incluso con producto_id, la etiqueta tiene identidad propia y no usa
    // el stock por unidad de la carta. El id negativo sobrevive a la recarga.
    const id = carrito.reduce((menor, l) => Math.min(menor, l.id), 0) - 1;
    carrito.push({ id, balanza: true, codigo: b.codigo, modo: b.modo,
      nombre: b.nombre, detalle: b.detalle, precio: b.precio,
      repetible: b.repetible, cantidad: 1 });
  }
  pintarCarrito();
  avisar(`${b.nombre} · ${b.detalle.split(" a $")[0]}`);
}

/* El código no está en la carta: se guarda AHORA, sin salir de la venta.

   Esta pantalla es la respuesta de verdad a «tráete la base de datos de SKU».
   Esa base no existe para Chile —GS1 vende códigos, no catálogos, y no hay
   descarga— así que el catálogo se arma solo: cada producto se escribe UNA vez,
   la primera vez que pasa por la caja, y queda para siempre.

   El nombre se pide a Open Food Facts, que es libre y tiene 6.680 productos
   chilenos. Para un almacén —leche, bebidas, abarrotes de marca— acierta harto.
   Para una botillería casi nunca: es una base nutricional y no tiene el alcohol
   chileno. Por eso el campo llega escrito PERO editable, y si no llegó nada, se
   escribe a mano y ya está — que es lo que se haría igual.

   El precio nunca viene de ninguna parte: ese es del local. */
async function dialogoProductoNuevoPorCodigo(codigo, categoriaId) {
  const cats = CATEGORIAS.filter((c) => c.activa);
  const cual = cats.find((c) => c.id === (categoriaId || catActiva)) || cats[0];

  $("#dialogoCodigo").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Producto nuevo</h2>
    ${codigo ? `<div class="codigo-leido">${esc(codigo)}</div>
    <p class="ayuda" id="cdDe">Buscando cómo se llama…</p>` : ""}
    <label class="campo"><span>¿Qué es?</span>
      <input id="cdNombre" type="text" placeholder="Escríbelo" autocomplete="off"></label>
    <div>
      <label class="campo"><span>¿A cuánto lo vendes?</span>
        <input id="cdPrecio" type="text" inputmode="numeric" placeholder="0"></label>
    </div>
    <label class="campo"><span>¿Dónde va?</span>
      <select id="cdCat">${cats.map((c) =>
        `<option value="${c.id}"${cual && c.id === cual.id ? " selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>
    ${usarInventario() ? `<label class="marca"><input id="cdCuenta" type="checkbox">
      Llevar la cuenta de este</label>` : ""}
    <p class="ayuda" style="margin-bottom:0">${codigo
      ? "Queda guardado con su código: la próxima vez que lo pases por el lector, entra solo al pedido."
      : usarInventario()
        ? "Si llevas la cuenta, anota cuántos hay en Bodega. Todo se cuenta por unidades."
        : "Queda en la carta, listo para vender."}</p>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" data-guardar-codigo="${esc(codigo || "")}"
              style="width:auto">${codigo ? "Guardar y cobrar" : "Guardar"}</button>
    </div>`;
  $("#capaCodigo").classList.add("is-on");
  setTimeout(() => $("#cdNombre").focus(), 60);
  if (!codigo) return;                    // sin código no hay a quién preguntarle el nombre

  // Preguntar el nombre va DESPUÉS de dibujar: que la pantalla esté lista
  // aunque no haya internet. Nunca se espera por esto para poder escribir.
  try {
    const r = await api(`/codigos/${encodeURIComponent(codigo)}/sugerir`);
    const campo = $("#cdNombre");
    if (!campo) return;                       // cerraron el diálogo mientras tanto
    if (r.nombre && !campo.value) {
      campo.value = r.nombre;
      $("#cdDe").innerHTML = `Lo encontré en <b>${esc(r.de_donde)}</b>. `
        + "Corrígelo si no es así: manda lo que escribas tú.";
    } else {
      $("#cdDe").textContent = "No está en ninguna base pública, así que escríbelo tú. "
        + "Se guarda con su código y no lo vuelves a escribir nunca.";
    }
  } catch (e) {
    const d = $("#cdDe");
    if (d) d.textContent = "Escribe cómo se llama.";
  }
}

async function guardarProductoDelCodigo(codigo) {
  const nombre = ($("#cdNombre").value || "").trim();
  const precio = soloNumeros($("#cdPrecio").value);
  if (!nombre) return avisar("Escribe qué es", true);
  if (!precio) return avisar("Ponle precio", true);

  const inventario = { llevar_cuenta: usarInventario() && !!$("#cdCuenta")?.checked };
  try {
    const p = await api("/productos", { method: "POST", body: JSON.stringify({
      categoria_id: +$("#cdCat").value,
      nombre, precio, codigo: codigo || "",
      ...inventario,
    }) });
    $("#capaCodigo").classList.remove("is-on");
    await cargarCarta();
    if (codigo) {
      agregarPorId(p);
      avisar(`${nombre} queda guardado. Ya está en el pedido.`);
    } else {
      avisar(`${nombre} queda guardado${inventario.llevar_cuenta ? ". Anota cuántos hay en Bodega." : ", listo para vender."}`);
    }
  } catch (e) { avisar(e.message, true); }
}

/* Escanear con la ficha de un producto abierta: el código se le pega a ESE
   producto. Es como se le agrega el código del pack de 6 a algo que ya existe. */
let FICHA_ABIERTA = null;

async function pintarCodigos(productoId) {
  FICHA_ABIERTA = productoId;
  const caja = $("#fCodigos");
  if (!caja) return;
  let lista = [];
  if (productoId == null) {
    // Producto nuevo: todavía no hay a quién preguntarle, así que se muestran los que
    // se juntaron en esta ficha.
    lista = CODIGOS_NUEVOS.map((c) => ({ codigo: c, cuantos: 1 }));
  } else {
    try { lista = await api(`/productos/${productoId}/codigos`); } catch (e) { }
  }
  caja.innerHTML = lista.length
    ? lista.map((c) => `<div class="codigo-fila">
        <code>${esc(c.codigo)}</code>
        ${c.cuantos > 1 ? `<span class="codigo-cuantos">× ${c.cuantos}</span>` : ""}
        <button class="btn btn--chico btn--fantasma" data-sacar-codigo="${esc(c.codigo)}">Sacar</button>
      </div>`).join("")
    : `<p class="ayuda" style="margin:0 0 8px;font-size:13px">Todavía no tiene ninguno.</p>`;
}

async function pegarCodigo(productoId) {
  const campo = $("#fCodigo");
  const codigo = (campo.value || "").trim();
  if (!codigo) return avisar("Pasa el producto por el lector, o escribe el número", true);
  if (productoId == null || productoId === "") {
    // El producto todavía no existe: el código se anota y se adjunta al guardarlo.
    if (!CODIGOS_NUEVOS.includes(codigo)) CODIGOS_NUEVOS.push(codigo);
    campo.value = "";
    await pintarCodigos(null);
    return avisar("Anotado. Queda puesto cuando guardes el producto.");
  }
  try {
    await api(`/productos/${productoId}/codigos`, { method: "POST",
      body: JSON.stringify({ codigo, cuantos: 1 }) });
    campo.value = "";
    await pintarCodigos(productoId);
    avisar("Código guardado");
  } catch (e) { avisar(e.message, true); }
}

async function ponerCodigoEnFicha(codigo) {
  const campo = $("#fCodigo");
  if (!campo) return;
  campo.value = codigo;
  campo.dispatchEvent(new Event("input", { bubbles: true }));
  avisar("Código leído. Se guarda al apretar Guardar.");
}

/* Agrega al pedido algo que vino del escáner, aunque la grilla no lo tenga
   cargado todavía: el producto puede ser de una categoría que no está abierta. */
function agregarPorId(prod) {
  // Se busca en la carta para saber cuántos quedan: lo que llega del escáner
  // trae nombre y precio, no el saldo.
  let p = prod;
  for (const c of CATEGORIAS) {
    const hallado = c.productos.find((x) => x.id === prod.id);
    if (hallado) { p = hallado; break; }
  }
  sumarAlPedido(p);
}

function pintarCarrito() {
  const cont = $("#lineas");
  if (!carrito.length) {
    cont.innerHTML = `<p class="vacio">Toca un producto para empezar</p>`;
  } else {
    cont.innerHTML = carrito.map((l) => `
      <div class="linea">
        <div class="linea__txt">
          <b>${esc(l.nombre)}</b>
          <small>${l.balanza ? esc(l.detalle) : `${l.manual ? "Productos varios · Monto a mano · " : ""}${clp(l.precio)} c/u`}</small>
        </div>
        <div class="cant">
          <button data-menos="${l.id}">−</button>
          <span>${l.cantidad}</span>
          <button data-mas="${l.id}">+</button>
        </div>
        <div class="linea__sub">${clp(l.precio * l.cantidad)}</div>
        <button type="button" class="linea__quitar" data-quitar-linea="${l.id}"
                aria-label="Quitar ${esc(l.nombre)} del pedido" title="Quitar toda la línea">✕</button>
      </div>`).join("");
  }
  $("#total").textContent = clp(totalCarrito());
  $("#btnCobrar").disabled = carrito.length === 0;
  guardarCarrito();
}

/* ---------------- cobro ---------------- */
/* Pago mixto: cuánto se puso en cada medio. Vacío = pago de un solo medio. */
let mixto = false;
let mixtoMontos = {};

function abrirCobro() {
  if (!carrito.length) return;
  medioPago = "efectivo";
  mixto = false;
  mixtoMontos = {};
  $("#pagoMixto").checked = false;
  $("#mixtoGrid").hidden = true;
  $$("#medios .medio").forEach((b) => b.classList.toggle("is-on", b.dataset.medio === "efectivo"));
  $("#bloqueEfectivo").style.display = "";
  $("#cobroTotal").textContent = clp(totalCarrito());
  $("#pagaCon").value = "";
  $("#propina").value = "";
  $("#descuento").value = "";
  $("#vuelto").classList.remove("is-on");
  pintarRapidos();
  $("#capaCobro").classList.add("is-on");
  setTimeout(() => $("#pagaCon").focus(), 50);
}

/* ---- pago mixto ----
   Se reparte lo cobrado (total menos descuento) entre los medios. La propina no
   se reparte —es una combinación rara que no vale la pena— así que en mixto no
   hay propina. El botón de cobrar espera a que las partes sumen justo. */
const NOMBRE_MEDIO_LARGO = { efectivo: "Efectivo", debito: "Débito",
                             credito: "Crédito", transferencia: "Transferencia" };

function cambiarAMixto(activar) {
  mixto = activar;
  $("#mixtoGrid").hidden = !activar;
  // En mixto no aplican: el medio único, el vuelto y la propina.
  $("#bloqueEfectivo").style.display = activar ? "none" : "";
  $("#propina").disabled = activar;
  $$("#medios .medio").forEach((b) => { b.disabled = activar; });
  if (activar) { mixtoMontos = {}; pintarMixto(); }
  else { actualizarCobro(); }
}

function pintarMixto() {
  const caja = $("#mixtoGrid");
  caja.innerHTML = `
    <div class="mixto">
      ${Object.keys(NOMBRE_MEDIO_LARGO).map((m) => `
        <label class="mixto__fila">
          <span>${NOMBRE_MEDIO_LARGO[m]}</span>
          <input type="text" inputmode="numeric" data-mixto="${m}"
                 value="${mixtoMontos[m] || ""}" placeholder="0" autocomplete="off">
        </label>`).join("")}
      <div class="mixto__resto" id="mixtoResto"></div>
    </div>`;
  pintarMixtoResto();
}

const sumaMixto = () =>
  Object.values(mixtoMontos).reduce((s, v) => s + (v || 0), 0);

function pintarMixtoResto() {
  const objetivo = Math.max(0, totalCarrito() - soloNumeros($("#descuento").value));
  const puesto = sumaMixto();
  const falta = objetivo - puesto;
  const caja = $("#mixtoResto");
  if (!caja) return;
  if (falta === 0) {
    caja.className = "mixto__resto es-ok";
    caja.innerHTML = `Listo: las partes suman <b>${clp(objetivo)}</b> ✓`;
  } else if (falta > 0) {
    caja.className = "mixto__resto";
    caja.innerHTML = `Falta repartir <b>${clp(falta)}</b> de ${clp(objetivo)}`;
  } else {
    caja.className = "mixto__resto es-mal";
    caja.innerHTML = `Te pasaste por <b>${clp(-falta)}</b> de ${clp(objetivo)}`;
  }
}

const aCobrar = () =>
  Math.max(0, totalCarrito() - soloNumeros($("#descuento").value)) + soloNumeros($("#propina").value);

function pintarRapidos() {
  const total = aCobrar();
  // Billetes chilenos que sirven para pagar este monto, más el monto justo.
  const billetes = [1000, 2000, 5000, 10000, 20000].filter((b) => b >= total);
  const opciones = [total, ...billetes].filter((v, i, a) => a.indexOf(v) === i).slice(0, 5);
  $("#rapidos").innerHTML = opciones
    .map((v) => `<button data-paga="${v}">${v === total ? "Justo" : clp(v)}</button>`)
    .join("");
}

function calcularVuelto() {
  const caja = $("#vuelto");
  if (medioPago !== "efectivo") { caja.classList.remove("is-on"); return; }
  const paga = soloNumeros($("#pagaCon").value);
  const cobrado = aCobrar();
  if (!paga) { caja.classList.remove("is-on"); return; }
  const dif = paga - cobrado;
  caja.classList.add("is-on");
  caja.classList.toggle("falta", dif < 0);
  caja.innerHTML = dif >= 0
    ? `Vuelto <b>${clp(dif)}</b>`
    : `Falta <b>${clp(-dif)}</b>`;
}

async function confirmarVenta() {
  const boton = $("#cobroConfirmar");
  boton.disabled = true;
  try {
    const cuerpo = {
      lineas: lineasParaVenta(),
      medio_pago: medioPago,
      descuento: soloNumeros($("#descuento").value),
      propina: soloNumeros($("#propina").value),
    };
    const paga = soloNumeros($("#pagaCon").value);
    if (medioPago === "efectivo" && paga && !mixto) cuerpo.paga_con = paga;

    if (mixto) {
      // Las partes que tienen algo, y que tienen que sumar lo cobrado sin propina.
      const pagos = Object.entries(mixtoMontos)
        .filter(([, monto]) => monto > 0)
        .map(([medio, monto]) => ({ medio, monto }));
      const objetivo = Math.max(0, totalCarrito() - soloNumeros($("#descuento").value));
      const suma = pagos.reduce((s, p) => s + p.monto, 0);
      if (pagos.length < 2) { boton.disabled = false;
        return avisar("Un pago mixto necesita al menos dos formas. Si es una sola, "
          + "desmarca «Paga en dos formas».", true); }
      if (suma !== objetivo) { boton.disabled = false;
        return avisar(`Las partes suman ${clp(suma)} y hay que cobrar ${clp(objetivo)}. `
          + "Tienen que dar lo mismo.", true); }
      cuerpo.pagos = pagos;
      cuerpo.propina = 0;             // en mixto no hay propina
    }

    const venta = await api("/ventas", { method: "POST", body: JSON.stringify(cuerpo) });
    carrito = [];
    olvidarAvisos();
    pintarCarrito();
    $("#capaCobro").classList.remove("is-on");
    ultimaVenta = venta.id;
    avisar(
      venta.vuelto != null && venta.vuelto > 0
        ? `Venta #${venta.numero} · vuelto ${clp(venta.vuelto)}`
        : `Venta #${venta.numero} registrada`
    );
    if (imprimirSiempre) imprimir(`/comprobante/${venta.id}`);
    cargarTurno();
    // Refrescar el saldo: con el tope duro, el pedido siguiente tiene que ver el
    // stock ya descontado. Sin esto, con 3 en bodega se vendían 3 y el toque
    // siguiente seguía viendo 3 —y el servidor lo rechazaba, mostrando un error
    // que la pantalla decía que no iba a pasar—.
    cargarCarta();
  } catch (e) {
    avisar(e.message, true);
  } finally {
    boton.disabled = false;
  }
}

/* ---------------- el día ---------------- */
const horasYminutos = (min) => {
  const h = Math.floor(min / 60), m = min % 60;
  return h ? `${h} h ${m ? m + " min" : ""}`.trim() : `${m} min`;
};

const hoyISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/* El día contesta dos preguntas que NO son la misma, y mezclarlas fue el
   problema: el local tenía la caja recién abierta, sin una sola venta, y la
   pantalla —que había quedado en "Mes"— mostraba plata vendida, ticket promedio
   y efectivo. Todo era del mes y era cierto, pero al lado de un cajón vacío se
   lee como si fuera de ahora y no hay cómo saber qué cifra creer.

   · por TURNO  — "cómo va la caja que está abierta". La mira el que atiende.
   · por DÍA / SEMANA / MES — "cuánto se vendió". La mira el dueño.

   Con caja abierta se entra por turno, que es el caso de casi todos los días.
   Con la caja cerrada no se muestra nada solo: hay que elegir a mano qué turno
   mirar. Un "$0" al lado de "Ticket promedio" también es un número que se lee
   como dato, y no lo es. */
let periodo = "dia";
let turnoElegido = null;      // el turno que se está mirando, cuando periodo es "turno"
let periodoALaMano = false;   // ¿lo eligió la persona? Entonces no se le cambia solo

/* De un día elegido saca el rango que corresponde al período.
   La semana parte el lunes, como se cuenta acá. */
function rangoDelPeriodo(f) {
  const [a, m, d] = f.split("-").map(Number);
  const base = new Date(a, m - 1, d);
  const iso = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  if (periodo === "semana") {
    const lunes = new Date(base);
    lunes.setDate(base.getDate() - ((base.getDay() + 6) % 7));
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    return [iso(lunes), iso(domingo)];
  }
  if (periodo === "mes") {
    return [iso(new Date(a, m - 1, 1)), iso(new Date(a, m, 0))];
  }
  return [f, f];               // "dia" y "turno" miran un solo día
}

const horaCorta = (x) => new Date(x).toLocaleTimeString("es-CL",
  { hour: "2-digit", minute: "2-digit", hour12: false });

/* Cuando El día se abre solo y hay caja abierta, parte por turno: es lo que
   quiere ver el que está atendiendo. Si la persona ya eligió un período con el
   dedo, se respeta y no se le mueve por debajo. */
function periodoQueCorresponde() {
  if (!periodoALaMano && TURNO && TURNO.abierto && TURNO.turno) {
    periodo = "turno";
    turnoElegido = TURNO.turno.id;
  }
  $$(".periodo").forEach((b) => b.classList.toggle("is-on", b.dataset.periodo === periodo));
}

/* La lista de turnos del día elegido. Nunca cae solo en uno cerrado: si no hay
   caja abierta, queda en "Elegí un turno" y no se muestra ninguna cifra. */
function pintarSelectorDeTurnos(turnos) {
  const sel = $("#selTurno");
  if (!turnos.some((t) => t.id === turnoElegido)) {
    const abierto = turnos.find((t) => !t.cerrado_at);
    turnoElegido = abierto ? abierto.id : null;
  }
  if (!turnos.length) {
    sel.innerHTML = `<option value="">No se abrió caja este día</option>`;
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  sel.innerHTML = (turnoElegido ? "" : `<option value="">Elegí un turno…</option>`)
    + turnos.map((t) => {
      const quien = t.abrio || t.cajero || "sin nombre";
      const cuando = t.cerrado_at
        ? `${horaCorta(t.abierto_at)} a ${horaCorta(t.cerrado_at)}`
        : `abierta desde las ${horaCorta(t.abierto_at)}`;
      return `<option value="${t.id}"${t.id === turnoElegido ? " selected" : ""}
        >${esc(quien)} · ${cuando}</option>`;
    }).join("");
}

/* Sin turno que mirar no se inventan cifras: un cartel y las tablas vacías. */
function nadaQueMirar(hayTurnos) {
  $("#kpis").innerHTML = `
    <div class="sin-turno" style="grid-column:1/-1">
      <b>${hayTurnos ? "Elegí un turno arriba" : "La caja está cerrada"}</b>
      ${hayTurnos
        ? "Las cifras que salgan van a ser las de ese turno."
        : "Este día no se abrió caja. Cuando se abra, acá va cómo va el turno."}
    </div>`;
  $("#tituloVentas").textContent = "Ventas";
  $("#tablaVentas").innerHTML = "";
  $("#zonaCaja").innerHTML = "";
  $("#tablaTop").innerHTML = "";
}

/* Las dos líneas cuyo monto no sale de la carta: lo escrito a mano y lo impreso en
   un ticket de balanza. No es sospecha: es que son las únicas que no se pueden
   revisar después contra un precio, así que se ven sumadas y con quién las cobró.
   El nombre lo escribe una persona: va escapado. */
function kpiQuienCobro(titulo, d) {
  if (!d || !d.cantidad) return "";
  const quienes = (d.por_persona || []).slice(0, 3)
    .map((x) => `${esc(x.nombre)} ${clp(x.total)}`).join(" · ");
  return `<div class="kpi"><span>${titulo}</span><b>${clp(d.total)}</b>
    <small>${d.cantidad} línea${d.cantidad === 1 ? "" : "s"}${quienes ? " · " + quienes : ""}</small></div>`;
}

async function cargarDia() {
  const campo = $("#fechaDia");
  if (!campo.value) campo.value = hoyISO();
  const f = campo.value;
  const [desde, hasta] = rangoDelPeriodo(f);

  // Los turnos primero: de ahí sale el selector, y sin él no se sabe qué pedir.
  const turnos = await api(`/turnos?desde=${desde}&hasta=${hasta}`);
  TURNOS_A_LA_VISTA = turnos;
  pintarCierresDeCaja(turnos);
  $("#campoTurno").hidden = periodo !== "turno";

  if (periodo === "turno") {
    pintarSelectorDeTurnos(turnos);
    if (!turnoElegido) return nadaQueMirar(turnos.length > 0);
  }

  const porTurno = periodo === "turno";
  const [r, lista] = await Promise.all([
    api(porTurno ? `/resumen?turno_id=${turnoElegido}` : `/resumen?desde=${desde}&hasta=${hasta}`),
    api(porTurno ? `/ventas?turno_id=${turnoElegido}` : `/ventas?fecha=${f}`),
  ]);

  // El rótulo dice de qué período es la plata. Antes decía "Vendido hoy" incluso
  // mirando el mes entero, y esa sola palabra hacía que un total del mes se
  // leyera como la venta del día.
  const t = r.turno;
  const rotulo = porTurno ? "Vendido en el turno"
    : periodo === "semana" ? "Vendido en la semana"
    : periodo === "mes" ? "Vendido en el mes"
    : f === hoyISO() ? "Vendido hoy" : "Vendido ese día";

  $("#kpis").innerHTML = `
    <div class="kpi"><span>${rotulo}</span><b>${clp(r.total)}</b>
      <small>${r.ventas} venta${r.ventas === 1 ? "" : "s"}</small></div>
    <div class="kpi"><span>Ticket promedio</span><b>${clp(r.ticket_promedio)}</b></div>
    ${r.dias > 1 ? `<div class="kpi"><span>Promedio por día</span><b>${clp(r.promedio_diario)}</b>
      <small>${r.dias} días</small></div>` : ""}
    <div class="kpi"><span>Efectivo</span><b>${clp(r.por_medio.efectivo.total)}</b>
      <small>${r.por_medio.efectivo.cantidad} ventas</small></div>
    <div class="kpi"><span>Tarjetas</span><b>${clp(r.por_medio.debito.total + r.por_medio.credito.total)}</b>
      <small>${r.por_medio.debito.cantidad + r.por_medio.credito.cantidad} ventas</small></div>
    ${r.sacado ? `<div class="kpi"><span>Sacado de la caja</span><b>−${clp(r.sacado)}</b>
      <small>${r.metido ? "y " + clp(r.metido) + " que entró" : "para comprar cosas"}</small></div>` : ""}
    ${!r.sacado && r.metido ? `<div class="kpi"><span>Metido a la caja</span><b>+${clp(r.metido)}</b></div>` : ""}
    ${t ? `<div class="kpi"><span>${t.abierto ? "Debe haber en el cajón" : "Debía haber al cerrar"}</span>
      <b>${clp(r.efectivo_en_caja)}</b>
      <small>fondo ${clp(t.monto_inicial)} + ventas − lo sacado</small></div>` : ""}
    <div class="kpi"><span>Neto / IVA</span><b>${clp(r.neto)}</b>
      <small>IVA ${clp(r.iva)}</small></div>
    ${r.propinas ? `<div class="kpi"><span>Propinas</span><b>${clp(r.propinas)}</b></div>` : ""}
    ${r.anuladas.cantidad ? `<div class="kpi"><span>Anuladas</span><b>${r.anuladas.cantidad}</b>
      <small>${clp(r.anuladas.total)}</small></div>` : ""}
    ${kpiQuienCobro("Cobros a mano", r.varios)}
    ${kpiQuienCobro("Balanza", r.balanza)}`;

  $("#tituloVentas").textContent = porTurno ? "Ventas del turno"
    : f === hoyISO() ? "Ventas de hoy" : "Ventas del día";
  $("#tablaVentas").innerHTML = `
    <tr><th>#</th><th>Hora</th><th>Medio</th><th class="num">Total</th><th></th></tr>
    ${lista.ventas.length ? lista.ventas.map((v) => `
      <tr class="${v.estado === "anulada" ? "anulada" : ""}">
        <td>${v.numero}</td>
        <td>${horaCorta(v.creada_at)}</td>
        <td><span class="pill">${v.medio_pago}</span></td>
        <td class="num">${clp(v.total)}</td>
        <td style="white-space:nowrap">
          <button class="btn btn--chico" data-imprimir="${v.id}">Imprimir</button>
          ${v.estado === "pagada"
            ? `<button class="btn btn--peligro btn--chico" data-anular="${v.id}">Anular</button>`
            : ""}</td>
      </tr>`).join("") : `<tr><td colspan="5" style="color:var(--suave)">${
        porTurno ? "Este turno todavía no ha vendido nada." : "Todavía no hay ventas."
      }</td></tr>`}`;

  pintarLaPlataDelCajon(r);

  $("#tablaTop").innerHTML = `
    <tr><th>Producto</th><th class="num">Cant.</th><th class="num">Total</th></tr>
    ${r.mas_vendidos.length ? r.mas_vendidos.map((p) => `
      <tr><td>${esc(p.nombre)}</td><td class="num">${p.cantidad}</td><td class="num">${clp(p.total)}</td></tr>
    `).join("") : `<tr><td colspan="3" style="color:var(--suave)">Sin datos todavía.</td></tr>`}`;
}

/* El cuadro del dinero del cajón. Lo pidió el local con estas palabras: "aparece
   lo sacado, pero no se resta". Tenían razón en el fondo del reclamo: el número
   se restaba, pero en ninguna parte se VEÍA restarse, así que no había cómo
   creerle. Mirando un turno la tabla es la cuenta entera —fondo, lo que entró,
   cada retiro con su motivo y su nombre, y cuánto tiene que haber— y da exacto
   el mismo total que el cierre, porque sale de la misma función del servidor. */
function pintarLaPlataDelCajon(r) {
  const movs = r.movimientos_caja || [];
  const t = r.turno;
  const fila = (m) => `
    <tr>
      <td>${esc(m.hora)}</td>
      <td>${esc(m.motivo)}</td>
      <td>${esc(m.hecho_por) || "—"}</td>
      <td class="num ${m.tipo === "ingreso" ? "ok" : "mal"}">
        ${m.tipo === "ingreso" ? "+" : "−"}${clp(m.monto)}</td>
    </tr>`;

  if (!t) {
    // Por día, semana o mes no existe "lo que hay en el cajón": son varios
    // cajones de varios turnos. Solo se muestra el movimiento, si lo hubo.
    $("#zonaCaja").innerHTML = !movs.length ? "" : `
      <h3 style="margin-top:22px">Plata sacada de la caja</h3>
      <div class="tabla-wrap"><table class="tabla">
        <tr><th>Hora</th><th>Motivo</th><th>Quién</th><th class="num">Monto</th></tr>
        ${movs.map(fila).join("")}
        <tr><td colspan="3"><b>Del efectivo vendido, queda</b></td>
            <td class="num"><b>${clp(r.efectivo_neto)}</b></td></tr>
      </table></div>`;
    return;
  }

  $("#zonaCaja").innerHTML = `
    <h3 style="margin-top:22px">La plata del cajón</h3>
    <div class="tabla-wrap"><table class="tabla">
      <tr><th>Hora</th><th>Qué</th><th>Quién</th><th class="num">Monto</th></tr>
      <tr><td>${horaCorta(t.abierto_at)}</td><td>Fondo con que se abrió</td>
          <td>${esc(t.abrio) || "—"}</td>
          <td class="num ok">+${clp(t.monto_inicial)}</td></tr>
      <tr><td>—</td><td>Lo que entró en efectivo</td><td>—</td>
          <td class="num ok">+${clp(t.efectivo_de_ventas)}</td></tr>
      ${movs.map(fila).join("")}
      ${t.propinas_pagadas ? `<tr><td>—</td>
          <td>Propinas de tarjeta pagadas en efectivo</td><td>—</td>
          <td class="num mal">−${clp(t.propinas_pagadas)}</td></tr>` : ""}
      <tr><td colspan="3"><b>${t.abierto ? "Debe haber en el cajón" : "Debía haber al cerrar"}</b></td>
          <td class="num"><b>${clp(r.efectivo_en_caja)}</b></td></tr>
      ${t.efectivo_contado == null ? "" : `<tr>
          <td colspan="3">Se contó al cerrar</td>
          <td class="num">${clp(t.efectivo_contado)}
            ${t.diferencia
              ? `<span class="mal">${t.diferencia < 0 ? "faltaron" : "sobraron"}
                   ${clp(Math.abs(t.diferencia))}</span>`
              : `<span class="ok">cuadra</span>`}</td></tr>`}
    </table></div>`;
}

function pintarCierresDeCaja(turnos) {
  $("#tablaTurnos").innerHTML = `
    <tr><th>Día</th><th>Abrió / cerró</th><th>Quiénes estuvieron</th>
        <th class="num">Esperado</th><th class="num">Contado</th><th class="num">Dif.</th><th></th></tr>
    ${turnos.length ? turnos.map((t) => {
      const d = t.diferencia;
      // Con signo adelante y no "$-9.100": el menos pegado al peso se lee como
      // parte del número y se pasa por alto justo cuando importa.
      const marca = d === null ? "<span class='pill'>abierto</span>"
        : d === 0 ? "<span class='ok'>cuadra</span>"
        : `<span class='mal'>${d < 0 ? "−" : "+"}${clp(Math.abs(d))}</span>`;
      return `<tr>
        <td>${new Date(t.abierto_at).toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit" })}</td>
        <td>${esc(t.abrio || t.cajero || "—")}
          ${t.cerro && t.cerro !== t.abrio ? `<div style="font-size:12.5px;color:var(--suave)">cerró ${esc(t.cerro)}</div>` : ""}</td>
        <td>${(t.estuvieron || []).length
              ? t.estuvieron.map((g) => `<span class="quien-pill" style="--c:${g.color || "#8A5A34"}">
                    ${esc(g.nombre)} <b>${horasYminutos(g.minutos)}</b></span>`).join(" ")
              : '<span style="color:var(--suave)">—</span>'}</td>
        <td class="num">${clp(t.efectivo_esperado)}</td>
        <td class="num">${t.efectivo_contado == null ? "—" : clp(t.efectivo_contado)}</td>
        <td class="num">${marca}</td>
        <td style="white-space:nowrap">
          <button class="btn btn--chico" data-ver-cierre="${t.id}">Ver</button>
          <button class="btn btn--chico" data-cierre="${t.id}">Imprimir</button></td>
      </tr>`;
    }).join("") : `<tr><td colspan="7" style="color:var(--suave)">Sin cierres en este período.</td></tr>`}`;
}

async function anular(id) {
  const motivo = prompt("¿Por qué se anula esta venta?\n(queda registrado)");
  if (motivo === null) return;
  try {
    await api(`/ventas/${id}/anular`, { method: "POST", body: JSON.stringify({ motivo }) });
    avisar("Venta anulada");
    cargarDia();
  } catch (e) { avisar(e.message, true); }
}

/* ---------------- editor de la carta ---------------- */
/* Los nombres de la biblioteca, agrupados para poder buscarlos. Las claves
   salen de dibujos.js: acá solo se les pone un nombre legible y un grupo.
   Lo que no esté nombrado igual aparece, con su clave: mejor un nombre feo que
   un dibujo escondido. */
const GRUPOS_DIBUJO = [
  ["Café y calientes", {
    "taza": "Espresso", "taza-cortado": "Cortado", "mug": "Café grande",
    "mug-espuma": "Capuchino", "mug-arte": "Latte con arte", "mug-crema": "Con crema",
    "para-llevar": "Para llevar", "para-llevar-te": "Té para llevar",
    "tetera": "Tetera", "tetera-verde": "Tetera verde",
  }],
  ["Fríos", {
    "vaso": "Vaso con hielo", "vaso-leche": "Con leche", "vaso-limon": "Con limón",
    "vaso-verde": "Verde", "vaso-menta": "Con menta", "frappe": "Frappé",
    "para-llevar-frio": "Frío para llevar",
  }],
  ["Envases", {
    "botella-agua": "Botella de agua", "botella-bebida": "Bebida",
    "botella-jugo": "Jugo en botella", "botella-vidrio": "Botella de vidrio",
    "lata": "Lata", "lata-verde": "Lata verde", "lata-naranja": "Lata naranja",
    "jugo-caja": "Jugo en caja", "jugo-caja-verde": "Jugo en caja verde",
  }],
  ["Panadería", {
    "pan-marraqueta": "Marraqueta", "pan-hallulla": "Hallulla",
    "pan-amasado": "Pan amasado", "pan-baguette": "Baguette",
    "pan-integral": "Pan integral", "croissant": "Croissant",
    "croissant-almendras": "Croissant de almendras",
    "empanada": "Empanada", "empanada-queso": "Empanada de queso",
    "empanada-cruda": "Empanada cruda",
  }],
  ["Sándwiches y comida", {
    "sandwich": "Sándwich", "sandwich-queso": "Sándwich de queso",
    "churrasco": "Churrasco", "wrap": "Wrap", "pizza": "Pizza",
    "sopa": "Sopa", "ensalada": "Ensalada", "yogurt": "Yogurt con granola",
    "plato": "Plato caliente", "plato-frio": "Plato frío",
  }],
  ["Dulces", {
    "torta": "Torta", "torta-chocolate": "Torta de chocolate",
    "torta-limon": "Torta de limón", "torta-manzana": "Kuchen",
    "cheesecake": "Cheesecake", "kuchen": "Kuchen en porción",
    "pie-limon": "Pie de limón", "brownie": "Brownie", "alfajor": "Alfajor",
    "galleta": "Galleta", "galleta-avena": "Galleta de avena",
    "dona": "Dona", "dona-chocolate": "Dona de chocolate",
    "dona-chispas": "Dona con chispas", "muffin": "Muffin",
    "muffin-chips": "Muffin con chips", "cupcake": "Cupcake",
    "helado": "Helado", "helado-chocolate": "Helado de chocolate",
  }],
  ["Cervezas", {
    "cerveza-lata": "Cerveza en lata", "cerveza-lata-roja": "Lata roja",
    "cerveza-lata-verde": "Lata verde", "cerveza-lata-azul": "Lata azul",
    "cerveza-botella": "Cerveza en botella", "cerveza-botella-verde": "Botella verde",
    "cerveza-litro": "Litro de cerveza", "pack-cervezas": "Pack de cervezas",
  }],
  ["Bebidas y aguas", {
    "bebida-cola": "Bebida cola", "bebida-naranja": "Bebida naranja",
    "bebida-amarilla": "Bebida amarilla", "bebida-lima": "Bebida lima limón",
    "bebida-lata-cola": "Cola en lata", "bebida-lata-naranja": "Naranja en lata",
    "agua-mineral": "Agua mineral", "agua-con-gas": "Agua con gas",
    "energetica": "Bebida energética", "pack-bebidas": "Pack de bebidas",
  }],
  ["Vinos y destilados", {
    "vino-tinto": "Vino tinto", "vino-blanco": "Vino blanco",
    "espumante": "Espumante", "pisco": "Pisco", "ron": "Ron", "whisky": "Whisky",
  }],
  ["Almacén", {
    "leche-caja": "Leche en caja", "nectar-caja": "Néctar en caja",
  }],
  ["Promociones", { "combo": "Combo", "desayuno": "Desayuno" }],
];

const DIBUJOS = Object.assign({}, ...GRUPOS_DIBUJO.map(([, m]) => m));

/* Elegir el dibujo VIÉNDOLO. Con 68 opciones, una lista de nombres es
   inservible: nadie sabe qué es "vaso-menta" hasta que lo ve. */
/* El selector de dibujos.

   Con 68 dibujos ya costaba encontrar uno; con los de botillería y almacén son
   más de 90 y en una grilla de recuadros de 80 px el nombre no se alcanzaba a
   leer. Dos arreglos: los recuadros crecen —el nombre es lo que se busca, no el
   dibujo— y hay un buscador que filtra mientras se escribe. */
function filtrarDibujos(texto) {
  const q = sinTildes(texto);
  document.querySelectorAll(".dibujos__seccion").forEach((sec) => {
    let vivos = 0;
    sec.querySelectorAll("[data-busca]").forEach((b) => {
      const calza = !q || b.dataset.busca.includes(q);
      b.hidden = !calza;
      if (calza) vivos++;
    });
    sec.hidden = vivos === 0;
  });
}

function selectorDeDibujo(elegido) {
  return `
    <div class="campo"><span>Dibujo en la pantalla</span>
      <input type="hidden" id="fDibujo" value="${esc(elegido || "mug")}">
      <input id="buscarDibujo" class="dibujos__buscar" type="text" autocomplete="off"
             placeholder="Buscar dibujo: cerveza, torta, lata...">
      <div class="dibujos">
        ${GRUPOS_DIBUJO.map(([grupo, mapa]) => `
          <div class="dibujos__seccion" data-grupo="${esc(grupo)}">
            <div class="dibujos__grupo">${esc(grupo)}</div>
            <div class="dibujos__fila">
              ${Object.entries(mapa).map(([k, nombre]) => `
                <button type="button" class="dibujo-op ${k === elegido ? "is-on" : ""}"
                        data-dibujo="${k}" data-busca="${esc(sinTildes(nombre + " " + grupo))}"
                        title="${esc(nombre)}">
                  ${dibujo({ k })}<small>${esc(nombre)}</small>
                </button>`).join("")}
            </div>
          </div>`).join("")}
      </div>
    </div>`;
}

function categoriasPlegadasGuardadas() {
  try {
    const ids = JSON.parse(localStorage.getItem("pos.carta.plegadas") || "[]");
    return new Set(Array.isArray(ids) ? ids.filter(Number.isInteger) : []);
  } catch (e) { return new Set(); }
}

const categoriasPlegadas = categoriasPlegadasGuardadas();

// Sólo ocultamos filas: buscar o plegar no descarta nombres/precios sin guardar.
function filtrarEditorCarta() {
  const q = sinTildes($("#buscarCarta").value.trim());
  $("#limpiarBuscarCarta").hidden = !q;
  let hallados = 0;
  $$("#editorCarta .grupo").forEach((grupo) => {
    let coincidencias = 0;
    grupo.querySelectorAll("[data-fila]").forEach((fila) => {
      const nombre = fila.querySelector('[data-campo="nombre"]').value;
      fila.hidden = !!q && !sinTildes(nombre).includes(q);
      if (!fila.hidden) coincidencias++;
    });
    grupo.hidden = !!q && coincidencias === 0;
    hallados += coincidencias;
    const plegada = !q && categoriasPlegadas.has(+grupo.dataset.grupo);
    grupo.querySelector(".grupo__productos").hidden = plegada;
    const boton = grupo.querySelector("[data-plegar-cat]");
    if (boton) boton.setAttribute("aria-expanded", String(!plegada));
  });
  $("#cartaSinResultados").hidden = !q || hallados > 0;
}

function alternarCategoriaCarta(id) {
  const grupo = $(`#editorCarta [data-grupo="${id}"]`);
  if (!grupo) return;
  const productos = grupo.querySelector(".grupo__productos");
  productos.hidden = !productos.hidden;
  grupo.querySelector("[data-plegar-cat]").setAttribute("aria-expanded", String(!productos.hidden));
  if (productos.hidden) categoriasPlegadas.add(id);
  else categoriasPlegadas.delete(id);
  try { localStorage.setItem("pos.carta.plegadas", JSON.stringify([...categoriasPlegadas])); } catch (e) {}
}

function pintarEditorCarta() {
  $("#editorCarta").innerHTML = CATEGORIAS.map((c) => `
    <div class="grupo" data-grupo="${c.id}">
      <div class="grupo__top">
        <h3><button type="button" class="grupo__plegar" data-plegar-cat="${c.id}"
                    aria-expanded="true" aria-controls="productos-carta-${c.id}">
          <span class="grupo__flecha" aria-hidden="true">▾</span>${esc(c.nombre)}</button></h3>
        <div class="grupo__acc">
          <button class="btn btn--chico btn--fantasma" data-cat-editar="${c.id}"
                  data-permiso="editar_carta">Editar</button>
          <button class="btn btn--chico btn--fantasma" data-cat-borrar="${c.id}"
                  data-permiso="editar_carta">Borrar</button>
          <button class="btn btn--chico" data-nuevo-en="${c.id}">+ Producto</button>
        </div>
      </div>
      <div class="grupo__productos" id="productos-carta-${c.id}">
      ${c.productos.map((p) => `
        <div class="fila${p.activo ? "" : " inactivo"}" data-fila="${p.id}">
          <input type="text" value="${esc(p.nombre)}" data-campo="nombre">
          <div class="num"><input type="text" inputmode="numeric" value="${p.precio}" data-campo="precio"></div>
          <label class="marca"><input type="checkbox" data-campo="activo" ${p.activo ? "checked" : ""}> A la venta</label>
          <div class="fila__acc">
            <button class="btn btn--chico" data-guardar="${p.id}">Guardar</button>
            <button class="btn btn--chico" data-editar="${p.id}" title="Todos los datos">···</button>
          </div>
        </div>`).join("") || `<p class="ayuda" style="margin:0 0 8px">Esta categoría todavía no tiene productos.</p>`}
      </div>
    </div>`).join("");
  // El editor se redibuja cada vez que cambia la carta, después de que
  // pintarQuien ya corrió, así que los botones que solo puede el dueño hay que
  // apagarlos acá o aparecen prendidos para el cajero hasta el próximo login.
  $$("#editorCarta [data-permiso]").forEach((b) => {
    const falta = !puedo(b.dataset.permiso);
    b.disabled = falta;
    b.title = falta ? "Esto lo hace el dueño" : "";
  });
  filtrarEditorCarta();
}

/* ---- editar y borrar una categoría ----
   Hasta la 2.11 una categoría solo se podía crear: el nombre no se podía
   corregir y borrarla no existía. Editar cambia el nombre (y de paso el orden,
   que es en qué lugar del rail aparece). Borrar es de verdad —la fila se va—
   pero solo si está vacía: un producto no puede quedar sin categoría. */
function editarCategoria(id) {
  const c = CATEGORIAS.find((x) => x.id === id);
  if (!c) return;
  const top = document.querySelector(`[data-grupo="${id}"] .grupo__top`);
  if (!top) return;
  top.innerHTML = `
    <div class="grupo__editar">
      <input type="text" id="catNombre" value="${esc(c.nombre)}" autocomplete="off"
             style="font-size:17px;font-weight:700">
      <label class="grupo__orden">Orden
        <input type="text" inputmode="numeric" id="catOrden" value="${c.orden}"></label>
      <button class="btn btn--chico btn--cobrar" data-cat-guardar="${id}">Guardar</button>
      <button class="btn btn--chico btn--fantasma" data-cat-cancelar>Cancelar</button>
    </div>`;
  setTimeout(() => { const n = $("#catNombre"); if (n) { n.focus(); n.select(); } }, 40);
}

function guardarCategoria(id) {
  const c = CATEGORIAS.find((x) => x.id === id);
  if (!c) return;
  const nombre = ($("#catNombre").value || "").trim();
  if (!nombre) return avisar("Escribe un nombre para la categoría", true);
  const orden = soloNumeros(($("#catOrden") || {}).value || 0);
  // activa va tal como está: el PUT pisa todos los campos, así que si no lo
  // mandáramos, una categoría apagada se prendería sola al cambiarle el nombre.
  api(`/categorias/${id}`, { method: "PUT",
    body: JSON.stringify({ nombre, orden, activa: c.activa }) })
    .then(() => { avisar("Categoría guardada"); cargarCarta(); })
    .catch((e) => avisar(e.message, true));
}

function borrarCategoria(id) {
  const c = CATEGORIAS.find((x) => x.id === id);
  if (!c) return;
  const cuantos = (c.productos || []).length;
  if (cuantos) {
    return avisar(`«${c.nombre}» tiene ${cuantos} producto${cuantos === 1 ? "" : "s"} `
      + "adentro. Muévelos a otra categoría o bórralos primero.", true);
  }
  if (!confirm(`¿Borrar la categoría «${c.nombre}»? Está vacía, así que no se pierde nada.`)) return;
  api(`/categorias/${id}`, { method: "DELETE" })
    .then(() => { avisar("Categoría borrada"); cargarCarta(); })
    .catch((e) => avisar(e.message, true));
}

/* Ficha completa del producto: acá viven los datos que usan las PANTALLAS del
   local (el dibujo, la etiqueta, el destacado), que no caben en la lista. */
/* Los códigos de un producto que TODAVÍA NO EXISTE. Se juntan acá mientras la ficha está
   abierta y se adjuntan recién después de crearlo: /productos/{id}/codigos necesita un id,
   y el producto no tiene uno hasta que se aprieta Guardar. */
let CODIGOS_NUEVOS = [];

const PRODUCTO_EN_BLANCO = {
  id: null, nombre: "", precio: 0, descripcion: "", etiqueta: "", badge: "",
  antes: null, dibujo: "", color: "", destacado: false, activo: true, orden: 0,
  llevar_cuenta: false,
};

/* `id` nulo = producto nuevo. La ficha es la MISMA: el dueño pedía llenar todo de una vez
   en vez de crear, cerrar y volver a entrar a editar.

   Lo que no cambia: nada se crea hasta Guardar. Ver el comentario de nuevoProducto(). */
function abrirFichaProducto(id, categoriaId) {
  const nuevo = id == null;
  CODIGOS_NUEVOS = [];
  const cat = nuevo
    ? (CATEGORIAS.find((c) => c.id === (categoriaId || catActiva))
       || CATEGORIAS.filter((c) => c.activa)[0])
    : CATEGORIAS.find((c) => c.productos.some((p) => p.id === id));
  const p = nuevo ? { ...PRODUCTO_EN_BLANCO, categoria_id: cat && cat.id }
                  : cat.productos.find((x) => x.id === id);
  const cats = CATEGORIAS
    .map((c) => `<option value="${c.id}"${cat && c.id === cat.id ? " selected" : ""}>${esc(c.nombre)}</option>`).join("");

  // Dos columnas, como el cobro y el cierre. A la izquierda lo que ES el
  // producto —nombre, precio, códigos, cuántos hay—; a la derecha cómo SE VE en
  // las pantallas del local. El selector de dibujos es lo más alto de todo y
  // ocupaba media pantalla en medio del formulario: puesto en su propia columna
  // deja de empujar todo lo demás para abajo.
  $("#dialogoProducto").className = "dialogo dialogo--ficha";
  $("#dialogoProducto").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>${nuevo ? "Producto nuevo" : esc(p.nombre)}</h2>

    <div class="ficha">
      <div class="ficha__col">
        <div class="fila2">
          <label class="campo"><span>Nombre</span>
            <input id="fNombre" type="text" value="${esc(p.nombre)}"></label>
          <label class="campo"><span>Precio</span>
            <input id="fPrecio" type="text" inputmode="numeric"
                   value="${p.precio || ""}" placeholder="0"></label>
        </div>
        <label class="campo"><span>Categoría</span><select id="fCat">${cats}</select></label>
        <label class="campo"><span>Descripción (se ve en la pantalla del menú)</span>
          <input id="fDesc" type="text" value="${esc(p.descripcion)}"></label>

        <div class="campo">
          <span>Códigos de barra</span>
          <div id="fCodigos"></div>
          <div class="codigo-poner">
            <!-- inputmode="none" a propósito: con "numeric" el teclado en
                 pantalla se abre encima cada vez que el lector "escribe" acá. -->
            <input id="fCodigo" type="text" inputmode="none" autocomplete="off"
                   placeholder="Pasa el producto por el lector">
            <button class="btn btn--chico" data-pegar-codigo="${p.id == null ? "" : p.id}">Agregar</button>
          </div>
          <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Un producto puede
            tener varios: la lata suelta y el pack de 6 traen códigos distintos.</p>
        </div>

        <div class="tal-cual" id="zonaTalCual" data-producto="${p.id == null ? "" : p.id}"></div>

        <details class="avanzado" id="fAvanzado">
          <summary>Sacar el precio desde lo que te cuesta</summary>
          <div class="avanzado__cuerpo">
            <label class="campo"><span>¿Cuánto te cuesta a ti?</span>
              <input id="fCosto" type="text" inputmode="numeric" placeholder="0"></label>
            <label class="marca" style="margin-bottom:6px">
              <input type="checkbox" id="fCostoConIva" checked>
              Ese precio ya trae IVA</label>
            <p class="ayuda" id="fCostoNota" style="margin:0 0 10px;font-size:12.5px"></p>
            <div id="fSugerido"></div>
          </div>
        </details>
        <details class="avanzado" id="fBalanza"${p.plu ? " open" : ""}>
          <summary>Se vende por peso (balanza)</summary>
          <div class="avanzado__cuerpo">
            <label class="campo"><span>Número en la balanza (PLU)</span>
              <input id="fPlu" type="text" inputmode="numeric" pattern="[0-9]*"
                     value="${esc(p.plu || "")}"></label>
            <label class="campo"><span>Precio por kilo</span>
              <input id="fPrecioKilo" type="text" inputmode="numeric"
                     value="${p.precio_kilo || ""}" placeholder="0"></label>
            <p class="ayuda">Si la balanza imprime una etiqueta con el número del producto,
              la caja lo reconoce y cobra el peso por el precio por kilo.
              Déjalo vacío si este producto no se pesa.</p>
          </div>
        </details>
      </div>

      <div class="ficha__col">
        ${selectorDeDibujo(p.dibujo)}
        <div class="fila2">
          <label class="campo"><span>Etiqueta (opcional)</span>
            <input id="fEtiqueta" type="text" value="${esc(p.etiqueta)}"
                   placeholder="Nuevo, Sin lactosa..."></label>
          <label class="campo"><span>Precio antes (oferta)</span>
            <input id="fAntes" type="text" inputmode="numeric" value="${p.antes || ""}"
                   placeholder="vacío si no hay"></label>
        </div>
        <label class="marca" style="margin-bottom:10px">
          <input type="checkbox" id="fDestacado" ${p.destacado ? "checked" : ""}>
          Mostrar en el recuadro grande de la pantalla</label>
        <label class="campo"><span>Texto del recuadro grande</span>
          <input id="fBadge" type="text" value="${esc(p.badge)}"
                 placeholder="Recomendado de hoy"></label>
        <label class="marca"><input type="checkbox" id="fActivo"
          ${p.activo ? "checked" : ""}> A la venta</label>
      </div>
    </div>

    <div class="dialogo__pie">
      ${nuevo ? "" : `<button class="btn btn--peligro" id="fBorrar">Borrar para siempre</button>`}
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="fGuardar" style="width:auto">Guardar</button>
    </div>`;
  $("#capaProducto").classList.add("is-on");
  pintarTalCual(p);
  pintarCodigos(p.id);
  $("#fPlu").addEventListener("input", (e) => {
    e.target.value = e.target.value.replace(/[^0-9]/g, "");
  });
  if (nuevo) setTimeout(() => $("#fNombre") && $("#fNombre").focus(), 60);

  const costoReal = () => costoConIva(
    soloNumeros(($("#fCosto") || {}).value || 0),
    !$("#fCostoConIva") || $("#fCostoConIva").checked);
  const pintarNotaCosto = () => {
    const nota = $("#fCostoNota");
    if (!nota) return;
    const escrito = soloNumeros(($("#fCosto") || {}).value || 0);
    const conIva = $("#fCostoConIva");
    nota.innerHTML = !escrito
      ? "Lo que pagas por cada uno. Si compras con factura, ese precio viene sin "
        + "IVA: desmarca la casilla y yo le sumo el 19%."
      : (!conIva || conIva.checked
        ? `Hago la cuenta con <b>${clp(escrito)}</b> cada uno.`
        : `${clp(escrito)} sin IVA son <b>${clp(costoConIva(escrito, false))}</b> `
          + "con IVA. Hago la cuenta con ese.");
  };
  const dibujarSugerido = () => {
    const caja = $("#fSugerido");
    if (!caja) return;
    pintarNotaCosto();
    caja.innerHTML = bloqueSugerido(costoReal(), "fPrecio");
    if (costoReal()) refrescarSugerido();
  };
  if ($("#fCosto")) $("#fCosto").addEventListener("input", dibujarSugerido);
  if ($("#fCostoConIva")) $("#fCostoConIva").addEventListener("change", dibujarSugerido);
  dibujarSugerido();

  /* Si el producto ya lleva su cuenta, el costo NO es un dato nuevo: está en la
     Bodega y es el mismo con el que se valoriza lo que queda. Se trae de ahí para
     que la sugerencia hable del costo de verdad y no de uno escrito de memoria.
     Va después de dibujar y sin esperarlo: la ficha se usa igual sin esto. */
  if (!nuevo && puedo("inventario")) {
    api(`/productos/${id}/receta`).then((r) => {
      const campo = $("#fCosto");
      if (!campo || campo.value || FICHA_ABIERTA !== id) return;   // cerró o ya escribió
      if (!r || !r.costo_total) return;
      campo.value = r.costo_total;
      dibujarSugerido();
    }).catch(() => { });        // sin permiso o sin receta: se escribe a mano
  }

  $("#fGuardar").onclick = async () => {
    const antes = soloNumeros($("#fAntes").value);
    if (nuevo && !$("#fNombre").value.trim()) {
      return avisar("Ponle un nombre antes de guardar", true);
    }
    try {
      const cuerpo = JSON.stringify({
        categoria_id: +$("#fCat").value,
        nombre: $("#fNombre").value.trim() || p.nombre,
        descripcion: $("#fDesc").value.trim(),
        precio: soloNumeros($("#fPrecio").value),
        plu: $("#fPlu").value.replace(/[^0-9]/g, ""),
        precio_kilo: soloNumeros($("#fPrecioKilo").value),
        activo: $("#fActivo").checked,
        orden: p.orden,
        destacado: $("#fDestacado").checked,
        badge: $("#fBadge").value.trim(),
        antes: antes || null,
        etiqueta: $("#fEtiqueta").value.trim(),
        dibujo: $("#fDibujo").value,
        color: p.color || "",
        ...(usarInventario() && $("#fCuenta") && $("#fCuenta").checked !== p.llevar_cuenta
          ? { llevar_cuenta: $("#fCuenta").checked } : {}),
        // El costo y la cantidad no son columnas del producto: el servidor se los
        // pasa a su insumo, que es el mismo que muestra la Bodega.
        ...(costoReal() ? { costo: costoReal() } : {}),
        ...(usarInventario() && $("#fCuenta") && $("#fCuenta").checked && !p.llevar_cuenta
          ? { stock_inicial: soloNumeros(($("#fStockInicial") || {}).value || 0) } : {}),
      });
      const guardado = nuevo
        ? await api("/productos", { method: "POST", body: cuerpo })
        : await api(`/productos/${id}`, { method: "PUT", body: cuerpo });

      // Los códigos se adjuntan RECIÉN ahora, que el producto ya tiene id. Si alguno
      // falla no se pierde el producto: ya está creado y solo se dice cuál no entró.
      const fallaron = [];
      for (const c of (nuevo ? CODIGOS_NUEVOS : [])) {
        try {
          await api(`/productos/${guardado.id}/codigos`, {
            method: "POST", body: JSON.stringify({ codigo: c, cuantos: 1 }) });
        } catch (e) { fallaron.push(c); }
      }
      CODIGOS_NUEVOS = [];
      $("#capaProducto").classList.remove("is-on");
      await cargarCarta();
      avisar(fallaron.length
        ? `Guardado, pero no pude ponerle ${fallaron.length === 1 ? "el código" : "los códigos"} `
          + `${fallaron.join(", ")}. Agrégalo editándolo.`
        : (nuevo ? "Producto creado" : "Guardado"), fallaron.length > 0);
    } catch (e) { avisar(e.message, true); }
  };

  if ($("#fBorrar")) $("#fBorrar").onclick = async () => {
    // Borrar es para SIEMPRE y no es lo mismo que esconder. Si solo lo quieren
    // sacar de la venta un rato, está la casilla «A la venta» de acá arriba, que
    // se vuelve a marcar cuando quieran. Esto no.
    if (!confirm(`¿Borrar «${p.nombre}» para siempre?\n\n`
      + "Esto NO se puede deshacer. Las ventas viejas no se tocan (siguen "
      + "cuadrando), pero el producto desaparece de la carta.\n\n"
      + "¿Solo quieres dejar de venderlo por ahora? Cierra esto y desmarca "
      + "«A la venta»: eso sí se puede deshacer.")) return;
    try {
      await api(`/productos/${id}`, { method: "DELETE" });
      $("#capaProducto").classList.remove("is-on");
      await cargarCarta();
      avisar("Producto borrado");
    } catch (e) { avisar(e.message, true); }
  };
}

/* Preguntar PRIMERO, crear después.

   Antes creaba un producto llamado "Producto nuevo" a $1.000 y recién ahí abría
   la ficha. Si alguien cerraba la ficha, el producto quedaba igual: en la carta
   del local quedaron NUEVE productos llamados "Producto nuevo" a $1.000, todos
   sin stock, todos vendibles sin límite.

   Ahora no existe nada hasta que se aprieta Guardar. */
function nuevoProducto(catId) {
  if (!CATEGORIAS.filter((c) => c.activa).length) {
    return avisar("Primero crea una categoría", true);
  }
  // La ficha COMPLETA, no el formulario de tres campos: el dueño pedía poder ponerle el
  // dibujo, la descripción y los códigos de una vez, en lugar de crear, cerrar y editar.
  //
  // El formulario corto NO se va: sigue siendo el de escanear un código desconocido en
  // medio de una venta (dialogoProductoNuevoPorCodigo), donde con la fila esperando se
  // quiere poner nombre y precio y seguir cobrando.
  abrirFichaProducto(null, catId);
}

async function nuevaCategoria() {
  const nombre = prompt("¿Cómo se llama la categoría nueva?");
  if (!nombre || !nombre.trim()) return;
  try {
    await api("/categorias", { method: "POST", body: JSON.stringify({
      nombre: nombre.trim(), orden: CATEGORIAS.length, activa: true }) });
    await cargarCarta();
    avisar("Categoría creada. Agrégale productos con + Producto.");
  } catch (e) { avisar(e.message, true); }
}

async function guardarProducto(id) {
  const fila = document.querySelector(`[data-fila="${id}"]`);
  const cat = CATEGORIAS.find((c) => c.productos.some((p) => p.id === id));
  const p = cat.productos.find((x) => x.id === id);
  const cuerpo = {
    ...p,
    nombre: fila.querySelector('[data-campo="nombre"]').value.trim() || p.nombre,
    precio: soloNumeros(fila.querySelector('[data-campo="precio"]').value),
    activo: fila.querySelector('[data-campo="activo"]').checked,
    categoria_id: cat.id,
  };
  delete cuerpo.id;
  try {
    await api(`/productos/${id}`, { method: "PUT", body: JSON.stringify(cuerpo) });
    avisar("Guardado. Las pantallas del local lo toman en su próxima revisión.");
    await cargarCarta();
  } catch (e) { avisar(e.message, true); }
}

/* Dirección que hay que pegar en las pantallas del local. La mostramos acá para
   que nadie tenga que ir a buscar la IP del computador. */
/* El recuadro de la pestaña Carta: la dirección de esta caja en la red, y las
   de cada televisor. Las pantallas volvieron a vivir acá adentro en la 2.8, así
   que la caja SÍ sabe en qué dirección están y puede mostrarlas con su botón de
   copiar — que es lo que había que hacer a mano mientras fueron un programa
   aparte. */
function pintarConectar(salud) {
  const caja = $("#conectar");
  if (!caja) return;
  $("#pantallasLocal").hidden = !salud.en_la_red;
  if (!salud.en_la_red) return;
  const mia = (salud.carta_url || "").replace("/api/v1/carta", "");
  const p = salud.pantallas_url || (mia + "/pantallas");
  const fila = (cual, url) => `
    <div class="conectar__url">
      <span class="conectar__cual">${cual}</span>
      <code>${url}</code>
      <button class="btn btn--chico" data-copiar="${url}">Copiar</button>
    </div>`;

  caja.innerHTML = `
    En cada televisor, abre el navegador y entra a la dirección que le toca. No
    hay que instalar ni copiar nada: la carta le llega de esta caja sola.
    ${fila("Vitrina", p + "?p=1")}
    ${fila("Carta con precios", p + "?p=2")}
    ${fila("Las dos turnándose", p + "?tv=1")}
    <div class="conectar__url conectar__url--simple">
      <span class="conectar__cual">Si el TV se ve mal</span>
      <code>${p}/simple</code>
      <button class="btn btn--chico" data-copiar="${p}/simple">Copiar</button>
    </div>
    <p style="margin:10px 0 0;font-size:13px;line-height:1.6">
      El navegador que traen algunos televisores es muy viejo y muestra la
      pantalla en blanco con letras negras. Si te pasa, usa la última dirección:
      es la misma carta, más sobria, y anda en cualquier televisor. La normal se
      cambia sola cuando se da cuenta.
    </p>
    ${mia ? `<div class="conectar__url conectar__url--simple">
      <span class="conectar__cual">Esta caja</span>
      <code>${mia}</code>
      <button class="btn btn--chico" data-copiar="${mia}">Copiar</button>
    </div>
    <p style="margin:8px 0 0;font-size:13px;line-height:1.6">Esa es para abrir la
      caja desde un tablet o desde otro computador del local. La primera vez pide el
      <b>PIN de red</b>: el dueño lo ve en Ayuda → Ajustes.</p>` : ""}`;
}

/* ---------------- actualizaciones ----------------
   El dueño no tiene por qué saber que existe una "versión": el número está
   chico en la barra y solo se pone verde cuando hay algo nuevo. */
let INFO_VERSION = null;

// Si la última actualización se puede deshacer, y a qué versión.
let VUELTA = null;

async function cargarVersion() {
  try {
    const v = await api("/version");
    $("#version").textContent = "v" + v.version;
    $("#version").title = `Versión ${v.version} · ${v.nombre}`;
  } catch (e) { }
  // La revisión en línea va aparte: si no hay internet, no molesta a nadie.
  try {
    INFO_VERSION = await api("/actualizacion");
    if (INFO_VERSION && INFO_VERSION.hay_nueva) {
      $("#version").classList.add("hay-nueva");
      $("#version").textContent = "Actualizar a v" + INFO_VERSION.disponible;
    }
  } catch (e) { }
  try { VUELTA = await api("/actualizacion/vuelta"); } catch (e) { }
}

function dialogoVersion() {
  const i = INFO_VERSION || {};
  const hay = i.ok && i.hay_nueva;
  const cuerpo = !i.ok
    ? `<p class="ayuda">Estás usando la versión <b>${esc(i.actual || "")}</b>.</p>
       <div class="aviso">No pude revisar si hay una versión nueva.<br>
         ${esc(i.error || "Puede ser que no haya internet.")}</div>`
    : hay
      ? `<p class="ayuda">Tienes la <b>v${esc(i.actual)}</b> y hay una nueva:
           <b>v${esc(i.disponible)}${i.disponible_nombre ? " · " + esc(i.disponible_nombre) : ""}</b>.</p>
         ${i.novedades ? `<div class="novedades">${esc(i.novedades)}</div>` : ""}
         <div class="aviso">Se cambia solo el programa. Tus ventas, precios y
           respaldos quedan intactos. La caja se reinicia sola y vuelve en unos segundos.</div>`
      : `<p class="ayuda">Estás al día con la <b>v${esc(i.actual)}</b>${i.actual_nombre ? " · " + esc(i.actual_nombre) : ""}.</p>`;

  $("#dialogoVersion").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>${hay ? "Hay una versión nueva" : "Versión del programa"}</h2>
    ${cuerpo}
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cerrar</button>
      ${VUELTA && VUELTA.disponible && puedo("config")
        ? `<button class="btn" data-volver-version>Volver a la v${esc(VUELTA.version)}</button>` : ""}
      ${hay ? `<button class="btn btn--cobrar" id="btnActualizar" style="width:auto">Actualizar ahora</button>` : ""}
    </div>`;
  $("#capaVersion").classList.add("is-on");

  if (hay) $("#btnActualizar").onclick = async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    b.textContent = "Actualizando…";
    try {
      const r = await api("/actualizacion", { method: "POST", body: JSON.stringify({ zip: i.zip || "" }) });
      if (!r.ok) throw new Error(r.error || "no se pudo actualizar");
      if (r.sin_cambios) { avisar(r.aviso); $("#capaVersion").classList.remove("is-on"); b.disabled = false; return; }
      $("#dialogoVersion").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
        <h2>Listo</h2>
        <p class="ayuda">Se actualizaron ${r.archivos.length} archivos.
          La caja se está reiniciando: la página se recarga sola en unos segundos.</p>`;
      // El servidor se cierra y el .bat lo vuelve a levantar. Reintentamos hasta
      // que conteste, y recién ahí recargamos.
      esperarQueVuelva();
    } catch (err) {
      avisar(err.message, true);
      b.disabled = false;
      b.textContent = "Actualizar ahora";
    }
  };
}

async function esperarQueVuelva(intentos = 40) {
  for (let i = 0; i < intentos; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const r = await fetch("/api/v1/salud", { cache: "no-store" });
      if (r.ok) { location.reload(); return; }
    } catch (e) { }
  }
  $("#dialogoVersion").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Casi listo</h2>
    <p class="ayuda">La actualización quedó instalada, pero la caja no volvió sola.
      Cierra esta ventana y vuelve a abrirla con el icono
      <b>«${esc(NOMBRE_DEL_LOCAL)} - Punto de venta»</b> del escritorio.</p>`;
}

/* ---------------- turno ---------------- */
/* Lo último que se supo del turno. Lo miran la puerta y el candado. */
let TURNO = { abierto: false, turno: null };

/* ---------------- la caja cerrada tapa todo ----------------
   Desde la 2.5 no se puede usar el programa sin abrir la caja. No es rigor por
   rigor: una venta sin turno queda con `turno_id` en nulo, no entra en ningún
   cuadre, no aparece en ningún cierre, y nadie se entera hasta que el efectivo
   del cajón no calza con nada. El servidor también la rechaza; esto es para que
   no se llegue a intentar.

   La puerta tiene DOS salidas y la segunda no es un adorno: sin ella, cerrar la
   caja a las 20:00 dejaría al dueño encerrado —la puerta le pediría abrirla de
   nuevo para poder hacer cualquier cosa—. Terminar el día es cerrar la caja y
   salir de la cuenta. */
function pintarPuertaDeLaCaja(t) {
  const puerta = $("#cajaCerrada");
  if (!puerta) return;
  const nombre = $("#cajaCerradaLocal");
  if (nombre) nombre.textContent = NOMBRE_DEL_LOCAL;
  // Con el candado arriba manda el candado: primero se sabe quién está.
  const hayCandado = !$("#candado").hidden;
  // Y la puerta se corre sola mientras se cuenta el fondo. Esto NO es cosmético:
  // la puerta va en z-index 80 con fondo opaco y los diálogos en 20, así que
  // tapaba el arqueo entero. El cajero apretaba «Abrir caja», el diálogo se
  // dibujaba DETRÁS, no pasaba nada a la vista, y quedaba encerrado: la única
  // salida era salir de su cuenta, volver a marcar el PIN y llegar a la misma
  // puerta. Solo le pasaba a los locales CON usuarios creados: sin usuarios la
  // sesión es provisoria y la puerta no aparece, que es por qué no se vio antes.
  const contandoElFondo = $("#capaTurno").classList.contains("is-on");
  puerta.hidden = !SESION.entrado || SESION.provisorio || t.abierto || hayCandado
                  || contandoElFondo;
}

async function cargarTurno() {
  const t = await api("/turnos/actual");
  const chip = $("#turnoEstado");
  $(".punto").classList.toggle("off", !t.abierto);
  chip.textContent = t.abierto
    ? `Resumen de caja${t.turno.cajero ? " · " + t.turno.cajero : ""}`
    : "Abrir caja";
  chip.dataset.abierto = t.abierto ? "1" : "0";
  TURNO = t;                    // trae `abierto`, `turno` y `fondo_anterior`
  pintarPuertaDeLaCaja(t);
  // De quién es la caja, al pasar el mouse. No se apaga el chip: el MISMO chip
  // sirve para ABRIR caja, que sí puede cualquiera.
  chip.title = t.abierto && esDeOtro(t.turno) && !puedo("turno_cerrar_ajeno")
    ? `La abrió ${t.turno.abrio}: la cierra ${t.turno.abrio} o el dueño`
    : "";
  return t;
}

/* ---------------- arqueo de caja ----------------
   Se cuenta por denominación, como en la planilla que usaban antes, pero con
   dos diferencias: el total lo saca el programa (no una fórmula que alguien
   puede pisar) y lo que DEBERÍA haber lo sabe la caja, no hay que escribirlo.

   El conteo va a ciegas: el esperado aparece recién cuando aprietas "Ver si
   cuadra". Si ves el número antes, es humano acomodar el conteo para que
   calce, y ahí el arqueo deja de servir para lo único que sirve. */
let DENOMINACIONES = [20000, 10000, 5000, 2000, 1000, 500, 100, 50, 10];
const NOMBRE_MEDIO = { efectivo: "Efectivo", debito: "Débito",
                       credito: "Crédito", transferencia: "Transferencia",
                       mixto: "Pago mixto" };
let conteoActual = {};

async function cargarDenominaciones() {
  try {
    const d = await api("/turnos/denominaciones");
    if (d.denominaciones && d.denominaciones.length) DENOMINACIONES = d.denominaciones;
  } catch (e) { }
}

const totalConteo = () =>
  DENOMINACIONES.reduce((s, v) => s + v * (conteoActual[v] || 0), 0);

/* El conteo se guarda en el equipo mientras se cuenta. Si el diálogo se cierra
   por lo que sea —un roce, un corte de luz, alguien que cierra la ventana—, al
   volver a abrir está todo lo contado. Se borra recién cuando la caja cierra. */
const recordarConteo = () => {
  try { localStorage.setItem("pos.conteo", JSON.stringify(conteoActual)); } catch (e) {}
};
const recuperarConteo = () => {
  try { return JSON.parse(localStorage.getItem("pos.conteo") || "{}"); }
  catch (e) { return {}; }
};
const olvidarConteo = () => {
  try { localStorage.removeItem("pos.conteo"); } catch (e) {}
};

function arqueoHTML() {
  return `<div class="arqueo" id="arqueo">
    ${DENOMINACIONES.map((v) => `
      <div class="arqueo__fila" data-den="${v}">
        <div class="arqueo__valor">${clp(v)}<small>${v >= 1000 ? "billete" : "moneda"}</small></div>
        <div class="arqueo__cant">
          <button data-den-menos="${v}" tabindex="-1">−</button>
          <input type="text" inputmode="numeric" data-teclado="entero"
                 data-den-cant="${v}" value="" placeholder="0">
          <button data-den-mas="${v}" tabindex="-1">+</button>
        </div>
        <div class="arqueo__sub" data-den-sub="${v}">—</div>
      </div>`).join("")}
  </div>
  <div class="arqueo__total"><span>Contado en el cajón</span><b id="arqueoTotal">$0</b></div>`;
}

function pintarArqueo() {
  DENOMINACIONES.forEach((v) => {
    const n = conteoActual[v] || 0;
    const fila = document.querySelector(`[data-den="${v}"]`);
    if (!fila) return;
    fila.classList.toggle("tiene", n > 0);
    fila.querySelector(`[data-den-sub="${v}"]`).textContent = n ? clp(v * n) : "—";
    const campo = fila.querySelector(`[data-den-cant="${v}"]`);
    if (document.activeElement !== campo) campo.value = n || "";
  });
  const t = $("#arqueoTotal");
  if (t) t.textContent = clp(totalConteo());
  recordarConteo();
  const btn = $("#verCuadre");
  if (btn) btn.disabled = false;
}

/* Los eventos del arqueo viven acá para no repetirlos en apertura y cierre. */
function conectarArqueo(alCambiar) {
  const caja = $("#arqueo");
  if (!caja) return;
  caja.addEventListener("click", (e) => {
    const mas = e.target.closest("[data-den-mas]");
    const menos = e.target.closest("[data-den-menos]");
    if (!mas && !menos) return;
    const v = +(mas || menos).dataset[mas ? "denMas" : "denMenos"];
    conteoActual[v] = Math.max(0, (conteoActual[v] || 0) + (mas ? 1 : -1));
    pintarArqueo();
    if (alCambiar) alCambiar();
  });
  caja.addEventListener("input", (e) => {
    const campo = e.target.closest("[data-den-cant]");
    if (!campo) return;
    conteoActual[+campo.dataset.denCant] = soloNumeros(campo.value);
    pintarArqueo();
    if (alCambiar) alCambiar();
  });
}

async function dialogoTurno() {
  await cargarDenominaciones();
  const t = await cargarTurno();
  // Si quedó un conteo a medias de este mismo turno, se retoma.
  conteoActual = t.abierto ? recuperarConteo() : {};
  if (!t.abierto) pintarAbrirCaja();
  else pintarCerrarCaja(t.turno);
  $("#capaTurno").classList.add("is-on");
  pintarPuertaDeLaCaja(t);      // recién ahora la puerta se corre y se ve el arqueo
}

/* ---- abrir: contar el fondo que queda en el cajón ---- */
/* Lo que quedó anoche, para contar contra un número y no a ciegas. */
function pintarFondoDeAnoche() {
  const caja = $("#fondoDeAnoche");
  if (!caja) return;
  const anoche = TURNO.fondo_anterior;
  if (anoche == null) { caja.innerHTML = ""; return; }

  const llevo = totalConteo();
  const dif = llevo - anoche;
  caja.innerHTML = `
    <div class="fondo-anoche ${!llevo ? "" : dif === 0 ? "es-ok" : "es-mal"}">
      <div class="pista__linea"><span>Anoche quedaron</span><b>${clp(anoche)}</b></div>
      ${llevo ? `<div class="pista__linea pista__dif">
        <span>${dif === 0 ? "Calza exacto" : dif > 0 ? "Llevas de más" : "Te falta"}</span>
        <b>${dif === 0 ? "✓" : clp(Math.abs(dif))}</b></div>` : ""}
      ${llevo && dif !== 0 ? `<p class="ayuda" style="margin:6px 0 0;font-size:12.5px">
        Cuenta de nuevo antes de abrir. Si abres con una diferencia acá, en la
        noche va a aparecer igual y ya no vas a saber de dónde salió.</p>` : ""}
    </div>`;
}

function pintarAbrirCaja() {
  $("#dialogoTurno").className = "dialogo dialogo--ancho";
  $("#dialogoTurno").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Abrir caja</h2>
    <label class="campo"><span>¿Quién atiende?</span>
      <input id="tCajero" type="text" placeholder="Nombre" autocomplete="off"></label>
    <p class="ayuda" style="margin-bottom:10px">Cuenta la plata con la que parte el cajón.
      Si no hay fondo, déjalo todo en cero.</p>
    <div id="fondoDeAnoche"></div>
    ${arqueoHTML()}
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="tAbrir" style="width:auto">Abrir caja</button>
    </div>`;
  pintarArqueo();
  // Comparar con lo que quedó anoche, MIENTRAS se cuenta. Es el momento barato
  // de encontrar la diferencia: acá se resuelve contando de nuevo, y doce horas
  // después ya no hay cómo saber de dónde salió.
  conectarArqueo(pintarFondoDeAnoche);
  pintarFondoDeAnoche();
  setTimeout(() => $("#tCajero").focus(), 60);
}

/* ¿La abrió otra persona? Un turno SIN dueño (abierto_por_id nulo) no es de
   otro: es de nadie. Están así todos los turnos anteriores a los usuarios, los
   que se abrieron en modo provisorio y los de la carta de ejemplo. Tratarlos
   como ajenos dejaría cajas viejas imposibles de cerrar. */
const esDeOtro = (tu) => !!(tu.abierto_por_id && SESION.id && tu.abierto_por_id !== SESION.id);

/* La pantalla del cajero que no puede cerrar. Explica el porqué y ofrece la
   salida —cambiar de usuario—, porque un "no puedes" sin salida, con el local
   cerrando, no le resuelve el problema a nadie. */
function pintarCajaAjena(tu) {
  $("#dialogoTurno").className = "dialogo";
  $("#dialogoTurno").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Esta caja no es tuya</h2>
    <p class="ayuda">La abrió <b>${esc(tu.abrio || "otra persona")}</b>, con el fondo
      que contó esa mañana. El cierre es de ${esc(tu.abrio || "esa persona")}, o del dueño.</p>
    <p class="ayuda" style="margin-bottom:0">No es desconfianza: si cierra otro, el
      descuadre queda sin dueño. No habría a quién preguntarle qué pasó a las once,
      y la diferencia se la come alguien que no contó ese fondo.</p>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Entendido</button>
      <button class="btn btn--cobrar" id="cambiarParaCerrar" style="width:auto">Cambiar de usuario</button>
    </div>`;
}

/* ---- cerrar: el cajón a ciegas, todo lo demás a la vista ----
   Dos columnas: a la izquierda se cuenta, a la derecha está lo que hay que
   MIRAR mientras se cuenta —lo vendido y el comprobante de la máquina—. Antes
   la columna de la derecha aparecía recién después de apretar "Ver si cuadra",
   así que el cajero escribía el total de Transbank sin haberlo visto venir.

   Lo único tapado hasta el final es el efectivo, y no es un capricho: si el
   número que "debería haber" está en pantalla, el conteo deja de ser un conteo
   y pasa a ser una confirmación —uno suma hasta llegar a esa cifra y ahí para—.
   Lo pagado con tarjeta no está en el cajón, así que mostrarlo desde el
   principio no ensucia nada. Ver docs/CONTRATO.md. */
function pintarCerrarCaja(tu) {
  // ANTES de dibujar un solo billete. Si la caja es de otro y no la puedo
  // cerrar, se dice acá y no después: descubrirlo con el cajón ya contado
  // significa haber contado la plata entera para nada, a las diez de la noche.
  const ajena = esDeOtro(tu);
  if (ajena && !puedo("turno_cerrar_ajeno")) return pintarCajaAjena(tu);

  $("#dialogoTurno").className = "dialogo dialogo--cierre";
  $("#dialogoTurno").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Cerrar caja</h2>
    ${ajena ? `<div class="aviso-ajena">Esta caja la abrió <b>${esc(tu.abrio)}</b>.
      La estás cerrando tú, y así va a quedar escrito en el cierre y en el
      registro del mes.</div>` : ""}
    ${retirosDelTurnoHTML(tu)}
    <div class="cierre">
      <div class="cierre__col">
        <div class="cierre__paso"><b>1</b> Cuenta la plata del cajón</div>
        <p class="ayuda" style="margin:0 0 12px">Billete por billete y moneda por
          moneda. Cuando termines te muestro si cuadra.</p>
        ${arqueoHTML()}
      </div>
      <div class="cierre__col">
        <div class="cierre__paso"><b>2</b> Lo que no está en el cajón</div>
        <p class="ayuda" style="margin:0 0 12px">Esto no se cuenta: el programa ya
          lo sabe. Compáralo con el comprobante de la máquina.</p>
        <div id="resumenTurno">${resumenDelTurno(tu, true)}</div>
        ${bloqueTarjetas(tu)}
      </div>
    </div>
    <div id="zonaCuadre"></div>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="verCuadre" style="width:auto">Ver si cuadra</button>
    </div>`;
  VENTAS_DEL_TURNO = null;      // se piden de nuevo cada vez que se abre el cierre
  pintarArqueo();
  conectarTarjetas(tu);
  // Si vuelven a tocar el conteo después de ver el cuadre, se rehace.
  conectarArqueo(() => { if ($("#zonaCuadre").dataset.visto) mostrarCuadre(tu); });

  $("#verCuadre").onclick = () => mostrarCuadre(tu);
}

/* ---- sacar plata del cajón en medio del turno ----
   El dueño manda a comprar gas o pan sin cerrar la caja, y esa plata tiene que
   quedar firmada. Va acá arriba, en la misma pantalla que abre el chip de la
   caja, porque es donde se maneja el cajón; separado del cierre para que no se
   confunda "saqué plata para el pan" con "estoy cerrando el día".

   Cualquiera puede sacar —el cajero es el que está solo en la mañana— y por eso
   lo que la cuida no es un permiso: es que cada retiro dice quién fue. */
function retirosDelTurnoHTML(tu) {
  const movs = tu.retiros || [];
  const enCajon = tu.efectivo_esperado;
  return `
    <div class="retiros" id="retirosTurno">
      <div class="retiros__cab">
        <div>
          <b>¿Moviste plata del cajón?</b>
          <p class="ayuda" style="margin:2px 0 0;font-size:12.5px">Sacar para ir a comprar,
            o meter cambio, sin cerrar la caja. Queda anotado quién y para qué.</p>
        </div>
        <div class="retiros__botones">
          <button class="btn btn--fantasma btn--chico" data-sacar-plata>Sacar plata</button>
          <button class="btn btn--fantasma btn--chico" data-meter-plata>Meter plata</button>
        </div>
      </div>
      <div id="sacarPlataForm" hidden></div>
      ${movs.length ? `
        <div class="retiros__lista">
          ${movs.map((r) => {
            const es = r.tipo === "ingreso";
            return `
            <div class="retiros__fila ${r.anulado ? "es-anulado" : ""}">
              <div class="retiros__que">
                <b>${es ? "+" : "−"}${clp(r.monto)}</b> · ${esc(r.motivo)}
                <small>${es ? "entró" : "salió"} · ${esc(r.hora)}${
                  r.hecho_por ? " · " + esc(r.hecho_por) : ""}${
                  r.anulado ? " · anulado" + (r.anulado_por ? " por " + esc(r.anulado_por) : "") : ""}</small>
              </div>
              ${r.anulado ? "" : `<button class="btn btn--fantasma btn--chico"
                data-anular-retiro="${r.id}">Anular</button>`}
            </div>`; }).join("")}
        </div>` : ""}
      <div class="retiros__total">En el cajón hay ahora: <b>${clp(enCajon)}</b></div>
    </div>`;
}

/* El formulario chico se abre dentro del mismo panel: dos campos y confirmar.
   Sirve para sacar y para meter; cambia el texto y, al sacar, no deja pasar de
   lo que hay. No abre otra ventana porque se hace con el cliente esperando y una
   capa arriba de otra en una pantalla chica es justo lo que enreda. */
function abrirFormRetiro(tu, tipo = "retiro") {
  const caja = $("#sacarPlataForm");
  if (!caja) return;
  const esInar = tipo === "ingreso";
  const hay = tu.efectivo_esperado;
  caja.hidden = false;
  caja.innerHTML = `
    <div class="retiros__form">
      <label class="campo"><span>${esInar ? "¿Cuánto metes?" : "¿Cuánto sacas?"}</span>
        <input id="rMonto" type="text" inputmode="numeric" placeholder="0" autocomplete="off"></label>
      <label class="campo"><span>¿Para qué?</span>
        <input id="rMotivo" type="text"
               placeholder="${esInar ? "Ej: traje cambio" : "Ej: gas, pan"}" autocomplete="off"></label>
      <div id="rAviso" class="ayuda" style="margin:-4px 0 10px;font-size:12.5px">${
        esInar ? "" : `En el cajón hay <b>${clp(hay)}</b>.`}</div>
      <div class="retiros__form-pie">
        <button class="btn btn--fantasma" data-cerrar-form-retiro>Cancelar</button>
        <button class="btn btn--cobrar" id="rConfirmar" style="width:auto">${
          esInar ? "Meter al cajón" : "Sacar del cajón"}</button>
      </div>
    </div>`;
  const monto = $("#rMonto");
  const aviso = $("#rAviso");
  const boton = $("#rConfirmar");
  const revisar = () => {
    const m = soloNumeros(monto.value);
    if (esInar) return;
    // Sacar plata que no está es imposible de verdad: se bloquea el botón y se
    // dice cuánto hay. No es como el stock, donde la repisa puede tener más.
    if (m > hay) {
      aviso.innerHTML = `Solo hay <b>${clp(hay)}</b> en el cajón: no puedes sacar más.`;
      boton.disabled = true;
    } else {
      aviso.innerHTML = `En el cajón hay <b>${clp(hay)}</b>.`;
      boton.disabled = false;
    }
  };
  monto.addEventListener("input", revisar);
  setTimeout(() => monto.focus(), 40);
  boton.onclick = () => {
    const m = soloNumeros(monto.value);
    const motivo = ($("#rMotivo").value || "").trim();
    if (!m) return avisar(esInar ? "Escribe cuánto metes" : "Escribe cuánto sacas", true);
    if (!motivo) return avisar("Escribe para qué", true);
    if (!esInar && m > hay) return avisar(`Solo hay ${clp(hay)} en el cajón`, true);
    api(`/turnos/${esInar ? "ingreso" : "retiro"}`, { method: "POST",
      body: JSON.stringify({ monto: m, motivo }) })
      .then((t) => { avisar(esInar ? `Metiste ${clp(m)} al cajón` : `Sacaste ${clp(m)} del cajón`);
        refrescarCierre(t); })
      .catch((e) => avisar(e.message, true));
  };
}

function anularRetiro(id) {
  if (!confirm("¿Anular este movimiento? El cajón vuelve a como estaba antes.")) return;
  api(`/turnos/retiro/${id}/anular`, { method: "POST" })
    .then((t) => { avisar("Movimiento anulado"); refrescarCierre(t); })
    .catch((e) => avisar(e.message, true));
}

/* Después de sacar o anular, se redibuja el cierre con el turno nuevo —el
   efectivo esperado ya viene con el retiro restado— sin perder lo que se llevaba
   contado: conteoActual vive en memoria y pintarArqueo lo repinta. */
function refrescarCierre(turnoNuevo) {
  if (turnoNuevo && turnoNuevo.id) { TURNO = { abierto: true, turno: turnoNuevo,
    fondo_anterior: TURNO.fondo_anterior }; }
  pintarCerrarCaja(TURNO.turno);
}

const propinasPorPagar = (tu) => (tu.propinas && tu.propinas.tarjeta) || 0;

function mostrarCuadre(tu) {
  const contado = totalConteo();
  // Lo que se pagó de propina en efectivo salió del cajón: el cajón tiene que
  // tener menos, y no es un faltante.
  const pagadas = $("#tPropinasPagadas")
    ? Math.min(soloNumeros($("#tPropinasPagadas").value), propinasPorPagar(tu)) : 0;
  const esperado = tu.efectivo_esperado - pagadas;
  const dif = contado - esperado;
  const ok = dif === 0;
  const zona = $("#zonaCuadre");
  zona.dataset.visto = "1";

  // Esto se vuelve a dibujar con CADA corrección del conteo, así que lo que la
  // persona ya escribió se rescata antes de rehacerlo. La nota se perdía en
  // cada tecla del arqueo.
  const fondoPrevio = $("#tFondo") ? soloNumeros($("#tFondo").value) : tu.monto_inicial;
  const notaPrevia = $("#tNota") ? $("#tNota").value : "";
  const propPrevia = $("#tPropinasPagadas") ? $("#tPropinasPagadas").value : "";

  // Ya contó: destapar el efectivo ya no arruina nada.
  $("#resumenTurno").innerHTML = resumenDelTurno(tu);

  zona.innerHTML = `
    <div class="cierre__paso"><b>3</b> Cómo quedó la caja</div>
    <div class="cierre">
      <div class="cierre__col">
        <div class="cuadre ${ok ? "cuadre--ok" : "cuadre--mal"}">
          <div class="cuadre__linea"><span>Fondo con el que abrió</span><span>${clp(tu.monto_inicial)}</span></div>
          <div class="cuadre__linea"><span>Ventas en efectivo</span><span>${clp(tu.ventas_efectivo)}</span></div>
          ${tu.retiros_total ? `<div class="cuadre__linea"><span>Lo que sacaste del cajón</span>
            <span>−${clp(tu.retiros_total)}</span></div>` : ""}
          ${tu.ingresos_total ? `<div class="cuadre__linea"><span>Lo que metiste al cajón</span>
            <span>+${clp(tu.ingresos_total)}</span></div>` : ""}
          ${pagadas ? `<div class="cuadre__linea"><span>Propinas que pagaste en efectivo</span>
            <span>−${clp(pagadas)}</span></div>` : ""}
          <div class="cuadre__linea"><span>Debería haber</span><span>${clp(esperado)}</span></div>
          <div class="cuadre__linea"><span>Contaste</span><span>${clp(contado)}</span></div>
          <div class="cuadre__linea cuadre__dif">
            <span>${ok ? "Cuadra exacto" : dif > 0 ? "Sobra" : "Falta"}</span>
            <span>${ok ? "✓" : clp(Math.abs(dif))}</span>
          </div>
        </div>
        ${bloquePropinas(tu)}
        <div id="pistaEfectivo"></div>
      </div>
      <div class="cierre__col">
        ${propinasPorPagar(tu) ? `
        <label class="campo"><span>¿Cuánta propina de tarjeta pagaste en efectivo?</span>
          <input id="tPropinasPagadas" type="text" inputmode="numeric"
                 value="${esc(propPrevia || tu.propinas_pagadas || "")}"
                 placeholder="0 · la caja anotó ${clp(propinasPorPagar(tu))} de propina en tarjeta"></label>
        <p class="ayuda" style="margin:-6px 0 12px;font-size:12.5px">Si le pasaste al
          equipo su propina sacándola del cajón, ponla acá: esa plata salió del
          cajón y el banco todavía no la deposita, así que si no la anotas
          aparece como si faltara.</p>` : ""}
        <label class="campo"><span>¿Cuánta propina vas a sacar AHORA del cajón?</span>
          <input id="tPropinaSacar" type="text" inputmode="numeric" placeholder="0"></label>
        <p class="ayuda" style="margin:-6px 0 12px;font-size:12.5px">Solo para decirte qué
          billetes separar, del dinero que acabas de contar. <b>Si ya la sacaste antes de
          contar, déjalo en cero</b>: en ese caso el cajón ya no la tiene y sacarla de nuevo
          sería pagarla dos veces. El número de arriba es otra cosa: ése es para el cuadre.</p>
        <label class="campo"><span>¿Cuánto dejas de fondo para mañana?</span>
          <input id="tFondo" type="text" inputmode="numeric" value="${fondoPrevio || ""}" placeholder="0"></label>
        <p class="ayuda" style="margin:-6px 0 10px;font-size:12.5px">Es plata en
          <b>efectivo</b>, la que queda en el cajón. La tarjeta y las transferencias
          no entran acá: ésas ya están en el banco.</p>
        <div class="medios-turno" id="tRetiro"></div>
        <div class="medios-turno" id="tPlanCierre"></div>
        <label class="campo"><span>Nota (opcional)</span>
          <input id="tNota" type="text" value="${esc(notaPrevia)}"
                 placeholder="Ej: le di vuelto de más a un cliente"></label>
      </div>
    </div>`;

  /* Qué billetes y monedas apartar, no solo cuánto. Es lo que evita el recuento de
     las once de la noche: se cuenta el cajón una vez y la caja dice qué separar.

     El reparto lo hace el servidor (core/fondo.py, con sus pruebas) y NO se calcula
     acá: dos implementaciones del mismo cuadre terminan dando números distintos, y en
     el cierre eso es exactamente lo que no puede pasar. */
  let pidiendoPlan = null;
  // Cada cálculo lleva número. Al escribir se disparan varios y no vuelven en orden: sin
  // esto, la respuesta del fondo viejo puede pisar a la del nuevo y el cajero separaría una
  // cantidad distinta de la que confirma.
  let ultimoPlan = 0;
  const planDelCierre = (fondo) => {
    const zonaPlan = $("#tPlanCierre");
    if (!zonaPlan) return;
    clearTimeout(pidiendoPlan);
    const mio = ++ultimoPlan;
    // La propina del plan es la que se va a sacar AHORA, del dinero recién contado. NO se
    // puede usar tPropinasPagadas: ésa ya salió del cajón —el cuadre la descuenta del
    // efectivo esperado— así que decir de nuevo qué billetes sacar haría pagarla dos veces.
    const propina = soloNumeros(($("#tPropinaSacar") || {}).value || 0);
    if (!fondo && !propina) { zonaPlan.innerHTML = ""; return; }
    // Se escribe dígito a dígito: solo se le pregunta al servidor cuando el dedo para.
    pidiendoPlan = setTimeout(async () => {
      let plan;
      try {
        plan = await api("/turnos/plan-cierre", {
          method: "POST",
          body: JSON.stringify({ conteo: conteoActual, propina, fondo }),
        });
      } catch (e) { if (mio === ultimoPlan) zonaPlan.innerHTML = ""; return; }
      if (mio !== ultimoPlan) return;        // llegó tarde: ya hay otro cálculo más nuevo
      const pila = (titulo, d, aviso) => {
        const piezas = Object.keys(d.detalle || {}).sort((a, b) => b - a)
          .map((v) => `${d.detalle[v]} de ${clp(v)}`).join(" · ");
        if (!piezas) return "";
        return `<div style="margin-top:8px">
          <b>${titulo}: ${clp(d.total)}</b><div>${piezas}</div>
          ${d.exacto ? "" : `<div class="ayuda" style="font-size:12px">${aviso}</div>`}</div>`;
      };
      zonaPlan.innerHTML =
        pila("Saca para la propina", plan.propina,
             "Con lo que hay en el cajón no se puede juntar esa propina justa; esto es lo "
             + "más cerca que se llega.")
        + pila("Deja en la caja", plan.fondo,
               `Con lo que hay en el cajón no se puede dejar justo eso. Lo más cerca es
                <b>${clp(plan.fondo.total)}</b>: si vas a separar esto,
                <b>cambia el fondo a esa cifra</b> antes de cerrar, o el cierre va a quedar
                anotando un fondo distinto del que dejaste.`)
        + pila("Va al sobre", { detalle: plan.sobre.detalle, total: plan.sobre.total,
                                exacto: true }, "");
    }, 250);
  };

  const pintarRetiro = () => {
    const escrito = soloNumeros($("#tFondo").value);
    const fondo = Math.min(escrito, contado);
    // Si pide dejar más de lo que contó, el fondo se recorta a lo que hay. Antes
    // el número se cambiaba solo, en silencio, y el cajero no entendía por qué;
    // ahora se dice, porque un recorte callado parece un error del programa.
    const recorte = escrito > contado
      ? `<div class="ayuda" style="margin-top:4px;font-size:12px">Contaste ${clp(contado)}
         en el cajón, así que no puedes dejar más que eso de fondo.</div>` : "";
    $("#tRetiro").innerHTML =
      `Te llevas del cajón (efectivo): <b>${clp(contado - fondo)}</b>${recorte}`;
    planDelCierre(fondo);
  };
  $("#tFondo").addEventListener("input", pintarRetiro);
  const campoSacar = $("#tPropinaSacar");
  if (campoSacar) campoSacar.addEventListener("input", pintarRetiro);
  pintarRetiro();
  const campoProp = $("#tPropinasPagadas");
  if (campoProp) {
    campoProp.addEventListener("input", () => {
      // mostrarCuadre rehace esta zona entera, así que hay que devolverle el
      // foco y el cursor: si no, escribir "1500" pierde el campo en el "1".
      const donde = campoProp.selectionStart;
      mostrarCuadre(tu);
      const nuevo = $("#tPropinasPagadas");
      if (nuevo) { nuevo.focus(); try { nuevo.setSelectionRange(donde, donde); } catch (e) {} }
    });
  }
  if (dif !== 0) buscarElDescuadre(tu, dif);

  const pie = document.querySelector("#dialogoTurno .dialogo__pie");
  pie.innerHTML = `
    <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
    <button class="btn btn--cobrar" id="tCerrar" style="width:auto">Cerrar caja</button>`;
  zona.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------------- quién está en la caja ----------------
   El candado es una CAPA que tapa todo, no una vista. Si fuera vista, escribir
   #/caja en la barra de direcciones la saltaría y sería un candado dibujado.
   El servidor lo respalda igual: sin galleta de sesión, la API contesta 401.

   Mientras no haya ningún usuario creado, la caja funciona sin candado. Es a
   propósito: la caja del local ya está vendiendo con una base sin usuarios, y
   una actualización que exija login dejaría al local sin poder cobrar el lunes
   en la mañana. Al crear el primer usuario, la puerta se cierra sola. */
let SESION = { entrado: false, provisorio: true, permisos: [] };
let CANDADO_USUARIOS = [];

const puedo = (permiso) => SESION.permisos.includes(permiso);

async function cargarSesion() {
  try {
    SESION = await api("/sesion");
  } catch (e) {
    SESION = { entrado: false, provisorio: false, permisos: [] };
  }
  pintarQuien();
  if (SESION.entrado) {
    // Los ajustes pueden haber cambiado mientras la caja estaba bloqueada.
    await cargarAjustes();
    pintarAjustes();
  }
  return SESION;
}

function pintarQuien() {
  const configurar = $("#btnConfigurar");
  if (configurar) configurar.textContent = puedo("config") ? "Configurar" : "Ayuda";
  $("#btnVarios").hidden = !puedo("cobrar_varios");
  const chip = $("#quienEsta");
  const equipo = $("#verEquipo");
  // Sin nadie registrado no hay equipo que administrar, y el candado tapa todo
  // igual. Va ANTES del return de abajo para que no quede prendido de adorno.
  if (equipo) equipo.hidden = SESION.provisorio || !SESION.nombre;
  if (SESION.provisorio || !SESION.nombre) { chip.hidden = true; return; }
  chip.hidden = false;
  $("#quienNombre").textContent = SESION.nombre;
  chip.title = SESION.rol_nombre + " · tocar para cambiar de usuario";
  // Los botones que la persona no puede usar no se esconden: se apagan. Que se
  // vean explica por qué existe el rol; esconderlos hace creer que el programa
  // no lo hace.
  $$("[data-permiso]").forEach((b) => {
    const falta = !puedo(b.dataset.permiso);
    b.disabled = falta;
    b.title = falta ? "Esto lo hace el dueño" : "";
  });
}

/* ---- la pantalla de entrada ---- */
let tCandado = null;

async function mostrarCandado(motivo) {
  clearTimeout(tCandado);
  // La caja se TAPA de inmediato; las caras llegan cuando contesta el servidor.
  // Esperar la respuesta para tapar era justo el hueco por donde se quedaba
  // pegada: si el servidor no contestaba, no se tapaba nunca.
  if ($("#candado").hidden) {
    $("#candadoCaja").innerHTML = `<h1>${esc(NOMBRE_DEL_LOCAL)}</h1>
      <p>${motivo || "¿Quién está en la caja?"}</p>`;
    $("#candado").hidden = false;
    const puerta = $("#cajaCerrada");
    if (puerta) puerta.hidden = true;
  }
  let info;
  try {
    info = await api("/candado", { espera: 6000 });
  } catch (e) {
    return candadoSinConexion(motivo);
  }
  CANDADO_USUARIOS = info.usuarios;
  if (info.primer_arranque) return pintarPrimerUsuario();

  $("#candadoCaja").innerHTML = `
    <h1>${esc(NOMBRE_DEL_LOCAL)}</h1>
    <p>${motivo || "¿Quién está en la caja?"}</p>
    <div class="candado__gente">
      ${info.usuarios.map((u) => `
        <button class="cara" data-entrar="${u.id}" style="--c:${u.color || "#C9552B"}">
          <span class="cara__ini">${esc((u.nombre[0] || "?").toUpperCase())}</span>
          <b>${esc(u.nombre)}</b>
        </button>`).join("")}
    </div>
    <input id="candadoPin" type="password" inputmode="numeric" data-teclado="pin"
           autocomplete="off" hidden>`;
  $("#candado").hidden = false;
  const puerta = $("#cajaCerrada");
  if (puerta) puerta.hidden = true;
}

function pintarPrimerUsuario() {
  // El nombre de fábrica no se sugiere: una cafetería nueva que deja «Kofe»
  // escrito sale así en el comprobante y en sus televisores.
  const sugerido = NOMBRE_DEL_LOCAL && NOMBRE_DEL_LOCAL !== "Kofe" ? NOMBRE_DEL_LOCAL : "";
  $("#candadoCaja").innerHTML = `
    <h1>Una caja nueva</h1>
    <p>Todavía no hay nadie registrado. Primero los datos del local; después el
       dueño, que va a poder crear a los demás.</p>
    <label class="campo"><span>¿Cómo se llama el local?</span>
      <input id="primerLocal" type="text" maxlength="40" value="${esc(sugerido)}"
             placeholder="Como lo conocen los clientes" autocomplete="off"></label>
    <div class="dos-campos">
      <label class="campo"><span>RUT del local (si lo tienes)</span>
        <input id="primerRut" type="text" maxlength="14" placeholder="12.345.678-9" autocomplete="off"></label>
      <label class="campo"><span>Dirección (si quieres)</span>
        <input id="primerDireccion" type="text" maxlength="80" autocomplete="off"></label>
    </div>
    <label class="campo"><span>¿Cómo te llamas?</span>
      <input id="primerNombre" type="text" placeholder="Tu nombre" autocomplete="off"></label>
    <label class="campo"><span>Inventa un PIN de 4 números</span>
      <input id="primerPin" type="password" inputmode="numeric" data-teclado="entero"
             placeholder="••••" autocomplete="off"></label>
    <button class="btn btn--cobrar" id="crearPrimero">Crear el local y mi usuario</button>
    <p class="candado__nota">El RUT y la dirección salen en el comprobante. Todo se cambia
      después en Ayuda → Ajustes.</p>`;
  $("#candado").hidden = false;
  setTimeout(() => $(sugerido ? "#primerNombre" : "#primerLocal").focus(), 80);
}

async function pedirPin(usuarioId) {
  const u = CANDADO_USUARIOS.find((x) => x.id === usuarioId);
  if (!u) return;
  // Con teclado de verdad no se dibuja uno: se pide el PIN escrito. El teclado
  // en pantalla existe para cuando llegue la pantalla táctil (ver ajustes).
  if (window.Teclado && Teclado.seUsa) {
    Teclado.abrir($("#candadoPin"), {
      modo: "pin",
      titulo: "PIN de " + u.nombre,
      alConfirmar: (pin) => entrarComo(u.id, pin),
    });
    return;
  }
  pedirPinEscrito(u);
}

/* El PIN escrito, cuando no hay teclado en pantalla.

   Se reemplaza la pantalla del candado por una sola cosa: el nombre de quien
   entra y un campo con el foco puesto. Enter confirma. Nada de tocar nada. */
function pedirPinEscrito(u) {
  $("#candadoCaja").innerHTML = `
    <h1>${esc(NOMBRE_DEL_LOCAL)}</h1>
    <div class="cara cara--sola" style="--c:${u.color || "#C9552B"}">
      <span class="cara__ini">${esc((u.nombre[0] || "?").toUpperCase())}</span>
      <b>${esc(u.nombre)}</b>
    </div>
    <label class="campo" style="max-width:280px;margin:22px auto 0;text-align:left">
      <span>Tu PIN</span>
      <input id="candadoPin" type="password" inputmode="numeric" maxlength="8"
             autocomplete="off" placeholder="••••"
             style="text-align:center;letter-spacing:.5em;font-size:26px"></label>
    <p class="candado__nota">Escríbelo y aprieta Enter.
      <button class="btn btn--fantasma btn--chico" data-otro-usuario
              style="margin-left:8px">Es otra persona</button></p>`;

  const campo = $("#candadoPin");
  setTimeout(() => campo.focus(), 60);
  campo.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const pin = (campo.value || "").replace(/\D/g, "");
    if (pin.length >= 4) entrarComo(u.id, pin);
  });
}

async function entrarComo(usuarioId, pin) {
  let r;
  try {
    r = await api("/sesion/entrar", {
      method: "POST", body: JSON.stringify({ usuario_id: usuarioId, pin }), espera: 10000 });
  } catch (e) {
    // Un PIN malo no puede sacar de la pantalla: se sacude y se vuelve a pedir.
    $("#candadoCaja").classList.add("candado--mal");
    setTimeout(() => $("#candadoCaja").classList.remove("candado--mal"), 420);
    avisar(e.message, true);
    setTimeout(() => pedirPin(usuarioId), 450);
    return;
  }
  // Ya entró. Si lo que sigue falla, NO es un PIN malo: antes caía en el mismo
  // catch y volvía a pedir el PIN sobre un candado ya escondido.
  $("#candado").hidden = true;
  try {
    await cargarSesion();
    await cargarTurno();          // la puerta de la caja depende de esto
  } catch (e) { avisar(e.message, true); }
  avisar("Hola, " + r.nombre);
  reiniciarInactividad();
}

async function crearPrimerUsuario() {
  const nombreLocal = ($("#primerLocal").value || "").trim();
  const rut = ($("#primerRut").value || "").trim();
  const direccion = ($("#primerDireccion").value || "").trim();
  const nombre = ($("#primerNombre").value || "").trim();
  const pin = ($("#primerPin").value || "").replace(/\D/g, "");
  if (!nombreLocal) return avisar("Escribe el nombre del local", true);
  if (!nombre) return avisar("Escribe tu nombre", true);
  if (pin.length < 4) return avisar("El PIN son 4 números", true);
  try {
    // El ORDEN importa. Mientras no hay nadie registrado, la caja deja hacer
    // todo (el dueño provisorio); apenas existe el primer usuario esa puerta se
    // cierra. Los datos del local y el PIN de red van ANTES, o quedarían sin
    // poder guardarse hasta que el dueño entre.
    await api("/local", { method: "PUT", body: JSON.stringify({ nombre: nombreLocal, rut, direccion }) });
    let pinRed = null;
    try { pinRed = (await api("/red/pin", { method: "POST", body: "{}" })).pin; }
    catch (e) { /* lo fijó la instalación: se queda el que está */ }
    const u = await api("/usuarios", { method: "POST",
      body: JSON.stringify({ nombre, pin, rol: "dueno" }) });
    ponerNombreDelLocal(nombreLocal);
    if (pinRed) return mostrarPinDeRed(pinRed, () => entrarComo(u.id, pin));
    await entrarComo(u.id, pin);
  } catch (e) { avisar(e.message, true); }
}

function ponerNombreDelLocal(nombre) {
  NOMBRE_DEL_LOCAL = nombre;
  $("#nombreLocal").textContent = nombre;
  document.title = "Caja · " + nombre;
}

/* El PIN de red se muestra una vez, al crear el local, en grande. Es el que
   van a pedir los tablets y los otros computadores la primera vez. Hasta la
   2.18 era «2468» en todas las cajas; ahora cada local tiene el suyo. */
function mostrarPinDeRed(pin, seguir) {
  $("#candadoCaja").innerHTML = `
    <h1>${esc(NOMBRE_DEL_LOCAL)}</h1>
    <p>Listo. Anota el <b>PIN de red</b> de esta caja: lo piden los tablets y los
       otros computadores del local la primera vez que la abren.</p>
    <div class="pin-red pin-red--grande">${esc(pin)}</div>
    <p class="candado__nota">Es distinto de tu PIN, y de cualquier otra caja. Lo vuelves
      a ver cuando quieras en Ayuda → Ajustes.</p>
    <button class="btn btn--cobrar" id="pinRedVisto">Anotado, entrar</button>`;
  $("#pinRedVisto").onclick = seguir;
}

/* ---------------- el equipo ----------------
   La API de usuarios existe desde la 1.2 (crear, editar, sacar), pero la
   pantalla para usarla nunca se construyó: el dueño podía crearse a sí mismo en
   el primer arranque y a nadie más. En el local quedó una sola cuenta.

   Sacar a alguien NO lo borra: sus ventas y sus turnos tienen que seguir
   cuadrando. Queda inactivo y desaparece del candado. */
let EQUIPO = [];
let PERMISOS_EQUIPO = { catalogo: [], roles: {} };

async function dialogoEquipo() {
  try {
    [EQUIPO, PERMISOS_EQUIPO] = await Promise.all([api("/usuarios"), api("/usuarios/permisos")]);
  }
  catch (e) { return avisar(e.message, true); }

  $("#dialogoEquipo").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Quiénes entran a la caja</h2>
    <p class="ayuda" style="margin-bottom:14px">Por su rol, el <b>dueño</b> puede todo. El
      <b>cajero</b> vende, cobra y cuadra su caja, pero no cambia precios ni
      corrige ventas de días pasados. Al editar puedes elegir los permisos de cada persona.</p>
    <div class="equipo">
      ${EQUIPO.map((u) => `
        <button class="equipo__fila ${u.activo ? "" : "es-baja"}" data-editar-usuario="${u.id}">
          <span class="equipo__ini" style="--c:${u.color || "#C9552B"}">${esc((u.nombre[0] || "?").toUpperCase())}</span>
          <span class="equipo__quien">
            <b>${esc(u.nombre)}</b>
            <small>${u.activo ? esc(u.rol_nombre) : "ya no entra a la caja"}</small>
          </span>
          <span class="equipo__ir">Editar</span>
        </button>`).join("")}
    </div>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cerrar</button>
      <button class="btn btn--cobrar" data-editar-usuario="nuevo" style="width:auto">Agregar a alguien</button>
    </div>`;
  $("#capaEquipo").classList.add("is-on");
}

function formUsuario(id) {
  const u = EQUIPO.find((x) => x.id === id) || { nombre: "", rol: "cajero", activo: true };
  const nuevo = !u.id;

  $("#dialogoEquipo").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>${nuevo ? "Agregar a alguien" : esc(u.nombre)}</h2>
    <label class="campo"><span>Nombre</span>
      <input id="uNombre" type="text" value="${esc(u.nombre)}"
             placeholder="Cómo se llama" autocomplete="off"></label>
    <label class="campo"><span>${nuevo ? "Invéntale un PIN de 4 números (que no empiece en 0)"
      : "PIN nuevo (déjalo vacío y le queda el que tenía)"}</span>
      <input id="uPin" type="password" inputmode="numeric" data-teclado="entero"
             placeholder="••••" autocomplete="off"></label>
    <div class="campo"><span>¿Qué puede hacer?</span>
      <div class="medios" id="uRol">
        <button class="medio ${u.rol === "cajero" ? "is-on" : ""}" data-rol="cajero">Cajero</button>
        <button class="medio ${u.rol === "dueno" ? "is-on" : ""}" data-rol="dueno">Dueño</button>
      </div>
    </div>
    <fieldset class="permisos-persona">
      <legend>Permisos de esta persona</legend>
      <label class="marca">
        <input id="uHeredar" type="checkbox" role="switch" ${u.permisos ? "" : "checked"}
               aria-controls="uPermisos"> Usar los permisos de su rol
      </label>
      <button type="button" class="btn btn--fantasma" id="uSoloVender">Que solo venda</button>
      <p class="ayuda">Abre la caja, vende y cierra su caja.</p>
      <div id="uPermisos" ${u.permisos ? "" : "hidden"}>
        ${PERMISOS_EQUIPO.catalogo.map((p) => `
          <label class="marca">
            <input type="checkbox" data-permiso-persona="${esc(p.clave)}"
              ${(u.permisos ? u.permisos.split(",").map((v) => v.trim()) : PERMISOS_EQUIPO.roles[u.rol] || []).includes(p.clave) ? "checked" : ""}>
            ${esc(p.nombre)}
          </label>`).join("")}
        <p class="ayuda">Marca al menos un permiso. Para impedir que entre, usa «Sacar de la caja».</p>
      </div>
      ${u.id === SESION.id ? `<p class="ayuda">No puedes quitarte «Crear y editar personas»: lo necesitas para administrar los permisos del equipo.</p>` : ""}
    </fieldset>
    ${nuevo ? "" : `<p class="ayuda">${u.activo
      ? "Si lo sacas de la caja deja de aparecer en la pantalla de entrada, pero sus ventas y sus turnos se conservan."
      : "Ahora mismo no aparece en la pantalla de entrada."}</p>`}
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-equipo-volver>Volver</button>
      ${nuevo ? "" : (u.activo
        ? `<button class="btn btn--fantasma" data-sacar-usuario="${u.id}">Sacar de la caja</button>`
        : `<button class="btn btn--fantasma" data-revivir-usuario="${u.id}">Dejarlo entrar de nuevo</button>`)}
      <button class="btn btn--cobrar" data-guardar-usuario="${u.id || 0}" style="width:auto">Guardar</button>
    </div>`;
  $("#uHeredar").addEventListener("change", () => {
    marcarPermisosPersona(PERMISOS_EQUIPO.roles[$("#uRol .is-on").dataset.rol] || []);
    $("#uPermisos").hidden = $("#uHeredar").checked;
  });
  $("#uSoloVender").addEventListener("click", () => {
    $("#uHeredar").checked = false;
    $("#uPermisos").hidden = false;
    marcarPermisosPersona(["vender", "turno_abrir", "turno_cerrar"]);
  });
  setTimeout(() => $("#uNombre").focus(), 60);
}

function marcarPermisosPersona(claves) {
  $$("[data-permiso-persona]").forEach((c) => { c.checked = claves.includes(c.dataset.permisoPersona); });
}

async function guardarUsuario(id) {
  const nombre = ($("#uNombre").value || "").trim();
  const pin = ($("#uPin").value || "").replace(/\D/g, "");
  const elegido = $("#uRol .is-on");
  const previo = EQUIPO.find((x) => x.id === id);

  if (!nombre) return avisar("Escribe el nombre", true);
  if (!id && pin.length < 4) return avisar("Ponle un PIN de 4 números", true);
  if (pin && pin.length < 4) return avisar("El PIN son 4 números", true);
  const rol = elegido ? elegido.dataset.rol : "cajero";
  const heredar = $("#uHeredar").checked;
  const seleccion = $$("[data-permiso-persona]:checked").map((c) => c.dataset.permisoPersona);
  if (!heredar && !seleccion.length)
    return avisar("Marca al menos un permiso o activa «Usar los permisos de su rol».", true);
  const efectivos = heredar ? PERMISOS_EQUIPO.roles[rol] || [] : seleccion;
  if (id === SESION.id && !efectivos.includes("usuarios"))
    return avisar("No puedes quitarte «Crear y editar personas»: lo necesitas para administrar los permisos del equipo.", true);

  const cuerpo = {
    nombre,
    rol,
    permisos: heredar ? "" : seleccion.join(","),
    // Guardar no puede revivir a alguien que sacaron: para eso está su botón.
    activo: previo ? previo.activo : true,
    color: previo ? previo.color : "",
    orden: previo ? previo.orden : 0,
  };
  if (pin) cuerpo.pin = pin;

  try {
    await api(id ? `/usuarios/${id}` : "/usuarios",
      { method: id ? "PUT" : "POST", body: JSON.stringify(cuerpo) });
    if (id === SESION.id) await cargarSesion();
    avisar(id ? "Guardado" : `${nombre} ya puede entrar a la caja`);
    dialogoEquipo();
  } catch (e) { avisar(e.message, true); }
}

async function sacarUsuario(id) {
  const u = EQUIPO.find((x) => x.id === id);
  if (!confirm(`¿Sacar a ${u ? u.nombre : "esta persona"} de la caja? `
             + "Deja de aparecer en la pantalla de entrada, pero sus ventas y "
             + "sus turnos se conservan.")) return;
  try {
    const r = await api(`/usuarios/${id}`, { method: "DELETE" });
    avisar(r.aviso || "Listo");
    dialogoEquipo();
  } catch (e) { avisar(e.message, true); }
}

async function revivirUsuario(id) {
  const u = EQUIPO.find((x) => x.id === id);
  if (!u) return;
  try {
    await api(`/usuarios/${id}`, { method: "PUT", body: JSON.stringify({
      nombre: u.nombre, rol: u.rol, activo: true, color: u.color || "", orden: u.orden || 0 }) });
    avisar(`${u.nombre} vuelve a entrar a la caja`);
    dialogoEquipo();
  } catch (e) { avisar(e.message, true); }
}

/* ¿Puedo irme? Solo si no dejo MI caja abierta.

   La condición es sobre la caja PROPIA y no sobre cualquier caja abierta, y eso
   evita un encierro: si la abrió Javi y está Ana en pantalla, Ana no puede
   cerrarla —esa es la regla de la 2.0— así que si tampoco pudiera cambiar de
   usuario, no habría forma de que Javi volviera a entrar a cerrar la suya. */
function puedoIrme() {
  if (!TURNO.abierto || !TURNO.turno) return true;
  return esDeOtro(TURNO.turno);
}

async function salirDeLaCaja(por) {
  const motivo = por === "bloqueo" ? "La caja se bloqueó sola. ¿Quién sigue?"
                                   : "¿Quién está en la caja?";
  // El candado va PRIMERO, sin esperar al servidor. Antes se dibujaba recién
  // cuando el servidor contestaba, y si no contestaba —o contestaba con error—
  // la caja quedaba a la vista, sin sesión y sin candado: no dejaba vender y no
  // había por dónde volver a entrar. Así "se quedaba pegada y había que
  // cerrarla", que es como lo contó el local.
  SESION = { entrado: false, provisorio: false, permisos: [] };
  pintarQuien();
  const candado = mostrarCandado(motivo);
  try {
    await api("/sesion/salir", { method: "POST", body: JSON.stringify({ por }), espera: 6000 });
  } catch (e) { /* se ordena solo cuando entre el siguiente */ }
  await cargarSesion();
  await candado;
}

/* El candado cuando el servidor no contesta. Igual TAPA la caja —una caja sin
   sesión a la vista parece que anda y no hace nada— y se reintenta sola. */
function candadoSinConexion(motivo) {
  $("#candadoCaja").innerHTML = `
    <h1>${esc(NOMBRE_DEL_LOCAL)}</h1>
    <p>${motivo || "¿Quién está en la caja?"}</p>
    <p class="candado__nota">La caja no está respondiendo. Se vuelve a intentar sola;
      si sigue así, cierra el programa y ábrelo de nuevo.</p>
    <button class="btn btn--cobrar" data-reintentar-candado>Reintentar ahora</button>`;
  $("#candado").hidden = false;
  const puerta = $("#cajaCerrada");
  if (puerta) puerta.hidden = true;
  clearTimeout(tCandado);
  tCandado = setTimeout(() => mostrarCandado(motivo), 5000);
}

/* El servidor ya no reconoce la sesión (401). Si la pantalla creía que había
   alguien adentro, se va al candado; si el candado ya está arriba, nada. */
let volviendoAlCandado = false;
function sesionPerdida() {
  if (volviendoAlCandado || !SESION.entrado || SESION.provisorio) return;
  if (!$("#candado").hidden) return;
  volviendoAlCandado = true;
  SESION = { entrado: false, provisorio: false, permisos: [] };
  pintarQuien();
  mostrarCandado("Se cerró la sesión. ¿Quién sigue?")
    .finally(() => { volviendoAlCandado = false; });
}

/* ¿La caja sigue viva? Se pregunta al volver a la ventana y cada minuto. Si no
   contesta, se dice con todas sus letras y se ofrece recargar, en vez de dejar
   una pantalla que parece andar y no hace nada. Con el candado arriba no hace
   falta: el candado ya lo dice. */
async function vigilarLaCaja() {
  let viva = true;
  try { await api("/salud", { espera: 5000 }); } catch (e) { viva = false; }
  if (viva) enviarPendientes();
  // El dueño puede cambiar el inventario desde otra pantalla del local.
  // Se toma al volver o cada minuto, sin cambiar un formulario a medio llenar.
  if (viva && SESION.entrado && !$$('.capa.is-on').length) await cargarAjustes();
  const aviso = $("#sinCaja");
  if (aviso) aviso.hidden = viva || !$("#candado").hidden;
}

/* ---- bloqueo por inactividad ----
   Es lo que hace honesta la presencia: una sesión que alguien dejó abierta y se
   fue diría que esa persona estuvo toda la tarde. Nunca corta una venta: si hay
   pedido armado o un diálogo abierto, espera. */
let relojInactividad = null;
const MINUTOS_QUIETO = 3;

function reiniciarInactividad() {
  clearTimeout(relojInactividad);
  if (!SESION.entrado || SESION.provisorio) return;
  relojInactividad = setTimeout(() => {
    const ocupado = carrito.length || $$(".capa.is-on").length || Teclado.abierto;
    if (ocupado) return reiniciarInactividad();
    salirDeLaCaja("bloqueo");
  }, (AJUSTES.bloqueo_minutos || MINUTOS_QUIETO) * 60000);
}

["pointerdown", "keydown"].forEach((evt) =>
  document.addEventListener(evt, reiniciarInactividad, true));

// El margen escrito a mano. Va como oyente global y no colgado del campo porque
// el recuadro se rehace cada vez que cambia el costo.
document.addEventListener("input", (e) => {
  const campo = e.target.closest && e.target.closest("[data-margen-libre]");
  if (campo) elegirMargen(soloNumeros(campo.value));
});

// El buscador de dibujos. Global porque el selector se dibuja de nuevo cada vez
// que se abre una ficha, y un oyente colgado del campo se perdería.
document.addEventListener("input", (e) => {
  if (e.target && e.target.id === "buscarDibujo") filtrarDibujos(e.target.value);
});

/* ---------------- bodega ----------------
   Lo que hay guardado y el libro de lo que entró y salió. El stock se descuenta
   solo al vender, según la receta de cada producto — y un producto sin receta
   se vende igual y no mueve nada. Eso último es lo que permite empezar con dos
   insumos cargados en vez de tener que cargar la bodega entera antes de servir. */
let BODEGA = { insumos: [], valor_total: 0 };

const unidadCorta = { g: "g", ml: "ml", un: "un" };

async function cargarBodega() {
  if (!usarInventario()) return;
  try {
    // Se arma entero y RECIÉN ahí se reemplaza. Asignando BODEGA antes de pedir
    // /bodega, dos cargas seguidas (entrar a Bodega mientras otra carga seguía en
    // curso) dejaban a una leyendo BODEGA.productos sin definir: error y tabla vacía.
    const nueva = await api("/inventario");
    nueva.productos = (await api("/bodega")).insumos;
    BODEGA = nueva;
  } catch (e) { return avisar(e.message, true); }
  pintarBodega();
  $("#buscarBodega").oninput = pintarBodega;
  $("#tablaInsumosAnteriores").innerHTML = BODEGA.insumos.filter((i) =>
    !BODEGA.productos.some((p) => p.id === i.id)).map((i) => `
    <tr><td>${esc(i.nombre)}</td><td>${esc(i.muestra)}</td><td>
      <button class="btn btn--chico" data-cantidad-bodega="${i.id}">Cambiar cantidad</button>
      <button class="btn btn--chico" data-libro="${i.id}">Ver movimientos</button>
      <button class="btn btn--chico" data-insumo="${i.id}">Editar insumo</button>
    </td></tr><tr id="editarCantidad${i.id}" hidden><td colspan="3"></td></tr>`).join("");
  $("#recetasAnteriores").innerHTML = CATEGORIAS.flatMap((c) => c.productos).map((p) =>
    `<button class="btn btn--chico" data-ver-receta="${p.id}">Receta: ${esc(p.nombre)}</button>`).join(" ");
}

function filtrarBodega(filas, consulta) {
  const nombre = (s) => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const q = nombre(consulta);
  return filas.filter((i) => nombre(i.nombre).includes(q) || (i.codigos || []).includes(consulta.trim()));
}

function pintarBodega() {
  const filas = filtrarBodega(BODEGA.productos || [], $("#buscarBodega").value || "");
  $("#tablaInsumos").innerHTML = filas.length ? `
    <tr><th>Producto</th><th class="num">Cantidad</th><th></th></tr>
    ${filas.map((i) => `<tr>
      <td><button class="btn btn--fantasma" data-cantidad-bodega="${i.id}">${esc(i.nombre)}</button></td>
      <td class="num"><button class="btn btn--fantasma" data-cantidad-bodega="${i.id}">${i.stock} un</button></td>
      <td><button class="btn btn--chico" data-libro="${i.id}">Ver movimientos</button></td>
    </tr><tr id="editarCantidad${i.id}" hidden><td colspan="3"></td></tr>`).join("")}`
    : '<tr><td class="vacio">No hay productos para mostrar. Marca «Llevar la cuenta de este» en su ficha de la Carta.</td></tr>';
}

function editarCantidadBodega(id) {
  const i = (BODEGA.productos || []).find((p) => p.id === id)
    || BODEGA.insumos.find((p) => p.id === id);
  if (!i) return;
  const fila = $("#editarCantidad" + id);
  fila.hidden = false;
  fila.querySelector("td").innerHTML = `
    <label class="campo"><span>Cuántos hay de ${esc(i.nombre)} (${esc(i.unidad || "un")})</span>
      <div class="cantidad-bodega">
        <button class="btn" data-paso-bodega="-1" data-id="${id}" aria-label="Restar uno">−</button>
        <input id="cantidadBodega${id}" type="number" min="0" max="2147483647" step="1" inputmode="numeric" value="${Math.max(0, i.stock)}">
        <button class="btn" data-paso-bodega="1" data-id="${id}" aria-label="Sumar una unidad">+</button>
        <button class="btn" data-pedir-motivo="${id}">Guardar</button>
        <button class="btn btn--fantasma" data-cancelar-cantidad="${id}">Cancelar</button>
      </div></label>
    <div id="motivoBodega${id}" hidden>
      <p>¿Por qué cambió?</p>
      ${[["llego", "Llegó"], ["se perdio", "Se perdió"], ["conteo", "Conteo"], ["ajuste", "Ajuste"]].map(([valor, titulo]) =>
        `<button class="btn" data-guardar-cantidad="${id}" data-razon="${valor}">${titulo}</button>`).join(" ")}
    </div>`;
  $("#cantidadBodega" + id).oninput = () => { $("#motivoBodega" + id).hidden = true; };
  $("#cantidadBodega" + id).focus();
  $("#cantidadBodega" + id).select();
}

function cantidadBodegaValida(id) {
  const campo = $("#cantidadBodega" + id);
  const n = Number(campo.value);
  if (!campo.value.trim() || !Number.isInteger(n) || n < 0 || n > 2147483647) {
    avisar("Escribe una cantidad entera de unidades, desde cero", true);
    return null;
  }
  return n;
}

async function guardarCantidadBodega(id, motivo) {
  const cantidad = cantidadBodegaValida(id);
  if (cantidad === null) return;
  const principal = BODEGA.productos.find((p) => p.id === id);
  const i = principal || BODEGA.insumos.find((p) => p.id === id);
  const fila = $("#editarCantidad" + id);
  if (fila.dataset.guardando) return;
  fila.dataset.guardando = "1";
  fila.querySelectorAll("button, input").forEach((b) => { b.disabled = true; });
  try {
    const ruta = principal ? `/bodega/${id}/cantidad` : `/inventario/insumos/${id}/cantidad`;
    await api(ruta, { method: "PUT", body: JSON.stringify({
      cantidad, stock_esperado: i.stock, motivo }) });
    await cargarBodega();
    await cargarCarta();
    avisar("Cantidad guardada en el libro");
  } catch (e) {
    avisar(e.message, true);
    delete fila.dataset.guardando;
    fila.querySelectorAll("button, input").forEach((b) => { b.disabled = false; });
  }
}

async function verRecetaAnterior(id) {
  try {
    const r = await api(`/productos/${id}/receta`);
    $("#dialogoBodega").innerHTML = `
      <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
      <h2>Receta anterior</h2>
      <p class="ayuda">Los ingredientes y sus medidas se conservan.</p>
      <table class="tabla">${r.lineas.map((l) => `<tr><td>${esc(l.nombre)}</td><td>${esc(l.muestra)}</td></tr>`).join("") || '<tr><td>Sin receta</td></tr>'}</table>`;
    $("#capaBodega").classList.add("is-on");
  } catch (e) { avisar(e.message, true); }
}

/* ---- el libro de un insumo: contesta "¿por qué me faltan 3 litros?" ---- */
async function verLibro(insumoId) {
  const d = await api(`/inventario/insumos/${insumoId}/movimientos`);
  $("#dialogoBodega").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>${esc(d.insumo.nombre)}</h2>
    <p class="ayuda">Queda <b>${esc(d.insumo.muestra)}</b>. Cada línea dice qué pasó,
      cuánto quedó después y quién lo hizo.</p>
    <div class="tabla-wrap" style="max-height:52vh">
      <table class="tabla">
        <tr><th>Cuándo</th><th>Qué pasó</th><th class="num">Cuánto</th>
            <th class="num">Quedó</th><th>Quién</th></tr>
        ${d.movimientos.length ? d.movimientos.map((m) => `
          <tr>
            <td>${esc(m.fecha.slice(8, 10))}-${esc(m.fecha.slice(5, 7))}
                <small style="color:var(--suave)">${esc(m.fecha.slice(11, 16))}</small></td>
            <td><span class="pill">${esc(m.tipo)}</span> ${esc(m.motivo)}</td>
            <td class="num ${m.cantidad < 0 ? "mal" : "ok"}">${esc(m.muestra)}</td>
            <td class="num">${esc(m.saldo_muestra)}</td>
            <td>${esc(m.quien || "—")}</td>
          </tr>`).join("") : '<tr><td colspan="5" class="vacio">Sin movimientos todavía.</td></tr>'}
      </table>
    </div>`;
  $("#capaBodega").classList.add("is-on");
}

/* ---- llegó mercadería ---- */
function dialogoCompra() {
  if (!BODEGA.insumos.length) return avisar("Primero agrega un insumo", true);
  $("#dialogoBodega").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Llegó mercadería</h2>
    <p class="ayuda">Se anota en envases, que es como se compra: 6 cajas de leche,
      no 6.000 mililitros.</p>
    ${selectorDeInsumo("cInsumo")}
    <label class="campo"><span>¿Cuántos envases llegaron?</span>
      <input id="cEnvases" type="text" inputmode="numeric" data-teclado="entero" value="1"></label>
    <label class="campo"><span>¿Cuánto costó cada envase? (opcional)</span>
      <input id="cCosto" type="text" inputmode="numeric" placeholder="Deja vacío si no cambió"></label>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="guardarCompra" style="width:auto">Guardar</button>
    </div>`;
  $("#capaBodega").classList.add("is-on");
}

/* ---- se perdió algo ---- */
function dialogoMerma() {
  if (!BODEGA.insumos.length) return avisar("Primero agrega un insumo", true);
  $("#dialogoBodega").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Se perdió algo</h2>
    <p class="ayuda">Anotarlo es lo que hace que el conteo cuadre después. Una
      pérdida sin motivo no se distingue de un faltante, por eso el motivo es
      obligatorio.</p>
    ${selectorDeInsumo("mInsumo")}
    <label class="campo"><span>¿Cuánto?</span>
      <input id="mCantidad" type="text" inputmode="numeric" data-teclado="entero"
             placeholder="0"><span class="ayuda" id="mUnidad"></span></label>
    <div class="rapidos" id="motivosRapidos">
      <button data-motivo="Se cayó">Se cayó</button>
      <button data-motivo="Se venció">Se venció</button>
      <button data-motivo="Se probó / calibración">Se probó</button>
      <button data-motivo="Consumo del personal">Nos lo tomamos</button>
    </div>
    <label class="campo"><span>¿Qué pasó?</span>
      <input id="mMotivo" type="text" placeholder="Se cayó la bandeja"></label>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="guardarMerma" style="width:auto">Guardar</button>
    </div>`;
  $("#capaBodega").classList.add("is-on");
}

/* ---- contar la bodega: a ciegas, como el arqueo de caja ---- */
function dialogoConteo() {
  if (!BODEGA.insumos.length) return avisar("Todavía no hay nada que contar", true);
  $("#dialogoBodega").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Contar la bodega</h2>
    <p class="ayuda">Escribe lo que hay de verdad. No te muestro lo que debería
      haber hasta el final, a propósito: si lo vieras antes, es humano acomodar
      el conteo para que calce.</p>
    <div class="arqueo">
      ${BODEGA.insumos.map((i) => `
        <div class="arqueo__fila" data-conteo-fila="${i.id}">
          <div class="arqueo__valor">${esc(i.nombre)}<small>${esc(unidadCorta[i.unidad] || i.unidad)}</small></div>
          <div class="arqueo__cant">
            <input type="text" inputmode="numeric" data-teclado="entero"
                   data-conteo="${i.id}" placeholder="0">
          </div>
          <div class="arqueo__sub">—</div>
        </div>`).join("")}
    </div>
    <div id="zonaConteo"></div>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="guardarConteo" style="width:auto">Ver si cuadra</button>
    </div>`;
  $("#capaBodega").classList.add("is-on");
}

async function guardarConteo() {
  const conteos = {};
  $$("[data-conteo]").forEach((c) => {
    const v = (c.value || "").trim();
    if (v !== "") conteos[c.dataset.conteo] = soloNumeros(v);
  });
  if (!Object.keys(conteos).length) return avisar("No contaste nada todavía", true);
  try {
    const r = await api("/inventario/conteo", { method: "POST",
      body: JSON.stringify({ conteos, nota: "Conteo de la bodega" }) });
    $("#capaBodega").classList.remove("is-on");
    await cargarBodega();
    if (!r.ajustados) return avisar("Cuadra todo: no había ninguna diferencia");
    avisar(`${r.ajustados} ${r.ajustados === 1 ? "insumo no cuadraba" : "insumos no cuadraban"}`
           + ` · ${clp(Math.abs(r.costo_del_descuadre))} de diferencia`, true);
  } catch (e) { avisar(e.message, true); }
}

function selectorDeInsumo(id) {
  return `<label class="campo"><span>¿Cuál?</span>
    <select id="${id}">
      ${BODEGA.insumos.map((i) => `<option value="${i.id}">${esc(i.nombre)} — queda ${esc(i.muestra)}</option>`).join("")}
    </select></label>`;
}

/* ---- la ficha de un insumo ---- */
function dialogoInsumo(insumoId) {
  const i = BODEGA.insumos.find((x) => x.id === insumoId) || {
    nombre: "", unidad: "un", minimo: 0, formato: "", compra_contenido: 1, compra_costo: 0 };
  const nuevo = !insumoId;
  $("#dialogoInsumo").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>${nuevo ? "Insumo nuevo" : esc(i.nombre)}</h2>
    <label class="campo"><span>¿Qué es?</span>
      <input id="iNombre" type="text" value="${esc(i.nombre)}" placeholder="Leche entera"></label>
    <label class="campo"><span>¿En qué se mide?</span>
      <select id="iUnidad" ${nuevo ? "" : "disabled"}>
        <option value="un"${i.unidad === "un" ? " selected" : ""}>Unidades (alfajores, botellas)</option>
        <option value="ml"${i.unidad === "ml" ? " selected" : ""}>Mililitros (leche, jarabes)</option>
        <option value="g"${i.unidad === "g" ? " selected" : ""}>Gramos (café, harina)</option>
      </select></label>
    <label class="campo"><span>¿Cómo se compra?</span>
      <input id="iFormato" type="text" value="${esc(i.formato)}" placeholder="Caja de 1 litro"></label>
    <label class="campo"><span>¿Cuánto trae cada envase? (en ${esc(i.unidad)})</span>
      <input id="iContenido" type="text" inputmode="numeric" value="${i.compra_contenido || 1}"></label>
    <label class="campo"><span>¿Cuánto cuesta el envase?</span>
      <input id="iCosto" type="text" inputmode="numeric" value="${i.compra_costo || ""}" placeholder="0"></label>
    <label class="campo"><span>Avísame cuando queden menos de (en ${esc(i.unidad)})</span>
      <input id="iMinimo" type="text" inputmode="numeric" value="${i.minimo || ""}" placeholder="0"></label>
    ${nuevo ? `<label class="campo"><span>¿Cuánto hay ahora mismo? (en ${esc(i.unidad)})</span>
      <input id="iInicial" type="text" inputmode="numeric" placeholder="0"></label>` : ""}
    <div class="dialogo__pie">
      ${nuevo ? "" : `<button class="btn btn--peligro" data-sacar-insumo="${insumoId}">Sacar de la bodega</button>`}
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" data-guardar-insumo="${insumoId || 0}" style="width:auto">Guardar</button>
    </div>`;
  $("#capaInsumo").classList.add("is-on");
}

async function guardarInsumo(insumoId) {
  const cuerpo = {
    nombre: ($("#iNombre").value || "").trim(),
    unidad: $("#iUnidad").value,
    formato: ($("#iFormato").value || "").trim(),
    compra_contenido: Math.max(1, soloNumeros($("#iContenido").value)),
    compra_costo: soloNumeros($("#iCosto").value),
    minimo: soloNumeros($("#iMinimo").value),
  };
  if (!cuerpo.nombre) return avisar("Ponle un nombre", true);
  if ($("#iInicial")) cuerpo.stock_inicial = soloNumeros($("#iInicial").value);
  try {
    await api(insumoId ? `/inventario/insumos/${insumoId}` : "/inventario/insumos",
              { method: insumoId ? "PUT" : "POST", body: JSON.stringify(cuerpo) });
    $("#capaInsumo").classList.remove("is-on");
    await cargarBodega();
    avisar("Guardado");
  } catch (e) { avisar(e.message, true); }
}

/* ---------------- traer la carta de otro lado ----------------
   Un local nuevo llega con su lista en un Excel. Escribir cuarenta productos a
   mano es la razón más tonta por la que alguien no empieza a usar el sistema.

   Son dos pasos SIEMPRE: primero se muestra lo que se entendió del archivo y
   recién cuando la persona lo revisó se guarda. El archivo del cliente siempre
   trae algo raro, y lo único que evita que eso entre a la caja es que alguien
   lo vea antes. */
let LEIDO = null;

function dialogoImportar() {
  LEIDO = null;
  $("#dialogoImportar").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Traer la carta</h2>
    <p class="ayuda">Si ya tienes tu lista de productos en un Excel o escrita en
      otra parte, no hay que copiarla a mano. Te la leo y te muestro lo que
      entendí antes de guardar nada.</p>

    <div class="traer">
      <label class="traer__caja" id="zonaArchivo">
        <input type="file" id="archivoCarta" accept=".xlsx,.xlsm,.csv,.txt" hidden>
        <b>Desde un archivo</b>
        <span>Excel (.xlsx) o CSV. Tócalo para elegirlo.</span>
      </label>
      <div class="traer__caja">
        <b>O pégala aquí</b>
        <span>Copia las filas desde Excel o desde un Word y pégalas.</span>
        <textarea id="textoCarta" rows="5" placeholder="Espresso   1900&#10;Latte   3400"></textarea>
      </div>
    </div>

    <div id="zonaLeido"></div>

    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="leerCarta" style="width:auto">Ver qué se entiende</button>
    </div>`;
  $("#capaImportar").classList.add("is-on");

  $("#archivoCarta").addEventListener("change", (e) => {
    if (e.target.files[0]) leerArchivo(e.target.files[0]);
  });
  $("#zonaArchivo").addEventListener("click", () => $("#archivoCarta").click());
}

async function leerArchivo(archivo) {
  const cuerpo = new FormData();
  cuerpo.append("archivo", archivo);
  avisar("Leyendo " + archivo.name + "…");
  try {
    const r = await fetch("/api/v1/importar/archivo", { method: "POST", body: cuerpo });
    if (!r.ok) throw new Error((await r.json()).detail || "No se pudo leer");
    pintarLeido(await r.json());
  } catch (e) { avisar(e.message, true); }
}

async function leerTexto() {
  const texto = ($("#textoCarta").value || "").trim();
  if (!texto) return avisar("Pega la lista o elige un archivo", true);
  try {
    pintarLeido(await api("/importar/texto", { method: "POST",
      body: JSON.stringify({ texto }) }));
  } catch (e) { avisar(e.message, true); }
}

function pintarLeido(datos) {
  LEIDO = datos;
  const r = datos.resumen;
  $("#zonaLeido").innerHTML = `
    <div class="cuadre ${r.nuevos || r.cambian_precio ? "cuadre--ok" : ""}"
         style="margin-top:18px">
      <div class="cuadre__linea"><span>Productos en ${esc(datos.origen)}</span><span>${r.total}</span></div>
      <div class="cuadre__linea"><span>Se van a agregar</span><span><b>${r.nuevos}</b></span></div>
      <div class="cuadre__linea"><span>Les cambia el precio</span><span><b>${r.cambian_precio}</b></span></div>
      <div class="cuadre__linea"><span>Quedan igual</span><span>${r.iguales}</span></div>
    </div>

    ${datos.avisos.length ? `<div class="conectar" style="border-color:#E8C9C6;background:#FBECEA">
      <b>Revisa esto:</b><br>${datos.avisos.map(esc).join("<br>")}</div>` : ""}

    <p class="ayuda">Destilda lo que no quieras traer. Los precios se pueden
      corregir acá mismo.</p>
    <div class="tabla-wrap" style="max-height:40vh">
      <table class="tabla" id="tablaImportar">
        <tr><th style="width:44px"></th><th>Producto</th><th>Categoría</th>
            <th class="num">Precio</th><th></th></tr>
        ${datos.productos.map((p, i) => `
          <tr>
            <td><input type="checkbox" class="marca-traer" data-i="${i}" checked
                       style="width:26px;height:26px;accent-color:var(--clay)"></td>
            <td><b>${esc(p.nombre)}</b>${p.descripcion
                  ? `<div style="font-size:12.5px;color:var(--suave)">${esc(p.descripcion)}</div>` : ""}</td>
            <td>${esc(p.categoria)}</td>
            <td class="num"><input type="text" inputmode="numeric" class="precio-traer"
                   data-i="${i}" value="${p.precio}"
                   style="width:110px;text-align:right;height:44px;padding:0 10px;
                          border:1px solid var(--linea);border-radius:8px;
                          background:var(--papel);font-family:inherit;font-size:15px"></td>
            <td>${p.que_pasa === "nuevo" ? '<span class="pill" style="background:#EAF6EF;color:#14603A">nuevo</span>'
                 : p.que_pasa === "cambia_precio" ? `<span class="pill" style="background:#FFF4E5;color:#8A5A34">antes ${clp(p.precio_anterior)}</span>`
                 : '<span class="pill">igual</span>'}</td>
          </tr>`).join("")}
      </table>
    </div>

    ${datos.no_estan_en_el_archivo.length ? `
      <label class="marca" style="margin-top:14px">
        <input type="checkbox" id="sacarSobrantes">
        <span>Sacar de la venta los ${datos.no_estan_en_el_archivo.length} productos
          que están en la caja y no vienen en el archivo</span>
      </label>
      <p class="ayuda" style="margin-top:4px">${esc(datos.no_estan_en_el_archivo.slice(0, 8).join(", "))}${
        datos.no_estan_en_el_archivo.length > 8 ? "…" : ""}</p>` : ""}`;

  const pie = $("#dialogoImportar").querySelector(".dialogo__pie");
  pie.innerHTML = `
    <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
    <button class="btn btn--cobrar" id="aplicarCarta" style="width:auto">
      Traer ${r.nuevos + r.cambian_precio} producto${r.nuevos + r.cambian_precio === 1 ? "" : "s"}</button>`;
}

async function aplicarImportacion() {
  if (!LEIDO) return;
  const precios = {};
  $$(".precio-traer").forEach((c) => { precios[c.dataset.i] = soloNumeros(c.value); });
  const elegidos = $$(".marca-traer").filter((c) => c.checked).map((c) => {
    const p = LEIDO.productos[+c.dataset.i];
    return { nombre: p.nombre, precio: precios[c.dataset.i] ?? p.precio,
             categoria: p.categoria, descripcion: p.descripcion, dibujo: p.dibujo };
  });
  if (!elegidos.length) return avisar("No dejaste ningún producto marcado", true);

  try {
    const r = await api("/importar/aplicar", { method: "POST", body: JSON.stringify({
      productos: elegidos,
      sacar_lo_que_no_vino: !!($("#sacarSobrantes") || {}).checked })});
    $("#capaImportar").classList.remove("is-on");
    await cargarCarta();
    pintarEditorCarta();
    avisar(r.aviso);
  } catch (e) { avisar(e.message, true); }
}



/* ---- lo que se vendió en el turno, entero ----
   Va desde que se abre el cierre, no después del cuadre: la primera pregunta al
   cerrar es "¿cuánto vendimos hoy?", y antes había que sacarla sumando de cabeza
   entre tres recuadros distintos.

   `ciego` tapa SOLO el efectivo. Es lo que está dentro del cajón —incluidas sus
   propinas— y verlo antes de contar convertiría el arqueo en una confirmación.
   Todo lo demás se muestra igual, porque se cuadra contra papeles de afuera. */
function resumenDelTurno(tu, ciego) {
  const medios = Object.entries(tu.por_medio || {});
  if (!medios.length) return "";
  const vendido = medios.reduce((n, [, d]) => n + d.ventas, 0);
  const cobrado = medios.reduce((n, [, d]) => n + d.cobrado, 0);
  const cuantas = medios.reduce((n, [, d]) => n + d.cantidad, 0);

  // Si el turno no tuvo efectivo no hay nada que tapar, y el aviso sobraría.
  const tapar = !!ciego && medios.some(([m]) => m === "efectivo");
  const tapa = '<span class="tapado">al contar</span>';

  return `
    <div class="resumen-turno">
      <div class="resumen-turno__tit">Lo que se vendió en este turno</div>
      <table class="tabla">
        <tr><th>Forma de pago</th><th class="num">Ventas</th>
            <th class="num">Vendido</th><th class="num">Propina</th></tr>
        ${medios.map(([m, d]) => {
          const oculto = tapar && m === "efectivo";
          return `
          <tr${oculto ? ' class="es-tapado"' : ""}>
            <td>${esc(NOMBRE_MEDIO[m] || m)}</td>
            <td class="num">${d.cantidad}</td>
            <td class="num">${oculto ? tapa : clp(d.ventas)}</td>
            <td class="num">${oculto ? tapa : (d.propinas ? clp(d.propinas) : "—")}</td>
          </tr>`;
        }).join("")}
        <tr class="resumen-turno__total">
          <td><b>Total</b></td>
          <td class="num"><b>${cuantas}</b></td>
          <td class="num">${tapar ? tapa : `<b>${clp(vendido)}</b>`}</td>
          <td class="num">${tapar ? tapa : `<b>${clp(cobrado - vendido)}</b>`}</td>
        </tr>
      </table>
      <div class="resumen-turno__pie">
        ${tapar
          ? "El efectivo se destapa cuando termines de contar: si lo vieras antes, contarías hasta llegar a ese número y el arqueo no serviría de nada."
          : `Entró en total <b>${clp(cobrado)}</b>, contando las propinas.`}
      </div>
    </div>`;
}

/* ---- lo que no es efectivo ----
   El efectivo se CUENTA; esto se COPIA del comprobante de cierre de la máquina
   y de la app del banco. Va después del arqueo y no antes porque contar el
   cajón es lo que no se puede interrumpir.

   Lo esperado incluye la propina: la máquina le cobró al cliente el total con
   propina adentro, así que compararlo contra lo vendido a secas daría una
   diferencia falsa todos los días, justo del tamaño de las propinas. */
/* Los medios que se cuadran contra un papel de afuera: todos menos el efectivo,
   que se cuenta. Salen de NOMBRE_MEDIO —la lista de lo que la caja sabe cobrar—
   y NO de lo que se vendió, y ahí está el cambio.

   Antes la fila existía solo si la CAJA había registrado una venta de ese medio.
   O sea que el descuadre más grande posible era el único invisible: si en la
   máquina pasó un débito que acá quedó como efectivo, o que no quedó, no había
   dónde escribir lo que dice el comprobante. Con el turno recién abierto la
   columna quedaba vacía del todo, que es como se vio en la pantalla del local. */
const MEDIOS_QUE_SE_CUADRAN = Object.keys(NOMBRE_MEDIO).filter((m) => m !== "efectivo");

/* La fila de cada medio: la que armó el servidor si hubo ventas, o una en cero
   si no las hubo. `tu.medios` solo trae los que tuvieron. */
function filasDeCuadre(tu) {
  const registrados = {};
  (tu.medios || []).forEach((m) => { registrados[m.medio] = m; });
  return MEDIOS_QUE_SE_CUADRAN.map((medio) => registrados[medio] || {
    medio, nombre: NOMBRE_MEDIO[medio] || medio,
    cantidad: 0, ventas: 0, propinas: 0, esperado: 0,
    declarado: null, diferencia: null, propina_dicha: null,
  });
}

/* Un medio "se usó" si la caja registró algo con él, o si alguien ya escribió su
   comprobante. Los demás se esconden para que la pantalla no sea una lista de casillas
   vacías todas las noches —lo pidió el dueño: "es mucha cosa en pantalla"—, pero NO se
   sacan del formulario: siguen ahí, ocultos, y vuelven con un toque.

   La diferencia importa. La fila existe para TODOS los medios a propósito (ver arriba):
   si en la máquina pasó un débito que acá quedó como efectivo, tiene que haber dónde
   escribir lo que dice el comprobante. Borrarlas volvería a tapar el descuadre más grande
   que puede haber; esconderlas solo ahorra ruido. */
function seUso(m) {
  return (m.cantidad || 0) > 0 || m.declarado != null || m.propina_dicha != null;
}

function bloqueTarjetas(tu) {
  const medios = filasDeCuadre(tu);
  const guardados = medios.filter((m) => !seUso(m));
  const tildes = guardados.length ? `
      <div class="tarjetas__sumar">
        <span class="ayuda">¿Hubo también?</span>
        ${guardados.map((m) => `
          <button type="button" class="chip" data-sumar-medio="${m.medio}">
            + ${esc(m.nombre)}</button>`).join("")}
      </div>` : "";
  return `
    <div class="tarjetas">
      <div class="tarjetas__tit">¿Cuánto dice la máquina?</div>
      <p class="ayuda" style="margin:0 0 10px">Escribe el total del comprobante de
        cierre de Transbank y lo que muestre el banco. Es opcional: si lo dejas
        vacío, la caja igual cierra.</p>
      ${medios.map((m) => `
        <div class="tarjetas__fila" data-medio-fila="${m.medio}"${seUso(m) ? "" : " hidden"}>
          <div>
            <b>${esc(m.nombre)}</b>
            <div class="tarjetas__detalle">${detalleDelMedio(m)}</div>
          </div>
          <div class="tarjetas__esperado">deberían ser<b>${clp(m.esperado)}</b></div>
          <input type="text" inputmode="numeric" data-dice="${m.medio}"
                 value="${m.declarado != null ? m.declarado : ""}" placeholder="0">
          <div class="tarjetas__dif" data-dif="${m.medio}"></div>
          <div class="tarjetas__propina">
            <span>De eso, propina</span>
            <input type="text" inputmode="numeric" data-propina-dice="${m.medio}"
                   value="${m.propina_dicha != null ? m.propina_dicha : ""}"
                   placeholder="${m.propinas || 0}">
            <small>la caja anotó ${clp(m.propinas || 0)}</small>
          </div>
          <div class="tarjetas__pista" data-pista="${m.medio}"></div>
        </div>`).join("")}
      ${tildes}
    </div>`;
}

/* Los campos se marcan `data-dice`, NO `data-medio`: los botones de medio de
   pago del diálogo de cobro ya usan `data-medio` y viven en index.html desde que
   carga la página, así que `querySelector` encontraba el botón en vez del campo
   y el "cuadra ✓" no aparecía nunca. */
/* Cuando el cajón no cuadra, decir dónde mirar.

   Dos sospechas, en el orden en que conviene revisarlas:

   1. EL FONDO DE LA MAÑANA. Es la que más veces explica un sobrante, y la más
      invisible: si el cajón se contó de menos al abrir, la diferencia aparece
      recién doce horas después y parece salida de la nada. Por eso va primero
      y con el número de anoche al lado.
   2. UNA VENTA EN EFECTIVO. Si la diferencia calza exacta con una, ahí está. */
async function buscarElDescuadre(tu, dif) {
  const caja = $("#pistaEfectivo");
  if (!caja) return;

  const partes = [];
  const anoche = tu.fondo_anterior;
  if (anoche != null && anoche !== tu.monto_inicial) {
    const salto = tu.monto_inicial - anoche;
    partes.push(`<div class="pista">
      <b>El fondo de la mañana no calza con el de anoche.</b>
      <div class="pista__linea"><span>Anoche quedaron</span><b>${clp(anoche)}</b></div>
      <div class="pista__linea"><span>Esta mañana se contaron</span><b>${clp(tu.monto_inicial)}</b></div>
      <div class="pista__linea pista__dif"><span>${salto > 0 ? "De más" : "De menos"}</span>
        <b>${clp(Math.abs(salto))}</b></div>
      <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Si el cajón se contó
        de menos en la mañana, el sobrante aparece recién ahora y parece salido de
        la nada.</p>
    </div>`);
  }

  const todas = await ventasDelTurno(tu.id);
  const enEfectivo = todas.filter((v) => v.medio_pago === "efectivo" && !v.anulada);
  const calzan = loQueExplicaLaDiferencia(enEfectivo, dif);
  if (calzan.length) {
    partes.push(`<div class="pista">
      <b>${dif > 0 ? "Esta venta calza con lo que sobra:" : "Esta venta calza con lo que falta:"}</b>
      ${calzan.map((g) => listaDeVentas(g, [g])).join("")}
      <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">${dif > 0
        ? "Puede ser una venta cobrada dos veces, o cobrada en efectivo y registrada como tarjeta."
        : "Puede ser una venta registrada y no cobrada, o un vuelto de más."}</p>
    </div>`);
  } else if (enEfectivo.length) {
    partes.push(`<div class="pista">
      <b>Ninguna venta sola explica la diferencia.</b>
      <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Estas son las ventas
        en efectivo del turno, por si alguna no calza con lo que recuerdas:</p>
      ${listaDeVentas(enEfectivo, [])}
    </div>`);
  }

  caja.innerHTML = partes.length
    ? `<div class="cierre__paso"><b>?</b> Dónde mirar</div>${partes.join("")}`
    : "";
}

/* ---------------- buscar el descuadre ----------------
   Hasta ahora el cierre decía "sobran $1.450" y ahí quedaba: uno sabe que algo
   no calza y no tiene dónde mirar. Estas dos funciones son el "dónde mirar".

   La de abajo es la que de verdad resuelve, y sale de algo que dijo el dueño:
   «por lo usual en tarjeta puede haber más en el sistema que en la vida real».
   Pasa cuando una venta se marcó como débito, la máquina la rechazó y nadie la
   anuló; o cuando se cobró en efectivo y se registró como tarjeta. Si la
   diferencia calza EXACTA con una venta, casi siempre es esa. */
let VENTAS_DEL_TURNO = null;

async function ventasDelTurno(turnoId) {
  if (VENTAS_DEL_TURNO) return VENTAS_DEL_TURNO;
  try { VENTAS_DEL_TURNO = await api(`/turnos/${turnoId}/ventas`); }
  catch (e) { VENTAS_DEL_TURNO = []; }
  return VENTAS_DEL_TURNO;
}

/* Qué venta —o qué par— explica una diferencia. Devuelve las candidatas.

   Se buscan sumas de UNA y de DOS ventas porque más allá de eso deja de ser una
   pista y pasa a ser numerología: con quince ventas, algún subconjunto siempre
   suma cualquier cosa. */
function loQueExplicaLaDiferencia(ventas, falta) {
  falta = Math.abs(falta);
  if (!falta || !ventas.length) return [];
  const solas = ventas.filter((v) => v.cobrado === falta);
  if (solas.length) return solas.map((v) => [v]);

  const pares = [];
  for (let i = 0; i < ventas.length && pares.length < 3; i++) {
    for (let j = i + 1; j < ventas.length; j++) {
      if (ventas[i].cobrado + ventas[j].cobrado === falta) {
        pares.push([ventas[i], ventas[j]]);
        break;
      }
    }
  }
  return pares;
}

function listaDeVentas(ventas, resaltar) {
  const marcadas = new Set((resaltar || []).flat().map((v) => v.id));
  return `<div class="ventas-mini">
    ${ventas.map((v) => `
      <div class="ventas-mini__fila${marcadas.has(v.id) ? " es-sospechosa" : ""}">
        <span class="ventas-mini__hora">${esc(v.hora)}</span>
        <span class="ventas-mini__n">#${v.numero}</span>
        <span class="ventas-mini__medio">${esc(v.medio)}</span>
        <b>${clp(v.cobrado)}</b>
      </div>`).join("")}
  </div>`;
}

/* Lo que la caja registró de ese medio, para la línea chica bajo el nombre. */
function detalleDelMedio(m) {
  if (!m.cantidad) return "la caja no registró ninguna";
  const propina = m.propinas ? " + " + clp(m.propinas) + " de propina" : "";
  return m.cantidad + " venta" + (m.cantidad === 1 ? "" : "s") + " · " + clp(m.ventas) + propina;
}

function conectarTarjetas(tu) {
  filasDeCuadre(tu).forEach((m) => {
    const campo = document.querySelector(`[data-dice="${m.medio}"]`);
    if (!campo) return;
    const pintar = async () => {
      const caja = document.querySelector(`[data-dif="${m.medio}"]`);
      const pista = document.querySelector(`[data-pista="${m.medio}"]`);
      const escrito = (campo.value || "").trim();
      if (pista) pista.innerHTML = "";
      if (!escrito) { caja.textContent = ""; caja.className = "tarjetas__dif"; return; }

      const dif = soloNumeros(escrito) - m.esperado;
      caja.textContent = dif === 0 ? "cuadra ✓"
        : (dif > 0 ? "sobran " : "faltan ") + clp(Math.abs(dif));
      caja.className = "tarjetas__dif " + (dif === 0 ? "ok" : "mal");
      if (dif === 0 || !pista) return;

      // Acá está el trabajo de verdad: decir CUÁL venta puede ser.
      const todas = await ventasDelTurno(tu.id);
      const deEsteMedio = todas.filter((v) => v.medio_pago === m.medio && !v.anulada);

      // El caso que antes no se podía ni escribir: la máquina dice que hubo y la
      // caja no registró NINGUNA. No es una venta que calce mal, es una venta que
      // se cobró con otra forma de pago. Buscarla entre las ventas de este medio
      // sería buscar en una lista vacía, así que se dice derecho qué pasó.
      if (!deEsteMedio.length) {
        pista.innerHTML = `<div class="pista">
          <b>La caja no registró ninguna venta en ${esc(m.nombre.toLowerCase())} este turno.</b>
          <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Si la máquina dice que
            sí hubo, esa venta quedó cobrada de otra forma —casi siempre efectivo—.
            Búscala en <b>El día</b>, anúlala y vuelve a cobrarla como corresponde: si no,
            el cajón va a aparecer con plata de más y la máquina con plata de menos.</p>
        </div>`;
        return;
      }

      const calzan = loQueExplicaLaDiferencia(deEsteMedio, dif);

      pista.innerHTML = `
        ${calzan.length ? `<div class="pista">
          <b>${calzan.length === 1 ? "Esta venta calza justo con la diferencia:"
                                   : "Estas calzan justo con la diferencia:"}</b>
          ${calzan.map((grupo) => listaDeVentas(grupo, [grupo])).join("")}
          <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Si la máquina la
            rechazó y quedó registrada igual, anúlala en <b>El día</b>. Si se pagó de
            otra forma, anúlala y vuelve a cobrarla como corresponde.</p>
        </div>` : `<div class="pista">
          <b>Ninguna venta sola explica la diferencia.</b>
          <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Puede ser una propina
            que la máquina cobró aparte, o varias ventas juntas. Acá están todas las
            de ${esc(m.nombre.toLowerCase())} de este turno:</p>
          ${listaDeVentas(deEsteMedio, [])}
        </div>`}`;
    };
    campo.addEventListener("input", pintar);
    pintar();
  });
}

/* La propina según la máquina, por medio. Puede no ser la que anotó la caja:
   el cliente la deja en el pinpad y el cajero no siempre la registra. */
function propinasDeclaradas() {
  const salida = {};
  $$("[data-propina-dice]").forEach((c) => {
    const v = (c.value || "").trim();
    if (v) salida[c.dataset.propinaDice] = soloNumeros(v);
  });
  return salida;
}

function mediosDeclarados() {
  const salida = {};
  $$("[data-dice]").forEach((c) => {
    const v = (c.value || "").trim();
    if (v) salida[c.dataset.dice] = soloNumeros(v);
  });
  return salida;
}

/* ---- propinas ----
   Separadas a propósito: la de efectivo ya está en el cajón y se reparte de
   ahí; la de tarjeta se la quedó el banco y hay que pagársela al equipo aparte.
   Sin esta distinción, alguien reparte dos veces o no reparte nunca. */
function bloquePropinas(tu) {
  const p = tu.propinas || { efectivo: 0, tarjeta: 0, total: 0 };
  if (!p.total) return "";
  return `
    <div class="cuadre" style="background:#FFF8EE;border-color:#E7D9C7">
      <div class="cuadre__linea"><span>Propinas en efectivo</span><span>${clp(p.efectivo)}</span></div>
      <div class="cuadre__linea"><span>Propinas por tarjeta</span><span>${clp(p.tarjeta)}</span></div>
      <div class="cuadre__linea cuadre__dif" style="font-size:16px">
        <span>Propinas del turno</span><span>${clp(p.total)}</span></div>
      ${p.tarjeta ? `<p class="ayuda" style="margin:8px 0 0">Los ${clp(p.tarjeta)} de
        tarjeta no están en el cajón: los depositó el banco y hay que pagarlos aparte.</p>` : ""}
    </div>`;
}

/* ---------------- ayuda ----------------
   Las guías viven en guias.js, aparte, porque son texto y no programa: así se
   corrigen sin tocar el código de la caja y viajan en una actualización como
   cualquier otro archivo. */
let guiaAbierta = null;

function pintarGuias(id) {
  const guias = (window.GUIAS || []).filter((g) => usarInventario() || !g.inventario);
  if (!guias.length) {
    $("#textoGuia").innerHTML = "<p class='ayuda'>Todavía no hay guías cargadas.</p>";
    return;
  }
  guiaAbierta = id || guiaAbierta || guias[0].id;
  const actual = guias.find((g) => g.id === guiaAbierta) || guias[0];

  $("#listaGuias").innerHTML = guias.map((g) => `
    <button class="ayuda-item ${g.id === actual.id ? "is-on" : ""}" data-guia="${g.id}">
      <b>${esc(g.titulo)}</b>
      <small>${esc(g.resumen)}</small>
    </button>`).join("");

  $("#textoGuia").innerHTML = `<h2>${esc(actual.titulo)}</h2>${actual.html}`;
  $("#textoGuia").querySelectorAll("[data-con-inventario]").forEach((el) => {
    el.hidden = !usarInventario();
  });
  $("#textoGuia").scrollTop = 0;
}

/* ---------------- ajustes de la caja ----------------
   Existe porque el changelog de la 2.5 prometía que el teclado en pantalla "se
   prende desde los ajustes" y esa pantalla no existía: el campo se guardaba, se
   leía, y no había ninguna forma de cambiarlo desde el programa. Si por lo que
   fuera quedaba prendido, el dueño no tenía cómo apagarlo. */
/* ---- Ayuda → Ajustes ----
   Todo lo de acá es del dueño. Desde la 2.19 están también los datos del local,
   el PIN de red, cuánto tarda en bloquearse, la copia de afuera, el canal de
   actualizaciones y el diagnóstico: lo que antes se configuraba con variables
   de Windows, o no se configuraba. */
// Las posiciones se muestran tal como las guarda el servidor: desde cero y
// hasta sin incluir. Así el dibujo permite revisar cada dígito sin traducirlo.
function dibujoFormatoBalanza(f) {
  const bien = (r) => Array.isArray(r) && r.every((n) => Number.isInteger(n) && n >= 0)
    && r[0] < r[1] && r[1] <= 12;
  const faltan = [!/^2[0-9]*$/.test(f.prefijo || "") && "el prefijo (solo números, empieza con 2)",
    !bien(f.codigo) && "dónde está el número", !bien(f.valor) && "dónde está el valor"]
    .filter(Boolean);
  if (faltan.length) return "Falta o está mal: " + faltan.join(", ") + ".";
  const marcas = Array.from({ length: 13 }, (_, i) => {
    if (i === 12) return "V";
    const partes = [i < f.prefijo.length ? "P" : "",
      i >= f.codigo[0] && i < f.codigo[1] ? "N" : "",
      i >= f.valor[0] && i < f.valor[1] ? "$" : ""].filter(Boolean);
    return partes.length > 1 ? "!" : partes[0] || "·";
  });
  return "0123456789012\n" + marcas.join("")
    + "\nP: prefijo · N: número\n$: valor · V: verificador\n!: partes superpuestas";
}

function bloqueBalanza() {
  const f = AJUSTES.formato_balanza || {
    modo: "ticket", prefijo: "25", codigo: [2, 6], valor: [6, 12], divisor_peso: 1000 };
  const usar = !!AJUSTES.usar_balanza;
  return `<div class="ajuste" id="ajBalanza">
    <h4>Balanza</h4>
    <label class="marca">
      <input type="checkbox" id="ajUsarBalanza" ${usar ? "checked" : ""}>
      Este local cobra etiquetas de una balanza</label>
    <p class="ayuda" style="margin:8px 0 0">Para el fiambre, el pan o el queso que se pesan
      y salen con una etiqueta con código de barras. Si este local no tiene balanza, déjalo
      apagado: así nadie puede cobrar un código de balanza inventado.</p>
    ${AJUSTES.formato_balanza_roto ? `<div class="ajuste__alerta">El formato guardado de la
      balanza no se entiende, así que la caja no está cobrando etiquetas. Revísalo abajo y
      guárdalo de nuevo.</div>` : ""}
    <div id="ajBalanzaCuerpo" ${usar ? "" : "hidden"}>
    <label class="campo" style="margin-top:12px"><span>Qué imprime la etiqueta</span>
      <select id="ajBalanzaModo">
        ${[["ticket", "Un ticket con el total (el detalle queda en el papel)"],
           ["plu_peso", "El número del producto y el peso"],
           ["plu_precio", "El número del producto y el precio"]].map(([modo, texto]) =>
          `<option value="${modo}"${f.modo === modo ? " selected" : ""}>${texto}</option>`).join("")}
      </select></label>
    <details class="avanzado">
      <summary>Cómo está armado el código</summary>
      <div class="avanzado__cuerpo">
        <label class="campo"><span>Prefijo</span>
          <input id="ajBalanzaPrefijo" inputmode="numeric" value="${esc(f.prefijo)}"></label>
        <p class="ayuda">Cuenta desde 0. «Hasta» no se incluye. El último dígito (12)
          es el verificador: no lo uses para el número ni el valor.</p>
        ${[["Codigo", "número", f.codigo], ["Valor", "valor", f.valor]].map(([id, nombre, rango]) => `
          <div class="fila2">
            <label class="campo"><span>El ${nombre}, desde</span>
              <input id="ajBalanza${id}Desde" type="number" min="0" max="11" value="${rango[0]}"></label>
            <label class="campo"><span>Hasta (sin incluir)</span>
              <input id="ajBalanza${id}Hasta" type="number" min="1" max="12" value="${rango[1]}"></label>
          </div>`).join("")}
        <label class="campo" id="ajBalanzaDivisorCampo"${f.modo === "plu_peso" ? "" : " hidden"}>
          <span>Divisor del peso</span>
          <input id="ajBalanzaDivisor" type="number" min="1" value="${f.divisor_peso}">
          <small class="ayuda" style="display:block;margin:6px 0 0">1000 si la etiqueta trae gramos.</small></label>
        <pre id="ajBalanzaDibujo" style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(dibujoFormatoBalanza(f))}</pre>
      </div>
    </details>
    <button type="button" class="btn" id="ajBalanzaGuardar">Guardar formato de balanza</button>
    <label class="campo"><span>Probar con una etiqueta</span>
      <input id="ajBalanzaPrueba" type="text" inputmode="numeric" autocomplete="off"
             placeholder="Escanea o escribe el código"></label>
    <p class="ayuda">La prueba usa lo guardado. Si cambiaste algo, guarda primero.</p>
    <button type="button" class="btn" id="ajBalanzaProbar">Probar etiqueta</button>
    <p class="ayuda" id="ajBalanzaResultado" role="status" aria-live="polite"></p>
    </div>
  </div>`;
}

function leerFormatoBalanza() {
  // Un campo vacío debe fallar al guardar, no convertirse silenciosamente en 0.
  const numero = (id) => $(id).value.trim() === "" ? null : Number($(id).value);
  return { modo: $("#ajBalanzaModo").value, prefijo: $("#ajBalanzaPrefijo").value.trim(),
    codigo: [numero("#ajBalanzaCodigoDesde"), numero("#ajBalanzaCodigoHasta")],
    valor: [numero("#ajBalanzaValorDesde"), numero("#ajBalanzaValorHasta")],
    // Solo el modo por peso usa el divisor. Oculto y mal escrito no puede impedir
    // guardar un ticket con un error sobre un campo que no se ve.
    divisor_peso: $("#ajBalanzaModo").value === "plu_peso"
      ? numero("#ajBalanzaDivisor")
      : ((AJUSTES.formato_balanza || {}).divisor_peso || 1000) };
}

function conectarBalanza() {
  $("#ajUsarBalanza").addEventListener("change", (e) => {
    e.stopPropagation();
    const usar = e.target.checked;
    $("#ajBalanzaCuerpo").hidden = !usar;
    guardarAjuste({ usar_balanza: usar ? 1 : 0 },
      usar ? "Balanza prendida: revisa qué imprime la etiqueta y prueba una"
           : "Balanza apagada: la caja ya no cobra etiquetas");
  });
  $("#ajBalanza").addEventListener("input", () => {
    const f = leerFormatoBalanza();
    $("#ajBalanzaDibujo").textContent = dibujoFormatoBalanza(f);
    $("#ajBalanzaDivisorCampo").hidden = f.modo !== "plu_peso";
  });
  $("#ajBalanzaGuardar").onclick = guardarFormatoBalanza;
  $("#ajBalanzaProbar").onclick = probarEtiquetaBalanza;
  $("#ajBalanzaPrueba").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    e.stopPropagation();
    probarEtiquetaBalanza();
  });
}

async function guardarFormatoBalanza() {
  if (!puedo("config")) return;
  try {
    const r = await api("/ajustes", { method: "PUT",
      body: JSON.stringify({ formato_balanza: leerFormatoBalanza() }) });
    AJUSTES = { ...AJUSTES, ...r };
    $("#ajBalanzaResultado").textContent = "Formato guardado. Ya puedes probar una etiqueta.";
    avisar("Formato de balanza guardado");
  } catch (e) {
    // Conservamos lo escrito para corregir las posiciones que rechazó el servidor.
    $("#ajBalanzaResultado").textContent = e.message;
    avisar(e.message, true);
  }
}

async function probarEtiquetaBalanza() {
  if (!puedo("config")) return;
  const resultado = $("#ajBalanzaResultado");
  const codigo = $("#ajBalanzaPrueba").value.trim();
  if (!codigo) { resultado.textContent = "Escanea o escribe una etiqueta"; return; }
  resultado.textContent = "Leyendo etiqueta…";
  try {
    const r = await api("/codigos/" + encodeURIComponent(codigo));
    resultado.textContent = r.balanza
      ? `${r.balanza.nombre} · ${r.balanza.detalle} · ${clp(r.balanza.precio)}`
      : r.problema || "Ese código no es una etiqueta de balanza";
  } catch (e) { resultado.textContent = e.message; }
}

function bloqueImpresion() {
  return `<div class="ajuste" id="ajImpresion">
    <h4>Impresión de comprobantes</h4>
    <label class="marca"><input type="checkbox" id="ajImprimirSiempre"
      ${imprimirSiempre ? "checked" : ""}> Imprimir comprobante después de cada venta</label>
    <p class="ayuda">Estas preferencias quedan en este navegador. Las impresoras son las
      instaladas en el computador Windows donde funciona la caja.</p>
    <div class="ajuste__campos">
      <label class="campo"><span>Tipo de impresora</span><select id="ajTipoImpresora">
        <option value="termica"${tipoImpresion() === "termica" ? " selected" : ""}>Impresora de tickets (térmica)</option>
        <option value="windows"${tipoImpresion() === "windows" ? " selected" : ""}>Impresora normal (Windows)</option>
        <option value="navegador"${tipoImpresion() === "navegador" ? " selected" : ""}>Preguntar al navegador</option>
      </select></label>
      <label class="campo"><span>Impresora</span><select id="ajImpresora">
        <option value="">Elige una impresora</option>
        ${IMPRESION.impresora ? `<option selected value="${esc(IMPRESION.impresora)}">${esc(IMPRESION.impresora)} (guardada)</option>` : ""}
      </select></label>
      <label class="campo"><span>Ancho del papel</span><select id="ajPapel">
        <option value="58"${IMPRESION.papel === 58 ? " selected" : ""}>58 mm</option>
        <option value="80"${IMPRESION.papel === 80 ? " selected" : ""}>80 mm</option>
      </select></label>
    </div>
    <p class="ayuda">Es el ancho del <b>rollo</b>, no el de la impresora. Si en la prueba los
      precios saltan a la línea de abajo, o las rayas salen cortadas en dos, el rollo es más
      angosto de lo elegido: cambia a 58 mm y prueba otra vez.</p>
    <div class="ajuste__fila">
      <button class="btn" id="ajActualizarImpresoras">Actualizar impresoras</button>
      <button class="btn" id="ajProbarImpresion"${probandoImpresion ? " disabled" : ""}>Imprimir prueba</button>
    </div>
    <div id="ajInstalacionImpresora" hidden>
      <label class="campo"><span>Puerto disponible</span><select id="ajPuertoImpresora"></select></label>
      <button class="btn" id="ajInstalarImpresora"${instalandoImpresora ? " disabled" : ""}>Instalar la impresora de tickets</button>
      <p class="ayuda">Windows va a pedir permiso para instalar la impresora.</p>
    </div>
    <p class="ayuda" id="ajImpresionEstado" role="status">Elige una impresora para imprimir directamente.
      Con «Preguntar al navegador» aparece el diálogo de impresión. Los cierres usan ese diálogo.</p>
  </div>`;
}

function guardarImpresion(tipoExplicito = false) {
  if (!puedo("config")) return;
  const siguiente = { automatica: $("#ajImprimirSiempre").checked,
    impresora: $("#ajImpresora").value, papel: +$("#ajPapel").value,
    puerto: impresorasWindows.find((p) => p.nombre === $("#ajImpresora").value)?.puerto
      || ($("#ajImpresora").value === IMPRESION.impresora ? IMPRESION.puerto : ""),
    tipo: tipoExplicito ? $("#ajTipoImpresora").value : IMPRESION.tipo };
  try {
    localStorage.setItem("pos.impresion", JSON.stringify(siguiente));
    IMPRESION = siguiente;
    imprimirSiempre = siguiente.automatica;
    $("#ajTipoImpresora").value = tipoImpresion();
    $("#ajImpresionEstado").textContent = "Preferencias de impresión guardadas en este navegador.";
  } catch (e) {
    $("#ajImprimirSiempre").checked = imprimirSiempre;
    $("#ajImpresora").value = IMPRESION.impresora;
    $("#ajPapel").value = String(IMPRESION.papel);
    $("#ajTipoImpresora").value = tipoImpresion();
    $("#ajImpresionEstado").textContent = "No se pudieron guardar las preferencias. Revisa el almacenamiento del navegador.";
  }
}

async function cargarImpresoras() {
  if (!puedo("config")) return;
  const selector = $("#ajImpresora"), boton = $("#ajActualizarImpresoras");
  const estado = $("#ajImpresionEstado");
  if (!selector || boton.disabled) return;
  boton.disabled = true;
  $("#ajInstalacionImpresora").hidden = true;
  puertosImpresion = [];
  estado.textContent = "Consultando las impresoras de Windows…";
  try {
    const r = await api("/impresion/impresoras");
    if (selector !== $("#ajImpresora")) return;
    const lista = r.impresoras || [];
    impresorasWindows = lista;
    const elegida = IMPRESION.impresora;
    const puerto = lista.find((p) => p.nombre === elegida)?.puerto;
    if (puerto && puerto !== IMPRESION.puerto) {
      // Recordar el puerto permite detectar el tipo al abrir de nuevo la caja,
      // aunque ese día el dueño no entre a Configurar.
      const siguiente = { ...IMPRESION, puerto };
      try {
        localStorage.setItem("pos.impresion", JSON.stringify(siguiente));
        IMPRESION = siguiente;
      } catch (e) { /* La lista sigue siendo útil aunque el navegador no guarde. */ }
    }
    selector.innerHTML = '<option value="">Elige una impresora</option>'
      + (elegida && !lista.some((p) => p.nombre === elegida)
        ? `<option value="${esc(elegida)}">${esc(elegida)} (no disponible)</option>` : "")
      + lista.map((p) => `<option value="${esc(p.nombre)}"${p.disponible ? "" : " disabled"}>${esc(p.nombre)}${p.disponible ? "" : " (requiere diálogo)"}</option>`).join("");
    selector.value = elegida;
    $("#ajTipoImpresora").value = tipoImpresion();
    estado.textContent = !r.disponible ? r.detalle
      : !lista.length ? "No hay impresoras instaladas. Instálala en Windows y actualiza esta lista."
      : elegida && !lista.some((p) => p.nombre === elegida && p.disponible)
        ? "La impresora guardada no está disponible para impresión directa. Elige otra o usa el navegador."
        : "Lista actualizada. Imprime una prueba para revisar el papel. Los cierres usan el diálogo del navegador.";
    if (r.disponible && !lista.some((p) => p.disponible)) {
      const libres = await api("/impresion/puertos");
      if (selector !== $("#ajImpresora")) return;
      // FILE/PDF no son conexiones de una impresora enchufada. USB va primero
      // para que el puerto habitual de una ticketera sea el sugerido.
      puertosImpresion = (libres.puertos || []).filter((p) =>
        !/^(FILE:|PORTPROMPT:|NUL:|SHRFAX:|Microsoft\.Office\.OneNote)/i.test(p.nombre))
        .sort((a, b) => Number(/^USB/i.test(b.nombre)) - Number(/^USB/i.test(a.nombre)));
      $("#ajPuertoImpresora").innerHTML = puertosImpresion.map((p) =>
        `<option value="${esc(p.nombre)}">${esc(p.nombre)}${p.descripcion ? " — " + esc(p.descripcion) : ""}</option>`).join("");
      $("#ajInstalacionImpresora").hidden = !puertosImpresion.length;
      if (puertosImpresion.length) estado.textContent = "Windows tiene puertos disponibles. Elige el de la impresora y pulsa Instalar.";
    }
  } catch (e) {
    estado.textContent = e.message + ". Se conserva la impresora guardada.";
  } finally { boton.disabled = false; }
}

async function probarImpresion() {
  if (!puedo("config") || probandoImpresion) return;
  const estado = $("#ajImpresionEstado");
  if (!IMPRESION.impresora || tipoImpresion() === "navegador") {
    estado.textContent = "Elige una impresora de Windows para imprimir la prueba.";
    return;
  }
  probandoImpresion = true;
  $("#ajProbarImpresion").disabled = true;
  estado.textContent = "Enviando la prueba…";
  try {
    const prefijo = tipoImpresion() === "termica" ? "crudo/" : "";
    const r = await api(`/impresion/${prefijo}prueba`, { method: "POST", espera: 25000,
      body: JSON.stringify({ impresora: IMPRESION.impresora, papel: IMPRESION.papel }) });
    estado.textContent = r.detalle;
  } catch (e) {
    estado.textContent = e.message + ". Revisa la cola de Windows antes de repetir la prueba.";
  } finally {
    probandoImpresion = false;
    const boton = $("#ajProbarImpresion");
    if (boton) boton.disabled = false;
  }
}

async function instalarImpresora() {
  if (!puedo("config") || instalandoImpresora) return;
  const puerto = $("#ajPuertoImpresora").value;
  if (!puertosImpresion.some((p) => p.nombre === puerto)) return;
  const estado = $("#ajImpresionEstado");
  instalandoImpresora = true;
  $("#ajInstalarImpresora").disabled = true;
  estado.textContent = "Acepta el permiso de Windows para instalar la impresora…";
  try {
    const r = await api("/impresion/instalar", { method: "POST", espera: 125000,
      body: JSON.stringify({ puerto, nombre: "Kofe Tickets" }) });
    // Guardar antes de consultar: la cola ya existe aunque falle la recarga o
    // el dueño haya salido de Configurar mientras aceptaba el permiso.
    const siguiente = { ...IMPRESION, impresora: r.nombre, puerto };
    try {
      localStorage.setItem("pos.impresion", JSON.stringify(siguiente));
      IMPRESION = siguiente;
    } catch (e) {
      throw Error("La impresora se instaló, pero no se pudo guardar la selección en este navegador. Actualiza la lista y selecciónala.");
    }
    await cargarImpresoras();
  } catch (e) {
    estado.textContent = e.message;
  } finally {
    instalandoImpresora = false;
    const boton = $("#ajInstalarImpresora");
    if (boton) boton.disabled = false;
  }
}

function conectarImpresion() {
  ["#ajImprimirSiempre", "#ajImpresora", "#ajPapel"].forEach((id) => {
    $(id).addEventListener("change", () => guardarImpresion());
  });
  $("#ajTipoImpresora").addEventListener("change", () => guardarImpresion(true));
  $("#ajActualizarImpresoras").onclick = cargarImpresoras;
  $("#ajProbarImpresion").onclick = probarImpresion;
  $("#ajInstalarImpresora").onclick = instalarImpresora;
  cargarImpresoras();
}

function pintarAjustes() {
  const caja = $("#panelAjustes");
  if (!caja) return;
  if (!puedo("config")) { caja.innerHTML = ""; return; }

  const prendido = !!AJUSTES.teclado_en_pantalla;
  const minutos = AJUSTES.bloqueo_minutos || MINUTOS_QUIETO;
  const piloto = AJUSTES.canal_actualizaciones === "piloto";
  caja.innerHTML = `
    <h3>Configurar esta caja</h3>

    ${bloqueImpresion()}

    <div class="ajuste">
      <h4>El local</h4>
      <div class="ajuste__campos">
        <label class="campo"><span>Nombre</span><input id="ajLocalNombre" maxlength="40"></label>
        <label class="campo"><span>RUT</span>
          <input id="ajLocalRut" maxlength="14" placeholder="12.345.678-9"></label>
        <label class="campo ajuste__ancho"><span>Dirección</span>
          <input id="ajLocalDireccion" maxlength="80"></label>
      </div>
      <div class="ajuste__fila">
        <button class="btn" data-guardar-local>Guardar los datos del local</button>
        <span class="ayuda" style="margin:0">Salen en el comprobante, en el cierre y en los televisores.</span>
      </div>
    </div>

    <div class="ajuste" id="ajRed"><h4>PIN de red</h4><p class="ayuda">Cargando…</p></div>

    <div class="ajuste">
      <h4>Inventario</h4>
      <label class="marca">
        <input type="checkbox" id="ajInventario" ${usarInventario() ? "checked" : ""}>
        Llevar inventario en este local</label>
      <p class="ayuda" style="margin:8px 0 0">Apágalo si solo quieres vender, sin llevar
        la cuenta de lo que queda. Se esconden Bodega y Por comprar, y no se pide costo
        ni existencias al agregar productos. Lo que ya tenías anotado se conserva:
        al prenderlo de nuevo, retomas desde esos saldos.</p>
    </div>

    ${bloqueBalanza()}

    <div class="ajuste">
      <h4>Bloqueo</h4>
      <label class="campo campo--linea"><span>La caja se bloquea sola después de</span>
        <select id="ajBloqueo">${[1, 2, 3, 5, 10, 15, 30].map((m) =>
          `<option value="${m}"${m === minutos ? " selected" : ""}>${m} minuto${m === 1 ? "" : "s"} sin uso</option>`).join("")}
        </select></label>
      <p class="ayuda" style="margin:8px 0 0">Nunca corta una venta: si hay un pedido armado o
        un diálogo abierto, espera.</p>
    </div>

    <div class="ajuste">
      <h4>Copia de afuera</h4>
      <p class="ayuda" style="margin:0">Cada respaldo se copia también a esta carpeta, y se
        revisa que abra. Conviene una que se sincronice sola con la nube (OneDrive, Google
        Drive, Dropbox) o un pendrive: si el disco de este computador se muere, o se roban
        el computador, las ventas quedan ahí.</p>
      ${estadoAfueraHTML(AJUSTES.respaldo_afuera_estado)}
      <div class="ajuste__fila">
        <input id="ajAfuera" class="ajuste__ruta" value="${esc(AJUSTES.respaldo_afuera || "")}"
               placeholder="Una carpeta de OneDrive, Google Drive o un pendrive">
        <button class="btn" data-guardar-afuera>Guardar</button>
        <button class="btn" data-probar-afuera>Respaldar ahora</button>
      </div>
      <div class="ajuste__lugares" id="ajLugares"></div>
    </div>

    <div class="ajuste">
      <h4>Actualizaciones</h4>
      <label class="campo campo--linea"><span>Recibir</span>
        <select id="ajCanal">
          <option value="estable"${piloto ? "" : " selected"}>Las versiones ya probadas (recomendado)</option>
          <option value="piloto"${piloto ? " selected" : ""}>Las nuevas, antes que nadie</option>
        </select></label>
      <p class="ayuda" style="margin:8px 0 0">Una versión nueva llega primero a un local de
        confianza y, si anda bien, días después a todos.</p>
    </div>

    <div class="ajuste">
      <h4>Si algo falla</h4>
      <p class="ayuda" style="margin:0">Baja un archivo con el registro de errores y el estado
        de la caja —sin tu PIN ni tus claves— y mándalo por WhatsApp a soporte.</p>
      <div class="ajuste__fila"><button class="btn" data-diagnostico>Descargar diagnóstico</button></div>
    </div>

    <div class="ajuste">
      <h4>Teclado</h4>
      <label class="marca">
        <input type="checkbox" id="ajTeclado" ${prendido ? "checked" : ""}>
        Usar el teclado numérico en pantalla</label>
      <p class="ayuda" style="margin:8px 0 0">
        Préndelo si esta caja tiene <b>pantalla táctil</b>. En un computador con
        teclado de verdad estorba: se abre solo y tapa media pantalla justo cuando
        quieres escribir. Apagado, se escribe con el teclado del computador,
        incluido el PIN.
      </p>
    </div>`;
  conectarBalanza();
  conectarImpresion();
  cargarAjustesDelLocal();
}

function estadoAfueraHTML(e) {
  e = e || {};
  if (!e.carpeta) {
    return `<div class="ajuste__alerta">Todavía no hay copia de afuera. Si el disco de este
      computador se muere, se pierden las ventas junto con sus respaldos.</div>`;
  }
  if (!e.cuando) {
    return `<p class="ayuda" style="margin:8px 0 0">Carpeta elegida. La primera copia sale en el
      próximo respaldo.</p>`;
  }
  const cuando = new Date(e.cuando).toLocaleString("es-CL",
    { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  return e.ok
    ? `<p class="ajuste__ok">Última copia: ${esc(cuando)} · se revisó y abre bien${
        e.ventas != null ? ` (${e.ventas} ventas)` : ""}.</p>`
    : `<div class="ajuste__alerta">La última copia falló (${esc(cuando)}): ${esc(e.detalle || "")}</div>`;
}

async function cargarAjustesDelLocal() {
  try {
    const d = await api("/local");
    $("#ajLocalNombre").value = d.nombre || "";
    $("#ajLocalRut").value = d.rut || "";
    $("#ajLocalDireccion").value = d.direccion || "";
  } catch (e) { }
  try { pintarRed(await api("/red")); }
  catch (e) { $("#ajRed").innerHTML = `<h4>PIN de red</h4><p class="ayuda">${esc(e.message)}</p>`; }
  try {
    const lugares = await api("/respaldo/lugares");
    $("#ajLugares").innerHTML = !lugares.length ? "" : "En este computador hay: " + lugares.map((l) =>
      `<button class="btn btn--chico" data-lugar="${esc(l.ruta)}" title="${esc(l.ruta)}">${esc(l.nombre)}</button>`).join(" ");
  } catch (e) { }
}

function pintarRed(r) {
  $("#ajRed").innerHTML = `
    <h4>PIN de red</h4>
    <p class="ayuda" style="margin:0">Lo piden los tablets y los otros computadores del local
      la primera vez que abren la caja. Desde este computador no se pide.</p>
    ${r.de_fabrica ? `<div class="ajuste__alerta">Es el PIN de fábrica, <b>el mismo de todas
      las cajas</b>: cualquiera en el Wi-Fi del local que lo sepa puede abrir la caja.
      Cámbialo por uno propio.</div>` : ""}
    <div class="ajuste__fila">
      <span class="pin-red" id="pinRedValor" data-pin="${esc(r.pin)}">••••••</span>
      <button class="btn btn--chico" data-ver-pin-red>Ver</button>
      ${r.fijo
        ? `<span class="ayuda" style="margin:0">Lo fijó la instalación: no se cambia desde acá.</span>`
        : `<button class="btn" data-nuevo-pin-red>${r.de_fabrica ? "Crear uno propio" : "Cambiar por uno nuevo"}</button>`}
    </div>`;
}

async function guardarAjuste(cambios, mensaje) {
  try {
    const antes = usarInventario();
    AJUSTES = { ...AJUSTES, ...(await api("/ajustes", { method: "PUT", body: JSON.stringify(cambios) })) };
    if (antes !== usarInventario()) aplicarInventario();
    avisar(mensaje);
    reiniciarInactividad();
  } catch (e) { avisar(e.message, true); pintarAjustes(); }
}

async function guardarLocal() {
  try {
    const d = await api("/local", { method: "PUT", body: JSON.stringify({
      nombre: $("#ajLocalNombre").value.trim(), rut: $("#ajLocalRut").value.trim(),
      direccion: $("#ajLocalDireccion").value.trim() }) });
    ponerNombreDelLocal(d.nombre);
    $("#ajLocalRut").value = d.rut;
    avisar("Guardado. Los televisores lo toman en su próxima revisión.");
  } catch (e) { avisar(e.message, true); }
}

async function nuevoPinDeRed() {
  if (!confirm("¿Cambiar el PIN de red?\nLos tablets y computadores que ya habían entrado " +
               "van a tener que escribir el nuevo.")) return;
  try {
    const r = await api("/red/pin", { method: "POST", body: "{}" });
    pintarRed(r);
    $("#pinRedValor").textContent = r.pin;
    avisar("PIN de red nuevo: " + r.pin + ". Anótalo.");
  } catch (e) { avisar(e.message, true); }
}

async function guardarAfuera(ruta) {
  try {
    AJUSTES = { ...AJUSTES, ...(await api("/ajustes", { method: "PUT",
      body: JSON.stringify({ respaldo_afuera: ruta.trim() }) })) };
    pintarAjustes();
    avisar(ruta.trim() ? "Carpeta guardada. Aprieta «Respaldar ahora» para probarla." : "Sin copia de afuera");
  } catch (e) { avisar(e.message, true); }
}

function afueraCorto(a) {
  if (!a || !a.configurado) return "";
  return a.ok ? " y copiado afuera" : " — la copia de afuera falló";
}

async function probarAfuera() {
  try {
    const r = await api("/respaldo", { method: "POST" });
    AJUSTES = { ...AJUSTES, ...(await api("/ajustes")) };
    pintarAjustes();
    if (!r.afuera || !r.afuera.configurado) {
      return avisar("Respaldo hecho en este computador. Falta elegir la carpeta de afuera.", true);
    }
    avisar(r.afuera.ok ? "Respaldo hecho y copiado afuera. La copia abre bien."
                       : "La copia de afuera falló: " + (r.afuera.detalle || ""), !r.afuera.ok);
  } catch (e) { avisar(e.message, true); }
}

async function volverDeVersion() {
  if (!VUELTA || !VUELTA.disponible) return;
  if (!confirm(`¿Volver a la v${VUELTA.version}?\nSe deshace la última actualización. ` +
               "Tus ventas, precios y respaldos no se tocan.")) return;
  try {
    const r = await api("/actualizacion/volver", { method: "POST" });
    if (!r.ok) throw new Error(r.error || "No se pudo volver");
    $("#dialogoVersion").innerHTML = `
      <h2>Volviendo a la v${esc(r.version)}</h2>
      <p class="ayuda">La caja se reinicia sola: la página se recarga en unos segundos.</p>`;
    esperarQueVuelva();
  } catch (e) { avisar(e.message, true); }
}

async function guardarTeclado(prendido) {
  AJUSTES.teclado_en_pantalla = prendido ? 1 : 0;
  if (window.Teclado) Teclado.encender(prendido);
  try {
    await api("/ajustes", { method: "PUT",
      body: JSON.stringify({ teclado_en_pantalla: AJUSTES.teclado_en_pantalla }) });
    avisar(prendido ? "Teclado en pantalla prendido" : "Teclado en pantalla apagado");
  } catch (e) { avisar(e.message, true); }
}

async function pintarVersionAyuda() {
  try {
    const r = await api("/novedades");
    $("#versionAyuda").textContent = "v" + r.actual;
    $("#versionAyuda").dataset.listo = "1";
  } catch (e) { }
}

/* El historial completo de versiones, para saber qué trae la que uno tiene. */
async function dialogoNovedades() {
  const r = await api("/novedades");
  $("#dialogoVersion").className = "dialogo dialogo--ancho";
  $("#dialogoVersion").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Qué trae cada versión</h2>
    <p class="ayuda">Tienes la <b>v${esc(r.actual)}</b>. Acá está todo lo que fue
      cambiando, de lo más nuevo a lo más viejo.</p>
    <div class="novedades" style="max-height:56vh">
      ${r.versiones.map((v) => `
        <div class="version-fila ${v.version === r.actual ? "es-la-tuya" : ""}">
          <div class="version-fila__tit">
            <b>v${esc(v.version)} · ${esc(v.nombre)}</b>
            <span>${esc(v.fecha)}${v.version === r.actual ? " · la que tienes" : ""}</span>
          </div>
          <p>${esc(v.novedades)}</p>
        </div>`).join("")}
    </div>
    <div class="dialogo__pie">
      <button class="btn" data-cerrar-capa>Cerrar</button>
    </div>`;
  $("#capaVersion").classList.add("is-on");
}

/* ---------------- el descuadre, mirado de cerca ----------------
   Guardar la diferencia no sirve de nada si después no hay dónde mirarla. Esto
   contesta las dos preguntas que se hacen de verdad: "¿cuánto llevamos
   descuadrado?" y "¿en qué falló ESE día?". */
let TURNOS_A_LA_VISTA = [];

function resumenDeDescuadres(turnos) {
  const cerrados = turnos.filter((t) => t.diferencia !== null);
  if (!cerrados.length) return "";
  const suma = cerrados.reduce((n, t) => n + t.diferencia, 0);
  const malos = cerrados.filter((t) => t.diferencia !== 0);
  return `
    <tr class="resumen-turno__total">
      <td colspan="5"><b>${cerrados.length} cierre${cerrados.length === 1 ? "" : "s"}</b>
        · ${malos.length ? `${malos.length} no cuadró${malos.length === 1 ? "" : "n"}`
                         : "todos cuadraron"}</td>
      <td class="num"><b class="${suma === 0 ? "ok" : "mal"}">${suma === 0 ? "cuadra" : clp(suma)}</b></td>
      <td></td>
    </tr>`;
}

function dialogoCierre(turnoId) {
  const t = TURNOS_A_LA_VISTA.find((x) => x.id === turnoId);
  if (!t) return;
  const d = t.diferencia;
  const conteo = t.conteo_cierre || {};
  const hayConteo = Object.keys(conteo).length > 0;

  $("#dialogoBodega").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Cierre del ${new Date(t.abierto_at).toLocaleDateString("es-CL",
        { day: "2-digit", month: "long" })}</h2>
    <p class="ayuda">Abrió ${esc(t.abrio || t.cajero || "—")}${
      t.cerro ? ` · cerró ${esc(t.cerro)}` : ""}.
      ${(t.estuvieron || []).length
        ? "Estuvieron: " + t.estuvieron.map((g) => `${esc(g.nombre)} (${horasYminutos(g.minutos)})`).join(", ")
        : ""}</p>

    ${resumenDelTurno(t)}

    <div class="cuadre ${d === 0 ? "cuadre--ok" : "cuadre--mal"}">
      <div class="cuadre__linea"><span>Fondo con el que abrió</span><span>${clp(t.monto_inicial)}</span></div>
      <div class="cuadre__linea"><span>Ventas en efectivo</span><span>${clp(t.ventas_efectivo)}</span></div>
      <div class="cuadre__linea"><span>Debería haber</span><span>${clp(t.efectivo_esperado)}</span></div>
      <div class="cuadre__linea"><span>Contó</span><span>${clp(t.efectivo_contado || 0)}</span></div>
      <div class="cuadre__linea cuadre__dif">
        <span>${d === 0 ? "Cuadró exacto" : d > 0 ? "Sobró" : "Faltó"}</span>
        <span>${d === 0 ? "✓" : clp(Math.abs(d))}</span>
      </div>
    </div>

    ${hayConteo ? `
      <div class="tarjetas">
        <div class="tarjetas__tit">Cómo estaba el cajón</div>
        <p class="ayuda" style="margin:0">${DENOMINACIONES.filter((v) => conteo[v])
          .map((v) => `${clp(v)} × ${conteo[v]}`).join(" · ")}</p>
      </div>` : ""}

    ${(t.medios || []).some((m) => m.declarado != null) ? `
      <div class="tarjetas">
        <div class="tarjetas__tit">Contra el banco</div>
        ${t.medios.filter((m) => m.declarado != null).map((m) => `
          <div class="cuadre__linea" style="padding:6px 0">
            <span>${esc(m.nombre)} · deberían ser ${clp(m.esperado)}</span>
            <span class="${m.diferencia === 0 ? "ok" : "mal"}">${clp(m.declarado)}${
              m.diferencia ? ` (${m.diferencia > 0 ? "+" : ""}${clp(m.diferencia)})` : " ✓"}</span>
          </div>`).join("")}
      </div>` : ""}

    ${t.nota ? `<p class="ayuda"><b>Nota:</b> ${esc(t.nota)}</p>` : ""}

    <div class="dialogo__pie">
      <button class="btn" data-cierre="${t.id}">Imprimir</button>
      <button class="btn btn--cobrar" data-cerrar-capa style="width:auto">Cerrar</button>
    </div>`;
  $("#capaBodega").classList.add("is-on");
}

/* ---- "se vende tal cual" ----
   El atajo para lo que se compra hecho y se vende igual: un pastel, un alfajor,
   una botella. Sin esto había que entender la palabra "insumo" y crear uno a
   mano, que es exactamente donde la gente se pierde. */
/* ---------------- cuánto cobrar ----------------
   Hasta acá el precio se ponía a ojo y el margen se veía DESPUÉS, cuando ya
   estaba decidido. Esto lo da vuelta: escribes lo que te cuesta y la pantalla
   propone un precio, que se toma o se pisa.

   El margen es SOBRE LA VENTA, no sobre el costo. Es la trampa clásica de poner
   precios —un 50% de margen es cobrar el doble; "50% sobre el costo" sería
   cobrar 1,5 veces y se gana bastante menos—, así que la pantalla escribe las
   dos formas al lado y no obliga a nadie a saberse la diferencia.

   La cuenta vive SOLO acá y no también en el servidor a propósito: es una
   sugerencia que se recalcula con cada tecla, nunca un dato que se guarde.
   Lo que sí guarda el servidor es el margen elegido (tabla Ajuste). */
let AJUSTES = { margen_sugerido: 50, redondeo_precio: 50, usar_inventario: 1 };

function usarInventario() {
  return AJUSTES.usar_inventario !== 0;
}

function aplicarInventario() {
  const activo = usarInventario();
  $(".tab[data-vista='inventario']").hidden = !activo;
  const interruptor = $("#ajInventario");
  if (interruptor) interruptor.checked = activo;
  if (!activo) {
    if ($(".vista.is-on")?.dataset.vista === "inventario") verVista("caja");
    ["#capaBodega", "#capaInsumo"].forEach((id) => $(id).classList.remove("is-on"));
  }
  const zona = $("#zonaTalCual");
  if (zona) {
    zona.style.display = activo ? "" : "none";
    if (!activo) zona.innerHTML = "";
    else {
      const p = productoDeLaCarta(+zona.dataset.producto);
      if (p) pintarTalCual(p);
    }
  }
  pintarGuias();
}

async function cargarAjustes() {
  const antes = usarInventario();
  try { AJUSTES = { ...AJUSTES, ...(await api("/ajustes")) }; }
  catch (e) { }        // con los valores por defecto la caja funciona igual
  if (antes !== usarInventario()) aplicarInventario();
}

/* Lo que el dueño escribe es lo que PAGA, y puede venir de dos partes.

   Comprando en el supermercado, el precio de la boleta ya trae el IVA. Comprando
   con factura, el de la factura es NETO: sugerir un precio de venta sobre ese
   número daría un margen que no existe, porque al vender hay que enterar el 19%
   que ahí no está. Por eso el precio de venta se saca SIEMPRE del costo con IVA:
   así el margen que se pide es el margen que queda. */
function costoConIva(escrito, yaTraeIva) {
  const n = Math.max(0, Math.round(escrito) || 0);
  return yaTraeIva ? n : Math.round(n * (1 + IVA));
}

function precioSugerido(costo, margenPct) {
  costo = Math.max(0, Math.round(costo) || 0);
  if (!costo) return 0;
  // 100% de margen es precio infinito: el tope lo pone el servidor, pero acá
  // también, porque el campo lo escribe una persona.
  const m = Math.min(Math.max(Math.round(margenPct) || 0, 0), 95);
  const bruto = costo * 100 / (100 - m);
  const paso = AJUSTES.redondeo_precio || 1;
  // Hacia ARRIBA: el margen pedido es un piso, no algo que el redondeo se coma.
  return Math.ceil(bruto / paso) * paso;
}

/* El recuadro del sugerido. `destino` es el id del campo de precio que se pisa
   al aceptar; sin costo escrito no se dibuja nada. */
function bloqueSugerido(costo, destino) {
  if (!costo) return "";
  return `
    <div class="sugerido" data-costo="${costo}" data-destino="${destino}">
      <div class="sugerido__tit">Qué cobrar</div>
      <div class="sugerido__cifra">
        <b data-sug-precio></b>
        <button class="btn btn--chico" data-usar-sugerido>Usar este precio</button>
      </div>
      <p class="sugerido__cuenta" data-sug-cuenta></p>
      <div class="sugerido__margenes">
        <span>Margen</span>
        ${[40, 50, 60, 70, 75].map((c) => `<button class="chip"
          data-margen="${c}">${c}%</button>`).join("")}
        <input type="text" inputmode="numeric" data-margen-libre
               aria-label="Otro margen"><span>%</span>
      </div>
    </div>`;
}

/* Recalcula los números SIN rehacer el recuadro: si se rehiciera, el campo del
   margen perdería el foco a media escritura. */
function refrescarSugerido() {
  const caja = $(".sugerido");
  if (!caja) return;
  const costo = +caja.dataset.costo || 0;
  const m = AJUSTES.margen_sugerido;
  const precio = precioSugerido(costo, m);
  const veces = costo ? (precio / costo).toFixed(1).replace(".", ",") : "0";

  caja.querySelector("[data-sug-precio]").textContent = clp(precio);
  caja.querySelector("[data-sug-cuenta]").innerHTML =
    `Te quedan <b>${clp(precio - costo)}</b> de cada venta · es <b>${veces} veces</b> `
    + `lo que te costó. El IVA ya va incluido en ese precio.`;
  caja.querySelectorAll("[data-margen]").forEach((b) =>
    b.classList.toggle("is-on", +b.dataset.margen === m));
  const libre = caja.querySelector("[data-margen-libre]");
  if (document.activeElement !== libre) libre.value = m;
}

/* Guardar el margen es del dueño: es cuánto gana el local, no una preferencia
   de pantalla. Si no puede guardarlo, igual se le mueve el sugerido en su
   pantalla — negarle la cuenta no protege nada. */
let relojMargen = null;

function elegirMargen(pct) {
  AJUSTES.margen_sugerido = Math.min(Math.max(Math.round(pct) || 0, 0), 95);
  refrescarSugerido();               // el número se mueve al toque
  if (!puedo("config")) return;      // el cajero lo mueve en su pantalla y ya

  // El guardado espera: escribir "60" a mano son dos teclas, y sin esto serían
  // dos escrituras a la base, la primera con un 6 que nadie quiso guardar.
  clearTimeout(relojMargen);
  relojMargen = setTimeout(() => {
    api("/ajustes", { method: "PUT",
      body: JSON.stringify({ margen_sugerido: AJUSTES.margen_sugerido }) })
      .catch(() => { });             // no poder guardarlo no invalida la cuenta
  }, 700);
}

async function pintarTalCual(p) {
  const zona = $("#zonaTalCual");
  if (!zona) return;
  zona.style.display = usarInventario() ? "" : "none";
  if (!usarInventario()) { zona.innerHTML = ""; return; }
  /* La cantidad se pregunta UNA vez: cuando se empieza a contar algo que no se
     contaba. Si ya se lleva la cuenta, el número vive en la Bodega — volver a
     escribirlo acá lo sumaría encima de lo que ya hay. */
  const empieza = !p.llevar_cuenta;
  zona.innerHTML = `<label class="marca"><input id="fCuenta" type="checkbox" ${p.llevar_cuenta ? "checked" : ""}>
    Llevar la cuenta de este</label>` + (empieza ? `
    <div id="fCuantosHay" hidden>
      <label class="campo" style="margin:10px 0 0"><span>¿Cuántos hay ahora?</span>
        <input id="fStockInicial" type="text" inputmode="numeric" placeholder="0"></label>
      <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Para partir con la
        cuenta al día. Si no sabes, déjalo vacío y cuéntalos en Bodega cuando
        puedas.</p>
    </div>` : "");
  const casilla = $("#fCuenta");
  if (casilla && casilla.addEventListener) {
    casilla.addEventListener("change", () => {
      const caja = $("#fCuantosHay");
      if (caja) caja.hidden = !casilla.checked;
    });
  }
}

/* ---------------- arranque y eventos ---------------- */
function reloj() {
  $("#reloj").textContent = new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false });
}

/* Ruteo por hash: refrescar la página no devuelve al cajero a la caja sin
   avisar, y se puede dejar "El día" abierto en otra pestaña. */
const VISTAS = ["caja", "dia", "carta", "inventario", "guias"];

/* En Windows el contenido web no puede quitar el marco de la aplicación.
   El puente usa la ventana nativa; en navegador usamos su API de pantalla completa. */
let pantallaCompletaNativa = false;
let cambiandoPantallaCompleta = false;

function pintarPantallaCompleta() {
  const activa = pantallaCompletaNativa || !!document.fullscreenElement;
  const boton = $("#btnPantallaCompleta");
  const nombre = activa ? "Salir de pantalla completa" : "Pantalla completa";
  boton.setAttribute("aria-pressed", String(activa));
  boton.setAttribute("aria-label", nombre);
  boton.title = nombre + " (F11)";
  boton.textContent = activa ? "↙" : "⛶";
}

async function sincronizarPantallaCompleta() {
  const puente = window.pywebview && window.pywebview.api;
  if (puente && puente.pantalla_completa) {
    try { pantallaCompletaNativa = await puente.pantalla_completa(); } catch (e) {}
  }
  pintarPantallaCompleta();
}

async function alternarPantallaCompleta(salir = false) {
  if (cambiandoPantallaCompleta) return;
  cambiandoPantallaCompleta = true;
  const boton = $("#btnPantallaCompleta");
  boton.disabled = true;
  try {
    const puente = window.pywebview && window.pywebview.api;
    if (puente && puente.pantalla_completa) {
      const actual = await puente.pantalla_completa();
      pantallaCompletaNativa = await puente.pantalla_completa(salir ? false : !actual);
    } else if (window.pywebview) {
      throw new Error("La ventana todavía se está preparando. Vuelve a intentar en un momento.");
    } else if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else if (!salir) {
      await document.documentElement.requestFullscreen();
    }
  } catch (e) {
    avisar("No se pudo cambiar la pantalla completa. " + e.message, true);
  } finally {
    cambiandoPantallaCompleta = false;
    boton.disabled = false;
    pintarPantallaCompleta();
  }
}

window.addEventListener("pywebviewready", sincronizarPantallaCompleta);
document.addEventListener("fullscreenchange", pintarPantallaCompleta);

function verVista(nombre, empujarHash = true) {
  if (!VISTAS.includes(nombre)) nombre = "caja";
  if (nombre === "inventario" && !usarInventario()) nombre = "caja";
  $$(".tab").forEach((b) => b.classList.toggle("is-on", b.dataset.vista === nombre));
  $$(".vista").forEach((v) => v.classList.toggle("is-on", v.dataset.vista === nombre));
  if (empujarHash) location.hash = "#/" + nombre;
  if (nombre === "dia") { periodoQueCorresponde(); cargarDia(); }
  if (nombre === "inventario") cargarBodega();
  if (nombre === "guias") pintarGuias();
}

function vistaDelHash() {
  return (location.hash || "").replace(/^#\/?/, "") || "caja";
}
window.addEventListener("hashchange", () => verVista(vistaDelHash(), false));

document.addEventListener("click", (e) => {
  const t = e.target;
  const cerca = (attr) => t.closest(`[${attr}]`);

  // OJO: solo las pestañas de arriba, no cualquier cosa con data-vista.
  // El <main> de cada vista también lo lleva, y con `cerca("data-vista")` este
  // primer if se tragaba TODOS los clics de adentro: no se podía ni agregar un
  // producto al pedido.
  const pestana = t.closest(".tab[data-vista]");
  if (pestana) return verVista(pestana.dataset.vista);
  if (cerca("data-cat")) {
    catActiva = +cerca("data-cat").dataset.cat;
    try { localStorage.setItem("pos.categoria", catActiva); } catch (e) {}
    $("#buscar").value = "";
    return buscar("");
  }
  if (cerca("data-prod")) return agregar(+cerca("data-prod").dataset.prod);
  if (cerca("data-mas")) return cambiarCantidad(+cerca("data-mas").dataset.mas, 1);
  if (cerca("data-menos")) return cambiarCantidad(+cerca("data-menos").dataset.menos, -1);
  if (cerca("data-quitar-linea")) return quitarLineaDelPedido(+cerca("data-quitar-linea").dataset.quitarLinea);
  if (cerca("data-plegar-cat")) return alternarCategoriaCarta(+cerca("data-plegar-cat").dataset.plegarCat);
  if (cerca("data-anular")) return anular(+cerca("data-anular").dataset.anular);
  if (cerca("data-imprimir")) return imprimir(`/comprobante/${cerca("data-imprimir").dataset.imprimir}`);
  if (cerca("data-ver-cierre")) return dialogoCierre(+cerca("data-ver-cierre").dataset.verCierre);
  if (cerca("data-cierre")) return imprimir(`/cierre/${cerca("data-cierre").dataset.cierre}`);
  if (cerca("data-periodo")) {
    periodo = cerca("data-periodo").dataset.periodo;
    // Lo eligió con el dedo: de acá en adelante no se le cambia solo al volver
    // a entrar, aunque haya caja abierta.
    periodoALaMano = true;
    $$(".periodo").forEach((b) => b.classList.toggle("is-on", b.dataset.periodo === periodo));
    return cargarDia();
  }
  if (cerca("data-guardar")) return guardarProducto(+cerca("data-guardar").dataset.guardar);
  if (cerca("data-editar")) return abrirFichaProducto(+cerca("data-editar").dataset.editar);
  if (cerca("data-nuevo-en")) return nuevoProducto(+cerca("data-nuevo-en").dataset.nuevoEn);
  if (cerca("data-cat-editar")) return editarCategoria(+cerca("data-cat-editar").dataset.catEditar);
  if (cerca("data-cat-guardar")) return guardarCategoria(+cerca("data-cat-guardar").dataset.catGuardar);
  if (cerca("data-cat-cancelar")) return pintarEditorCarta();
  if (cerca("data-cat-borrar")) return borrarCategoria(+cerca("data-cat-borrar").dataset.catBorrar);
  if (cerca("data-paga")) {
    const campo = $("#pagaCon");
    campo.value = cerca("data-paga").dataset.paga;
    // Disparar "input" y no llamar directo: el teclado en pantalla escucha
    // ahí para no quedarse mostrando el monto anterior.
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  if (cerca("data-desc")) {
    const pct = +cerca("data-desc").dataset.desc;
    // Redondeado a $10 para que el vuelto no quede con monedas que no existen.
    $("#descuento").value = pct ? Math.round(totalCarrito() * pct / 100 / 10) * 10 : "";
    actualizarCobro();
    return;
  }
  if (cerca("data-sacar-plata")) return abrirFormRetiro(TURNO.turno, "retiro");
  if (cerca("data-meter-plata")) return abrirFormRetiro(TURNO.turno, "ingreso");
  if (cerca("data-cerrar-form-retiro")) {
    const f = $("#sacarPlataForm");
    if (f) { f.hidden = true; f.innerHTML = ""; }
    return;
  }
  if (cerca("data-anular-retiro")) return anularRetiro(+cerca("data-anular-retiro").dataset.anularRetiro);
  if (cerca("data-cerrar-capa")) {
    $$(".capa").forEach((c) => c.classList.remove("is-on"));
    // La puerta vuelve si se cerró el arqueo sin abrir la caja. Sin esto el
    // programa quedaría usable con la caja cerrada, que es justo lo que la
    // puerta existe para impedir.
    return pintarPuertaDeLaCaja(TURNO);
  }

  if (cerca("data-sumar-medio")) {
    // Aparece la fila que estaba escondida y se va su tilde. No se recarga nada: la fila
    // ya estaba en el formulario, solo no se veía.
    const cual = cerca("data-sumar-medio").dataset.sumarMedio;
    const fila = $(`[data-medio-fila="${cual}"]`);
    if (fila) { fila.hidden = false; fila.querySelector("input")?.focus(); }
    cerca("data-sumar-medio").remove();
    const barra = $(".tarjetas__sumar");
    if (barra && !barra.querySelector("[data-sumar-medio]")) barra.remove();
    return;
  }

  if (t.closest("#medios .medio")) {
    medioPago = t.closest(".medio").dataset.medio;
    $$("#medios .medio").forEach((b) => b.classList.toggle("is-on", b.dataset.medio === medioPago));
    $("#bloqueEfectivo").style.display = medioPago === "efectivo" ? "" : "none";
    return calcularVuelto();
  }
  if (t.id === "limpiarBuscar") { $("#buscar").value = ""; $("#buscar").focus(); return buscar(""); }
  if (t.id === "limpiarBuscarCarta") {
    $("#buscarCarta").value = "";
    $("#buscarCarta").focus();
    return filtrarEditorCarta();
  }
  if (t.closest("#btnPantallaCompleta")) return alternarPantallaCompleta();
  if (t.id === "btnNuevaCat") return nuevaCategoria();
  if (t.id === "btnHoy") { $("#fechaDia").value = hoyISO(); turnoElegido = null; return cargarDia(); }
  if (t.id === "btnExportar") {
    const [d1, d2] = rangoDelPeriodo($("#fechaDia").value || hoyISO());
    // Dos archivos: el resumen de ventas y el detalle por producto.
    window.open(`/api/v1/exportar/ventas?desde=${d1}&hasta=${d2}`, "_blank");
    setTimeout(() => window.open(`/api/v1/exportar/detalle?desde=${d1}&hasta=${d2}`, "_blank"), 400);
    // El archivo del contador va SIEMPRE por fechas, aunque en pantalla se esté
    // mirando un turno: al contador se le entregan días, no turnos.
    return avisar(`Descargando ${periodo === "semana" || periodo === "mes"
      ? "el " + periodo : "el día"}`);
  }
  if (t.id === "btnRespaldar") {
    return api("/respaldo", { method: "POST" })
      .then((r) => avisar(r.ok ? `Respaldo guardado (${r.archivo}, ${r.tamano_kb} KB)${afueraCorto(r.afuera)}`
                                 : r.detalle, !r.ok || !!(r.afuera && r.afuera.configurado && !r.afuera.ok)))
      .catch((err) => avisar(err.message, true));
  }
  if (t.id === "btnCobrar") return abrirCobro();
  if (t.id === "btnVarios") return dialogoVarios();
  if (t.id === "agregarVarios") return agregarVarios();
  if (t.id === "btnLimpiar") { carrito = []; olvidarAvisos(); return pintarCarrito(); }
  if (t.id === "cobroCancelar") return $("#capaCobro").classList.remove("is-on");
  if (t.id === "cobroConfirmar") return confirmarVenta();
  if (t.id === "turnoEstado") return dialogoTurno();
  if (t.id === "version") return dialogoVersion();
  if (t.id === "tAbrir") {
    return api("/turnos/abrir", { method: "POST", body: JSON.stringify({
      cajero: $("#tCajero").value.trim(), conteo: conteoActual,
      monto_inicial: totalConteo() }) })
      .then((r) => { $("#capaTurno").classList.remove("is-on"); cargarTurno();
        avisar(`Caja abierta con ${clp(r.monto_inicial)} de fondo`); })
      .catch((err) => avisar(err.message, true));
  }
  if (t.id === "tCerrar") {
    return api("/turnos/cerrar", { method: "POST", body: JSON.stringify({
      conteo: conteoActual,
      efectivo_contado: totalConteo(),
      fondo_siguiente: soloNumeros(($("#tFondo") || {}).value || 0),
      medios: mediosDeclarados(),
      propinas_medios: propinasDeclaradas(),
      propinas_pagadas: soloNumeros(($("#tPropinasPagadas") || {}).value || 0),
      nota: (($("#tNota") || {}).value || "").trim() }) })
      .then((r) => { olvidarConteo();
        $("#capaTurno").classList.remove("is-on"); cargarTurno();
        avisar(r.diferencia === 0 ? "Caja cerrada, cuadra exacto"
          : `Caja cerrada · ${r.diferencia > 0 ? "sobran" : "faltan"} ${clp(Math.abs(r.diferencia))}`);
        imprimir(`/cierre/${r.id}`); })
      .catch((err) => avisar(err.message, true));
  }
  // ---- candado ----
  if (cerca("data-entrar")) return pedirPin(+cerca("data-entrar").dataset.entrar);
  if (cerca("data-otro-usuario")) return mostrarCandado();
  if (cerca("data-reintentar-candado")) return mostrarCandado();
  if (cerca("data-recargar")) return location.reload();
  if (cerca("data-guardar-local")) return guardarLocal();
  if (cerca("data-ver-pin-red")) {
    const v = $("#pinRedValor");
    v.textContent = v.textContent.includes("•") ? v.dataset.pin : "••••••";
    return;
  }
  if (cerca("data-nuevo-pin-red")) return nuevoPinDeRed();
  if (cerca("data-guardar-afuera")) return guardarAfuera($("#ajAfuera").value);
  if (cerca("data-probar-afuera")) return probarAfuera();
  if (cerca("data-lugar")) { $("#ajAfuera").value = cerca("data-lugar").dataset.lugar; return; }
  if (cerca("data-diagnostico")) { window.open("/api/v1/diagnostico", "_blank"); return; }
  if (cerca("data-volver-version")) return volverDeVersion();
  if (t.id === "ajTeclado") return guardarTeclado(t.checked);
  if (t.id === "ajInventario") return guardarAjuste({ usar_inventario: t.checked ? 1 : 0 },
    t.checked ? "Listo: vuelves a llevar inventario" : "Listo: puedes vender sin llevar inventario");
  if (t.id === "ajBloqueo") return guardarAjuste({ bloqueo_minutos: +t.value },
    `Listo: la caja se bloquea después de ${t.value} min sin uso`);
  if (t.id === "ajCanal") return guardarAjuste({ canal_actualizaciones: t.value },
    t.value === "piloto" ? "Vas a recibir las versiones nuevas antes que nadie"
                         : "Vas a recibir solo las versiones ya probadas");
  if (t.id === "abrirLaCaja") return dialogoTurno();
  if (t.id === "salirSinCaja") return salirDeLaCaja("cambio");
  if (t.id === "crearPrimero") return crearPrimerUsuario();
  if (t.id === "quienEsta" || t.closest("#quienEsta")) {
    if (!puedoIrme()) {
      return avisar("Tienes la caja abierta. Ciérrala antes de salir o de cambiar "
                    + "de usuario: si no, tu turno queda a medias.", true);
    }
    return salirDeLaCaja("cambio");
  }
  if (t.id === "cambiarParaCerrar" || t.closest("#cambiarParaCerrar")) {
    $("#capaTurno").classList.remove("is-on");
    return salirDeLaCaja("cambio");
  }

  // ---- el lector de codigos ----
  if (cerca("data-guardar-codigo"))
    return guardarProductoDelCodigo(cerca("data-guardar-codigo").dataset.guardarCodigo);
  if (cerca("data-pegar-codigo"))
    return pegarCodigo(+cerca("data-pegar-codigo").dataset.pegarCodigo);
  if (cerca("data-sacar-codigo")) {
    const c = cerca("data-sacar-codigo").dataset.sacarCodigo;
    if (FICHA_ABIERTA == null) {
      // Producto nuevo: el código solo está anotado acá, no hay nada que borrar en la base.
      CODIGOS_NUEVOS = CODIGOS_NUEVOS.filter((x) => x !== c);
      return pintarCodigos(null);
    }
    return api("/codigos/" + encodeURIComponent(c), { method: "DELETE" })
      .then(() => { avisar("Código sacado"); pintarCodigos(FICHA_ABIERTA); })
      .catch((e) => avisar(e.message, true));
  }

  // ---- cuanto cobrar ----
  if (cerca("data-usar-sugerido")) {
    const caja = cerca("data-usar-sugerido").closest(".sugerido");
    const campo = $("#" + caja.dataset.destino);
    if (!campo) return avisar("No encuentro el campo del precio", true);
    campo.value = precioSugerido(+caja.dataset.costo, AJUSTES.margen_sugerido);
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    // No se guarda solo: el precio se escribe cuando la persona toca Guardar.
    return avisar("Precio puesto. Puedes cambiarlo antes de guardar.");
  }
  if (cerca("data-margen")) return elegirMargen(+cerca("data-margen").dataset.margen);

  // ---- el equipo ----
  if (t.closest("#verEquipo")) return dialogoEquipo();
  if (cerca("data-editar-usuario")) {
    const v = cerca("data-editar-usuario").dataset.editarUsuario;
    return formUsuario(v === "nuevo" ? 0 : +v);
  }
  if (cerca("data-equipo-volver")) return dialogoEquipo();
  if (cerca("data-rol")) {
    const b = cerca("data-rol");
    $$("#uRol .medio").forEach((o) => o.classList.toggle("is-on", o === b));
    if ($("#uHeredar").checked) marcarPermisosPersona(PERMISOS_EQUIPO.roles[b.dataset.rol] || []);
    return;
  }
  if (cerca("data-guardar-usuario"))
    return guardarUsuario(+cerca("data-guardar-usuario").dataset.guardarUsuario);
  if (cerca("data-sacar-usuario"))
    return sacarUsuario(+cerca("data-sacar-usuario").dataset.sacarUsuario);
  if (cerca("data-revivir-usuario"))
    return revivirUsuario(+cerca("data-revivir-usuario").dataset.revivirUsuario);

  // ---- bodega ----
  if (cerca("data-cantidad-bodega")) return editarCantidadBodega(+cerca("data-cantidad-bodega").dataset.cantidadBodega);
  if (cerca("data-cancelar-cantidad")) {
    $("#editarCantidad" + cerca("data-cancelar-cantidad").dataset.cancelarCantidad).hidden = true;
    return;
  }
  if (cerca("data-paso-bodega")) {
    const b = cerca("data-paso-bodega");
    const campo = $("#cantidadBodega" + b.dataset.id);
    campo.value = Math.min(2147483647, Math.max(0, (Number(campo.value) || 0) + Number(b.dataset.pasoBodega)));
    $("#motivoBodega" + b.dataset.id).hidden = true;
    return;
  }
  if (cerca("data-pedir-motivo")) {
    const id = +cerca("data-pedir-motivo").dataset.pedirMotivo;
    if (cantidadBodegaValida(id) !== null) $("#motivoBodega" + id).hidden = false;
    return;
  }
  if (cerca("data-guardar-cantidad")) {
    const b = cerca("data-guardar-cantidad");
    return guardarCantidadBodega(+b.dataset.guardarCantidad, b.dataset.razon);
  }
  if (cerca("data-ver-receta")) return verRecetaAnterior(+cerca("data-ver-receta").dataset.verReceta);
  if (cerca("data-libro")) return verLibro(+cerca("data-libro").dataset.libro);
  if (cerca("data-insumo")) return dialogoInsumo(+cerca("data-insumo").dataset.insumo);
  if (cerca("data-guardar-insumo"))
    return guardarInsumo(+cerca("data-guardar-insumo").dataset.guardarInsumo || 0);
  if (cerca("data-sacar-insumo")) {
    const id = +cerca("data-sacar-insumo").dataset.sacarInsumo;
    if (!confirm("¿Sacar este insumo de la bodega? Los movimientos viejos se conservan.")) return;
    return api(`/inventario/insumos/${id}`, { method: "DELETE" })
      .then(() => { $("#capaInsumo").classList.remove("is-on"); cargarBodega(); avisar("Listo"); })
      .catch((err) => avisar(err.message, true));
  }
  if (cerca("data-motivo")) { $("#mMotivo").value = cerca("data-motivo").dataset.motivo; return; }
  if (cerca("data-dibujo")) {
    const b = cerca("data-dibujo");
    $("#fDibujo").value = b.dataset.dibujo;
    $$(".dibujo-op").forEach((x) => x.classList.toggle("is-on", x === b));
    return;
  }
  if (cerca("data-guia")) return pintarGuias(cerca("data-guia").dataset.guia);
  if (t.id === "versionAyuda") return dialogoNovedades();
  if (cerca("data-copiar")) {
    const txt = cerca("data-copiar").dataset.copiar;
    if (navigator.clipboard) navigator.clipboard.writeText(txt).then(() => avisar("Dirección copiada"));
    else avisar("Selecciona la dirección y cópiala con Ctrl+C");
    return;
  }
  if (t.id === "btnNuevoInsumo") return dialogoInsumo(0);
  if (t.id === "btnCompra") return dialogoCompra();
  if (t.id === "btnMerma") return dialogoMerma();
  if (t.id === "btnConteo") return dialogoConteo();
  if (t.id === "guardarConteo") return guardarConteo();
  if (t.id === "guardarCompra") {
    return api("/inventario/compras", { method: "POST", body: JSON.stringify({
      insumo_id: +$("#cInsumo").value,
      envases: Math.max(1, soloNumeros($("#cEnvases").value)),
      compra_costo: $("#cCosto").value ? soloNumeros($("#cCosto").value) : null }) })
      .then((r) => { $("#capaBodega").classList.remove("is-on"); cargarBodega();
        avisar(`Anotado · quedan ${r.muestra}`); })
      .catch((err) => avisar(err.message, true));
  }
  if (t.id === "guardarMerma") {
    return api("/inventario/mermas", { method: "POST", body: JSON.stringify({
      insumo_id: +$("#mInsumo").value,
      cantidad: soloNumeros($("#mCantidad").value),
      motivo: ($("#mMotivo").value || "").trim() }) })
      .then((r) => { $("#capaBodega").classList.remove("is-on"); cargarBodega();
        avisar(`Anotado · se perdieron ${clp(r.costo)}`); })
      .catch((err) => avisar(err.message, true));
  }

  // ---- traer la carta ----
  if (t.id === "btnImportar") return dialogoImportar();
  if (t.id === "leerCarta") return leerTexto();
  if (t.id === "aplicarCarta") return aplicarImportacion();

  // Tocar el fondo NO cierra nada. En una pantalla táctil el dedo roza el borde
  // todo el rato, y cada roce costaba volver a hacer el trabajo entero: contar
  // el cajón de nuevo, rearmar el cobro, reescribir la ficha del producto.
  // Los diálogos se cierran con su botón o con la X, que están para eso.
});

function actualizarCobro() {
  const desc = soloNumeros($("#descuento").value);
  $("#cobroTotal").textContent = desc
    ? `${clp(aCobrar() - soloNumeros($("#propina").value))} (antes ${clp(totalCarrito())})`
    : clp(totalCarrito());
  pintarRapidos();
  calcularVuelto();
  if (mixto) pintarMixtoResto();     // el descuento cambia lo que hay que repartir
}

// El interruptor de pago mixto y los montos de cada medio.
$("#pagoMixto").addEventListener("change", (e) => cambiarAMixto(e.target.checked));
$("#mixtoGrid").addEventListener("input", (e) => {
  const campo = e.target.closest("[data-mixto]");
  if (!campo) return;
  mixtoMontos[campo.dataset.mixto] = soloNumeros(campo.value);
  pintarMixtoResto();
});

$("#buscar").addEventListener("input", (e) => buscar(e.target.value));
$("#buscarCarta").addEventListener("input", filtrarEditorCarta);
$("#buscarCarta").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; filtrarEditorCarta(); }
});
$("#buscar").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; buscar(""); }
});
// Al cambiar de día los turnos son otros: se suelta el elegido para que el
// selector vuelva a partir del que esté abierto (o de ninguno).
$("#fechaDia").addEventListener("change", () => { turnoElegido = null; cargarDia(); });
$("#selTurno").addEventListener("change", (e) => {
  turnoElegido = e.target.value ? +e.target.value : null;
  cargarDia();
});
$("#pagaCon").addEventListener("input", calcularVuelto);
$("#propina").addEventListener("input", actualizarCobro);
$("#descuento").addEventListener("input", actualizarCobro);

document.addEventListener("keydown", (e) => {
  if (e.key === "F11") {
    e.preventDefault();
    return alternarPantallaCompleta();
  }
  if (e.key === "Escape" && pantallaCompletaNativa) alternarPantallaCompleta(true);
  // Escape tampoco: es demasiado fácil apretarlo sin querer y perder el trabajo.
  // Para cerrar están la X y el botón Cancelar de cada diálogo.
  if (e.key === "Escape") return Teclado.cerrar();
  // Enter y Espacio sobre un botón o un título plegable activan ese control.
  if (e.target.closest("button, summary")) return;
  if (e.target.tagName === "INPUT") {
    if (e.key === "Enter" && $("#capaCobro").classList.contains("is-on")) confirmarVenta();
    return;
  }
  // Escribir cualquier letra manda el foco al buscador: no hay que apuntarle con el dedo.
  if (!e.ctrlKey && !e.altKey && e.key.length === 1 && /[a-záéíóúñ]/i.test(e.key)
      && !$$(".capa.is-on").length && $(".vista.is-on").dataset.vista === "caja") {
    $("#buscar").focus();
    return;
  }
  if (e.key === "Enter" && carrito.length && !$$(".capa.is-on").length) abrirCobro();
});

(async function iniciar() {
  sincronizarPantallaCompleta();
  reloj();
  setInterval(reloj, 20000);
  // La caja se vigila sola: al volver a la ventana y cada minuto.
  setInterval(vigilarLaCaja, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) vigilarLaCaja(); });
  addEventListener("focus", vigilarLaCaja);
  try {
    const s = await api("/salud");
    NOMBRE_DEL_LOCAL = s.local;
    $("#nombreLocal").textContent = s.local;
    document.title = "Caja · " + s.local;
    pintarConectar(s);
  } catch (e) { avisar("No se pudo conectar con el punto de venta", true); }

  // Los ajustes van PRIMERO: el candado pregunta el PIN de una forma o de otra
  // según haya teclado en pantalla o no. Si se leyeran después, la primera
  // pantalla del día se dibujaría con el valor por defecto y no con el del local.
  await cargarAjustes();
  if (window.Escaner) window.Escaner.alLeer = alEscanear;
  if (window.Teclado) Teclado.encender(!!AJUSTES.teclado_en_pantalla);

  // Y recién ahí, quién está. Si no hay nadie, el candado tapa todo.
  await cargarSesion();
  if (!SESION.entrado) await mostrarCandado();
  else {
    reiniciarInactividad();
    // Una caja recién instalada abre con el asistente: el nombre del local, su
    // RUT y el PIN de red se piden al principio, no cuando alguien se acuerde.
    // Sin gente la sesión es provisoria y la caja abría directo, así que el
    // asistente no aparecía nunca. Una caja que ya vende sin usuarios no lo ve.
    if (SESION.provisorio) {
      try { if ((await api("/candado")).instalacion_nueva) await mostrarCandado(); } catch (e) { }
    }
  }
  await cargarCarta();
  await cargarTurno();
  cargarVersion();
  pintarVersionAyuda();
  pintarAjustes();
  pintarCarrito();
  verVista(vistaDelHash(), false);
})();
