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
// Preferencia del local: si imprime comprobante en cada venta. Queda en este equipo.
let imprimirSiempre = localStorage.getItem("pos.imprimir") === "1";

/* El comprobante se imprime desde un marco escondido, no desde una ventana
   aparte. Es obligatorio: dentro de la ventana de la aplicación (WebView2)
   window.open devuelve null y no se imprimía nada — probado. De paso el
   cajero nunca sale de la caja, que era la intención original.

   La página del comprobante se manda a imprimir sola al cargar, así que acá
   solo hay que ponerla y sacarla después. */
function imprimir(ruta) {
  const anterior = document.getElementById("marcoImpresion");
  if (anterior) anterior.remove();
  const marco = document.createElement("iframe");
  marco.id = "marcoImpresion";
  marco.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  marco.src = ruta;
  document.body.appendChild(marco);
  // 60 s: lo que puede demorar alguien en decidir en el diálogo de impresión.
  setTimeout(() => marco.remove(), 60000);
}

/* ---------------- utilidades ---------------- */
async function api(ruta, opciones = {}) {
  const r = await fetch("/api/v1" + ruta, {
    headers: { "Content-Type": "application/json" },
    ...opciones,
  });
  if (!r.ok) {
    let detalle = "Error " + r.status;
    try { detalle = (await r.json()).detail || detalle; } catch (e) {}
    throw new Error(typeof detalle === "string" ? detalle : JSON.stringify(detalle));
  }
  return r.status === 204 ? null : r.json();
}

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
        <span class="prod__precio">${clp(p.precio)}</span>
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
/* ---------------- agregar al pedido ----------------
   Con TOPE en lo que queda. Antes se podía poner 12 de algo que tenía 3, y el
   inventario quedaba en −9 sin que nadie lo notara hasta el conteo.

   El tope se puede pasar a propósito, y eso es a propósito: el saldo de la
   bodega es lo que dice el programa, no lo que hay en la repisa. Si llegó
   mercadería y nadie la anotó, negarse a vender sería peor que descuadrar el
   inventario — el cliente está ahí con la plata en la mano. Ver CONTRATO,
   decisión 7: el stock avisa. Ahora avisa MEJOR: una vez, y deja seguir.

   Solo topea lo que se vende TAL CUAL. Un capuchino no tiene "cuántos quedan":
   tiene leche y café. */
/* De qué productos ya se avisó en este pedido. Avisar en cada toque sería un
   cartel que nadie lee; avisar una vez y dejar pasar, es un tope de verdad. */
const avisado = new Set();
const olvidarAvisos = () => avisado.clear();

function agregar(id) {
  const cat = CATEGORIAS.find((c) => c.productos.some((p) => p.id === id));
  const p = cat && cat.productos.find((x) => x.id === id);
  if (!p) return;
  sumarAlPedido(p);
}

function sumarAlPedido(p) {
  const ya = carrito.find((l) => l.id === p.id);
  const pide = (ya ? ya.cantidad : 0) + 1;

  if (p.stock != null && pide > p.stock && !avisado.has(p.id)) {
    avisado.add(p.id);
    avisar(p.stock > 0
      ? `Quedan ${p.stock} de ${p.nombre}. Si igual los tienes, sigue agregando.`
      : `${p.nombre} está en cero. Si igual lo tienes, sigue agregando.`, true);
    return;                                  // el primer toque avisa y no suma
  }

  if (ya) ya.cantidad += 1;
  else carrito.push({ id: p.id, nombre: p.nombre, precio: p.precio,
                      cantidad: 1, stock: p.stock });
  pintarCarrito();
}



function cambiarCantidad(id, delta) {
  const l = carrito.find((x) => x.id === id);
  if (!l) return;
  l.cantidad += delta;
  if (l.cantidad <= 0) carrito = carrito.filter((x) => x.id !== id);
  pintarCarrito();
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
  // Con un diálogo abierto que no sea el de la carta, el escaneo no es para
  // vender: puede ser el dueño pegándole un código a un producto.
  const ficha = $("#capaProducto.is-on") && $("#fCodigo");
  if (ficha) return ponerCodigoEnFicha(codigo);

  if (!puedo("vender")) return;

  let r;
  try { r = await api("/codigos/" + encodeURIComponent(codigo)); }
  catch (e) { return avisar(e.message, true); }

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
async function dialogoProductoNuevoPorCodigo(codigo) {
  const cats = CATEGORIAS.filter((c) => c.activa);
  const cual = cats.find((c) => c.id === catActiva) || cats[0];

  $("#dialogoCodigo").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Producto nuevo</h2>
    <div class="codigo-leido">${esc(codigo)}</div>
    <p class="ayuda" id="cdDe">Buscando cómo se llama…</p>
    <label class="campo"><span>¿Qué es?</span>
      <input id="cdNombre" type="text" placeholder="Escríbelo" autocomplete="off"></label>
    <div class="fila2">
      <label class="campo"><span>¿A cuánto lo vendes?</span>
        <input id="cdPrecio" type="text" inputmode="numeric" placeholder="0"></label>
      <label class="campo"><span>¿Cuánto te cuesta?</span>
        <input id="cdCosto" type="text" inputmode="numeric" placeholder="0"></label>
    </div>
    <div id="cdSugerido"></div>
    <label class="campo"><span>¿Dónde va?</span>
      <select id="cdCat">${cats.map((c) =>
        `<option value="${c.id}"${cual && c.id === cual.id ? " selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>
    <label class="campo"><span>¿Cuántos tienes ahora?</span>
      <input id="cdStock" type="text" inputmode="numeric" placeholder="0"></label>
    <p class="ayuda" style="margin-bottom:0">Queda guardado con su código: la próxima vez
      que lo pases por el lector, entra solo al pedido.</p>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Ahora no</button>
      <button class="btn btn--cobrar" data-guardar-codigo="${esc(codigo)}"
              style="width:auto">Guardar y cobrar</button>
    </div>`;
  $("#capaCodigo").classList.add("is-on");
  setTimeout(() => $("#cdNombre").focus(), 60);

  // El sugerido de precio se mueve solo con lo que cuesta.
  $("#cdCosto").addEventListener("input", () => {
    const v = soloNumeros($("#cdCosto").value);
    const caja = $(".sugerido");
    if (caja) return repintarSugerido(v);
    $("#cdSugerido").innerHTML = bloqueSugerido(v, "cdPrecio");
    refrescarSugerido();
  });

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

  const costo = soloNumeros($("#cdCosto").value);
  const stock = soloNumeros($("#cdStock").value);
  try {
    const p = await api("/productos", { method: "POST", body: JSON.stringify({
      categoria_id: +$("#cdCat").value,
      nombre, precio, codigo,
      // Lo que viene del escáner se compra y se vende tal cual, siempre: es una
      // botella, una lata, un paquete. Por eso no se pregunta.
      tal_cual: true, costo, stock_inicial: stock,
    }) });
    $("#capaCodigo").classList.remove("is-on");
    await cargarCarta();
    agregarPorId(p);
    avisar(`${nombre} queda guardado. Ya está en el pedido.`);
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
  try { lista = await api(`/productos/${productoId}/codigos`); } catch (e) { }
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
          <b>${l.nombre}</b>
          <small>${clp(l.precio)} c/u</small>
        </div>
        <div class="cant">
          <button data-menos="${l.id}">−</button>
          <span>${l.cantidad}</span>
          <button data-mas="${l.id}">+</button>
        </div>
        <div class="linea__sub">${clp(l.precio * l.cantidad)}</div>
      </div>`).join("");
  }
  $("#total").textContent = clp(totalCarrito());
  $("#btnCobrar").disabled = carrito.length === 0;
  guardarCarrito();
}

/* ---------------- cobro ---------------- */
function abrirCobro() {
  if (!carrito.length) return;
  medioPago = "efectivo";
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
      lineas: carrito.map((l) => ({ producto_id: l.id, cantidad: l.cantidad })),
      medio_pago: medioPago,
      descuento: soloNumeros($("#descuento").value),
      propina: soloNumeros($("#propina").value),
    };
    const paga = soloNumeros($("#pagaCon").value);
    if (medioPago === "efectivo" && paga) cuerpo.paga_con = paga;

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

let periodo = "dia";

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
  return [f, f];
}

async function cargarDia() {
  const campo = $("#fechaDia");
  if (!campo.value) campo.value = hoyISO();
  const f = campo.value;
  const [desde, hasta] = rangoDelPeriodo(f);
  const [r, lista, turnos] = await Promise.all([
    api(`/resumen?desde=${desde}&hasta=${hasta}`),
    api(`/ventas?fecha=${f}`),
    api(`/turnos?desde=${desde}&hasta=${hasta}`),
  ]);

  $("#kpis").innerHTML = `
    <div class="kpi"><span>Vendido hoy</span><b>${clp(r.total)}</b>
      <small>${r.ventas} venta${r.ventas === 1 ? "" : "s"}</small></div>
    <div class="kpi"><span>Ticket promedio</span><b>${clp(r.ticket_promedio)}</b></div>
    ${r.dias > 1 ? `<div class="kpi"><span>Promedio por día</span><b>${clp(r.promedio_diario)}</b>
      <small>${r.dias} días</small></div>` : ""}
    <div class="kpi"><span>Efectivo</span><b>${clp(r.por_medio.efectivo.total)}</b>
      <small>${r.por_medio.efectivo.cantidad} ventas</small></div>
    <div class="kpi"><span>Tarjetas</span><b>${clp(r.por_medio.debito.total + r.por_medio.credito.total)}</b>
      <small>${r.por_medio.debito.cantidad + r.por_medio.credito.cantidad} ventas</small></div>
    <div class="kpi"><span>Neto / IVA</span><b>${clp(r.neto)}</b>
      <small>IVA ${clp(r.iva)}</small></div>
    ${r.propinas ? `<div class="kpi"><span>Propinas</span><b>${clp(r.propinas)}</b></div>` : ""}
    ${r.anuladas.cantidad ? `<div class="kpi"><span>Anuladas</span><b>${r.anuladas.cantidad}</b>
      <small>${clp(r.anuladas.total)}</small></div>` : ""}`;

  $("#tablaVentas").innerHTML = `
    <tr><th>#</th><th>Hora</th><th>Medio</th><th class="num">Total</th><th></th></tr>
    ${lista.ventas.length ? lista.ventas.map((v) => `
      <tr class="${v.estado === "anulada" ? "anulada" : ""}">
        <td>${v.numero}</td>
        <td>${new Date(v.creada_at).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false })}</td>
        <td><span class="pill">${v.medio_pago}</span></td>
        <td class="num">${clp(v.total)}</td>
        <td style="white-space:nowrap">
          <button class="btn btn--chico" data-imprimir="${v.id}">Imprimir</button>
          ${v.estado === "pagada"
            ? `<button class="btn btn--peligro btn--chico" data-anular="${v.id}">Anular</button>`
            : ""}</td>
      </tr>`).join("") : `<tr><td colspan="5" style="color:var(--suave)">Todavía no hay ventas hoy.</td></tr>`}`;

  TURNOS_A_LA_VISTA = turnos;
  $("#tablaTurnos").innerHTML = `
    <tr><th>Día</th><th>Abrió / cerró</th><th>Quiénes estuvieron</th>
        <th class="num">Esperado</th><th class="num">Contado</th><th class="num">Dif.</th><th></th></tr>
    ${turnos.length ? turnos.map((t) => {
      const d = t.diferencia;
      const marca = d === null ? "<span class='pill'>abierto</span>"
        : d === 0 ? "<span class='ok'>cuadra</span>"
        : `<span class='mal'>${clp(d)}</span>`;
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
    }).join("") : `<tr><td colspan="6" style="color:var(--suave)">Sin cierres en este período.</td></tr>`}`;

  $("#tablaTop").innerHTML = `
    <tr><th>Producto</th><th class="num">Cant.</th><th class="num">Total</th></tr>
    ${r.mas_vendidos.length ? r.mas_vendidos.map((p) => `
      <tr><td>${p.nombre}</td><td class="num">${p.cantidad}</td><td class="num">${clp(p.total)}</td></tr>
    `).join("") : `<tr><td colspan="3" style="color:var(--suave)">Sin datos todavía.</td></tr>`}`;
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

function pintarEditorCarta() {
  $("#editorCarta").innerHTML = CATEGORIAS.map((c) => `
    <div class="grupo">
      <div class="grupo__top">
        <h3>${esc(c.nombre)}</h3>
        <button class="btn btn--chico" data-nuevo-en="${c.id}">+ Producto</button>
      </div>
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
    </div>`).join("");
}

/* Ficha completa del producto: acá viven los datos que usan las PANTALLAS del
   local (el dibujo, la etiqueta, el destacado), que no caben en la lista. */
function abrirFichaProducto(id) {
  const cat = CATEGORIAS.find((c) => c.productos.some((p) => p.id === id));
  const p = cat.productos.find((x) => x.id === id);
  const cats = CATEGORIAS
    .map((c) => `<option value="${c.id}"${c.id === cat.id ? " selected" : ""}>${esc(c.nombre)}</option>`).join("");

  $("#dialogoProducto").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>${esc(p.nombre)}</h2>
    <div class="fila2">
      <label class="campo"><span>Nombre</span><input id="fNombre" type="text" value="${esc(p.nombre)}"></label>
      <label class="campo"><span>Precio</span><input id="fPrecio" type="text" inputmode="numeric" value="${p.precio}"></label>
    </div>
    <label class="campo"><span>Descripción (se ve en la pantalla del menú)</span>
      <input id="fDesc" type="text" value="${esc(p.descripcion)}"></label>
    <label class="campo"><span>Categoría</span><select id="fCat">${cats}</select></label>
    <div class="campo">
      <span>Códigos de barra</span>
      <div id="fCodigos"></div>
      <div class="codigo-poner">
        <!-- inputmode="none" a propósito: con "numeric" el teclado en pantalla
             se abre encima cada vez que el lector "escribe" acá. -->
        <input id="fCodigo" type="text" inputmode="none" autocomplete="off"
               placeholder="Pasa el producto por el lector">
        <button class="btn btn--chico" data-pegar-codigo="${p.id}">Agregar</button>
      </div>
      <p class="ayuda" style="margin:6px 0 0;font-size:12.5px">Un producto puede tener
        varios: la lata suelta y el pack de 6 traen códigos distintos.</p>
    </div>
    ${selectorDeDibujo(p.dibujo)}
    <div class="fila2">
      <label class="campo"><span>Etiqueta (opcional)</span>
        <input id="fEtiqueta" type="text" value="${esc(p.etiqueta)}" placeholder="Nuevo, Sin lactosa..."></label>
      <label class="campo"><span>Precio antes (oferta)</span>
        <input id="fAntes" type="text" inputmode="numeric" value="${p.antes || ""}" placeholder="vacío si no hay"></label>
    </div>
    <label class="marca" style="margin-bottom:12px">
      <input type="checkbox" id="fDestacado" ${p.destacado ? "checked" : ""}>
      Mostrar en el recuadro grande de la pantalla</label>
    <label class="campo"><span>Texto del recuadro grande</span>
      <input id="fBadge" type="text" value="${esc(p.badge)}" placeholder="Recomendado de hoy"></label>
    <label class="marca"><input type="checkbox" id="fActivo" ${p.activo ? "checked" : ""}> A la venta</label>

    <div class="tal-cual" id="zonaTalCual" data-producto="${p.id}"></div>

    <div class="dialogo__pie">
      <button class="btn btn--peligro" id="fBorrar">Sacar de la carta</button>
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="fGuardar" style="width:auto">Guardar</button>
    </div>`;
  $("#capaProducto").classList.add("is-on");
  pintarTalCual(p);
  pintarCodigos(p.id);

  $("#fGuardar").onclick = async () => {
    const antes = soloNumeros($("#fAntes").value);
    try {
      await api(`/productos/${id}`, { method: "PUT", body: JSON.stringify({
        categoria_id: +$("#fCat").value,
        nombre: $("#fNombre").value.trim() || p.nombre,
        descripcion: $("#fDesc").value.trim(),
        precio: soloNumeros($("#fPrecio").value),
        activo: $("#fActivo").checked,
        orden: p.orden,
        destacado: $("#fDestacado").checked,
        badge: $("#fBadge").value.trim(),
        antes: antes || null,
        etiqueta: $("#fEtiqueta").value.trim(),
        dibujo: $("#fDibujo").value,
        color: p.color || "",
      }) });
      $("#capaProducto").classList.remove("is-on");
      await cargarCarta();
      avisar("Guardado");
    } catch (e) { avisar(e.message, true); }
  };

  $("#fBorrar").onclick = async () => {
    if (!confirm("¿Sacar este producto de la carta? Las ventas viejas no se tocan.")) return;
    try {
      await api(`/productos/${id}`, { method: "DELETE" });
      $("#capaProducto").classList.remove("is-on");
      await cargarCarta();
      avisar("Producto sacado de la carta");
    } catch (e) { avisar(e.message, true); }
  };
}

async function nuevoProducto(catId) {
  try {
    const p = await api("/productos", { method: "POST", body: JSON.stringify({
      categoria_id: catId, nombre: "Producto nuevo", descripcion: "", precio: 1000,
      activo: true, orden: 99, destacado: false, badge: "", antes: null,
      etiqueta: "", dibujo: "mug", color: "" }) });
    await cargarCarta();
    abrirFichaProducto(p.id);
  } catch (e) { avisar(e.message, true); }
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
/* El recuadro de la pestaña Carta.

   Muestra la dirección de ESTA caja en la red —que sirve para abrirla desde un
   tablet o desde otro computador del local— y avisa que las pantallas del menú
   son otro programa desde la 2.2.

   Las direcciones de las PANTALLAS no se muestran acá a propósito: esta caja no
   sabe si ese programa está instalado en este computador, ni en qué puerto
   quedó. Escribir una dirección que capaz no existe es peor que no escribir
   ninguna — el dueño la pega en el televisor, no anda, y no sabe si el problema
   es el TV, la red o el programa. Esas direcciones las muestra el programa de
   las pantallas, que sí las conoce. */
function pintarConectar(salud) {
  const caja = $("#conectar");
  if (!caja) return;
  if (!salud.en_la_red) { caja.hidden = true; return; }
  const mia = (salud.carta_url || "").replace("/api/v1/carta", "");
  caja.innerHTML = `
    <b>Esta caja en la red del local</b><br>
    Para abrirla desde un tablet o desde otro computador, en el mismo wifi.
    ${mia ? `<div class="conectar__url">
      <span class="conectar__cual">La caja</span>
      <code>${mia}</code>
      <button class="btn btn--chico" data-copiar="${mia}">Copiar</button>
    </div>` : ""}
    <div class="conectar__url conectar__url--simple">
      <span class="conectar__cual">Las pantallas del menú</span>
      <span style="font-size:13.5px;line-height:1.6">Son un programa aparte.
        Se abren con su propio icono, <b>Pantallas del menú</b>, y ahí salen las
        direcciones de cada televisor.</span>
    </div>
    <p style="margin:10px 0 0;font-size:13px;line-height:1.6">
      La carta le llega sola a los televisores: la vienen a buscar acá. Eso sí,
      esta caja tiene que estar abierta — si el computador se apaga, se quedan
      con la última que alcanzaron a leer.
    </p>`;
}

/* ---------------- actualizaciones ----------------
   El dueño no tiene por qué saber que existe una "versión": el número está
   chico en la barra y solo se pone verde cuando hay algo nuevo. */
let INFO_VERSION = null;

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
  puerta.hidden = !SESION.entrado || SESION.provisorio || t.abierto || hayCandado;
}

async function cargarTurno() {
  const t = await api("/turnos/actual");
  const chip = $("#turnoEstado");
  $(".punto").classList.toggle("off", !t.abierto);
  chip.textContent = t.abierto
    ? `Caja abierta${t.turno.cajero ? " · " + t.turno.cajero : ""}`
    : "Caja cerrada";
  chip.dataset.abierto = t.abierto ? "1" : "0";
  TURNO = t;
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
                       credito: "Crédito", transferencia: "Transferencia" };
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
}

/* ---- abrir: contar el fondo que queda en el cajón ---- */
function pintarAbrirCaja() {
  $("#dialogoTurno").className = "dialogo dialogo--ancho";
  $("#dialogoTurno").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Abrir caja</h2>
    <label class="campo"><span>¿Quién atiende?</span>
      <input id="tCajero" type="text" placeholder="Nombre" autocomplete="off"></label>
    <p class="ayuda" style="margin-bottom:10px">Cuenta la plata con la que parte el cajón.
      Si no hay fondo, déjalo todo en cero.</p>
    ${arqueoHTML()}
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="tAbrir" style="width:auto">Abrir caja</button>
    </div>`;
  pintarArqueo();
  conectarArqueo();
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
  pintarArqueo();
  conectarTarjetas(tu);
  // Si vuelven a tocar el conteo después de ver el cuadre, se rehace.
  conectarArqueo(() => { if ($("#zonaCuadre").dataset.visto) mostrarCuadre(tu); });

  $("#verCuadre").onclick = () => mostrarCuadre(tu);
}

function mostrarCuadre(tu) {
  const contado = totalConteo();
  const dif = contado - tu.efectivo_esperado;
  const ok = dif === 0;
  const zona = $("#zonaCuadre");
  zona.dataset.visto = "1";

  // Esto se vuelve a dibujar con CADA corrección del conteo, así que lo que la
  // persona ya escribió se rescata antes de rehacerlo. La nota se perdía en
  // cada tecla del arqueo.
  const fondoPrevio = $("#tFondo") ? soloNumeros($("#tFondo").value) : tu.monto_inicial;
  const notaPrevia = $("#tNota") ? $("#tNota").value : "";

  // Ya contó: destapar el efectivo ya no arruina nada.
  $("#resumenTurno").innerHTML = resumenDelTurno(tu);

  zona.innerHTML = `
    <div class="cierre__paso"><b>3</b> Cómo quedó la caja</div>
    <div class="cierre">
      <div class="cierre__col">
        <div class="cuadre ${ok ? "cuadre--ok" : "cuadre--mal"}">
          <div class="cuadre__linea"><span>Fondo con el que abrió</span><span>${clp(tu.monto_inicial)}</span></div>
          <div class="cuadre__linea"><span>Ventas en efectivo</span><span>${clp(tu.ventas_efectivo)}</span></div>
          <div class="cuadre__linea"><span>Debería haber</span><span>${clp(tu.efectivo_esperado)}</span></div>
          <div class="cuadre__linea"><span>Contaste</span><span>${clp(contado)}</span></div>
          <div class="cuadre__linea cuadre__dif">
            <span>${ok ? "Cuadra exacto" : dif > 0 ? "Sobra" : "Falta"}</span>
            <span>${ok ? "✓" : clp(Math.abs(dif))}</span>
          </div>
        </div>
        ${bloquePropinas(tu)}
      </div>
      <div class="cierre__col">
        <label class="campo"><span>¿Cuánto dejas de fondo para mañana?</span>
          <input id="tFondo" type="text" inputmode="numeric" value="${fondoPrevio || ""}" placeholder="0"></label>
        <div class="medios-turno" id="tRetiro"></div>
        <label class="campo"><span>Nota (opcional)</span>
          <input id="tNota" type="text" value="${esc(notaPrevia)}"
                 placeholder="Ej: le di vuelto de más a un cliente"></label>
      </div>
    </div>`;

  const pintarRetiro = () => {
    const fondo = Math.min(soloNumeros($("#tFondo").value), contado);
    $("#tRetiro").innerHTML = `Te llevas del cajón: <b>${clp(contado - fondo)}</b>`;
  };
  $("#tFondo").addEventListener("input", pintarRetiro);
  pintarRetiro();

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
  return SESION;
}

function pintarQuien() {
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
async function mostrarCandado(motivo) {
  const info = await api("/candado");
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
  $("#candadoCaja").innerHTML = `
    <h1>${esc(NOMBRE_DEL_LOCAL)}</h1>
    <p>Todavía no hay nadie registrado en esta caja.<br>
       El primero es el dueño: va a poder crear a los demás.</p>
    <label class="campo"><span>¿Cómo te llamas?</span>
      <input id="primerNombre" type="text" placeholder="Tu nombre" autocomplete="off"></label>
    <label class="campo"><span>Inventa un PIN de 4 números</span>
      <input id="primerPin" type="password" inputmode="numeric" data-teclado="entero"
             placeholder="••••" autocomplete="off"></label>
    <button class="btn btn--cobrar" id="crearPrimero">Crear mi usuario</button>
    <p class="candado__nota">Con esto la caja va a saber quién abrió, quién cerró
      y quién estuvo en cada turno.</p>`;
  $("#candado").hidden = false;
  setTimeout(() => $("#primerNombre").focus(), 80);
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
  try {
    const r = await api("/sesion/entrar", {
      method: "POST", body: JSON.stringify({ usuario_id: usuarioId, pin }) });
    $("#candado").hidden = true;
    await cargarSesion();
    await cargarTurno();          // la puerta de la caja depende de esto
    avisar("Hola, " + r.nombre);
    reiniciarInactividad();
  } catch (e) {
    // Un PIN malo no puede sacar de la pantalla: se sacude y se vuelve a pedir.
    $("#candadoCaja").classList.add("candado--mal");
    setTimeout(() => $("#candadoCaja").classList.remove("candado--mal"), 420);
    avisar(e.message, true);
    setTimeout(() => pedirPin(usuarioId), 450);
  }
}

async function crearPrimerUsuario() {
  const nombre = ($("#primerNombre").value || "").trim();
  const pin = ($("#primerPin").value || "").replace(/\D/g, "");
  if (!nombre) return avisar("Escribe tu nombre", true);
  if (pin.length < 4) return avisar("El PIN son 4 números", true);
  try {
    const u = await api("/usuarios", { method: "POST",
      body: JSON.stringify({ nombre, pin, rol: "dueno" }) });
    await entrarComo(u.id, pin);
  } catch (e) { avisar(e.message, true); }
}

/* ---------------- el equipo ----------------
   La API de usuarios existe desde la 1.2 (crear, editar, sacar), pero la
   pantalla para usarla nunca se construyó: el dueño podía crearse a sí mismo en
   el primer arranque y a nadie más. En el local quedó una sola cuenta.

   Sacar a alguien NO lo borra: sus ventas y sus turnos tienen que seguir
   cuadrando. Queda inactivo y desaparece del candado. */
let EQUIPO = [];

async function dialogoEquipo() {
  try { EQUIPO = await api("/usuarios"); }
  catch (e) { return avisar(e.message, true); }

  $("#dialogoEquipo").innerHTML = `
    <button class="dialogo__x" data-cerrar-capa aria-label="Cerrar">✕</button>
    <h2>Quiénes entran a la caja</h2>
    <p class="ayuda" style="margin-bottom:14px">El <b>dueño</b> puede todo. El
      <b>cajero</b> vende, cobra y cuadra su caja, pero no cambia precios ni
      corrige ventas de días pasados.</p>
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
  setTimeout(() => $("#uNombre").focus(), 60);
}

async function guardarUsuario(id) {
  const nombre = ($("#uNombre").value || "").trim();
  const pin = ($("#uPin").value || "").replace(/\D/g, "");
  const elegido = $("#uRol .is-on");
  const previo = EQUIPO.find((x) => x.id === id);

  if (!nombre) return avisar("Escribe el nombre", true);
  if (!id && pin.length < 4) return avisar("Ponle un PIN de 4 números", true);
  if (pin && pin.length < 4) return avisar("El PIN son 4 números", true);

  const cuerpo = {
    nombre,
    rol: elegido ? elegido.dataset.rol : "cajero",
    // Guardar no puede revivir a alguien que sacaron: para eso está su botón.
    activo: previo ? previo.activo : true,
    color: previo ? previo.color : "",
    orden: previo ? previo.orden : 0,
  };
  if (pin) cuerpo.pin = pin;

  try {
    await api(id ? `/usuarios/${id}` : "/usuarios",
      { method: id ? "PUT" : "POST", body: JSON.stringify(cuerpo) });
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
  try { await api("/sesion/salir", { method: "POST", body: JSON.stringify({ por }) }); }
  catch (e) {}
  await cargarSesion();
  mostrarCandado(por === "bloqueo" ? "La caja se bloqueó sola. ¿Quién sigue?"
                                   : "¿Quién está en la caja?");
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
  }, MINUTOS_QUIETO * 60000);
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
  try {
    BODEGA = await api("/inventario");
  } catch (e) { return avisar(e.message, true); }

  const faltan = BODEGA.por_comprar || [];
  $("#kpisBodega").innerHTML = `
    <div class="kpi"><span>Insumos</span><b>${BODEGA.insumos.length}</b>
      <small>${BODEGA.productos_con_receta} de ${BODEGA.productos_totales} productos con receta</small></div>
    <div class="kpi"><span>Vale la bodega</span><b>${clp(BODEGA.valor_total)}</b>
      <small>a precio de la última compra</small></div>
    <div class="kpi"><span>Por comprar</span><b class="${faltan.length ? "mal" : "ok"}">${faltan.length}</b>
      <small>${faltan.length ? faltan.map((f) => esc(f.nombre)).join(", ") : "no falta nada"}</small></div>`;

  $("#avisoBodega").innerHTML = faltan.length ? `
    <div class="conectar" style="border-color:#E8C9C6;background:#FBECEA">
      <b>Hay que comprar:</b>
      ${faltan.map((f) => `${esc(f.nombre)} (queda ${esc(f.muestra)})`).join(" · ")}
    </div>` : "";

  $("#tablaInsumos").innerHTML = !BODEGA.insumos.length ? `
    <tr><td class="vacio" style="padding:34px">Todavía no hay nada en la bodega.<br>
      Agrega un insumo, o entra a un producto de la Carta y usa
      <b>“se vende tal cual”</b>.</td></tr>` : `
    <tr><th>Insumo</th><th class="num">Queda</th><th class="num">Mínimo</th>
        <th class="num">Vale</th><th>Cómo se compra</th><th></th></tr>
    ${BODEGA.insumos.map((i) => `
      <tr class="${i.bajo_cero ? "bajo-cero" : i.bajo_minimo ? "bajo-minimo" : ""}">
        <td><b>${esc(i.nombre)}</b></td>
        <td class="num"><b>${esc(i.muestra)}</b>
          ${i.bajo_cero ? '<div class="mal" style="font-size:12px">falta registrar una compra</div>'
                        : i.bajo_minimo ? '<div class="mal" style="font-size:12px">bajo el mínimo</div>' : ""}</td>
        <td class="num">${i.minimo ? esc(i.minimo_muestra) : "—"}</td>
        <td class="num">${clp(i.valor)}</td>
        <td>${esc(i.formato || "—")}${i.compra_costo ? ` · ${clp(i.compra_costo)}` : ""}</td>
        <td>
          <button class="btn btn--chico" data-libro="${i.id}">Ver movimientos</button>
          <button class="btn btn--chico" data-insumo="${i.id}">Editar</button>
        </td>
      </tr>`).join("")}`;
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
function bloqueTarjetas(tu) {
  const medios = tu.medios || [];
  if (!medios.length) return "";
  return `
    <div class="tarjetas">
      <div class="tarjetas__tit">¿Cuánto dice la máquina?</div>
      <p class="ayuda" style="margin:0 0 10px">Escribe el total del comprobante de
        cierre de Transbank y lo que muestre el banco. Es opcional: si lo dejas
        vacío, la caja igual cierra.</p>
      ${medios.map((m) => `
        <div class="tarjetas__fila" data-medio-fila="${m.medio}">
          <div>
            <b>${esc(m.nombre)}</b>
            <div class="tarjetas__detalle">${m.cantidad} venta${m.cantidad === 1 ? "" : "s"}
              · ${clp(m.ventas)}${m.propinas ? ` + ${clp(m.propinas)} de propina` : ""}</div>
          </div>
          <div class="tarjetas__esperado">deberían ser<b>${clp(m.esperado)}</b></div>
          <input type="text" inputmode="numeric" data-dice="${m.medio}"
                 value="${m.declarado != null ? m.declarado : ""}" placeholder="0">
          <div class="tarjetas__dif" data-dif="${m.medio}"></div>
        </div>`).join("")}
    </div>`;
}

/* Los campos se marcan `data-dice`, NO `data-medio`: los botones de medio de
   pago del diálogo de cobro ya usan `data-medio` y viven en index.html desde que
   carga la página, así que `querySelector` encontraba el botón en vez del campo
   y el "cuadra ✓" no aparecía nunca. */
function conectarTarjetas(tu) {
  (tu.medios || []).forEach((m) => {
    const campo = document.querySelector(`[data-dice="${m.medio}"]`);
    if (!campo) return;
    const pintar = () => {
      const caja = document.querySelector(`[data-dif="${m.medio}"]`);
      const escrito = (campo.value || "").trim();
      if (!escrito) { caja.textContent = ""; caja.className = "tarjetas__dif"; return; }
      const dif = soloNumeros(escrito) - m.esperado;
      caja.textContent = dif === 0 ? "cuadra ✓"
        : (dif > 0 ? "sobran " : "faltan ") + clp(Math.abs(dif));
      caja.className = "tarjetas__dif " + (dif === 0 ? "ok" : "mal");
    };
    campo.addEventListener("input", pintar);
    pintar();
  });
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
  const guias = window.GUIAS || [];
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
  $("#textoGuia").scrollTop = 0;
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
let AJUSTES = { margen_sugerido: 50, redondeo_precio: 50 };

async function cargarAjustes() {
  try { AJUSTES = { ...AJUSTES, ...(await api("/ajustes")) }; }
  catch (e) { }        // con los valores por defecto la caja funciona igual
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

function repintarSugerido(costo) {
  const caja = $(".sugerido");
  if (!caja) {
    const zona = $("#zonaSugerido");
    if (zona) { zona.innerHTML = bloqueSugerido(costo, "fPrecio"); refrescarSugerido(); }
    return;
  }
  if (!costo) return caja.remove();
  caja.dataset.costo = costo;
  refrescarSugerido();
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
  let receta = null;
  try { receta = await api(`/productos/${p.id}/receta`); } catch (e) { return; }

  if (receta.lineas.length) {
    const l = receta.lineas[0];
    const simple = receta.lineas.length === 1 && l.nombre === p.nombre;
    zona.innerHTML = `
      <div class="tal-cual__tit">Bodega</div>
      <p class="ayuda" style="margin:0 0 8px">
        ${simple
          ? `Se descuenta de <b>${esc(l.nombre)}</b>. Quedan <b>${esc(l.stock_muestra)}</b>.`
          : `Lleva ${receta.lineas.length} ingredientes.`}
        ${receta.alcanza_para != null
          ? ` Con lo que hay alcanza para <b>${receta.alcanza_para}</b>.` : ""}
      </p>
      ${receta.costo_total ? `
        <p class="ayuda" style="margin:0 0 10px">Te cuesta
          <b>${clp(receta.costo_total)}</b> y lo vendes a <b>${clp(p.precio)}</b>:
          te quedan <b>${clp(receta.margen)}</b> (${receta.margen_pct}%).</p>
        ${bloqueSugerido(receta.costo_total, "fPrecio")}` : ""}`;
    refrescarSugerido();
    return;
  }

  zona.innerHTML = `
    <div class="tal-cual__tit">Bodega</div>
    <p class="ayuda" style="margin:0 0 10px">Este producto todavía no descuenta
      nada al venderse. Si es algo que compras hecho y vendes tal cual —un
      pastel, una botella, un alfajor— acá se resuelve de un toque.</p>
    <div class="tal-cual__campos">
      <label class="campo"><span>¿Cuántos tienes?</span>
        <input id="tcStock" type="text" inputmode="numeric" placeholder="0"></label>
      <label class="campo"><span>¿Cuánto te cuesta cada uno?</span>
        <input id="tcCosto" type="text" inputmode="numeric" placeholder="0"></label>
      <label class="campo"><span>Avísame bajo</span>
        <input id="tcMinimo" type="text" inputmode="numeric" placeholder="0"></label>
    </div>
    <div id="zonaSugerido"></div>
    <button class="btn" data-tal-cual="${p.id}">Se vende tal cual</button>`;

  // El sugerido aparece en cuanto hay un costo escrito, y se recalcula solo.
  const costo = $("#tcCosto");
  costo.addEventListener("input", () => repintarSugerido(soloNumeros(costo.value)));
}

async function marcarTalCual(id) {
  try {
    await api(`/productos/${id}/receta/tal-cual`, { method: "POST", body: JSON.stringify({
      stock_inicial: soloNumeros(($("#tcStock") || {}).value || 0),
      compra_costo: soloNumeros(($("#tcCosto") || {}).value || 0),
      minimo: soloNumeros(($("#tcMinimo") || {}).value || 0) })});
    const cat = CATEGORIAS.find((c) => c.productos.some((x) => x.id === id));
    await pintarTalCual(cat.productos.find((x) => x.id === id));
    avisar("Listo: ahora se descuenta solo al venderlo");
  } catch (e) { avisar(e.message, true); }
}

/* ---------------- arranque y eventos ---------------- */
function reloj() {
  $("#reloj").textContent = new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false });
}

/* Ruteo por hash: refrescar la página no devuelve al cajero a la caja sin
   avisar, y se puede dejar "El día" abierto en otra pestaña. */
const VISTAS = ["caja", "dia", "carta", "inventario", "guias"];

function verVista(nombre, empujarHash = true) {
  if (!VISTAS.includes(nombre)) nombre = "caja";
  $$(".tab").forEach((b) => b.classList.toggle("is-on", b.dataset.vista === nombre));
  $$(".vista").forEach((v) => v.classList.toggle("is-on", v.dataset.vista === nombre));
  if (empujarHash) location.hash = "#/" + nombre;
  if (nombre === "dia") cargarDia();
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
  if (cerca("data-anular")) return anular(+cerca("data-anular").dataset.anular);
  if (cerca("data-imprimir")) return imprimir(`/comprobante/${cerca("data-imprimir").dataset.imprimir}`);
  if (cerca("data-ver-cierre")) return dialogoCierre(+cerca("data-ver-cierre").dataset.verCierre);
  if (cerca("data-cierre")) return imprimir(`/cierre/${cerca("data-cierre").dataset.cierre}`);
  if (cerca("data-periodo")) {
    periodo = cerca("data-periodo").dataset.periodo;
    $$(".periodo").forEach((b) => b.classList.toggle("is-on", b.dataset.periodo === periodo));
    return cargarDia();
  }
  if (cerca("data-guardar")) return guardarProducto(+cerca("data-guardar").dataset.guardar);
  if (cerca("data-editar")) return abrirFichaProducto(+cerca("data-editar").dataset.editar);
  if (cerca("data-nuevo-en")) return nuevoProducto(+cerca("data-nuevo-en").dataset.nuevoEn);
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
  if (cerca("data-cerrar-capa")) return $$(".capa").forEach((c) => c.classList.remove("is-on"));

  if (t.closest("#medios .medio")) {
    medioPago = t.closest(".medio").dataset.medio;
    $$("#medios .medio").forEach((b) => b.classList.toggle("is-on", b.dataset.medio === medioPago));
    $("#bloqueEfectivo").style.display = medioPago === "efectivo" ? "" : "none";
    return calcularVuelto();
  }
  if (t.id === "limpiarBuscar") { $("#buscar").value = ""; $("#buscar").focus(); return buscar(""); }
  if (t.id === "btnNuevaCat") return nuevaCategoria();
  if (t.id === "btnHoy") { $("#fechaDia").value = hoyISO(); return cargarDia(); }
  if (t.id === "btnExportar") {
    const [d1, d2] = rangoDelPeriodo($("#fechaDia").value || hoyISO());
    // Dos archivos: el resumen de ventas y el detalle por producto.
    window.open(`/api/v1/exportar/ventas?desde=${d1}&hasta=${d2}`, "_blank");
    setTimeout(() => window.open(`/api/v1/exportar/detalle?desde=${d1}&hasta=${d2}`, "_blank"), 400);
    return avisar(`Descargando ${periodo === "dia" ? "el día" : "el " + periodo}`);
  }
  if (t.id === "btnRespaldar") {
    return api("/respaldo", { method: "POST" })
      .then((r) => avisar(r.ok ? `Respaldo guardado (${r.archivo}, ${r.tamano_kb} KB)` : r.detalle, !r.ok))
      .catch((err) => avisar(err.message, true));
  }
  if (t.id === "btnCobrar") return abrirCobro();
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
    return $$("#uRol .medio").forEach((o) => o.classList.toggle("is-on", o === b));
  }
  if (cerca("data-guardar-usuario"))
    return guardarUsuario(+cerca("data-guardar-usuario").dataset.guardarUsuario);
  if (cerca("data-sacar-usuario"))
    return sacarUsuario(+cerca("data-sacar-usuario").dataset.sacarUsuario);
  if (cerca("data-revivir-usuario"))
    return revivirUsuario(+cerca("data-revivir-usuario").dataset.revivirUsuario);

  // ---- bodega ----
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
  if (cerca("data-tal-cual")) return marcarTalCual(+cerca("data-tal-cual").dataset.talCual);
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
}

$("#buscar").addEventListener("input", (e) => buscar(e.target.value));
$("#buscar").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.target.value = ""; buscar(""); }
});
$("#fechaDia").addEventListener("change", cargarDia);
$("#pagaCon").addEventListener("input", calcularVuelto);
$("#propina").addEventListener("input", actualizarCobro);
$("#descuento").addEventListener("input", actualizarCobro);

document.addEventListener("keydown", (e) => {
  // Escape tampoco: es demasiado fácil apretarlo sin querer y perder el trabajo.
  // Para cerrar están la X y el botón Cancelar de cada diálogo.
  if (e.key === "Escape") return Teclado.cerrar();
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
  if (e.key === "Enter" && carrito.length && !$("#capaCobro").classList.contains("is-on")) abrirCobro();
});

(async function iniciar() {
  reloj();
  setInterval(reloj, 20000);
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
  else reiniciarInactividad();
  await cargarCarta();
  await cargarTurno();
  cargarVersion();
  pintarVersionAyuda();
  pintarCarrito();
  verVista(vistaDelHash(), false);
})();
