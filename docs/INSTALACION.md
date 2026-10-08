# Instalar el punto de venta en el notebook del local

> Guía para dejarlo andando. Está escrita para alguien que no es técnico:
> si algo no calza con lo que ves en pantalla, avisa antes de seguir.

---

## Lo que recibes

Un archivo **`CajaTersa-Instalar-vX.Y.exe`**: el instalador. Trae la aplicación completa,
**no hay que instalar Python ni nada más**.

## Lo que necesitas

- Un **notebook o computador con Windows 10 u 11**. No hace falta que sea potente.
- 5 minutos. No necesita internet para instalarse.
- **No pide administrador**: se instala solo para el usuario que lo abre.

---

## La forma fácil: el instalador

1. **Haz doble clic** en `CajaTersa-Instalar-vX.Y.exe`.
2. Si sale una pantalla azul que dice **«Windows protegió su PC»**: toca **Más información** y
   después **Ejecutar de todas formas**. Pasa una sola vez, es normal (ver el paso 4 más abajo).
3. Elige el idioma si te lo pide y toca **Siguiente**. Hay una casilla, apagada, que dice
   **«Abrir Caja Tersa al prender el computador»**: márcala solo si quieres que la caja se
   abra sola cada mañana.
4. Toca **Instalar** y, al terminar, **Finalizar** (deja marcado «Abrir Caja Tersa»).

Listo: queda un icono **Caja Tersa** en el Escritorio y en el menú Inicio. Sigue en el
**paso 5** («Los datos del local y tu usuario»).

- **Si ya estaba instalada, instalar de nuevo es actualizar**: ejecuta el instalador nuevo y
  listo. No se pierde nada: las ventas, los usuarios y los precios se quedan como estaban.
  Si la caja está abierta, el instalador te pide cerrarla primero.
- **Para quitarla**: Configuración de Windows → **Aplicaciones** → **Caja Tersa** → Desinstalar.
  Las ventas y los datos **no se borran**: quedan en la carpeta del programa, por si la
  vuelves a instalar.

> Las cajas que ya se instalaron (con el ZIP, o cuando se llamaba Caja Clara o Kofe) siguen
> como están; no hay que cambiarlas. Se siguen actualizando solas desde el botón de la
> versión, y conservan su ejecutable y su icono de antes. Si quieres pasarlas a la
> aplicación instalada, sigue la sección de abajo.

## Pasar una caja instalada con ZIP a la aplicación

Para un local que hoy usa la caja desde una carpeta (en el Escritorio, en Documentos…, con
`Kofe.exe` o `CajaClara.exe`) y quiere pasar a la aplicación instalada **sin perder nada**.
Sus ventas, usuarios y ajustes se **copian**; la carpeta vieja **no se toca ni se borra sola**.

1. **Actualiza la caja vieja a la última versión** desde el botón de la versión (es
   obligatorio). Así, cuando se mude, la carpeta vieja sabrá avisar «esta caja se mudó» y
   nadie podrá vender en ella; sin eso, las ventas de las dos cajas se separarían. Si no está
   actualizada, el instalador lo dice («Primero abre la caja vieja y deja que se actualice a
   la última versión; después vuelve a correr este instalador») y no sigue con la mudanza.
2. **Cierra la caja** (la ventana). El instalador no sigue si está abierta, y la mudanza
   tampoco: la aplicación comprueba que la caja vieja esté cerrada de verdad.
3. Abre **`CajaTersa-Instalar-vX.Y.exe`**. Después de la bienvenida aparece
   **«¿Este computador ya tenía la caja?»**. El instalador la busca solo por los accesos
   directos del Escritorio, del menú Inicio y de Inicio. Déjala marcada en
   **«Sí, traer las ventas, usuarios y ajustes de la caja anterior»**. Si encontró otra carpeta
   que no es, o ninguna, usa **«Elegir otra carpeta…»** (tiene que ser la que tiene
   `pos.db` y el programa). Si es una caja nueva, marca **«No, es una caja nueva»**.
4. **Siguiente… Instalar… Finalizar.** El instalador borra los accesos directos de la caja
   vieja (solo esos), para que nadie la abra por costumbre; si la vieja se abría sola al prender el
   computador, la nueva queda marcada para hacerlo (puedes desmarcarlo).
5. **Abre Caja Tersa.** La primera vez trae los datos (unos segundos) y muestra un aviso:
   «Se trajeron las ventas y ajustes desde …». En Ayuda → Ajustes queda la línea «Esta caja se
   mudó desde … el …».
6. **Revisa**: las ventas de hoy y de ayer, el cierre de la caja anterior, los usuarios y sus
   PIN, el nombre del local y los productos.
7. **Recién ahí**, si todo está, borra la carpeta vieja. Nunca antes.

Qué pasa con lo demás:

- **Impresora y balanza**: se configuran en la caja (Ayuda → Ajustes), así que viajan con los
  ajustes. La impresora «Kofe Tickets» es de Windows y sigue ahí.
- **Televisores**: siguen apuntando al mismo puerto (8090) de este computador. Mientras la
  caja nueva esté abierta, funcionan como siempre; no hay que tocarlos.
- **Equipos de la red** (tablets, celulares): siguen entrando sin pedir de nuevo el PIN de
  red, porque la llave de las sesiones (`.secreto`) también se copia.
- **Acceso directo**: el de la caja vieja se borra y queda el de Caja Tersa en el
  Escritorio. Si tenías la caja anclada a la barra de tareas, desancla la vieja a mano.
- **Respaldos**: antes de traer nada se saca un respaldo completo
  (`respaldos\antes-de-mudar-<fecha>.db` en la aplicación nueva, que la poda nunca borra).
  Si ese respaldo falla o algo no queda idéntico, **no se muda nada**.
  `Kofe-respaldos` y `%USERPROFILE%\.kofe` no se tocan.

**Si algo sale mal**

- Mientras la mudanza no termine de traer las ventas, **la caja nueva no abre para vender**:
  muestra una pantalla con el motivo en palabras simples (por ejemplo «Cierra la caja vieja
  para terminar la mudanza») y dos botones: **Reintentar** y **Esta caja es nueva, no traer
  nada** (pide confirmación; la caja vieja queda como estaba y la nueva abre normal). Así no
  se pueden crear usuarios ni ventas nuevas que separen los historiales.
- Si se corta la luz o se cierra a la mitad, al abrir de nuevo **se retoma** donde iba.
- Si las ventas se trajeron pero no se pudo copiar algo menor (respaldos, registros, la llave
  de las sesiones), la caja abre y avisa **qué faltó**, con el botón **Reintentar copia**. El
  aviso solo dice que se puede borrar la carpeta vieja cuando todo se copió y se comprobó.
  Si sigue fallando, manda el diagnóstico (Ayuda → Ajustes).
- Si la caja nueva ya tenía ventas o usuarios propios, **no se trae nada** y lo avisa, para
  no pisarlos.
- **Salida de emergencia**: si la aplicación nueva no abre, entra a la carpeta vieja y
  **borra solo el archivo `ESTA-CAJA-SE-MUDO.txt`**. La caja vieja vuelve a funcionar igual
  que antes. (Lo que se haya vendido en la nueva después de mudarse no está en la vieja.)

Para instalar sin pantallas (pruebas): `CajaTersa-Instalar-vX.Y.exe /VERYSILENT
/MUDARDESDE="C:\ruta\de\la\caja"`.

## La otra forma: el ZIP

Si ya tienes **`CajaTersa-instalar-vX.Y.zip`** (unos 29 MB), también sirve: se extrae y se
abre. Estos son los pasos.

### 1. Desbloquea el ZIP ANTES de extraerlo

Clic derecho sobre `CajaTersa-instalar-vX.Y.zip` → **Propiedades** → abajo de todo, si aparece una
casilla que dice **Desbloquear**, márcala y dale **Aceptar**.

> **Por qué.** Windows le pone una marca de "bajado de internet" a todo lo que sale de un
> ZIP descargado — en este paquete son más de 1.600 archivos — y por esa marca se niega a
> cargar una parte del programa. El resultado es que la caja se abre en el navegador en vez
> de en su propia ventana. Desbloquear el ZIP **antes** de extraerlo evita el problema de
> raíz, porque la marca no llega a pasar a los archivos.
>
> Si se te olvida, no pasa nada grave: el programa se destraba solo la primera vez que lo
> abres. Este paso es para que funcione bien a la primera.

### 2. Descomprime el ZIP donde quieras dejarlo

Clic derecho sobre `CajaTersa-instalar-vX.Y.zip` → **Extraer todo**. Recomendado: dejar la carpeta
en el **Escritorio** o en `C:\CajaTersa`.

> ⚠️ **No lo dejes dentro del ZIP.** Si haces doble clic sin extraer, Windows lo abre en
> una carpeta temporal y se pierde todo cada vez, ventas incluidas.

### 3. Doble clic en `CajaTersa.exe`

Se abre la aplicación, con su ventana y su icono de gota. La primera vez demora unos
segundos más porque prepara la base de datos.

> Dentro de la carpeta hay otras cosas (`_internal`, `apps`, `core`…). **No se tocan.**
> Lo único que se abre es `CajaTersa.exe` (en las cajas instaladas antes se llama `CajaClara.exe`, o `Kofe.exe` si son de antes de la 2.31).

### 4. Si Windows muestra un aviso azul (con el instalador o con el ZIP)

La primera vez puede aparecer una pantalla azul que dice **“Windows protegió tu PC”**.
Es normal: el programa es nuevo y Windows todavía no lo conoce. No es un virus.

1. Toca **Más información**.
2. Toca **Ejecutar de todas formas**.

Pasa **una sola vez**. De ahí en adelante abre directo.

> ¿Por qué pasa? Porque el programa no está firmado con un certificado comercial. Un
> certificado cuesta del orden de US$200 al año y solo sirve para que no salga ese aviso;
> no cambia en nada cómo funciona el programa. Si algún día quieren, se puede comprar.

### 5. Los datos del local y tu usuario

La primera vez, la caja pregunta **cómo se llama el local** (y, si quieres, su RUT y su
dirección: salen en el comprobante), y después **tu nombre y un PIN de 4 números**. Ese
primer usuario queda como **dueño**: es el único que puede crear a los cajeros, cambiar
precios y ver los ajustes.

Esto se hace **en el computador de la caja**. Desde un tablet no se puede crear el primer
usuario: así nadie conectado al Wi-Fi se queda con una caja recién instalada.

> Elige un PIN que no sea 1234 y que los cajeros no sepan: es lo que separa lo tuyo de lo
> de ellos.

Al terminar aparece, en grande, el **PIN de red**: 6 números que son solo de esta caja.
**Anótalo.** Lo piden los tablets y los otros computadores del local la primera vez que
abren la caja. Si se te olvida, lo ves en **Ayuda → Ajustes**.

### 6. Anota la dirección para las pantallas del menú

Abre la pestaña **Carta**: arriba aparece la dirección que hay que pegar en las pantallas
del local para que tomen los precios desde la caja. Es algo así:

```
http://192.168.1.12:8090/api/v1/carta
```

Guárdala.

---

## Dejarlo cómodo para el día a día

### Que se abra con un clic desde el Escritorio

**No hay que hacer nada.** La primera vez que arranca, la caja deja sola un icono
«Caja Tersa» en el escritorio (en las cajas instaladas antes conserva su nombre: «Caja Clara», o «Kofe - Punto de venta» si son de antes de la 2.31), apuntando al lanzador que de verdad sirve en
ese equipo. Si el dueño lo borra, no se vuelve a crear: se entiende que no lo quiere.

No lo crees a mano con **Enviar a → Escritorio**: eso apunta al archivo sobre el que
hiciste clic derecho, y en un equipo donde el `.exe` está bloqueado ese icono no abre
nada. El que crea el programa ya eligió bien.

Para dejarlo en la barra de tareas: abre el programa, clic derecho en su icono de la barra
→ **Anclar a la barra de tareas**.

### Que se abra solo al prender el computador

Con el instalador es una casilla al instalar (si no la marcaste, vuelve a ejecutar el
instalador y márcala). A mano:

1. Tecla **Windows + R**, escribe `shell:startup` y Enter.
2. Se abre una carpeta. Copia ahí el icono de la caja del escritorio
   (cópialo, no lo arrastres: arrastrar lo MUEVE y desaparece del escritorio).

### Que no se apague la pantalla

Configuración de Windows → **Sistema** → **Inicio/apagado** → en "Apagar la pantalla"
elige **Nunca**.

---

### Que las ventas no dependan de este disco

La caja guarda un respaldo al abrir y otro al cerrar, pero en el mismo computador: si el
disco se muere o se lo roban, se van las ventas junto con sus respaldos. En **Ayuda →
Ajustes → Copia de afuera** elige una carpeta que se sincronice sola con la nube (OneDrive,
Google Drive, Dropbox) o un pendrive que quede conectado, y aprieta **Respaldar ahora**.
Tiene que decir *«se revisó y abre bien»*.

## Lo primero que hay que hacer adentro

1. **Crear a los cajeros.** Cada uno con su PIN. Así la caja sabe quién hizo qué.
2. **Cambiar la carta.** Los productos y precios que trae son de ejemplo.
   Pestaña **Carta** → cambias precios, agregas los tuyos con **+ Producto**, y sacas
   los que no vendes.
3. **Cargar la bodega, de a poco.** Pestaña **Bodega** → **+ Insumo** con la leche y el
   café, y después le pones la receta a los productos que más vendes. No hace falta cargar
   todo: lo que no tenga receta se vende igual.
4. **Abrir la caja** cada mañana con el fondo que haya en el cajón, y **cerrarla** en la
   noche contando el efectivo.

---

## Cómo actualizar el programa más adelante

**Lo normal:** el número de versión de la barra se pone verde solo cuando hay algo nuevo.
Le haces clic y aprietas **Actualizar ahora**. La caja se cierra y se vuelve a abrir sola
en unos segundos.

Las actualizaciones pesan unos **120 KB**, no 29 MB: solo viaja el programa, no el motor.

**Si prefieres a mano:** ejecuta el instalador de la versión nueva (`CajaTersa-Instalar-vX.Y.exe`)
encima, o bien:

1. Cierra la aplicación.
2. Descomprime el ZIP de actualización **encima** de la carpeta, aceptando reemplazar.
3. Vuelve a abrir `CajaTersa.exe` (o `CajaClara.exe` / `Kofe.exe`, el que tenga la carpeta).

**No se pierden las ventas, los usuarios ni los precios**: `pos.db` no viene en el ZIP, así
que tu base se queda como está. Y si la versión nueva agrega campos, el programa se los
agrega solo a la base al arrancar.

---

## Si algo no funciona

| Lo que ves | Qué hacer |
|---|---|
| “Windows protegió tu PC” | **Más información** → **Ejecutar de todas formas**. Pasa una sola vez. Es SmartScreen, y **no** es lo mismo que lo de abajo. |
| **“El Control de aplicaciones inteligente bloqueó el acceso”** | Es otra cosa y más dura: bloquea el programa **y sus librerías**, no tiene excepciones por aplicación, y no se arregla con "Ejecutar de todas formas". Hay que apagarlo: **Seguridad de Windows** → **Control de aplicaciones y explorador** → **Control de aplicaciones inteligente** → **Desactivado**. Desde abril de 2026 se puede volver a activar cuando quieras, sin reinstalar Windows. |
| El antivirus lo borró o lo bloqueó | Agrégalo a las excepciones del antivirus (la carpeta completa). Pasa con programas nuevos que no tienen certificado. |
| No abre nada al hacer doble clic | La carpeta quedó dentro del ZIP. Extráela de verdad (clic derecho → Extraer todo) y abre el `.exe` de ahí. |
| “Hay otro programa ocupando el puerto 8090” | Ya está abierto en otra ventana, o quedó corriendo de antes. Ciérralo desde el Administrador de tareas y vuelve a abrir. |
| Se abre la ventana pero queda en blanco | Espera unos segundos: todavía estaba arrancando. Si sigue así, ciérrala y vuelve a abrir. |
| **Se abrió en el navegador** y salió un aviso diciéndolo | Es el plan B: funciona igual, pero la ventana propia no pudo abrir. Cierra todo, borra la carpeta, desbloquea el ZIP (paso 1) y extrae de nuevo. Adentro de la carpeta queda `problema-ventana.txt` con el motivo: mándamelo. |
| Olvidé el PIN del dueño | Se puede resetear desde el mismo computador. Pídemelo: son dos minutos. |
| Otro equipo del local no entra | Tiene que estar en la misma red, y la primera vez pide el **PIN de red**: el dueño lo ve en Ayuda → Ajustes. |
| Dice «Demasiados intentos» | Se escribió mal el PIN cinco veces seguidas. Hay que esperar lo que dice (empieza en 30 segundos) y probar de nuevo. |
| Algo anda raro y hay que avisar | Ayuda → Ajustes → **Descargar diagnóstico**, y manda ese archivo por WhatsApp. No lleva tu PIN ni tus claves. |
| Se murió el disco o se perdió el computador | Si había copia de afuera, la base está en la carpeta `Kofe-respaldos`. Se vuelve con `tools/restaurar.py`; pídeme ayuda. |
| Las pantallas no toman los precios | Revisa que pegaste la dirección con la IP (no `127.0.0.1`) y que el computador de la caja esté encendido. |

---

## Para el que arma el instalador

Después de `python -m despliegue.construir_exe`, corre `python -m despliegue.construir_instalador`:
deja `despliegue/CajaTersa-Instalar-vX.Y.exe` junto a los zips. Necesita Inno Setup 6, que es
gratis (`winget install --id JRSoftware.InnoSetup -e`). La versión sale de `core/config.py`.
El script es `despliegue/instalador/caja-tersa.iss`. Instala por usuario en
`%LOCALAPPDATA%\Programs\CajaTersa` (el actualizador escribe ahí; si el computador ya tenía
una instalación de antes, el instalador la reutiliza en su carpeta vieja) y jamás borra `pos.db`,
`respaldos\`, `registros\`, `.secreto` ni `datos-ventana\`, ni al reinstalar ni al desinstalar.
En una mudanza desde una caja vieja solo borra accesos directos (`.lnk`) de esa caja; los datos
los copia la aplicación al abrir (`apps/pos/mudanza.py`), no el instalador.

## Para el que instala: la versión sin `.exe`

La carpeta también trae `INICIAR-POS.bat`, que hace lo mismo pero usando el Python del
computador (y lo instala si falta). Sirve para probar cambios en el código sin volver a
construir el ejecutable. Para el local no hace falta: `CajaTersa.exe` es más simple.
