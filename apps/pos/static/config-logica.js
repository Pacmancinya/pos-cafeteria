/* La lógica de la pestaña Config que no necesita pantalla: buscar un ajuste sin tildes ni mayúsculas,
   armar la vista previa del ticket, validar el RUT, dibujar el formato de la balanza, armar las
   direcciones de los televisores, filtrar la lista de respaldos y escribir las frases de estado.
   Está aparte de config.js para poder probarla con Node (apps/pos/tests/config_logica.cjs). No toca
   el DOM ni le pide nada al servidor. */
(function (raiz) {
  "use strict";

  const sinTildes = (t) => String(t == null ? "" : t).normalize("NFD")
    .replace(/[̀-ͯ]/g, "").toLowerCase();
  const conMiles = (n) => String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const pesos = (n) => "$" + conMiles(n);

  /* ---------------- las secciones y el índice del buscador ---------------- */
  const SECCIONES = [
    ["local", "Mi local", "Cómo se llama tu local y qué sale en el ticket."],
    ["equipo", "Equipo", "Quiénes entran a la caja y qué puede hacer cada uno."],
    ["cobro", "Cobro", "Formas de pago, propinas, descuentos y precios sugeridos."],
    ["impresora", "Impresora y balanza", "El ticket, el papel y las etiquetas de la balanza."],
    ["pantallas", "Pantallas del local", "Los televisores y lo que muestra cada uno."],
    ["caja", "Esta caja", "Cómo se usa este computador y cómo entran los demás equipos."],
    ["respaldos", "Respaldos y actualizaciones", "Copias de seguridad, versión del programa y ayuda para soporte."],
  ];
  const nombreSeccion = (k) => (SECCIONES.find((s) => s[0] === k) || [])[1];

  // [id del ajuste, sección, título, palabras que lo encuentran]
  const INDICE = [
    ["l-nombre", "local", "Nombre del local", "comprobante cierre televisores marca"],
    ["l-rut", "local", "RUT del local", "rol tributario"],
    ["l-dir", "local", "Dirección del local", "calle domicilio"],
    ["l-mensaje", "local", "Mensaje al pie del ticket", "gracias comprobante texto despedida"],
    ["l-logo", "local", "Logo del ticket", "imagen dibujo marca proximamente"],
    ["l-inv", "local", "Llevar inventario", "stock bodega existencias productos"],
    ["e-lista", "equipo", "Personas que entran a la caja", "usuarios cajero cajera dueño agregar nueva persona"],
    ["e-lista", "equipo", "PIN de cada persona", "clave contraseña usuario"],
    ["e-lista", "equipo", "Color de cada persona", "avatar usuario"],
    ["e-lista", "equipo", "Permisos de cada persona", "vender anular reportes informes inventario stock configurar abrir cerrar caja retirar plata cobrar varios editar carta"],
    ["e-lista", "equipo", "Que solo venda", "permisos mínimos cajero"],
    ["e-lista", "equipo", "Ver reportes", "dueño ganancia ventas permiso"],
    ["e-lista", "equipo", "Sacar a alguien de la caja", "borrar eliminar usuario baja despedir"],
    ["c-medios", "cobro", "Formas de pago", "efectivo débito crédito transferencia tarjeta"],
    ["c-mixto", "cobro", "Pago en dos formas", "mixto parte y parte"],
    ["c-propina", "cobro", "Propinas", "propina sugerida tarjeta"],
    ["c-desc", "cobro", "Descuentos rápidos", "descuento porcentaje botones"],
    ["c-margen", "cobro", "Margen sugerido", "ganancia precio costo cuánto cobrar"],
    ["c-redondeo", "cobro", "Redondeo de precios", "múltiplo 10 50 100 sugerido"],
    ["i-siempre", "impresora", "Imprimir el comprobante después de cada venta", "ticket automática"],
    ["i-tipo", "impresora", "Tipo de impresora", "térmica tickets windows navegador"],
    ["i-impresora", "impresora", "Impresora", "lista actualizar pos-58 elegir"],
    ["i-papel", "impresora", "Ancho del papel", "rollo 58 80 mm"],
    ["i-prueba", "impresora", "Imprimir prueba", "probar ticket"],
    ["i-instalar", "impresora", "Instalar la impresora de tickets", "puerto usb no aparece driver"],
    ["b-usar", "impresora", "Balanza", "etiquetas pesar fiambre pan queso"],
    ["b-modo", "impresora", "Qué imprime la etiqueta de la balanza", "ticket plu peso precio"],
    ["b-codigo", "impresora", "Cómo está armado el código de la balanza", "prefijo posiciones divisor verificador"],
    ["b-prueba", "impresora", "Probar con una etiqueta", "escanear balanza código"],
    ["p-tvs", "pantallas", "Televisores del local", "tv pantalla vitrina carta agregar quitar nombre"],
    ["p-tvs", "pantallas", "Qué muestra cada televisor", "vitrina carta turnándose"],
    ["p-tvs", "pantallas", "TV parado o acostado", "vertical horizontal orientación girar"],
    ["p-tvs", "pantallas", "Tiempos de las pantallas", "segundos vitrina categoría combo"],
    ["p-tvs", "pantallas", "Decoración de Fiestas Patrias", "septiembre banderines"],
    ["p-tvs", "pantallas", "Modo suave del televisor", "menos movimiento lento"],
    ["p-tvs", "pantallas", "Ajustar al TV", "margen borde achicar agrandar"],
    ["p-tvs", "pantallas", "Dirección de cada televisor", "url enlace copiar p=1 p=2 tv=1 simple navegador viejo"],
    ["p-totem", "pantallas", "Tótem de autoservicio", "próximamente pedir solo cliente"],
    ["p-textos", "pantallas", "Textos de las pantallas", "frase combo título logo kicker"],
    ["p-cinta", "pantallas", "Horarios y avisos que corren abajo", "cinta frases wifi"],
    ["p-fuente", "pantallas", "Leer la carta desde otra dirección", "punto de venta url json conexión"],
    ["p-resp", "pantallas", "Respaldo de las pantallas", "descargar cargar datos de ejemplo"],
    ["k-tactil", "caja", "Modo táctil y teclado en pantalla", "pantalla táctil teclado numérico"],
    ["k-completa", "caja", "Pantalla completa", "f11 ventana"],
    ["k-barra", "caja", "Esconder la barra de arriba", "menú barra"],
    ["k-bloqueo", "caja", "Bloqueo automático", "minutos sin uso candado seguridad"],
    ["k-red", "caja", "Abrir la caja desde otro equipo", "tablet red wifi dirección ip"],
    ["k-pinred", "caja", "PIN de red", "tablet clave wifi acceso"],
    ["k-sesion", "caja", "Cambiar de usuario o salir de mi cuenta", "cerrar sesión salir quién está en la caja"],
    ["r-ahora", "respaldos", "Respaldar ahora", "copia seguridad backup"],
    ["r-afuera", "respaldos", "Copia de afuera", "nube onedrive google drive dropbox pendrive carpeta"],
    ["r-export", "respaldos", "Descargar para el contador", "exportar ventas excel detalle"],
    ["r-version", "respaldos", "Versión del programa", "actualizar buscar actualizaciones novedades"],
    ["r-canal", "respaldos", "Qué versiones recibir", "canal estable piloto nuevas antes"],
    ["r-diag", "respaldos", "Diagnóstico para soporte", "error falla registro whatsapp"],
    ["r-mudanza", "respaldos", "Mudanza desde otra caja", "traer ventas computador anterior"],
    ["r-restaurar", "respaldos", "Restaurar un respaldo", "recuperar volver atrás disco murió"],
    ["r-volver", "respaldos", "Volver a la versión anterior", "deshacer actualización"],
  ];

  /* Los ajustes que calzan con lo escrito: todas las palabras tienen que aparecer en el título, en
     las palabras clave o en el nombre de la sección; los que calzan en el título van primero. */
  function buscarAjustes(q, indice, max) {
    const toks = sinTildes(q).trim().split(/\s+/).filter(Boolean);
    if (!toks.length) return { toks, hits: [] };
    const lista = indice || INDICE;
    const hits = lista.filter(([, s, t, k]) => {
      const h = sinTildes(t + " " + k + " " + (nombreSeccion(s) || ""));
      return toks.every((w) => h.includes(w));
    });
    const punt = (h) => (toks.every((w) => sinTildes(h[2]).includes(w)) ? 0 : 1);
    const vistos = new Set();
    const unicos = hits.filter(([id, , t]) => {
      const key = id + "|" + t;
      if (vistos.has(key)) return false;
      vistos.add(key);
      return true;
    }).map((h, i) => [h, i]).sort((a, b) => punt(a[0]) - punt(b[0]) || a[1] - b[1]).map((x) => x[0]);
    return { toks, hits: unicos.slice(0, max || 8) };
  }

  /* El título con lo buscado marcado. Se marca sobre el TEXTO ya escapado, y la búsqueda ignora
     tildes: «impresion» marca «impresión». */
  const escapar = (t) => String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/"/g, "&quot;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;");
  function resaltar(texto, toks) {
    const original = String(texto);
    const plano = sinTildes(original);
    const marcas = new Array(original.length).fill(false);
    // sinTildes puede cambiar el largo en casos raros; si pasa, no se marca nada en vez de marcar mal.
    if (plano.length !== original.length) return escapar(original);
    (toks || []).filter((w) => w.length > 1).forEach((w) => {
      const i = plano.indexOf(w);
      if (i >= 0) for (let k = i; k < i + w.length; k++) marcas[k] = true;
    });
    let salida = "", abierta = false;
    for (let k = 0; k < original.length; k++) {
      if (marcas[k] && !abierta) { salida += "<mark>"; abierta = true; }
      if (!marcas[k] && abierta) { salida += "</mark>"; abierta = false; }
      salida += escapar(original[k]);
    }
    return salida + (abierta ? "</mark>" : "");
  }

  /* ---------------- el ticket ---------------- */
  function envuelve(txt, n) {
    const out = [];
    let l = "";
    String(txt == null ? "" : txt).split(/\s+/).filter(Boolean).forEach((w) => {
      while (w.length > n) {
        if (l) { out.push(l); l = ""; }
        out.push(w.slice(0, n));
        w = w.slice(n);
      }
      if ((l + " " + w).trim().length > n) { if (l) out.push(l); l = w; } else l = (l + " " + w).trim();
    });
    if (l) out.push(l);
    return out;
  }

  /* El comprobante de ejemplo tal como sale en papel de 58 mm (32 columnas) o de 80 mm (48). */
  function ticketTxt(local, ancho) {
    const W = ancho || 32;
    const centrar = (t) => " ".repeat(Math.max(0, Math.floor((W - t.length) / 2))) + t;
    const rep = "-".repeat(W);
    const lin = (a, b) => a + " ".repeat(Math.max(1, W - a.length - b.length)) + b;
    const ls = [];
    envuelve((local && local.nombre) || "Tu local", W).forEach((t) => ls.push(centrar(t)));
    if (local && local.rut) ls.push(centrar("RUT " + local.rut));
    envuelve((local && local.direccion) || "", W).forEach((t) => ls.push(centrar(t)));
    ls.push(rep, lin("Comprobante", "N° 0412"), rep, lin("1 x Latte", "$3.400"), lin("1 x Croissant", "$2.500"),
      rep, lin("TOTAL", "$5.900"), lin("Débito", "$5.900"), rep, centrar("NO ES BOLETA"), "");
    envuelve((local && local.mensaje) || "¡Gracias!", W).forEach((t) => ls.push(centrar(t)));
    return ls.join("\n");
  }

  /* ---------------- el RUT ---------------- */
  function rutDV(cuerpo) {
    let suma = 0, m = 2;
    for (let i = cuerpo.length - 1; i >= 0; i--) { suma += Number(cuerpo[i]) * m; m = m === 7 ? 2 : m + 1; }
    const r = 11 - (suma % 11);
    return r === 11 ? "0" : r === 10 ? "K" : String(r);
  }
  function rutFormato(t) {
    const l = String(t == null ? "" : t).replace(/[^0-9kK]/g, "").toUpperCase();
    if (l.length < 2) return null;
    const cuerpo = l.slice(0, -1), dv = l.slice(-1);
    if (!/^\d{1,8}$/.test(cuerpo) || rutDV(cuerpo) !== dv) return null;
    return conMiles(cuerpo) + "-" + dv;
  }

  /* ---------------- precios sugeridos ---------------- */
  function precioSugerido(costo, margen, paso) {
    costo = Math.max(0, Math.round(costo) || 0);
    if (!costo) return 0;
    const m = Math.min(Math.max(Math.round(margen) || 0, 0), 95);
    const p = paso || 1;
    return Math.ceil(costo * 100 / (100 - m) / p) * p;
  }
  function ejemploMargen(margen, redondeo) {
    const costo = 1300, p = precioSugerido(costo, margen, redondeo);
    return `Si un insumo te cuesta <b>${pesos(costo)}</b>, la caja te sugiere cobrar <b>${pesos(p)}</b>: te quedan `
      + `<b>${pesos(p - costo)}</b> de cada venta (${(p / costo).toFixed(1).replace(".", ",")} veces lo que te costó). `
      + "El IVA ya va incluido.";
  }

  /* ---------------- la balanza ---------------- */
  // Las posiciones se muestran tal como las guarda el servidor: desde cero y hasta sin incluir.
  function dibujoFormatoBalanza(f) {
    const bien = (r) => Array.isArray(r) && r.every((n) => Number.isInteger(n) && n >= 0)
      && r[0] < r[1] && r[1] <= 12;
    const faltan = [!/^2[0-9]*$/.test(f.prefijo || "") && "el prefijo (solo números, empieza con 2)",
      !bien(f.codigo) && "dónde está el número", !bien(f.valor) && "dónde está el valor"].filter(Boolean);
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
  const formatoBalanzaValido = (f) => {
    const t = dibujoFormatoBalanza(f);
    return !t.startsWith("Falta") && !t.split("\n")[1].includes("!");
  };

  /* ---------------- televisores ---------------- */
  const MODO_TXT = { turnar: "Las dos, turnándose", vitrina: "Solo la vitrina", menu: "Solo la carta" };
  const ORIENT_TXT = { vertical: "parado", horizontal: "acostado" };
  /* La dirección de un televisor. Las de siempre (?p=1, ?p=2, ?tv=1 y /pantallas/simple) más su número
     (&t=), que sirve para que la caja sepa que ese televisor está conectado y le entregue lo suyo. */
  function urlTv(tv, base) {
    const b = String(base || "").replace(/\/+$/, "");
    if (tv.simple) return b + "/pantallas/simple?t=" + tv.id;
    return b + "/pantallas?" + (tv.modo === "vitrina" ? "p=1" : tv.modo === "menu" ? "p=2" : "tv=1") + "&t=" + tv.id;
  }
  function textoVisto(segundos) {
    if (segundos == null) return { activo: false, texto: "Sin conectar todavía" };
    const m = Math.floor(segundos / 60);
    const cuando = m < 1 ? "hace un momento" : m < 60 ? "hace " + m + " min"
      : m < 1440 ? "hace " + Math.floor(m / 60) + " h" : "hace más de un día";
    // Los televisores preguntan por la caja cada 5 minutos; más de 12 sin noticias es raro.
    return { activo: segundos <= 12 * 60, texto: (segundos <= 12 * 60 ? "Conectado" : "Sin señal") + " · visto " + cuando };
  }

  /* ---------------- respaldos ---------------- */
  const DIAS_L = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  const MESES_L = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre"];
  function partesFecha(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? { a: +m[1], m: +m[2], d: +m[3] } : null;
  }
  function etiquetaRespaldo(copia) {
    const p = partesFecha(copia.fecha);
    if (!p) return copia.archivo;
    const dia = DIAS_L[new Date(Date.UTC(p.a, p.m - 1, p.d)).getUTCDay()];
    return (copia.tipo === "antes" ? "Antes de restaurar · " : "") + dia + " " + p.d + " de " + MESES_L[p.m - 1] + " · " + copia.hora;
  }
  /* Buscar un respaldo por «lunes», «2 de octubre», «09-27», «2026-09-27» o parte del nombre. */
  function respaldoCalza(copia, q) {
    const toks = sinTildes(q).trim().split(/\s+/).filter(Boolean);
    if (!toks.length) return true;
    const p = partesFecha(copia.fecha) || { d: 0, m: 0, a: 0 };
    const pad = (n) => String(n).padStart(2, "0");
    const heno = sinTildes(etiquetaRespaldo(copia) + " " + copia.archivo + " " + copia.fecha + " "
      + pad(p.m) + "-" + pad(p.d) + " " + p.d + "-" + p.m + " " + p.d + "/" + p.m + " " + pad(p.d) + "/" + pad(p.m)
      + (copia.tipo === "antes" ? " antes de restaurar" : ""));
    return toks.every((w) => heno.includes(w));
  }

  /* ---------------- impresoras ---------------- */
  /* Lo que se muestra al actualizar la lista de impresoras de Windows. La impresora guardada se
     conserva aunque no aparezca: un fallo de Windows no puede borrar la selección. */
  function resumenImpresoras(r, elegida) {
    const lista = (r && r.impresoras) || [];
    const opciones = [{ valor: "", texto: "Elige una impresora" }];
    if (elegida && !lista.some((p) => p.nombre === elegida)) {
      opciones.push({ valor: elegida, texto: elegida + " (no disponible)" });
    }
    lista.forEach((p) => opciones.push({ valor: p.nombre, texto: p.nombre + (p.disponible ? "" : " (requiere diálogo)"),
      deshabilitada: !p.disponible }));
    let estado;
    if (!r || r.disponible === false) estado = (r && r.detalle) || "La impresión directa requiere Windows.";
    else if (!lista.length) estado = "No hay impresoras instaladas. Instálala en Windows y actualiza esta lista.";
    else if (elegida && !lista.some((p) => p.nombre === elegida && p.disponible)) {
      estado = "La impresora guardada no está disponible para impresión directa. Elige otra o usa el navegador.";
    } else estado = "Lista actualizada. Imprime una prueba para revisar el papel.";
    return { opciones, estado, hayPapel: lista.some((p) => p.disponible) };
  }
  /* FILE/PDF no son conexiones de una impresora enchufada. USB va primero para que el puerto
     habitual de una ticketera sea el sugerido. */
  function puertosUtiles(puertos) {
    return (puertos || []).filter((p) => !/^(FILE:|PORTPROMPT:|NUL:|SHRFAX:|Microsoft\.Office\.OneNote)/i.test(p.nombre))
      .sort((a, b) => Number(/^USB/i.test(b.nombre)) - Number(/^USB/i.test(a.nombre)));
  }
  /* El tipo de impresora cuando el dueño no eligió uno: se deduce del nombre y del puerto. */
  function deducirTipo(nombre, puerto) {
    if (!nombre) return "navegador";
    return /sewoo|slk[- ]?ts|t[eé]rmica|thermal|receipt|tickets?|esc[ /-]?pos|\bpos\b|epson.*tm[- ]|usb\d+/i
      .test(nombre + " " + (puerto || "")) ? "termica" : "windows";
  }

  /* ---------------- los permisos de una persona ---------------- */
  const GRUPOS_PERMISOS = [
    ["Vender", ["vender", "anular", "anular_pasado", "cobrar_varios"]],
    ["La caja", ["turno_abrir", "turno_cerrar", "turno_cerrar_ajeno", "caja_retirar"]],
    ["Mirar", ["ver_dia", "ver_reportes", "ver_informes"]],
    ["Carta e inventario", ["editar_carta", "inventario", "inventario_ajustar"]],
    ["Administrar", ["usuarios", "config"]],
  ];
  /* Los permisos del catálogo del servidor, ordenados en grupos y filtrados por lo que se busca.
     Lo que el servidor agregue y no esté en un grupo cae en «Otros»: nunca se pierde un permiso. */
  function permisosAgrupados(catalogo, q) {
    const t = sinTildes(q).trim();
    const nombre = {};
    (catalogo || []).forEach((p) => { nombre[p.clave] = p.nombre; });
    const usados = new Set();
    const grupos = GRUPOS_PERMISOS.map(([g, claves]) => [g, claves.filter((k) => nombre[k])]);
    grupos.forEach(([, cs]) => cs.forEach((k) => usados.add(k)));
    const otros = (catalogo || []).map((p) => p.clave).filter((k) => !usados.has(k));
    if (otros.length) grupos.push(["Otros", otros]);
    return grupos.map(([g, cs]) => [g, cs.filter((k) => !t || sinTildes(nombre[k] + " " + g).includes(t))
      .map((k) => ({ clave: k, nombre: nombre[k] }))]).filter(([, cs]) => cs.length);
  }
  const SOLO_VENDER = ["vender", "turno_abrir", "turno_cerrar"];

  /* ---------------- frases ---------------- */
  const minutosTxt = (m) => m + " minuto" + (m === 1 ? "" : "s");
  /* Cuántas ventas se pierden al restaurar, dicho para la casilla de confirmación. */
  function fraseConfirmarRestaurar(perderia) {
    return perderia > 0
      ? `Entiendo que esas ${conMiles(perderia)} venta${perderia === 1 ? "" : "s"} no van a estar en la caja.`
      : "Entiendo que la caja vuelve a como estaba en ese respaldo.";
  }

  /* Un porcentaje escrito a mano → entero entre 1 y 100, o null. */
  function porcentajeValido(v) {
    const n = Number(String(v == null ? "" : v).replace(/\D/g, ""));
    return Number.isInteger(n) && n >= 1 && n <= 100 ? n : null;
  }
  /* Agrega o quita un valor de una lista de porcentajes, ordenada y sin repetir. */
  function alternarPorcentaje(lista, v, max) {
    const arr = (lista || []).slice();
    const i = arr.indexOf(v);
    if (i >= 0) arr.splice(i, 1);
    else if (arr.length < (max || 6)) { arr.push(v); arr.sort((a, b) => a - b); }
    return arr;
  }

  const modulo = {
    SECCIONES, INDICE, MODO_TXT, ORIENT_TXT, GRUPOS_PERMISOS, SOLO_VENDER, DIAS_L, MESES_L,
    sinTildes, conMiles, pesos, escapar, nombreSeccion, buscarAjustes, resaltar,
    envuelve, ticketTxt, rutDV, rutFormato, precioSugerido, ejemploMargen,
    dibujoFormatoBalanza, formatoBalanzaValido,
    urlTv, textoVisto, etiquetaRespaldo, respaldoCalza, resumenImpresoras, puertosUtiles, deducirTipo,
    permisosAgrupados, minutosTxt, fraseConfirmarRestaurar, porcentajeValido, alternarPorcentaje,
  };
  raiz.ConfigLogica = modulo;
  if (typeof module !== "undefined" && module.exports) module.exports = modulo;
})(typeof window !== "undefined" ? window : globalThis);
