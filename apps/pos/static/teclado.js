/* ==========================================================
   TECLADO NUMÉRICO EN PANTALLA
   Archivo: apps/pos/static/teclado.js
   Se carga en index.html ANTES de app.js, y también en la página del PIN
   de acceso.py:
       <script src="/static/teclado.js?v=1"></script>

   POR QUÉ existe: en la pantalla táctil, cualquier input numérico hace
   saltar el teclado de Windows, que ocupa la mitad de abajo — o sea, justo
   donde está "Confirmar venta". Este teclado lo reemplaza y, además, sabe
   subir el diálogo para no taparlo.

   POR QUÉ se engancha solo: los ocho campos numéricos del POS ya declaran
   inputmode="numeric" y TODOS se leen con soloNumeros(), que borra los
   puntos. Por eso acá se puede escribir "12.000" con separador de miles sin
   que nadie más en el programa se entere, y por eso este archivo no obliga
   a tocar ni un manejador existente: escribe en el campo y dispara "input",
   que es lo que calcularVuelto, conectarArqueo y pintarRetiro ya escuchan.
   ========================================================== */
(function () {
  "use strict";

  // Cada modo decide cuántos dígitos acepta, cómo se ve el eco grande y qué
  // se escribe en el campo.
  const MODOS = {
    monto: {
      largo: 8, extra: "000",
      eco:   (b) => "$" + Number(b || 0).toLocaleString("es-CL"),
      valor: (b) => (b ? Number(b).toLocaleString("es-CL") : ""),
    },
    entero: {                                  // arqueo, cantidades de inventario
      largo: 4, extra: null,
      eco:   (b) => String(Number(b || 0)),
      valor: (b) => (b ? String(Number(b)) : ""),
    },
    pin: {                                     // login y PIN de red
      largo: 4, extra: null, centrado: true, auto: true,
      eco:   (b) => (b ? "●".repeat(b.length) : "····"),
      valor: (b) => b,
    },
  };

  // El orden de la grilla. "ok" ocupa dos filas y el 0 se estira para llenar.
  const TECLAS = ["7","8","9","borrar","4","5","6","limpiar","1","2","3","ok","0","extra"];
  const ROTULO = { borrar: "⌫", limpiar: "C", ok: "Listo" };
  const SELECTOR = 'input[data-teclado], input[inputmode="numeric"]';

  let caja = null, eco = null, titulo = null, estado = null, volcando = false;

  /* ---------------- armado ---------------- */
  function construir() {
    caja = document.createElement("div");
    caja.className = "teclado";
    caja.id = "teclado";
    caja.hidden = true;
    caja.setAttribute("role", "group");
    caja.setAttribute("aria-label", "Teclado numérico");
    caja.innerHTML =
      '<div class="teclado__caja">' +
        '<div class="teclado__cab">' +
          '<span class="teclado__tit"></span>' +
          '<output class="teclado__eco"></output>' +
        '</div>' +
        '<div class="teclado__grilla"></div>' +
      '</div>';
    document.body.appendChild(caja);
    titulo = caja.querySelector(".teclado__tit");
    eco    = caja.querySelector(".teclado__eco");

    // pointerdown + preventDefault: si el foco se va del campo a la tecla, el
    // campo pierde el caret y pintarArqueo() le pisa el valor de vuelta (mira
    // el guard `if (document.activeElement !== campo)` de app.js).
    caja.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".teclado__t")) e.preventDefault();
    });
    caja.addEventListener("click", (e) => {
      const t = e.target.closest(".teclado__t");
      if (t) pulsar(t.dataset.tecla);
    });
  }

  function pintarTeclas(modo) {
    const cfg = MODOS[modo];
    caja.querySelector(".teclado__grilla").innerHTML = TECLAS.map((k) => {
      if (k === "extra" && !cfg.extra) return "";        // sin extra, el 0 ocupa 3
      const cls = ["teclado__t"];
      if (k === "ok") cls.push("teclado__t--ok");
      else if (k === "borrar" || k === "limpiar") cls.push("teclado__t--acc");
      if (k === "0") cls.push(cfg.extra ? "teclado__t--ancho" : "teclado__t--triple");
      const txt = k === "extra" ? cfg.extra : (ROTULO[k] !== undefined ? ROTULO[k] : k);
      return '<button type="button" class="' + cls.join(" ") +
             '" data-tecla="' + k + '" tabindex="-1">' + txt + "</button>";
    }).join("");
  }

  /* ---------------- teclas ---------------- */
  function pulsar(k) {
    if (!estado) return;
    // El diálogo se pudo haber redibujado debajo (mostrarCuadre() rehace el
    // pie y el campo #tFondo). Si el campo ya no está en la página, cerramos.
    if (!estado.campo.isConnected) return cerrar();
    const cfg = MODOS[estado.modo];

    if (k === "ok") return confirmar();
    if (k === "limpiar") estado.buf = "";
    else if (k === "borrar") estado.buf = estado.buf.slice(0, -1);
    else {
      const d = k === "extra" ? cfg.extra : k;
      if (!estado.buf && d === "000") return;             // no se empieza en cero
      if ((estado.buf + d).length > cfg.largo) return;
      estado.buf = (estado.buf + d).replace(/^0+(?=\d)/, "");
    }
    volcar();
    if (cfg.auto && estado.buf.length === cfg.largo) confirmar();
  }

  function volcar() {
    const cfg = MODOS[estado.modo];
    eco.textContent = cfg.eco(estado.buf);
    volcando = true;                                       // no re-leernos a nosotros mismos
    estado.campo.value = cfg.valor(estado.buf);
    estado.campo.dispatchEvent(new Event("input", { bubbles: true }));
    volcando = false;
  }

  function confirmar() {
    const fn = estado.op.alConfirmar, buf = estado.buf, campo = estado.campo;
    cerrar();
    if (fn) fn(buf, campo);
  }

  /* ---------------- abrir y cerrar ---------------- */
  function tituloDe(campo) {
    const fila = campo.closest("[data-den]");
    if (fila) return "Cuántos de $" + Number(fila.dataset.den).toLocaleString("es-CL");
    const et = campo.closest("label"), s = et && et.querySelector("span");
    return s ? s.textContent.trim() : "Número";
  }

  function abrir(campo, op) {
    op = op || {};
    if (!caja) construir();
    const modo = op.modo || campo.dataset.teclado || "monto";
    const cfg = MODOS[modo];
    if (!cfg) return;
    const centrado = !!(op.centrado || cfg.centrado);

    estado = { campo: campo, modo: modo, op: op,
               buf: String(campo.value || "").replace(/\D/g, "").slice(0, cfg.largo) };

    // Sin esto Windows abre ADEMÁS su teclado táctil y quedan dos apilados.
    // El data-teclado es obligatorio: al poner inputmode="none" el campo deja
    // de calzar con input[inputmode="numeric"] y no volvería a abrirlo nunca.
    campo.setAttribute("inputmode", "none");
    if (!campo.dataset.teclado) campo.dataset.teclado = modo;

    titulo.textContent = op.titulo || tituloDe(campo);
    eco.textContent = cfg.eco(estado.buf);
    caja.classList.toggle("teclado--centro", centrado);
    pintarTeclas(modo);
    caja.hidden = false;

    if (!centrado) {
      document.documentElement.style.setProperty("--alto-teclado", caja.offsetHeight + "px");
      document.querySelectorAll(".capa.is-on").forEach((c) => c.classList.add("con-teclado"));
      acomodar();
    }
  }

  // Si el campo quedó debajo del teclado, subimos su contenedor con scroll.
  function acomodar() {
    const tope = window.innerHeight - caja.offsetHeight - 16;
    const r = estado.campo.getBoundingClientRect();
    if (r.bottom <= tope) return;
    let n = estado.campo.parentElement;
    while (n && n !== document.body) {
      const ov = getComputedStyle(n).overflowY;
      if ((ov === "auto" || ov === "scroll") && n.scrollHeight > n.clientHeight) {
        n.scrollTop += (r.bottom - tope) + 20;
        return;
      }
      n = n.parentElement;
    }
  }

  function cerrar() {
    if (!caja || caja.hidden) return;
    caja.hidden = true;
    document.documentElement.style.setProperty("--alto-teclado", "0px");
    document.querySelectorAll(".con-teclado").forEach((c) => c.classList.remove("con-teclado"));
    estado = null;
  }

  /* ---------------- ¿se usa este teclado? ----------------
     Apagado por defecto desde la 2.5. La caja se diseñó "táctil primero"
     pensando en una pantalla táctil que todavía no existe; en el notebook del
     local hay un teclado de verdad, y un teclado dibujado que se abre solo tapa
     media pantalla y estorba justo para lo que uno quiere hacer, que es
     escribir. Cuando llegue la pantalla táctil se prende desde los ajustes y
     vuelve entero: el código no se borró. */
  let SE_USA = false;
  function encender(siONo) {
    SE_USA = !!siONo;
    if (!SE_USA && estado) cerrar();
  }

  /* ---------------- enganche automático ---------------- */
  document.addEventListener("focusin", (e) => {
    if (!SE_USA) return;                 // con teclado de verdad, no estorbamos
    const campo = e.target.closest && e.target.closest(SELECTOR);
    if (campo) { if (!estado || estado.campo !== campo) abrir(campo); return; }
    if (estado && !caja.contains(e.target)) cerrar();
  });

  // focusin no alcanza: tocar un pedazo de fondo que no toma foco no lo dispara.
  document.addEventListener("pointerdown", (e) => {
    if (!estado || caja.contains(e.target)) return;
    if (e.target.closest && e.target.closest(SELECTOR) === estado.campo) return;
    cerrar();
  }, true);

  // El dueño tiene teclado físico: inputmode="none" no lo bloquea, así que si
  // escribe a mano hay que releer el campo o el eco miente.
  document.addEventListener("input", (e) => {
    if (!estado || volcando || e.target !== estado.campo) return;
    const cfg = MODOS[estado.modo];
    estado.buf = String(e.target.value).replace(/\D/g, "").slice(0, cfg.largo);
    eco.textContent = cfg.eco(estado.buf);
  });

  /* El teclado FÍSICO también escribe acá.
     Hace falta porque el campo del PIN está oculto: nunca toma el foco, así que
     el navegador no le manda las teclas y sin esto el dueño no podía entrar
     desde el notebook. Vale para los tres modos, no solo el PIN. */
  document.addEventListener("keydown", (e) => {
    if (!estado) return;
    if (e.key === "Escape") return cerrar();
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    // Si el foco está en el propio campo, escribe el navegador y el oyente de
    // "input" sincroniza el eco: meter mano acá duplicaría cada tecla.
    if (document.activeElement === estado.campo) return;

    if (/^[0-9]$/.test(e.key)) { e.preventDefault(); return pulsar(e.key); }
    if (e.key === "Backspace") { e.preventDefault(); return pulsar("borrar"); }
    if (e.key === "Delete")    { e.preventDefault(); return pulsar("limpiar"); }
    if (e.key === "Enter")     { e.preventDefault(); return pulsar("ok"); }
  });
  window.addEventListener("resize", () => { if (estado) acomodar(); });

  if (document.body) construir();
  else document.addEventListener("DOMContentLoaded", construir);

  window.Teclado = { abrir: abrir, cerrar: cerrar, encender: encender,
                     get seUsa() { return SE_USA; },
                     get abierto() { return !!estado; } };
})();
