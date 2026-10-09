/* ==========================================================
   La pestaña «Ventas»: arriba se elige entre «Mi turno» y «Reportes» (con candado).

   · Mi turno — SOLO el turno que está abierto. Es lo que mira quien atiende: cuánto lleva
     vendido, cuánta plata debería haber en el cajón y la lista de sus ventas. Cerrar el turno
     abre el cierre de siempre (arqueo a ciegas y cuadre de tarjetas, en app.js).
   · Reportes — para el dueño. Pide el PIN (lo verifica el servidor) y deja entrar solo a quien
     tenga el permiso «Ver reportes». Se cierra sola tras 5 minutos sin uso.

   Todo lo que se calcula se calcula en el servidor (apps/pos/api/reportes.py y el corte de
   apps/pos/api/turnos.py): acá solo se dibuja. Los gráficos son SVG y CSS propios, porque la
   caja no tiene internet garantizado. La lógica sin pantalla (buscar sin tildes, comparar,
   geometría de los gráficos) está en ventas-logica.js, que se prueba con Node.

   Cuidado con los atributos data-*: app.js tiene UN solo manejador de clics para toda la
   página y reacciona a data-anular, data-imprimir, data-periodo, data-mas… Los de acá llevan
   todos el prefijo «v» (data-v-…) para no cruzarse con ninguno.
   ========================================================== */
(function () {
  "use strict";
  const V = window.VentasLogica;
  const { clp, sinTildes, MENOS } = V;
  const vista = document.getElementById("vistaVentas");
  if (!vista) return;
  const capa = document.getElementById("capaVentas");
  const dlgEl = document.getElementById("dialogoVentas");

  const I = {
    lupa: '<svg class="i-lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 21 21"/></svg>',
    cierra: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    ojo: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    imprime: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V4h10v5M7 17H5a1 1 0 0 1-1-1v-5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5a1 1 0 0 1-1 1h-2"/><rect x="7" y="14" width="10" height="6" rx="1"/></svg>',
    borrar: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6-7z"/><path d="M12.5 9.5l5 5M17.5 9.5l-5 5"/></svg>',
    mas: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    llave: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    baja: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 11l5 5 5-5M5 20h14"/></svg>',
    sale: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h4M14 8l4 4-4 4M18 12H9"/></svg>',
    izq: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>',
    der: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>',
  };
  const colorOk = (c, defecto) => (/^#[0-9a-f]{3,8}$/i.test(String(c || "")) ? c : defecto);
  const avatar = (nombre, color) => `<span class="av" style="--c:${colorOk(color, "#8A5A34")}">${esc(String(nombre || "?").charAt(0).toUpperCase())}</span>`;
  const colorCat = (id) => (id == null ? "#A8978A" : colorDeCat(id));
  const nVentas = (n) => `${n} venta${n === 1 ? "" : "s"}`;
  const buscadorHTML = (id, ph, valor, extra) => `<div class="i-busca ${extra || ""}">${I.lupa}
      <input id="${id}" type="search" placeholder="${ph}" autocomplete="off" spellcheck="false" value="${esc(valor)}">
      <button type="button" class="i-x" data-v-limpia="${id}" aria-label="Limpiar">${I.cierra}</button></div>`;

  /* ==========================================================
     LOS DIÁLOGOS (uno solo a la vez, en su propia capa)
     ========================================================== */
  let alCerrarDlg = null;
  function abrirDlg(clase, html, alCerrar) {
    alCerrarDlg = alCerrar || null;
    dlgEl.className = "dialogo i-dlg " + clase;
    dlgEl.innerHTML = html;
    capa.classList.add("is-on");
    return dlgEl;
  }
  function cerrarDlg() {
    capa.classList.remove("is-on");
    dlgEl.innerHTML = "";
    const f = alCerrarDlg;
    alCerrarDlg = null;
    if (f) f();
  }
  const cabeceraDlg = (titulo, sub) => `<header class="i-cab"><div><h2>${titulo}</h2>${sub ? `<p>${sub}</p>` : ""}</div>
      <button type="button" class="i-cerrar" data-v-x aria-label="Cerrar">${I.cierra}</button></header>`;
  const tecladoHTML = (para) => `<div class="vk" data-v-para="${para}">${["1", "2", "3", "4", "5", "6", "7", "8", "9", "c", "0", "x"].map((k) =>
    k === "x" ? `<button type="button" class="teclado__t teclado__t--acc" data-v-tecla="x" aria-label="Borrar">${I.borrar}</button>`
      : k === "c" ? `<button type="button" class="teclado__t teclado__t--acc" data-v-tecla="c" aria-label="Limpiar">C</button>`
        : `<button type="button" class="teclado__t" data-v-tecla="${k}">${k}</button>`).join("")}</div>`;

  dlgEl.addEventListener("click", (e) => {
    if (e.target.closest("[data-v-x]")) return cerrarDlg();
    const t = e.target.closest("[data-v-tecla]");
    if (t) {
      const campo = document.getElementById(t.closest(".vk").dataset.vPara);
      campo.value = V.teclear(campo.value, t.dataset.vTecla);
      campo.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    const x = e.target.closest("[data-v-limpia]");
    if (x) {
      const campo = document.getElementById(x.dataset.vLimpia);
      campo.value = "";
      campo.dispatchEvent(new Event("input", { bubbles: true }));
      campo.focus();
    }
  });

  /* ==========================================================
     EL CORTE DE UN TURNO (Mi turno y el detalle desde Reportes)
     ========================================================== */
  function montarCorte(el, corte0, opts) {
    const vivo = !!(opts && opts.vivo);
    const S = { q: "", corte: corte0 };

    const cabeceraVivo = (c) => {
      const t = c.turno;
      const min = V.minutosEntre(t.abierto_at, null, Date.now());
      return `<div class="vt-cab">
        <div class="vt-quien">${avatar(t.abrio, t.color)}
          <div><h2>Turno de ${esc(t.abrio)} <span>· abierto ${V.cuandoAbrio(t.abierto_at, hoyISO())} (hace ${V.duracion(min)})</span></h2>
            <p>${esc(NOMBRE_DEL_LOCAL)}</p></div></div>
        <div class="vt-bot"><button type="button" class="i-btn i-btn--prin vt-grande" data-v-acc="cerrar">Cerrar turno</button></div>
      </div>`;
    };
    const bannerCorte = (c) => {
      const t = c.turno;
      if (t.abierto) {
        return `<div class="vt-banner vt-banner--ok"><div><b>Turno en curso</b> · abierto ${V.hhmm(t.abierto_at)}</div>
          <div>Debería haber <b>${clp(c.caja.esperado)}</b> en el cajón · el efectivo se cuenta al cerrar</div></div>`;
      }
      const ci = c.cierre || {};
      const dif = ci.diferencia == null ? 0 : ci.diferencia;
      const min = V.minutosEntre(t.abierto_at, t.cerrado_at, 0);
      return `<div class="vt-banner vt-banner--${V.claseDif(dif)}">
        <div><b>Turno cerrado ${V.hhmm(t.cerrado_at)}</b> · duró ${V.duracion(min)}${t.cerro && t.cerro !== t.abrio ? " · cerró " + esc(t.cerro) : ""}</div>
        <div>Debía haber <b>${clp(c.caja.esperado)}</b> · se contó <b>${clp(ci.contado || 0)}</b> · <strong>${V.textoDif(dif)}</strong></div></div>`;
    };

    function tarjetasHTML(c) {
      const k = c.caja;
      const medios = c.por_medio.map((m) => {
        const share = V.pct(m.total, c.vendido);
        return `<li style="--c:${V.COLOR_MEDIO[m.medio]}"><span class="pg-t"><i></i>${esc(m.nombre)}</span>
          <span class="pg-bar"><u style="width:${Math.max(m.total ? 3 : 0, share)}%"></u></span>
          <span class="pg-m"><b>${clp(m.total)}</b><small>${nVentas(m.n)}</small></span></li>`;
      }).join("");
      const mx = c.por_categoria.length ? c.por_categoria[0].total : 1;
      const cats = c.por_categoria.map((x) => `<li style="--c:${colorCat(x.id)}"><span class="ct-t"><i></i>${esc(x.nombre)}</span>
          <span class="ct-bar"><u style="width:${Math.max(3, Math.round(x.total / mx * 100))}%"></u></span>
          <b>${clp(x.total)}</b></li>`).join("");
      const lin = (a, b, cero) => `<li class="${cero ? "cj-cero" : ""}"><span>${a}</span><b>${b}</b></li>`;
      const p = c.propinas;
      return `<div class="vt-cards">
        <section class="vcard vcard--vend"><h3>Vendido</h3>
          <b class="vcard-big">${clp(c.vendido)}</b>
          <p><strong>${c.n}</strong> venta${c.n === 1 ? "" : "s"} · ticket promedio <strong>${clp(c.ticket)}</strong></p>
          ${c.anuladas.n ? `<p class="vcard-nota">${c.anuladas.n} anulada${c.anuladas.n === 1 ? "" : "s"} (${clp(c.anuladas.total)}) no ${c.anuladas.n === 1 ? "cuenta" : "cuentan"}</p>` : ""}
        </section>
        <section class="vcard vcard--prop"><h3>Propinas</h3>
          <b class="vcard-med">${clp(p.total)}</b>
          <p>${p.n ? `${nVentas(p.n)} con propina` + (p.tarjeta ? ` · ${clp(p.tarjeta)} en tarjeta` : "") + (p.efectivo ? ` · ${clp(p.efectivo)} en efectivo` : "")
            : "Ninguna en este turno"}</p>
        </section>
        <section class="vcard vcard--caja"><h3>Dinero en caja</h3>
          <ul class="cj">
            ${lin("Fondo inicial", "+" + clp(k.fondo))}
            ${lin("Ventas en efectivo", "+" + clp(k.ventas_efectivo))}
            ${lin("Entradas", (k.entradas ? "+" : "") + clp(k.entradas), !k.entradas)}
            ${lin("Retiros", (k.retiros ? MENOS : "") + clp(k.retiros), !k.retiros)}
            ${lin("Devoluciones", (k.devoluciones ? MENOS : "") + clp(k.devoluciones), !k.devoluciones)}
            ${k.propinas_pagadas ? lin("Propinas pagadas del cajón", MENOS + clp(k.propinas_pagadas)) : ""}
          </ul>
          <div class="cj-total"><span>${c.turno.abierto ? "Debería haber en el cajón" : "Debía haber al cerrar"}</span><b>${clp(k.esperado)}</b></div>
        </section>
        <section class="vcard vcard--pago"><h3>Por forma de pago</h3><ul class="pg">${medios}</ul></section>
        <section class="vcard vcard--cat"><h3>Por categoría</h3><ul class="ct">${cats || '<li class="ct-nada">Todavía no hay ventas</li>'}</ul></section>
      </div>`;
    }

    function movimientosHTML(c) {
      const movs = c.movimientos.filter((m) => !m.anulado);
      const filas = movs.map((m) => `<li>
          <span class="vmov-h">${esc(m.hora)}</span>
          <div class="vmov-q"><b>${esc(m.motivo)}</b><small>${esc(m.hecho_por || "—")} · ${m.tipo === "retiro" ? "retiro" : "entrada"}</small></div>
          <span class="vmov-m vmov-m--${m.tipo}">${m.tipo === "retiro" ? MENOS : "+"}${clp(m.monto)}</span>
          ${vivo && puedo("caja_retirar") ? `<button type="button" class="vmov-anula" data-v-anumov="${m.id}" title="Anular este movimiento" aria-label="Anular este movimiento">${I.cierra}</button>` : ""}
        </li>`).join("");
      const puede = vivo && puedo("caja_retirar");
      return `<aside class="vmov">
        <div class="vmov-cab"><h3>Movimientos de caja</h3></div>
        ${vivo ? `<div class="vmov-acc">
          <button type="button" class="i-btn" data-v-acc="retiro" ${puede ? "" : 'disabled title="Esto lo hace el dueño"'}>Retiro de caja</button>
          <button type="button" class="i-btn i-btn--suave" data-v-acc="entrada" ${puede ? "" : 'disabled title="Esto lo hace el dueño"'}>${I.mas}Entrada</button></div>` : ""}
        <ul class="vmov-lista">${filas || '<li class="vmov-nada">No hubo retiros ni entradas de efectivo.</li>'}</ul>
      </aside>`;
    }

    function listaShell(c) {
      return `<section class="vl">
        <div class="vl-cab"><h3>Ventas del turno <em class="vl-n">${c.ventas.length}</em></h3>
          ${buscadorHTML("vlQ", "Buscar por n°, producto o monto", S.q, "vl-busca")}</div>
        <div class="vl-tabla"><table class="vl-t">
          <thead><tr><th class="vl-cn">N°</th><th class="vl-ch">Hora</th><th class="vl-cp">Qué se vendió</th><th class="vl-cg">Pago</th><th class="vl-ct">Total</th><th class="vl-ca"></th></tr></thead>
          <tbody id="vlCuerpo"></tbody></table></div>
        <div class="vl-pie" id="vlPie"></div>
      </section>`;
    }

    function resumenProductos(v) {
      const a = v.productos.slice(0, 2).map((l) => (l.cantidad !== 1 ? l.cantidad + " × " : "") + l.nombre);
      const mas = v.productos.length - 2;
      return esc(a.join(", ")) + (mas > 0 ? ` <em>+${mas} más</em>` : "");
    }

    function pintarLista() {
      const c = S.corte;
      const todas = c.ventas;                         // el servidor las manda de la más nueva a la más vieja
      const lista = todas.filter((v) => V.ventaCalza(v, S.q));
      const cuerpo = el.querySelector("#vlCuerpo");
      cuerpo.innerHTML = lista.map((v) => {
        const nombre = v.medio_pago === "mixto" ? "Mixto" : v.medio;
        const color = V.COLOR_MEDIO[v.medio_pago] || "#8A5A34";
        return `<tr data-v-fila="${v.id}" class="${v.anulada ? "vl-anulada" : ""}">
          <td class="vl-cn">${v.numero}</td><td class="vl-ch">${esc(v.hora)}</td>
          <td class="vl-cp">${resumenProductos(v)}</td>
          <td class="vl-cg">${v.anulada ? '<span class="v-pill v-pill--anulada">Anulada</span>'
            : `<span class="v-pill" style="--c:${color}"><i></i>${esc(nombre)}</span>`}</td>
          <td class="vl-ct">${clp(v.cobrado)}</td>
          <td class="vl-ca">
            <button type="button" class="i-ico" data-v-ver="${v.id}" aria-label="Ver detalle" title="Ver detalle">${I.ojo}</button>
            <button type="button" class="i-ico" data-v-imp="${v.id}" aria-label="Reimprimir" title="Reimprimir el comprobante">${I.imprime}</button>
            ${vivo && !v.anulada && puedo("anular") ? `<button type="button" class="i-btn i-btn--aviso vl-anula" data-v-anu="${v.id}">Anular</button>` : ""}
          </td></tr>`;
      }).join("") || `<tr class="vl-vacia"><td colspan="6">${S.q ? "No hay ventas que calcen con esa búsqueda." : "Este turno todavía no ha vendido nada."}</td></tr>`;
      el.querySelector("#vlPie").textContent = S.q ? `${lista.length} de ${todas.length} ventas`
        : `${todas.length} venta${todas.length === 1 ? "" : "s"} · la más nueva arriba`;
    }

    function pintar() {
      const c = S.corte;
      el.innerHTML = (vivo ? cabeceraVivo(c) : bannerCorte(c)) + tarjetasHTML(c)
        + `<div class="vt-bajo">${listaShell(c)}${movimientosHTML(c)}</div>`;
      pintarLista();
    }

    el.addEventListener("input", (e) => {
      if (e.target.id !== "vlQ") return;
      S.q = e.target.value;
      pintarLista();
    });
    el.addEventListener("click", (e) => {
      const g = e.target;
      const limpia = g.closest("[data-v-limpia]");
      if (limpia) {
        S.q = "";
        const q = el.querySelector("#vlQ");
        q.value = "";
        pintarLista();
        q.focus();
        return;
      }
      const ver = g.closest("[data-v-ver]"), imp = g.closest("[data-v-imp]"), anu = g.closest("[data-v-anu]");
      const volver = opts && opts.volver;
      if (imp) return imprimir("/comprobante/" + imp.dataset.vImp);
      if (anu) return abrirAnular(+anu.dataset.vAnu, S.corte);
      if (ver) return abrirVenta(+ver.dataset.vVer, vivo, volver);
      const fila = g.closest("tr[data-v-fila]");
      if (fila && !g.closest("button")) return abrirVenta(+fila.dataset.vFila, vivo, volver);
      const mov = g.closest("[data-v-anumov]");
      if (mov) return anularMovimiento(+mov.dataset.vAnumov);
      const a = g.closest("[data-v-acc]");
      if (!a || a.disabled) return;
      if (a.dataset.vAcc === "cerrar") dialogoTurno();
      else if (a.dataset.vAcc === "retiro") abrirMovimiento("retiro", S.corte);
      else if (a.dataset.vAcc === "entrada") abrirMovimiento("ingreso", S.corte);
    });

    pintar();
    return { el, pintar, poner(corte) { S.corte = corte; pintar(); } };
  }

  /* ==========================================================
     DETALLE, REIMPRIMIR Y ANULAR UNA VENTA
     ========================================================== */
  async function abrirVenta(id, vivo, volver) {
    let v;
    try { v = await api("/ventas/" + id); } catch (e) { return avisar(e.message, true); }
    const filas = v.lineas.map((l) => `<li><span class="dv-c">${l.cantidad}</span>
      <span class="dv-n">${esc(l.nombre)}<small>${clp(l.precio_unitario)}${l.cantidad !== 1 ? " c/u" : ""}${l.detalle ? " · " + esc(l.detalle) : ""}</small></span>
      <b>${clp(l.subtotal)}</b></li>`).join("");
    const pagos = v.medio_pago === "mixto" && v.pagos && v.pagos.length
      ? v.pagos.map((p) => `${V.NOMBRE_MEDIO[p.medio] || p.medio} ${clp(p.monto)}`).join(" + ")
      : `${V.NOMBRE_MEDIO[v.medio_pago] || v.medio_pago} ${clp(v.cobrado)}`;
    const anulada = v.estado === "anulada";
    const fecha = v.creada_at;
    abrirDlg("i-dlg--chico", `${cabeceraDlg("Venta N° " + v.numero,
      `${V.fechaCorta(fecha)} · ${V.hhmm(fecha)}${v.quien ? " · cobró " + esc(v.quien) : ""}`)}
      <div class="i-cuerpo">
        ${anulada ? `<div class="dv-anulada"><b>Venta anulada</b>${v.anulada_por ? " por " + esc(v.anulada_por) : ""}${v.anulada_at ? " a las " + V.hhmm(v.anulada_at) : ""}<br>Motivo: ${esc(v.anulada_motivo || "—")}</div>` : ""}
        <ul class="dv">${filas}</ul>
        ${v.descuento ? `<div class="dv-lin"><span>Subtotal</span><b>${clp(v.total)}</b></div>
          <div class="dv-lin"><span>Descuento</span><b>${MENOS}${clp(v.descuento)}</b></div>` : ""}
        <div class="dv-tot"><span>Total</span><b>${clp(v.cobrado)}</b></div>
        ${v.propina ? `<div class="dv-lin"><span>Propina (${esc((V.NOMBRE_MEDIO[v.medio_pago] || v.medio_pago).toLowerCase())})</span><b>${clp(v.propina)}</b></div>` : ""}
        <div class="dv-lin"><span>Pagó con</span><b>${esc(pagos)}</b></div>
        ${v.nota ? `<div class="dv-lin"><span>Nota</span><b>${esc(v.nota)}</b></div>` : ""}
      </div>
      <footer class="dialogo__pie">
        <button type="button" class="i-btn" data-v-reimp>${I.imprime}Reimprimir</button>
        ${vivo && !anulada && puedo("anular") ? '<button type="button" class="i-btn i-btn--aviso" data-v-anudlg>Anular venta</button>' : ""}
        <button type="button" class="i-btn i-btn--prin" data-v-x>Listo</button>
      </footer>`, volver);
    dlgEl.querySelector("[data-v-reimp]").onclick = () => imprimir("/comprobante/" + id);
    const b = dlgEl.querySelector("[data-v-anudlg]");
    if (b) b.onclick = () => abrirAnular(id, null, v);
  }

  const MOTIVOS_ANULAR = ["Error al cobrar", "Cliente se arrepintió", "Producto equivocado", "Cobro repetido"];
  function abrirAnular(id, corte, venta) {
    const v = venta || (corte && corte.ventas.find((x) => x.id === id));
    if (!v) return;
    const numero = v.numero, total = v.cobrado;
    abrirDlg("i-dlg--medio", `${cabeceraDlg("¿Anular la venta N° " + numero + "?", `${clp(total)}`)}
      <div class="i-cuerpo">
        <p class="vt-texto">La venta deja de contar en lo vendido y, si se cobró en efectivo, esa plata se descuenta del cajón.
          Queda anotado quién la anuló y por qué.</p>
        <div class="vt-sec">¿Por qué se anula?</div>
        <div class="vt-motivos" id="vAnMot">${MOTIVOS_ANULAR.map((m) => `<button type="button" class="i-chip i-chip--m" data-v-mot="${esc(m)}">${esc(m)}</button>`).join("")}</div>
        <label class="i-campo vt-otro"><span>O escribe otro motivo</span>
          <input id="vAnOtro" type="text" autocomplete="off" placeholder="Ej: el cliente cambió de idea"></label>
      </div>
      <footer class="dialogo__pie">
        <span class="i-msg" id="vAnMsg">Elige un motivo para poder anular.</span>
        <button type="button" class="i-btn" data-v-x>No anular</button>
        <button type="button" class="i-btn i-btn--aviso" id="vAnOk" disabled>Anular venta</button>
      </footer>`);
    let mot = "";
    const ok = dlgEl.querySelector("#vAnOk"), otro = dlgEl.querySelector("#vAnOtro"), msg = dlgEl.querySelector("#vAnMsg");
    const act = () => {
      const m = otro.value.trim() || mot;
      ok.disabled = !m;
      msg.textContent = m ? "Motivo: " + m : "Elige un motivo para poder anular.";
    };
    dlgEl.querySelector("#vAnMot").onclick = (e) => {
      const b = e.target.closest("[data-v-mot]");
      if (!b) return;
      mot = b.dataset.vMot;
      otro.value = "";
      dlgEl.querySelectorAll("[data-v-mot]").forEach((x) => x.classList.toggle("is-on", x === b));
      act();
    };
    otro.oninput = () => {
      if (otro.value) { mot = ""; dlgEl.querySelectorAll("[data-v-mot]").forEach((x) => x.classList.remove("is-on")); }
      act();
    };
    ok.onclick = async () => {
      const m = otro.value.trim() || mot;
      if (!m) return;
      ok.disabled = true;
      try {
        await api(`/ventas/${id}/anular`, { method: "POST", body: JSON.stringify({ motivo: m }) });
      } catch (e) {
        msg.textContent = e.message;
        msg.classList.add("i-msg--mal");
        ok.disabled = false;
        return;
      }
      cerrarDlg();
      avisar("Venta N° " + numero + " anulada");
      refrescar();
    };
  }

  /* ==========================================================
     RETIRO / ENTRADA DE CAJA
     ========================================================== */
  function abrirMovimiento(tipo, corte) {
    const esRet = tipo === "retiro";
    const motivos = esRet ? ["Compra de insumos", "Pago a proveedor", "Cambio / sencillo", "Propina al equipo"]
      : ["Cambio / sencillo", "Aporte del dueño", "Monedas para vuelto"];
    const hay = corte.caja.esperado;
    abrirDlg("i-dlg--medio", `${cabeceraDlg(esRet ? "Retiro de caja" : "Entrada de efectivo",
      `Lo anota ${esc(SESION.nombre || corte.turno.abrio)} · queda con su nombre y la hora`)}
      <div class="i-cuerpo">
        <div class="vm">
          <div class="vm-col">
            <div class="vt-sec">¿Cuánto?</div>
            <div class="vm-plata"><b>$</b><input id="vmMonto" type="text" inputmode="numeric" placeholder="0" autocomplete="off"></div>
            ${tecladoHTML("vmMonto")}
          </div>
          <div class="vm-col">
            <div class="vt-sec">¿Para qué?</div>
            <div class="vt-motivos vt-motivos--col" id="vmMot">${motivos.map((m) => `<button type="button" class="i-chip i-chip--m" data-v-mot="${esc(m)}">${esc(m)}</button>`).join("")}</div>
            <label class="i-campo vt-otro"><span>O escribe el motivo</span>
              <input id="vmOtro" type="text" autocomplete="off" placeholder="Ej: compra de vasos"></label>
            <p class="i-ayuda">${esRet ? `En el cajón debería haber ${clp(hay)}. El retiro se resta del dinero en caja.` : "La entrada se suma al dinero en caja."}</p>
          </div>
        </div>
      </div>
      <footer class="dialogo__pie">
        <span class="i-msg" id="vmMsg"></span>
        <button type="button" class="i-btn" data-v-x>Cancelar</button>
        <button type="button" class="i-btn i-btn--prin" id="vmOk" disabled>${esRet ? "Guardar retiro" : "Guardar entrada"}</button>
      </footer>`);
    let mot = "";
    const monto = dlgEl.querySelector("#vmMonto"), otro = dlgEl.querySelector("#vmOtro");
    const ok = dlgEl.querySelector("#vmOk"), msg = dlgEl.querySelector("#vmMsg");
    const act = () => {
      const m = soloNumeros(monto.value), why = otro.value.trim() || mot;
      const err = esRet && m > hay ? "No puedes sacar más de lo que hay en el cajón." : "";
      msg.textContent = err;
      msg.classList.toggle("i-msg--mal", !!err);
      ok.disabled = !(m > 0 && why && !err);
    };
    monto.oninput = () => { monto.value = V.conPuntos(soloNumeros(monto.value) || ""); act(); };
    dlgEl.querySelector("#vmMot").onclick = (e) => {
      const b = e.target.closest("[data-v-mot]");
      if (!b) return;
      mot = b.dataset.vMot;
      otro.value = "";
      dlgEl.querySelectorAll("[data-v-mot]").forEach((x) => x.classList.toggle("is-on", x === b));
      act();
    };
    otro.oninput = () => {
      if (otro.value) { mot = ""; dlgEl.querySelectorAll("[data-v-mot]").forEach((x) => x.classList.remove("is-on")); }
      act();
    };
    ok.onclick = async () => {
      const m = soloNumeros(monto.value), why = otro.value.trim() || mot;
      if (!(m > 0 && why)) return;
      ok.disabled = true;
      try {
        await api(`/turnos/${esRet ? "retiro" : "ingreso"}`, { method: "POST", body: JSON.stringify({ monto: m, motivo: why }) });
      } catch (e) {
        msg.textContent = e.message;
        msg.classList.add("i-msg--mal");
        ok.disabled = false;
        return;
      }
      cerrarDlg();
      avisar((esRet ? "Retiro de " : "Entrada de ") + clp(m) + " anotado: " + why);
      refrescar();
    };
    setTimeout(() => monto.focus(), 50);
  }

  async function anularMovimiento(id) {
    if (!confirm("¿Anular este movimiento? El cajón vuelve a como estaba antes.")) return;
    try {
      await api(`/turnos/retiro/${id}/anular`, { method: "POST" });
    } catch (e) { return avisar(e.message, true); }
    avisar("Movimiento anulado");
    refrescar();
  }

  /* ==========================================================
     LA PESTAÑA: Mi turno | Reportes
     ========================================================== */
  const E = { sub: "turno", ctl: null };
  let cuerpo = null, ultimaApertura = 0;

  function montar() {
    vista.innerHTML = `<div class="vv">
      <div class="vv-sel"><div class="i-seg vv-seg" id="vvSeg" role="group" aria-label="Qué quieres ver">
        <button type="button" class="i-seg__b" data-v-sub="turno">Mi turno</button>
        <button type="button" class="i-seg__b vv-llave" data-v-sub="reportes">${I.llave}Reportes</button></div>
        <span class="vv-nota" id="vvNota"></span></div>
      <div class="vv-cuerpo" id="vvCuerpo"></div></div>`;
    cuerpo = vista.querySelector("#vvCuerpo");
    vista.dataset.listo = "1";
  }

  function mostrarSub(s) {
    E.sub = s;
    vista.querySelectorAll("#vvSeg [data-v-sub]").forEach((b) => b.classList.toggle("is-on", b.dataset.vSub === s));
    vista.querySelector("#vvNota").textContent = s === "turno" ? "Solo lo de este turno" : "Para el dueño";
    if (s === "turno") pintarTurno();
    else abrirReportes();
  }

  async function pintarTurno() {
    cuerpo.className = "vv-cuerpo vv-cuerpo--turno";
    E.ctl = null;
    if (!puedo("ver_dia")) {
      cuerpo.innerHTML = `<div class="vv-vacio"><h2>Este usuario no puede ver las ventas</h2>
        <p>Lo da el dueño en Equipo, con el permiso «Ver Ventas».</p></div>`;
      return;
    }
    cuerpo.innerHTML = '<p class="vv-cargando">Cargando el turno…</p>';
    let t;
    try { t = await cargarTurno(); } catch (e) {
      cuerpo.innerHTML = `<div class="vv-vacio"><h2>No se pudo leer el turno</h2><p>${esc(e.message)}</p>
        <button type="button" class="i-btn" data-v-acc2="reintentar">Reintentar</button></div>`;
      return;
    }
    if (E.sub !== "turno") return;
    if (!t.abierto) {
      cuerpo.innerHTML = `<div class="vv-vacio"><h2>La caja está cerrada</h2>
        <p>No hay un turno abierto, así que no hay nada que mostrar. Cuando se abra, acá va cómo va el turno.</p>
        <button type="button" class="i-btn i-btn--prin vt-grande" data-v-acc2="abrir">Abrir turno</button></div>`;
      return;
    }
    let corte;
    try { corte = await api(`/turnos/${t.turno.id}/corte`); } catch (e) {
      cuerpo.innerHTML = `<div class="vv-vacio"><h2>No se pudo leer el turno</h2><p>${esc(e.message)}</p>
        <button type="button" class="i-btn" data-v-acc2="reintentar">Reintentar</button></div>`;
      return;
    }
    if (E.sub !== "turno") return;
    cuerpo.innerHTML = '<div class="vt" id="vtRaiz"></div>';
    E.ctl = montarCorte(cuerpo.querySelector("#vtRaiz"), corte, { vivo: true });
  }

  /* Vuelve a leer el turno sin mover la pantalla (después de anular, de sacar plata…). */
  async function refrescar() {
    if (!vista.dataset.listo || E.sub !== "turno") return;
    if (!E.ctl || !E.ctl.el.isConnected) return pintarTurno();
    try {
      const t = await cargarTurno();
      if (!t.abierto) return pintarTurno();
      E.ctl.poner(await api(`/turnos/${t.turno.id}/corte`));
    } catch (e) { avisar(e.message, true); }
  }

  vista.addEventListener("click", (e) => {
    const b = e.target.closest("#vvSeg [data-v-sub]");
    if (b) { if (b.dataset.vSub !== E.sub || b.dataset.vSub === "reportes") mostrarSub(b.dataset.vSub); return; }
    const a2 = e.target.closest("[data-v-acc2]");
    if (a2) return a2.dataset.vAcc2 === "abrir" ? dialogoTurno() : pintarTurno();
  });

  /* ==========================================================
     REPORTES: el PIN
     ========================================================== */
  const MINUTOS_SIN_USO = 5;
  const R = {
    user: null, pin: "", msg: null, enviando: false,
    periodo: "7d", desde: "", hasta: "", datos: null, error: "", req: 0,
    sel: null, heat: null, topModo: "cant", topQ: "", turQ: "", soloDif: false,
    ultimo: Date.now(), latido: Date.now(), sinUsoMs: MINUTOS_SIN_USO * 60 * 1000,
  };

  /* Los endpoints de reportes dicen 401 cuando el acceso se acabó: no es una sesión perdida
     (para eso está app.js), es volver al PIN. */
  async function rapi(ruta, opciones) {
    try {
      return await api("/reportes" + ruta, opciones);
    } catch (e) {
      if (e.status === 401) {
        if (/Hay que entrar/.test(e.message)) sesionPerdida();
        else if (R.user) salirDeReportes(e.message);
      }
      throw e;
    }
  }

  function reportesVisible() {
    return vista.isConnected && vista.classList.contains("is-on") && E.sub === "reportes";
  }

  function salirDeReportes(aviso, avisoMalo) {
    const estaba = !!R.user;
    R.user = null; R.pin = ""; R.msg = null; R.datos = null; R.sel = null; R.heat = null; R.req++;
    if (estaba) api("/reportes/salir", { method: "POST", espera: 4000 }).catch(() => { });
    if (reportesVisible()) mostrarSub("turno");
    else E.sub = "turno";
    if (aviso) avisar(aviso, !!avisoMalo);
  }

  setInterval(() => {
    if (!R.user) return;
    const ahora = Date.now();
    if (ahora - R.ultimo > R.sinUsoMs) return salirDeReportes("Reportes se cerró solo tras 5 minutos sin uso. Para volver, pide el PIN de nuevo.");
    // Mientras se usa, el servidor se entera de que sigue en uso (renueva sus 5 minutos).
    if (reportesVisible() && ahora - R.ultimo < 4 * 60 * 1000 && ahora - R.latido > 90 * 1000) {
      R.latido = ahora;
      api("/reportes/estado", { espera: 5000 }).then((r) => { if (r && !r.activo && R.user) salirDeReportes("Reportes se cerró. Pide el PIN de nuevo."); }).catch(() => { });
    }
  }, 5000);
  ["pointerdown", "keydown", "wheel", "input"].forEach((ev) =>
    vista.addEventListener(ev, () => { R.ultimo = Date.now(); }, true));

  async function abrirReportes() {
    cuerpo.className = "vv-cuerpo vv-cuerpo--rp";
    E.ctl = null;
    if (R.user) return pintarReportes();
    // ¿El servidor todavía lo tiene abierto? (se recargó la página hace un momento)
    try {
      const e = await api("/reportes/estado", { espera: 5000 });
      if (E.sub !== "reportes") return;
      if (e.activo) { R.user = e.usuario; R.ultimo = R.latido = Date.now(); return pintarReportes(); }
    } catch (x) { /* si no contesta, se pide el PIN */ }
    if (SESION.provisorio) return entrarSinPin();
    R.pin = ""; R.msg = null;
    pintarPin();
  }

  async function entrarSinPin() {
    try {
      const r = await api("/reportes/entrar", { method: "POST", body: JSON.stringify({}), espera: 10000 });
      R.user = r.usuario; R.ultimo = R.latido = Date.now();
      pintarReportes();
    } catch (e) { R.msg = { t: "sin", texto: e.message }; pintarPin(); }
  }

  function pinHTML() {
    if (R.msg && R.msg.t === "sin") {
      return `<div class="pin"><div class="pin-caja pin-caja--sin">
        <div class="pin-ico pin-ico--no">${I.llave}</div>
        <h2>${esc(R.msg.texto)}</h2>
        <p>Los reportes muestran lo que gana el local, así que solo los ve quien tenga el permiso «Ver reportes».
          Si lo necesitas, pídeselo a quien administra el local (Equipo).</p>
        <div class="pin-botones">
          <button type="button" class="i-btn i-btn--prin vt-grande" data-v-pin="otro">Probar con otro PIN</button>
          <button type="button" class="i-btn vt-grande" data-v-pin="miturno">Volver a Mi turno</button></div>
      </div></div>`;
    }
    const teclas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "c", "0", "x"].map((k) =>
      k === "x" ? `<button type="button" class="teclado__t teclado__t--acc" data-v-pk="x" aria-label="Borrar">${I.borrar}</button>`
        : k === "c" ? `<button type="button" class="teclado__t teclado__t--acc" data-v-pk="c" aria-label="Limpiar">C</button>`
          : `<button type="button" class="teclado__t" data-v-pk="${k}">${k}</button>`).join("");
    const puntos = Math.max(4, R.pin.length);
    return `<div class="pin"><div class="pin-caja" id="vPinCaja">
      <div class="pin-ico">${I.llave}</div>
      <h2>Reportes</h2>
      <p>Reportes es para quien tenga el permiso «Ver reportes». Escribe tu PIN.</p>
      <div class="pin-puntos" id="vPinPuntos" aria-label="PIN">${Array.from({ length: puntos }, (_, i) => `<i class="pin-punto${i < R.pin.length ? " is-on" : ""}"></i>`).join("")}</div>
      <div class="pin-msg" id="vPinMsg" role="alert">${R.msg ? esc(R.msg.texto) : ""}</div>
      <div class="pin-teclas">${teclas}</div>
      <button type="button" class="i-btn i-btn--prin vt-grande pin-entrar" id="vPinEntrar" data-v-pin="entrar">Entrar</button>
    </div></div>`;
  }

  function pintarPin() {
    cuerpo.className = "vv-cuerpo vv-cuerpo--pin";
    cuerpo.innerHTML = pinHTML();
    const b = cuerpo.querySelector("#vPinEntrar");
    if (b) b.focus({ preventScroll: true });
  }
  function repintarPuntos() {
    const p = cuerpo.querySelector("#vPinPuntos");
    if (!p) return;
    const puntos = Math.max(4, R.pin.length);
    p.innerHTML = Array.from({ length: puntos }, (_, i) => `<i class="pin-punto${i < R.pin.length ? " is-on" : ""}"></i>`).join("");
    const m = cuerpo.querySelector("#vPinMsg");
    if (m) m.textContent = R.msg ? R.msg.texto : "";
  }
  function teclaPin(k) {
    if (R.enviando || (R.msg && R.msg.t === "sin")) return;
    R.msg = null;
    if (k === "x") R.pin = R.pin.slice(0, -1);
    else if (k === "c") R.pin = "";
    else if (R.pin.length < 8) R.pin += k;
    repintarPuntos();
  }
  async function probarPin() {
    if (R.enviando) return;
    if (R.pin.length < 4) { R.msg = { t: "corto", texto: "El PIN tiene 4 números o más." }; return repintarPuntos(); }
    const pin = R.pin;
    R.enviando = true;
    try {
      const r = await api("/reportes/entrar", { method: "POST", body: JSON.stringify({ pin }), espera: 15000 });
      R.enviando = false;
      R.user = r.usuario; R.pin = ""; R.msg = null; R.datos = null; R.sel = null; R.heat = null;
      R.ultimo = R.latido = Date.now();
      if (reportesVisible()) pintarReportes();
    } catch (e) {
      R.enviando = false;
      R.pin = "";
      if (e.status === 401 && /Hay que entrar/.test(e.message)) return sesionPerdida();
      R.msg = e.status === 403 ? { t: "sin", texto: e.message } : { t: "mal", texto: e.message };
      if (!reportesVisible()) return;
      pintarPin();
      const caja = cuerpo.querySelector("#vPinCaja");
      if (caja && R.msg.t === "mal") { caja.classList.add("pin-mal"); setTimeout(() => caja.classList.remove("pin-mal"), 450); }
    }
  }
  document.addEventListener("keydown", (e) => {
    if (R.user || !reportesVisible() || !cuerpo.querySelector("#vPinCaja") || capa.classList.contains("is-on")) return;
    if (/^[0-9]$/.test(e.key)) teclaPin(e.key);
    else if (e.key === "Backspace") teclaPin("x");
  });

  /* ==========================================================
     REPORTES: el tablero
     ========================================================== */
  const PERIODOS = [["hoy", "Hoy"], ["ayer", "Ayer"], ["7d", "7 días"], ["mes", "Este mes"], ["mesp", "Mes pasado"], ["rango", "Rango"]];
  const miles = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

  function consulta() {
    let q = "periodo=" + R.periodo;
    if (R.periodo === "rango") q += `&desde=${R.desde}&hasta=${R.hasta}`;
    return q;
  }

  function pintarReportes() {
    cuerpo.className = "vv-cuerpo vv-cuerpo--rp";
    if (R.periodo === "rango" && !R.desde) { R.hasta = hoyISO(); R.desde = diasAntes(13); }
    cuerpo.innerHTML = `<div class="rp-top">
        <div class="rp-fila1">
          <div class="rp-tit"><h2>Reportes</h2><span>${avatar(R.user.nombre || "Dueño", R.user.color)} ${R.user.nombre ? "Sesión de " + esc(R.user.nombre) + " · " + esc(R.user.rol_nombre) : "Caja sin personas creadas"}</span></div>
          <div class="rp-acc">
            <button type="button" class="i-btn" data-v-rp="exportar">${I.baja}Exportar</button>
            <button type="button" class="i-btn i-btn--aviso" data-v-rp="salir">${I.sale}Salir de reportes</button></div>
        </div>
        <div class="rp-fila2">
          <div class="i-seg rp-per" id="rpPer" role="group" aria-label="Período">
            ${PERIODOS.map(([k, t]) => `<button type="button" class="i-seg__b${R.periodo === k ? " is-on" : ""}" data-v-per="${k}">${t}</button>`).join("")}</div>
          <div class="rp-rango" id="rpRango" ${R.periodo === "rango" ? "" : "hidden"}>
            <label>Desde <input type="date" id="rpDesde" value="${R.desde}" max="${hoyISO()}"></label>
            <label>Hasta <input type="date" id="rpHasta" value="${R.hasta}" max="${hoyISO()}"></label></div>
        </div>
      </div>
      <div class="rp-cuerpo" id="rpCuerpo"></div>`;
    cargarDatos();
  }

  function diasAntes(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  async function cargarDatos() {
    const mi = ++R.req;
    const host = cuerpo.querySelector("#rpCuerpo");
    if (host) host.innerHTML = '<p class="vv-cargando">Calculando…</p>';
    const q = consulta();
    try {
      const [res, calor, prod, caj, tur] = await Promise.all([
        rapi("/resumen?" + q), rapi("/calor?" + q), rapi("/productos?" + q),
        rapi("/cajeros?" + q), rapi("/turnos?" + q)]);
      if (mi !== R.req || !R.user) return;
      R.datos = { res, calor, prod, caj, tur };
      R.error = "";
    } catch (e) {
      if (mi !== R.req || !R.user) return;
      R.error = e.message;
      R.datos = null;
    }
    pintarTablero();
  }

  function pintarTablero() {
    const host = cuerpo.querySelector("#rpCuerpo");
    if (!host) return;
    if (!R.datos) {
      host.innerHTML = `<div class="vv-vacio"><h2>No se pudieron calcular los reportes</h2><p>${esc(R.error)}</p>
        <button type="button" class="i-btn" data-v-rp="reintentar">Reintentar</button></div>`;
      return;
    }
    const top = host.scrollTop;
    host.innerHTML = tableroHTML();
    pintarTop();
    pintarTurnos();
    dibujarBarras();
    host.scrollTop = top;
  }

  const kpi = (tit, val, sub, d, extra) => `<div class="rk"><span class="rk-t">${tit}</span><b class="rk-v">${val}</b>
      <div class="rk-p"><span class="dl dl--${d.clase}">${d.texto}</span><small>${sub}</small></div>${extra || ""}</div>`;

  function kpisHTML() {
    const r = R.datos.res, c = r.actual, p = r.previo || {};
    const hay = r.hay_previo && !!r.previo;
    const dl = (a, b) => V.delta(a, b, hay);
    return `<div class="rp-kpis">
      ${kpi("Ventas", clp(c.total), "vendido", dl(c.total, p.total))}
      ${kpi("N° de ventas", miles(c.n), "ventas", dl(c.n, p.n))}
      ${kpi("Ticket promedio", clp(c.ticket), "por venta", dl(c.ticket, p.ticket))}
      ${kpi("Ganancia estimada", clp(c.ganancia), "margen " + c.margen + "%", dl(c.ganancia, p.ganancia),
        `<div class="rk-nota" title="La ganancia es lo vendido menos el costo de cada producto. Si un producto no tiene costo cargado, esa venta no entra en la cuenta.">Estimada: ${r.productos_sin_costo} producto${r.productos_sin_costo === 1 ? "" : "s"} sin costo no ${r.productos_sin_costo === 1 ? "cuenta" : "cuentan"}${c.venta_sin_costo ? " (" + clp(c.venta_sin_costo) + " vendidos)" : ""}</div>`)}
      ${kpi("Propinas", clp(c.propinas), r.propinas.tarjeta === c.propinas ? "en tarjeta" : "en total", dl(c.propinas, p.propinas))}
    </div>
    <p class="rp-vs"><b>${esc(V.rangoTexto(r.desde, r.hasta))}</b>${r.un_dia ? "" : " (" + r.dias + " días)"}${r.en_curso && r.corte ? ", hasta las " + r.corte : ""}. Los porcentajes comparan con ${esc(r.vs)}${hay ? "" : " (de ese tramo no hay datos)"}.${c.anuladas.n ? ` · ${c.anuladas.n} venta${c.anuladas.n === 1 ? "" : "s"} anulada${c.anuladas.n === 1 ? "" : "s"} (${clp(c.anuladas.total)}) no se cuenta${c.anuladas.n === 1 ? "" : "n"}.` : ""}</p>`;
  }

  function serie() {
    const r = R.datos.res;
    if (r.un_dia) {
      return { titulo: "Ventas por hora", sub: "de ese día", items: r.por_hora.map((h) => ({
        etq: String(h.hora), etqL: `${h.hora}:00 a ${h.hora + 1}:00`, total: h.total, n: h.n, fin: false })) };
    }
    return { titulo: "Ventas por día", sub: "las barras marrones son sábado y domingo", items: r.por_dia.map((d) => ({
      etq: String(+d.fecha.slice(8)), etqL: V.fechaCorta(d.fecha), total: d.total, n: d.n, fin: d.fin_de_semana })) };
  }

  function dibujarBarras() {
    const cont = cuerpo.querySelector("#rpGDias");
    if (!cont || !R.datos) return;
    const S = serie();
    const g = V.geometriaBarras(S.items, cont.clientWidth, 230, R.sel, !R.datos.res.un_dia);
    R.sel = g.sel;
    let sv = "";
    g.lineas.forEach((l) => { sv += `<line x1="${g.ml}" x2="${g.W - g.mr}" y1="${l.y}" y2="${l.y}" class="g-lin"/><text x="${g.ml - 8}" y="${l.y + 4}" text-anchor="end" class="g-eje">${esc(l.etq)}</text>`; });
    g.barras.forEach((b) => {
      sv += `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="${Math.min(4, b.w / 2)}" class="g-bar${b.fin ? " g-bar--fin" : ""}${b.sel ? " is-sel" : ""}"/>`;
      if (b.verEtq) sv += `<text x="${b.cx}" y="${g.H - 10}" text-anchor="middle" class="g-eje${b.sel ? " g-eje--sel" : ""}">${esc(b.etq)}</text>`;
      sv += `<rect x="${b.zonaX}" y="${g.mt}" width="${b.zonaW}" height="${g.ph}" fill="transparent" data-v-i="${b.i}" class="g-hit"/>`;
    });
    if (g.promedio) sv += `<line x1="${g.ml}" x2="${g.W - g.mr}" y1="${g.promedio.y}" y2="${g.promedio.y}" class="g-prom"/><text x="${g.W - g.mr - 2}" y="${g.promedio.y - 5}" text-anchor="end" class="g-promt">${esc(g.promedio.texto)}</text>`;
    cont.innerHTML = `<svg width="${g.W}" height="${g.H}" viewBox="0 0 ${g.W} ${g.H}" role="img" aria-label="${esc(S.titulo)}">${sv}</svg>`;
    const s = S.items[g.sel];
    const lee = cuerpo.querySelector("#rpGDiasLee");
    if (lee && s) lee.innerHTML = `<b>${esc(s.etqL)}</b> · ${clp(s.total)} · ${nVentas(s.n)}${s.n ? ` · ticket ${clp(Math.round(s.total / s.n))}` : ""}`;
  }
  new ResizeObserver(() => { if (R.user && reportesVisible()) dibujarBarras(); }).observe(vista);

  function pagoHTML() {
    const r = R.datos.res;
    const items = r.por_medio.slice().sort((a, b) => b.total - a.total);
    const tot = items.reduce((s, m) => s + m.total, 0) || 1, radio = 46;
    const arcos = V.arcosDona(items, radio).map((a) =>
      `<circle cx="60" cy="60" r="${radio}" fill="none" stroke="${V.COLOR_MEDIO[a.medio]}" stroke-width="22" stroke-dasharray="${a.largo} ${a.resto}" stroke-dashoffset="${a.desde}" transform="rotate(-90 60 60)"/>`).join("");
    return `<div class="dona"><svg viewBox="0 0 120 120" class="dona-svg" role="img" aria-label="Formas de pago">
        <circle cx="60" cy="60" r="${radio}" fill="none" stroke="#EFE4D5" stroke-width="22"/>${arcos}
        <text x="60" y="58" text-anchor="middle" class="dona-n">${miles(r.actual.n)}</text><text x="60" y="73" text-anchor="middle" class="dona-tx">ventas</text></svg>
      <ul class="dona-lista">${items.map((m) => `<li style="--c:${V.COLOR_MEDIO[m.medio]}"><i></i><span>${esc(m.nombre)}</span><b>${V.pct(m.total, tot)}%</b><small>${clp(m.total)}</small></li>`).join("")}</ul></div>
      ${r.n_mixtas ? `<p class="rcard-pie">${r.n_mixtas} venta${r.n_mixtas === 1 ? "" : "s"} pagada${r.n_mixtas === 1 ? "" : "s"} en dos formas se reparte${r.n_mixtas === 1 ? "" : "n"} entre las dos.</p>` : ""}`;
  }

  function catHTML() {
    const cats = R.datos.res.por_categoria;
    const tot = cats.reduce((s, x) => s + x.total, 0) || 1, mx = cats.length ? cats[0].total : 1;
    return `<ul class="hb">${cats.map((x) => `<li style="--c:${colorCat(x.id)}"><span class="hb-t"><i></i>${esc(x.nombre)}</span>
      <span class="hb-bar"><u style="width:${Math.max(2, Math.round(x.total / mx * 100))}%"></u></span><b>${clp(x.total)}</b><small>${V.pct(x.total, tot)}%</small></li>`).join("") || '<li class="hb-nada">Sin ventas en este período</li>'}</ul>`;
  }

  function heatHTML() {
    const c = R.datos.calor, hs = V.horasDelCalor(c);
    const orden = [0, 1, 2, 3, 4, 5, 6];
    let max = 1;
    orden.forEach((d) => hs.forEach((h) => { max = Math.max(max, c.celdas[d][h]); }));
    const maxT = Math.max(1, ...hs.map((h) => c.todos[h]));
    const sel = R.heat || V.celdaMejor(c);
    const celda = (v, m, d, h) => {
      const p = V.intensidad(v, m);
      return `<div class="hm-c${sel.d === d && sel.h === h ? " is-sel" : ""}" data-v-d="${d}" data-v-h="${h}" style="background:${p ? `color-mix(in srgb,#C9552B ${p}%,#F4EADB)` : "#F4EADB"}" title="${d === 7 ? "Todos los días" : V.DIAS_SEM[d]} ${h} h"></div>`;
    };
    return `<p class="hm-tit">${V.fraseCalor(c)}
        ${c.ultimas_4_semanas ? "<em>Con pocos días no se nota el patrón: se usan las últimas 4 semanas.</em>" : ""}</p>
      <div class="hm" style="--cols:${hs.length}">
        <div class="hm-f hm-f--cab"><span></span>${hs.map((h) => `<span>${h}</span>`).join("")}</div>
        ${orden.map((d) => `<div class="hm-f"><span class="hm-d">${V.DIAS_SEM_C[d]}</span>${hs.map((h) => celda(c.celdas[d][h], max, d, h)).join("")}</div>`).join("")}
        <div class="hm-f hm-f--todos"><span class="hm-d">todos</span>${hs.map((h) => celda(c.todos[h], maxT, 7, h)).join("")}</div>
      </div>
      <div class="hm-pie"><div class="hm-lee">${V.fraseCelda(c, sel)}</div>
        <div class="hm-esc"><span>menos</span><i></i><span>más</span></div></div>`;
  }

  function topHTML() {
    const L = V.listaProductos(R.datos.prod, R.topModo, R.topQ);
    const mx = Math.max(1, ...L.filas.map((f) => (R.topModo === "cant" ? f.cantidad : f.total)));
    const hoy = hoyISO();
    const cuerpoTop = L.filas.map((f, i) => {
      const col = f.categoria_id == null ? "#A8978A" : colorDeCat(f.categoria_id);
      let der = "";
      if (R.topModo === "sin") {
        const dd = f.ultima_venta ? Math.max(0, Math.round((Date.parse(hoy) - Date.parse(f.ultima_venta)) / 86400000)) : null;
        der = `<span class="tp-v"><b>${f.ultima_venta ? "hace " + dd + (dd === 1 ? " día" : " días") : "nunca"}</b><small>${f.ultima_venta ? "última venta" : "sin ventas registradas"}</small></span>`;
      } else {
        der = `<span class="tp-v"><b>${R.topModo === "cant" ? f.cantidad + " u." : clp(f.total)}</b><small>${R.topModo === "cant" ? clp(f.total) : f.cantidad + " u."}</small></span>`;
      }
      const barra = R.topModo === "sin" ? "" : `<span class="tp-bar"><u style="width:${Math.max(3, Math.round((R.topModo === "cant" ? f.cantidad : f.total) / mx * 100))}%"></u></span>`;
      const mini = f.id == null ? "" : dibujo({ k: f.dibujo || "plato", col: f.color || undefined });
      return `<li style="--c:${col}"><span class="tp-r">${R.topModo === "sin" ? "" : i + 1}</span>
        <span class="i-mini i-mini--s" style="--c:${col}">${mini}</span>
        <span class="tp-n"><b>${esc(f.nombre)}</b><small>${esc(f.categoria)}</small>${barra}</span>${der}</li>`;
    }).join("") || `<li class="tp-nada">${R.topQ ? "Ningún producto calza con esa búsqueda." : R.topModo === "sin" ? "Todos los productos se vendieron en este período." : "Sin ventas en este período."}</li>`;
    const pie = R.topQ ? `${L.filas.length} de ${L.todas} productos` : `${L.todas} producto${L.todas === 1 ? "" : "s"} · ${L.vendidos} se vendieron, ${L.sin} no`;
    return { html: cuerpoTop, pie };
  }
  function pintarTop() {
    const lista = cuerpo.querySelector("#tpLista");
    if (!lista) return;
    const t = topHTML();
    lista.innerHTML = t.html;
    cuerpo.querySelector("#tpPie").textContent = t.pie;
  }

  function cajerosHTML() {
    const filas = R.datos.caj.map((cj) => {
      const difs = cj.diferencias;
      const dTot = cj.diferencia_total;
      const chips = difs.slice(0, 10).map((x) => `<span class="df df--${V.claseDif(x.diferencia)}" title="${V.fechaCorta(x.fecha)}: ${x.diferencia === 0 ? "cuadró" : (x.diferencia > 0 ? "sobraron " : "faltaron ") + clp(Math.abs(x.diferencia))}">
        <small>${V.diaMes(x.fecha)}</small>${x.diferencia === 0 ? "&#10003;" : (x.diferencia > 0 ? "+" : MENOS) + miles(Math.abs(x.diferencia))}</span>`).join("");
      return `<div class="cj2">
        <div class="cj2-top">${avatar(cj.nombre, cj.color)}<b class="cj2-n">${esc(cj.nombre)}</b>
          <div class="cj2-c"><b>${clp(cj.total)}</b><small>vendido</small></div>
          <div class="cj2-c"><b>${miles(cj.n)}</b><small>ventas</small></div>
          <div class="cj2-c"><b>${cj.turnos}</b><small>turno${cj.turnos === 1 ? "" : "s"}</small></div>
          <div class="cj2-c cj2-c--dif ${cj.cerrados ? V.claseDif(dTot) : ""}"><b>${cj.cerrados ? (dTot === 0 ? "Cuadra" : (dTot > 0 ? "Sobró " : "Faltó ") + clp(Math.abs(dTot))) : "—"}</b><small>${cj.cerrados ? (cj.con_diferencia ? cj.con_diferencia + " de " + cj.cerrados + " turnos con diferencia" : "todos cuadraron") : "sin turnos cerrados"}</small></div></div>
        ${chips ? `<div class="cj2-chips"><span class="cj2-lab">Arqueo por turno</span>${chips}${difs.length > 10 ? `<small class="cj2-mas">+${difs.length - 10} más</small>` : ""}</div>` : ""}
      </div>`;
    }).join("");
    return filas || '<p class="hb-nada">Sin turnos ni ventas en este período.</p>';
  }

  function pintarTurnos() {
    const cuerpoT = cuerpo.querySelector("#htCuerpo");
    if (!cuerpoT) return;
    const todos = R.datos.tur;
    const ts = todos.filter((t) => V.turnoCalza(t, R.turQ, R.soloDif));
    cuerpoT.innerHTML = ts.map((t) => {
      const dif = t.diferencia;
      const arq = t.abierto ? '<span class="v-pill v-pill--curso">En curso</span>'
        : dif == null ? "—"
          : dif === 0 ? '<span class="df df--ok">&#10003; Cuadra</span>'
            : `<span class="df df--${dif > 0 ? "mas" : "menos"}">${dif > 0 ? "Sobra " : "Falta "}${clp(Math.abs(dif))}</span>`;
      const dur = V.minutosEntre(t.abierto_at, t.cerrado_at, Date.now());
      return `<tr data-v-turno="${t.id}" tabindex="0">
        <td class="ht-f">${V.fechaCorta(t.abierto_at)}</td>
        <td class="ht-q">${avatar(t.abrio, t.color)} ${esc(t.abrio)}</td>
        <td class="ht-h">${V.hhmm(t.abierto_at)} &ndash; ${t.cerrado_at ? V.hhmm(t.cerrado_at) : "ahora"}<small>${V.duracion(dur)}</small></td>
        <td class="ht-v">${clp(t.vendido)}<small>${nVentas(t.n)}</small></td>
        <td class="ht-a">${arq}</td>
        <td class="ht-b"><button type="button" class="i-btn i-btn--suave" data-v-corte="${t.id}">Ver corte</button></td></tr>`;
    }).join("") || '<tr class="vl-vacia"><td colspan="6">No hay turnos con ese filtro.</td></tr>';
    cuerpo.querySelector("#htPie").textContent = `${ts.length} de ${todos.length} turnos del período · toca uno para ver su corte completo`;
  }

  function tableroHTML() {
    const S = serie();
    return `${kpisHTML()}
      <div class="rp-grid">
        <section class="rcard rcard--dias"><h3>${S.titulo} <em>${S.sub}</em></h3>
          <div id="rpGDias" class="grafico"></div>
          <div class="gsel"><button type="button" class="i-ico" data-v-paso="-1" aria-label="Anterior">${I.izq}</button>
            <div id="rpGDiasLee" class="gsel-t"></div>
            <button type="button" class="i-ico" data-v-paso="1" aria-label="Siguiente">${I.der}</button></div>
        </section>
        <section class="rcard rcard--pago"><h3>Formas de pago <em>cuánto se pagó con cada una</em></h3>${pagoHTML()}</section>
        <section class="rcard rcard--hora"><h3>¿A qué hora se vende más? <em>cuanto más oscuro, más plata</em></h3><div id="hmBox">${heatHTML()}</div></section>
        <section class="rcard rcard--cat"><h3>Ventas por categoría</h3>${catHTML()}</section>
        <section class="rcard rcard--top"><h3>Productos</h3>
          <div class="rcard-ctl">
            <div class="i-seg i-seg--chico" id="tpModo">
              <button type="button" class="i-seg__b${R.topModo === "cant" ? " is-on" : ""}" data-v-modo="cant">Más vendidos</button>
              <button type="button" class="i-seg__b${R.topModo === "plata" ? " is-on" : ""}" data-v-modo="plata">Más plata</button>
              <button type="button" class="i-seg__b${R.topModo === "sin" ? " is-on" : ""}" data-v-modo="sin">Sin ventas</button></div>
            ${buscadorHTML("tpQ", "Buscar un producto", R.topQ)}</div>
          <ol class="tp" id="tpLista"></ol><div class="rcard-pie" id="tpPie"></div>
        </section>
        <section class="rcard rcard--caj"><h3>Por cajero <em>ventas y diferencias de arqueo</em></h3>${cajerosHTML()}</section>
        <section class="rcard rcard--his"><h3>Historial de turnos</h3>
          <div class="rcard-ctl">
            ${buscadorHTML("htQ", "Buscar por cajero o día", R.turQ)}
            <button type="button" class="i-chip i-chip--m${R.soloDif ? " is-on" : ""}" id="htDif">Solo con diferencia</button></div>
          <div class="ht"><table class="ht-t"><thead><tr><th class="ht-f">Día</th><th class="ht-q">Quién</th><th class="ht-h">Desde &ndash; hasta</th><th class="ht-v">Vendido</th><th class="ht-a">Arqueo del efectivo</th><th class="ht-b"></th></tr></thead>
            <tbody id="htCuerpo"></tbody></table></div>
          <div class="rcard-pie" id="htPie"></div>
        </section>
      </div>`;
  }

  /* El corte completo de un turno del historial: el mismo resumen de «Mi turno», para leer. */
  async function abrirCorteDeTurno(id) {
    let c;
    try { c = await rapi("/turnos/" + id); } catch (e) { return avisar(e.message, true); }
    const t = c.turno;
    abrirDlg("i-dlg--ficha", `${cabeceraDlg("Corte del turno de " + esc(t.abrio),
      `${V.fechaLarga(t.abierto_at)} · ${V.hhmm(t.abierto_at)} a ${t.cerrado_at ? V.hhmm(t.cerrado_at) : "ahora (sigue abierto)"}`)}
      <div class="i-cuerpo vt-dlg-cuerpo"><div class="vt vt--dlg" id="vCorteDlg"></div></div>
      <footer class="dialogo__pie"><span class="i-msg">Solo lectura: un turno de otro día no se modifica.</span>
        ${t.abierto ? "" : `<button type="button" class="i-btn" id="vCorteImp">${I.imprime}Imprimir corte</button>`}
        <button type="button" class="i-btn i-btn--prin" data-v-x>Listo</button></footer>`);
    montarCorte(dlgEl.querySelector("#vCorteDlg"), c, { vivo: false, volver: () => abrirCorteDeTurno(id) });
    const imp = dlgEl.querySelector("#vCorteImp");
    if (imp) imp.onclick = () => imprimir("/cierre/" + id);
  }

  function exportar() {
    const q = consulta();
    window.open(`/api/v1/reportes/exportar?tipo=ventas&${q}`, "_blank");
    // Dos archivos, como siempre: el resumen de ventas y el detalle por producto.
    setTimeout(() => window.open(`/api/v1/reportes/exportar?tipo=detalle&${q}`, "_blank"), 400);
    avisar("Descargando el reporte de este período (ventas y detalle por producto)");
  }

  conectarEventos();
  function conectarEventos() {
    vista.addEventListener("click", (e) => {
      const g = e.target;
      const pk = g.closest("[data-v-pk]");
      if (pk) return teclaPin(pk.dataset.vPk);
      const pin = g.closest("[data-v-pin]");
      if (pin) {
        const a = pin.dataset.vPin;
        if (a === "entrar") probarPin();
        else if (a === "otro") { R.msg = null; R.pin = ""; pintarPin(); }
        else if (a === "miturno") { R.msg = null; R.pin = ""; mostrarSub("turno"); }
        return;
      }
      if (!R.user) return;
      const rp = g.closest("[data-v-rp]");
      if (rp) {
        const a = rp.dataset.vRp;
        if (a === "salir") salirDeReportes();
        else if (a === "exportar") exportar();
        else if (a === "reintentar") cargarDatos();
        return;
      }
      const per = g.closest("[data-v-per]");
      if (per) {
        R.periodo = per.dataset.vPer; R.sel = null; R.heat = null;
        cuerpo.querySelectorAll("#rpPer .i-seg__b").forEach((b) => b.classList.toggle("is-on", b === per));
        if (R.periodo === "rango" && !R.desde) { R.hasta = hoyISO(); R.desde = diasAntes(13); }
        const rango = cuerpo.querySelector("#rpRango");
        rango.hidden = R.periodo !== "rango";
        if (R.periodo === "rango") { cuerpo.querySelector("#rpDesde").value = R.desde; cuerpo.querySelector("#rpHasta").value = R.hasta; }
        cargarDatos();
        return;
      }
      const hit = g.closest(".g-hit");
      if (hit) { R.sel = +hit.dataset.vI; dibujarBarras(); return; }
      const paso = g.closest("[data-v-paso]");
      if (paso) { R.sel = (R.sel || 0) + +paso.dataset.vPaso; R.sel = Math.max(0, R.sel); dibujarBarras(); return; }
      const cel = g.closest(".hm-c");
      if (cel) { R.heat = { d: +cel.dataset.vD, h: +cel.dataset.vH }; cuerpo.querySelector("#hmBox").innerHTML = heatHTML(); return; }
      const modo = g.closest("#tpModo [data-v-modo]");
      if (modo) {
        R.topModo = modo.dataset.vModo;
        cuerpo.querySelectorAll("#tpModo .i-seg__b").forEach((b) => b.classList.toggle("is-on", b === modo));
        pintarTop();
        return;
      }
      const lq = g.closest("[data-v-limpia]");
      if (lq && (lq.dataset.vLimpia === "tpQ" || lq.dataset.vLimpia === "htQ")) {
        const id = lq.dataset.vLimpia, inp = cuerpo.querySelector("#" + id);
        inp.value = "";
        if (id === "tpQ") { R.topQ = ""; pintarTop(); } else { R.turQ = ""; pintarTurnos(); }
        inp.focus();
        return;
      }
      if (g.closest("#htDif")) {
        R.soloDif = !R.soloDif;
        g.closest("#htDif").classList.toggle("is-on", R.soloDif);
        pintarTurnos();
        return;
      }
      const fila = g.closest("tr[data-v-turno]");
      if (fila) abrirCorteDeTurno(+fila.dataset.vTurno);
    });
    vista.addEventListener("input", (e) => {
      const g = e.target;
      if (g.id === "tpQ") { R.topQ = g.value; pintarTop(); }
      else if (g.id === "htQ") { R.turQ = g.value; pintarTurnos(); }
    });
    vista.addEventListener("change", (e) => {
      if (e.target.id === "rpDesde" || e.target.id === "rpHasta") {
        const d = cuerpo.querySelector("#rpDesde").value, h = cuerpo.querySelector("#rpHasta").value;
        if (!d || !h) return;
        R.desde = d <= h ? d : h;
        R.hasta = d <= h ? h : d;
        R.sel = null; R.heat = null;
        cuerpo.querySelector("#rpDesde").value = R.desde;
        cuerpo.querySelector("#rpHasta").value = R.hasta;
        cargarDatos();
      }
    });
    vista.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.matches && e.target.matches("tr[data-v-turno]")) e.target.click();
    });
  }

  /* ==========================================================
     LO QUE USA app.js
     ========================================================== */
  window.Ventas = {
    /* Al tocar la pestaña. Siempre parte en «Mi turno». */
    abrir() {
      // Al tocar una pestaña, verVista corre dos veces (el clic y el cambio de dirección #/dia).
      // La segunda no puede mandar de vuelta a «Mi turno» a quien ya tocó Reportes.
      if (vista.dataset.listo && Date.now() - ultimaApertura < 600) return;
      ultimaApertura = Date.now();
      if (!vista.dataset.listo) montar();
      mostrarSub("turno");
    },
    refrescar,
    /* El candado, el cambio de usuario o el bloqueo cierran Reportes de inmediato. */
    cerrarReportes() { if (R.user) salirDeReportes(); },
    /* Para las pruebas con navegador. */
    _estado: R,
  };
})();
