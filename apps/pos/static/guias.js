/* ==========================================================
   Las guías que se leen dentro de la caja.

   Es TEXTO, no programa: vive en su propio archivo para poder corregirlo sin
   tocar el código de la caja, y viaja en una actualización como cualquier otro
   archivo.

   Cómo se escriben: se le habla al dueño de una cafetería, de pie, con el local
   abierto. Frases cortas, ejemplos con plata de verdad, y nada de palabras del
   programa ("registro", "entidad", "endpoint").
   ========================================================== */
window.GUIAS = [
{
  id: "primeros-pasos",
  titulo: "Por dónde empezar",
  resumen: "Lo primero que hay que hacer, en orden.",
  html: `
    <p>Si es la primera vez, hazlo en este orden. Cada paso toma unos minutos y
       ninguno te obliga a terminar el siguiente.</p>
    <ol>
      <li><b>Crea a tu gente.</b> Tú ya eres el dueño. Agrega a cada cajero con
          su propio PIN: así la caja sabe quién hizo cada cosa.</li>
      <li><b>Arregla la carta.</b> Los productos que vienen son de ejemplo.
          Cámbialos por los tuyos en la pestaña <b>Carta</b>. Si ya tienes la
          lista en un Excel, no la copies a mano: mira la guía
          <i>Traer la carta de un Excel</i>.</li>
      <li><b>Vende.</b> Con eso ya funciona. Todo lo demás es opcional.</li>
      <li><b>Cuando tengas tiempo</b>, carga la bodega para saber cuánto te
          queda de cada cosa. Se puede hacer de a poco.</li>
    </ol>
    <div class="ayuda">No hace falta tener todo listo para empezar a cobrar. La
      caja funciona con la carta a medias y con la bodega vacía.</div>`,
},
{
  id: "agregar-producto",
  titulo: "Agregar un producto o cambiar un precio",
  resumen: "Lo que el cliente compra y paga.",
  html: `
    <p>Un <b>producto</b> es lo que aparece en la caja para tocarlo y cobrarlo:
       un café, una marraqueta, un alfajor. Tiene nombre y precio.</p>

    <h3>Cambiar un precio</h3>
    <ol>
      <li>Pestaña <b>Carta</b>.</li>
      <li>Escribe el precio nuevo y aprieta <b>Guardar</b>.</li>
    </ol>
    <p>El precio va sin puntos: escribes <b>3400</b> y en la pantalla sale
       $3.400. El cambio se ve en la caja al tiro, y en las pantallas del local
       en la siguiente revisión.</p>

    <h3>Agregar uno nuevo</h3>
    <ol>
      <li>Pestaña <b>Carta</b> → botón <b>+ Producto</b> en la categoría que
          corresponda.</li>
      <li>Ponle nombre y precio.</li>
      <li>Elige el <b>dibujo</b>: hay más de 60 y se eligen viéndolos, no por el
          nombre. Es el que van a ver en la caja y en las pantallas del local.</li>
      <li>Si quieres, ponle una <b>etiqueta</b> ("Nuevo", "Sin lactosa").</li>
    </ol>

    <div class="ayuda"><b>Sacar algo de la venta</b> no lo borra: destilda
      <i>A la venta</i>. Deja de aparecer en la caja, pero las ventas viejas
      siguen cuadrando. Nunca se borra un producto que ya se vendió.</div>`,
},
{
  id: "traer-carta",
  titulo: "Traer la carta de un Excel",
  resumen: "Si ya tienes tu lista escrita, no la copies a mano.",
  html: `
    <p>Pestaña <b>Carta</b> → <b>Traer la carta de un archivo</b>.</p>
    <ol>
      <li>Sube el Excel o el CSV, <b>o pega la lista</b> copiada de donde la
          tengas: un Excel, un Word, un correo.</li>
      <li>Te muestro <b>lo que entendí, antes de guardar nada</b>: cuántos
          productos va a agregar, a cuáles les cambia el precio y cuáles quedan
          igual.</li>
      <li>Destilda lo que no quieras y corrige precios ahí mismo.</li>
      <li>Aprieta el botón verde.</li>
    </ol>
    <p>Entiende los precios como se escriben acá: <b>$3.500</b>, <b>3.500</b> y
       <b>3500</b> son lo mismo. Si tu lista tiene títulos de sección (CAFÉS,
       PASTELERÍA), los toma como categorías. Y le adivina el dibujo a cada
       producto por el nombre.</p>
    <div class="ayuda"><b>Lo que ya tenías no se borra.</b> Si tu carta actual
      tiene productos que el archivo no trae, se quedan como están. Si de verdad
      quieres sacarlos, hay una casilla abajo que lo dice.</div>`,
},
{
  id: "compre-pasteles",
  titulo: "Compré pasteles: ¿dónde los pongo?",
  resumen: "En un solo lugar. Ya no hay que escribirlo dos veces.",
  html: `
    <p>En <b>un solo lugar</b>: la pestaña <b>Carta</b>. Antes había que crearlo
       acá y después otra vez en la Bodega, escribiendo el mismo nombre a mano.
       Eso se acabó.</p>

    <h3>Cómo se hace</h3>
    <ol>
      <li>Carta → <b>+ Producto</b>. Nombre y precio.</li>
      <li>Más abajo, en <b>Bodega</b>, escribe <b>cuántos tienes</b> y
          <b>cuánto te cuesta cada uno</b>, y toca <b>Se vende tal cual</b>.</li>
    </ol>
    <p>Listo. Cada vez que vendas uno, el stock baja solo.</p>

    <div class="ayuda"><b>Si tienes lector de códigos</b>, es todavía más corto:
      pasa el producto por el lector en la pantalla de venta. Como no lo conoce,
      te lo pregunta ahí mismo — y queda guardado con su código para siempre.
      Mira la guía <i>Vender con lector de códigos</i>.</div>

    <h3>Cuando llegue más mercadería</h3>
    <p>Bodega → <b>Llegó mercadería</b> → eliges el pastel y pones cuántos
       llegaron.</p>

    <h3>¿Cuándo NO sirve esto?</h3>
    <p>Cuando lo que vendes <b>se prepara</b> con cosas que comparte con otros
       productos. Un latte gasta leche, y esa misma leche la gastan el capuchino
       y el cortado. Ahí necesitas una receta, que está en la guía de al lado.</p>

    <div class="ayuda"><b>Si la bodega te dice que ya existe algo con ese
      nombre</b>, no lo crees de nuevo: es lo mismo. Antes se creaban dos en
      silencio y quedaban dos saldos, cada uno con la mitad de la verdad.</div>`,
},
{
  id: "lector-de-codigos",
  titulo: "Vender con lector de códigos",
  resumen: "La pistola, y cómo el catálogo se arma solo.",
  html: `
    <p>Sirve cualquier <b>lector de pistola USB</b> de los que se venden en
       Chile (entre $15.000 y $40.000). Se enchufa y ya: para el computador es un
       teclado, no hay nada que instalar.</p>

    <h3>Vender</h3>
    <p>Pasa el producto por el lector. Entra solo al pedido. Nada más.</p>

    <h3>Cuando el producto es nuevo</h3>
    <p>La primera vez que pasas algo que la caja no conoce, te pregunta ahí
       mismo: qué es, a cuánto lo vendes, cuánto te cuesta y cuántos tienes.
       Lo guardas y sigue la venta.</p>
    <p><b>Esa es toda la carga de productos.</b> No hay que sentarse una tarde a
       escribir el almacén entero: se arma solo, un producto por vez, la primera
       que pasa por la caja. En una semana de trabajo normal ya está casi todo.</p>

    <div class="ayuda"><b>El nombre a veces llega escrito.</b> La caja lo busca en
      una base pública y gratis (Open Food Facts). Para abarrotes, lácteos y
      bebidas de marca acierta harto. Para <b>alcohol chileno casi nunca</b>: esa
      base es de información nutricional y no tiene cervezas ni vinos ni piscos.
      Cuando no lo encuentra, lo escribes tú y listo — igual queda para siempre.</div>

    <p><b>El precio nunca viene de ninguna parte.</b> Ese es tuyo y lo pones tú.
       No existe ninguna base en el mundo que sepa a cuánto vendes.</p>

    <h3>El pack de 6</h3>
    <p>La lata suelta y el pack traen códigos distintos y son el mismo trago. En
       la ficha del producto puedes agregarle <b>varios códigos</b>: pasas el
       pack por el lector y le dices que entrega 6. Al venderlo descuenta seis
       del mismo saldo.</p>

    <h3>Lo que el lector NO puede hacer</h3>
    <ul>
      <li><b>El pan y el fiambre pesados.</b> La etiqueta que imprime la balanza
          lleva el peso adentro, así que el código <b>cambia con cada trozo</b>.
          La caja los reconoce y no los deja guardar: si lo hiciera, tendrías un
          producto nuevo por cada pan que vendas. Esos se cobran a mano.</li>
      <li><b>El código del cartón.</b> La caja de una docena tiene su propio
          código, distinto al de la botella. Escanea la unidad suelta.</li>
      <li><b>Con la cámara del computador no se puede.</b> Windows no trae lo que
          hace falta para leer códigos de barra por cámara, y con el celular
          tampoco funciona por cómo se conecta a la caja. La pistola sale más
          barata que cualquier vuelta.</li>
    </ul>

    <div class="ayuda">Si el código sale mal leído, la caja te lo dice y te pide
      pasarlo de nuevo, en vez de crear un producto fantasma. Pasa con etiquetas
      arrugadas.</div>`,
},
{
  id: "descuento-automatico",
  titulo: "Que el stock baje solo al vender",
  resumen: "Para lo que preparas: café, jugos, sándwiches.",
  html: `
    <p>Sirve cuando varios productos gastan de <b>lo mismo</b>. Ejemplo: la
       leche la gastan el latte, el capuchino y el cortado.</p>

    <h3>Paso 1 — carga lo que se gasta</h3>
    <p>Pestaña <b>Bodega</b> → <b>+ Insumo</b>. Para la leche:</p>
    <ul>
      <li><b>Qué es:</b> Leche entera</li>
      <li><b>En qué se mide:</b> Mililitros</li>
      <li><b>Cómo se compra:</b> Caja de 1 litro</li>
      <li><b>Cuánto trae el envase:</b> 1000</li>
      <li><b>Cuánto cuesta el envase:</b> 1200</li>
      <li><b>Cuánto hay ahora:</b> lo que tengas, en mililitros</li>
      <li><b>Avísame cuando queden menos de:</b> 2000 (o sea, 2 litros)</li>
    </ul>

    <h3>Paso 2 — dile a cada producto cuánto usa</h3>
    <p>Abre el producto en la <b>Carta</b> y ponle su <b>receta</b>: un latte
       lleva 200 ml de leche y 18 g de café.</p>

    <p>Desde ahí, cada latte que vendas descuenta 200 ml solo. Y cuando la leche
       baje de 2 litros, aparece en <b>Por comprar</b>.</p>

    <div class="ayuda"><b>No hace falta cargar todo.</b> Un producto sin receta
      se vende igual y no descuenta nada. Puedes empezar con la leche y el café
      —que son los que más se van— y dejar el resto para después.</div>

    <h3>Los tres botones de la Bodega</h3>
    <ul>
      <li><b>Llegó mercadería</b> — se anota en envases, como se compra: 6 cajas
          de leche, no 6.000 mililitros.</li>
      <li><b>Se perdió algo</b> — se cayó, se venció, lo probamos. El motivo es
          obligatorio: sin motivo, una pérdida no se distingue de un faltante.</li>
      <li><b>Contar la bodega</b> — cuentas lo que hay de verdad y el programa
          ajusta la diferencia. No te muestra lo que debería haber hasta el
          final, igual que el arqueo de caja.</li>
    </ul>

    <div class="ayuda"><b>El stock nunca te impide cobrar.</b> Si el sistema
      cree que no queda leche y tú sabes que sí, vendes igual y el número queda
      en negativo. Ese negativo no es un error: te está avisando que hay una
      compra que nadie anotó.</div>`,
},
{
  id: "abrir-cerrar-caja",
  titulo: "Abrir y cerrar la caja",
  resumen: "El arqueo del cajón y el cuadre de las tarjetas.",
  html: `
    <div class="ayuda"><b>Sin caja abierta no se puede hacer nada.</b> Desde la
      2.5, al entrar te espera una sola pantalla: abrir la caja. No es rigor por
      rigor — una venta cobrada sin caja abierta no entra en ningún cuadre y no
      aparece en ningún cierre. Es plata sin dueño, y no se descubre hasta que
      el cajón no calza con nada.</div>

    <p>Y al revés: <b>no puedes salir de tu cuenta dejando TU caja abierta.</b>
       Si terminaste, ciérrala y después sal. Si la caja es de otra persona, sí
       puedes cambiar de usuario — justamente para que esa persona entre a
       cerrar la suya.</p>

    <h3>En la mañana</h3>
    <p>Arriba a la derecha dice <b>Caja cerrada</b>. Tócalo → <b>Abrir caja</b>.
       Cuenta el fondo del cajón billete por billete; el total lo suma el
       programa. Si no hay fondo, deja todo en cero.</p>

    <div class="ayuda"><b>La caja la cierra quien la abrió.</b> Si la abrió la
      Javiera en la mañana, el cierre es de ella: a otro cajero la pantalla le
      dice de quién es y no lo deja contar. Tú, como dueño, puedes cerrar
      cualquiera.</div>

    <p>Es porque el fondo del cajón lo contó ella. Si cierra otro, el descuadre
       queda sin dueño: no hay a quién preguntarle qué pasó a las once, y la
       diferencia se la come alguien que no contó ese fondo. Y si se fue sin
       cerrar, la cierras tú — queda escrito que la cerraste tú, en el papel del
       cierre y en el registro del mes, y eso también sirve.</p>

    <h3>En la noche</h3>
    <p>La pantalla se abre partida en dos. A la <b>izquierda</b> cuentas; a la
       <b>derecha</b> está todo lo que necesitas mirar mientras cuentas, desde
       el primer segundo.</p>
    <ol>
      <li><b>Cuenta el cajón</b>, por denominación. Con <b>+</b> y <b>−</b> o
          escribiendo la cantidad.</li>
      <li>Mientras cuentas, en la columna de la derecha, en
          <b>¿cuánto dice la máquina?</b>, escribe el total del comprobante de
          cierre de Transbank y lo que muestre el banco. Te dice al tiro si
          cuadra, en verde o en rojo.</li>
      <li>Aprieta <b>Ver si cuadra</b>. Ahí aparece cuánto debería haber en
          efectivo y si falta o sobra.</li>
      <li>Elige cuánto fondo dejas para mañana. El resto es lo que te llevas.</li>
    </ol>
    <p>Puedes corregir el conteo después de apretar <b>Ver si cuadra</b>: lo que
       ya escribiste —los totales de la máquina, el fondo, la nota— se queda
       donde está.</p>

    <div class="ayuda"><b>Lo único tapado es el efectivo</b>, y dice
      «al contar» hasta que termines. Es a propósito: si el número que debería
      haber estuviera en pantalla, es humano contar hasta llegar a esa cifra y
      parar ahí — y el arqueo dejaría de servir. Lo de tarjeta se ve desde el
      principio porque no está en el cajón: eso se compara con el comprobante,
      que es papel aparte.</div>

    <div class="ayuda"><b>Lo esperado de la tarjeta incluye la propina</b>,
      porque la máquina le cobró al cliente el total con la propina adentro.
      Y las propinas salen separadas: las de efectivo ya están en el cajón; las
      de tarjeta las depositó el banco y hay que pagarlas aparte.</div>

    <p>Escribir lo de las tarjetas es <b>opcional</b>: si no encuentras el
       comprobante, la caja cierra igual.</p>`,
},
{
  id: "no-cuadra",
  titulo: "No cuadró: qué hago",
  resumen: "Cómo buscar dónde está el error.",
  html: `
    <p>Primero: <b>guarda el cierre igual</b>. Esconder un descuadre es lo
       contrario de para lo que sirve cuadrar la caja. Queda anotado y se puede
       revisar después.</p>

    <h3>La caja te dice dónde mirar</h3>
    <p>Cuando algo no calza, aparece un recuadro <b>Dónde mirar</b> con las
       sospechas, en el orden en que conviene revisarlas.</p>

    <h3>1. El fondo de la mañana</h3>
    <p>Es la causa más común de un <b>sobrante</b>, y la más difícil de ver: si
       el cajón se contó de menos al abrir, la diferencia aparece recién doce
       horas después y parece salida de la nada.</p>
    <p>Por eso, al <b>abrir</b> la caja te muestra con cuánto quedó anoche y va
       comparando mientras cuentas. Si no calza, cuenta de nuevo <b>ahí mismo</b>:
       es el momento barato de arreglarlo.</p>

    <h3>2. Una venta que no calza</h3>
    <p>Si la diferencia coincide <b>exacta</b> con una venta, la caja te la
       muestra marcada. Casi siempre es esa.</p>
    <div class="ayuda"><b>El caso que más se repite en tarjeta:</b> el sistema
      tiene más de lo que hay en la vida real. Una venta se cobró como débito,
      la máquina la rechazó, y quedó registrada igual. O se pagó en efectivo y
      se marcó como tarjeta. En los dos casos: <b>anúlala</b> en El día, y si
      corresponde vúlvela a cobrar como fue de verdad.</div>

    <h3>3. Lo demás</h3>
    <ul>
      <li><b>Falta plata:</b> un vuelto de más, una venta registrada y no
          cobrada, o alguien sacó del cajón sin anotar.</li>
      <li><b>Sobra plata:</b> una venta cobrada y no registrada, o el fondo de
          la mañana mal contado.</li>
      <li><b>Ninguna venta sola explica la diferencia:</b> la caja te lista
          todas las del turno para que revises cuál no calza con lo que
          recuerdas. También puede ser una propina que la máquina cobró
          aparte.</li>
    </ul>

    <div class="ayuda">Las tarjetas y las transferencias <b>no están en el
      cajón</b>: esa plata la tiene el banco. Por eso el arqueo del efectivo solo
      compara contra las ventas en efectivo, y las tarjetas se cuadran aparte
      contra el comprobante de la máquina.</div>`
},
{
  id: "quien-es-quien",
  titulo: "Usuarios, PIN y permisos",
  resumen: "Quién puede hacer qué, y por qué.",
  html: `
    <p>Cada persona entra tocando su nombre y marcando su PIN de 4 números. Dos
       toques. Desde ahí la caja sabe quién hizo cada cosa.</p>

    <h3>Los dos roles</h3>
    <ul>
      <li><b>Dueño:</b> todo. Precios, informes, usuarios, ajustar el stock,
          anular ventas de cajas ya cerradas.</li>
      <li><b>Cajero:</b> vende, anula lo del turno en curso, abre la caja y
          cierra <b>la que abrió él</b>, mira la bodega y anota compras y
          pérdidas.</li>
    </ul>
    <p>El cajero <b>sí</b> puede anular una venta del turno en curso. Prohibirlo
       suena prudente y no lo es: a las 8 de la mañana no estás, y el cajero
       terminaría dejando la venta mala adentro — que descuadra la caja igual.
       El control es que toda anulación queda con autor y motivo.</p>

    <h3>Agregar a alguien</h3>
    <p>Arriba a la derecha, el botón <b>Equipo</b>. Ahí sale la lista de quiénes
       entran a la caja y el botón <b>Agregar a alguien</b>: nombre, un PIN de 4
       números que no empiece en 0, y si es cajero o dueño. Listo, ya le aparece
       la cara en la pantalla de entrada.</p>
    <p>Para cambiarle el nombre, el PIN o el rol a alguien, tócalo en esa misma
       lista. Si dejas el PIN vacío le queda el que tenía.</p>
    <p><b>Sacar a alguien</b> no lo borra: deja de aparecer en la pantalla de
       entrada, pero sus ventas y sus turnos se conservan enteros — si se
       borraran, los cierres de esos días dejarían de cuadrar. Si se equivocaron
       y hay que devolverlo, aparece en gris al final de la lista con el botón
       <b>Dejarlo entrar de nuevo</b>.</p>
    <p>El botón <b>Equipo</b> solo lo usa el dueño. Al cajero le aparece
       apagado: se ve, para que sepa que existe, pero no lo puede abrir.</p>

    <h3>Cambiar de persona</h3>
    <p>Toca el nombre de arriba a la derecha. No hay que cerrar nada ni salir
       del pedido.</p>
    <p>Si nadie toca la pantalla por 3 minutos, la caja se bloquea sola. Nunca
       lo hace con un pedido a medio armar ni con el cobro abierto: jamás te va
       a cortar una venta.</p>

    <div class="ayuda"><b>Si se corta la luz</b>, al volver se pide el PIN de
      nuevo, pero no se pierde nada: la caja abierta, las ventas, el pedido a
      medio armar y el conteo del cajón siguen donde estaban. Se pide el PIN
      porque el programa no puede saber quién quedó frente a la pantalla.</div>`,
},
{
  id: "pantallas-del-local",
  titulo: "Las pantallas del menú",
  resumen: "Son otro programa. Cómo se conectan y cómo se arreglan.",
  html: `
    <p>Las pantallas del menú son un <b>programa aparte</b> de esta caja. Se
       abren con su propio icono: <b>Pantallas del menú</b>.</p>
    <div class="ayuda">Están separadas porque no todos los locales tienen
      televisores. Un almacén o una botillería instalan solo la caja y no cargan
      ni actualizan código que nunca van a usar.</div>

    <h3>Conectar un televisor</h3>
    <ol>
      <li>Abre el programa <b>Pantallas del menú</b> en este mismo computador.
          Se abre una ventana negra con las direcciones escritas.</li>
      <li>En el televisor, abre el navegador y entra a la que le toca:
        <ul>
          <li><b>?p=1</b> — la vitrina, la que invita a elegir.</li>
          <li><b>?p=2</b> — la carta con los precios.</li>
          <li><b>?tv=1</b> — las dos turnándose, si tienes un solo televisor.</li>
        </ul>
      </li>
    </ol>
    <p>Esa ventana negra <b>tiene que quedarse abierta</b>: es la que sirve las
       pantallas. Cerrarla las apaga. No es como la caja, que se abre sola y sin
       ventana — acá la ventana es el programa.</p>

    <h3>La carta le llega sola</h3>
    <p>Cada precio que cambies acá se ve en los televisores en la siguiente
       revisión, sin tocar nada. Las pantallas vienen a buscar la carta a esta
       caja.</p>
    <div class="ayuda">Por eso la caja tiene que estar <b>abierta</b>. Si apagas
      este computador, los televisores se quedan sin carta.</div>

    <h3>Si el televisor la muestra en blanco y sin colores</h3>
    <p>Se ve fondo blanco, letras negras chicas y botones grises: el navegador de
       ese televisor es muy viejo. Usa la dirección que termina en
       <b>/simple</b> — la misma carta, más sobria, y anda en cualquier cosa.
       La normal se cambia sola a esa cuando se da cuenta.</p>
    <div class="ayuda">Agrégale <b>?diag=1</b> a la dirección simple y sale en
      grande qué entiende ese televisor. Sirve para pedir ayuda con datos.</div>

    <h3>Si se ve cortada por los bordes</h3>
    <p>Casi todos los televisores <b>recortan entre 3% y 5%</b> de cada borde por
       HDMI. En el televisor, mueve el mouse o toca la pantalla: aparece una
       barra abajo con <b>Ajustar al TV</b>. Queda guardado.</p>

    <h3>Si está al revés, o quedó en pantalla completa</h3>
    <p>En esa misma barra: <b>Girar pantalla</b> y <b>Salir</b>. La tecla
       <b>Escape</b> saca de todo.</p>

    <h3>Dos televisores con un solo cable</h3>
    <p>Cada pantalla es una dirección de la red, así que <b>no necesitas cable</b>
       desde el computador. Lo más simple es un aparatito barato en cada TV
       (Chromecast, Fire Stick o una caja Android) abriendo su dirección.</p>
    <div class="ayuda">Un divisor de HDMI <b>no sirve</b>: manda la misma imagen a
      los dos televisores, y acá cada uno muestra algo distinto.</div>`,
},
{
  id: "cuanto-cobrar",
  titulo: "¿Cuánto cobro? El IVA y la ganancia",
  resumen: "Quién pone el IVA y cómo sale el precio.",
  html: `
    <h3>El IVA ya va adentro</h3>
    <p>El precio que escribes es el que paga el cliente. Si pones <b>$2.500</b>,
       el cliente paga $2.500 — la caja no le suma un 19% encima. Es como
       cualquier vitrina en Chile.</p>
    <p>Lo que hace el programa es al revés: <b>separa</b> ese precio cuando hace
       falta. En la boleta y en el archivo del contador, esos $2.500 aparecen
       como $2.101 de neto más $399 de IVA. Suman exactamente $2.500: no se
       pierde ni se gana un peso por redondeo.</p>
    <div class="ayuda">O sea: <b>nunca</b> escribas el precio sin IVA pensando
      que la caja se lo agrega. Escribe lo que quieres cobrar.</div>

    <h3>Cuánto cobrar por algo que compraste</h3>
    <p>Abre el producto y anda a la parte de abajo, donde dice <b>Bodega</b>.
       Escribe cuánto te cuesta cada uno y aparece un recuadro verde con el
       precio sugerido.</p>
    <ul>
      <li>El botón <b>Usar este precio</b> lo copia arriba. De ahí lo puedes
          cambiar: es una sugerencia, no una orden.</li>
      <li>Los botones de <b>margen</b> mueven el sugerido. Ese porcentaje queda
          guardado para la próxima vez.</li>
      <li>El sugerido siempre <b>sube</b> al múltiplo de $50 más cercano hacia
          arriba: nadie cobra $2.437.</li>
    </ul>

    <h3>Ojo con qué significa el porcentaje</h3>
    <p>Acá el margen es <b>sobre lo que vendes</b>, no sobre lo que te costó.
       Es la confusión clásica y cuesta plata de verdad:</p>
    <ul>
      <li>Un pastel te cuesta <b>$1.200</b>.</li>
      <li>Con <b>50% de margen</b> lo cobras <b>$2.400</b>: la mitad de cada
          venta es tuya. Es cobrar el <b>doble</b> del costo.</li>
      <li>Si alguien dice "le pongo un 50% al costo" está cobrando $1.800, y se
          queda con $600 — la mitad de lo anterior.</li>
    </ul>
    <p>Por eso el recuadro te escribe siempre las dos formas: cuánta plata te
       queda, y cuántas veces el costo es el precio. No tienes que acordarte de
       la diferencia.</p>
    <div class="ayuda">El margen que elijas es del local, no de este computador:
      si abres la caja desde otro lado, es el mismo. Cambiarlo es cosa del
      dueño.</div>`,
},
{
  id: "respaldos",
  titulo: "Respaldos y datos para el contador",
  resumen: "Dónde queda todo y cómo se saca.",
  html: `
    <h3>Se respalda solo</h3>
    <p>La caja guarda una copia de todo <b>al abrir en la mañana</b> y <b>al
       cerrar caja</b>. Quedan en la carpeta <b>respaldos</b>, al lado del
       programa. Se guardan las últimas 30.</p>

    <h3>Para el contador</h3>
    <p>Pestaña <b>El día</b> → <b>Descargar para el contador</b>. Baja dos
       archivos que se abren con Excel: el resumen de ventas y el detalle por
       producto. Puedes elegir día, semana o mes.</p>

    <div class="ayuda">Ese informe <b>no reemplaza la declaración</b>. Mientras
      las boletas se emitan por fuera, lo que dice la caja y lo que se declara
      son dos cosas separadas. Conviene compararlas de vez en cuando: la
      diferencia entre ambas es justo donde aparecen las ventas que no se
      boletearon.</div>

    <h3>Si cambias de computador</h3>
    <p>Copia el archivo <b>pos.db</b> y la carpeta <b>respaldos</b>. Ahí está
       todo: ventas, precios, usuarios y bodega.</p>`,
},
];
