/* Una lista y una ficha. El servidor conserva la autoridad sobre precios y stock. */
let INV = { productos: [], recetas_antiguas: false };
let invFiltro = "todos", invCategoria = null, invBusqueda = "", invCarga = 0;
let invFicha = null, invCodigos = [], invOperacion = null;
let invEntradas = [], invContados = {}, invConteoFiltro = "todos";
const IL = window.InventarioLogica;
const invPuedeStock = () => usarInventario() && puedo("inventario");
const invPuedeContar = () => invPuedeStock() && puedo("inventario_ajustar");

function invBuscador(id, placeholder, valor = "") {
  return `<div class="buscador inv-busca"><svg class="buscador__lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 21 21"/></svg>
    <input type="search" id="${id}" value="${esc(valor)}" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}" autocomplete="off" spellcheck="false">
    <button type="button" class="buscador__x" data-inv-limpiar="${id}" aria-label="Limpiar búsqueda">×</button></div>`;
}

async function cargarInventario() {
  const carga = ++invCarga;
  if (!puedo("editar_carta") && !puedo("inventario")) {
    INV = { productos: [], recetas_antiguas: false };
    $("#vistaInventario").innerHTML = '<p class="vacio">No tienes permiso para ver Inventario.</p>';
    return;
  }
  try {
    const d = await api("/inventario/productos");
    if (carga !== invCarga) return;
    INV = d;
    pintarInventario();
  } catch (e) { avisar(e.message, true); }
}

function pintarInventario() {
  const raiz = $("#vistaInventario");
  if (!raiz) return;
  const editar = puedo("editar_carta"), stock = invPuedeStock();
  raiz.innerHTML = `<div class="inv-barra">
    <div class="inv-acciones"><button class="btn btn--cobrar" id="invNuevo" ${editar ? "" : "disabled"}>+ Nuevo producto</button>
      <button class="btn" id="invCategorias" ${editar ? "" : "disabled"}>Categorías</button>
      <button class="btn" id="btnImportar" ${editar ? "" : "disabled"}>Importar</button></div>
    <div class="inv-acciones" ${stock ? "" : "hidden"}><button class="btn" data-inv-operacion="entrada">Entrada de mercadería</button>
      <button class="btn" data-inv-operacion="conteo" ${invPuedeContar() ? "" : "disabled"}>Conteo</button>
      <button class="btn" data-inv-operacion="merma">Merma</button>
      <button class="btn inv-comprar" data-inv-filtro="comprar">Por comprar (${INV.productos.filter(IL.porComprar).length})</button></div></div>
    <div class="inv-filtros">${invBuscador("invBuscar", "Buscar por nombre, código de barras o PLU", invBusqueda)}
      <div class="inv-acciones">${[["todos", "Todos"], ["cuenta", "Con inventario"], ["comprar", "Por comprar"], ["ocultos", "Ocultos"]]
        .filter(([k]) => stock || !["cuenta", "comprar"].includes(k))
        .map(([k, n]) => `<button class="btn ${invFiltro === k ? "is-on" : ""}" data-inv-filtro="${k}">${n}</button>`).join("")}</div></div>
    <div class="inv-categorias"><button class="btn ${invCategoria == null ? "is-on" : ""}" data-inv-categoria="">Todas</button>
      ${CATEGORIAS.map((c) => `<button class="btn ${invCategoria === c.id ? "is-on" : ""}" data-inv-categoria="${c.id}">${esc(c.nombre)}</button>`).join("")}</div>
    ${INV.recetas_antiguas ? '<p class="ayuda inv-legado">Este local tiene recetas antiguas: siguen funcionando</p>' : ""}
    <div class="inv-tabla"><table class="tabla"><thead><tr><th>Producto</th><th>Categoría</th><th class="num">Precio</th><th class="num">Stock</th></tr></thead><tbody id="invFilas"></tbody></table></div>
    <p class="ayuda" id="invTotal" role="status"></p>`;
  invPintarFilas();
}

function invPintarFilas() {
  const filas = INV.productos.filter((p) => IL.coincide(p, invBusqueda)
    && (invCategoria == null || p.categoria_id === invCategoria)
    && (invFiltro !== "cuenta" || p.cuenta) && (invFiltro !== "comprar" || IL.porComprar(p))
    && (invFiltro !== "ocultos" || !p.activo))
    .sort((a,b) => CATEGORIAS.findIndex(c => c.id === a.categoria_id) - CATEGORIAS.findIndex(c => c.id === b.categoria_id)
      || a.orden - b.orden || a.id - b.id);
  const cuerpo = $("#invFilas");
  if (!cuerpo) return;
  cuerpo.innerHTML = filas.map((p) => `<tr data-inv-producto="${p.id}"><td><button class="inv-producto" data-inv-producto="${p.id}">
    <span class="inv-dibujo">${dibujo({ k: p.dibujo, col: p.color || undefined })}</span>
    <span><b>${esc(p.nombre)}</b><small>${!p.activo ? "No está a la venta" : ""}${!p.en_tv ? (p.activo ? "" : " · ") + "Sin TV" : ""}</small></span></button></td>
    <td>${esc(CATEGORIAS.find((c) => c.id === p.categoria_id)?.nombre || "")}</td>
    <td class="num">${clp(p.precio_kilo > 0 && !p.precio ? p.precio_kilo : p.precio)}${p.precio_kilo > 0 && !p.precio ? " / kg" : ""}</td>
    <td class="num ${IL.porComprar(p) ? "inv-bajo" : ""}">${p.cuenta && invPuedeStock() ? p.stock : "—"}
      ${p.cuenta && invPuedeStock() && p.minimo ? `<small>mín. ${p.minimo}</small>` : ""}</td></tr>`).join("")
      || '<tr><td colspan="4">No hay productos con estos filtros.</td></tr>';
  $("#invTotal").textContent = `${filas.length} productos`;
}

function invCampo(id, nombre, valor = "", tipo = "text", extra = "") {
  return `<label class="campo"><span>${nombre}</span><input id="${id}" type="${tipo}" value="${esc(valor)}" ${extra}></label>`;
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
  const editar = puedo("editar_carta"), stock = editar && invPuedeStock() && !p.receta_antigua;
  const porPeso = p.precio_kilo > 0 && !p.precio;
  $("#dialogoProducto").className = "dialogo inv-dialogo inv-ficha";
  $("#dialogoProducto").innerHTML = `<h2>${p.id == null ? "Nuevo producto" : "Ficha de producto"}</h2>
    <div class="inv-interior"><fieldset ${editar ? "" : "disabled"} class="inv-campos">
    <section><h3>Producto</h3><div id="invCodigos"></div><div class="inv-codigo-nuevo">
      <input id="fCodigo" placeholder="Código de barras" aria-label="Código de barras" autocomplete="off">
      <button class="btn" id="invOtroCodigo">+ otro código</button></div>
      ${invCampo("fNombre", "Nombre", p.nombre)}
      ${CATEGORIAS.length > 8 ? invBuscador("invCategoriaBuscar", "Buscar categoría") : ""}
      <label class="campo"><span>Categoría</span><select id="fCategoria">${CATEGORIAS.map((c) => `<option value="${c.id}" ${c.id === p.categoria_id ? "selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>
      <label class="campo"><span>Se vende</span><select id="invModo"><option value="unidad">Por unidad</option><option value="peso" ${porPeso ? "selected" : ""}>Por peso (balanza)</option></select></label>
      <div id="invPeso" ${porPeso ? "" : "hidden"}>${invCampo("fPlu", "PLU de balanza", p.plu || "", "text", 'inputmode="numeric"')}</div>
      <h3 id="invTituloPrecios">Precios ${porPeso ? "por kilo" : ""}</h3><div class="inv-precios">
        ${invCampo("invCosto", "Costo", p.costo, "number", 'min="0" step="1"')}
        ${invCampo("invGanancia", "Ganancia % sobre costo", IL.ganancia(p.costo, porPeso ? p.precio_kilo : p.precio)?.toFixed(2) || "", "number", 'min="-99" step="0.01"')}
        ${invCampo("fPrecio", "Precio de venta", porPeso ? p.precio_kilo : p.precio, "number", 'min="0" step="1"')}</div>
      <div class="inv-acciones"><span>Redondear hacia arriba</span><button class="btn" data-inv-redondeo="10">$10</button><button class="btn" data-inv-redondeo="50">$50</button>
        <button class="btn" id="invSugerido">Sugerido</button></div>
      <p class="ayuda" id="invSugeridoTexto"></p>
      ${p.precio > 0 && p.precio_kilo > 0 ? `<p class="ayuda">También conserva su precio anterior de balanza: ${clp(p.precio_kilo)} / kg.</p>` : ""}
      <h3>Dónde aparece</h3><label class="marca"><input type="checkbox" id="fActivo" ${p.activo ? "checked" : ""}> A la venta</label>
      <label class="marca"><input type="checkbox" id="fTv" ${p.en_tv ? "checked" : ""}> En los televisores</label>
      <!-- Aquí iría la visibilidad del tótem cuando se integre su rama. -->
      ${stock ? `<h3>Inventario</h3><label class="marca"><input type="checkbox" id="fCuenta" role="switch" ${p.cuenta ? "checked" : ""}
        ${!p.cuenta && !p.contado && !invPuedeContar() ? "disabled" : ""}> Este producto lleva inventario</label>
        ${!p.cuenta && !p.contado && !invPuedeContar() ? '<p class="ayuda">Activarlo pide contar cuántos hay: hace falta el permiso para corregir el stock.</p>' : ""}
        <div id="invSaldo" ${p.cuenta ? "" : "hidden"}><div class="fila2">${invCampo("invHay", "Hay ahora", p.stock, "number", `min="0" step="1" ${invPuedeContar() ? "" : "disabled"}`)}
        ${invCampo("invMinimo", "Mínimo", p.minimo, "number", 'min="0" step="1"')}</div>
        <p class="ayuda">Contar registra un movimiento. Apagar conserva todo el historial.</p></div>` : ""}
      ${p.receta_antigua ? '<p class="ayuda">Este producto tiene una receta antigua: sigue funcionando.</p>' : ""}</section>
    <section><h3>Cómo se ve</h3><div id="invPrevia" class="inv-previa"></div>
      ${selectorDeDibujo(p.dibujo, p.color)}
      <label class="campo"><span>Color</span><input type="color" id="invColor" value="${colorBolsaOk(p.color) ? esc(p.color) : "#c9552b"}"></label>
    </section></fieldset></div>
    <div class="dialogo__pie"><button class="btn btn--peligro" id="invEliminar" ${p.id == null || !editar ? "hidden" : ""}>Eliminar</button>
      <button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button><button class="btn btn--cobrar" id="fGuardar" ${editar ? "" : "disabled"}>Guardar</button></div>`;
  invPintarCodigos(); invPrevia(); invPrecio("venta");
  $("#capaProducto").classList.add("is-on");
  $("#fNombre").focus();
}

function invPintarCodigos() {
  $("#invCodigos").innerHTML = invCodigos.map((b, i) => `<span class="inv-chip"><code>${esc(b.codigo)}</code>${b.cuantos > 1 ? ` × ${b.cuantos}` : ""}
    <button type="button" class="btn btn--fantasma" data-inv-quitar-codigo="${i}" aria-label="Quitar código ${esc(b.codigo)}">×</button></span>`).join("");
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
  const s = IL.sugerido(Number(c.value), AJUSTES.margen_sugerido, AJUSTES.redondeo_precio);
  $("#invSugeridoTexto").textContent = `Sugerido ${clp(s)} · margen de Ajustes ${AJUSTES.margen_sugerido}% sobre la venta. El precio de venta es el que cobra la caja.`;
  invPrevia();
}
function invPrevia() {
  const previa = $("#invPrevia");
  if (!previa) return;
  previa.innerHTML = `${dibujo({ k: $("#fDibujo").value, col: $("#fColor").value || invFicha.color || undefined })}<b>${esc($("#fNombre").value || "Nombre del producto")}</b>
    <span>${clp($("#fPrecio").value)}${$("#invModo").value === "peso" ? " / kg" : ""}</span>`;
}

async function invGuardarFicha() {
  if (!invFicha || !puedo("editar_carta")) return;
  const boton = $("#fGuardar");
  if (boton.disabled) return;
  const p = invFicha, peso = $("#invModo").value === "peso";
  const nombre = $("#fNombre").value.trim();
  if (!nombre) return avisar("Escribe el nombre del producto", true);
  for (const id of ["invCosto", "fPrecio", "invMinimo", "invHay"]) {
    const campo = $("#" + id);
    if (id === "invHay" && p.cuenta && !p.hayEditado) continue;
    if (campo && !campo.disabled && !campo.closest("[hidden]") && (!campo.validity.valid || campo.value === ""))
      return avisar("Revisa el valor de " + campo.previousElementSibling.textContent, true);
  }
  invAgregarCodigo();
  const cuerpo = { categoria_id: Number($("#fCategoria").value), nombre,
    precio: peso ? 0 : Number($("#fPrecio").value), precio_kilo: peso ? Number($("#fPrecio").value) : 0,
    plu: peso ? $("#fPlu").value.trim() : "", costo: Number($("#invCosto").value),
    activo: $("#fActivo").checked, en_tv: $("#fTv").checked,
    dibujo: $("#fDibujo").value, color: $("#fColor").value || p.color || "",
    codigos: invCodigos, descripcion: p.descripcion || "", orden: p.orden || 0,
    destacado: p.destacado || false, badge: p.badge || "", antes: p.antes ?? null, etiqueta: p.etiqueta || "" };
  // Mostrar un costo unitario redondeado no debe reescribir un envase antiguo.
  if (p.id != null && cuerpo.costo === p.costo) delete cuerpo.costo;
  // Fichas anteriores podían cobrar unidades y balanza. Editar su nombre no borra el PLU.
  if (!peso && !p.modoCambiado && p.precio > 0 && p.precio_kilo > 0) {
    cuerpo.plu = p.plu; cuerpo.precio_kilo = p.precio_kilo;
  }
  const cuenta = $("#fCuenta");
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

function invAbrirCategorias() {
  if (!puedo("editar_carta")) return;
  invOperacion = null;
  $("#dialogoBodega").className = "dialogo inv-dialogo";
  $("#dialogoBodega").innerHTML = `<h2>Categorías</h2><div class="inv-interior">
    ${invBuscador("invBuscarCategorias", "Buscar categoría")}
    <div id="invListaCategorias">${CATEGORIAS.map((c) => `<div class="inv-categoria-fila" data-inv-cat-fila="${c.id}">
      <input aria-label="Nombre de categoría" data-inv-cat-nombre value="${esc(c.nombre)}">
      <input aria-label="Orden de categoría" type="number" data-inv-cat-orden value="${c.orden}">
      <button class="btn" data-inv-cat-guardar="${c.id}">Guardar</button>
      <button class="btn btn--peligro" data-inv-cat-borrar="${c.id}" ${(c.productos || []).length ? "disabled" : ""}>Borrar</button></div>`).join("")}</div>
    <div class="inv-categoria-fila"><input id="invCatNueva" aria-label="Nueva categoría" placeholder="Nueva categoría"><button class="btn" id="invCatCrear">Crear</button></div>
    </div><div class="dialogo__pie"><button class="btn" data-cerrar-capa>Cerrar</button></div>`;
  $("#capaBodega").classList.add("is-on");
}

function invProductosStock() { return INV.productos.filter((p) => p.cuenta && !p.receta_antigua && p.insumo_id); }
function invSugerencias(texto) {
  const filas = invProductosStock().filter((p) => IL.coincide(p, texto));
  $("#invSugerencias").innerHTML = texto ? filas.slice(0, 12).map((p) => `<button class="btn inv-sugerencia" data-inv-elegir="${p.id}">${esc(p.nombre)} · ${p.stock} un</button>`).join("") || '<p class="ayuda">No hay productos con inventario.</p>' : "";
}
async function invAbrirOperacion(tipo) {
  if (!invPuedeStock() || (tipo === "conteo" && !invPuedeContar())) return;
  await cargarInventario();
  invOperacion = { tipo, producto: null }; invEntradas = []; invContados = {}; invConteoFiltro = "todos";
  const titulo = { entrada: "Entrada de mercadería", conteo: "Conteo", merma: "Merma" }[tipo];
  $("#dialogoBodega").className = "dialogo inv-dialogo";
  $("#dialogoBodega").innerHTML = `<h2>${titulo}</h2><div class="inv-interior">${invBuscador("invBuscarMovimiento", "Buscar por nombre, código de barras o PLU")}
    ${tipo === "conteo" ? `<div class="inv-acciones">${[["todos", "Todos"], ["sin", "Sin contar"], ["diferencia", "Con diferencia"]].map(([k, n]) => `<button class="btn" data-inv-conteo-filtro="${k}">${n}</button>`).join("")}</div>
      <div class="tabla-wrap"><table class="tabla"><thead><tr><th>Producto</th><th>En sistema</th><th>Contado</th><th>Diferencia</th></tr></thead>
      <tbody id="invConteoFilas">${invProductosStock().map((p) => `<tr data-inv-conteo-fila="${p.id}"><td>${esc(p.nombre)}</td><td>${p.stock}</td><td>
      <input type="number" min="0" step="1" aria-label="Contado de ${esc(p.nombre)}" data-inv-contado="${p.id}" value=""></td><td data-inv-diferencia="${p.id}">—</td></tr>`).join("")}</tbody></table></div>`
      : `<div id="invSugerencias" class="inv-sugerencias"></div><p id="invElegido" class="ayuda">Elige un producto con inventario</p>
      <div class="fila2">${invCampo("invCantidad", "Cantidad", "", "number", 'min="1" step="1"')}
      ${tipo === "entrada" ? invCampo("invCompraCosto", "Costo por unidad (opcional)", "", "number", 'min="0" step="1"') : `<label class="campo"><span>Motivo</span><select id="invMotivo"><option value="">Elige un motivo</option><option>Vencido</option><option>Roto</option><option>Consumo interno</option><option>Otro</option></select></label>`}</div>
      ${tipo === "entrada" ? '<button class="btn" id="invAgregarEntrada">Agregar renglón</button><div id="invEntradas"></div>' : invCampo("invOtroMotivo", "Detalle (obligatorio si es otro)")}`}
    </div><div class="dialogo__pie"><button class="btn btn--fantasma" data-cerrar-capa>Cancelar</button><button class="btn btn--cobrar" id="invGuardarMovimiento">Guardar</button></div>`;
  $("#capaBodega").classList.add("is-on"); $("#invBuscarMovimiento").focus();
}
function invElegirMovimiento(id) {
  const p = invProductosStock().find((p) => p.id === id);
  if (!p) return;
  invOperacion.producto = p;
  $("#invElegido").textContent = p.nombre;
  $("#invSugerencias").innerHTML = "";
  $("#invBuscarMovimiento").value = p.nombre;
  $("#invCantidad").focus();
}
function invFiltrarConteo() {
  const q = $("#invBuscarMovimiento").value;
  $$('[data-inv-conteo-fila]').forEach((fila) => {
    const p = INV.productos.find((p) => p.id === +fila.dataset.invConteoFila), n = invContados[p.id];
    fila.hidden = !IL.coincide(p, q) || (invConteoFiltro === "sin" && n != null)
      || (invConteoFiltro === "diferencia" && (n == null || n === p.stock));
  });
}
function invPintarEntradas() {
  $("#invEntradas").innerHTML = invEntradas.map((r, i) => `<div class="inv-entrada-fila"><b>${esc(r.producto.nombre)}</b><span>${r.cantidad} un${r.costo == null ? "" : ` · ${clp(r.costo)}/un`}</span><button class="btn" data-inv-quitar-entrada="${i}">Quitar</button></div>`).join("");
}
function invAgregarEntrada() {
  const p = invOperacion.producto, campo = $("#invCantidad"), c = $("#invCompraCosto");
  if (!p || !campo.validity.valid || !campo.value || (c.value && !c.validity.valid)) return avisar("Elige un producto y una cantidad entera mayor que cero", true);
  invEntradas.push({ producto: p, cantidad: Number(campo.value), costo: c.value === "" ? null : Number(c.value) });
  invOperacion.producto = null; $("#invBuscarMovimiento").value = ""; $("#invElegido").textContent = "Elige otro producto";
  campo.value = ""; c.value = ""; invPintarEntradas(); $("#invBuscarMovimiento").focus();
}
async function invGuardarMovimiento() {
  if (!invOperacion || !invPuedeStock()) return;
  const boton = $("#invGuardarMovimiento");
  if (boton.disabled) return;
  boton.disabled = true;
  try {
    if (invOperacion.tipo === "entrada") {
      if (invOperacion.producto) {
        const antes = invEntradas.length;
        invAgregarEntrada();
        if (invEntradas.length === antes) throw new Error("Revisa el renglón pendiente antes de guardar");
      }
      if (!invEntradas.length) throw new Error("Agrega al menos un renglón");
      // Cada renglón confirmado se retira: un error posterior no duplica compras al reintentar.
      while (invEntradas.length) {
        const r = invEntradas[0];
        await api("/inventario/compras", { method: "POST", body: JSON.stringify({
          insumo_id: r.producto.insumo_id, cantidad: r.cantidad,
          costo_unitario: r.costo,
          motivo: "Entrada de mercadería desde Inventario" }) });
        invEntradas.shift(); invPintarEntradas();
      }
    } else if (invOperacion.tipo === "conteo") {
      const conteos = {}, esperados = {};
      $$('[data-inv-contado]').forEach((campo) => {
        if (campo.value === "") return;
        if (!campo.validity.valid) throw new Error("El conteo debe ser entero y mayor o igual a cero");
        const p = INV.productos.find((p) => p.id === +campo.dataset.invContado);
        conteos[p.insumo_id] = Number(campo.value); esperados[p.insumo_id] = p.stock;
      });
      if (!Object.keys(conteos).length) throw new Error("Cuenta al menos un producto");
      await api("/inventario/conteo", { method: "POST", body: JSON.stringify({ conteos, esperados, nota: "Conteo desde Inventario" }) });
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
  const p = (movimiento ? invProductosStock() : INV.productos).find((p) => IL.exacto(p, codigo));
  if (!p) { avisar("Ese código no está en Inventario", true); return true; }
  if (movimiento && invOperacion.tipo === "conteo") {
    $("#invBuscarMovimiento").value = ""; invConteoFiltro = "todos"; invFiltrarConteo();
    const campo = $(`[data-inv-contado="${p.id}"]`); campo.scrollIntoView({ block: "nearest" }); campo.focus();
  } else if (movimiento) invElegirMovimiento(p.id);
  else abrirFichaProducto(p.id);
  return true;
}

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
  if (t.id === "invCategoriaBuscar") {
    const sel = $("#fCategoria");
    const cats = CATEGORIAS.filter((c) => IL.normalizar(c.nombre).includes(IL.normalizar(t.value)));
    const elegida = sel.value;
    sel.innerHTML = cats.map((c) => `<option value="${c.id}" ${String(c.id) === elegida ? "selected" : ""}>${esc(c.nombre)}</option>`).join("");
  }
  if (t.id === "invBuscarCategorias") $$('[data-inv-cat-fila]').forEach((f) => { f.hidden = !IL.normalizar(f.querySelector("input").value).includes(IL.normalizar(t.value)); });
  if (t.id === "invBuscarMovimiento") {
    if (invOperacion?.tipo === "conteo") invFiltrarConteo();
    else { invOperacion.producto = null; $("#invElegido").textContent = "Elige un producto"; invSugerencias(t.value); }
  }
  if (t.dataset.invContado) {
    const id = +t.dataset.invContado, p = INV.productos.find((p) => p.id === id);
    if (t.value === "") delete invContados[id]; else invContados[id] = Number(t.value);
    $(`[data-inv-diferencia="${id}"]`).textContent = t.value === "" ? "—" : Number(t.value) - p.stock;
    invFiltrarConteo();
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "fCuenta") $("#invSaldo").hidden = !e.target.checked;
  if (e.target.id === "invModo") {
    const peso = e.target.value === "peso";
    invFicha.modoCambiado = true;
    $("#invPeso").hidden = !peso;
    $("#invTituloPrecios").textContent = peso ? "Precios por kilo" : "Precios";
    $("#fPrecio").previousElementSibling.textContent = peso ? "Precio de venta por kilo" : "Precio de venta";
    $("#invCosto").previousElementSibling.textContent = peso ? "Costo por kilo" : "Costo";
    invPrevia();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (e.target.id === "fCodigo") { e.preventDefault(); invAgregarCodigo(); }
  if (e.target.id === "invBuscar") { e.preventDefault(); invEscanear(e.target.value); }
  if (e.target.id === "invBuscarMovimiento") {
    e.preventDefault();
    const p = invProductosStock().find((p) => IL.exacto(p, e.target.value))
      || invProductosStock().find((p) => IL.coincide(p, e.target.value));
    if (!p) return;
    if (invOperacion.tipo === "conteo") {
      invConteoFiltro = "todos"; e.target.value = ""; invFiltrarConteo();
      $(`[data-inv-contado="${p.id}"]`).focus();
    } else invElegirMovimiento(p.id);
  }
});
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
    if (b.dataset.invFiltro) { invFiltro = b.dataset.invFiltro; pintarInventario(); }
    if (b.hasAttribute("data-inv-categoria")) { invCategoria = b.dataset.invCategoria ? +b.dataset.invCategoria : null; pintarInventario(); }
    if (b.id === "invOtroCodigo") invAgregarCodigo();
    if (b.hasAttribute("data-inv-quitar-codigo")) { invCodigos.splice(+b.dataset.invQuitarCodigo, 1); invPintarCodigos(); }
    if (b.dataset.invRedondeo) { $("#fPrecio").value = IL.redondear(Number($("#fPrecio").value), +b.dataset.invRedondeo); invPrecio("venta"); }
    if (b.id === "invSugerido") { $("#fPrecio").value = IL.sugerido(Number($("#invCosto").value), AJUSTES.margen_sugerido, AJUSTES.redondeo_precio); invPrecio("venta"); }
    if (b.dataset.dibujo || b.hasAttribute("data-color-bolsa")) invPrevia();
    if (b.id === "fGuardar") await invGuardarFicha();
    if (b.id === "invEliminar" && invFicha && confirm(`¿Eliminar «${invFicha.nombre}»? Las ventas y los movimientos se conservan.`)) {
      await api(`/productos/${invFicha.id}`, { method: "DELETE" }); $("#capaProducto").classList.remove("is-on"); invFicha = null; await cargarCarta(); await cargarInventario();
    }
    if (b.dataset.invOperacion) await invAbrirOperacion(b.dataset.invOperacion);
    if (b.dataset.invElegir) invElegirMovimiento(+b.dataset.invElegir);
    if (b.id === "invAgregarEntrada") invAgregarEntrada();
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
