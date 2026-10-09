/* La lógica de la pestaña Ventas que no necesita pantalla: buscar sin tildes ni mayúsculas,
   comparar con el período anterior, armar la geometría de los gráficos y escribir las frases
   («se vende más a las…»). Está aparte de ventas.js para poder probarla con Node
   (apps/pos/tests/ventas_logica.cjs). No toca el DOM ni pide nada al servidor.

   Las fechas y horas que manda el servidor ya vienen en hora del local («2026-10-08T14:22:00-03:00»):
   acá se leen del TEXTO y no con `new Date(...)`, así el día que se muestra es el del local
   aunque el navegador esté en otra zona horaria. */
(function (raiz) {
  "use strict";

  const DIAS_C = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];       // getDay(): 0 = domingo
  const DIAS_L = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  const MESES_C = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const MESES_L = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre"];
  // El servidor cuenta los días desde el lunes (0 = lunes), como Python.
  const DIAS_SEM = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
  const DIAS_SEM_C = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];

  const NOMBRE_MEDIO = { efectivo: "Efectivo", debito: "Débito", credito: "Crédito",
    transferencia: "Transferencia", mixto: "Pago mixto" };
  const COLOR_MEDIO = { efectivo: "#4E7C5B", debito: "#3E6E8E", credito: "#C9552B",
    transferencia: "#B5892E", mixto: "#8C4A6B" };

  const sinTildes = (t) => String(t == null ? "" : t).normalize("NFD")
    .replace(/[̀-ͯ]/g, "").toLowerCase();
  const soloDigitos = (t) => String(t == null ? "" : t).replace(/\D/g, "");
  const clp = (n) => "$" + (Number(n) || 0).toLocaleString("es-CL");
  const MENOS = "−";
  const conSigno = (n) => (n < 0 ? MENOS : "+") + clp(Math.abs(n));

  /* ---------- fechas del local, leídas del texto ---------- */
  function partes(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(iso || ""));
    if (!m) return null;
    return { a: +m[1], m: +m[2], d: +m[3], hh: m[4] == null ? null : +m[4], mm: m[5] == null ? null : +m[5] };
  }
  const diaSemana = (p) => new Date(Date.UTC(p.a, p.m - 1, p.d)).getUTCDay();
  const pad = (n) => String(n).padStart(2, "0");
  const hhmm = (iso) => { const p = partes(iso); return p && p.hh != null ? pad(p.hh) + ":" + pad(p.mm) : ""; };
  const fechaCorta = (iso) => { const p = partes(iso); return p ? `${DIAS_C[diaSemana(p)]} ${p.d} ${MESES_C[p.m - 1]}` : ""; };
  const fechaLarga = (iso) => { const p = partes(iso); return p ? `${DIAS_L[diaSemana(p)]} ${p.d} de ${MESES_L[p.m - 1]}` : ""; };
  const diaMes = (iso) => { const p = partes(iso); return p ? `${p.d}/${p.m}` : ""; };
  const claveDia = (iso) => String(iso || "").slice(0, 10);

  /* minutos entre dos textos del local (o hasta `ahoraMin` si todavía no terminó) */
  function minutosEntre(desdeIso, hastaIso, ahoraMs) {
    const a = Date.parse(desdeIso);
    const b = hastaIso ? Date.parse(hastaIso) : ahoraMs;
    if (isNaN(a) || isNaN(b)) return 0;
    return Math.max(0, Math.round((b - a) / 60000));
  }
  function duracion(min) {
    min = Math.max(0, Math.round(min));
    const h = Math.floor(min / 60), m = min % 60;
    return h ? h + " h" + (m ? " " + m + " min" : "") : m + " min";
  }
  /* «abierto hoy 08:30» / «abierto lun 5 oct 08:30» */
  function cuandoAbrio(iso, hoyClave) {
    return claveDia(iso) === hoyClave ? `hoy ${hhmm(iso)}` : `${fechaCorta(iso)} ${hhmm(iso)}`;
  }

  /* ---------- el arqueo ---------- */
  const claseDif = (d) => (d === 0 ? "ok" : d > 0 ? "mas" : "menos");
  const textoDif = (d) => (d === 0 ? "Cuadra exacto" : d > 0 ? "Sobran " + clp(d) : "Faltan " + clp(-d));
  const textoDifCorto = (d) => (d === 0 ? "Cuadra" : (d > 0 ? "Sobra " : "Falta ") + clp(Math.abs(d)));

  /* ---------- buscadores (lupa, ×, sin tildes ni mayúsculas) ---------- */
  function ventaCalza(v, texto) {
    const q = sinTildes(texto).trim();
    if (!q) return true;
    const qd = soloDigitos(q);
    if ((v.productos || []).some((p) => sinTildes(p.nombre).includes(q))) return true;
    if (v.anulada && "anulada".includes(q)) return true;
    const medios = [v.medio_pago, ...(v.pagos || []).map((p) => p.medio)]
      .map((m) => sinTildes(NOMBRE_MEDIO[m] || m));
    if (medios.some((m) => m.includes(q))) return true;
    return !!qd && (String(v.numero).includes(qd) || String(v.cobrado).includes(qd));
  }

  function textoDeTurno(t) {
    const dif = t.diferencia;
    const estado = t.abierto ? "en curso abierto" : dif == null ? "" : dif === 0 ? "cuadra cuadro"
      : dif > 0 ? "sobra sobro con diferencia" : "falta falto con diferencia";
    return [t.abrio, fechaCorta(t.abierto_at), fechaLarga(t.abierto_at), diaMes(t.abierto_at), estado].join(" ");
  }
  function turnoCalza(t, texto, soloConDiferencia) {
    if (soloConDiferencia && !(t.diferencia != null && t.diferencia !== 0)) return false;
    const q = sinTildes(texto).trim();
    return !q || sinTildes(textoDeTurno(t)).includes(q);
  }

  function productoCalza(p, texto) {
    const q = sinTildes(texto).trim();
    return !q || sinTildes(p.nombre).includes(q) || sinTildes(p.categoria).includes(q);
  }

  /* La lista de «Productos» de Reportes. modo: cant | plata | sin */
  function listaProductos(datos, modo, texto) {
    let filas;
    if (modo === "sin") {
      // Primero los que hace más que no se venden; los que nunca se vendieron, antes que todos.
      filas = datos.sin_ventas.slice().sort((a, b) => {
        if (!a.ultima_venta && !b.ultima_venta) return a.nombre.localeCompare(b.nombre, "es");
        if (!a.ultima_venta) return -1;
        if (!b.ultima_venta) return 1;
        return a.ultima_venta < b.ultima_venta ? -1 : a.ultima_venta > b.ultima_venta ? 1 : 0;
      });
    } else {
      const k = modo === "cant" ? "cantidad" : "total";
      filas = datos.vendidos.slice().sort((a, b) => b[k] - a[k] || a.nombre.localeCompare(b.nombre, "es"));
    }
    const todas = filas.length;
    const visibles = filas.filter((p) => productoCalza(p, texto));
    return { filas: visibles, todas, vendidos: datos.vendidos.length, sin: datos.sin_ventas.length };
  }

  /* ---------- comparación con el período anterior ---------- */
  function delta(actual, previo, hayPrevio) {
    if (!hayPrevio || previo == null) return { clase: "na", texto: "sin comparar" };
    if (!previo) return actual ? { clase: "na", texto: "sin comparar" } : { clase: "eq", texto: "= igual" };
    const r = Math.round((actual - previo) / previo * 100);
    if (r === 0) return { clase: "eq", texto: "= igual" };
    return r > 0 ? { clase: "up", texto: "▲ +" + r + "%" } : { clase: "down", texto: "▼ " + MENOS + Math.abs(r) + "%" };
  }

  /* «Del 2 al 8 de octubre» / «jueves 8 de octubre» */
  function rangoTexto(desdeIso, hastaIso) {
    const a = partes(desdeIso), b = partes(hastaIso);
    if (!a || !b) return "";
    if (desdeIso === hastaIso) return fechaLarga(desdeIso);
    if (a.m === b.m && a.a === b.a) return `Del ${a.d} al ${b.d} de ${MESES_L[b.m - 1]}`;
    return `Del ${a.d} de ${MESES_C[a.m - 1]} al ${b.d} de ${MESES_C[b.m - 1]}`;
  }

  /* ---------- gráficos ---------- */
  /* Un eje «bonito»: 4 o 5 divisiones de 1, 2, 2,5, 5 o 10 por potencia de diez. */
  function escalaBonita(max) {
    if (!(max > 0)) return { paso: 1, n: 1 };
    const crudo = max / 4, mag = Math.pow(10, Math.floor(Math.log10(crudo)));
    const paso = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= crudo);
    return { paso, n: Math.ceil(max / paso) };
  }
  const decimal = (x) => String(x).replace(".", ",");
  function ejeY(n) {
    if (n === 0) return "$0";
    if (n >= 1e6) return "$" + decimal(+(n / 1e6).toFixed(2)) + " M";
    return "$" + decimal(+(n / 1000).toFixed(1)) + " mil";
  }

  /* La geometría del gráfico de barras: nada de dibujar acá, solo dónde va cada cosa.
     items: [{etq, total, fin}] · ancho/alto en píxeles · sel: la barra marcada (o null = la mayor). */
  function geometriaBarras(items, ancho, alto, sel, conPromedio) {
    const ml = 58, mr = 10, mt = 14, mb = 30;
    const W = Math.max(280, ancho), H = alto, pw = W - ml - mr, ph = H - mt - mb;
    const max = Math.max(1, ...items.map((x) => x.total));
    const { paso, n } = escalaBonita(max), tope = paso * n;
    let marcada = sel;
    if (marcada == null || marcada >= items.length || marcada < 0) {
      marcada = 0;
      items.forEach((x, i) => { if (x.total > items[marcada].total) marcada = i; });
    }
    const bw = pw / (items.length || 1);
    const w = Math.max(2, Math.min(46, bw * 0.7));
    const cadaX = Math.max(1, Math.ceil(36 / bw));
    const lineas = [];
    for (let i = 0; i <= n; i++) lineas.push({ y: mt + ph - ph * i * paso / tope, etq: ejeY(i * paso) });
    const barras = items.map((x, i) => {
      const cx = ml + bw * i + bw / 2, h = ph * x.total / tope;
      return { i, cx, x: cx - w / 2, y: mt + ph - h, w, h: Math.max(0, h), fin: !!x.fin, sel: i === marcada,
        etq: x.etq, verEtq: i % cadaX === 0 || i === marcada, zonaX: ml + bw * i, zonaW: bw };
    });
    let promedio = null;
    if (conPromedio && items.length) {
      const prom = items.reduce((s, x) => s + x.total, 0) / items.length;
      promedio = { y: mt + ph - ph * prom / tope, texto: "promedio " + ejeY(Math.round(prom / 1000) * 1000) };
    }
    return { W, H, ml, mr, mt, ph, lineas, barras, promedio, sel: marcada };
  }

  /* La dona de formas de pago: cada arco con su largo y desde dónde parte. */
  function arcosDona(medios, radio) {
    const L = 2 * Math.PI * radio;
    const total = medios.reduce((s, m) => s + m.total, 0) || 1;
    let acum = 0;
    return medios.filter((m) => m.total > 0).map((m) => {
      const largo = L * m.total / total, arco = { medio: m.medio, largo, resto: L - largo, desde: -acum };
      acum += largo;
      return arco;
    });
  }
  const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

  /* ---------- el mapa de calor ---------- */
  function horasDelCalor(c) {
    const hs = [];
    for (let h = c.hora_ini; h <= c.hora_fin; h++) hs.push(h);
    return hs;
  }
  function celdaMejor(c) {
    let mejor = { d: 5, h: c.hora_ini, v: -1 };
    for (let d = 0; d < 7; d++) for (const h of horasDelCalor(c)) {
      if (c.celdas[d][h] > mejor.v) mejor = { d, h, v: c.celdas[d][h] };
    }
    return mejor;
  }
  /* «Se vende más a las 9 h y a las 17 h. El día más fuerte es el sábado.» */
  function fraseCalor(c) {
    const hs = horasDelCalor(c);
    const porHora = hs.map((h) => ({ h, v: c.todos[h] })).sort((a, b) => b.v - a.v);
    if (!porHora.length || !(porHora[0].v > 0)) return "Todavía no hay ventas suficientes para ver un patrón.";
    const h1 = porHora[0].h;
    const otro = porHora.find((x) => Math.abs(x.h - h1) > 2 && x.v > 0) || porHora.find((x) => x.h !== h1 && x.v > 0);
    const dias = [0, 1, 2, 3, 4, 5, 6].map((d) => ({ d, v: hs.reduce((s, h) => s + c.celdas[d][h], 0) }))
      .sort((a, b) => b.v - a.v);
    const [a, b] = otro ? [h1, otro.h].sort((x, y) => x - y) : [h1, null];
    const horas = b == null ? `a las <b>${a} h</b>` : `a las <b>${a} h</b> y a las <b>${b} h</b>`;
    return `Se vende más ${horas}. El día más fuerte es el <b>${DIAS_SEM[dias[0].d]}</b>.`;
  }
  /* La frase de la celda marcada. d = 7 es la fila «todos». */
  function fraseCelda(c, sel) {
    const v = sel.d === 7 ? c.todos[sel.h] : c.celdas[sel.d][sel.h];
    const cuando = sel.d === 7 ? "Todos los días" : "Un " + DIAS_SEM[sel.d];
    return `${cuando} entre las <b>${sel.h}</b> y las <b>${sel.h + 1} h</b>: en promedio <b>${clp(v)}</b>${sel.d === 7 ? " por día" : " ese día"}.`;
  }
  /* 0..100 de lo oscura que va una celda */
  function intensidad(v, max) { return v <= 0 || !(max > 0) ? 0 : Math.round(10 + 90 * v / max); }

  /* ---------- el teclado numérico de los diálogos ---------- */
  const conPuntos = (n) => (n === "" || n == null ? "" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."));
  function teclear(valor, tecla) {
    let d = soloDigitos(valor);
    if (tecla === "x") d = d.slice(0, -1);
    else if (tecla === "c") d = "";
    else d = (d + tecla).replace(/^0+/, "").slice(0, 9);
    return conPuntos(d);
  }

  const modulo = {
    DIAS_SEM, DIAS_SEM_C, NOMBRE_MEDIO, COLOR_MEDIO, MENOS,
    sinTildes, soloDigitos, clp, conSigno, partes, hhmm, fechaCorta, fechaLarga, diaMes, claveDia,
    minutosEntre, duracion, cuandoAbrio, claseDif, textoDif, textoDifCorto,
    ventaCalza, textoDeTurno, turnoCalza, productoCalza, listaProductos,
    delta, rangoTexto, escalaBonita, ejeY, geometriaBarras, arcosDona, pct,
    horasDelCalor, celdaMejor, fraseCalor, fraseCelda, intensidad, conPuntos, teclear,
  };
  raiz.VentasLogica = modulo;
  if (typeof module !== "undefined" && module.exports) module.exports = modulo;
})(typeof window !== "undefined" ? window : globalThis);
