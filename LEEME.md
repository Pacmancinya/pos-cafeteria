# LÉEME — la caja de la cafetería

Esta carpeta es el **punto de venta**: donde se cobra, se ve cuánto se vendió en el día
y se cuadra la caja al cerrar. Además es de donde las **pantallas del local** sacan los
precios, así que un cambio acá se ve en las dos partes.

## Para empezar

Doble clic en **`Kofe.exe`**. Se abre como cualquier aplicación, con su ventana propia.
Para cerrarla, la cierras con la X.

> La primera vez, Windows puede mostrar un aviso azul que dice *“Windows protegió tu PC”*.
> Es porque el programa es nuevo y todavía no lo conoce. Toca **Más información** y después
> **Ejecutar de todas formas**. Pasa una sola vez.

> ¿Recién lo estás instalando? Está todo explicado paso a paso en
> **`docs/INSTALACION.md`**.

## Las cuatro pestañas

| Pestaña | Para qué |
|---|---|
| **Caja** | Cobrar. Tocas los productos, se van sumando, y aprietas **Cobrar**. |
| **El día** | Cuánto se vendió (cualquier día, no solo hoy), en qué se pagó, lo más vendido, imprimir un comprobante y anular una venta mal hecha. |
| **Carta** | Agregar productos, cambiar nombres y precios, o sacar algo de la venta. |
| **Bodega** | Cuánto queda de cada insumo, qué hay que comprar y en qué se te va la plata. |

## Cobrar, paso a paso

Los productos salen como cuadraditos con su dibujo, agrupados por categoría (la lista de
la izquierda). Si son muchos, escribe en el **buscador** de arriba: encuentra igual aunque
no le pongas tilde. Basta con empezar a escribir, no hace falta hacerle clic.

1. Toca los productos. Si te equivocas, con **−** sacas uno.
2. Aprieta **Cobrar** (o la tecla Enter).
3. Elige cómo paga. Si es **efectivo**, escribe con cuánto paga y te muestra el vuelto
   solo — o aprieta uno de los botones rápidos ($5.000, $10.000, "Justo").
4. Si corresponde, pon un **descuento** (hay botones de 10%, 15% y 20%, o escribes el
   monto que quieras).
5. **Confirmar venta**. Listo, queda registrada.

> Si se te cierra la pestaña con un pedido a medias, no se pierde: al volver a abrir,
> el pedido sigue ahí.

## Entrar a la caja

Al abrir la aplicación aparece la pregunta **¿quién está en la caja?** con el nombre de
cada uno. Tocas el tuyo, marcas tu PIN de 4 números y listo: dos toques.

Desde ahí el programa sabe quién hizo cada cosa. En el cierre de caja vas a ver quién la
abrió, quién la cerró y **quiénes estuvieron durante el turno** — aunque no hayan
alcanzado a vender nada.

- **Para cambiar de persona:** se toca el nombre arriba a la derecha. No hay que cerrar
  nada ni salir del pedido.
- **Si nadie toca la pantalla por 3 minutos**, la caja se bloquea sola y vuelve a
  preguntar quién está. Nunca lo hace con un pedido a medio armar ni con el cobro abierto:
  eso jamás te va a cortar una venta.

> **La primera vez** no hay nadie registrado: la caja te pide crear tu usuario y ése queda
> como **dueño**. Después, desde ahí mismo, creas a los cajeros.

**Qué puede cada uno**

| | Dueño | Cajero |
|---|:--:|:--:|
| Vender, anular, abrir y cerrar la caja | ✅ | ✅ |
| Mirar la bodega, anotar compras y pérdidas | ✅ | ✅ |
| Cambiar precios y productos | ✅ | — |
| Informes, respaldos, crear usuarios | ✅ | — |
| Contar la bodega (ajustar el stock) | ✅ | — |
| Anular una venta de una caja ya cerrada | ✅ | — |

## Abrir y cerrar la caja

Arriba a la derecha dice **Caja cerrada** o **Caja abierta**. Se aprieta ahí.

- **Al empezar el día:** *Abrir caja* → quién atiende y **cuentas el fondo** que queda en
  el cajón: cuántos billetes de $10.000, cuántas monedas de $500, etc. El total lo suma
  el programa. Si no hay fondo, dejas todo en cero.
- **Al terminar:** *Cerrar caja* → cuentas la plata igual, por denominación. Con **+** y
  **−**, o escribiendo la cantidad directo. Después aprietas **Ver si cuadra**.

Ahí recién aparece el cuadre: con cuánto abriste, cuánto se vendió en efectivo, cuánto
**debería haber**, cuánto **contaste**, y si **cuadra, sobra o falta**. Al final eliges
cuánto fondo dejas para mañana y el programa te dice cuánto te llevas del cajón.

> **La plata de tarjeta no se cuenta a mano**: el programa ya sabe cuánto se cobró. Pero
> sí se puede **cuadrar contra el banco**, más abajo en la misma pantalla.

**Después del cuadre del efectivo, viene el de las tarjetas.** Aparece un recuadro que
dice *¿cuánto dice la máquina?* con una línea por cada forma de pago que se usó. Al lado de
cada una dice **cuánto deberían ser**, y tú escribes lo que sale en el comprobante de
cierre de Transbank y en la app del banco. Te dice al tiro si cuadra o cuánto falta.

> **Lo esperado incluye la propina.** Es a propósito: la máquina le cobró al cliente el
> total con la propina adentro. Si comparáramos contra lo vendido a secas, te aparecería
> una diferencia falsa todos los días, justo del tamaño de las propinas.

Es **opcional**: si no encuentras el comprobante, la caja igual cierra.

**Las propinas salen separadas.** Las de efectivo ya están en el cajón. Las de tarjeta se
las quedó el banco y hay que pagarlas aparte — por eso van en su propia línea, para que no
se repartan dos veces ni se olviden.

> **Tocar al lado no cierra el conteo.** Mientras estás contando, un roce en la pantalla
> no te bota lo que llevas. Y si igual se cierra —se corta la luz, alguien cierra la
> ventana—, al volver a abrir el conteo está donde lo dejaste.

> **El conteo va a ciegas a propósito:** el número esperado aparece recién cuando aprietas
> *Ver si cuadra*. Si lo vieras antes, es humano acomodar el conteo para que calce — y
> ahí el arqueo deja de servir para lo único que sirve.

> La diferencia se guarda aunque no cuadre, junto con el detalle de cuántos billetes de
> cada uno había. Eso es lo que después permite buscar **dónde** estuvo el error, no solo
> cuánto faltó. Si el descuadre se pudiera esconder, cuadrar la caja no serviría de nada.

## Cambiar un precio o agregar un producto

Pestaña **Carta**. Para cambiar el precio: lo escribes y aprietas **Guardar**. El precio
va sin puntos: escribes `3400` y en la pantalla sale $3.400.

Para **agregar** algo nuevo: botón **+ Producto** en la categoría que corresponda. Se abre
una ficha donde eliges también el **dibujo** que va a mostrar la pantalla del local
(taza, vaso con hielo, croissant, torta…), si lleva etiqueta ("Nuevo", "Sin lactosa") y si
va en el recuadro grande.

Lo que cambies acá se ve en la caja al tiro, y en las **pantallas del local** en la
siguiente revisión (cada 10 minutos, o lo que se haya configurado ahí).

## Traer tu carta de un Excel

Si ya tienes tu lista de productos escrita en alguna parte, no la copies a mano.

Pestaña **Carta** → **Traer la carta de un archivo**. Puedes:

- **Subir el archivo** (Excel `.xlsx` o CSV), o
- **pegar la lista** copiada de un Excel, un Word o un correo.

El programa la lee y **te muestra lo que entendió antes de guardar nada**: cuántos
productos va a agregar, a cuáles les va a cambiar el precio y cuáles quedan igual. Ahí
mismo puedes destildar lo que no quieras y corregir precios.

Entiende los precios como se escriben acá: `$3.500`, `3.500` y `3500` son lo mismo. Si tu
lista tiene títulos de sección (CAFÉS, PASTELERÍA), los toma como categorías. Y le adivina
el dibujo a cada producto por el nombre — un latte sale con su tacita, un croissant con su
croissant. Los que no achunte los cambias después en dos toques.

> **Lo que ya tenías no se borra.** Si tu carta actual tiene productos que el archivo no
> trae, se quedan como están. Si de verdad quieres sacarlos, hay una casilla abajo que lo
> dice explícitamente.

> Si un producto ya existía, solo se le actualiza el precio. El dibujo y la descripción
> que hayas ajustado a mano **no se pisan**: esa decisión tuya vale más que lo que adivinó
> el programa.

## La bodega

Pestaña **Bodega**. Sirve para saber cuánto queda de cada cosa y en qué se te va la plata.

**Cómo se empieza (con calma, no hace falta cargar todo).**

1. **+ Insumo** para lo que se gasta: leche, café, vasos. Le pones cómo se compra
   (“Caja de 1 litro”, cuánto trae, cuánto cuesta) y cuánto hay ahora.
2. Después, en la ficha de un producto, le dices cuánto usa: un latte lleva 200 ml de
   leche y 18 g de café. Eso es la **receta**.
3. Para lo que se vende tal cual —un alfajor, una botella— hay un atajo: **“se vende tal
   cual”**, y queda listo de un toque.

Desde ahí el stock se descuenta solo cada vez que vendes.

> **Un producto sin receta se vende igual y no descuenta nada.** No es un error: puedes
> cargar la leche y el café hoy, y las tortas el mes que viene. Sirve desde el primer día.

**Los tres botones**

- **Llegó mercadería** — se anota en envases, que es como se compra: 6 cajas de leche, no
  6.000 mililitros.
- **Se perdió algo** — se cayó, se venció, lo probamos. El motivo es obligatorio: una
  pérdida sin motivo no se distingue de un faltante, y es justo lo que después quieres
  poder mirar.
- **Contar la bodega** — cuentas lo que hay de verdad y el programa ajusta la diferencia.
  Igual que el arqueo de caja, no te muestra lo que debería haber hasta el final.

**Ver movimientos** es la pantalla que contesta *“¿por qué me faltan 3 litros de leche?”*:
cada línea dice qué pasó, cuánto quedó después y quién lo hizo.

> **El stock nunca te va a impedir cobrar.** Si el sistema cree que no queda leche y tú
> sabes que sí, vendes igual y el número queda en negativo. Ese negativo no es un error: te
> está diciendo que hay una compra que nadie anotó.

En esa misma pestaña, arriba, está la **dirección que hay que pegar en las pantallas**
para conectarlas. Tiene un botón para copiarla.

## Imprimir

- Después de cobrar, en **El día** cada venta tiene un botón **Imprimir**: sale un
  comprobante angosto, del ancho de una boleta.
- Al **cerrar la caja** se imprime solo el papelito del cierre, con lo vendido, lo contado
  y la diferencia. Ese es el que conviene pegar en el cuaderno.

> Ojo: ese comprobante **no es una boleta**, y lo dice impreso. La boleta del SII se sigue
> emitiendo como se hace hoy.

## Guardar una copia y pasarle los datos al contador

En **El día**:

- **Respaldar ahora** guarda una copia de todo en la carpeta `respaldos`. Además se guarda
  solo cada vez que abres el programa y cada vez que cierras la caja.
- **Descargar para el contador** baja dos archivos de Excel del día que tengas elegido:
  uno con las ventas (con neto e IVA) y otro con el detalle de qué se vendió.

> El respaldo queda en el mismo computador. Si se echa a perder el disco, se pierde igual:
> conviene copiar esa carpeta a un pendrive de vez en cuando.

## Si alguien entra desde otro equipo

La caja se puede abrir desde un tablet o desde otro computador del local, escribiendo la
dirección que aparece en la ventana negra al arrancar. La primera vez pide un **PIN**
(viene `2468`). Desde el computador de la caja no pide nada.

Esto existe porque el wifi de invitados está en la misma red: sin el PIN, un cliente
podría abrir la caja desde el celular.

## Si se corta la luz o se cierra la app

**No se pierde nada de la venta.** Al volver a abrir:

- La **caja sigue abierta** si la habías abierto.
- Las **ventas cobradas** están todas.
- El **pedido que estabas armando** sigue ahí.
- El **conteo del cajón**, si estabas cerrando, también.

**Lo único que se pide de nuevo es el PIN.** Es a propósito: el programa no tiene cómo
saber si quien está ahora frente a la pantalla es la misma persona de antes. Si la sesión
siguiera abierta, cualquiera que prenda el computador quedaría vendiendo bajo el nombre del
último cajero — y el turno diría que esa persona estuvo trabajando todo ese rato.

Son dos toques y sigues exactamente donde estabas.

## Actualizaciones

Arriba a la derecha, al lado de la hora, está el número de versión. Cuando hay
una versión nueva se pone **verde** y dice *"Actualizar a v…"*. Le haces clic,
lees qué trae y aprietas **Actualizar ahora**.

La caja se cierra y se vuelve a abrir sola en unos segundos. **No se pierde
nada**: tus ventas, tus precios y tus respaldos quedan igual; lo único que
cambia es el programa.

Si no hay internet, simplemente no aparece nada. También se puede desde
**BUSCAR-ACTUALIZACIONES.bat**.

## Un par de cosas importantes

- **Una venta cobrada no se edita, se anula.** En *El día* hay un botón **Anular** y te
  pide el motivo. Queda registrado. Cambiar montos del pasado descuadraría la caja.
- **Si sacas un producto de la carta, las ventas viejas no se tocan.** Siguen sumando
  igual, con el nombre y el precio que tenían ese día.
- **Los precios que trae son de ejemplo.** Cámbialos por los tuyos en la pestaña Carta.

## Todavía NO hace

- **No emite boleta electrónica.** Registra la venta y cuadra la caja, pero la boleta
  del SII se sigue emitiendo como se hace hoy. Es lo siguiente que hay que decidir.
- **No cobra tarjetas.** La tarjeta se pasa por la máquina del banco como siempre; acá
  solo se registra que se pagó con tarjeta.
- **No lleva proveedores.** La bodega registra que llegó mercadería, no a quién se le
  compró ni cuánto se le debe.
