/* ==========================================================
   TECLADO NUMÉRICO EN PANTALLA
   Archivo: apps/pos/static/teclado.js
   Se carga en index.html ANTES de app.js, y también en la página del PIN
   de acceso.py:
       <script src="/static/teclado.js?v=1"></script>

   POR QUÉ existe: en la pantalla táctil, cualquier input numérico hace
   saltar el teclado de Windows, que ocupa la mitad de abajo — o sea, justo
   donde está "Confirmar venta". Este teclado lo reemplaza.

   Son DOS teclados con la misma distribución de teléfono:

       [1][2][3]
       [4][5][6]
       [7][8][9]
       [✱][0][⌫]

   · El PANEL de los campos: flota al costado izquierdo, centrado en alto, y
     se abre solo al tocar un campo numérico. No tapa el diálogo (que se corre
     a la derecha, ver .capa.con-teclado) ni el botón de confirmar. Sin botón
     "Listo": el valor ya se escribe en el campo en vivo. Acá ✱ vale "000" en
     el modo monto y está apagada en los demás.
   · El teclado FIJO de la pantalla de venta (#mult, en su franja de abajo a la
     derecha de la zona de productos):
     sirve para multiplicar. Se escribe un número, se toca ✱ y luego un
     producto: entran esa cantidad de una vez. Ver `multiplicador` más abajo.

   En los dos, ⌫ borra el último dígito y, mantenida ~0,6 s, borra todo.

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

  // El orden de la grilla de teléfono. «extra» es ✱ (000 en los montos).
  const TECLAS = ["1","2","3","4","5","6","7","8","9","extra","0","borrar"];
  const SELECTOR = 'input[data-teclado], input[inputmode="numeric"]';
  const MS_BORRAR_TODO = 600;                  // ⌫ mantenida: borra todo

  let caja = null, eco = null, titulo = null, estado = null, volcando = false;

  /* ---------------- la grilla, común a los dos teclados ---------------- */
  // Qué se dibuja en cada tecla. `extra` cambia según quién la pida: en el panel
  // de un campo es «000» (solo montos) y en el de multiplicar, «✱».
  function teclasDe(modo) {
    const cfg = modo && MODOS[modo];
    return TECLAS.map((k) => {
      if (k === "borrar") return { tecla: k, rotulo: "⌫", etiqueta: "Borrar", acc: true };
      if (k === "extra") {
        if (!modo) return { tecla: k, rotulo: "✱", etiqueta: "Multiplicar", acc: true };
        return cfg && cfg.extra
          ? { tecla: k, rotulo: cfg.extra, etiqueta: "Tres ceros", acc: true }
          : { tecla: k, rotulo: "✱", etiqueta: "No disponible", acc: true, apagada: true };
      }
      return { tecla: k, rotulo: k };
    });
  }

  function grillaHTML(modo) {
    return teclasDe(modo).map((t) =>
      '<button type="button" class="teclado__t' + (t.acc ? " teclado__t--acc" : "") +
      '" data-tecla="' + t.tecla + '" tabindex="-1"' +
      (t.etiqueta ? ' aria-label="' + t.etiqueta + '"' : "") +
      (t.apagada ? " disabled" : "") + ">" + t.rotulo + "</button>"
    ).join("");
  }

  // Toque corto = `corto(tecla)`; ⌫ mantenida = `largo()`. pointerdown con
  // preventDefault: si el foco se va del campo a la tecla, el campo pierde el
  // caret y pintarArqueo() le pisa el valor de vuelta (mira el guard
  // `if (document.activeElement !== campo)` de app.js).
  function enlazar(contenedor, corto, largo) {
    let reloj = null, fueLargo = false;
    const soltar = () => { clearTimeout(reloj); reloj = null; };
    contenedor.addEventListener("pointerdown", (e) => {
      const t = e.target.closest(".teclado__t");
      if (!t) return;
      e.preventDefault();
      fueLargo = false;
      if (t.dataset.tecla === "borrar") {
        soltar();
        reloj = setTimeout(() => { fueLargo = true; largo(); }, MS_BORRAR_TODO);
      }
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((ev) =>
      contenedor.addEventListener(ev, soltar));
    // Mantener apretado no debe abrir el menú contextual del dedo.
    contenedor.addEventListener("contextmenu", (e) => {
      if (e.target.closest(".teclado__t")) e.preventDefault();
    });
    contenedor.addEventListener("click", (e) => {
      const t = e.target.closest(".teclado__t");
      if (!t || t.disabled) return;
      if (fueLargo) { fueLargo = false; return; }   // ya borró todo al mantener
      corto(t.dataset.tecla);
    });
  }

  /* ---------------- el panel de los campos ---------------- */
  function construir() {
    if (caja) return;
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
    enlazar(caja, pulsar, () => pulsar("limpiar"));
    construirMult();
  }

  function pintarTeclas(modo) {
    caja.querySelector(".teclado__grilla").innerHTML = grillaHTML(modo);
  }

  /* ---------------- teclas ---------------- */
  function pulsar(k) {
    if (!estado) return;
    // El diálogo se pudo haber redibujado debajo (mostrarCuadre() rehace el
    // pie y el campo #tFondo). Si el campo ya no está en la página, cerramos.
    if (!estado.campo.isConnected) return cerrar();
    const cfg = MODOS[estado.modo];

    if (k === "limpiar") estado.buf = "";
    else if (k === "borrar") estado.buf = estado.buf.slice(0, -1);
    else {
      if (k === "extra" && !cfg.extra) return;            // ✱ solo vale en montos
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

  // Ya no hay botón «Listo»: solo confirman el PIN al juntar sus dígitos y el
  // Enter del teclado físico.
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

    // El panel flota a la izquierda y no tapa nada del centro ni de abajo: lo
    // único que hace falta es correr los diálogos que sí quedarían debajo de él
    // (en 1024 px de ancho el cobro mide casi todo; en 1366 no hace falta y el
    // diálogo no se mueve). Ya no hay que subirlos ni reservar alto: el viejo
    // --alto-teclado y acomodar() sobraron.
    clearTimeout(soltarCapas);
    if (!centrado) {
      const borde = caja.getBoundingClientRect().right + 12;
      document.querySelectorAll(".capa.is-on").forEach((c) => {
        const d = c.querySelector(".dialogo");
        if (d && d.getBoundingClientRect().left < borde) c.classList.add("con-teclado");
      });
    }
  }

  // El diálogo vuelve a su lugar un instante DESPUÉS de cerrar el panel: tocar
  // «Cancelar» cierra el panel en pointerdown, y si el diálogo se moviera ahí
  // mismo el dedo soltaría sobre otro lugar y el toque se perdería.
  let soltarCapas = null;
  function cerrar() {
    if (!caja || caja.hidden) return;
    caja.hidden = true;
    estado = null;
    clearTimeout(soltarCapas);
    soltarCapas = setTimeout(() => {
      if (estado) return;                      // se abrió otro campo mientras tanto
      document.querySelectorAll(".con-teclado").forEach((c) => c.classList.remove("con-teclado"));
    }, 350);
  }

  /* ---------------- el multiplicador de la pantalla de venta ----------------
     «2 ✱» y tocar Latte → 2 Latte de una vez. Es estado puro (sin DOM) para que
     la prueba lo corra en Node; app.js solo llama a tomar() al tocar un producto.

       · dígitos: hasta 2 (1 a 99); un 0 inicial no entra.
       · ✱: arma la cantidad escrita (si hay una). El visor muestra «2 ×».
       · ⌫: borra el último dígito; con ✱ armado, primero lo desarma.
         Mantenida, borra todo.
       · un dígito nuevo con ✱ armado empieza otra cantidad.
       · tomar(): lo que pide el producto tocado. Con ✱ armado devuelve la
         cantidad; sin él, 1. Siempre deja el visor limpio, así que números sin
         ✱ no multiplican nada.

     NO se escucha el teclado físico: el lector de códigos de barra escribe
     dígitos por ahí y se pisarían (ver escaner.js). */
  const MAX_MULT = 2;
  const multiplicador = {
    buf: "", armado: false,
    tecla(k) {
      if (/^[0-9]$/.test(k)) {
        if (this.armado) { this.buf = ""; this.armado = false; }
        if (this.buf.length >= MAX_MULT) return pintarMult();
        if (this.buf === "" && k === "0") return pintarMult();
        this.buf += k;
      } else if (k === "extra") {
        if (this.buf && Number(this.buf) >= 1) this.armado = true;
      } else if (k === "borrar") {
        if (this.armado) this.armado = false;
        else this.buf = this.buf.slice(0, -1);
      } else if (k === "limpiar") {
        this.buf = ""; this.armado = false;
      }
      pintarMult();
    },
    visor() { return this.armado ? this.buf + " ×" : this.buf; },
    tomar() {
      // Con el modo táctil apagado el multiplicador no existe: siempre 1.
      const n = SE_USA && this.armado ? Number(this.buf) : 1;
      this.buf = ""; this.armado = false;
      pintarMult();
      return n;
    },
  };

  let multCaja = null, multVisor = null;
  function construirMult() {
    multCaja = document.getElementById("mult");
    if (!multCaja) return;                   // la página del PIN no lo tiene
    multCaja.innerHTML =
      '<div class="mult__lado">' +
        '<output class="mult__visor" aria-live="polite"></output>' +
        '<p class="mult__ayuda">Escribe un número, toca ✱ y luego el producto.</p>' +
      "</div>" +
      '<div class="mult__grilla">' + grillaHTML(null) + "</div>";
    multVisor = multCaja.querySelector(".mult__visor");
    enlazar(multCaja, (k) => multiplicador.tecla(k), () => multiplicador.tecla("limpiar"));
    multCaja.hidden = !SE_USA;
    pintarMult();
  }

  function pintarMult() {
    if (!multVisor) return;
    const v = multiplicador.visor();
    multVisor.textContent = v || "Cantidad";
    multVisor.classList.toggle("mult__visor--vacio", !v);
    multVisor.classList.toggle("mult__visor--armado", multiplicador.armado);
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
    if (!SE_USA) multiplicador.tecla("limpiar");
    if (multCaja) multCaja.hidden = !SE_USA;
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
    if (e.key === "Enter")     { e.preventDefault(); return confirmar(); }
  });

  if (document.body) construir();
  else document.addEventListener("DOMContentLoaded", construir);

  window.Teclado = { abrir: abrir, cerrar: cerrar, encender: encender,
                     multiplicador: multiplicador,
                     teclasDe: teclasDe, grillaHTML: grillaHTML,
                     get seUsa() { return SE_USA; },
                     get abierto() { return !!estado; } };
})();
