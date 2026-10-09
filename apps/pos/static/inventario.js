/* Una lista y una ficha. El servidor conserva la autoridad sobre precios y stock. */
let INV = { productos: [], ingredientes: [], recetas_antiguas: false };
let invFiltro = "todos", invCategoria = null, invBusqueda = "", invCarga = 0;
let invFicha = null, invCodigos = [], invCodigosOriginales = [], invOperacion = null, invPaso = 10;
let invEntradas = [], invContados = {}, invConteoFiltro = "todos";
const IL = window.InventarioLogica;
const invPuedeStock = () => usarInventario() && puedo("inventario");
const invPuedeContar = () => invPuedeStock() && puedo("inventario_ajustar");

const INV_ICONO = {
  mas: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  carro: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l2.2 11h10.6L20 7H6.2"/><circle cx="9" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/></svg>',
  alerta: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 2.8 19.5h18.4L12 4z"/><path d="M12 10v4.5M12 17.2v.1"/></svg>',
  cierra: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  basura: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12.2A2 2 0 0 0 9 21h6a2 2 0 0 0 2-1.8L18 7M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"/></svg>',
  lector: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M7 9v6M10.5 9v6M14 9v6M17 9v6"/></svg>',
  lupa: '<svg class="i-lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 21 21"/></svg>',
};
const invColorCat = (id) => (typeof colorDeCat === "function" ? colorDeCat(id) : "#C9552B");
const invCategoriaDe = (id) => CATEGORIAS.find((c) => c.id === id);
const invUnidad = (x) => x.unidad || "un";
const invHay = (x) => x.muestra || String(x.stock);

function invBuscador(id, placeholder, valor = "", clase = "") {
  return `<div class="buscador inv-busca i-busca ${clase}">${INV_ICONO.lupa}
    <input type="search" id="${id}" value="${esc(valor)}" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}" autocomplete="off" spellcheck="false">
    <button type="button" class="i-x" data-inv-limpiar="${id}" aria-label="Limpiar búsqueda">${INV_ICONO.cierra}</button></div>`;
}

async function cargarInventario() {
  const carga = ++invCarga;
  if (!puedo("editar_carta") && !puedo("inventario")) {
    INV = { productos: [], ingredientes: [], recetas_antiguas: false };
    $("#vistaInventario").innerHTML = '<p class="vacio">No tienes permiso para ver Inventario.</p>';
    return;
  }
  try {
    const d = await api("/inventario/productos");
    if (carga !== invCarga) return;
    INV = { ingredientes: [], ...d };
    pintarInventario();
  } catch (e) { avisar(e.message, true); }
}

/* ---------------------------------------------------------------- lista */
function pintarInventario() {
  const raiz = $("#vistaInventario");
  if (!raiz) return;
  const editar = puedo("editar_carta"), stock = invPuedeStock();
  const porComprar = INV.productos.filter(IL.porComprar).length;
  const filtros = [["todos", "Todos"], ["cuenta", "Con inventario"], ["comprar", "Por comprar"], ["ocultos", "Ocultos"]]
    .filter(([k]) => stock || !["cuenta", "comprar"].includes(k));
  const verIngredientes = stock && INV.recetas_antiguas && (INV.ingredientes || []).length;
  raiz.innerHTML = `<div class="i-barra">
    <div class="i-grupo"><button class="i-btn i-btn--prin" id="invNuevo" ${editar ? "" : "disabled"}>${INV_ICONO.mas}Nuevo producto</button>
      <button class="i-btn" id="invCategorias" ${editar ? "" : "disabled"}>Categorías</button>
      <button class="i-btn" id="btnImportar" ${editar ? "" : "disabled"}>Importar</button></div>
    <div class="i-grupo" ${stock ? "" : "hidden"}><button class="i-btn" data-inv-operacion="entrada">${INV_ICONO.carro}Entrada de mercadería</button>
      <button class="i-btn" data-inv-operacion="conteo" ${invPuedeContar() ? "" : "disabled"}>Conteo</button>
      <button class="i-btn" data-inv-operacion="merma">Merma</button>
      <button class="i-btn i-btn--aviso inv-comprar ${invFiltro === "comprar" ? "is-on" : ""}" data-inv-filtro="comprar" ${porComprar ? "" : "disabled"}>${INV_ICONO.alerta}Por comprar (${porComprar})</button></div></div>
    <div class="i-filtros">${invBuscador("invBuscar", "Buscar por nombre, código de barras o PLU", invBusqueda)}
      <div class="i-seg" role="group" aria-label="Filtro rápido">${filtros
        .map(([k, n]) => `<button class="i-seg__b ${invFiltro === k ? "is-on" : ""}" data-inv-filtro="${k}">${n}</button>`).join("")}</div></div>
    <div class="i-chips"><button class="i-chip ${invCategoria == null ? "is-on" : ""}" data-inv-categoria="">Todas</button>
      ${CATEGORIAS.map((c) => `<button class="i-chip ${invCategoria === c.id ? "is-on" : ""}" data-inv-categoria="${c.id}" style="--c:${invColorCat(c.id)}"><i class="i-punto"></i>${esc(c.nombre)}</button>`).join("")}</div>
    ${INV.recetas_antiguas ? `<p class="i-legado inv-legado">Este local tiene recetas antiguas: siguen funcionando.
      ${verIngredientes ? '<button type="button" class="i-enlace" id="invVerIngredientes">Ver ingredientes</button>' : ""}</p>` : ""}
    <div class="i-tabla inv-tabla"><table><thead><tr><th class="c-art"></th><th class="c-nom">Producto</th><th class="c-cat">Categoría</th><th class="c-pre">Precio</th><th class="c-sto">${stock ? "Hay" : ""}</th></tr></thead><tbody id="invFilas"></tbody></table></div>
    <p class="i-pie" id="invTotal" role="status"></p>`;
  invPintarFilas();
}

function invPintarFilas() {
  const filas = INV.productos.filter((p) => IL.coincide(p, invBusqueda)
    && (invCategoria == null || p.categoria_id === invCategoria)
    && (invFiltro !== "cuenta" || p.cuenta) && (invFiltro !== "comprar" || IL.porComprar(p))
    && (invFiltro !== "ocultos" || !p.activo))
    .sort((a, b) => CATEGORIAS.findIndex((c) => c.id === a.categoria_id) - CATEGORIAS.findIndex((c) => c.id === b.categoria_id)
      || a.orden - b.orden || a.id - b.id);
  const cuerpo = $("#invFilas");
  if (!cuerpo) return;
  const puedeVer = invPuedeStock();
  cuerpo.innerHTML = filas.map((p) => {
    const cat = invCategoriaDe(p.categoria_id), color = invColorCat(p.categoria_id);
    const kilo = p.precio_kilo > 0 && !p.precio;
    const marcas = [!p.activo ? '<span class="i-marca i-marca--no">No está a la venta</span>' : "",
      !p.en_tv ? '<span class="i-marca">Sin TV</span>' : ""].join("");
    const hay = p.cuenta && puedeVer
      ? `<span class="i-stock ${IL.porComprar(p) ? "inv-bajo" : ""}">${p.stock}</span>${p.minimo ? `<small>mín. ${p.minimo}</small>` : ""}`
      : '<span class="i-sin">—</span>';
    return `<tr data-inv-producto="${p.id}" tabindex="0" class="${p.activo ? "" : "i-off"}">
      <td class="c-art"><button class="inv-producto i-mini" data-inv-producto="${p.id}" style="--c:${color}" aria-label="Abrir ${esc(p.nombre)}">
        ${dibujo({ k: p.dibujo, col: p.color || undefined })}</button></td>
      <td class="c-nom"><b>${esc(p.nombre)}</b>${marcas ? `<span class="i-marcas">${marcas}</span>` : ""}</td>
      <td class="c-cat"><span class="i-pastilla" style="--c:${color}">${esc(cat?.nombre || "")}</span></td>
      <td class="c-pre">${clp(kilo ? p.precio_kilo : p.precio)}${kilo ? "<small>por kilo</small>" : ""}</td>
      <td class="c-sto">${hay}</td></tr>`;
  }).join("") || '<tr class="i-vacia"><td colspan="5">No hay productos con estos filtros.</td></tr>';
  const total = INV.productos.length;
  $("#invTotal").textContent = filas.length === total ? `${total} productos` : `${filas.length} de ${total} productos`;
}

/* ---------------------------------------------------------------- ficha */
function invCampo(id, nombre, valor = "", tipo = "text", extra = "", clase = "") {
  return `<label class="i-campo ${clase}"><span>${nombre}</span><input id="${id}" type="${tipo}" value="${esc(valor)}" ${extra}></label>`;
}
function invInterruptor(id, titulo, ayuda, activo, extra = "", ancho = false) {
  return `<label class="i-tog ${ancho ? "i-tog--ancho" : ""}"><input type="checkbox" id="${id}" role="switch" ${activo ? "checked" : ""} ${extra}>
    <span class="i-sw"></span><span class="i-tog__t"><b>${titulo}</b>${ayuda ? `<small>${ayuda}</small>` : ""}</span></label>`;
}
function invCategoriaCampo(p) {
  if (CATEGORIAS.length <= 8) {
    return `<label class="i-campo"><span>Categoría</span><select id="fCategoria">${CATEGORIAS.map((c) =>
      `<option value="${c.id}" ${c.id === p.categoria_id ? "selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>`;
  }
  const actual = invCategoriaDe(p.categoria_id) || CATEGORIAS[0];
  return `<div class="i-campo"><span>Categoría</span><div class="i-combo"><input type="hidden" id="fCategoria" value="${actual.id}">
    <div class="i-busca">${INV_ICONO.lupa}<input id="invCategoriaTxt" type="text" value="${esc(actual.nombre)}" placeholder="Escribe para buscar" autocomplete="off" spellcheck="false"></div>
    <div class="i-resultados" id="invCategoriaRes" hidden></div></div></div>`;
}
function invCategoriaLista() {
  const txt = $("#invCategoriaTxt"), res = $("#invCategoriaRes");
  if (!txt || !res) return;
  const t = IL.normalizar(txt.value);
  const lista = CATEGORIAS.filter((c) => !t || IL.normalizar(c.nombre).includes(t));
  const crear = t && !CATEGORIAS.some((c) => IL.normalizar(c.nombre) === t) && puedo("editar_carta");
  res.hidden = false;
  res.innerHTML = lista.map((c) => `<button type="button" class="i-res" data-inv-cat-elegir="${c.id}"><i class="i-punto" style="--c:${invColorCat(c.id)}"></i><b>${esc(c.nombre)}</b></button>`).join("")
    + (crear ? `<button type="button" class="i-res i-res--crear" data-inv-cat-crear="1">${INV_ICONO.mas}<b>Crear categoría «${esc(txt.value.trim())}»</b></button>` : "")
    + (!lista.length && !crear ? '<div class="i-res i-res--nada">No hay una categoría con ese nombre.</div>' : "");
}
function invElegirCategoria(c) {
  $("#fCategoria").value = c.id; $("#invCategoriaTxt").value = c.nombre; $("#invCategoriaRes").hidden = true;
  invPrevia();
}

async function abrirFichaProducto(id, categoriaId) {
  if (!INV.productos.length && id != null) await cargarInventario();
  const p = id == null ? { id: null, nombre: "", categoria_id: categoriaId || invCategoria || CATEGORIAS[0]?.id,
    precio: 0, precio_kilo: 0, plu: "", dibujo: "mug", color: "", activo: true, en_tv: true,
    cuenta: false, llevar_cuenta: false, costo: 0, stock: 0, minimo: 0, codigos: [] }
    : INV.productos.find((x) => x.id === id);
  if (!p) return avisar("El producto ya no está. Actualiza Inventario.", true);
  if (!CATEGORIAS.length) return invAbrirCategorias();
  invFicha = { ...p };
  invCodigos = (p.codigos || []).map((b) => ({ ...b }));
  invCodigosOriginales = (p.codigos || []).map((b) => ({ ...b }));
  const editar = puedo("editar_carta"), stock = editar && invPuedeStock() && !p.receta_antigua;
  const porPeso = p.precio_kilo > 0 && !p.precio;
  const costoBloqueado = !!p.receta_antigua || p.costo == null;
  const valorVenta = porPeso ? p.precio_kilo : p.precio;
  invPaso = [10, 50].includes(AJUSTES.redondeo_precio) ? AJUSTES.redondeo_precio : 10;
  const sinContar = !p.cuenta && !p.contado && !invPuedeContar();
  $("#dialogoProducto").className = "dialogo inv-dialogo i-dlg i-dlg--ficha inv-ficha";
  $("#dialogoProducto").innerHTML = `<header class="i-cab"><div><h2>${p.id == null ? "Nuevo producto" : "Editar producto"}</h2>${p.id == null ? "" : `<p>${esc(p.nombre)}</p>`}</div>
      <button type="button" class="i-cerrar" data-cerrar-capa aria-label="Cerrar">${INV_ICONO.cierra}</button></header>
    <div class="inv-interior i-cuerpo"><fieldset ${editar ? "" : "disabled"} class="inv-campos i-ficha">
    <div class="i-col">
      <section><h3>Producto</h3>
        <div class="i-campo"><span>Código de barras <em>(puede tener varios)</em></span><div class="i-codigo">
          <span class="i-codigo__ico">${INV_ICONO.lector}</span>
          <input id="fCodigo" placeholder="Escanea o escribe el código" aria-label="Código de barras" autocomplete="off">
          <button class="i-btn i-btn--suave" id="invOtroCodigo" type="button">+ otro código</button></div></div>
        <div id="invCodigos" class="i-codigos"></div>
        <div class="i-par">${invCampo("fNombre", "Nombre", p.nombre, "text", 'placeholder="Ej.: Alfajor" autocomplete="off"')}${invCategoriaCampo(p)}</div>
      </section>
      <section><h3>Se vende</h3>
        <input type="hidden" id="invModo" value="${porPeso ? "peso" : "unidad"}">
        <div class="i-radios" role="radiogroup">
          <button type="button" class="i-radio ${porPeso ? "" : "is-on"}" data-inv-modo="unidad" role="radio" aria-checked="${!porPeso}"><i></i>Por unidad</button>
          <button type="button" class="i-radio ${porPeso ? "is-on" : ""}" data-inv-modo="peso" role="radio" aria-checked="${porPeso}"><i></i>Por peso (balanza)</button></div>
        <div id="invPeso" ${porPeso ? "" : "hidden"}>${invCampo("fPlu", "PLU de balanza", p.plu || "", "text", 'inputmode="numeric" placeholder="Ej.: 21"', "i-campo--plu")}</div>
      </section>
      <section><h3 id="invTituloPrecios">Precios <em id="invGanas"></em></h3><div class="i-tres">
        ${invCampo("invCosto", porPeso ? "Costo por kilo" : "Precio costo", costoBloqueado && p.costo == null ? "" : p.costo, "number", `min="0" step="1" ${costoBloqueado ? "disabled" : ""}`, "i-plata")}
        ${invCampo("invGanancia", "Ganancia %", IL.ganancia(p.costo, valorVenta)?.toFixed(2) || "", "number", 'min="-99" step="0.01"', "i-plata i-plata--pct")}
        ${invCampo("fPrecio", porPeso ? "Precio por kilo" : "Precio venta", valorVenta, "number", 'min="0" step="1"', "i-plata i-plata--venta")}</div>
        ${p.receta_antigua ? '<p class="i-ayuda">Costo calculado por receta antigua.</p>' : (p.costo == null ? '<p class="i-ayuda">No tienes permiso para ver ni cambiar el costo.</p>' : "")}
        <div class="i-redondeo"><span>Redondear a</span><div class="i-seg i-seg--chico" role="group">
          <button type="button" class="i-seg__b ${invPaso === 10 ? "is-on" : ""}" data-inv-redondeo="10">$10</button>
          <button type="button" class="i-seg__b ${invPaso === 50 ? "is-on" : ""}" data-inv-redondeo="50">$50</button></div>
          <span class="i-sug" id="invSugerido"></span></div>
        ${p.precio > 0 && p.precio_kilo > 0 ? `<p class="i-ayuda">También conserva su precio anterior de balanza: ${clp(p.precio_kilo)} / kg.</p>` : ""}
      </section>
    </div>
    <div class="i-col">
      <section><h3>Cómo se ve</h3><div class="i-vista"><div id="invPrevia" class="inv-previa i-previa"></div>
        <div class="i-elige">${selectorDeDibujo(p.dibujo, p.color)}
        <input type="color" id="invColor" value="${colorBolsaOk(p.color) ? esc(p.color) : "#c9552b"}" hidden></div></div></section>
      <section><h3>Dónde aparece</h3><div class="i-donde">
        ${invInterruptor("fActivo", "A la venta", "en la caja", p.activo)}
        ${invInterruptor("fTv", "En los televisores", "carta del TV", p.en_tv)}</div>
        <!-- Aquí iría la visibilidad del tótem cuando se integre su rama. --></section>
      ${stock ? `<section><h3>Inventario</h3>${invInterruptor("fCuenta", "Este producto lleva inventario", "", p.cuenta,
          sinContar ? "disabled" : "", true)}
        ${sinContar ? '<p class="i-ayuda">Activarlo pide contar cuántos hay: hace falta el permiso para corregir el stock.</p>' : ""}
        <div id="invSaldo" class="i-par i-par--inv" ${p.cuenta ? "" : "hidden"}>
          <label class="i-campo"><span id="invHayEtiqueta">${p.cuenta ? "Hay ahora" : "¿Cuántos hay ahora?"}</span>
            <input id="invHay" type="number" min="0" step="1" value="${p.cuenta ? p.stock : ""}" placeholder="0" ${invPuedeContar() ? "" : "disabled"}></label>
          ${invCampo("invMinimo", "Mínimo", p.minimo, "number", 'min="0" step="1"')}</div>
        <p class="i-ayuda">Se descuenta solo con cada venta. Contar registra un movimiento y apagar conserva todo el historial.</p></section>` : ""}
      ${p.receta_antigua ? '<p class="i-ayuda">Este producto tiene una receta antigua: sigue funcionando.</p>' : ""}
    </div></fieldset></div>
    <div class="dialogo__pie"><button class="i-btn i-btn--borrar" id="invEliminar" ${p.id == null || !editar ? "hidden" : ""}>${INV_ICONO.basura}Eliminar</button>
      <button class="i-btn" data-cerrar-capa>Cancelar</button><button class="i-btn i-btn--prin" id="fGuardar" ${editar ? "" : "disabled"}>Guardar</button></div>`;
  invPintarCodigos(); invPrevia(); invPrecio("venta");
  $("#capaProducto").classList.add("is-on");
  $("#fNombre").focus();
}

function invPintarCodigos() {
  $("#invCodigos").innerHTML = invCodigos.map((b, i) => `<span class="i-cod inv-chip"><code>${esc(b.codigo)}</code>${b.cuantos > 1 ? ` × ${b.cuantos}` : ""}
    <button type="button" data-inv-quitar-codigo="${i}" aria-label="Quitar código ${esc(b.codigo)}">${INV_ICONO.cierra}</button></span>`).join("");
}
function invAgregarCodigo(codigo = $("#fCodigo")?.value) {
  codigo = IL.codigo(codigo || "");
  if (!codigo) return;
  if (!invCodigos.some((b) => b.codigo === codigo)) invCodigos.push({ codigo, cuantos: 1, nota: "" });
  $("#fCodigo").value = ""; invPintarCodigos();
}
function invPrecio(origen) {
  const c = $("#invCosto"), g = $("#invGanancia"), v = $("#fPrecio");
  if (!c || !v) return;
  if (origen === "ganancia") v.value = IL.venta(Number(c.value), Number(g.value));
  else if (origen === "costo" && g.value !== "") v.value = IL.venta(Number(c.value), Number(g.value));
  else if (origen === "venta") g.value = IL.ganancia(Number(c.value), Number(v.value))?.toFixed(2) || "";
  const costo = Number(c.value), venta = Number(v.value), s = IL.sugerido(costo, AJUSTES.margen_sugerido, invPaso);
  const sug = $("#invSugerido"), ganas = $("#invGanas");
  if (sug) sug.innerHTML = !s ? "" : s === venta ? `Sugerido: <b>${clp(s)}</b> ✓`
    : `Sugerido: <b>${clp(s)}</b> <button type="button" class="i-enlace" id="invUsarSugerido" data-sugerido="${s}">Usar</button>`;
  if (ganas) ganas.textContent = costo > 0 && venta > 0 ? `· ganas ${clp(venta - costo)} por ${$("#invModo")?.value === "peso" ? "kilo" : "unidad"}` : "";
  invPrevia();
}
function invPrevia() {
  const previa = $("#invPrevia");
  if (!previa) return;
  const cat = Number($("#fCategoria")?.value) || invFicha?.categoria_id;
  const peso = $("#invModo")?.value === "peso";
  previa.innerHTML = `<span class="prod prod--prev" style="--c:${invColorCat(cat)};--alto-card:100%;--cols:1">
    <span class="prod__art">${dibujo({ k: $("#fDibujo").value, col: $("#fColor").value || invFicha.color || undefined })}</span>
    <span class="prod__pie"><span class="prod__nombre">${esc($("#fNombre").value || "Nombre del producto")}</span>
    <span class="prod__precio">${clp($("#fPrecio").value)}${peso ? " /kg" : ""}</span></span></span>`;
}

async function invGuardarFicha() {
  if (!invFicha || !puedo("editar_carta")) return;
  const boton = $("#fGuardar");
  if (boton.disabled) return;
  const p = invFicha, peso = $("#invModo").value === "peso";
  const nombre = $("#fNombre").value.trim();
  if (!nombre) return avisar("Escribe el nombre del producto", true);
  const categoria = Number($("#fCategoria").value);
  if (!CATEGORIAS.some((c) => c.id === categoria)) return avisar("Elige una categoría de la lista o crea una nueva", true);
  const cuenta = $("#fCuenta");
  if (cuenta?.checked && !p.cuenta && invPuedeContar() && $("#invHay").value === "")
    return avisar("Escribe cuántos hay ahora (puede ser 0)", true);
  for (const id of ["invCosto", "fPrecio", "invMinimo", "invHay"]) {
    const campo = $("#" + id);
    if (id === "invHay" && p.cuenta && !p.hayEditado) continue;
    if (campo && !campo.disabled && !campo.closest("[hidden]") && (!campo.validity.valid || campo.value === ""))
      return avisar("Revisa el valor de " + campo.previousElementSibling.textContent, true);
  }
  invAgregarCodigo();
  const cuerpo = { categoria_id: categoria, nombre,
    precio: peso ? 0 : Number($("#fPrecio").value), precio_kilo: peso ? Number($("#fPrecio").value) : 0,
    plu: peso ? $("#fPlu").value.trim() : "", costo: Number($("#invCosto").value),
    activo: $("#fActivo").checked, en_tv: $("#fTv").checked,
    dibujo: $("#fDibujo").value, color: $("#fColor").value || p.color || "",
    descripcion: p.descripcion || "", orden: p.orden || 0,
    destacado: p.destacado || false, badge: p.badge || "", antes: p.antes ?? null, etiqueta: p.etiqueta || "" };
  if (p.id == null) cuerpo.codigos = invCodigos;
  else {
    // Solo lo que esta ficha cambió: un código que otro equipo agregó mientras tanto no se pierde.
    const antes = new Map(invCodigosOriginales.map((b) => [b.codigo, b]));
    cuerpo.codigos = invCodigos.filter((b) => { const o = antes.get(b.codigo); return !o || o.cuantos !== b.cuantos || o.nota !== b.nota; });
    cuerpo.codigos_quitar = invCodigosOriginales.map((b) => b.codigo).filter((c) => !invCodigos.some((b) => b.codigo === c));
  }
  // Mostrar un costo unitario redondeado no debe reescribir un envase antiguo.
  if (p.id != null && cuerpo.costo === p.costo) delete cuerpo.costo;
  // El costo de una receta antigua se calcula de sus ingredientes, y sin permiso no se ve ni se cambia.
  if (p.receta_antigua || p.costo == null) delete cuerpo.costo;
  // Fichas anteriores podían cobrar unidades y balanza. Editar su nombre no borra el PLU.
  if (!peso && !p.modoCambiado && p.precio > 0 && p.precio_kilo > 0) {
    cuerpo.plu = p.plu; cuerpo.precio_kilo = p.precio_kilo;
  }
  if (cuenta) {
    // Un NULL de antes conserva sus recetas al guardar nombre o precio.
    if (cuenta.checked !== !!p.cuenta || p.llevar_cuenta !== null) cuerpo.llevar_cuenta = cuenta.checked;
    if (cuenta.checked) {
      cuerpo.minimo = Number($("#invMinimo").value);
      if (invPuedeContar() && (Number($("#invHay").value) !== p.stock || !p.cuenta || (p.hayEditado && !p.contado))) {
        cuerpo.hay_ahora = Number($("#invHay").value); cuerpo.stock_esperado = p.stock;
      }
    }
  }
  boton.disabled = true;
  try {
    await api(p.id == null ? "/productos" : `/productos/${p.id}`, { method: p.id == null ? "POST" : "PUT", body: JSON.stringify(cuerpo) });
    try { await cargarCarta(); await cargarInventario(); }
    catch (e) { avisar("Producto guardado. Actualiza la lista: " + e.message, true); }
    $("#capaProducto").classList.remove("is-on"); invFicha = null;
    avisar("Producto guardado");
  } catch (e) { avisar(e.message, true); }
  finally { boton.disabled = false; }
}

/* ---------------------------------------------------------------- categorías */
function invAbrirCategorias() {
  if (!puedo("editar_carta")) return;
  invOperacion = null;
  $("#dialogoBodega").className = "dialogo inv-dialogo i-dlg i-dlg--medio";
  $("#dialogoBodega").innerHTML = `<header class="i-cab"><div><h2>Categorías</h2><p>Así se ordenan en la caja y en los televisores.</p></div>
      <button type="button" class="i-cerrar" data-cerrar-capa aria-label="Cerrar">${INV_ICONO.cierra}</button></header>
    <div class="i-sub">${invBuscador("invBuscarCategorias", "Buscar categoría")}</div>
    <div class="inv-interior i-cuerpo">
    <div id="invListaCategorias">${CATEGORIAS.map((c) => `<div class="i-cat-fila inv-categoria-fila" data-inv-cat-fila="${c.id}" style="--c:${invColorCat(c.id)}">
      <button type="button" class="i-cat-ico" data-inv-cat-dibujo="${c.id}" aria-label="Cambiar el ícono de ${esc(c.nombre)}"
        title="${c.dibujo ? "Ícono elegido" : "Ícono automático"}: toca para cambiarlo">${dibujo({ k: dibujoDeCategoria(c), col: c.dibujo && c.color ? c.color : undefined })}</button>
      <input aria-label="Nombre de categoría" data-inv-cat-nombre value="${esc(c.nombre)}">
      <input aria-label="Orden de categoría" type="number" data-inv-cat-orden value="${c.orden}">
      <span class="i-cat-n">${(c.productos || []).length} ${(c.productos || []).length === 1 ? "producto" : "productos"}</span>
      <button class="i-btn" data-inv-cat-guardar="${c.id}">Guardar</button>
      <button class="i-ico i-ico--borra" data-inv-cat-borrar="${c.id}" aria-label="Borrar categoría" ${(c.productos || []).length ? "disabled" : ""}>${INV_ICONO.basura}</button></div>`).join("")}</div>
    <div class="i-cat-fila i-cat-nueva"><input id="invCatNueva" aria-label="Nueva categoría" placeholder="Nueva categoría"><button class="i-btn i-btn--prin" id="invCatCrear">${INV_ICONO.mas}Agregar</button></div>
    </div><div class="dialogo__pie"><button class="i-btn i-btn--prin" data-cerrar-capa>Listo</button></div>`;
  $("#capaBodega").classList.add("is-on");
}

/* El ícono de una categoría: el mismo selector de dibujos de la ficha de producto, en el
   mismo diálogo. Elegir guarda al tiro; «Automático» vuelve a calcularlo según los productos. */
let invCatDibujoId = null;
function invAbrirDibujoCategoria(id) {
  const c = CATEGORIAS.find((x) => x.id === id);
  if (!c) return;
  invCatDibujoId = id;
  $("#dialogoBodega").className = "dialogo inv-dialogo i-dlg i-dlg--medio";
  $("#dialogoBodega").innerHTML = `<header class="i-cab"><div><h2>Ícono de «${esc(c.nombre)}»</h2><p>Así se ve en la columna de la caja.</p></div>
      <button type="button" class="i-cerrar" data-cerrar-capa aria-label="Cerrar">${INV_ICONO.cierra}</button></header>
    <div class="inv-interior i-cuerpo">
      <button type="button" class="i-btn i-cat-auto ${c.dibujo ? "" : "is-on"}" data-inv-cat-auto="${id}">
        <span class="i-cat-ico i-cat-ico--chico">${dibujo({ k: dibujoDeCategoria({ productos: c.productos }) })}</span>Automático (según sus productos)</button>
      ${selectorDeDibujo(c.dibujo || "", c.color)}
    </div><div class="dialogo__pie"><button type="button" class="i-btn i-btn--prin" data-inv-cat-volver>Listo</button></div>`;
  if (!c.dibujo) $$(".dibujo-op").forEach((x) => x.classList.remove("is-on"));
  $("#capaBodega").classList.add("is-on");
}
async function invGuardarDibujoCategoria(dib, color, cerrar) {
  const c = CATEGORIAS.find((x) => x.id === invCatDibujoId);
  if (!c) return;
  await api(`/categorias/${c.id}`, { method: "PUT", body: JSON.stringify({
    nombre: c.nombre, orden: c.orden, activa: c.activa, dibujo: dib, color: esDibujoDeBolsa(dib) ? color : "" }) });
  await cargarCarta(); await cargarInventario();
  if (cerrar) { invCatDibujoId = null; invAbrirCategorias(); }
  else avisar("Ícono guardado");
}

/* ---------------------------------------------------------------- entrada, conteo y merma */
function invProductosStock() { return INV.productos.filter((p) => p.cuenta && !p.receta_antigua && p.insumo_id); }
/* Ingredientes de recetas antiguas: mismo formato que un producto para reusar los diálogos. */
function invIngredientes() {
  return (INV.ingredientes || []).map((i) => ({ id: -i.id, nombre: i.nombre, insumo_id: i.id, stock: i.stock,
    muestra: i.muestra, minimo: i.minimo, unidad: i.unidad, codigos: [], plu: "", ingrediente: true }));
}
function invPool() { return invOperacion?.ingredientes ? invIngredientes() : invProductosStock(); }
function invItem(id) { return invPool().find((p) => p.id === id); }
function invMini(p) {
  return p.ingrediente ? '<span class="i-mini i-mini--s i-mini--ing">ing.</span>'
    : `<span class="i-mini i-mini--s" style="--c:${invColorCat(p.categoria_id)}">${dibujo({ k: p.dibujo, col: p.color || undefined })}</span>`;
}
function invSugerencias(texto) {
  const caja = $("#invSugerencias");
  if (!caja) return;
  if (!texto) { caja.hidden = true; caja.innerHTML = ""; return; }
  const filas = invPool().filter((p) => IL.coincide(p, texto)).slice(0, 8);
  caja.hidden = false;
  caja.innerHTML = filas.map((p) => `<button class="i-res inv-sugerencia" data-inv-elegir="${p.id}">${invMini(p)}<b>${esc(p.nombre)}</b>
    <small>Hay ${invHay(p)}${p.ingrediente ? "" : " un"}</small></button>`).join("")
    || '<div class="i-res i-res--nada">Ningún producto con inventario se llama así.</div>';
}
function invCabecera(titulo, sub) {
  return `<header class="i-cab"><div><h2>${titulo}</h2>${sub ? `<p>${sub}</p>` : ""}</div>
    <button type="button" class="i-cerrar" data-cerrar-capa aria-label="Cerrar">${INV_ICONO.cierra}</button></header>`;
}
async function invAbrirOperacion(tipo, ingredientes = false) {
  if (!invPuedeStock() || (tipo === "conteo" && !invPuedeContar())) return;
  await cargarInventario();
  invOperacion = { tipo, producto: null, ingredientes };
  invEntradas = []; invContados = {}; invConteoFiltro = "todos";
  const titulo = { entrada: "Entrada de mercadería", conteo: "Conteo", merma: "Merma" }[tipo];
  const sub = { entrada: "Lo que llegó del proveedor. Suma al stock.",
    conteo: "Cuenta lo que hay en el local y escríbelo. Se corrige solo la diferencia.",
    merma: "Lo que se perdió y ya no se puede vender." }[tipo] + (ingredientes ? " (Ingredientes de recetas antiguas)" : "");
  const ancho = tipo === "merma" ? "i-dlg--chico" : "i-dlg--ancho";
  $("#dialogoBodega").className = `dialogo inv-dialogo i-dlg ${ancho}`;
  const buscador = invBuscador("invBuscarMovimiento", "Busca por nombre, código de barras o PLU", "", "i-busca--dlg");
  let cuerpo;
  if (tipo === "conteo") {
    cuerpo = `<div class="i-sub"><div class="i-fila-filtro">${buscador}<div class="i-seg i-seg--chico" role="group" aria-label="Filtro del conteo">
        ${[["todos", "Todos"], ["sin", "Sin contar"], ["diferencia", "Con diferencia"]].map(([k, n]) => `<button class="i-seg__b ${k === "todos" ? "is-on" : ""}" data-inv-conteo-filtro="${k}">${n}</button>`).join("")}</div></div></div>
      <div class="inv-interior i-cuerpo"><div class="i-reng i-reng--tit i-reng--conteo"><span>Producto</span><span>En el sistema</span><span>Contado</span><span>Diferencia</span></div>
      <div id="invConteoFilas">${invPool().map((p) => `<div class="i-reng i-reng--conteo" data-inv-conteo-fila="${p.id}">
        <span class="i-reng__nom"><b>${esc(p.nombre)}</b></span><span class="i-sis" data-inv-sistema="${p.id}">${invHay(p)}</span>
        <label class="i-campo i-campo--sola"><input type="number" min="0" step="1" placeholder="—" aria-label="Contado de ${esc(p.nombre)}" data-inv-contado="${p.id}" value=""><i>${invUnidad(p)}</i></label>
        <span class="i-dif" data-inv-diferencia="${p.id}">—</span></div>`).join("")
        || '<div class="i-vacio">No hay nada que contar.</div>'}</div></div>`;
  } else if (tipo === "entrada") {
    cuerpo = `<div class="inv-interior i-cuerpo"><div class="i-buscar-prod">${buscador}<div id="invSugerencias" class="i-resultados" hidden></div></div>
      <div id="invEntradas" class="i-renglones"></div>
      <p class="i-ayuda">Aquí solo aparecen ${ingredientes ? "los ingredientes de recetas antiguas" : "los productos que llevan inventario"}.</p></div>`;
  } else {
    cuerpo = `<div class="inv-interior i-cuerpo i-merma"><div class="i-campo"><span>Producto</span>
      <div id="invElige" class="i-buscar-prod">${buscador}<div id="invSugerencias" class="i-resultados" hidden></div></div>
      <div id="invElegido" class="i-elegido" hidden></div></div>
      <label class="i-campo"><span id="invCantidadEtiqueta">Cantidad</span><input id="invCantidad" type="number" min="1" step="1" placeholder="0"></label>
      <div class="i-campo"><span>Motivo <em>(obligatorio)</em></span><input type="hidden" id="invMotivo" value="">
        <div class="i-motivos">${["Vencido", "Roto", "Consumo interno", "Otro"].map((m) => `<button type="button" class="i-chip i-chip--m" data-inv-motivo="${m}">${m}</button>`).join("")}</div></div>
      <div id="invDetalle" hidden>${invCampo("invOtroMotivo", "Detalle (obligatorio si es otro)")}</div>
      <p class="i-ayuda" id="invQueda"></p></div>`;
  }
  $("#dialogoBodega").innerHTML = `${invCabecera(titulo, sub)}${cuerpo}
    <div class="dialogo__pie"><span class="i-msg" id="invMensaje" role="status"></span><button class="i-btn" data-cerrar-capa>Cancelar</button>
      <button class="i-btn i-btn--prin" id="invGuardarMovimiento">${tipo === "entrada" ? "Guardar entrada" : tipo === "conteo" ? "Guardar conteo" : "Guardar merma"}</button></div>`;
  if (tipo === "entrada") invPintarEntradas();
  $("#capaBodega").classList.add("is-on"); $("#invBuscarMovimiento").focus();
}
function invAbrirIngredientes() {
  if (!invPuedeStock()) return;
  invOperacion = null;
  const filas = INV.ingredientes || [];
  $("#dialogoBodega").className = "dialogo inv-dialogo i-dlg i-dlg--medio";
  $("#dialogoBodega").innerHTML = `${invCabecera("Ingredientes de recetas antiguas", "Siguen descontándose al vender los productos que los usan.")}
    <div class="inv-interior i-cuerpo">${filas.length ? `<table class="i-tabla-simple"><thead><tr><th>Ingrediente</th><th class="num">Hay</th><th class="num">Mínimo</th></tr></thead><tbody>
      ${filas.map((i) => `<tr><td>${esc(i.nombre)}</td><td class="num ${i.stock < 0 || (i.minimo && i.stock < i.minimo) ? "inv-bajo" : ""}">${esc(i.muestra)}</td>
        <td class="num">${i.minimo ? esc(i.minimo_muestra) : "—"}</td></tr>`).join("")}</tbody></table>`
      : '<div class="i-vacio">No hay ingredientes.</div>'}</div>
    <div class="dialogo__pie"><button class="i-btn" data-inv-ing-operacion="entrada">${INV_ICONO.carro}Entrada</button>
      <button class="i-btn" data-inv-ing-operacion="conteo" ${invPuedeContar() ? "" : "disabled"}>Conteo</button>
      <button class="i-btn" data-inv-ing-operacion="merma">Merma</button>
      <button class="i-btn i-btn--prin" data-cerrar-capa>Cerrar</button></div>`;
  $("#capaBodega").classList.add("is-on");
}
function invElegirMovimiento(id) {
  const p = invItem(id);
  if (!p) return;
  invOperacion.producto = p;
  $("#invSugerencias").hidden = true; $("#invSugerencias").innerHTML = "";
  $("#invBuscarMovimiento").value = "";
  if (invOperacion.tipo === "merma") {
    $("#invElige").hidden = true;
    const caja = $("#invElegido");
    caja.hidden = false;
    caja.innerHTML = `${invMini(p)}<b>${esc(p.nombre)}</b><small>Hay ${invHay(p)}${p.ingrediente ? "" : " un"}</small>
      <button type="button" class="i-btn i-btn--suave" data-inv-cambiar>Cambiar</button>`;
    invQueda();
  }
  $("#invCantidad")?.focus();
}
function invQueda() {
  const p = invOperacion?.producto, c = Number($("#invCantidad")?.value), e = $("#invQueda");
  if (!e) return;
  e.textContent = p && c > 0 ? `Quedarán ${p.stock - c} ${invUnidad(p)}.` : "";
  const et = $("#invCantidadEtiqueta"); if (et) et.textContent = p && p.ingrediente ? `Cantidad (${invUnidad(p)})` : "Cantidad";
}
function invDiferenciaTexto(celda, n, p) {
  if (n == null) { celda.textContent = "—"; celda.className = "i-dif"; return; }
  const d = n - p.stock;
  celda.textContent = d === 0 ? "Cuadra" : (d > 0 ? "+" : "−") + Math.abs(d);
  celda.className = "i-dif " + (d === 0 ? "i-dif--ok" : d > 0 ? "i-dif--mas" : "i-dif--menos");
}
function invFiltrarConteo() {
  const q = $("#invBuscarMovimiento").value;
  $$('[data-inv-conteo-fila]').forEach((fila) => {
    const p = invItem(+fila.dataset.invConteoFila), n = invContados[p?.id];
    if (!p) return;
    fila.hidden = !IL.coincide(p, q) || (invConteoFiltro === "sin" && n != null)
      || (invConteoFiltro === "diferencia" && (n == null || n === p.stock));
  });
  $$("[data-inv-conteo-filtro]").forEach((b) => b.classList.toggle("is-on", b.dataset.invConteoFiltro === invConteoFiltro));
}
function invPintarEntradas() {
  const caja = $("#invEntradas");
  if (!caja) return;
  caja.innerHTML = invEntradas.length ? `<div class="i-reng i-reng--tit"><span>Producto</span><span>Llegaron</span><span>Costo c/u <em>(opcional)</em></span><span></span></div>`
    + invEntradas.map((r, i) => `<div class="i-reng" data-inv-entrada="${i}">
      <span class="i-reng__nom"><b>${esc(r.producto.nombre)}</b><small>Hay ${invHay(r.producto)}${r.producto.ingrediente ? "" : " un"}</small></span>
      <label class="i-campo i-campo--sola"><input type="number" min="1" step="1" placeholder="0" aria-label="Cantidad que llegó de ${esc(r.producto.nombre)}" data-inv-entrada-cantidad="${i}" value="${esc(r.cantidad)}"><i>${invUnidad(r.producto)}</i></label>
      ${r.producto.ingrediente ? "<span></span>" : `<label class="i-campo i-campo--sola"><b class="i-pre">$</b><input type="number" min="0" step="1" placeholder="${esc(r.producto.costo ?? "")}" aria-label="Costo por unidad de ${esc(r.producto.nombre)}" data-inv-entrada-costo="${i}" value="${esc(r.costo)}"></label>`}
      <button class="i-ico i-ico--borra" data-inv-quitar-entrada="${i}" aria-label="Quitar renglón">${INV_ICONO.cierra}</button></div>`).join("")
    : '<div class="i-vacio">Todavía no agregas nada. Busca arriba el primer producto.</div>';
}
function invAgregarEntrada(p) {
  if (!p) return;
  let r = invEntradas.find((x) => x.producto.id === p.id);
  if (!r) { r = { producto: p, cantidad: "", costo: "" }; invEntradas.push(r); }
  invOperacion.producto = null; $("#invBuscarMovimiento").value = ""; invSugerencias("");
  invPintarEntradas();
  const campo = $(`[data-inv-entrada-cantidad="${invEntradas.indexOf(r)}"]`); campo?.focus(); campo?.select?.();
}
/* Conteo rechazado porque se vendió algo mientras se contaba: se trae el saldo nuevo y se conserva lo contado. */
async function invRefrescarConteo() {
  const antes = Object.fromEntries(invPool().map((p) => [p.id, p.stock]));
  await cargarInventario();
  const cambiados = [];
  for (const p of invPool()) {
    if (antes[p.id] != null && antes[p.id] !== p.stock) cambiados.push(`${p.nombre} (${antes[p.id] - p.stock})`);
    const sis = $(`[data-inv-sistema="${p.id}"]`);
    if (sis) sis.textContent = invHay(p);
    const campo = $(`[data-inv-contado="${p.id}"]`), dif = $(`[data-inv-diferencia="${p.id}"]`);
    if (campo && dif) invDiferenciaTexto(dif, campo.value === "" ? null : Number(campo.value), p);
  }
  invFiltrarConteo();
  const lista = cambiados.slice(0, 3).join(", ") + (cambiados.length > 3 ? " y más" : "");
  avisar(cambiados.length ? `Se vendió ${lista} mientras contabas: revisa la diferencia y guarda de nuevo`
    : "El saldo cambió mientras contabas: revisa la diferencia y guarda de nuevo", true);
}
async function invGuardarMovimiento() {
  if (!invOperacion || !invPuedeStock()) return;
  const boton = $("#invGuardarMovimiento");
  if (boton.disabled) return;
  boton.disabled = true;
  try {
    if (invOperacion.tipo === "entrada") {
      const filas = invEntradas.filter((r) => r.cantidad !== "");
      if (!filas.length) throw new Error("Escribe cuántos llegaron de al menos un producto");
      for (const r of filas) if (!Number.isInteger(Number(r.cantidad)) || Number(r.cantidad) < 1)
        throw new Error(`La cantidad de ${r.producto.nombre} debe ser un entero mayor que cero`);
      // Cada renglón confirmado se retira: un error posterior no duplica compras al reintentar.
      for (const r of filas) {
        await api("/inventario/compras", { method: "POST", body: JSON.stringify({
          insumo_id: r.producto.insumo_id, cantidad: Number(r.cantidad),
          costo_unitario: r.costo === "" || r.producto.ingrediente ? null : Number(r.costo),
          motivo: "Entrada de mercadería desde Inventario" }) });
        invEntradas.splice(invEntradas.indexOf(r), 1); invPintarEntradas();
      }
    } else if (invOperacion.tipo === "conteo") {
      const conteos = {}, esperados = {};
      $$('[data-inv-contado]').forEach((campo) => {
        if (campo.value === "") return;
        if (!campo.validity.valid) throw new Error("El conteo debe ser entero y mayor o igual a cero");
        const p = invItem(+campo.dataset.invContado);
        if (!p) return;
        conteos[p.insumo_id] = Number(campo.value); esperados[p.insumo_id] = p.stock;
      });
      if (!Object.keys(conteos).length) throw new Error("Cuenta al menos un producto");
      try {
        await api("/inventario/conteo", { method: "POST", body: JSON.stringify({ conteos, esperados, nota: "Conteo desde Inventario" }) });
      } catch (e) {
        if (e.status === 409) { await invRefrescarConteo(); return; }
        throw e;
      }
    } else {
      const p = invOperacion.producto, campo = $("#invCantidad"), motivo = $("#invMotivo").value, otro = $("#invOtroMotivo").value.trim();
      if (!p || !campo.validity.valid || !campo.value || !motivo || (motivo === "Otro" && !otro)) throw new Error("Elige producto, cantidad y motivo; escribe el detalle si es otro");
      await api("/inventario/mermas", { method: "POST", body: JSON.stringify({ insumo_id: p.insumo_id,
        cantidad: Number(campo.value), motivo: motivo === "Otro" ? `Otro: ${otro}` : motivo }) });
    }
    $("#capaBodega").classList.remove("is-on"); invOperacion = null;
    await cargarCarta(); await cargarInventario(); avisar("Movimiento guardado");
  } catch (e) { avisar(e.message, true); }
  finally { boton.disabled = false; }
}

function invEscanear(codigo) {
  if ($("#capaProducto.is-on") && invFicha) { invAgregarCodigo(codigo); return true; }
  const movimiento = $("#capaBodega.is-on") && invOperacion;
  if ($$(".capa.is-on").length && !movimiento) return false;
  if (!movimiento && $(".vista.is-on")?.dataset.vista !== "inventario") return false;
  const p = (movimiento ? invPool() : INV.productos).find((p) => IL.exacto(p, codigo));
  if (!p) { avisar("Ese código no está en Inventario", true); return true; }
  if (movimiento && invOperacion.tipo === "conteo") {
    $("#invBuscarMovimiento").value = ""; invConteoFiltro = "todos"; invFiltrarConteo();
    const campo = $(`[data-inv-contado="${p.id}"]`); campo.scrollIntoView({ block: "nearest" }); campo.focus();
  } else if (movimiento && invOperacion.tipo === "entrada") invAgregarEntrada(p);
  else if (movimiento) invElegirMovimiento(p.id);
  else abrirFichaProducto(p.id);
  return true;
}

/* ---------------------------------------------------------------- eventos */
document.addEventListener("input", (e) => {
  const t = e.target;
  if (t.id === "invBuscar") { invBusqueda = t.value; invPintarFilas(); }
  if (t.id === "invCosto") invPrecio("costo");
  if (t.id === "invGanancia") invPrecio("ganancia");
  if (t.id === "invHay" && invFicha) invFicha.hayEditado = true;
  if (t.id === "fPrecio") invPrecio("venta");
  if (["fNombre", "invColor", "fColorLibre"].includes(t.id)) {
    if (t.id === "invColor") $("#fColor").value = t.value;
    invPrevia();
  }
  if (t.id === "invCategoriaTxt") invCategoriaLista();
  if (t.id === "invBuscarCategorias") $$('[data-inv-cat-fila]').forEach((f) => { f.hidden = !IL.normalizar(f.querySelector("input").value).includes(IL.normalizar(t.value)); });
  if (t.id === "invBuscarMovimiento" && invOperacion) {
    if (invOperacion.tipo === "conteo") invFiltrarConteo();
    else { if (invOperacion.tipo === "merma") invOperacion.producto = null; invSugerencias(t.value); }
  }
  if (t.id === "invCantidad") invQueda();
  if (t.dataset.invContado) {
    const id = +t.dataset.invContado, p = invItem(id);
    if (!p) return;
    if (t.value === "") delete invContados[id]; else invContados[id] = Number(t.value);
    invDiferenciaTexto($(`[data-inv-diferencia="${id}"]`), t.value === "" ? null : Number(t.value), p);
    $("#invMensaje").textContent = `${Object.keys(invContados).length} contados de ${invPool().length}.`;
    // La fila no desaparece mientras se escribe: el filtro se aplica al cambiar de campo.
  }
  if (t.dataset.invEntradaCantidad != null && t.dataset.invEntradaCantidad !== "") invEntradas[+t.dataset.invEntradaCantidad].cantidad = t.value;
  if (t.dataset.invEntradaCosto != null && t.dataset.invEntradaCosto !== "") invEntradas[+t.dataset.invEntradaCosto].costo = t.value;
});
document.addEventListener("focusout", (e) => { if (e.target.dataset?.invContado && invConteoFiltro !== "todos") invFiltrarConteo(); });
document.addEventListener("focusin", (e) => { if (e.target.id === "invCategoriaTxt") { e.target.select(); invCategoriaLista(); } });
document.addEventListener("change", (e) => {
  if (e.target.id === "fCuenta") $("#invSaldo").hidden = !e.target.checked;
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (e.target.id === "fCodigo") { e.preventDefault(); invAgregarCodigo(); }
  if (e.target.id === "invBuscar") { e.preventDefault(); invEscanear(e.target.value); }
  if (e.target.id === "invCategoriaTxt") {
    e.preventDefault();
    const t = IL.normalizar(e.target.value);
    const c = CATEGORIAS.find((c) => IL.normalizar(c.nombre) === t) || CATEGORIAS.find((c) => IL.normalizar(c.nombre).includes(t));
    if (c) invElegirCategoria(c);
  }
  if (e.target.id === "invBuscarMovimiento" && invOperacion) {
    e.preventDefault();
    const pool = invPool();
    const p = pool.find((p) => IL.exacto(p, e.target.value)) || pool.find((p) => IL.coincide(p, e.target.value));
    if (!p) return;
    if (invOperacion.tipo === "conteo") {
      invConteoFiltro = "todos"; e.target.value = ""; invFiltrarConteo();
      $(`[data-inv-contado="${p.id}"]`).focus();
    } else if (invOperacion.tipo === "entrada") invAgregarEntrada(p);
    else invElegirMovimiento(p.id);
  }
});
document.addEventListener("mousedown", (e) => { if (e.target.closest?.(".i-resultados")) e.preventDefault(); });
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  const fila = e.target.closest("tr[data-inv-producto]");
  if (!b && fila) return abrirFichaProducto(+fila.dataset.invProducto);
  if (!b || b.disabled) return;
  try {
    if (b.dataset.invLimpiar) { const c = $("#" + b.dataset.invLimpiar); c.value = ""; c.dispatchEvent(new Event("input", { bubbles: true })); c.focus(); }
    if (b.id === "invNuevo") await abrirFichaProducto(null);
    if (b.dataset.invProducto) await abrirFichaProducto(+b.dataset.invProducto);
    if (b.id === "invCategorias") invAbrirCategorias();
    if (b.id === "invVerIngredientes") invAbrirIngredientes();
    if (b.dataset.invIngOperacion) await invAbrirOperacion(b.dataset.invIngOperacion, true);
    if (b.dataset.invFiltro) { invFiltro = invFiltro === b.dataset.invFiltro && b.dataset.invFiltro === "comprar" ? "todos" : b.dataset.invFiltro; pintarInventario(); }
    if (b.hasAttribute("data-inv-categoria")) { invCategoria = b.dataset.invCategoria ? +b.dataset.invCategoria : null; pintarInventario(); }
    if (b.id === "invOtroCodigo") invAgregarCodigo();
    if (b.hasAttribute("data-inv-quitar-codigo")) { invCodigos.splice(+b.dataset.invQuitarCodigo, 1); invPintarCodigos(); }
    if (b.dataset.invModo) {
      $("#invModo").value = b.dataset.invModo; invFicha.modoCambiado = true;
      const peso = b.dataset.invModo === "peso";
      $$("[data-inv-modo]").forEach((x) => { const on = x === b; x.classList.toggle("is-on", on); x.setAttribute("aria-checked", on); });
      $("#invPeso").hidden = !peso;
      $("#fPrecio").previousElementSibling.textContent = peso ? "Precio por kilo" : "Precio venta";
      $("#invCosto").previousElementSibling.textContent = peso ? "Costo por kilo" : "Precio costo";
      invPrecio();
    }
    if (b.dataset.invRedondeo) {
      invPaso = +b.dataset.invRedondeo;
      $$("[data-inv-redondeo]").forEach((x) => x.classList.toggle("is-on", x === b));
      invPrecio();
    }
    if (b.id === "invUsarSugerido") { $("#fPrecio").value = b.dataset.sugerido; invPrecio("venta"); }
    if (b.dataset.invCatElegir) invElegirCategoria(invCategoriaDe(+b.dataset.invCatElegir));
    if (b.dataset.invCatCrear) {
      const nombre = $("#invCategoriaTxt").value.trim();
      const nueva = await api("/categorias", { method: "POST", body: JSON.stringify({ nombre, orden: CATEGORIAS.length }) });
      await cargarCarta();
      invElegirCategoria(invCategoriaDe(nueva.id) || { id: nueva.id, nombre });
    }
    if (b.dataset.invCatDibujo) invAbrirDibujoCategoria(+b.dataset.invCatDibujo);
    if (b.hasAttribute("data-inv-cat-volver")) { invCatDibujoId = null; invAbrirCategorias(); }
    if (b.dataset.invCatAuto) await invGuardarDibujoCategoria("", "", true);
    if (invCatDibujoId != null && b.closest("#dialogoBodega")) {
      if (b.dataset.dibujo) {
        const bolsa = esDibujoDeBolsa(b.dataset.dibujo);
        await invGuardarDibujoCategoria(b.dataset.dibujo, bolsa ? ($("#fColor")?.value || "") : "", !bolsa);
      } else if (b.hasAttribute("data-color-bolsa")) {
        const k = $("#fDibujo")?.value;
        if (esDibujoDeBolsa(k)) await invGuardarDibujoCategoria(k, b.dataset.colorBolsa || "", false);
      }
    }
    if (b.dataset.dibujo || b.hasAttribute("data-color-bolsa")) invPrevia();
    if (b.id === "fGuardar") await invGuardarFicha();
    if (b.id === "invEliminar" && invFicha && confirm(`¿Eliminar «${invFicha.nombre}»? Las ventas y los movimientos se conservan.`)) {
      await api(`/productos/${invFicha.id}`, { method: "DELETE" }); $("#capaProducto").classList.remove("is-on"); invFicha = null; await cargarCarta(); await cargarInventario();
    }
    if (b.dataset.invOperacion) await invAbrirOperacion(b.dataset.invOperacion);
    if (b.dataset.invElegir) {
      if (invOperacion?.tipo === "entrada") invAgregarEntrada(invItem(+b.dataset.invElegir));
      else invElegirMovimiento(+b.dataset.invElegir);
    }
    if (b.hasAttribute("data-inv-cambiar")) {
      invOperacion.producto = null; $("#invElegido").hidden = true; $("#invElige").hidden = false;
      $("#invBuscarMovimiento").focus(); invQueda();
    }
    if (b.dataset.invMotivo) {
      $("#invMotivo").value = b.dataset.invMotivo;
      $$("[data-inv-motivo]").forEach((x) => x.classList.toggle("is-on", x === b));
      $("#invDetalle").hidden = b.dataset.invMotivo !== "Otro";
    }
    if (b.hasAttribute("data-inv-quitar-entrada")) { invEntradas.splice(+b.dataset.invQuitarEntrada, 1); invPintarEntradas(); }
    if (b.dataset.invConteoFiltro) { invConteoFiltro = b.dataset.invConteoFiltro; invFiltrarConteo(); }
    if (b.id === "invGuardarMovimiento") await invGuardarMovimiento();
    if (b.id === "invCatCrear" || b.dataset.invCatGuardar || b.dataset.invCatBorrar) {
      if (b.id === "invCatCrear") {
        const nombre = $("#invCatNueva").value.trim(); if (!nombre) throw new Error("Escribe un nombre");
        await api("/categorias", { method: "POST", body: JSON.stringify({ nombre, orden: CATEGORIAS.length }) });
      } else {
        const id = +(b.dataset.invCatGuardar || b.dataset.invCatBorrar), c = CATEGORIAS.find((c) => c.id === id);
        if (b.dataset.invCatBorrar) {
          if (!confirm(`¿Borrar «${c.nombre}»?`)) return;
          await api(`/categorias/${id}`, { method: "DELETE" });
        } else {
          const f = b.closest("[data-inv-cat-fila]");
          await api(`/categorias/${id}`, { method: "PUT", body: JSON.stringify({ nombre: f.querySelector('[data-inv-cat-nombre]').value.trim(), orden: Number(f.querySelector('[data-inv-cat-orden]').value), activa: c.activa }) });
        }
      }
      await cargarCarta(); await cargarInventario(); invAbrirCategorias();
    }
  } catch (err) { avisar(err.message, true); }
});
