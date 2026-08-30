/* ==========================================================
   EL LECTOR DE CÓDIGOS DE BARRA

   Un lector de pistola USB no es un aparato: para Windows es un TECLADO. Manda
   los 13 dígitos como si alguien los tecleara muy rápido y termina con Enter.
   No hay driver, ni puerto, ni permiso que pedir.

   Y ahí está el problema, que es la razón de que este archivo exista.

   ---------------------------------------------------------------
   LO QUE PASABA SIN ESTO — no es teórico, es el flujo normal
   ---------------------------------------------------------------

   La caja ya tiene dos oyentes globales de teclado, y los dos se comen el
   escaneo, algunos de forma cara:

   · Con el diálogo de COBRO abierto y el foco en «Paga con», los 13 dígitos
     entran como monto y el Enter final llama a confirmarVenta().
     O sea: un escaneo accidental COBRABA LA VENTA con «paga con
     $7.801.610.001.196».

   · Con el carrito armado y el foco en ningún lado, el Enter del lector abría
     solo el diálogo de cobro. El código se perdía y aparecía la pantalla de
     pago.

   · En la pantalla del PIN, el teclado en pantalla confirma solo al juntar 4
     dígitos: un código de 13 se convertía en TRES intentos de entrar seguidos.
     Escanear 200 productos frente al candado son 600 intentos en dos minutos.

   ---------------------------------------------------------------
   CÓMO SE ARREGLA
   ---------------------------------------------------------------

   Este oyente va en `window` y en fase de CAPTURA (el `true` del final). La
   captura en window corre ANTES que cualquier oyente de burbujeo en document,
   así que le gana a los otros dos sin importar en qué orden se carguen los
   <script>. Por eso este archivo va antes que app.js en index.html.

   Cómo sabe que es el lector y no una persona: por el hueco entre teclas. Un
   lector manda todo en 30-150 ms, o sea 3-20 ms entre tecla y tecla. Una
   persona no baja de 80 ms. El corte en 40 ms deja un margen cómodo: para un
   falso positivo alguien tendría que escribir seis dígitos seguidos a más de 25
   por segundo.

   Lo honesto: no se puede saber que empezó una ráfaga hasta la SEGUNDA tecla,
   así que el primer dígito alcanza a filtrarse al campo que tuviera el foco.
   Se limpia después. Si el lector permite programarle un prefijo —casi todos—
   eso sería 100% confiable y esta heurística sobraría; se deja porque no se
   puede suponer qué lector compró el local.
   ========================================================== */
(function () {
  "use strict";

  var MS_ENTRE_TECLAS = 40;    // lector: 3-20 · persona: 80-300
  var LARGO_MINIMO = 6;        // el más corto de verdad es EAN-8
  var LARGO_MAXIMO = 20;       // más que eso no es un código, es alguien jugando
  var MS_SIN_ENTER = 80;       // red por si el lector no manda Enter

  var buf = "";
  var ultima = 0;
  var reloj = null;
  var campoTocado = null;      // dónde se filtró el primer dígito
  var valorAntes = null;

  /* Se le asigna desde app.js. Mientras no exista, el escáner igual PROTEGE:
     consume las ráfagas para que no cobren una venta ni intenten un PIN. */
  window.Escaner = { alLeer: null };

  function candadoArriba() {
    var c = document.getElementById("candado");
    return !!(c && !c.hidden);
  }

  function limpiarLoQueSeFiltro() {
    // El primer dígito de la ráfaga alcanzó a entrar al campo con foco, porque
    // recién con el segundo se sabe que era el lector. Se devuelve como estaba.
    if (campoTocado && valorAntes !== null && campoTocado.isConnected) {
      if (campoTocado.value !== valorAntes) {
        campoTocado.value = valorAntes;
        campoTocado.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    campoTocado = null;
    valorAntes = null;
  }

  function soltar() {
    var codigo = buf;
    buf = "";
    clearTimeout(reloj);
    reloj = null;
    limpiarLoQueSeFiltro();
    if (codigo.length < LARGO_MINIMO) return;

    // Frente al candado se consume y no se hace nada. Un código de barras no es
    // el PIN de nadie, y dejarlo pasar convierte cada escaneo en intentos de
    // entrar.
    if (candadoArriba()) return;

    if (typeof window.Escaner.alLeer === "function") {
      window.Escaner.alLeer(codigo);
    }
  }

  window.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;

    // La marca del EVENTO, no Date.now(): si la caja está repintando la grilla,
    // el JS puede correr tarde y Date.now() daría huecos falsos de 200 ms.
    var t = e.timeStamp;
    var rapido = (t - ultima) < MS_ENTRE_TECLAS;
    ultima = t;

    if (e.key === "Enter") {
      if (buf.length >= LARGO_MINIMO && rapido) {
        // Este Enter es del lector. Que NO llegue a app.js: allá abre el cobro
        // o confirma la venta.
        e.preventDefault();
        e.stopPropagation();
        soltar();
      } else {
        buf = "";
        limpiarLoQueSeFiltro();
      }
      return;
    }

    if (e.key.length !== 1) return;              // Shift, Tab, F1, muertas
    if (!/[0-9]/.test(e.key)) {                  // los códigos son puros dígitos
      buf = "";
      limpiarLoQueSeFiltro();
      return;
    }

    if (rapido && buf.length) {
      // Segunda tecla en adelante: es una ráfaga. Se traga.
      e.preventDefault();
      e.stopPropagation();
      if (buf.length === 1) {
        // Recién ahora se sabe. Se cierra el teclado en pantalla, que si no se
        // come el resto o confirma un PIN a los 4 dígitos.
        if (window.Teclado && window.Teclado.abierto) window.Teclado.cerrar();
      }
      if (buf.length < LARGO_MAXIMO) buf += e.key;
    } else {
      // Primera tecla: todavía no se sabe si es el lector o una persona. Se deja
      // pasar, y se guarda dónde cayó para poder devolverlo.
      buf = e.key;
      var f = document.activeElement;
      if (f && typeof f.value === "string" && f.tagName === "INPUT") {
        campoTocado = f;
        valorAntes = f.value;
      } else {
        campoTocado = null;
        valorAntes = null;
      }
    }

    clearTimeout(reloj);
    reloj = setTimeout(soltar, MS_SIN_ENTER);
  }, true);
}());
