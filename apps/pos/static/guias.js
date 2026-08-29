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
  resumen: "El caso más común, resuelto de un toque.",
  html: `
    <p>Esta es la duda que más se repite, y tiene una respuesta corta.</p>

    <h3>Primero, la diferencia</h3>
    <ul>
      <li>Un <b>producto</b> es lo que el cliente compra y paga. Está en la
          <b>Carta</b>.</li>
      <li>Un <b>insumo</b> es lo que se te gasta de la bodega. Está en la
          <b>Bodega</b>.</li>
    </ul>
    <p>Para un pastel que compras hecho y vendes tal cual, <b>son la misma
       cosa</b>. Y por eso hay un atajo.</p>

    <h3>El atajo: "se vende tal cual"</h3>
    <ol>
      <li>Crea el producto en la <b>Carta</b>, como cualquier otro: nombre,
          precio, dibujo.</li>
      <li>Abre su ficha y usa <b>"se vende tal cual"</b>.</li>
      <li>Te va a preguntar cuántos tienes ahora y cuánto te costó cada uno.</li>
    </ol>
    <p>Listo. Cada vez que vendas uno, el stock baja solo. No tienes que
       entender la palabra "insumo" ni crear nada aparte.</p>

    <div class="ayuda"><b>Cuando llegue más mercadería:</b> Bodega →
      <b>Llegó mercadería</b> → eliges el pastel y pones cuántos llegaron.</div>

    <h3>¿Cuándo NO sirve el atajo?</h3>
    <p>Cuando lo que vendes <b>se prepara</b> con cosas que comparte con otros
       productos. Un latte gasta leche, y esa misma leche la gasta el capuchino
       y el cortado. Ahí no puedes tratar el latte como si fuera un insumo:
       necesitas una receta. Está explicado en la guía de al lado.</p>`,
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
  resumen: "Cómo se busca dónde estuvo el error.",
  html: `
    <p>Lo primero: <b>la diferencia se guarda igual</b>, cuadre o no. Esconder
       un descuadre sería lo contrario de para lo que sirve cuadrar la caja.</p>

    <h3>Para revisar un cierre</h3>
    <p>Pestaña <b>El día</b> → abajo, <b>Cierres de caja</b> → botón <b>Ver</b>.
       Ahí sale todo: lo vendido por forma de pago, cómo estaba el cajón billete
       por billete, y el cuadre contra el banco.</p>
    <p>Al final de esa tabla aparece el <b>acumulado del período</b>: cuántos
       cierres hubo y cuánto suman las diferencias. Si un día falta y otro sobra
       lo mismo, casi siempre es un vuelto mal dado.</p>

    <h3>Si falta plata en el cajón</h3>
    <ul>
      <li>Revisa las <b>anulaciones</b> del día: quedan con el motivo y con el
          nombre de quien las hizo.</li>
      <li>Fíjate en la <b>hora</b> de las ventas: un descuadre suele estar cerca
          del cambio de turno.</li>
      <li>Mira quién <b>estuvo</b> en el turno. Sale en el mismo cierre.</li>
    </ul>

    <h3>Si no cuadra la tarjeta</h3>
    <p>Casi siempre es una de dos: una venta que se cobró en la máquina pero no
       se marcó en la caja, o al revés. Compara la cantidad de operaciones, no
       solo el total.</p>

    <div class="ayuda">Cada cierre queda además escrito en un archivo que se
      abre con Excel, en la carpeta <b>registros</b> que está al lado del
      programa. Una fila por cierre, sin que nadie tenga que acordarse de
      exportar nada.</div>`,
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
  resumen: "Cómo se conectan y cómo se arreglan si se ven mal.",
  html: `
    <p>Las pantallas del local <b>las sirve esta misma caja</b>. No hay que
       instalar ni copiar nada en el televisor: solo abrir una dirección.</p>

    <h3>Conectar un televisor</h3>
    <ol>
      <li>Pestaña <b>Carta</b>: ahí están las tres direcciones, con su botón de
          copiar.</li>
      <li>En el televisor, abre el navegador y entra a la que le toca:
        <ul>
          <li><b>?p=1</b> — la vitrina, la que invita a elegir.</li>
          <li><b>?p=2</b> — la carta con los precios.</li>
          <li><b>?tv=1</b> — las dos turnándose, si tienes un solo televisor.</li>
        </ul>
      </li>
    </ol>
    <div class="ayuda">La carta le llega sola, desde esta caja. Cada precio que
      cambies acá se ve allá en la siguiente revisión, sin tocar el televisor.</div>

    <h3>Si se ve cortada por los bordes</h3>
    <p>Casi todos los televisores <b>recortan entre 3% y 5%</b> de cada borde
       cuando reciben por HDMI. No es la pantalla, es el TV.</p>
    <p>En el televisor, <b>mueve el mouse o toca la pantalla</b>: aparece una
       barra abajo. Usa <b>Ajustar al TV</b> con − y + hasta que entre entero.
       Queda guardado.</p>
    <p>Si prefieres arreglarlo en el televisor, busca en su menú de imagen algo
       que diga <b>Just Scan</b>, <b>Ajuste de pantalla</b> o <b>1:1</b>.</p>

    <h3>Si está al revés (vertical u horizontal)</h3>
    <p>En esa misma barra: <b>Girar pantalla</b>. Un toque.</p>

    <h3>Si quedó en pantalla completa y no puedes salir</h3>
    <p>La barra también trae <b>Salir</b>. Y la tecla <b>Escape</b> saca de todo.</p>

    <h3>Dos televisores con un solo cable</h3>
    <p>Como cada pantalla es una dirección de la red, <b>no necesitas cable</b>
       desde el computador. Lo más simple es un aparatito barato en cada TV
       (Chromecast, Fire Stick o una caja Android) abriendo su dirección. Así
       las pantallas siguen andando aunque muevas el notebook.</p>
    <div class="ayuda">Un divisor de HDMI <b>no sirve</b> para esto: manda la
      misma imagen a los dos televisores, y acá cada uno muestra algo distinto.</div>`,
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
