/* ==========================================================
   La pestaña «Config»: un menú de siete secciones a la izquierda y el contenido a la derecha, un
   buscador de ajustes que salta al ajuste y lo resalta, y guardado automático («Guardado ✓»).
   Lo peligroso (restaurar un respaldo, volver de versión, sacar a alguien, reiniciar las pantallas)
   va aparte y pide confirmación.

   Reemplaza a «Ayuda → Ajustes», al diálogo «Equipo» y a «Las pantallas del local». No se pierde
   ninguna opción: cada una tiene su lugar en el menú (ver el resumen en docs/CONTRATO.md).

   EL PIN. Config pide el PIN de alguien con el permiso «Cambiar los ajustes» y lo verifica el
   SERVIDOR (apps/pos/api/config.py), igual que Reportes: el acceso vale 5 minutos y se renueva con
   cada uso. Sin uso, esta pantalla vuelve sola al PIN, y el servidor también cierra: los
   endpoints que cambian algo exigen ese acceso, no esta pantalla. Las guías se leen sin PIN.

   La lógica sin pantalla (buscar sin tildes, vista previa del ticket, direcciones de los
   televisores, filtrar respaldos…) está en config-logica.js, que se prueba con Node.

   Cuidado con los atributos data-*: app.js tiene UN solo manejador de clics para toda la página y
   reacciona a data-copiar, data-margen, data-lugar, data-guia, data-rol… Los de acá llevan todos el
   prefijo «c» (data-c-…) para no cruzarse con ninguno.
   ========================================================== */
(function () {
  "use strict";
  const L = window.ConfigLogica;
  const vista = document.getElementById("vistaConfig");
  if (!vista) return;
  const capa = document.getElementById("capaConfig");
  const dlgEl = document.getElementById("dialogoConfig");
  const $c = (s, r) => (r || vista).querySelector(s);
  const $$c = (s, r) => Array.from((r || vista).querySelectorAll(s));
  const sinTildes = L.sinTildes;
  const conMiles = L.conMiles;
  const pesos = L.pesos;
  const MIN_SIN_USO = 5;

  /* ---------------- íconos ---------------- */
  const sv = (p) => `<svg viewBox="0 0 24 24" aria-hidden="true">${p}</svg>`;
  const IC = {
    local: sv('<path d="M4 9l1.5-5h13L20 9M4 9v10h16V9M4 9h16M9 19v-5h6v5"/>'),
    equipo: sv('<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c0-3.2 2.4-5.2 5.5-5.2s5.5 2 5.5 5.2M16 5.2a3 3 0 0 1 0 5.6M17.5 14.2c2 .6 3.2 2.3 3.2 4.8"/>'),
    cobro: sv('<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/><path d="M6.5 9.5h.01M17.5 14.5h.01"/>'),
    impresora: sv('<path d="M7 9V4h10v5M7 17H5a1 1 0 0 1-1-1v-5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5a1 1 0 0 1-1 1h-2"/><rect x="7" y="14" width="10" height="6" rx="1"/>'),
    pantallas: sv('<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/>'),
    caja: sv('<rect x="4" y="3" width="16" height="9" rx="1.5"/><path d="M6 12h12l2 8H4zM9 16h6"/>'),
    respaldos: sv('<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2.2 2.2L15.5 10"/>'),
    guias: sv('<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.2 1-1.2 1.9M12 17v.01"/>'),
    lupa: '<svg class="i-lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 21 21"/></svg>',
    cierra: sv('<path d="M6 6l12 12M18 6 6 18"/>'),
    llave: sv('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
    borrar: sv('<path d="M9 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6-7z"/><path d="M12.5 9.5l5 5M17.5 9.5l-5 5"/>'),
    sale: sv('<path d="M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h4M14 8l4 4-4 4M18 12H9"/>'),
    copia: sv('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>'),
    mas: sv('<path d="M12 5v14M5 12h14"/>'),
    alerta: sv('<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.01"/>'),
    baja: sv('<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>'),
    totem: sv('<rect x="7" y="2.5" width="10" height="16" rx="2"/><path d="M12 15.5h.01M9 21.5h6M12 18.5v3"/>'),
  };

  /* ---------------- el estado de la pantalla ---------------- */
  const S = {
    user: null, pin: "", msg: null, enviando: false,
    ultimo: Date.now(), latido: Date.now(), inactivoMs: MIN_SIN_USO * 60 * 1000,
    sec: "local", q: "", flash: null, pendiente: null, abiertos: new Set(), rq: "", eq: "",
    dlg: null, req: 0, ultimaApertura: 0, guiasSolas: false,
    D: {},            // lo que se trajo del servidor, por sección
    bal: null,        // el borrador del formato de la balanza
    cargada: {},      // secciones ya traídas alguna vez
    ticketAncho: null,
  };
  const SECCIONES = L.SECCIONES.map(([k, t, d]) => [k, t, d, IC[k]]);
  const NAV_EXTRA = ["guias", "Guías y ayuda", "Cómo se hace cada cosa, paso a paso. Se pueden leer sin PIN.", IC.guias];
  const TODAS = SECCIONES.concat([NAV_EXTRA]);
  const seccionDe = (k) => TODAS.find((s) => s[0] === k);
  const visible = () => vista.classList.contains("is-on");

  /* ---------------- ayudas para armar pantallas ---------------- */
  const aj = (id, tit, ayuda, ctl, o) => {
    o = o || {};
    return `<div class="cfg-aj${o.cls ? " " + o.cls : ""}" data-aj="${id}">
      <div class="cfg-aj__t"><b>${tit}${o.pronto ? '<span class="cfg-pronto">Próximamente</span>' : ""}</b>${ayuda ? `<small>${ayuda}</small>` : ""}</div>
      <div class="cfg-aj__c">${ctl}</div></div>`;
  };
  const sw = (path, on, nombre, off) => `<button type="button" class="cfg-sw${on ? " is-on" : ""}" role="switch" aria-checked="${!!on}" data-c-tog="${path}" aria-label="${esc(nombre || "")}"${off ? " disabled" : ""}><i></i></button>`;
  const ajSw = (id, tit, ayuda, path, on, o) => aj(id, tit, ayuda, sw(path, on, tit), Object.assign({ cls: "cfg-aj--sw" }, o || {}));
  const seg = (clave, ops, actual, cls) => `<div class="i-seg cfg-seg ${cls || ""}" role="group">${ops.map(([v, t]) =>
    `<button type="button" class="i-seg__b${String(v) === String(actual) ? " is-on" : ""}" data-c-seg="${clave}" data-v="${v}">${t}</button>`).join("")}</div>`;
  const radios = (clave, ops, actual) => `<div class="cfg-radios">${ops.map(([v, t, h]) =>
    `<button type="button" class="cfg-radio${String(v) === String(actual) ? " is-on" : ""}" data-c-seg="${clave}" data-v="${v}" role="radio" aria-checked="${String(v) === String(actual)}"><i></i><span>${t}${h ? `<small>${h}</small>` : ""}</span></button>`).join("")}</div>`;
  const campo = (clave, val, o) => {
    o = o || {};
    return `<input class="cfg-in" data-c-in="${clave}" value="${esc(val)}"${o.max ? ` maxlength="${o.max}"` : ""}${o.ph ? ` placeholder="${esc(o.ph)}"` : ""}${o.tipo ? ` inputmode="${o.tipo}"` : ""}${o.id ? ` id="${o.id}"` : ""} autocomplete="off" spellcheck="false">${o.err ? `<small class="cfg-err" data-c-err="${o.err}"></small>` : ""}`;
  };
  const det = (id, titulo, sub, cuerpo) => `<details class="cfg-det" data-c-det="${id}"${S.abiertos.has(id) ? " open" : ""}><summary>${titulo}${sub ? ` <small>${sub}</small>` : ""}</summary><div class="cfg-det__cuerpo">${cuerpo}</div></details>`;
  const buscadorHTML = (id, ph, val) => `<div class="i-busca">${IC.lupa}<input id="${id}" type="search" placeholder="${ph}" autocomplete="off" spellcheck="false" value="${esc(val || "")}"><button type="button" class="i-x" data-c-lq="${id}" aria-label="Limpiar">${IC.cierra}</button></div>`;
  const avatar = (u) => `<span class="av" style="--c:${/^#[0-9a-f]{3,8}$/i.test(u.color || "") ? u.color : "#8A5A34"}">${esc(String(u.nombre || "?").charAt(0).toUpperCase())}</span>`;
  const el = (id) => document.getElementById(id);

  /* ---------------- "Guardado ✓" ---------------- */
  let tG, tGs, dlgOk = false;
  function guardado() {
    dlgOk = true;
    const e = $c("#cfgGuardado"); if (e) e.classList.add("is-on");
    const d = el("cfgDlgOk"); if (d) d.textContent = "Guardado ✓";
    clearTimeout(tG);
    tG = setTimeout(() => {
      dlgOk = false;
      const e2 = $c("#cfgGuardado"); if (e2) e2.classList.remove("is-on");
      const d2 = el("cfgDlgOk"); if (d2) d2.textContent = "";
    }, 2400);
  }
  // Lo que se escribe a mano no se guarda con cada tecla: espera a que la persona termine.
  const esperas = {};
  function despues(clave, fn, ms) { clearTimeout(esperas[clave]); esperas[clave] = setTimeout(fn, ms || 650); }

  /* ---------------- hablar con el servidor ---------------- */
  /* Un 401 «Config …» no es una sesión perdida (para eso está app.js): es volver al PIN. */
  async function capi(ruta, opciones) {
    try {
      return await api(ruta, opciones);
    } catch (e) {
      if (e.status === 401 && /^Config /.test(e.message) && S.user) salir(e.message);
      throw e;
    }
  }
  const json = (o) => JSON.stringify(o);
  async function refrescarAjustes() {
    AJUSTES = { ...AJUSTES, ...(await capi("/ajustes")) };
    return AJUSTES;
  }
  async function guardarAjustes(cambios, aviso) {
    const antes = usarInventario();
    try {
      const r = await capi("/ajustes", { method: "PUT", body: json(cambios) });
      AJUSTES = { ...AJUSTES, ...r };
      if (antes !== usarInventario()) aplicarInventario();
      if ("bloqueo_minutos" in cambios) reiniciarInactividad();
      guardado();
      if (aviso) avisar(aviso);
      return r;
    } catch (e) {
      avisar(e.message, true);
      if (S.user && visible()) pintarSeccion();
      return null;
    }
  }

  /* ==========================================================
     EL PIN
     ========================================================== */
  function salir(motivo) {
    const estaba = !!S.user;
    S.user = null; S.pin = ""; S.msg = null; S.q = ""; S.D = {}; S.cargada = {}; S.guiasSolas = false;
    S.req++;
    if (estaba) api("/config/salir", { method: "POST", espera: 4000 }).catch(() => { });
    if (S.dlg) cerrarDlg();
    if (visible()) render();
    if (motivo && estaba) avisar(motivo === "inactividad"
      ? "Config se cerró sola tras 5 minutos sin uso. Para volver, pide el PIN de nuevo." : motivo, motivo !== "inactividad" && motivo !== "cerrar");
  }
  setInterval(() => {
    if (!S.user) return;
    const ahora = Date.now();
    if (ahora - S.ultimo > S.inactivoMs) return salir("inactividad");
    // Mientras se usa, el servidor se entera de que sigue en uso (renueva sus 5 minutos).
    if (visible() && ahora - S.ultimo < 4 * 60 * 1000 && ahora - S.latido > 90 * 1000) {
      S.latido = ahora;
      api("/config/estado", { espera: 5000 }).then((r) => {
        if (r && !r.activo && S.user) salir("Config se cerró. Pide el PIN de nuevo.");
      }).catch(() => { });
    }
  }, 5000);
  ["pointerdown", "keydown", "wheel", "input"].forEach((ev) => {
    vista.addEventListener(ev, () => { S.ultimo = Date.now(); }, true);
    dlgEl.addEventListener(ev, () => { S.ultimo = Date.now(); }, true);
  });

  async function probarPin() {
    if (S.enviando) return;
    if (S.pin.length < 4) { S.msg = { t: "corto", texto: "El PIN tiene 4 números o más." }; return repintarPuntos(); }
    const pin = S.pin;
    S.enviando = true;
    try {
      const r = await api("/config/entrar", { method: "POST", body: json({ pin }), espera: 15000 });
      S.enviando = false;
      entrarComo(r.usuario);
    } catch (e) {
      S.enviando = false;
      S.pin = "";
      if (e.status === 401 && /Hay que entrar/.test(e.message)) return;       // la sesión se perdió: app.js
      S.msg = e.status === 403 ? { t: "sin", texto: e.message } : { t: "mal", texto: e.message };
      if (!visible()) return;
      render();
      const caja = $c("#cfgPinCaja");
      if (caja && S.msg.t === "mal") { caja.classList.add("pin-mal"); setTimeout(() => caja.classList.remove("pin-mal"), 450); }
    }
  }
  function entrarComo(usuario) {
    S.user = usuario; S.pin = ""; S.msg = null; S.ultimo = S.latido = Date.now();
    S.D = {}; S.cargada = {};
    if (S.pendiente) { S.sec = S.pendiente; S.pendiente = null; }
    if (visible()) render();
  }
  async function entrarSinPin() {
    try {
      const r = await api("/config/entrar", { method: "POST", body: json({}), espera: 10000 });
      entrarComo(r.usuario);
    } catch (e) { S.msg = { t: "sin", texto: e.message }; if (visible()) render(); }
  }
  function teclaPin(k) {
    if (S.enviando || (S.msg && S.msg.t === "sin")) return;
    S.msg = null;
    if (k === "x") S.pin = S.pin.slice(0, -1);
    else if (k === "c") S.pin = "";
    else if (S.pin.length < 8) S.pin += k;
    repintarPuntos();
  }
  function repintarPuntos() {
    const p = $c("#cfgPinPuntos");
    if (!p) return;
    const n = Math.max(4, S.pin.length);
    p.innerHTML = Array.from({ length: n }, (_, i) => `<i class="pin-punto${i < S.pin.length ? " is-on" : ""}"></i>`).join("");
    const m = $c("#cfgPinMsg");
    if (m) m.textContent = S.msg ? S.msg.texto : "";
  }
  function pinHTML() {
    if (S.msg && S.msg.t === "sin") {
      return `<div class="pin"><div class="pin-caja pin-caja--sin">
        <div class="pin-ico pin-ico--no">${IC.llave}</div>
        <h2>${esc(S.msg.texto)}</h2>
        <p>Los ajustes cambian cómo funciona el local (precios sugeridos, impresora, quién entra), así que solo los ve quien tenga el permiso «Cambiar los ajustes». Si lo necesitas, pídeselo al dueño.</p>
        <div class="pin-botones">
          <button type="button" class="i-btn i-btn--prin vt-grande" data-c-act="otro">Probar con otro PIN</button>
          <button type="button" class="i-btn vt-grande" data-c-act="vercaja">Volver a la Caja</button>
          <button type="button" class="i-btn i-btn--suave" data-c-act="guias">Ver las guías (sin PIN)</button></div>
      </div></div>`;
    }
    const teclas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "c", "0", "x"].map((k) =>
      k === "x" ? `<button type="button" class="teclado__t teclado__t--acc" data-c-pk="x" aria-label="Borrar">${IC.borrar}</button>`
        : k === "c" ? `<button type="button" class="teclado__t teclado__t--acc" data-c-pk="c" aria-label="Limpiar">C</button>`
          : `<button type="button" class="teclado__t" data-c-pk="${k}">${k}</button>`).join("");
    const n = Math.max(4, S.pin.length);
    return `<div class="pin"><div class="pin-caja" id="cfgPinCaja">
      <div class="pin-ico">${IC.llave}</div>
      <h2>Config</h2>
      <p>Config es para quien tenga el permiso «Cambiar los ajustes». Escribe tu PIN.</p>
      <div class="pin-puntos" id="cfgPinPuntos" aria-label="PIN">${Array.from({ length: n }, (_, i) => `<i class="pin-punto${i < S.pin.length ? " is-on" : ""}"></i>`).join("")}</div>
      <div class="pin-msg" id="cfgPinMsg" role="alert">${S.msg ? esc(S.msg.texto) : ""}</div>
      <div class="pin-teclas">${teclas}</div>
      <button type="button" class="i-btn i-btn--prin vt-grande pin-entrar" data-c-act="entrar">Entrar</button>
      <button type="button" class="i-btn i-btn--suave pin-entrar" data-c-act="guias">Ver las guías (sin PIN)</button>
    </div></div>`;
  }

  /* ==========================================================
     EL MARCO: menú + contenido
     ========================================================== */
  function render() {
    if (!S.user) {
      vista.classList.add("cfg-bloqueada");
      if (S.guiasSolas) {
        vista.innerHTML = `<div class="cfg-guias-vuelta"><button type="button" class="i-btn i-btn--prin" data-c-act="singuias">${IC.llave} Volver al PIN</button>
          <span class="cfg-card__nota">Las guías se leen sin PIN.</span></div><div class="cfg-guias">${guiasHTML()}</div>`;
        pintarGuias();
        return;
      }
      vista.innerHTML = pinHTML();
      return;
    }
    vista.classList.remove("cfg-bloqueada");
    vista.innerHTML = `<div class="cfg">
      <nav class="cfg-nav" aria-label="Secciones de Config">
        <div class="cfg-nav__busca">${buscadorHTML("cfgBuscar", "Buscar un ajuste…", S.q)}</div>
        <div class="cfg-nav__lista" id="cfgNavLista"></div>
        <div class="cfg-nav__pie">
          <div class="cfg-nav__quien">${avatar(S.user)}<span><b>${esc(S.user.nombre || "Dueño")}</b><br>${esc(S.user.rol_nombre || "")}</span></div>
          <button type="button" class="i-btn" data-c-act="salir">${IC.sale} Salir de Config</button>
        </div>
      </nav>
      <section class="cfg-cont"><header class="cfg-cab" id="cfgCab"></header><div class="cfg-cuerpo" id="cfgCuerpo"></div></section>
    </div>`;
    pintarNav();
    pintarSeccion(true);
  }

  function pintarNav() {
    const box = $c("#cfgNavLista");
    if (!box) return;
    const { toks, hits } = L.buscarAjustes(S.q);
    if (!toks.length) {
      box.innerHTML = SECCIONES.map(([k, t, , ic]) => `<button type="button" class="cfg-nav__b${k === S.sec ? " is-on" : ""}" data-c-sec="${k}">${ic}<span>${esc(t)}</span></button>`).join("")
        + `<div class="cfg-nav__sep"></div><button type="button" class="cfg-nav__b${S.sec === "guias" ? " is-on" : ""}" data-c-sec="guias">${IC.guias}<span>Guías y ayuda</span></button>`;
      return;
    }
    if (!hits.length) {
      box.innerHTML = `<p class="cfg-nav__nada">No encontré ningún ajuste con eso. Prueba con otra palabra: <b>impresora</b>, <b>propina</b>, <b>PIN</b>…</p>`;
      return;
    }
    box.innerHTML = `<div class="cfg-nav__tit">${hits.length} resultado${hits.length === 1 ? "" : "s"}</div>` + hits.map(([id, s, t]) =>
      `<button type="button" class="cfg-nav__b cfg-nav__res" data-c-ir="${id}" data-c-sec="${s}"><b>${L.resaltar(t, toks)}</b><small>en ${esc(L.nombreSeccion(s))}</small></button>`).join("");
  }

  function pintarNavSoloMarca() {
    $$c(".cfg-nav__b[data-c-sec]").forEach((b) => { if (!b.classList.contains("cfg-nav__res")) b.classList.toggle("is-on", b.dataset.cSec === S.sec); });
  }

  function cabHTML() {
    const s = seccionDe(S.sec);
    return `<div><h2>${esc(s[1])}</h2><p>${esc(s[2])}</p></div>
      <span class="cfg-guardado" id="cfgGuardado" aria-live="polite"><span class="cfg-guardado__fijo">Los cambios se guardan solos</span><b class="cfg-guardado__ok">Guardado ✓</b></span>`;
  }

  /* Pinta la sección con lo que ya se trajo; si falta algo, lo trae y vuelve a pintar. */
  function pintarSeccion(reset) {
    const cuerpo = $c("#cfgCuerpo");
    if (!cuerpo) return;
    const y = reset ? 0 : cuerpo.scrollTop;
    $c("#cfgCab").innerHTML = cabHTML();
    const sec = S.sec;
    if (S.cargada[sec] || !CARGAS[sec]) {
      cuerpo.innerHTML = SEC[sec]();
      cuerpo.scrollTop = y;
      alPintar(sec);
    } else {
      cuerpo.innerHTML = '<p class="cfg-cargando">Cargando…</p>';
      cargarSeccion(sec);
    }
    pintarNavSoloMarca();
    if (S.flash && (S.cargada[sec] || !CARGAS[sec])) { const id = S.flash; S.flash = null; setTimeout(() => resaltar(id), 30); }
  }
  async function cargarSeccion(sec) {
    const mi = ++S.req;
    try {
      await CARGAS[sec]();
      S.cargada[sec] = true;
    } catch (e) {
      if (mi !== S.req || !S.user || S.sec !== sec) return;
      const cuerpo = $c("#cfgCuerpo");
      if (cuerpo) cuerpo.innerHTML = `<div class="cfg-aviso cfg-aviso--mal"><b>No se pudo cargar esta sección.</b> ${esc(e.message)}
        <div class="cfg-fila" style="margin-top:8px"><button type="button" class="i-btn" data-c-act="reintentar">Reintentar</button></div></div>`;
      return;
    }
    if (mi !== S.req || !S.user || S.sec !== sec || !visible()) return;
    pintarSeccion(true);
  }
  function resaltar(id) {
    const e = $c(`[data-aj="${id}"]`);
    if (!e) return;
    const d = e.closest("details");
    if (d) { d.open = true; S.abiertos.add(d.dataset.cDet); }
    e.scrollIntoView({ block: "center" });
    e.classList.remove("cfg-flash");
    void e.offsetWidth;
    e.classList.add("cfg-flash");
    setTimeout(() => e.classList.remove("cfg-flash"), 2700);
  }
  function ir(sec, id) {
    S.sec = sec; S.q = ""; S.flash = id;
    const inp = $c("#cfgBuscar"); if (inp) inp.value = "";
    pintarNav();
    pintarSeccion(true);
  }

  /* ==========================================================
     LO QUE SE TRAE DEL SERVIDOR, SECCIÓN POR SECCIÓN
     ========================================================== */
  const CARGAS = {
    async local() {
      const [local] = await Promise.all([capi("/local"), refrescarAjustes()]);
      S.D.local = local;
    },
    async equipo() {
      const [usuarios, permisos] = await Promise.all([capi("/usuarios"), capi("/usuarios/permisos")]);
      S.D.usuarios = usuarios; S.D.permisos = permisos;
    },
    async cobro() { await refrescarAjustes(); },
    async impresora() {
      await refrescarAjustes();
      S.bal = null;
      if (tipoImpresion() !== "navegador") cargarImpresoras(true);
    },
    async pantallas() {
      const [tvs, textos, salud] = await Promise.all([capi("/config/televisores"), capi("/config/pantallas"), capi("/salud")]);
      S.D.tvs = tvs.televisores; S.D.textos = textos.textos; S.D.ejemplo = textos.ejemplo; S.D.salud = salud;
    },
    async caja() {
      const [red, salud] = await Promise.all([capi("/red").catch((e) => ({ error: e.message })), capi("/salud"), refrescarAjustes()]);
      S.D.red = red; S.D.salud = salud; S.D.pinVisible = false;
    },
    async respaldos() {
      const [, copias, lugares, info, vuelta, mudanza] = await Promise.all([
        refrescarAjustes(),
        capi("/config/respaldos"),
        capi("/respaldo/lugares").catch(() => []),
        capi("/actualizacion").catch(() => null),
        capi("/actualizacion/vuelta").catch(() => null),
        capi("/mudanza").catch(() => null),
      ]);
      S.D.copias = copias.copias; S.D.ventasHoy = copias.ventas_hoy; S.D.cajaAbierta = copias.caja_abierta;
      S.D.lugares = lugares; S.D.info = info; S.D.vuelta = vuelta; S.D.mudanza = mudanza;
      if (info) INFO_VERSION = info;
      if (vuelta) VUELTA = vuelta;
    },
  };

  /* ==========================================================
     SECCIÓN · MI LOCAL
     ========================================================== */
  function anchoPapel() { return IMPRESION.papel === 58 ? 32 : 48; }
  function ticketActual() {
    const l = S.D.local || {};
    return L.ticketTxt({ nombre: l.nombre, rut: l.rut, direccion: l.direccion, mensaje: AJUSTES.mensaje_ticket }, S.ticketAncho || anchoPapel());
  }
  function secLocal() {
    const l = S.D.local || {};
    const ancho = S.ticketAncho || anchoPapel();
    return `<div class="cfg-dos">
      <div class="cfg-card">
        <h3 class="cfg-card__t">Datos del local</h3>
        ${aj("l-nombre", "Nombre del local", "Sale en el comprobante, en el cierre y en los televisores.", campo("local.nombre", l.nombre || "", { max: 40, err: "nombre" }), { cls: "cfg-aj--in" })}
        ${aj("l-rut", "RUT", "Sale en el comprobante. Se revisa el dígito verificador.", campo("local.rut", l.rut || "", { max: 14, ph: "12.345.678-9", err: "rut" }), { cls: "cfg-aj--in" })}
        ${aj("l-dir", "Dirección", "Sale en el comprobante y en el cierre.", campo("local.direccion", l.direccion || "", { max: 80 }), { cls: "cfg-aj--in" })}
        ${aj("l-mensaje", "Mensaje al pie del ticket", "Una frase corta de despedida. Si lo dejas vacío sale «¡Gracias!», como hasta ahora.", campo("ajuste.mensaje_ticket", AJUSTES.mensaje_ticket === "¡Gracias!" ? "" : AJUSTES.mensaje_ticket || "", { max: 60, ph: "¡Gracias!" }), { cls: "cfg-aj--in" })}
        ${aj("l-logo", "Logo del ticket", "Un dibujo chico arriba del nombre.", `<button type="button" class="i-btn" disabled>Elegir imagen</button>`, { pronto: true, cls: "cfg-aj--soon" })}
      </div>
      <aside class="cfg-previa"><h4>Así sale en el ticket</h4>
        ${seg("ticket", [[32, "58 mm"], [48, "80 mm"]], ancho)}
        <pre class="cfg-ticket${ancho === 48 ? " cfg-ticket--80" : ""}" id="cfgTicket">${esc(ticketActual())}</pre></aside>
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Cómo trabaja tu local</h3>
      ${ajSw("l-inv", "Llevar inventario en este local", "Apágalo si solo quieres vender, sin llevar la cuenta de lo que queda. Se esconden las herramientas de stock y Por comprar; lo que ya tenías anotado se conserva.", "inv", usarInventario())}
    </div>`;
  }

  /* ==========================================================
     SECCIÓN · EQUIPO
     ========================================================== */
  function secEquipo() {
    const q = sinTildes(S.eq).trim();
    const gente = S.D.usuarios || [];
    const filas = gente.filter((u) => !q || sinTildes(u.nombre).includes(q)).map((u) => `
      <button type="button" class="cfg-fila-p${u.activo ? "" : " es-baja"}" data-c-persona="${u.id}">
        ${avatar(u)}<span><b>${esc(u.nombre)}</b><small>${u.activo ? esc(u.rol_nombre) + (u.permisos ? " · con permisos propios" : "") + (S.user && u.id === S.user.id ? " · eres tú" : "") : "ya no entra a la caja"}</small></span>
        <span class="cfg-fila-p__ir">Editar</span></button>`).join("");
    return `<div class="cfg-card" data-aj="e-lista">
      <div class="cfg-lista__tit"><h3 class="cfg-card__t">Quiénes entran a la caja</h3>${gente.length > 6 ? buscadorHTML("cfgEqBusca", "Buscar a alguien…", S.eq) : ""}</div>
      <p class="cfg-card__nota">El <b>dueño</b> puede todo. El <b>cajero</b> vende, cobra y cuadra su caja, pero no cambia precios ni corrige ventas de días pasados. Al editar a alguien puedes elegir sus permisos uno por uno, y su color.</p>
      <div class="cfg-lista">${filas || '<p class="cfg-rvacio">No hay nadie con ese nombre.</p>'}</div>
      <div class="cfg-fila" style="margin-bottom:12px"><button type="button" class="i-btn i-btn--prin" data-c-persona="nuevo">${IC.mas} Agregar a alguien</button></div>
    </div>`;
  }

  /* ==========================================================
     SECCIÓN · COBRO
     ========================================================== */
  const MEDIOS = [["efectivo", "Efectivo"], ["debito", "Débito"], ["credito", "Crédito"], ["transferencia", "Transferencia"]];
  const chip = (attrs, on, txt) => `<button type="button" class="i-chip${on ? " is-on" : ""}" ${attrs}>${txt}</button>`;
  function secCobro() {
    const A = AJUSTES, activos = A.medios_pago || [];
    const propSug = A.propina_sugerida || [], desc = A.descuentos_rapidos || [];
    return `<div class="cfg-card">
      <h3 class="cfg-card__t">Cómo te pagan</h3>
      ${aj("c-medios", "Formas de pago", "Los botones que aparecen al cobrar. Siempre tiene que quedar al menos una.",
        `<div class="cfg-chips">${MEDIOS.map(([k, t]) => chip(`data-c-medio="${k}" aria-pressed="${activos.includes(k)}"`, activos.includes(k), t)).join("")}</div>`, { cls: "cfg-aj--col" })}
      ${ajSw("c-mixto", "Permitir pagar en dos formas", "Parte en efectivo y parte con tarjeta, por ejemplo. Cada parte queda anotada aparte.", "mixto", A.pago_mixto)}
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Propinas y descuentos</h3>
      ${ajSw("c-propina", "Ofrecer propina al cobrar", "Aparece el campo de propina en el cobro. Apagado, el campo no está.", "propina", A.propinas)}
      ${A.propinas ? aj("c-propina", "Propinas sugeridas", "Botones de porcentaje para que el cliente elija rápido. Sin ninguno marcado no hay botones.",
        `<div class="cfg-chips">${[5, 10, 15, 20].map((p) => chip(`data-c-chip="propina_sugerida" data-v="${p}"`, propSug.includes(p), p + "%")).join("")}</div>`, { cls: "cfg-aj--col" }) : ""}
      ${A.propinas ? ajSw("c-propina", "La propina solo se cobra con tarjeta", "Así queda en el cuadre de tarjetas y no en el cajón. Con efectivo o transferencia el campo de propina se apaga.", "solotarjeta", A.propina_solo_tarjeta) : ""}
      ${aj("c-desc", "Descuentos rápidos", "Los botones de descuento del cobro (hasta 6). «Sin descuento» está siempre.",
        `<div class="cfg-chips">${[5, 10, 15, 20, 25].concat(desc.filter((p) => ![5, 10, 15, 20, 25].includes(p))).map((p) => chip(`data-c-chip="descuentos_rapidos" data-v="${p}"`, desc.includes(p), p + "%")).join("")}
          <span class="cfg-num" style="width:104px"><input class="cfg-in" id="cfgDescOtro" inputmode="numeric" placeholder="Otro" aria-label="Otro descuento" maxlength="3"><i>%</i></span>
          <button type="button" class="i-btn" data-c-act="descotro">Agregar</button></div>`, { cls: "cfg-aj--col" })}
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Precios sugeridos</h3>
      ${aj("c-margen", "Margen sugerido", "Cuánto de cada venta se queda el local. Al ponerle precio a un producto, la caja propone uno con este margen: 50% es cobrar el doble de lo que costó.",
        `<div class="cfg-chips">${[40, 50, 60, 70, 75].map((p) => chip(`data-c-margen="${p}"`, A.margen_sugerido === p, p + "%")).join("")}
         <span class="cfg-num"><input class="cfg-in" data-c-in="margen" inputmode="numeric" value="${A.margen_sugerido}" aria-label="Otro margen"><i>%</i></span></div>`, { cls: "cfg-aj--col" })}
      ${aj("c-redondeo", "Redondear el precio sugerido hacia arriba", "Nadie cobra $2.437: el sugerido sube al múltiplo de arriba, así el margen es un piso y el redondeo no se lo come.",
        seg("redondeo", [[10, "$10"], [50, "$50"], [100, "$100"]], A.redondeo_precio), { cls: "cfg-aj--col" })}
      <div class="cfg-ejemplo" id="cfgEjMargen">${L.ejemploMargen(A.margen_sugerido, A.redondeo_precio)}</div>
    </div>`;
  }

  /* ==========================================================
     SECCIÓN · IMPRESORA Y BALANZA
     ========================================================== */
  const TIPOS = [["termica", "Impresora de tickets (térmica)", "La que corta el papel sola. Imprime directo, sin preguntar."],
    ["windows", "Impresora normal (Windows)", "Usa el driver de Windows."],
    ["navegador", "Preguntar al navegador", "Aparece el diálogo de impresión de siempre."]];
  let imprimiendoPrueba = false, instalando = false, cargandoImpresoras = false;
  function balBorrador() {
    if (!S.bal) {
      const f = AJUSTES.formato_balanza || { modo: "ticket", prefijo: "25", codigo: [2, 6], valor: [6, 12], divisor_peso: 1000 };
      S.bal = { modo: f.modo, prefijo: f.prefijo, codigo: f.codigo.slice(), valor: f.valor.slice(), divisor_peso: f.divisor_peso, prueba: "", resultado: "" };
    }
    return S.bal;
  }
  function formatoDe(b) { return { modo: b.modo, prefijo: String(b.prefijo).trim(), codigo: b.codigo.slice(), valor: b.valor.slice(), divisor_peso: b.divisor_peso }; }
  function secImpresora() {
    const tipo = tipoImpresion(), directa = tipo !== "navegador";
    const lista = S.D.impresoras;
    const usar = !!AJUSTES.usar_balanza, B = balBorrador();
    const dib = L.dibujoFormatoBalanza(formatoDe(B));
    const opciones = lista ? lista.opciones : [{ valor: "", texto: "Elige una impresora" }].concat(IMPRESION.impresora ? [{ valor: IMPRESION.impresora, texto: IMPRESION.impresora + " (guardada)" }] : []);
    const puertos = S.D.puertos || [];
    return `<div class="cfg-card">
      <h3 class="cfg-card__t">Impresión de comprobantes</h3>
      ${ajSw("i-siempre", "Imprimir el comprobante después de cada venta", "Si lo apagas, el comprobante se imprime solo cuando alguien lo pide. Esta preferencia queda en este navegador.", "imp.siempre", IMPRESION.automatica)}
      ${aj("i-tipo", "Tipo de impresora", "", radios("imp.tipo", TIPOS, tipo), { cls: "cfg-aj--col" })}
      ${directa ? aj("i-impresora", "Impresora", "Las instaladas en el computador de la caja.",
        `<select class="cfg-sel cfg-sel--240" id="cfgImpSel" data-c-sel="impresora">${opciones.map((o) => `<option value="${esc(o.valor)}"${o.deshabilitada ? " disabled" : ""}${o.valor === IMPRESION.impresora ? " selected" : ""}>${esc(o.texto)}</option>`).join("")}</select>
         <button type="button" class="i-btn" data-c-act="actualizar" id="cfgImpAct"${cargandoImpresoras ? " disabled" : ""}>Actualizar lista</button>`, { cls: "cfg-aj--nowrap" }) : ""}
      ${aj("i-papel", "Ancho del papel", "Es el ancho del <b>rollo</b>, no el de la impresora. Si en la prueba los precios saltan a la línea de abajo, o las rayas salen cortadas, el rollo es más angosto: cambia a 58 mm y prueba otra vez.",
        seg("imp.papel", [[58, "58 mm"], [80, "80 mm"]], IMPRESION.papel))}
      ${aj("i-prueba", "Imprimir prueba", "Sale un ticket de ejemplo con precios, tildes y tu mensaje del pie, para revisar el papel.",
        `<button type="button" class="i-btn i-btn--prin" data-c-act="prueba" id="cfgImpPrueba"${directa && !imprimiendoPrueba ? "" : " disabled"}>${IC.impresora} Imprimir prueba</button>`)}
      <div class="cfg-estado" id="cfgImpEstado" role="status">${esc(S.D.impEstado || (directa ? "Elige una impresora para imprimir directamente." : "Con «Preguntar al navegador» no hay prueba directa: el diálogo aparece al imprimir."))}</div>
      ${det("instalar", "¿No aparece tu impresora?", "", puertos.length
        ? aj("i-instalar", "Instalar la impresora de tickets", "Windows va a pedir permiso para instalarla.",
          `<select class="cfg-sel" id="cfgPuerto" style="min-width:200px">${puertos.map((p) => `<option value="${esc(p.nombre)}">${esc(p.nombre)}${p.descripcion ? " — " + esc(p.descripcion) : ""}</option>`).join("")}</select>
           <button type="button" class="i-btn" data-c-act="instalar" id="cfgInstalar"${instalando ? " disabled" : ""}>Instalar</button>`)
        : aj("i-instalar", "Instalar la impresora de tickets", "Conecta la impresora al computador, enciéndela y aprieta «Actualizar lista». Si Windows no la tiene instalada y hay un puerto libre, aquí se ofrece instalarla.", ""))}
    </div>
    <div class="cfg-card" data-aj="b-usar">
      <h3 class="cfg-card__t">Balanza</h3>
      ${ajSw("b-usar", "Este local cobra etiquetas de una balanza", "Para el café a granel, el pan o el queso que se pesan y salen con una etiqueta con código de barras. Si no tienes balanza, déjalo apagado: así nadie puede cobrar un código inventado.", "bal.usar", usar)}
      ${AJUSTES.formato_balanza_roto ? `<div class="cfg-aviso cfg-aviso--mal">El formato guardado de la balanza no se entiende, así que la caja no está cobrando etiquetas. Revísalo abajo: se guarda solo cuando queda bien.</div>` : ""}
      ${usar ? `
        ${aj("b-modo", "Qué imprime la etiqueta", "", radios("bal.modo", [["ticket", "Un ticket con el total", "El detalle queda en el papel."], ["plu_peso", "El número del producto y el peso", "La caja calcula el precio."], ["plu_precio", "El número del producto y el precio", "La balanza ya calculó el precio."]], B.modo), { cls: "cfg-aj--col" })}
        ${det("codigo", "Cómo está armado el código", "(solo si la balanza es distinta)", `
          <div data-aj="b-codigo">
          <p class="cfg-card__nota">Las posiciones se cuentan desde 0 y «hasta» no se incluye. El último dígito (12) es el verificador: no lo uses para el número ni el valor. Se guarda solo cuando queda bien.</p>
          <div class="cfg-3cols" style="margin:10px 0">
            <label class="cfg-campo"><span>Prefijo</span><input class="cfg-in" data-c-bal="prefijo" inputmode="numeric" value="${esc(B.prefijo)}"></label>
            <label class="cfg-campo"><span>El número, desde</span><input class="cfg-in" data-c-bal="c0" type="number" min="0" max="11" value="${B.codigo[0] == null ? "" : B.codigo[0]}"></label>
            <label class="cfg-campo"><span>Hasta (sin incluir)</span><input class="cfg-in" data-c-bal="c1" type="number" min="1" max="12" value="${B.codigo[1] == null ? "" : B.codigo[1]}"></label>
            <label class="cfg-campo"><span>${B.modo === "plu_peso" ? "Divisor del peso" : "&nbsp;"}</span>${B.modo === "plu_peso" ? `<input class="cfg-in" data-c-bal="div" type="number" min="1" value="${B.divisor_peso}">` : ""}</label>
            <label class="cfg-campo"><span>El valor, desde</span><input class="cfg-in" data-c-bal="v0" type="number" min="0" max="11" value="${B.valor[0] == null ? "" : B.valor[0]}"></label>
            <label class="cfg-campo"><span>Hasta (sin incluir)</span><input class="cfg-in" data-c-bal="v1" type="number" min="1" max="12" value="${B.valor[1] == null ? "" : B.valor[1]}"></label>
          </div>
          ${B.modo === "plu_peso" ? `<p class="cfg-card__nota">Divisor del peso: 1000 si la etiqueta trae gramos.</p>` : ""}
          <pre class="cfg-balanza-dib" id="cfgBalDib">${esc(dib)}</pre></div>`)}
        ${aj("b-prueba", "Probar con una etiqueta", "Escanea una etiqueta o escribe su código y mira qué entiende la caja.",
          `<div class="cfg-fila" style="justify-content:flex-end"><input class="cfg-in" id="cfgBalCod" data-c-bal="prueba" inputmode="numeric" placeholder="Escanea o escribe el código" value="${esc(B.prueba)}" style="width:230px" autocomplete="off">
           <button type="button" class="i-btn" data-c-act="balprobar">Probar</button><button type="button" class="i-btn i-btn--suave" data-c-act="balejemplo">Usar un ejemplo</button></div>`, { cls: "cfg-aj--col" })}
        <div class="cfg-estado" id="cfgBalRes" role="status" aria-live="polite">${esc(B.resultado)}</div>` : ""}
    </div>`;
  }

  /* ----- la impresora ----- */
  function guardarPrefs(cambios) {
    const sig = { ...IMPRESION, ...cambios };
    try {
      localStorage.setItem("pos.impresion", json(sig));
    } catch (e) {
      avisar("No se pudieron guardar las preferencias. Revisa el almacenamiento del navegador.", true);
      return false;
    }
    IMPRESION = sig;
    imprimirSiempre = sig.automatica;
    guardado();
    return true;
  }
  const estadoImp = (t) => { S.D.impEstado = t; const e = el("cfgImpEstado"); if (e) e.textContent = t; };
  async function cargarImpresoras(silencioso) {
    if (cargandoImpresoras) return;
    cargandoImpresoras = true;
    const b = el("cfgImpAct"); if (b) b.disabled = true;
    S.D.puertos = [];
    if (!silencioso) estadoImp("Consultando las impresoras de Windows…");
    try {
      const r = await capi("/impresion/impresoras");
      impresorasWindows = r.impresoras || [];
      const elegida = IMPRESION.impresora;
      const puerto = impresorasWindows.find((p) => p.nombre === elegida)?.puerto;
      // Recordar el puerto permite detectar el tipo al abrir de nuevo la caja.
      if (puerto && puerto !== IMPRESION.puerto) { try { guardarPrefsSilencioso({ puerto }); } catch (e) { /* la lista sirve igual */ } }
      const res = L.resumenImpresoras(r, elegida);
      S.D.impresoras = res;
      estadoImp(res.estado);
      if (r.disponible && !res.hayPapel) {
        try { S.D.puertos = L.puertosUtiles((await capi("/impresion/puertos")).puertos); } catch (e) { /* sin puertos */ }
        if (S.D.puertos.length) estadoImp("Windows tiene puertos disponibles. Elige el de la impresora y pulsa Instalar.");
      }
    } catch (e) {
      estadoImp(e.message + ". Se conserva la impresora guardada.");
    } finally {
      cargandoImpresoras = false;
      if (S.user && S.sec === "impresora" && visible() && S.cargada.impresora) repintarImpresion();
    }
  }
  function guardarPrefsSilencioso(cambios) {
    const sig = { ...IMPRESION, ...cambios };
    localStorage.setItem("pos.impresion", json(sig));
    IMPRESION = sig;
  }
  /* Repinta la tarjeta de impresión sin perder el lugar ni lo que se escribe en la balanza. */
  function repintarImpresion() {
    const cuerpo = $c("#cfgCuerpo");
    if (!cuerpo || S.sec !== "impresora") return;
    const y = cuerpo.scrollTop;
    cuerpo.innerHTML = secImpresora();
    cuerpo.scrollTop = y;
  }
  async function probarImpresionConfig() {
    if (imprimiendoPrueba) return;
    if (!IMPRESION.impresora || tipoImpresion() === "navegador") return estadoImp("Elige una impresora de Windows para imprimir la prueba.");
    imprimiendoPrueba = true;
    const b = el("cfgImpPrueba"); if (b) b.disabled = true;
    estadoImp("Enviando la prueba…");
    try {
      const prefijo = tipoImpresion() === "termica" ? "crudo/" : "";
      const r = await capi(`/impresion/${prefijo}prueba`, { method: "POST", espera: 25000,
        body: json({ impresora: IMPRESION.impresora, papel: IMPRESION.papel }) });
      estadoImp(r.detalle);
    } catch (e) {
      estadoImp(e.message + ". Revisa la cola de Windows antes de repetir la prueba.");
    } finally {
      imprimiendoPrueba = false;
      const b2 = el("cfgImpPrueba"); if (b2) b2.disabled = false;
    }
  }
  async function instalarImpresoraConfig() {
    if (instalando) return;
    const puerto = (el("cfgPuerto") || {}).value;
    if (!(S.D.puertos || []).some((p) => p.nombre === puerto)) return;
    instalando = true;
    const b = el("cfgInstalar"); if (b) b.disabled = true;
    estadoImp("Acepta el permiso de Windows para instalar la impresora…");
    try {
      const r = await capi("/impresion/instalar", { method: "POST", espera: 125000,
        body: json({ puerto, nombre: "Kofe Tickets" }) });
      // Guardar antes de consultar: la cola ya existe aunque falle la recarga.
      if (!guardarPrefs({ impresora: r.nombre, puerto })) throw Error("La impresora se instaló, pero no se pudo guardar la selección en este navegador. Actualiza la lista y selecciónala.");
      instalando = false;
      await cargarImpresoras();
    } catch (e) {
      estadoImp(e.message);
    } finally {
      instalando = false;
      const b2 = el("cfgInstalar"); if (b2) b2.disabled = false;
    }
  }

  /* ----- la balanza ----- */
  function ean13(d12) { let s = 0; for (let i = 0; i < 12; i++) s += Number(d12[i]) * (i % 2 ? 3 : 1); return d12 + String((10 - (s % 10)) % 10); }
  function ejemploEtiqueta(b) {
    const pad = (n, l) => String(n).padStart(l, "0");
    const nc = b.codigo[1] - b.codigo[0], nv = b.valor[1] - b.valor[0];
    const base = (b.prefijo + pad(b.modo === "ticket" ? 412 : 123, nc) + pad(b.modo === "plu_peso" ? 850 : b.modo === "plu_precio" ? 21165 : 14500, nv)).padEnd(12, "0").slice(0, 12);
    return ean13(base);
  }
  async function guardarFormatoBalanza() {
    const B = balBorrador();
    try {
      const r = await capi("/ajustes", { method: "PUT", body: json({ formato_balanza: formatoDe(B) }) });
      AJUSTES = { ...AJUSTES, ...r };
      guardado();
      B.resultado = "Formato guardado. Ya puedes probar una etiqueta.";
    } catch (e) {
      // Conservamos lo escrito para corregir las posiciones que rechazó el servidor.
      B.resultado = e.message;
    }
    const r2 = el("cfgBalRes"); if (r2) r2.textContent = B.resultado;
  }
  async function probarEtiqueta() {
    const B = balBorrador();
    const campo_ = el("cfgBalCod");
    const codigo = (campo_ ? campo_.value : B.prueba).trim();
    B.prueba = codigo;
    const salida = (t) => { B.resultado = t; const e = el("cfgBalRes"); if (e) e.textContent = t; };
    if (!codigo) return salida("Escanea o escribe una etiqueta.");
    if (!L.formatoBalanzaValido(formatoDe(B))) return salida("Primero arregla el formato de arriba.");
    salida("Leyendo etiqueta…");
    try {
      const r = await capi("/codigos/" + encodeURIComponent(codigo));
      salida(r.balanza ? `${r.balanza.nombre} · ${r.balanza.detalle} · ${clp(r.balanza.precio)}`
        : r.problema || "Ese código no es una etiqueta de balanza.");
    } catch (e) { salida(e.message); }
  }

  /* ==========================================================
     SECCIÓN · PANTALLAS DEL LOCAL
     ========================================================== */
  const baseDeLaCaja = () => {
    const s = S.D.salud || {};
    return String(s.pantallas_url || "").replace(/\/pantallas$/, "") || location.origin;
  };
  function secPantallas() {
    const tvs = S.D.tvs || [], P = S.D.textos || {}, ej = S.D.ejemplo || {}, enRed = !S.D.salud || S.D.salud.en_la_red !== false;
    const base = baseDeLaCaja();
    const tarjetas = tvs.map((tv) => {
      const v = L.textoVisto(tv.visto_hace_s), url = L.urlTv(tv, base);
      return `<div class="cfg-tv">
        <div class="cfg-tv__cab"><span class="cfg-tv__pant ${tv.orient === "vertical" ? "v" : "h"}"></span>
          <span><b>${esc(tv.nombre)}</b><small>Muestra: <b>${L.MODO_TXT[tv.modo]}</b> · ${L.ORIENT_TXT[tv.orient]}${tv.simple ? " · versión simple" : ""}</small>
            <small><span class="cfg-punto${v.activo ? "" : " cfg-punto--no"}"></span>${esc(v.texto)}</small></span>
          <button type="button" class="i-btn" data-c-tv="${tv.id}">Editar</button></div>
        <div class="cfg-url"><code>${esc(url)}</code><button type="button" class="i-btn" data-c-copiar="${esc(url)}">${IC.copia} Copiar</button></div></div>`;
    }).join("");
    const cinta = (P.cinta || []).map((t, i) => `<div class="cfg-frase"><input class="cfg-in" data-c-cinta="${i}" value="${esc(t)}" maxlength="90" aria-label="Frase ${i + 1}"><button type="button" class="cfg-x" data-c-cinta-x="${i}" aria-label="Borrar la frase">&#x2715;</button></div>`).join("");
    const textos = [["kicker", "Frase de arriba"], ["bajada", "Frase bajo el nombre"], ["marcaTxt", "Texto al lado del logo, en la carta"], ["tituloSug", "Título del combo"], ["pieSug", "Línea de abajo del combo"]]
      .map(([k, t]) => aj("p-textos", t, "", campo("txt." + k, P[k] || "", { max: 70, ph: ej[k] || "" }), { cls: "cfg-aj--in" })).join("");
    return `${enRed ? "" : `<div class="cfg-aviso">Esta caja atiende solo en este computador, así que los televisores no pueden conectarse. Se arregla en la instalación (la caja tiene que escuchar en la red del local).</div>`}
    <div class="cfg-card" data-aj="p-tvs">
      <h3 class="cfg-card__t">Televisores</h3>
      <p class="cfg-card__nota">En cada televisor abre el navegador y entra a su dirección: no hay que instalar nada, la carta le llega de esta caja sola. Para cambiar lo que muestra uno, tócale <b>Editar</b>. Si cambias lo que muestra, copia su dirección nueva.</p>
      ${tarjetas || '<p class="cfg-rvacio">Todavía no hay televisores.</p>'}
      <div class="cfg-fila" style="margin-bottom:12px"><button type="button" class="i-btn i-btn--prin" data-c-act="tvnuevo">${IC.mas} Agregar un televisor</button></div>
    </div>
    <div class="cfg-card" data-aj="p-totem">
      <h3 class="cfg-card__t">Otras pantallas</h3>
      <div class="cfg-soon">${IC.totem}<span><b>Tótem de autoservicio <span class="cfg-pronto">Próximamente</span></b><small>Una pantalla táctil para que el cliente pida y pague solo.</small></span><button type="button" class="i-btn" disabled>Configurar</button></div>
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Lo que dicen las pantallas</h3>
      ${det("textos", "Textos de las pantallas", "", `<div data-aj="p-textos">
        <p class="cfg-card__nota">El nombre del local viene de «Mi local». Lo que dejes vacío queda como estaba. Mejor que el título del combo no sea una pregunta: el televisor no es táctil y la gente igual lo toca.</p>
        ${textos}</div>`)}
      ${det("cinta", "Horarios y avisos que corren abajo", `(${(P.cinta || []).length})`, `<div data-aj="p-cinta">
        <p class="cfg-card__nota">Las frases que pasan corriendo abajo en la carta: horarios, wifi, si hay leche sin lactosa, lo que sea. Sin ninguna, salen las de siempre.</p>
        <div style="margin-top:10px">${cinta}</div>
        <button type="button" class="i-btn" data-c-act="cintamas"${(P.cinta || []).length >= 12 ? " disabled" : ""}>${IC.mas} Agregar una frase</button></div>`)}
      ${det("avanzado", "Avanzado", "(carta desde otra dirección, respaldo de las pantallas)", `
        ${aj("p-fuente", "Leer la carta desde otra dirección", "Hoy las pantallas leen la carta de esta caja (Inventario). Solo cámbialo si otro sistema publica la carta en una dirección web.",
          `<div style="width:100%"><input class="cfg-in" data-c-in="txt.fuente_url" placeholder="https://mi-sistema.cl/carta.json" value="${esc(P.fuente_url || "")}" maxlength="300">
           <div class="cfg-fila" style="margin-top:8px"><label class="cfg-fila" style="gap:8px">Revisar cada <span class="cfg-num" style="width:96px"><input class="cfg-in" data-c-in="txt.fuente_cada" inputmode="numeric" value="${P.fuente_cada || 10}"><i>min</i></span></label>
           <button type="button" class="i-btn" data-c-act="fuenteprobar">Probar la conexión</button></div>
           <div class="cfg-estado" id="cfgFuenteEst" role="status">${esc(S.D.fuenteEst || "")}</div></div>`, { cls: "cfg-aj--col" })}
        ${aj("p-resp", "Respaldo de las pantallas", "Los televisores y los textos quedan guardados en esta caja. Descarga una copia si vas a pasarla a otra.",
          `<button type="button" class="i-btn" data-c-act="pantbajar">${IC.baja} Descargar</button><button type="button" class="i-btn" data-c-act="pantsubir">Cargar un respaldo</button><button type="button" class="i-btn i-btn--borrar" style="margin-right:0" data-c-act="pantreset">Volver a los datos de ejemplo</button>
           <input type="file" id="cfgPantArchivo" accept=".json,application/json" hidden>`, { cls: "cfg-aj--col" })}`)}
    </div>`;
  }

  /* ==========================================================
     SECCIÓN · ESTA CAJA
     ========================================================== */
  function secCaja() {
    const A = AJUSTES, red = S.D.red || {}, base = baseDeLaCaja();
    const pantallaCompleta = pantallaCompletaNativa || !!document.fullscreenElement;
    const oculta = document.body.classList.contains("barra-oculta");
    const quien = SESION && SESION.nombre ? esc(SESION.nombre) : "nadie";
    const caja = TURNO && TURNO.abierto ? "con la caja abierta" : "con la caja cerrada";
    return `<div class="cfg-card">
      <h3 class="cfg-card__t">Esta pantalla</h3>
      ${ajSw("k-tactil", "Modo táctil", "Muestra el teclado numérico en pantalla. Préndelo si esta caja tiene pantalla táctil. En un computador con teclado de verdad estorba: apagado, se escribe con el teclado de siempre, también el PIN.", "tactil", A.teclado_en_pantalla)}
      ${aj("k-completa", "Pantalla completa", "Saca el marco de la ventana para usar toda la pantalla. También sirve la tecla F11.", `<button type="button" class="i-btn" data-c-act="completa">⛶ ${pantallaCompleta ? "Salir de pantalla completa" : "Pasar a pantalla completa"}</button>`)}
      ${aj("k-barra", "Esconder la barra de arriba", "Deja solo una franja fina para ganar espacio. Se vuelve a mostrar tocando «Menú».", `<button type="button" class="i-btn" data-c-act="barra">⌃ ${oculta ? "La barra ya está escondida" : "Esconder la barra"}</button>`)}
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Seguridad</h3>
      ${aj("k-bloqueo", "La caja se bloquea sola después de", "Nunca corta una venta: si hay un pedido armado o una ventana abierta, espera.",
        `<select class="cfg-sel" data-c-sel="bloqueo" style="min-width:210px">${[1, 2, 3, 5, 10, 15, 30].map((m) => `<option value="${m}"${m === (A.bloqueo_minutos || 3) ? " selected" : ""}>${L.minutosTxt(m)} sin uso</option>`).join("")}</select>`)}
      ${aj("k-sesion", "Quién está en la caja", `Ahora está <b>${quien}</b>, ${caja}. Para cambiar de usuario o salir de su cuenta, primero hay que cerrar la caja.`,
        `<button type="button" class="i-btn" data-c-act="sesion">${IC.sale} Cambiar de usuario</button>`)}
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Abrir la caja desde otro equipo</h3>
      <p class="cfg-card__nota">Sirve para usar la caja desde un tablet o desde otro computador del local. Desde este computador no se pide PIN.</p>
      ${aj("k-red", "Dirección de esta caja", "Se escribe en el navegador del otro equipo, con el Wi-Fi del local.",
        `<div class="cfg-url" style="width:100%;min-width:260px"><code>${esc(base)}</code><button type="button" class="i-btn" data-c-copiar="${esc(base)}">${IC.copia} Copiar</button></div>`, { cls: "cfg-aj--in" })}
      ${red.error ? aj("k-pinred", "PIN de red", esc(red.error), "") : `${red.de_fabrica ? `<div class="cfg-aviso">Es el PIN de fábrica, <b>el mismo de todas las cajas</b>: cualquiera en el Wi-Fi del local que lo sepa puede abrir la caja. Cámbialo por uno propio.</div>` : ""}
      ${aj("k-pinred", "PIN de red", "Lo piden los tablets y otros computadores la primera vez que abren la caja. Si lo cambias, los que ya habían entrado tendrán que escribir el nuevo.",
        `<b id="cfgPinRed" style="font-size:22px;letter-spacing:.2em;min-width:104px;text-align:right">${S.D.pinVisible ? esc(red.pin) : "••••••"}</b>
         <button type="button" class="i-btn" data-c-act="verpin">${S.D.pinVisible ? "Esconder" : "Ver"}</button>
         ${red.fijo ? `<span class="cfg-card__nota">Lo fijó la instalación: no se cambia desde acá.</span>` : `<button type="button" class="i-btn" data-c-act="nuevopin">${red.de_fabrica ? "Crear uno propio" : "Cambiar por uno nuevo"}</button>`}`)}`}
    </div>`;
  }

  /* ==========================================================
     SECCIÓN · RESPALDOS Y ACTUALIZACIONES
     ========================================================== */
  function estadoAfueraHTML(e) {
    e = e || {};
    if (!e.carpeta) {
      return `<span class="cfg-aviso" style="display:block;margin:0">Todavía no hay copia de afuera. Si el disco de este computador se muere, se pierden las ventas junto con sus respaldos.</span>`;
    }
    if (!e.cuando) return "Carpeta elegida. La primera copia sale en el próximo respaldo.";
    const cuando = new Date(e.cuando).toLocaleString("es-CL",
      { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
    return e.ok
      ? `<span class="cfg-ok">Última copia: ${esc(cuando)} · se revisó y abre bien${e.ventas != null ? ` (${e.ventas} ventas)` : ""}.</span>`
      : `<span class="cfg-aviso cfg-aviso--mal" style="display:block;margin:0">La última copia falló (${esc(cuando)}): ${esc(e.detalle || "")}</span>`;
  }
  const hoyTxt = () => new Date().toLocaleDateString("sv-SE");
  function listaRespaldosHTML() {
    const rs = (S.D.copias || []).filter((c) => L.respaldoCalza(c, S.rq));
    if (!rs.length) return `<p class="cfg-rvacio">${S.rq ? "No hay ningún respaldo de esa fecha." : "Todavía no hay respaldos en esta caja."}</p>`;
    return rs.map((r) => `<div class="cfg-rfila"><span><b>${esc(L.etiquetaRespaldo(r))}</b><small>${esc(r.archivo)} · ${r.tamano_kb >= 1024 ? (r.tamano_kb / 1024).toFixed(1).replace(".", ",") + " MB" : r.tamano_kb + " KB"} · ${r.abre ? conMiles(r.ventas) + " ventas · se abre bien ✓" : "no se pudo abrir"}</small></span>
      <button type="button" class="i-btn i-btn--aviso" data-c-restaurar="${esc(r.archivo)}"${r.abre ? "" : " disabled"}>Restaurar</button></div>`).join("");
  }
  function secRespaldos() {
    const A = AJUSTES, info = S.D.info || {}, vuelta = S.D.vuelta, m = S.D.mudanza;
    const piloto = A.canal_actualizaciones === "piloto";
    const hay = !!(info.ok && info.hay_nueva);
    const ultima = (S.D.copias || []).find((c) => c.tipo === "diario");
    const exp = S.D.export || { desde: hoyTxt().slice(0, 8) + "01", hasta: hoyTxt() };
    S.D.export = exp;
    const mudanza = m && m.estado === "hecha" ? `<div class="cfg-aviso cfg-aviso--ok" data-aj="r-mudanza">${lineaDeMudanza(m).replace(/<\/?p[^>]*>/g, "")}
        ${m.aviso_visto ? "" : `<div class="cfg-fila" style="margin-top:8px"><button type="button" class="i-btn" data-c-act="mudanzavista">Entendido</button></div>`}</div>` : "";
    return `${mudanza}
    <div class="cfg-card">
      <h3 class="cfg-card__t">Respaldos</h3>
      ${aj("r-ahora", "Respaldo de las ventas", `Cada vez que se abre la caja y al cerrarla se guarda una copia sola. ${ultima ? `La última es del ${esc(L.etiquetaRespaldo(ultima))}: ${ultima.abre ? `abre bien (${conMiles(ultima.ventas)} ventas)` : "no se pudo abrir"}.` : "Todavía no hay ninguna."}`,
        `<button type="button" class="i-btn i-btn--prin" data-c-act="respaldar" id="cfgRespaldar">Respaldar ahora</button>`)}
      ${aj("r-afuera", "Copia de afuera", "Cada respaldo se copia también a esta carpeta. Conviene una que se sincronice sola con la nube (OneDrive, Google Drive, Dropbox) o un pendrive: si el disco de este computador se muere, o se roban el computador, las ventas quedan ahí.",
        `<div style="width:100%"><input class="cfg-in" data-c-in="afuera" id="cfgAfuera" value="${esc(A.respaldo_afuera || "")}" placeholder="Una carpeta de OneDrive, Google Drive o un pendrive">
          ${(S.D.lugares || []).length ? `<div class="cfg-fila" style="margin-top:8px">En este computador hay: ${(S.D.lugares || []).map((l) => `<button type="button" class="i-chip" data-c-lugar="${esc(l.ruta)}" title="${esc(l.ruta)}">${esc(l.nombre)}</button>`).join("")}</div>` : ""}
          <div class="cfg-estado" id="cfgAfueraEst">${estadoAfueraHTML(A.respaldo_afuera_estado)}</div></div>`, { cls: "cfg-aj--col" })}
      ${aj("r-export", "Descargar para el contador", "Dos planillas: las ventas y el detalle de cada una, del período que elijas.",
        `<div class="cfg-fila" style="justify-content:flex-end"><label class="cfg-fila" style="gap:6px">Desde <input class="cfg-in" type="date" data-c-in="exp.desde" value="${exp.desde}" style="width:160px"></label>
          <label class="cfg-fila" style="gap:6px">Hasta <input class="cfg-in" type="date" data-c-in="exp.hasta" value="${exp.hasta}" style="width:160px"></label>
          <button type="button" class="i-btn" data-c-act="exportar">${IC.baja} Descargar</button></div>`, { cls: "cfg-aj--col" })}
    </div>
    <div class="cfg-card">
      <h3 class="cfg-card__t">Versión del programa</h3>
      ${aj("r-version", `Gespoint v${esc(info.actual || (INFO_VERSION && INFO_VERSION.actual) || "")}${info.actual_nombre ? " · " + esc(info.actual_nombre) : ""}`,
        hay ? `<b>Hay una versión nueva: v${esc(info.disponible)}${info.disponible_nombre ? " · " + esc(info.disponible_nombre) : ""}.</b> Se cambia solo el programa; tus ventas, precios y respaldos quedan intactos. La caja se reinicia sola.`
          : info.ok === false ? `No pude revisar si hay una versión nueva. ${esc(info.error || "Puede ser que no haya internet.")}`
            : `Estás al día. <span id="cfgVerEst">${esc(S.D.verEst || "")}</span>`,
        `<button type="button" class="i-btn" data-c-act="novedades">Qué trae cada versión</button>${hay ? `<button type="button" class="i-btn i-btn--prin" data-c-act="actualizar2">Actualizar ahora</button>` : `<button type="button" class="i-btn" data-c-act="buscaract" id="cfgBuscarAct">Buscar actualizaciones</button>`}`)}
      ${aj("r-canal", "Qué versiones recibir", "Una versión nueva llega primero a un local de confianza y, si anda bien, días después a todos.",
        radios("canal", [["estable", "Las versiones ya probadas", "Recomendado."], ["piloto", "Las nuevas, antes que nadie", "Pueden traer algún detalle por pulir."]], piloto ? "piloto" : "estable"), { cls: "cfg-aj--col" })}
      ${aj("r-diag", "Si algo falla", "Baja un archivo con el registro de errores y el estado de la caja —sin tu PIN ni tus claves— y mándalo por WhatsApp a soporte.",
        `<button type="button" class="i-btn" data-c-act="diagnostico">${IC.baja} Descargar diagnóstico</button>`)}
    </div>
    <div class="cfg-peligro" data-aj="r-peligro">
      <h3 class="cfg-card__t">${IC.alerta} Cosas delicadas</h3>
      <p class="cfg-card__nota">Estas dos acciones cambian el programa o las ventas de la caja. Antes de hacerlas te vamos a pedir confirmación.</p>
      ${aj("r-restaurar", "Restaurar un respaldo", "Vuelve la caja a como estaba en un respaldo. Antes de hacerlo se guarda una copia de lo de hoy, pero las ventas hechas después de esa fecha no van a estar.",
        `<div style="width:100%"><div class="cfg-rbusca">${buscadorHTML("cfgRespBusca", "Buscar un respaldo: lunes, 2 de octubre, 09-27…", S.rq)}</div><div class="cfg-rlista" id="cfgRespLista">${listaRespaldosHTML()}</div></div>`, { cls: "cfg-aj--col" })}
      ${aj("r-volver", "Volver a la versión anterior", vuelta && vuelta.disponible ? `Deshace la última actualización y vuelve a la v${esc(vuelta.version)}. Tus ventas, precios y respaldos no se tocan.` : "No hay una versión anterior a la que volver.",
        `<button type="button" class="i-btn i-btn--aviso" data-c-act="volver"${vuelta && vuelta.disponible ? "" : " disabled"}>Volver a la v${esc(vuelta && vuelta.disponible ? vuelta.version : "—")}</button>`)}
    </div>`;
  }

  /* ----- las guías (se leen sin PIN) ----- */
  function guiasHTML() {
    return `<div class="panel--ayuda"><div class="ayuda-cabecera"><div><h3>Guías</h3>
      <p class="ayuda" style="margin:0">Cómo se hace cada cosa, explicado paso a paso. Se puede leer de pie, con el local abierto.</p></div></div>
      <div class="ayuda-cuerpo"><nav class="ayuda-lista" id="listaGuias"></nav><article class="ayuda-texto" id="textoGuia"></article></div></div>`;
  }
  function secGuias() { return `<div class="cfg-guias" style="padding:0">${guiasHTML()}</div>`; }

  const SEC = { local: secLocal, equipo: secEquipo, cobro: secCobro, impresora: secImpresora, pantallas: secPantallas, caja: secCaja, respaldos: secRespaldos, guias: secGuias };
  function alPintar(sec) {
    if (sec === "guias") pintarGuias();
  }

  /* ==========================================================
     DIÁLOGOS
     ========================================================== */
  let alCerrarDlg = null;
  function abrirDlg(clase, html, tipo, alCerrar) {
    alCerrarDlg = alCerrar || null;
    dlgEl.className = "dialogo i-dlg " + clase;
    dlgEl.innerHTML = html;
    capa.classList.add("is-on");
    S.dlg = { tipo };
    return dlgEl;
  }
  function cerrarDlg() {
    capa.classList.remove("is-on");
    dlgEl.innerHTML = "";
    S.dlg = null;
    const f = alCerrarDlg;
    alCerrarDlg = null;
    if (f) f();
  }
  const cab = (t, s) => `<header class="i-cab"><div><h2>${t}</h2>${s ? `<p>${s}</p>` : ""}</div><button type="button" class="i-cerrar" data-c-x aria-label="Cerrar">${IC.cierra}</button></header>`;
  const pie = (...b) => `<footer class="dialogo__pie">${b.join("")}</footer>`;
  const dlgSimple = (tipo, titulo, cuerpo, botones) =>
    abrirDlg("i-dlg--chico", `${cab(titulo)}<div class="i-cuerpo"><p class="cfg-texto">${cuerpo}</p></div>${pie(...botones)}`, tipo);

  /* ----- una persona ----- */
  let P = null;
  const COLORES_BASE = ["#C9552B", "#4E7C5B", "#3E6E8E", "#B5892E", "#8C4A6B", "#8A5A34"];
  const colores = () => (S.D.permisos && S.D.permisos.colores) || COLORES_BASE;
  const rolPermisos = (rol) => ((S.D.permisos && S.D.permisos.roles) || {})[rol] || [];
  const ROL_TXT = { dueno: "Dueño", cajero: "Cajero" };
  function abrirPersona(id) {
    if (id === "nuevo") {
      const hay = (S.D.usuarios || []).filter((u) => u.activo).length;
      P = { nuevo: true, vista: "form", pinBuf: "", q: "",
        u: { id: 0, nombre: "", rol: "cajero", color: colores()[hay % colores().length], activo: true, orden: 0, pinNuevo: "" },
        custom: false, sel: new Set(rolPermisos("cajero")) };
    } else {
      const u = (S.D.usuarios || []).find((x) => x.id === Number(id));
      if (!u) return;
      const propios = u.permisos ? u.permisos.split(",").map((s) => s.trim()).filter(Boolean) : [];
      P = { nuevo: false, vista: "form", pinBuf: "", q: "", u: { ...u, pinNuevo: "" },
        custom: propios.length > 0, sel: new Set(propios.length ? propios : rolPermisos(u.rol)) };
    }
    pintarPersona(true);
  }
  function permisosString() {
    if (!P.custom) return "";
    const orden = ((S.D.permisos && S.D.permisos.catalogo) || []).map((p) => p.clave);
    return orden.filter((k) => P.sel.has(k)).join(",");
  }
  function permisoFilas() {
    const yo = S.user && P.u.id && P.u.id === S.user.id;
    const grupos = L.permisosAgrupados((S.D.permisos || {}).catalogo, P.q);
    const base = P.custom ? P.sel : new Set(rolPermisos(P.u.rol));
    return grupos.map(([g, cs]) => `<div class="cfg-pgrupo">${esc(g)}</div>` + cs.map((p) => {
      const bloquea = !P.custom || (yo && p.clave === "usuarios");
      return `<button type="button" class="cfg-perm${base.has(p.clave) ? " is-on" : ""}" role="checkbox" aria-checked="${base.has(p.clave)}" data-c-perm="${p.clave}"${bloquea ? " disabled" : ""}><i></i><span>${esc(p.nombre)}</span>${yo && p.clave === "usuarios" ? "<small>lo necesitas</small>" : ""}</button>`;
    }).join("")).join("") || `<p class="cfg-rvacio">No hay ningún permiso con ese nombre.</p>`;
  }
  function pintarPersona(nueva) {
    const u = P.u;
    if (P.vista === "pin") {
      const teclas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "c", "0", "x"].map((k) =>
        k === "x" ? `<button type="button" class="teclado__t teclado__t--acc" data-c-dpk="x" aria-label="Borrar">${IC.borrar}</button>`
          : k === "c" ? `<button type="button" class="teclado__t teclado__t--acc" data-c-dpk="c" aria-label="Limpiar">C</button>`
            : `<button type="button" class="teclado__t" data-c-dpk="${k}">${k}</button>`).join("");
      abrirDlg("i-dlg--chico", `${cab(P.nuevo ? "PIN para " + esc(u.nombre || "la persona nueva") : "PIN nuevo de " + esc(u.nombre), "4 números. Con él entra a la caja.")}
        <div class="i-cuerpo"><div class="cfg-pinpad">
          <div class="pin-puntos">${[0, 1, 2, 3].map((i) => `<i class="pin-punto${i < P.pinBuf.length ? " is-on" : ""}"></i>`).join("")}</div>
          <div class="pin-msg" id="cfgPinMsgP" role="alert"></div>
          <div class="pin-teclas">${teclas}</div></div></div>
        ${pie(`<button type="button" class="i-btn" data-c-d="pin-cancelar">Cancelar</button>`)}`, "persona");
      return;
    }
    const yo = S.user && u.id && u.id === S.user.id;
    const html = `${cab(P.nuevo ? "Agregar a alguien" : esc(u.nombre), P.nuevo ? "Va a poder entrar a la caja con su PIN." : esc(ROL_TXT[u.rol] || u.rol) + (u.activo ? "" : " · ya no entra a la caja"))}
      <div class="i-cuerpo"><div class="cfg-persona">
        <div class="cfg-persona__izq">
          <label class="cfg-campo"><span>Nombre</span><input id="cfgPNombre" class="cfg-in" maxlength="30" value="${esc(u.nombre)}" placeholder="Cómo se llama" autocomplete="off"></label>
          <div class="cfg-campo"><span>Color</span><div class="cfg-colores">${colores().map((c) => `<button type="button" class="cfg-col${String(u.color || "").toLowerCase() === c.toLowerCase() ? " is-on" : ""}" style="--k:${c}" data-c-color="${c}" aria-label="Color ${c}"></button>`).join("")}</div></div>
          <div class="cfg-campo"><span>PIN</span><div class="cfg-pinfila"><b>${(!P.nuevo || u.pinNuevo) ? "••••" : "—"}</b><button type="button" class="i-btn" data-c-d="pin">${(!P.nuevo || u.pinNuevo) ? "Cambiar PIN" : "Elegir PIN"}</button></div></div>
          <div class="cfg-campo"><span>¿Qué rol tiene?</span>${seg("prol", [["cajero", "Cajero"], ["dueno", "Dueño"]], u.rol)}</div>
          ${P.nuevo ? "" : `<div class="cfg-zona"><p><b>Zona delicada.</b> ${u.activo ? "Si lo sacas de la caja deja de aparecer en la pantalla de entrada, pero sus ventas y sus turnos se conservan." : "Ahora no aparece en la pantalla de entrada."}</p>
            ${u.activo ? `<button type="button" class="i-btn i-btn--aviso" data-c-d="sacar"${yo ? " disabled" : ""}>Sacar de la caja</button>${yo ? "<p>No puedes sacarte a ti mismo.</p>" : ""}`
              : `<button type="button" class="i-btn" data-c-d="revivir">Dejarlo entrar de nuevo</button>`}</div>`}
        </div>
        <div class="cfg-persona__der">
          <div class="cfg-campo"><span>Permisos de esta persona</span>
            <div class="cfg-aj cfg-aj--sw" style="padding:6px 0;min-height:56px;border:0" data-c-dsw="heredar"><div class="cfg-aj__t"><b>Usar los permisos de su rol</b><small>${u.rol === "dueno" ? "El dueño puede todo." : "Vende, cobra y cuadra su caja."}</small></div><div class="cfg-aj__c">${sw("x", !P.custom, "Usar los permisos de su rol")}</div></div>
            <div class="cfg-fila" style="margin:2px 0 6px"><button type="button" class="i-btn" data-c-d="solovender">Que solo venda</button><small style="color:var(--suave);font-size:12.5px">Abre la caja, vende y cierra su caja.</small></div>
          </div>
          <div class="cfg-pbusca">${buscadorHTML("cfgPermBusca", "Buscar un permiso…", P.q)}</div>
          <div id="cfgPermisos">${permisoFilas()}</div>
          ${yo ? `<p class="cfg-card__nota">No puedes quitarte «Crear y editar personas»: lo necesitas para administrar los permisos del equipo.</p>` : ""}
        </div>
      </div></div>
      ${pie(`<span class="cfg-dlg-ok" id="cfgDlgOk">${dlgOk ? "Guardado ✓" : ""}</span>`, P.nuevo
        ? `<button type="button" class="i-btn" data-c-d="cerrar">Cancelar</button><button type="button" class="i-btn i-btn--prin" data-c-d="agregar" id="cfgAgregar">Agregar a la caja</button>`
        : `<button type="button" class="i-btn i-btn--prin" data-c-d="cerrar">Listo</button>`)}`;
    const previo = S.dlg && S.dlg.tipo === "persona" ? dlgEl.querySelector(".i-cuerpo") : null;
    const y = previo ? previo.scrollTop : 0;
    if (nueva || !S.dlg || S.dlg.tipo !== "persona") abrirDlg("i-dlg--persona", html, "persona");
    else {
      dlgEl.className = "dialogo i-dlg i-dlg--persona";
      dlgEl.innerHTML = html;
      const cu = dlgEl.querySelector(".i-cuerpo"); if (cu) cu.scrollTop = y;
    }
    actualizarAgregar();
  }
  function actualizarAgregar() {
    const b = el("cfgAgregar");
    if (b && P) b.disabled = !P.u.nombre.trim() || P.u.pinNuevo.length < 4;
  }
  async function cargarUsuarios() {
    S.D.usuarios = await capi("/usuarios");
  }
  /* Guarda a la persona que se está editando (la que ya existe). */
  async function guardarPersona(extra) {
    const u = P.u;
    if (P.nuevo) return true;
    if (!u.nombre.trim()) return false;
    const cuerpo = { nombre: u.nombre.trim(), rol: u.rol, permisos: permisosString(), activo: u.activo, color: u.color || "", orden: u.orden || 0, ...(extra || {}) };
    try {
      const r = await capi(`/usuarios/${u.id}`, { method: "PUT", body: json(cuerpo) });
      const i = (S.D.usuarios || []).findIndex((x) => x.id === u.id);
      if (i >= 0) S.D.usuarios[i] = r;
      u.nombre = r.nombre; u.rol = r.rol; u.color = r.color; u.activo = r.activo;
      guardado();
      // Cambió el nombre o el rol de quien está en la caja: la barra de arriba se actualiza.
      if (SESION && SESION.id === u.id) cargarSesion();
      return true;
    } catch (e) {
      avisar(e.message, true);
      // Volver a lo que tiene guardado: la pantalla no puede quedar mostrando algo que no es.
      try { await cargarUsuarios(); } catch (x) { /* sigue */ }
      const real = (S.D.usuarios || []).find((x) => x.id === u.id);
      if (real) {
        const propios = real.permisos ? real.permisos.split(",").filter(Boolean) : [];
        P.u = { ...real, pinNuevo: "" }; P.custom = propios.length > 0; P.sel = new Set(propios.length ? propios : rolPermisos(real.rol));
      }
      pintarPersona();
      return false;
    }
  }
  function clickPersona(e) {
    const t = e.target;
    const col = t.closest("[data-c-color]");
    if (col) { P.u.color = col.dataset.cColor; guardarPersona(); pintarPersona(); return; }
    const rol = t.closest("[data-c-seg='prol']");
    if (rol) {
      P.u.rol = rol.dataset.v;
      if (!P.custom) P.sel = new Set(rolPermisos(P.u.rol));
      guardarPersona(); pintarPersona(); return;
    }
    const per = t.closest("[data-c-perm]");
    if (per) {
      if (per.disabled) return;
      const k = per.dataset.cPerm;
      if (P.sel.has(k)) { if (P.sel.size <= 1) return avisar("Marca al menos un permiso o activa «Usar los permisos de su rol».", true); P.sel.delete(k); } else P.sel.add(k);
      guardarPersona(); const caja_ = el("cfgPermisos"); if (caja_) caja_.innerHTML = permisoFilas(); return;
    }
    if (t.closest("[data-c-dsw='heredar']")) {
      P.custom = !P.custom;
      if (P.custom) P.sel = new Set(rolPermisos(P.u.rol));
      guardarPersona(); pintarPersona(); return;
    }
    const x = t.closest("[data-c-lq]");
    if (x && x.dataset.cLq === "cfgPermBusca") { P.q = ""; el("cfgPermBusca").value = ""; el("cfgPermisos").innerHTML = permisoFilas(); return; }
    const pk = t.closest("[data-c-dpk]");
    if (pk) {
      const k = pk.dataset.cDpk;
      if (k === "x") P.pinBuf = P.pinBuf.slice(0, -1); else if (k === "c") P.pinBuf = ""; else if (P.pinBuf.length < 4) P.pinBuf += k;
      $$c(".pin-punto", dlgEl).forEach((p, i) => p.classList.toggle("is-on", i < P.pinBuf.length));
      if (P.pinBuf.length === 4) {
        const pin = P.pinBuf;
        P.pinBuf = "";
        if (P.nuevo) { P.u.pinNuevo = pin; P.vista = "form"; setTimeout(() => pintarPersona(), 120); }
        else {
          guardarPersona({ pin }).then((ok) => { if (ok) avisar("PIN cambiado"); P.vista = "form"; pintarPersona(); });
        }
      }
      return;
    }
    const d = t.closest("[data-c-d]");
    if (!d) return;
    switch (d.dataset.cD) {
      case "pin": P.vista = "pin"; P.pinBuf = ""; pintarPersona(true); break;
      case "pin-cancelar": P.vista = "form"; pintarPersona(true); break;
      case "solovender": P.custom = true; P.sel = new Set(L.SOLO_VENDER); guardarPersona(); pintarPersona(); break;
      case "cerrar": cerrarDlg(); if (visible() && S.sec === "equipo") pintarSeccion(); break;
      case "agregar": agregarPersona(); break;
      case "sacar": confirmarSacar(); break;
      case "revivir": P.u.activo = true; guardarPersona().then((ok) => { if (ok) avisar(P.u.nombre + " vuelve a entrar a la caja"); pintarPersona(); }); break;
      case "sacar-si": sacarPersona(); break;
      case "sacar-no": pintarPersona(true); break;
    }
  }
  async function agregarPersona() {
    const u = P.u;
    try {
      await capi("/usuarios", { method: "POST", body: json({ nombre: u.nombre.trim(), pin: u.pinNuevo, rol: u.rol, permisos: permisosString(), color: u.color }) });
      await cargarUsuarios();
      cerrarDlg();
      if (visible() && S.sec === "equipo") pintarSeccion();
      guardado();
      avisar(u.nombre.trim() + " ya puede entrar a la caja");
    } catch (e) { avisar(e.message, true); }
  }
  function confirmarSacar() {
    const u = P.u;
    abrirDlg("i-dlg--chico", `${cab("¿Sacar a " + esc(u.nombre) + " de la caja?")}
      <div class="i-cuerpo"><p class="cfg-texto">Deja de aparecer en la pantalla de entrada y no puede usar su PIN. <b>Sus ventas y sus turnos se conservan</b>: los cierres siguen cuadrando. Si cambias de opinión, lo dejas entrar de nuevo desde su ficha.</p></div>
      ${pie(`<button type="button" class="i-btn" data-c-d="sacar-no">No, volver</button>`, `<button type="button" class="i-btn i-btn--rojo" data-c-d="sacar-si">Sí, sacar de la caja</button>`)}`, "persona");
  }
  async function sacarPersona() {
    const u = P.u;
    try {
      const r = await capi(`/usuarios/${u.id}`, { method: "DELETE" });
      await cargarUsuarios();
      cerrarDlg();
      if (visible() && S.sec === "equipo") pintarSeccion();
      guardado();
      avisar((r && r.aviso) || (u.nombre + " ya no entra a la caja. Sus ventas se conservan."));
    } catch (e) { avisar(e.message, true); pintarPersona(true); }
  }

  /* ----- un televisor ----- */
  let TV = null;
  const MODOS_TV = Object.entries(L.MODO_TXT);
  function pintarTv(nueva) {
    const tv = TV;
    const num = (k, t) => `<label class="cfg-campo"><span>${t}</span><span class="cfg-num" style="width:100%"><input class="cfg-in" data-c-tvt="${k}" inputmode="numeric" value="${tv.t[k]}"><i>seg</i></span></label>`;
    const url = L.urlTv(tv, baseDeLaCaja());
    const html = `${cab(esc(tv.nombre), "Todo se guarda solo.")}
      <div class="i-cuerpo">
        <label class="cfg-campo" style="margin-bottom:12px"><span>Nombre del televisor (solo para ti)</span><input class="cfg-in" id="cfgTvNombre" maxlength="30" value="${esc(tv.nombre)}" autocomplete="off"></label>
        <div class="cfg-aj cfg-aj--col" style="padding-top:2px"><div class="cfg-aj__t"><b>Qué muestra este televisor</b><small>Con dos televisores, pon uno en «Solo la vitrina» y el otro en «Solo la carta».</small></div>
          <div class="cfg-aj__c"><div class="cfg-radios" style="flex-direction:row;flex-wrap:wrap">${MODOS_TV.map(([v, t]) => `<button type="button" class="cfg-radio${tv.modo === v ? " is-on" : ""}" data-c-tvset="modo" data-v="${v}" style="flex:1 1 170px;width:auto"><i></i><span>${t}</span></button>`).join("")}</div></div></div>
        <div class="cfg-aj cfg-aj--col"><div class="cfg-aj__t"><b>Cómo está puesto el televisor</b><small>El diseño se reordena solo: parado, los productos quedan uno bajo otro.</small></div>
          <div class="cfg-aj__c">${seg("tv", [["horizontal", "Acostado (horizontal)"], ["vertical", "Parado (vertical)"]], tv.orient).replace(/data-c-seg="tv"/g, 'data-c-tvset="orient"')}</div></div>
        <div class="cfg-aj cfg-aj--col"><div class="cfg-aj__t"><b>Cuánto se queda cada cosa</b><small>Antes de cambiar sola, en segundos (entre 5 y 180).</small></div>
          <div class="cfg-aj__c" style="width:100%"><div class="cfg-3cols" style="width:100%">${num("vitrina", "La vitrina")}${num("cat", "Cada categoría")}${num("reco", "El combo")}</div></div></div>
        <div class="cfg-aj cfg-aj--col"><div class="cfg-aj__t"><b>Decoración de Fiestas Patrias</b><small>En Automática se prende sola del 12 al 20 de septiembre.</small></div>
          <div class="cfg-aj__c">${seg("tv", [["auto", "Automática"], ["siempre", "Prendida"], ["nunca", "Apagada"]], tv.fiestas).replace(/data-c-seg="tv"/g, 'data-c-tvset="fiestas"')}</div></div>
        <div class="cfg-aj cfg-aj--sw" data-c-tvsw="suave"><div class="cfg-aj__t"><b>Modo suave</b><small>Para un televisor lento: congela vapor y burbujas y deja solo las transiciones.</small></div><div class="cfg-aj__c">${sw("x", tv.suave, "Modo suave")}</div></div>
        <div class="cfg-aj"><div class="cfg-aj__t"><b>Ajustar al televisor</b><small>Si el borde del televisor se come la pantalla, achica el contenido.</small></div>
          <div class="cfg-aj__c"><button type="button" class="i-btn" data-c-tvmargen="-1" aria-label="Achicar">−</button><b style="min-width:44px;text-align:center;font-size:17px">${tv.margen}%</b><button type="button" class="i-btn" data-c-tvmargen="1" aria-label="Agrandar">+</button></div></div>
        <div class="cfg-aj cfg-aj--sw" data-c-tvsw="simple"><div class="cfg-aj__t"><b>Usar la versión simple</b><small>Si el televisor es muy viejo y muestra la pantalla en blanco con letras negras. Es la misma carta, más sobria.</small></div><div class="cfg-aj__c">${sw("x", tv.simple, "Versión simple")}</div></div>
        <div class="cfg-aj cfg-aj--col" style="border-bottom:0"><div class="cfg-aj__t"><b>Dirección de este televisor</b><small>Escríbela en el navegador del televisor. Las de siempre (<b>?p=1</b>, <b>?p=2</b>, <b>?tv=1</b>) siguen andando; si la dirección trae <b>?p=1</b> o <b>?p=2</b>, esa manda sobre lo de arriba.</small></div>
          <div class="cfg-aj__c" style="width:100%"><div class="cfg-url" style="width:100%"><code>${esc(url)}</code><button type="button" class="i-btn" data-c-copiar="${esc(url)}">${IC.copia} Copiar</button></div></div></div>
      </div>
      ${pie(`<button type="button" class="i-btn i-btn--borrar" data-c-tvd="quitar">Quitar este televisor</button>`, `<span class="cfg-dlg-ok" id="cfgDlgOk">${dlgOk ? "Guardado ✓" : ""}</span>`, `<button type="button" class="i-btn i-btn--prin" data-c-tvd="listo">Listo</button>`)}`;
    const previo = S.dlg && S.dlg.tipo === "tv" ? dlgEl.querySelector(".i-cuerpo") : null;
    const y = previo ? previo.scrollTop : 0;
    if (nueva || !S.dlg || S.dlg.tipo !== "tv") abrirDlg("i-dlg--ancho", html, "tv");
    else { dlgEl.innerHTML = html; const cu = dlgEl.querySelector(".i-cuerpo"); if (cu) cu.scrollTop = y; }
  }
  async function guardarTv(cambios) {
    try {
      const r = await capi(`/config/televisores/${TV.id}`, { method: "PUT", body: json(cambios) });
      TV = r;
      const i = (S.D.tvs || []).findIndex((x) => x.id === r.id);
      if (i >= 0) S.D.tvs[i] = r;
      guardado();
      return true;
    } catch (e) { avisar(e.message, true); return false; }
  }
  function clickTv(e) {
    const t = e.target, tv = TV;
    const s = t.closest("[data-c-tvset]");
    if (s) { guardarTv({ [s.dataset.cTvset]: s.dataset.v }).then(() => pintarTv()); return; }
    const w = t.closest("[data-c-tvsw]");
    if (w) { guardarTv({ [w.dataset.cTvsw]: !tv[w.dataset.cTvsw] }).then(() => pintarTv()); return; }
    const m = t.closest("[data-c-tvmargen]");
    if (m) { guardarTv({ margen: Math.max(0, Math.min(15, tv.margen + Number(m.dataset.cTvmargen))) }).then(() => pintarTv()); return; }
    const c = t.closest("[data-c-copiar]");
    if (c) return copiar(c.dataset.cCopiar);
    const d = t.closest("[data-c-tvd]");
    if (!d) return;
    if (d.dataset.cTvd === "listo") { cerrarDlg(); if (visible() && S.sec === "pantallas") pintarSeccion(); }
    if (d.dataset.cTvd === "quitar") {
      abrirDlg("i-dlg--chico", `${cab("¿Quitar «" + esc(tv.nombre) + "»?")}
        <div class="i-cuerpo"><p class="cfg-texto">Se borra de esta lista. <b>El televisor sigue encendido y mostrando la carta</b> mientras no cierres su ventana; solo dejas de verlo acá. Puedes volver a agregarlo cuando quieras.</p></div>
        ${pie(`<button type="button" class="i-btn" data-c-tvd="no">No, volver</button>`, `<button type="button" class="i-btn i-btn--rojo" data-c-tvd="si">Sí, quitarlo</button>`)}`, "tvq");
    }
    if (d.dataset.cTvd === "no") pintarTv(true);
    if (d.dataset.cTvd === "si") {
      capi(`/config/televisores/${tv.id}`, { method: "DELETE" }).then(() => {
        S.D.tvs = (S.D.tvs || []).filter((x) => x.id !== tv.id);
        cerrarDlg(); if (visible() && S.sec === "pantallas") pintarSeccion();
        guardado(); avisar("Televisor quitado de la lista");
      }).catch((err) => avisar(err.message, true));
    }
  }
  function copiar(txt) {
    const listo = () => avisar("Dirección copiada");
    try {
      if (navigator.clipboard) { navigator.clipboard.writeText(txt).then(listo, () => avisar("Selecciona la dirección y cópiala con Ctrl+C")); return; }
    } catch (e) { /* sin portapapeles */ }
    avisar("Selecciona la dirección y cópiala con Ctrl+C");
  }

  /* ----- restaurar un respaldo (lo más delicado) ----- */
  let RS = null;
  async function dlgRestaurar(archivo) {
    let v;
    try { v = await capi("/config/respaldos/" + encodeURIComponent(archivo)); }
    catch (e) { return avisar(e.message, true); }
    const copia = (S.D.copias || []).find((c) => c.archivo === archivo) || { archivo, fecha: "", hora: "", tipo: "diario" };
    if (!v.ok) {
      return dlgSimple("simple", "Ese respaldo no se puede restaurar", esc(v.detalle || "No se pudo revisar."),
        [`<button type="button" class="i-btn i-btn--prin" data-c-sd="cerrar">Entendido</button>`]);
    }
    RS = { archivo, perderia: v.perderia, ok: false, enviando: false, v, copia };
    pintarRestaurar();
  }
  function pintarRestaurar() {
    const { v, copia } = RS, perd = RS.perderia;
    const etiqueta = L.etiquetaRespaldo(copia);
    const abierta = v.caja_abierta;
    abrirDlg("i-dlg--medio", `${cab("Restaurar el respaldo " + esc(etiqueta), "Esto cambia las ventas de la caja.")}
      <div class="i-cuerpo">
        <div class="cfg-aviso cfg-aviso--mal" style="margin-top:0">${perd > 0
          ? `<b>Se van a perder ${conMiles(perd)} venta${perd === 1 ? "" : "s"}.</b> La caja vuelve a como estaba en ese respaldo: las ventas, los cierres y los cambios hechos después de eso no van a estar.`
          : `<b>No se pierde ninguna venta:</b> ese respaldo tiene ${conMiles(v.ventas)} y la caja tiene ${conMiles(v.ventas_hoy)}. Igual, la caja vuelve a como estaba entonces (cierres y cambios incluidos).`}</div>
        <dl class="cfg-datos"><dt>Ventas hoy</dt><dd>${conMiles(v.ventas_hoy)}</dd><dt>Ventas en este respaldo</dt><dd>${conMiles(v.ventas)}</dd><dt>Archivo</dt><dd>${esc(archivo_(v.archivo))}</dd></dl>
        <p class="cfg-suave">Antes de restaurar se guarda la base de hoy como <b style="color:var(--tinta)">antes-de-restaurar-&lt;fecha y hora&gt;.db</b>, y esa copia no se borra sola: con ella se puede deshacer. ${abierta ? `Hay una caja abierta (${esc(abierta.quien)}): si puedes, ciérrala antes. ` : ""}La caja se reinicia sola.</p>
        <button type="button" class="cfg-confirma${RS.ok ? " is-on" : ""}" data-c-rok role="checkbox" aria-checked="${RS.ok}"><i></i><span>${esc(L.fraseConfirmarRestaurar(perd))}</span></button>
        <div class="cfg-estado cfg-estado--mal" id="cfgRestMsg" role="alert"></div>
      </div>
      ${pie(`<button type="button" class="i-btn" data-c-rd="no">Cancelar</button>`, `<button type="button" class="i-btn i-btn--rojo" data-c-rd="si"${RS.ok && !RS.enviando ? "" : " disabled"}>Restaurar este respaldo</button>`)}`, "restaurar");
  }
  const archivo_ = (a) => a;
  async function restaurarAhora() {
    if (!RS || !RS.ok || RS.enviando) return;
    RS.enviando = true;
    pintarRestaurar();
    try {
      const r = await capi("/config/restaurar", { method: "POST", espera: 0,
        body: json({ archivo: RS.archivo, ventas_que_se_pierden: RS.perderia }) });
      abrirDlg("i-dlg--chico", `${cab("Restaurando…")}<div class="i-cuerpo"><p class="cfg-texto">Se restauró el respaldo (${conMiles(r.ventas)} ventas). La base de antes quedó guardada como <b>${esc(r.guardada || "")}</b>. La caja se está reiniciando: la página se recarga sola en unos segundos.</p></div>`, "reinicio");
      esperarCaja();
    } catch (e) {
      RS.enviando = false;
      pintarRestaurar();
      const m = el("cfgRestMsg"); if (m) m.textContent = e.message;
    }
  }
  /* Espera a que la caja se cierre y vuelva a abrir, y recarga la página. Antes de recargar tiene
     que haberla visto caer (o haber pasado un buen rato): si no, se recargaría contra la caja vieja. */
  async function esperarCaja() {
    const inicio = Date.now();
    let cayo = false;
    await new Promise((r) => setTimeout(r, 2500));
    for (let i = 0; i < 60; i++) {
      try {
        const r = await fetch("/api/v1/salud", { cache: "no-store" });
        if (r.ok && (cayo || Date.now() - inicio > 10000)) { location.reload(); return; }
      } catch (e) { cayo = true; }
      await new Promise((r) => setTimeout(r, 1500));
    }
    abrirDlg("i-dlg--chico", `${cab("Casi listo")}<div class="i-cuerpo"><p class="cfg-texto">El cambio quedó hecho, pero la caja no volvió sola. Cierra esta ventana y vuelve a abrirla con el icono <b>«${esc(NOMBRE_DEL_LOCAL)} - Punto de venta»</b> del escritorio.</p></div>`, "reinicio");
  }

  /* ----- novedades, actualizar, volver ----- */
  async function dlgNovedades() {
    let r;
    try { r = await capi("/novedades"); } catch (e) { return avisar(e.message, true); }
    const lista = (q) => {
      const t = sinTildes(q).trim();
      return r.versiones.filter((v) => !t || sinTildes([v.version, v.nombre, v.fecha, v.novedades].join(" ")).includes(t)).map((v) =>
        `<div class="cfg-ver${v.version === r.actual ? " es-la-tuya" : ""}"><b>v${esc(v.version)} · ${esc(v.nombre)}</b><span>${esc(v.fecha)}${v.version === r.actual ? " · la que tienes" : ""}</span><p>${esc(v.novedades)}</p></div>`).join("")
        || '<p class="cfg-rvacio">Ninguna versión dice eso.</p>';
    };
    abrirDlg("i-dlg--medio", `${cab("Qué trae cada versión", "Tienes la v" + esc(r.actual) + ". De lo más nuevo a lo más viejo.")}
      <div class="i-cuerpo"><div class="cfg-pbusca">${buscadorHTML("cfgVerBusca", "Buscar en las novedades…", "")}</div><div class="cfg-hist" id="cfgHist">${lista("")}</div></div>
      ${pie(`<button type="button" class="i-btn i-btn--prin" data-c-sd="cerrar">Cerrar</button>`)}`, "nov");
    S.dlg.lista = lista;
  }
  function dlgActualizar() {
    const i = S.D.info || {};
    dlgSimple("simple", "Actualizar a la v" + esc(i.disponible || ""),
      `Se cambia solo el programa. Tus ventas, precios y respaldos quedan intactos. <b>La caja se reinicia sola</b> y vuelve en unos segundos: mejor hacerlo cuando no haya una venta en curso.${i.novedades ? `<br><br><span class="cfg-suave">${esc(i.novedades)}</span>` : ""}`,
      [`<button type="button" class="i-btn" data-c-sd="cerrar">Ahora no</button>`, `<button type="button" class="i-btn i-btn--prin" data-c-sd="act-si">Actualizar ahora</button>`]);
  }
  async function instalarVersion() {
    const i = S.D.info || {};
    abrirDlg("i-dlg--chico", `${cab("Actualizando…")}<div class="i-cuerpo"><p class="cfg-texto">Bajando e instalando la versión nueva. No cierres esta ventana.</p></div>`, "reinicio");
    try {
      const r = await capi("/actualizacion", { method: "POST", body: json({ zip: i.zip || "" }) });
      if (!r.ok) throw new Error(r.error || "No se pudo actualizar");
      if (r.sin_cambios) { cerrarDlg(); return avisar(r.aviso); }
      abrirDlg("i-dlg--chico", `${cab("Listo")}<div class="i-cuerpo"><p class="cfg-texto">Se actualizaron ${r.archivos.length} archivos. La caja se está reiniciando: la página se recarga sola en unos segundos.</p></div>`, "reinicio");
      esperarCaja();
    } catch (e) { cerrarDlg(); avisar(e.message, true); }
  }
  async function volverVersion() {
    abrirDlg("i-dlg--chico", `${cab("Volviendo…")}<div class="i-cuerpo"><p class="cfg-texto">Deshaciendo la última actualización. No cierres esta ventana.</p></div>`, "reinicio");
    try {
      const r = await capi("/actualizacion/volver", { method: "POST" });
      if (!r.ok) throw new Error(r.error || "No se pudo volver");
      abrirDlg("i-dlg--chico", `${cab("Volviendo a la v" + esc(r.version))}<div class="i-cuerpo"><p class="cfg-texto">La caja se reinicia sola: la página se recarga en unos segundos. Tus ventas, precios y respaldos no se tocaron.</p></div>`, "reinicio");
      esperarCaja();
    } catch (e) { cerrarDlg(); avisar(e.message, true); }
  }

  /* ==========================================================
     LAS ACCIONES
     ========================================================== */
  function descargar(ruta) {
    // Igual que el resto de la caja (reportes, diagnóstico): una ventana de descarga. Antes se
    // renueva el acceso, para que no se abra una página de error si Config justo se cerró.
    capi("/config/estado").then((r) => {
      if (r && r.activo === false) return salir("Config se cerró. Pide el PIN de nuevo.");
      window.open("/api/v1" + ruta, "_blank");
    }).catch((e) => avisar(e.message, true));
  }
  async function accion(a) {
    const Z = S.D;
    switch (a) {
      case "entrar": return probarPin();
      case "otro": S.msg = null; S.pin = ""; render(); break;
      case "vercaja": S.msg = null; S.pin = ""; verVista("caja"); break;
      case "guias": S.guiasSolas = true; render(); break;
      case "singuias": S.guiasSolas = false; render(); break;
      case "salir": salir("cerrar"); break;
      case "reintentar": S.cargada[S.sec] = false; pintarSeccion(true); break;
      case "descotro": {
        const n = L.porcentajeValido((el("cfgDescOtro") || {}).value);
        if (n == null) return avisar("Escribe un porcentaje entre 1 y 100.", true);
        const lista = L.alternarPorcentaje((AJUSTES.descuentos_rapidos || []).filter((x) => x !== n), n, 6);
        if (lista.length === (AJUSTES.descuentos_rapidos || []).filter((x) => x !== n).length) return avisar("Son como máximo 6 botones de descuento.", true);
        await guardarAjustes({ descuentos_rapidos: lista }); pintarSeccion(); break;
      }
      case "actualizar": cargarImpresoras(); break;
      case "prueba": probarImpresionConfig(); break;
      case "instalar": instalarImpresoraConfig(); break;
      case "balprobar": probarEtiqueta(); break;
      case "balejemplo": {
        const B = balBorrador();
        if (!L.formatoBalanzaValido(formatoDe(B))) return avisar("Primero arregla el formato de arriba.", true);
        B.prueba = ejemploEtiqueta(B);
        const c = el("cfgBalCod"); if (c) c.value = B.prueba;
        probarEtiqueta(); break;
      }
      case "tvnuevo": {
        const n = (Z.tvs || []).length + 1;
        try {
          TV = await capi("/config/televisores", { method: "POST", body: json({ nombre: "Televisor " + n }) });
          Z.tvs = (Z.tvs || []).concat(TV);
          guardado(); pintarSeccion(); pintarTv(true);
        } catch (e) { avisar(e.message, true); }
        break;
      }
      case "cintamas": {
        const t = Z.textos; t.cinta = (t.cinta || []).concat("");
        S.abiertos.add("cinta"); pintarSeccion();
        const ins = $$c("[data-c-cinta]"); if (ins.length) ins[ins.length - 1].focus();
        break;
      }
      case "fuenteprobar": {
        const e = el("cfgFuenteEst");
        const url = (Z.textos.fuente_url || "").trim();
        if (e) e.textContent = url ? "Probando…" : "";
        try {
          const r = await capi("/config/pantallas/probar", { method: "POST", body: json({ url }), espera: 15000 });
          Z.fuenteEst = r.detalle;
        } catch (err) { Z.fuenteEst = err.message; }
        const e2 = el("cfgFuenteEst"); if (e2) e2.textContent = Z.fuenteEst;
        break;
      }
      case "pantbajar": descargar("/config/pantallas/respaldo"); break;
      case "pantsubir": { const f = el("cfgPantArchivo"); if (f) f.click(); break; }
      case "pantreset":
        dlgSimple("simple", "¿Volver a los datos de ejemplo?", "Las pantallas vuelven a mostrar sus textos y avisos de siempre. <b>Lo que escribiste en «Textos de las pantallas», en los avisos y en la carta desde otra dirección se pierde.</b> Los televisores de la lista no cambian.",
          [`<button type="button" class="i-btn" data-c-sd="cerrar">No, volver</button>`, `<button type="button" class="i-btn i-btn--rojo" data-c-sd="pantreset-si">Sí, volver al ejemplo</button>`]);
        break;
      case "completa": await alternarPantallaCompleta(); if (S.sec === "caja") pintarSeccion(); break;
      case "barra": ponerBarra(true); avisar("Barra escondida. Toca «Menú» arriba para volver a verla."); verVista("caja"); break;
      case "sesion":
        if (!puedoIrme()) return avisar("Tienes la caja abierta. Ciérrala antes de salir o de cambiar de usuario: si no, tu turno queda a medias.", true);
        salirDeLaCaja("cambio"); break;
      case "verpin": Z.pinVisible = !Z.pinVisible; pintarSeccion(); break;
      case "nuevopin":
        dlgSimple("simple", "¿Cambiar el PIN de red?", "Los tablets y computadores que ya habían entrado van a tener que escribir el nuevo. Desde este computador no se pide.",
          [`<button type="button" class="i-btn" data-c-sd="cerrar">No, dejarlo</button>`, `<button type="button" class="i-btn i-btn--prin" data-c-sd="pinred-si">Sí, crear uno nuevo</button>`]);
        break;
      case "respaldar": {
        const b = el("cfgRespaldar"); if (b) { b.disabled = true; b.textContent = "Respaldando…"; }
        try {
          const r = await capi("/config/respaldar", { method: "POST" });
          if (!r.ok) throw new Error(r.detalle || "No se pudo respaldar");
          const af = r.afuera;
          avisar(!af || !af.configurado ? "Respaldo hecho en este computador. Falta elegir la carpeta de afuera."
            : af.ok ? "Respaldo hecho y copiado afuera. La copia abre bien." : "La copia de afuera falló: " + (af.detalle || ""), !!(af && af.configurado && !af.ok));
          guardado();
          S.cargada.respaldos = false; cargarSeccion("respaldos");
        } catch (e) { avisar(e.message, true); pintarSeccion(); }
        break;
      }
      case "exportar": {
        const x = Z.export;
        if (!x.desde || !x.hasta) return avisar("Elige las dos fechas.", true);
        const d = x.desde <= x.hasta ? x.desde : x.hasta, h = x.desde <= x.hasta ? x.hasta : x.desde;
        descargar(`/exportar/ventas?desde=${d}&hasta=${h}`);
        setTimeout(() => descargar(`/exportar/detalle?desde=${d}&hasta=${h}`), 500);
        break;
      }
      case "novedades": dlgNovedades(); break;
      case "buscaract": {
        const b = el("cfgBuscarAct"); if (b) b.disabled = true;
        const e = el("cfgVerEst"); if (e) e.textContent = "Buscando…";
        try {
          Z.info = await capi("/actualizacion"); INFO_VERSION = Z.info;
          Z.verEst = Z.info.ok ? "Revisado hace un momento." : "";
          if (Z.info.ok && Z.info.hay_nueva) { cargarVersion(); }
        } catch (err) { Z.verEst = err.message; }
        pintarSeccion(); break;
      }
      case "actualizar2": dlgActualizar(); break;
      case "diagnostico": descargar("/diagnostico"); break;
      case "mudanzavista":
        try { await capi("/mudanza/visto", { method: "POST" }); if (Z.mudanza) Z.mudanza.aviso_visto = true; guardado(); } catch (e) { /* sigue */ }
        pintarSeccion(); break;
      case "volver": {
        const v = Z.vuelta;
        if (!v || !v.disponible) return;
        dlgSimple("simple", "¿Volver a la v" + esc(v.version) + "?", "Se deshace la última actualización. <b>Tus ventas, precios y respaldos no se tocan.</b> La caja se reinicia sola y vuelve en unos segundos.",
          [`<button type="button" class="i-btn" data-c-sd="cerrar">No, quedarme acá</button>`, `<button type="button" class="i-btn i-btn--rojo" data-c-sd="volver-si">Sí, volver a la v${esc(v.version)}</button>`]);
        break;
      }
    }
  }
  async function alternar(path) {
    const A = AJUSTES;
    switch (path) {
      case "inv": await guardarAjustes({ usar_inventario: usarInventario() ? 0 : 1 }, usarInventario() ? "Listo: puedes vender sin llevar inventario" : "Listo: vuelves a llevar inventario"); break;
      case "mixto": await guardarAjustes({ pago_mixto: A.pago_mixto ? 0 : 1 }); break;
      case "propina": await guardarAjustes({ propinas: A.propinas ? 0 : 1 }); break;
      case "solotarjeta": await guardarAjustes({ propina_solo_tarjeta: A.propina_solo_tarjeta ? 0 : 1 }); break;
      case "tactil": {
        const v = A.teclado_en_pantalla ? 0 : 1;
        const r = await guardarAjustes({ teclado_en_pantalla: v }, v ? "Teclado en pantalla prendido" : "Teclado en pantalla apagado");
        if (r && window.Teclado) Teclado.encender(!!v);
        break;
      }
      case "imp.siempre": guardarPrefs({ automatica: !IMPRESION.automatica }); break;
      case "bal.usar": {
        const v = A.usar_balanza ? 0 : 1;
        await guardarAjustes({ usar_balanza: v }, v ? "Balanza prendida: revisa qué imprime la etiqueta y prueba una" : "Balanza apagada: la caja ya no cobra etiquetas");
        break;
      }
    }
    pintarSeccion();
  }
  async function elegir(clave, v) {
    switch (clave) {
      case "redondeo": await guardarAjustes({ redondeo_precio: Number(v) }); break;
      case "imp.tipo": if (guardarPrefs({ tipo: v })) S.D.impEstado = ""; if (v !== "navegador") cargarImpresoras(true); break;
      case "imp.papel": guardarPrefs({ papel: Number(v) }); S.ticketAncho = null; break;
      case "bal.modo": {
        const B = balBorrador(); B.modo = v;
        if (L.formatoBalanzaValido(formatoDe(B))) await guardarFormatoBalanza();
        break;
      }
      case "canal": await guardarAjustes({ canal_actualizaciones: v }, v === "piloto" ? "Vas a recibir las versiones nuevas antes que nadie" : "Vas a recibir solo las versiones ya probadas"); break;
      case "ticket": S.ticketAncho = Number(v); break;
    }
    pintarSeccion();
  }
  async function cambiarMedio(k) {
    const act = (AJUSTES.medios_pago || []).slice();
    const i = act.indexOf(k);
    if (i >= 0) { if (act.length <= 1) return avisar("Tiene que quedar al menos una forma de pago.", true); act.splice(i, 1); } else act.push(k);
    await guardarAjustes({ medios_pago: act });
    pintarSeccion();
  }
  async function cambiarChip(clave, v) {
    const lista = L.alternarPorcentaje(AJUSTES[clave] || [], v, 6);
    if (lista.length === (AJUSTES[clave] || []).length && !(AJUSTES[clave] || []).includes(v)) return avisar("Son como máximo 6 botones.", true);
    await guardarAjustes({ [clave]: lista });
    pintarSeccion();
  }
  async function elegirMargenConfig(n) {
    n = Math.min(95, Math.max(0, n));
    AJUSTES.margen_sugerido = n;
    await guardarAjustes({ margen_sugerido: n });
  }

  /* ==========================================================
     LOS EVENTOS
     ========================================================== */
  function rutValido(v) { return !v.trim() || !!L.rutFormato(v); }
  async function guardarLocalConfig() {
    const l = S.D.local;
    if (!String(l.nombre || "").trim()) return;
    if (!rutValido(l.rut || "")) return;
    try {
      const r = await capi("/local", { method: "PUT", body: json({ nombre: l.nombre.trim(), rut: (l.rut || "").trim(), direccion: (l.direccion || "").trim() }) });
      S.D.local = { ...l, ...r };
      ponerNombreDelLocal(r.nombre);
      guardado();
      const e = $c('[data-c-in="local.rut"]');
      if (e && document.activeElement !== e) e.value = r.rut;
    } catch (e) {
      const er = $c('[data-c-err="rut"]'); if (er) er.textContent = e.message;
      avisar(e.message, true);
    }
  }
  function alEscribir(g) {
    const clave = g.dataset.cIn;
    if (clave === "local.nombre") {
      const mal = !g.value.trim();
      g.classList.toggle("cfg-in--mal", mal);
      const er = $c('[data-c-err="nombre"]'); if (er) er.textContent = mal ? "El local necesita un nombre." : "";
      S.D.local.nombre = g.value; actualizarTicket();
      if (!mal) despues("local", guardarLocalConfig);
    } else if (clave === "local.rut") {
      const ok = rutValido(g.value);
      g.classList.toggle("cfg-in--mal", !ok);
      const er = $c('[data-c-err="rut"]'); if (er) er.textContent = ok ? "" : "Ese RUT no es válido: revisa el dígito verificador.";
      S.D.local.rut = g.value; actualizarTicket();
      if (ok) despues("local", guardarLocalConfig);
    } else if (clave === "local.direccion") {
      S.D.local.direccion = g.value; actualizarTicket(); despues("local", guardarLocalConfig);
    } else if (clave === "ajuste.mensaje_ticket") {
      const v = g.value;
      AJUSTES.mensaje_ticket = v.trim() || "¡Gracias!"; actualizarTicket();
      despues("mensaje", () => guardarAjustes({ mensaje_ticket: v.trim() }));
    } else if (clave === "margen") {
      const n = Math.min(95, Number(String(g.value).replace(/\D/g, "")) || 0);
      AJUSTES.margen_sugerido = n;
      $$c("[data-c-margen]").forEach((b) => b.classList.toggle("is-on", Number(b.dataset.cMargen) === n));
      const ej = el("cfgEjMargen"); if (ej) ej.innerHTML = L.ejemploMargen(n, AJUSTES.redondeo_precio);
      despues("margen", () => guardarAjustes({ margen_sugerido: n }));
    } else if (clave === "afuera") {
      /* se guarda al terminar (change) */
    } else if (clave && clave.startsWith("txt.")) {
      const k = clave.slice(4), t = S.D.textos;
      if (k === "fuente_cada") t[k] = Math.max(1, Math.min(240, Number(String(g.value).replace(/\D/g, "")) || 10));
      else t[k] = g.value;
      despues("textos", guardarTextos);
    } else if (clave === "exp.desde" || clave === "exp.hasta") {
      S.D.export[clave.slice(4)] = g.value;
    }
  }
  function actualizarTicket() {
    const t = el("cfgTicket"); if (t) t.textContent = ticketActual();
  }
  async function guardarTextos() {
    const t = S.D.textos;
    try {
      const r = await capi("/config/pantallas", { method: "PUT", body: json({ ...t, cinta: (t.cinta || []).map((x) => x.trim()).filter(Boolean) }) });
      guardado();
      // Los avisos vacíos que se están escribiendo no se pierden mientras tanto.
      S.D.guardadoTextos = r.textos;
    } catch (e) { avisar(e.message, true); }
  }
  function alEscribirBal(g) {
    const B = balBorrador(), k = g.dataset.cBal, v = g.value;
    if (k === "prueba") { B.prueba = v; return; }
    const num = (x) => (x === "" ? NaN : Number(x));
    if (k === "prefijo") B.prefijo = v.trim();
    else if (k === "div") B.divisor_peso = Number(v) || 0;
    else if (k === "c0") B.codigo[0] = num(v); else if (k === "c1") B.codigo[1] = num(v);
    else if (k === "v0") B.valor[0] = num(v); else if (k === "v1") B.valor[1] = num(v);
    const f = formatoDe(B);
    const d = el("cfgBalDib"); if (d) d.textContent = L.dibujoFormatoBalanza(f);
    if (L.formatoBalanzaValido(f)) despues("balanza", guardarFormatoBalanza);
  }

  vista.addEventListener("input", (e) => {
    const g = e.target;
    if (g.id === "cfgBuscar") { S.q = g.value; pintarNav(); return; }
    if (g.id === "cfgRespBusca") { S.rq = g.value; const l = el("cfgRespLista"); if (l) l.innerHTML = listaRespaldosHTML(); return; }
    if (g.id === "cfgEqBusca") {
      S.eq = g.value; pintarSeccion();
      const n = el("cfgEqBusca"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); }
      return;
    }
    if (g.dataset.cIn) return alEscribir(g);
    if (g.dataset.cBal) return alEscribirBal(g);
    if (g.dataset.cCinta !== undefined) { S.D.textos.cinta[Number(g.dataset.cCinta)] = g.value; despues("textos", guardarTextos); }
  });
  vista.addEventListener("change", async (e) => {
    const g = e.target;
    if (g.dataset.cIn === "local.rut") {
      const f = L.rutFormato(g.value);
      if (f) { g.value = f; S.D.local.rut = f; g.classList.remove("cfg-in--mal"); const er = $c('[data-c-err="rut"]'); if (er) er.textContent = ""; actualizarTicket(); despues("local", guardarLocalConfig, 50); }
    }
    if (g.dataset.cIn === "afuera") {
      const ruta = (g.value || "").trim();
      const r = await guardarAjustes({ respaldo_afuera: ruta }, ruta ? "Carpeta guardada. Aprieta «Respaldar ahora» para probarla." : "Sin copia de afuera");
      if (r) { const est = el("cfgAfueraEst"); if (est) est.innerHTML = estadoAfueraHTML(AJUSTES.respaldo_afuera_estado); }
    }
    if (g.dataset.cSel === "impresora") {
      const nombre = g.value;
      const puerto = impresorasWindows.find((p) => p.nombre === nombre)?.puerto || (nombre === IMPRESION.impresora ? IMPRESION.puerto : "");
      if (guardarPrefs({ impresora: nombre, puerto })) {
        S.D.impEstado = nombre ? "Impresora elegida: " + nombre + ". Imprime una prueba para revisar el papel." : "Elige una impresora para imprimir directamente.";
        estadoImp(S.D.impEstado);
        const tipoAntes = IMPRESION.tipo;
        void tipoAntes;
      }
    }
    if (g.dataset.cSel === "bloqueo") {
      const m = Number(g.value);
      const r = await guardarAjustes({ bloqueo_minutos: m }, "Listo: la caja se bloquea después de " + m + " min sin uso");
      void r;
    }
    if (g.id === "cfgPantArchivo" && g.files && g.files[0]) {
      const archivo = g.files[0];
      g.value = "";
      try {
        const datos = JSON.parse(await archivo.text());
        await capi("/config/pantallas/respaldo", { method: "PUT", body: json(datos) });
        S.cargada.pantallas = false; guardado(); avisar("Respaldo de las pantallas cargado");
        cargarSeccion("pantallas");
      } catch (err) { avisar(err instanceof SyntaxError ? "Ese archivo no es un respaldo de las pantallas." : err.message, true); }
    }
  });
  vista.addEventListener("toggle", (e) => {
    const d = e.target;
    if (d.dataset && d.dataset.cDet) { if (d.open) S.abiertos.add(d.dataset.cDet); else S.abiertos.delete(d.dataset.cDet); }
  }, true);

  vista.addEventListener("click", (e) => {
    const t = e.target;
    const pk = t.closest("[data-c-pk]"); if (pk) return teclaPin(pk.dataset.cPk);
    const a = t.closest("[data-c-act]"); if (a) return accion(a.dataset.cAct);
    const lq = t.closest("[data-c-lq]");
    if (lq) {
      const inp = document.getElementById(lq.dataset.cLq);
      inp.value = ""; inp.dispatchEvent(new Event("input", { bubbles: true })); inp.focus(); return;
    }
    const ir_ = t.closest("[data-c-ir]"); if (ir_) return ir(ir_.dataset.cSec, ir_.dataset.cIr);
    const sec = t.closest(".cfg-nav__b[data-c-sec]");
    if (sec) { S.sec = sec.dataset.cSec; pintarNavSoloMarca(); pintarSeccion(true); return; }
    const cp = t.closest("[data-c-copiar]"); if (cp) return copiar(cp.dataset.cCopiar);
    const per = t.closest("[data-c-persona]"); if (per) return abrirPersona(per.dataset.cPersona);
    const tv = t.closest("[data-c-tv]");
    if (tv) { TV = (S.D.tvs || []).find((x) => x.id === Number(tv.dataset.cTv)); if (TV) pintarTv(true); return; }
    const medio = t.closest("[data-c-medio]"); if (medio) return cambiarMedio(medio.dataset.cMedio);
    const ch = t.closest("[data-c-chip]"); if (ch) return cambiarChip(ch.dataset.cChip, Number(ch.dataset.v));
    const mg = t.closest("[data-c-margen]"); if (mg) return elegirMargenConfig(Number(mg.dataset.cMargen)).then(() => pintarSeccion());
    const sg = t.closest("[data-c-seg]"); if (sg) return elegir(sg.dataset.cSeg, sg.dataset.v);
    const tg = t.closest(".cfg-aj--sw");
    if (tg) { const b = $c("[data-c-tog]", tg); if (b && !b.disabled) return alternar(b.dataset.cTog); }
    const lugar = t.closest("[data-c-lugar]");
    if (lugar) { AJUSTES.respaldo_afuera = lugar.dataset.cLugar; const inp = el("cfgAfuera"); if (inp) { inp.value = lugar.dataset.cLugar; inp.dispatchEvent(new Event("change", { bubbles: true })); } return; }
    const cx = t.closest("[data-c-cinta-x]");
    if (cx) { S.D.textos.cinta.splice(Number(cx.dataset.cCintaX), 1); S.abiertos.add("cinta"); guardarTextos(); pintarSeccion(); return; }
    const rs = t.closest("[data-c-restaurar]"); if (rs) return dlgRestaurar(rs.dataset.cRestaurar);
  });
  vista.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && e.target.id === "cfgBuscar") { S.q = ""; e.target.value = ""; pintarNav(); }
    if (e.key === "Enter" && e.target.id === "cfgBuscar") { const p = $c("[data-c-ir]"); if (p) ir(p.dataset.cSec, p.dataset.cIr); }
  });
  // El teclado del computador escribe el PIN: dígitos, borrar y Enter.
  document.addEventListener("keydown", (e) => {
    if (S.user || !visible() || S.guiasSolas || capa.classList.contains("is-on")) return;
    if (!$c("#cfgPinCaja") || (S.msg && S.msg.t === "sin")) return;
    if (/^[0-9]$/.test(e.key)) teclaPin(e.key);
    else if (e.key === "Backspace") teclaPin("x");
    else if (e.key === "Enter") probarPin();
  });

  /* Los diálogos viven en su propia capa: sus clics y campos se atienden acá. */
  dlgEl.addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest("[data-c-x]")) {
      if (S.dlg && S.dlg.tipo === "reinicio") return;           // mientras la caja se reinicia no se cierra
      cerrarDlg(); if (visible() && S.user) pintarSeccion(); return;
    }
    const tipo = S.dlg && S.dlg.tipo;
    if (tipo === "persona") return clickPersona(e);
    if (tipo === "tv" || tipo === "tvq") return clickTv(e);
    if (tipo === "restaurar") {
      if (t.closest("[data-c-rok]")) { RS.ok = !RS.ok; return pintarRestaurar(); }
      const d = t.closest("[data-c-rd]");
      if (!d || d.disabled) return;
      if (d.dataset.cRd === "no") { cerrarDlg(); return; }
      if (d.dataset.cRd === "si") return restaurarAhora();
      return;
    }
    const lq = t.closest("[data-c-lq]");
    if (lq && lq.dataset.cLq === "cfgVerBusca") { const i = el("cfgVerBusca"); i.value = ""; el("cfgHist").innerHTML = S.dlg.lista(""); return; }
    const d = t.closest("[data-c-sd]");
    if (!d) return;
    switch (d.dataset.cSd) {
      case "cerrar": cerrarDlg(); break;
      case "pinred-si":
        capi("/red/pin", { method: "POST", body: "{}" }).then((r) => {
          S.D.red = r; S.D.pinVisible = true; cerrarDlg(); pintarSeccion(); guardado();
          avisar("PIN de red nuevo: " + r.pin + ". Anótalo.");
        }).catch((err) => { cerrarDlg(); avisar(err.message, true); });
        break;
      case "act-si": instalarVersion(); break;
      case "volver-si": volverVersion(); break;
      case "pantreset-si":
        capi("/config/pantallas/ejemplo", { method: "POST" }).then((r) => {
          S.D.textos = r.textos; S.D.fuenteEst = ""; cerrarDlg(); pintarSeccion(); guardado();
          avisar("Volviste a los datos de ejemplo de las pantallas");
        }).catch((err) => { cerrarDlg(); avisar(err.message, true); });
        break;
    }
  });
  dlgEl.addEventListener("input", (e) => {
    const g = e.target;
    if (g.dataset.cTvt) {
      const n = Math.max(5, Math.min(180, Number(String(g.value).replace(/\D/g, "")) || 5));
      TV.t[g.dataset.cTvt] = n;
      despues("tv", () => guardarTv({ t: { [g.dataset.cTvt]: n } }));
    } else if (g.id === "cfgTvNombre") {
      TV.nombre = g.value || "Televisor";
      despues("tvn", () => guardarTv({ nombre: TV.nombre }));
    } else if (g.id === "cfgPNombre") {
      P.u.nombre = g.value; actualizarAgregar();
      if (!P.nuevo && g.value.trim()) despues("pnombre", () => guardarPersona());
    } else if (g.id === "cfgPermBusca") {
      P.q = g.value; el("cfgPermisos").innerHTML = permisoFilas();
    } else if (g.id === "cfgVerBusca") {
      el("cfgHist").innerHTML = S.dlg.lista(g.value);
    }
  });

  // Mientras Config está abierta, un cambio de pantalla completa o de barra se refleja en «Esta caja».
  document.addEventListener("fullscreenchange", () => { if (S.user && visible() && S.sec === "caja") pintarSeccion(); });

  /* ==========================================================
     LO QUE USA app.js
     ========================================================== */
  async function abrir(sec) {
    if (S.user && Date.now() - S.ultimaApertura < 600 && vista.dataset.listo && !sec) return;
    S.ultimaApertura = Date.now();
    vista.dataset.listo = "1";
    if (sec) { if (S.user) S.sec = sec; else S.pendiente = sec; }
    if (S.user) return render();
    S.pin = ""; S.msg = null; S.guiasSolas = false;
    render();
    // ¿El servidor todavía la tiene abierta? (se recargó la página hace un momento)
    try {
      const e = await api("/config/estado", { espera: 5000 });
      if (e.activo && !S.user) {
        if (sec || S.pendiente) { /* conserva la sección pedida */ }
        return entrarComo(e.usuario);
      }
    } catch (x) { /* si no contesta, se pide el PIN */ }
    // Una caja sin personas no tiene PIN que pedir.
    if (!S.user && SESION && SESION.provisorio) entrarSinPin();
  }
  window.Config = {
    abrir() { return abrir(); },
    /* Ir directo a una sección (el botón «Equipo» de la barra). Pide el PIN si hace falta. */
    irA(sec) {
      S.pendiente = sec;
      if (S.user) { S.sec = sec; S.pendiente = null; }
      verVista("guias");
      if (visible() && S.user) render();
    },
    /* El candado, el cambio de usuario o el bloqueo cierran Config de inmediato. */
    cerrar() { if (S.user) salir(); else { S.guiasSolas = false; } },
    /* El lector de códigos de barras: ¿hay un campo de prueba de etiquetas a la vista? */
    campoDePrueba() {
      if (!S.user || !visible() || S.sec !== "impresora" || !AJUSTES.usar_balanza) return null;
      return el("cfgBalCod");
    },
    probarEtiqueta,
    /* Para las pruebas con navegador. */
    _estado: S,
  };
})();
