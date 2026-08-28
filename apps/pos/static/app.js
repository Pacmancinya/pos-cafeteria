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
function agregar(id) {
  const cat = CATEGORIAS.find((c) => c.productos.some((p) => p.id === id));
  const p = cat && cat.productos.find((x) => x.id === id);
  if (!p) return;
  const ya = carrito.find((l) => l.id === id);
  if (ya) ya.cantidad += 1;
  else carrito.push({ id: p.id, nombre: p.nombre, precio: p.precio, cantidad: 1 });
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
        <td><button class="btn btn--chico" data-cierre="${t.id}">Imprimir</button></td>
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
const DIBUJOS = {
  "taza": "Taza chica (espresso)",
  "taza-cortado": "Taza chica con leche",
  "mug": "Taza grande",
  "mug-espuma": "Taza grande con espuma",
  "mug-arte": "Taza grande con arte",
  "mug-crema": "Taza grande con crema",
  "vaso": "Vaso frío oscuro",
  "vaso-leche": "Vaso frío con leche",
  "vaso-limon": "Vaso frío con limón",
  "vaso-verde": "Vaso frío verde",
  "vaso-menta": "Vaso frío con menta",
  "frappe": "Frappé con crema",
  "croissant": "Croissant",
  "croissant-almendras": "Croissant de almendras",
  "torta": "Trozo de torta",
  "torta-manzana": "Trozo de kuchen",
  "brownie": "Brownie",
  "alfajor": "Alfajor",
};

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
  const dibujos = Object.entries(DIBUJOS)
    .map(([k, v]) => `<option value="${k}"${k === p.dibujo ? " selected" : ""}>${v}</option>`).join("");
  const cats = CATEGORIAS
    .map((c) => `<option value="${c.id}"${c.id === cat.id ? " selected" : ""}>${esc(c.nombre)}</option>`).join("");

  $("#dialogoProducto").innerHTML = `
    <h2>${esc(p.nombre)}</h2>
    <div class="fila2">
      <label class="campo"><span>Nombre</span><input id="fNombre" type="text" value="${esc(p.nombre)}"></label>
      <label class="campo"><span>Precio</span><input id="fPrecio" type="text" inputmode="numeric" value="${p.precio}"></label>
    </div>
    <label class="campo"><span>Descripción (se ve en la pantalla del menú)</span>
      <input id="fDesc" type="text" value="${esc(p.descripcion)}"></label>
    <div class="fila2">
      <label class="campo"><span>Categoría</span><select id="fCat">${cats}</select></label>
      <label class="campo"><span>Dibujo en la pantalla</span><select id="fDibujo">${dibujos}</select></label>
    </div>
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
    <div class="dialogo__pie">
      <button class="btn btn--peligro" id="fBorrar">Sacar de la carta</button>
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="fGuardar" style="width:auto">Guardar</button>
    </div>`;
  $("#capaProducto").classList.add("is-on");

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
function pintarConectar(salud) {
  $("#conectar").innerHTML = `
    <b>Conectar las pantallas del local</b><br>
    En la pantalla: tecla <b>C</b> → Punto de venta → pegar esta dirección y apretar
    “Probar la conexión”. Después, cada precio que cambies acá se ve allá solo.
    <div class="conectar__url">
      <code id="cartaUrl">${salud.carta_url}</code>
      <button class="btn btn--chico" id="copiarUrl">Copiar</button>
    </div>`;
  $("#copiarUrl").onclick = () => {
    const t = salud.carta_url;
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(() => avisar("Dirección copiada"));
    else avisar("Selecciona la dirección y copia con Ctrl+C");
  };
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
    <h2>Casi listo</h2>
    <p class="ayuda">La actualización quedó instalada, pero la caja no volvió sola.
      Cierra la ventana negra y vuelve a abrir <b>INICIAR-POS.bat</b>.</p>`;
}

/* ---------------- turno ---------------- */
async function cargarTurno() {
  const t = await api("/turnos/actual");
  const chip = $("#turnoEstado");
  $(".punto").classList.toggle("off", !t.abierto);
  chip.textContent = t.abierto
    ? `Caja abierta${t.turno.cajero ? " · " + t.turno.cajero : ""}`
    : "Caja cerrada";
  chip.dataset.abierto = t.abierto ? "1" : "0";
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

/* ---- cerrar: arqueo a ciegas y recién después el cuadre ---- */
function pintarCerrarCaja(tu) {
  const medios = Object.entries(tu.por_medio || {})
    .filter(([m]) => m !== "efectivo")
    .map(([m, d]) => `${NOMBRE_MEDIO[m] || m} <b>${clp(d.total)}</b>`).join(" · ");

  $("#dialogoTurno").className = "dialogo dialogo--ancho";
  $("#dialogoTurno").innerHTML = `
    <h2>Cerrar caja</h2>
    <p class="ayuda" style="margin-bottom:8px">Cuenta la plata del cajón, billete por billete.
      Cuando termines te muestro si cuadra.</p>
    ${medios ? `<div class="medios-turno">Lo pagado con tarjeta o transferencia no se cuenta:
      el programa ya lo sabe.<br>${medios}</div>` : ""}
    ${arqueoHTML()}
    <div id="zonaCuadre"></div>
    <div class="dialogo__pie">
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button>
      <button class="btn btn--cobrar" id="verCuadre" style="width:auto">Ver si cuadra</button>
    </div>`;
  pintarArqueo();
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

  const fondoPrevio = zona.querySelector("#tFondo") ? soloNumeros($("#tFondo").value) : tu.monto_inicial;

  zona.innerHTML = `
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
    <label class="campo"><span>¿Cuánto dejas de fondo para mañana?</span>
      <input id="tFondo" type="text" inputmode="numeric" value="${fondoPrevio || ""}" placeholder="0"></label>
    <div class="medios-turno" id="tRetiro"></div>

    ${bloqueTarjetas(tu)}
    ${bloquePropinas(tu)}

    <label class="campo"><span>Nota (opcional)</span>
      <input id="tNota" type="text" placeholder="Ej: le di vuelto de más a un cliente"></label>`;

  const pintarRetiro = () => {
    const fondo = Math.min(soloNumeros($("#tFondo").value), contado);
    $("#tRetiro").innerHTML = `Te llevas del cajón: <b>${clp(contado - fondo)}</b>`;
  };
  $("#tFondo").addEventListener("input", pintarRetiro);
  pintarRetiro();
  conectarTarjetas(tu);

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
  Teclado.abrir($("#candadoPin"), {
    modo: "pin",
    titulo: "PIN de " + u.nombre,
    alConfirmar: (pin) => entrarComo(u.id, pin),
  });
}

async function entrarComo(usuarioId, pin) {
  try {
    const r = await api("/sesion/entrar", {
      method: "POST", body: JSON.stringify({ usuario_id: usuarioId, pin }) });
    $("#candado").hidden = true;
    await cargarSesion();
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
          <input type="text" inputmode="numeric" data-medio="${m.medio}"
                 value="${m.declarado != null ? m.declarado : ""}" placeholder="0">
          <div class="tarjetas__dif" data-dif="${m.medio}"></div>
        </div>`).join("")}
    </div>`;
}

function conectarTarjetas(tu) {
  (tu.medios || []).forEach((m) => {
    const campo = document.querySelector(`[data-medio="${m.medio}"]`);
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
  $$("[data-medio]").forEach((c) => {
    const v = (c.value || "").trim();
    if (v) salida[c.dataset.medio] = soloNumeros(v);
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

/* ---------------- arranque y eventos ---------------- */
function reloj() {
  $("#reloj").textContent = new Date().toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false });
}

/* Ruteo por hash: refrescar la página no devuelve al cajero a la caja sin
   avisar, y se puede dejar "El día" abierto en otra pestaña. */
const VISTAS = ["caja", "dia", "carta", "inventario"];

function verVista(nombre, empujarHash = true) {
  if (!VISTAS.includes(nombre)) nombre = "caja";
  $$(".tab").forEach((b) => b.classList.toggle("is-on", b.dataset.vista === nombre));
  $$(".vista").forEach((v) => v.classList.toggle("is-on", v.dataset.vista === nombre));
  if (empujarHash) location.hash = "#/" + nombre;
  if (nombre === "dia") cargarDia();
  if (nombre === "inventario") cargarBodega();
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
  if (t.id === "btnLimpiar") { carrito = []; return pintarCarrito(); }
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
  if (t.id === "crearPrimero") return crearPrimerUsuario();
  if (t.id === "quienEsta" || t.closest("#quienEsta")) return salirDeLaCaja("cambio");

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

  // Tocar el fondo cierra el diálogo... salvo los que tienen trabajo adentro.
  // Perder un arqueo a medio contar por rozar la pantalla es carísimo: hay que
  // volver a contar el cajón entero. Pasó de verdad.
  if (t.classList.contains("capa") && !t.classList.contains("capa--firme"))
    t.classList.remove("is-on");
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
  if (e.key === "Escape")
    return $$(".capa:not(.capa--firme)").forEach((c) => c.classList.remove("is-on"));
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

  // Antes que nada, quién está. Si no hay nadie, el candado tapa todo.
  await cargarSesion();
  if (!SESION.entrado) await mostrarCandado();
  else reiniciarInactividad();

  await cargarCarta();
  await cargarTurno();
  cargarVersion();
  pintarCarrito();
  verVista(vistaDelHash(), false);
})();
