# CONTRATO — modelo de datos y API del punto de venta

> **Fuente de verdad del proyecto.** Si el código y este documento no coinciden, gana el
> código (`apps/pos/db/models.py`) — pero entonces hay que actualizar este archivo en el
> mismo commit. Esa es la regla.
>
> `[IMPL]` = implementado y probado · `[ROADMAP]` = diseñado, todavía no construido.

---

## 1. Decisiones que mandan sobre todo lo demás

**1. La plata es entera y bruta.** Todos los montos son **enteros en pesos chilenos**. Nada
de decimales, nada de flotantes: en CLP no hay centavos y un `float` termina dando
$3.399,9999. El precio guardado es el **bruto** (lo que paga el cliente, con IVA incluido),
porque es lo que se muestra en la carta y lo que el cajero cobra.

El neto y el IVA se **calculan al momento del informe**, nunca se guardan sueltos:

```
neto = round(bruto / 1.19)
iva  = bruto - neto          # así neto + iva == bruto SIEMPRE, sin descuadres de $1
```

**2. La línea de venta congela nombre y precio.** `VentaLinea` guarda el nombre y el precio
unitario **copiados** al momento de vender. Si mañana sube el café, las ventas de ayer no
cambian. Un POS que recalcula el pasado es un POS que miente en el cuadre.

**3. El punto de venta es el dueño de la carta.** Los productos viven acá y las pantallas
del local los leen por `GET /api/v1/carta`. No hay dos listas de precios. Esto es lo que
pidió el cliente: configurar todo desde el punto de venta.

**4. Nombres del dominio en español.** `Producto`, `Venta`, `Turno`. El dominio es una
cafetería chilena y lo va a leer gente que habla español. (En Gesfact los modelos están en
inglés porque el dominio técnico es un SaaS; acá la decisión es al revés, a propósito.)

**5. Una venta pagada no se edita. Se anula.** Corregir montos en el pasado rompe el cuadre
y es exactamente el agujero que Gesfact existe para detectar. Anular deja rastro.

**6. La caja es táctil primero.** Se usa de pie y con el dedo, no con mouse. El mínimo
cómodo son 48 px de alto (`--toque`), 56 para lo que se toca todo el día (`--toque-alto`)
y 64 para lo que se toca en cada venta (`--toque-rey`). Van como token y no como padding
porque con padding el alto real depende del font-size del navegador — así había once
alturas distintas sin que nadie lo decidiera. Los campos numéricos usan el teclado de
`teclado.js`, no el de Windows, porque el de Windows tapa el botón *Confirmar venta*.

> **Revertido en la 2.5, y con motivo.** El teclado numérico en pantalla queda APAGADO por
> defecto (`TECLADO_EN_PANTALLA`). Se diseñó para una pantalla táctil que todavía no existe;
> en el notebook del local hay un teclado de verdad, y un teclado dibujado que se abre solo
> tapa media pantalla justo cuando uno quiere escribir. Los tamaños cómodos para el dedo se
> quedan: no estorban con mouse y sirven el día que llegue la pantalla. El código del teclado
> tampoco se borró — se prende desde los ajustes.

**7. El stock avisa, no bloquea.** Nunca, bajo ninguna configuración, la falta de stock
puede impedir cobrar una venta. Ver la sección de inventario.

> **Matizado en la 2.5.** Sigue sin bloquear, pero ahora AVISA DE VERDAD: al pasar de lo
> que queda, el primer toque no suma y dice cuántos hay. El segundo sí suma. Antes se podía
> poner 12 de algo que tenía 3 sin que nada dijera nada, y el inventario quedaba en −9 hasta
> el conteo. El tope se pasa a propósito porque el saldo es lo que dice el programa, no lo
> que hay en la repisa: si llegó mercadería y nadie la anotó, negarse a vender sería peor
> que descuadrar el inventario — el cliente está ahí con la plata en la mano. Solo aplica a
> lo que se vende TAL CUAL: un capuchino no tiene "cuántos quedan", tiene leche y café.
>
> **Corregido en la 2.9. "Avisa" no era lo que decía ser, y hay video.** Lo de la 2.5 se
> escribió como si el segundo toque fuera una confirmación. No lo era: el aviso se iba solo
> a los tres segundos y el toque siguiente pasaba igual, viniera un segundo después o un
> minuto. Con eso se vendieron 27 unidades de un producto que estaba en cero, y el local lo
> reclamó tres veces —"me deja vender 30 que no existen"— antes de que quedara arreglado.
>
> Ahora es una PREGUNTA: dice cuántos quedan, cuántos se están poniendo y en cuánto va a
> quedar el inventario, y hay que contestar que sí. El sí vale para ese producto y ese
> pedido; se olvida al cobrar. Preguntar en cada toque sería peor —el cajero terminaría
> apretando Aceptar sin leer, que es como se llega otra vez a 27.
>
> **Y había un agujero más grande abajo:** un producto sin inventario no tenía tope
> NINGUNO. No es que el aviso fallara; es que `p.stock` venía nulo y la comparación no
> existía. Un producto creado sin insumo se vendía sin límite y en silencio. La 2.9 agrega
> `POST /inventario/llevar-la-cuenta-de-todo` y un panel en la Bodega que lo dice con esas
> palabras, para no arreglarlos de a uno.
>
> **La lección, que es la misma de la decisión 12:** un aviso que se va solo no es un tope,
> es un adorno. Si la regla importa, tiene que costar algo pasarla.

**8. Reiniciar el programa pide el PIN de nuevo, pero no pierde nada.** Las galletas
emitidas antes de que arrancara el proceso (`sesion.ARRANQUE`) no valen. Es la única
respuesta honesta a un corte de luz: el programa no tiene cómo saber si al volver está la
misma persona frente a la pantalla, y con la sesión viva, cualquiera que prenda el
computador queda operando bajo el nombre del último cajero. Lo que sí sobrevive es todo lo
demás — el turno abierto, las ventas, el pedido a medio armar y el conteo del cajón, que
viven en la base o en el equipo. Al arrancar se cierran además las presencias que quedaron
abiertas, con `salida_por="corte"`: si no, el turno diría que esa persona estuvo en la caja
durante días.

**9. Un diálogo donde se cuenta plata no se cierra solo.** Las capas con trabajo adentro
(el arqueo de caja, el conteo de bodega) llevan `.capa--firme`: ni un toque en el fondo ni
la tecla Escape las cierran. Además el conteo del cajón se guarda en el equipo mientras se
cuenta y se recupera al reabrir. Perder un arqueo a medio contar obliga a contar el cajón
entero de nuevo, y pasó de verdad.

**10. La caja la cierra quien la abrió, o el dueño.** El cierre no es un trámite: es la
firma de que el cajón que se contó en la mañana cuadra en la noche. Quien abrió es el único
que sabe con cuánto partió el cajón y qué pasó durante el día, así que si cierra otro, el
descuadre queda sin dueño — no hay a quién preguntarle dónde estuvo el error, y la
diferencia se le carga a alguien que no contó ese fondo. Por eso el permiso `turno_cerrar`
**no alcanza solo**: además se compara `Turno.abierto_por_id` con quien pide el cierre. El
dueño pasa por encima siempre (`turno_cerrar_ajeno`), y no es un privilegio decorativo: el
caso real es el cajero que se fue a las 19:00 sin cerrar, y una caja abierta hasta el día
siguiente parte el arqueo en dos jornadas.

> **Un turno sin `abierto_por_id` es de NADIE, no de otro.** Están así todos los turnos
> anteriores a que existieran los usuarios —los nueve de la base del local, incluido el que
> estaba abierto cuando se escribió esto—, los abiertos en modo provisorio y los de la carta
> de ejemplo. Una guarda escrita como `abierto_por_id != mi_id` los deja imposibles de
> cerrar. Tiene que ser `is not None and != mi_id`. Lo mismo si la fila del usuario ya no
> existe: una caja que nadie puede nombrar no puede ser una caja que nadie puede cerrar.

**11. El precio guardado es el que paga el cliente; el margen es sobre la venta.** Nadie
le suma IVA a nada: `Producto.precio` es bruto (decisión 1) y el neto sale por diferencia
en el informe. Sobre el margen sugerido, la definición es **sobre la venta** —
`(precio − costo) / precio` — y no sobre el costo. Es la misma cuenta que `margen_pct` de
la receta ya mostraba, y usar dos definiciones distintas del mismo número en la misma
pantalla confunde más que no tener ninguna. Como la confusión cuesta plata de verdad (un
"50% sobre el costo" gana la mitad que un 50% de margen), la pantalla escribe siempre las
dos formas al lado: cuánto queda y cuántas veces el costo es el precio. El sugerido
redondea SIEMPRE hacia arriba, para que el margen pedido sea un piso y no algo que el
redondeo se come.

**12. Las pantallas del menú las sirve la caja, en `/pantallas`.** Cada TV abre una
dirección de la red y la carta le llega del MISMO origen: no hay archivo que copiar, ni IP
que escribir, ni CORS que pelear.

> **Esta decisión cambió dos veces, y la segunda fue un error mío que conviene dejar
> escrito.** Antes de la 1.8 las pantallas eran un `.html` que había que copiar a CADA
> televisor y al que había que escribirle la IP a mano: ese era el dolor, y la 1.8 lo
> resolvió metiéndolas acá. En la 2.2 las saqué a un programa aparte, con el argumento de
> que un almacén sin televisores no tenía por qué cargar ese código. El argumento no
> aguanta: son **184 KB de archivos estáticos que nadie pide si nadie los abre**. A cambio,
> la cafetería tenía que dejar una ventana negra más abierta todo el día, y la caja dejaba
> de poder mostrar las direcciones de los TV porque ya no sabía en qué puerto estaban. Se
> cambió algo que costaba nada por algo que costaba todos los días. Volvieron en la 2.8.

> **Regla que sale de ahí:** antes de separar dos cosas por prolijidad, medir qué cuesta
> tenerlas juntas. Si la respuesta es «184 KB», no se separan.

**13. Un producto se crea en UN solo lugar.** `POST /api/v1/productos` con `tal_cual` crea
la ficha, su insumo, la receta que los amarra y el saldo inicial **en la misma transacción**.
Antes había que crearlo en la carta, ir a la bodega, escribir el nombre otra vez a mano y
recién ahí amarrarlos. El resultado de ese diseño está en la base del local: **148 ventas y
UN insumo cargado**. No es que el inventario no importe — es que entrar costaba más de lo
que daba.

> **Va todo junto o no va nada.** Un producto a medio crear —ficha sí, insumo no— es peor
> que no haberlo creado: se vende, no descuenta, y nadie se entera hasta el conteo.

**14. Lo que se vende y lo que se guarda se amarran por ID, nunca por nombre.**
`Insumo.producto_id` es el vínculo. Antes se comparaban los NOMBRES y eso falló de tres
formas distintas, las tres vistas en la base real: "Coca-Cola 1.5 L" y "Coca Cola 1.5L"
creaban dos insumos y el saldo del primero quedaba huérfano; renombrar el producto dejaba
el insumo con el nombre viejo —quedó uno llamado "Producto nuevo" apuntando a "redbul
550ml"—; y la búsqueda no filtraba `activo`, así que podía amarrar la receta a un insumo
sacado de la bodega, y entonces la venta no descontaba nada **sin dar ningún error**.

> **`Producto` sigue SIN columna de stock**, y es a propósito (ver la sección de
> inventario). La tentación en una botillería es obvia y el precio se paga el día que
> exista el pack de 6: la botella saldría del stock por dos caminos y el inventario deja de
> cuadrar. La receta de una línea cuesta una fila y hace que el pack y la unidad suelta
> descuenten del mismo saldo, sin código nuevo.

**15. Un código de barras identifica un producto, y un producto puede tener varios.**
Tabla `CodigoBarra`, no una columna: la lata suelta y el pack de 6 traen códigos distintos
y son el mismo trago. `cuantos` dice cuántas unidades entrega cada código.

Se guardan **siempre normalizados a 13 dígitos**: un UPC-A de 12 es un EAN-13 con un cero
adelante, y guardarlos distinto deja el mismo producto duplicado según qué lector lo leyó.
Se valida el dígito verificador **antes** de buscar: una etiqueta arrugada devuelve dígitos
cambiados, y sin esa validación se crea un producto fantasma.

> **Los códigos que empiezan con 2 NO se guardan nunca.** Son los que imprime la balanza
> del local para el pan, el fiambre y el queso: llevan el peso o el precio adentro, así que
> **cambian con cada trozo**. Si se aceptaran, habría un producto nuevo por cada pan
> vendido. La caja los reconoce y se niega, explicando por qué.

**16. El escáner intercepta en fase de CAPTURA sobre `window`, y eso no es un detalle.**
Un lector de pistola es un teclado: manda los dígitos y un Enter. La caja ya tenía dos
oyentes globales de teclado, y sin interceptar antes que ellos pasaba esto: con el diálogo
de cobro abierto, **el escaneo cobraba la venta** con "paga con $7.801.610.001.196"; con el
carrito armado, el Enter abría solo el cobro; y frente al candado, un código de 13 dígitos
se convertía en **tres intentos de entrar seguidos**. Está probado en `test_codigos.py` y
verificado en el navegador. Si alguien mueve ese oyente a `document` o a fase de burbujeo,
vuelven los tres.

> **La cámara no es una opción en Windows, y no es cosa de esperar.** `BarcodeDetector`
> delega en el sistema operativo y Windows no tiene esa API, así que en WebView2 sencilla-
> mente no existe. Y escanear desde el celular por la red tampoco: `getUserMedia` exige
> contexto seguro, y `http://192.168.x.x` no lo es. La pistola USB cuesta menos que
> cualquiera de las salidas.

**17. No existe una base de códigos de barra chilena, y el catálogo se arma solo.** GS1
Chile **vende** códigos a los fabricantes; no publica un catálogo ni tiene API abierta.
Open Food Facts sí es libre (ODbL, sin clave) pero tiene **6.680 productos chilenos** contra
4,7 millones en el mundo, y **cero** cervezas, vinos y piscos: es una base nutricional. Para
un almacén ayuda; para una botillería, casi nunca.

Por eso Open Food Facts se usa **solo para sugerir el nombre**, editable, y nunca como
catálogo. El precio no está en ninguna base del mundo: ese es del local. Lo que de verdad
resuelve el problema es que cada producto se escriba UNA vez, la primera que pasa por la
caja, y quede con su código para siempre.

**18. Sin caja abierta no se vende, y no se usa el programa.** El servidor responde 409 a
cualquier venta sin turno, y la pantalla tapa todo con una puerta hasta que se abra la caja.
Antes se aceptaba y la venta quedaba con `turno_id` en nulo: no entraba en ningún cuadre, no
aparecía en ningún cierre, y nadie se enteraba hasta que el efectivo del cajón no calzaba con
nada. Una venta que no pertenece a ningún turno es plata sin dueño.

> **La puerta tiene DOS salidas, y la segunda no es un adorno.** Además de «Abrir caja» está
> «Salir de mi cuenta». Sin ella, cerrar la caja a las 20:00 dejaría al dueño encerrado: la
> puerta le pediría abrirla de nuevo para poder hacer cualquier cosa. Terminar el día es
> cerrar la caja y salir.

> **No se puede salir dejando la caja PROPIA abierta**, pero sí dejando la de otro. La
> condición es sobre la caja propia a propósito: si la abrió Javi y está Ana en pantalla, Ana
> no puede cerrarla —decisión 10— así que si tampoco pudiera cambiar de usuario, no habría
> forma de que Javi volviera a entrar a cerrar la suya. El bloqueo por inactividad no cuenta
> como salir: bloquea la pantalla y deja el turno donde está.

**19. Dos productos activos no pueden llamarse igual, y "igual" ignora tildes y
mayúsculas.** `POST` y `PUT /api/v1/productos` responden 409 con el nombre del que ya
existe. No es prolijidad: el nombre es lo ÚNICO con que cuenta el cajero para elegir. En la
carta del local llegaron a quedar **nueve** productos llamados «Producto nuevo», y con eso
el cajero no sabe cuál tocar, "lo más vendido" los cuenta por separado, y el saldo de uno no
dice nada del otro aunque sean la misma botella.

La comparación normaliza tildes y mayúsculas porque «Té» y «TE» tecleados con apuro son el
mismo producto para quien mira la pantalla, y una regla que el ojo no puede verificar no
sirve de nada.

**Solo entre productos ACTIVOS.** Uno sacado de la carta libera su nombre: ya no se puede
tocar ni vender, así que no hay con qué confundirlo. Y la unicidad NO es una restricción de
la base: hay locales con duplicados de antes, y convertirlos en un error dejaría la caja sin
arrancar. Se valida al escribir, que es donde se puede explicar.

**Al editar solo se valida si el nombre CAMBIA**, y eso no es una concesión: los nueve
«Producto nuevo» del local existen. Si se validara siempre, guardarles el precio daría 409 y
quedarían congelados — inarreglables e irrenombrables, que es exactamente lo que hay que
poder hacer con ellos. La regla existe para no crear colisiones nuevas, no para castigar las
que ya están.

> **Esto no reemplaza a la decisión 14.** El amarre sigue siendo por ID. Que los nombres no
> se repitan es para la PERSONA que mira la pantalla, no para el programa.

---

## 2. Modelo de datos `[IMPL]`

Tabla `apps/pos/db/models.py`. SQLModel sobre SQLite (archivo `pos.db`), migrable a
Postgres cambiando `DB_URL` sin tocar código.

```
Categoria(id, nombre, orden, activa)
    # "Café caliente", "Fríos", "Pastelería"…

Producto(id, categoria_id→Categoria, nombre, descripcion, precio,
         activo, orden, destacado, badge,
         antes, etiqueta, dibujo, color)
    # precio  = bruto en CLP (entero)
    # antes   = precio tachado de oferta (opcional, entero)
    # destacado = va al recuadro grande de la pantalla del menú (1 por categoría)
    # dibujo   = "receta" del dibujo: taza, taza-cortado, mug, mug-espuma, mug-arte,
    #            mug-crema, vaso, vaso-leche, vaso-limon, vaso-verde, vaso-menta,
    #            frappe, croissant, croissant-almendras, torta, torta-manzana,
    #            brownie, alfajor. Lo entienden IGUAL la caja y las pantallas.
    # color/etiqueta = presentación; el POS no los usa para cobrar

Turno(id, cajero, abierto_at, cerrado_at, monto_inicial,
      efectivo_contado, diferencia, nota)
    # un turno = una jornada de caja. El cierre compara lo contado con lo esperado.

Venta(id, numero, turno_id→Turno, creada_at, estado,
      total, propina, medio_pago, nota, anulada_at, anulada_motivo)
    # numero    = correlativo global, empieza en 1
    # estado    = pagada | anulada
    # total     = suma de las líneas (SIN propina)
    # medio_pago= efectivo | debito | credito | transferencia

VentaLinea(id, venta_id→Venta, producto_id→Producto,
           nombre, precio_unitario, cantidad, subtotal)
    # nombre y precio_unitario son COPIAS congeladas (ver decisión 2)
    # subtotal = precio_unitario * cantidad

Usuario(id, nombre, rol, pin_hash, activo, color, orden,
        creado_at, ultimo_ingreso_at)
    # rol      = dueno | cajero  (sin ñ: la clave viaja por la API)
    # pin_hash = pbkdf2_sha256$iteraciones$sal$hash. NUNCA sale por la API.
    #            Se hashea porque pos.db se copia a respaldos/ dos veces al día
    #            y esa carpeta termina en pendrives y en el correo del contador.
    # activo   = borrado lógico. Un usuario no se borra nunca: sus ventas
    #            tienen que seguir diciendo quién las hizo.

Presencia(id, usuario_id→Usuario, turno_id→Turno,
          entro_at, salio_at, salida_por)
    # Quién ESTUVO en la caja y desde cuándo hasta cuándo. Con solo el autor de
    # cada venta, alguien que atendió dos horas sin cobrar nada sería invisible.
    # salio_at nulo = está adentro ahora mismo
    # salida_por    = cambio | bloqueo | salir

Insumo(id, nombre, unidad, stock, minimo, activo, orden,
       formato, compra_contenido, compra_costo)
    # unidad = g | ml | un — la unidad BASE. Todo entero: 200 ml es 200.
    # stock  = saldo en unidad base. Es una COPIA rápida de la suma del libro,
    #          no la verdad. Puede quedar NEGATIVO y eso no es un error.
    # formato/compra_contenido/compra_costo = cómo se compra ("Caja 1 L", 1000,
    #          $1.200). El costo por mililitro NO se guarda: $1,2 redondeado a
    #          $1 le quita un 17% al valor del inventario. Ver core.config.costo_de().

Receta(id, producto_id→Producto, insumo_id→Insumo, cantidad)
    # Una fila = un ingrediente. El latte son dos filas; el alfajor, una de 1 un.
    # Un producto SIN filas acá no mueve stock, y eso NO es un error: es el
    # estado normal el primer día.

Movimiento(id, insumo_id→Insumo, creado_at, tipo, cantidad, saldo_despues,
           costo, motivo, venta_id→Venta, turno_id→Turno, usuario_id, hecho_por)
    # EL LIBRO. Fuente de verdad del stock. Solo se AGREGAN filas.
    # tipo     = compra | venta | merma | ajuste | devolucion | carga
    # cantidad = CON SIGNO: + entra, − sale. Un solo campo, para que sea
    #            imposible escribir un informe que sume las mermas como si entraran.
    # costo    = lo que valía esa cantidad, CONGELADO (igual que el precio en
    #            VentaLinea): cuánto costó la merma de julio no puede depender
    #            de lo que vale la leche hoy.
    # hecho_por= nombre copiado, además del usuario_id.

Turno(... , abierto_por_id→Usuario, cerrado_por_id→Usuario)
Venta(... , usuario_id→Usuario, anulada_por_id→Usuario)
    # NULL en las filas anteriores al login: a esas no se les inventa un autor.

RetiroCaja(id, turno_id→Turno, monto, motivo, creado_at,
           usuario_id→Usuario, hecho_por, anulado, anulado_at, anulado_por)
    # La plata que sale del cajón EN MEDIO del turno, para comprar cosas sin
    # cerrar la caja. Libro de solo-agregar, como Movimiento, pero de PLATA y no
    # de inventario. El motivo nunca va vacío. Se resta del efectivo esperado.
    # Se corrige anulando (la fila queda), no borrando. NO es Turno.retiro, que
    # es lo que se lleva el dueño al cerrar.
```

### Reglas de integridad
- `Venta.total` == suma de `VentaLinea.subtotal` de esa venta. Se verifica en el test
  `test_ventas.py::test_total_cuadra_con_lineas`.
- Una venta siempre nace **pagada**: el POS registra la venta cuando ya se cobró. No hay
  carrito a medio pagar en la base (el carrito vive en el navegador del cajero).
- `producto_id` puede quedar apuntando a un producto borrado; por eso la línea guarda el
  nombre. Nunca se borra una `VentaLinea`.

### Extensión `[ROADMAP]` — boleta electrónica
```
Boleta(id, venta_id→Venta, folio, tipo_dte, emitida_at, estado, xml_path, pdf_path)
```
No está construido y **no bloquea nada**: el POS registra ventas y cuadra caja sin emitir
boleta. Cuando se decida el proveedor de facturación electrónica se conecta acá. Ver la
sección 6 de `README.md` antes de empezar eso.

---

## 3. API REST (`/api/v1`)

Todas las respuestas son JSON. Los montos, enteros.

### Carta (lo que consumen las pantallas del local) `[IMPL]`
```
GET /api/v1/carta
```
Devuelve **exactamente** el formato que esperan las pantallas de `menu-cafeteria`:

```json
{
  "avisos": ["Lunes a sábado de 8:00 a 20:00"],
  "categorias": [
    {
      "nombre": "Café caliente",
      "productos": [
        {"nombre":"Espresso","descripcion":"Doble carga","precio":1900,
         "antes":null,"etiqueta":null,"dibujo":"taza","color":null}
      ],
      "destacado": {"nombre":"Mocha","descripcion":"…","precio":3900,
                    "etiqueta":"Recomendado de hoy","dibujo":"mug"}
    }
  ]
}
```
> 🔴 El `dibujo` viaja como **nombre de receta**, no como forma pelada: `mug-espuma`,
> `vaso-limon`, `torta-manzana`. La caja y las pantallas tienen la misma tabla de recetas
> (`apps/pos/static/dibujos.js` y `ART_DEFECTO` en las pantallas). Si se agrega una receta
> hay que agregarla **en los dos lados**, o el producto se dibuja con el genérico.

> 🔴 Este endpoint **manda CORS abierto** (`Access-Control-Allow-Origin: *`). Sin eso el
> navegador de la pantalla rechaza la respuesta y el menú se queda con la carta vieja.
> Es de solo lectura y solo expone precios públicos, así que abrirlo no filtra nada.

### Operación de caja `[IMPL]`
```
GET  /api/v1/salud                      → {ok, version, turno_abierto}
GET  /api/v1/categorias                 → categorías activas con sus productos
POST /api/v1/ventas                     → registra una venta cobrada
GET  /api/v1/ventas?fecha=AAAA-MM-DD    → ventas del día (sin líneas, liviano)
GET  /api/v1/ventas/{id}                → una venta con sus líneas
POST /api/v1/ventas/{id}/anular         → {motivo}
GET  /api/v1/resumen?fecha=AAAA-MM-DD   → totales del día por medio de pago + neto/IVA
```

`POST /api/v1/ventas` recibe:
```json
{"lineas":[{"producto_id":1,"cantidad":2}],
 "medio_pago":"efectivo","propina":0,"nota":null,"paga_con":5000}
```
`paga_con` es opcional y solo sirve para devolver el **vuelto** calculado; no se guarda.

### Respaldo y exportación `[IMPL]`
```
POST /api/v1/respaldo                        → copia la base a respaldos/pos-AAAA-MM-DD.db
GET  /api/v1/respaldos                       → qué copias hay
GET  /api/v1/exportar/ventas?desde=&hasta=   → CSV para el contador
GET  /api/v1/exportar/detalle?desde=&hasta=  → CSV con una fila por producto vendido
```
El respaldo se dispara solo al **abrir el programa** y al **cerrar la caja**, además del
botón. Usa la API de respaldo de SQLite, no una copia del archivo: copiar el `.db` mientras
está en uso puede dejar una copia corrupta justo cuando más se necesita. Se guardan las
últimas 30.

Los CSV salen con separador `;` y `utf-8-sig` (BOM) porque así el Excel en español los
abre en columnas y con los acentos correctos.

### Papeles imprimibles `[IMPL]`
```
GET /comprobante/{venta_id}   → comprobante de 80 mm
GET /cierre/{turno_id}        → papelito del cierre de caja
```
Son páginas HTML angostas que se mandan a imprimir con el navegador: funcionan con la
impresora térmica **y** con cualquier impresora normal, sin drivers ni ESC/POS.

> 🔴 El comprobante dice **NO ES BOLETA** en un recuadro, y no es decorativo: mientras no
> esté conectada la facturación electrónica, un papel que se parezca a una boleta sin
> serlo deja expuesto al local.

### Turnos `[IMPL]`
```
GET  /api/v1/turnos/actual
GET  /api/v1/turnos/denominaciones
POST /api/v1/turnos/abrir              {cajero, conteo}
POST /api/v1/turnos/cerrar             {conteo, fondo_siguiente, medios, nota}
POST /api/v1/turnos/retiro             {monto, motivo}      ← sacar plata en medio del turno
POST /api/v1/turnos/retiro/{id}/anular
```
El cierre calcula: `esperado = monto_inicial + ventas en efectivo − propinas de tarjeta
pagadas en efectivo − retiros del turno`, y guarda la `diferencia` (contado − esperado).
**Se guarda aunque descuadre** — ocultar el descuadre sería justamente lo contrario a lo
que sirve. Esa cuenta vive en **una sola función** (`turnos._efectivo_esperado`): la
pantalla, el cierre y el papel de 80 mm la llaman a ella. Antes cada uno la calculaba por
su lado y el papel ni siquiera restaba las propinas pagadas — tres fórmulas que tenían que
dar lo mismo y no lo daban.

**Sacar plata en medio del turno** (`RetiroCaja`) es para ir a comprar cosas —gas, pan, un
insumo que faltó— sin cerrar la caja. Es un libro de solo-agregar con quién, cuánto, cuándo
y para qué; el motivo es obligatorio, porque un retiro sin motivo no se distingue de un
faltante. **Lo puede hacer cualquiera** (permiso `caja_retirar`, dueño y cajero): el cajero
es el que está solo en la mañana, y lo que cuida la plata no es un permiso sino que cada
retiro queda firmado. Se corrige anulando, no borrando: la fila queda, con quién la anuló.
Y el cuadre lo resta solo del efectivo esperado, o esa plata aparecería de noche como un
faltante que no existe. **No es** el `retiro` del cierre, que es lo que se lleva el dueño al
final del día.

**El arqueo se cuenta por denominación**, no se escribe un total. `conteo` es
`{"10000": 2, "500": 6}` y el servidor lo suma con `total_del_conteo()`, que ignora
cualquier valor que no sea plata chilena. Se guarda el conteo completo (`conteo_apertura`,
`conteo_cierre`) porque un descuadre con detalle se puede investigar y uno sin detalle
solo se puede lamentar. `efectivo_contado` suelto sigue aceptándose para no romper nada
que ya lo mande, pero si viene `conteo`, manda el conteo.

`fondo_siguiente` es lo que queda en el cajón para el día siguiente; el `retiro` es el
resto y lo calcula el servidor, nunca se pide escrito. No se puede dejar de fondo más de
lo que se contó.

**A ciegas es SOLO el efectivo.** Al abrir el cierre se muestra todo: cuántas ventas hubo,
cuánto se pagó con cada tarjeta, cuánta propina, y los campos para escribir lo que dice la
máquina. Lo único tapado es la columna del efectivo —ventas y propinas— porque es lo que
está dentro del cajón: si el número que debería haber estuviera en pantalla, contar hasta
llegar a esa cifra sería lo natural y el arqueo no probaría nada. Lo de tarjeta no está en
el cajón y se cuadra contra un papel de afuera, así que taparlo no protegía nada y solo
obligaba a escribir el total de Transbank sin haberlo visto venir.

**El efectivo se CUENTA; las tarjetas se COPIAN.** Son dos cuadres distintos y por eso
`conteo_cierre` y `conteo_medios` son campos separados. El conteo del cajón se hace por
denominación y a ciegas; lo de tarjeta sale del comprobante de cierre de la máquina y de
la app del banco, y se escribe tal cual. `medios` en la respuesta del turno trae, por cada
forma de pago que no sea efectivo: `esperado`, `declarado` y `diferencia`.

> **`esperado` incluye la propina, y eso es lo que hace que el cuadre sirva.** La máquina
> le cobró al cliente el total CON propina adentro. Compararlo contra lo vendido a secas
> daría una diferencia falsa todos los días, exactamente del tamaño de las propinas.

Escribir lo del banco es **opcional**: sin eso, `declarado` y `diferencia` quedan en `null`
y no se inventa un cuadre. Nadie se puede quedar sin cerrar la caja porque no encuentra un
comprobante.

**Las propinas se informan separadas** (`propinas.efectivo` / `propinas.tarjeta`): la de
efectivo ya está en el cajón y se reparte de ahí; la de tarjeta la depositó el banco y hay
que pagarla aparte. Sin esa distinción, o se reparte dos veces o no se reparte nunca.

### Usuarios y sesión `[IMPL]`
```
GET  /api/v1/candado                    → los nombres para la pantalla de entrada (libre)
GET  /api/v1/sesion                     → quién soy y qué puedo hacer
POST /api/v1/sesion/entrar   {usuario_id, pin}
POST /api/v1/sesion/salir    {por}      → cambio | bloqueo | salir
GET/POST/PUT/DELETE /api/v1/usuarios[/{id}]
GET  /api/v1/turnos/{id}/presencias     → quién estuvo, cuánto rato y en qué tramos
```

**Son DOS candados en capas, y es a propósito.** `acceso.py` cuida la RED (qué equipo
puede hablarle a la caja) y `sesion.py` cuida la IDENTIDAD (quién está frente a la
pantalla). Tienen reglas OPUESTAS para `127.0.0.1`: la red lo deja pasar libre porque el
cajero no debe tener fricción, y el login tiene que morder justo ahí, porque ése es el PC
de la caja. Fundirlos obligaría a romper una de las dos.

**Con cero usuarios activos, la caja funciona sin login y todos entran como dueño.** No es
un descuido: la base del local ya está vendiendo y no tiene usuarios; si esta versión
exigiera login, el lunes en la mañana nadie podría cobrar. Al crear el primer usuario la
puerta se cierra sola y no se vuelve a abrir mientras quede alguien activo. El primer
usuario es SIEMPRE dueño, si no el local quedaría sin nadie capaz de crear usuarios.

El PIN se guarda con PBKDF2-HMAC-SHA256 y sal (solo biblioteca estándar). La sesión es una
galleta firmada con HMAC, no una tabla: la caja es un computador con 2-4 personas, no un
SaaS. Lo que sí va a la base es la **presencia**, porque es el dato que se pidió. El rol se
lee de la base en cada petición, no de la galleta: ascender o bajar a alguien tiene efecto
al toque.

La llave que firma las galletas vive en `.secreto`, un archivo suelto en la raíz. No va
dentro de `pos.db` porque entonces viajaría en cada respaldo, o sea el respaldo sería una
llave maestra. Empieza con punto: el actualizador nunca lo pisa. Perderlo cuesta
exactamente una cosa — todos marcan su PIN una vez más.

| Permiso | Dueño | Cajero |
|---|:--:|:--:|
| vender, anular, abrir caja, ver el día | ✅ | ✅ |
| cerrar la caja que abrió esa misma persona | ✅ | ✅ |
| cerrar una caja que abrió otro (`turno_cerrar_ajeno`) | ✅ | — |
| ver la bodega y anotar compras y mermas | ✅ | ✅ |
| editar la carta, informes, respaldos | ✅ | — |
| ajustar stock (conteo físico), crear usuarios | ✅ | — |
| anular una venta de una caja YA CERRADA | ✅ | — |

> El cajero SÍ puede anular una venta del turno en curso. Prohibírselo suena prudente y no
> lo es: a las 8 de la mañana el dueño no está, y el cajero terminaría dejando la venta
> mala adentro — que descuadra la caja al cierre. El control es que toda anulación queda
> con autor y motivo, no que no se pueda hacer.

> El cajero **no** cierra la caja de otro, y ahí sí se le corta el paso. No es el mismo
> caso que la anulación: una venta mala que queda adentro descuadra la caja, o sea que
> impedirla causa el daño. Un cierre firmado por quien no contó el fondo no arregla nada —
> el cajón ya está contado o no lo está— y en cambio borra al único testigo del descuadre.
> La pantalla avisa ANTES de que se cuente un solo billete, con el nombre de quien la
> abrió: enterarse después de contar sería hacerle contar la plata entera para nada.

### Inventario `[IMPL]`
```
GET  /api/v1/inventario                      → insumos, valor, qué falta comprar
GET  /api/v1/inventario/alertas
GET  /api/v1/inventario/insumos/{id}/movimientos   → el libro de ese insumo
POST/PUT/DELETE /api/v1/inventario/insumos[/{id}]
POST /api/v1/inventario/compras  {insumo_id, envases, compra_costo}
POST /api/v1/inventario/mermas   {insumo_id, cantidad, motivo}   ← motivo obligatorio
POST /api/v1/inventario/conteo   {conteos:{"3":4000}, nota}
POST /api/v1/inventario/recalcular
GET/PUT/DELETE /api/v1/productos/{id}/receta
POST /api/v1/productos/{id}/receta/tal-cual  {stock_inicial, minimo, compra_costo}
POST /api/v1/inventario/llevar-la-cuenta-de-todo  -> {cuantos}
```

**Un solo modelo para los dos casos.** El alfajor que se vende tal cual también es un
Insumo (unidad `un`) y su producto tiene una receta de una línea. Con dos mecanismos —una
columna `stock` en Producto para lo simple y recetas para lo preparado— habría dos verdades
y dos códigos que descontar, y el día que exista el combo "café + alfajor" el alfajor
saldría de los dos lados y los números dejarían de cuadrar.

**`llevar-la-cuenta-de-todo` existe porque un producto sin inventario no tiene tope.** No
es un atajo de comodidad: es el arreglo de un agujero. Le da su propio insumo y una receta
de 1 —al costo y con el saldo en cero— a cada producto activo que no tenga ninguna. **No
toca a los que ya llevan cuenta ni a los que tienen receta de verdad:** un capuchino no
"es" un insumo, se hace con leche y café, y convertirlo en su propio insumo descontaría dos
veces. Empieza en cero a propósito: cero es la verdad hasta que alguien cuente la bodega, y
un número inventado sería peor que ninguno.

**El libro es la verdad; `Insumo.stock` es una copia rápida.** El saldo existe para que
cobrar sea un UPDATE y no un SUM sobre todo el historial de la leche. Si alguna vez se
despegan, manda el libro: `/recalcular` lo reconstruye y **reporta** las diferencias en vez
de arreglarlas calladamente.

**El stock nunca bloquea una venta, y no existe la opción de configurarlo para que lo
haga.** Hay cola en el mostrador y el cliente muchas veces ya pagó en la máquina del banco;
si el POS se negara, el cajero solo podría mentirle al cliente o anotar la venta en un
papel. Además el número siempre está algo equivocado, porque sale de recetas que son
estimaciones. Y un saldo negativo es la señal más valiosa que da el sistema: −4 L dice
"vendiste más lattes que la leche que tus papeles decían que tenías", o sea hay una compra
sin registrar. Bloquear destruiría esa señal, porque obligaría al cajero a inventar un
ajuste falso para poder vender.

**Anular devuelve el stock leyendo el libro, no la receta.** Si entremedio alguien cambió
el latte de 200 a 180 ml, recalcular devolvería 180 y se perderían 20 ml para siempre sin
que nadie lo note. Es el mismo principio por el que `VentaLinea` congela el precio. De
regalo, una venta anterior a que existiera la receta no escribió movimientos y no devuelve
nada, sin ningún caso especial.

### Traer la carta de otro lado `[IMPL]`
```
POST /api/v1/importar/archivo   (multipart)  → previsualización
POST /api/v1/importar/texto     {texto}      → previsualización
POST /api/v1/importar/aplicar   {productos, sacar_lo_que_no_vino}
```

**Dos pasos separados, siempre.** Leer no escribe. El archivo de un cliente siempre trae
algo raro —un total al final, una fila de encabezado, un producto repetido— y lo único que
evita que eso entre a la caja es que una persona lo vea antes. `aplicar` recibe la lista ya
revisada, no el archivo: lo que se guarda es lo que la persona confirmó en pantalla.

**El .xlsx se lee con biblioteca estándar** (`core/planilla.py`): un xlsx es un ZIP con XML
adentro. Agregar `openpyxl` obligaría al local a bajar los 29 MB del ejecutable otra vez en
vez de una actualización de 140 KB — el mismo motivo por el que el código viaja suelto al
lado del .exe.

**El punto y la coma se resuelven por la forma, no por el símbolo.** `3.500` son tres mil
quinientos, pero Excel guarda `4.0365000000000005` cuando la celda tenía una fórmula. Sin
separar esos casos, ese precio entra a la caja como cuarenta mil billones de pesos: pasó
con una planilla real. Ver `core.planilla.a_precio`, y `parece_precio` para distinguir un
precio de un texto que tiene números («CARTA 2026» no vale $2.026).

**Un archivo incompleto no puede borrar una carta.** Lo que está en la caja y no viene en
el archivo se informa pero no se toca; sacarlo es una casilla aparte, en falso por defecto,
y es borrado lógico.

**Al actualizar solo se pisa el precio.** El dibujo y la descripción quedan como estaban:
si alguien los ajustó a mano, esa decisión vale más que lo que adivinó el importador.

### Administración de la carta `[IMPL]`
```
GET/POST/PUT/DELETE /api/v1/productos[/{id}]
GET/POST/PUT/DELETE /api/v1/categorias[/{id}]
```
`DELETE` sobre un producto lo marca `activo=false` (borrado lógico), no lo elimina: las
ventas viejas tienen que seguir cuadrando.

---

## 4. Quién puede entrar `[IMPL]`

El punto de venta escucha en **toda la red del local** (`0.0.0.0`), porque las pantallas
del menú suelen vivir en otro computador. Pero en una cafetería el wifi de invitados está
en la misma red: sin candado, un cliente podría abrir la caja desde el celular y registrar
o anular ventas.

La regla, en `apps/pos/acceso.py`:

| Desde dónde | Qué pasa |
|---|---|
| El propio PC de la caja (`127.0.0.1`) | Entra directo, sin PIN. Cero fricción para el cajero. |
| Otro equipo de la red | Pide el PIN una vez y deja una galleta de 180 días. |
| Cualquiera, a `/api/v1/carta` y `/api/v1/salud` | Libre: son de solo lectura y muestran precios que ya están a la vista. |

El PIN se cambia con la variable `POS_PIN` (por defecto `2468`). El token de la galleta se
deriva del PIN, así que reiniciar el programa no desloguea al tablet.

> Esto **no** dice quién vendió: solo impide que entre cualquiera desde la red. Quién es
> la persona lo resuelve el otro candado, el de usuarios, más abajo en esta misma sección.

## 5. Puertos y orígenes

| Qué | Puerto | Por qué fijo |
|---|---|---|
| Punto de venta | **8090** | El navegador guarda la sesión por origen; si el puerto baila, se pierde |
| Pantallas del menú | 8123 | Ya definido en `menu-cafeteria` |

En la misma máquina o en la red del local: las pantallas apuntan a
`http://<ip-del-pc-de-la-caja>:8090/api/v1/carta`.

---

## 6. Lo que NO hace este POS (y es a propósito)

- **No emite boleta electrónica** todavía. Registra la venta y cuadra la caja.
- **No cobra tarjetas.** El pago con tarjeta se hace en la máquina del banco.
- **No cobra tarjetas.** El pago con tarjeta se hace en la máquina del banco y en el POS
  se registra el medio de pago. Integrar Transbank es otro proyecto.
