# Instalar el punto de venta en el notebook del local

> Guía para dejarlo andando. Está escrita para alguien que no es técnico:
> si algo no calza con lo que ves en pantalla, avisa antes de seguir.

---

## Lo que recibes

Un archivo **`Kofe-instalar.zip`** de unos 29 MB. Adentro va la aplicación completa:
**no hay que instalar Python ni nada más**. Se extrae y se abre.

## Lo que necesitas

- Un **notebook o computador con Windows 10 u 11**. No hace falta que sea potente.
- 5 minutos. No necesita internet para instalarse.

---

## Paso a paso

### 1. Desbloquea el ZIP ANTES de extraerlo

Clic derecho sobre `Kofe-instalar.zip` → **Propiedades** → abajo de todo, si aparece una
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

Clic derecho sobre `Kofe-instalar.zip` → **Extraer todo**. Recomendado: dejar la carpeta
en el **Escritorio** o en `C:\Kofe`.

> ⚠️ **No lo dejes dentro del ZIP.** Si haces doble clic sin extraer, Windows lo abre en
> una carpeta temporal y se pierde todo cada vez, ventas incluidas.

### 3. Doble clic en `Kofe.exe`

Se abre la aplicación, con su ventana y su icono de tacita. La primera vez demora unos
segundos más porque prepara la base de datos.

> Dentro de la carpeta hay otras cosas (`_internal`, `apps`, `core`…). **No se tocan.**
> Lo único que se abre es `Kofe.exe`.

### 4. Si Windows muestra un aviso azul

La primera vez puede aparecer una pantalla azul que dice **“Windows protegió tu PC”**.
Es normal: el programa es nuevo y Windows todavía no lo conoce. No es un virus.

1. Toca **Más información**.
2. Toca **Ejecutar de todas formas**.

Pasa **una sola vez**. De ahí en adelante abre directo.

> ¿Por qué pasa? Porque el programa no está firmado con un certificado comercial. Un
> certificado cuesta del orden de US$200 al año y solo sirve para que no salga ese aviso;
> no cambia en nada cómo funciona el programa. Si algún día quieren, se puede comprar.

### 5. Crea tu usuario

La primera vez la caja te va a decir que todavía no hay nadie registrado y te va a pedir
tu nombre y un **PIN de 4 números**. Ese primer usuario queda como **dueño**: es el único
que puede cambiar precios, ver los informes y crear a los demás.

Después, desde la misma caja, creas a los cajeros.

> Elige un PIN que no sea 1234 y que los cajeros no sepan: es lo que separa lo tuyo de lo
> de ellos.

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

Clic derecho en `Kofe.exe` → **Mostrar más opciones** → **Enviar a** →
**Escritorio (crear acceso directo)**.

Para dejarlo en la barra de tareas: abre el programa, clic derecho en su icono de la barra
→ **Anclar a la barra de tareas**.

### Que se abra solo al prender el computador

1. Tecla **Windows + R**, escribe `shell:startup` y Enter.
2. Se abre una carpeta. Arrastra ahí el acceso directo que creaste.

### Que no se apague la pantalla

Configuración de Windows → **Sistema** → **Inicio/apagado** → en "Apagar la pantalla"
elige **Nunca**.

---

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

**Si prefieres a mano:**

1. Cierra la aplicación.
2. Descomprime el ZIP de actualización **encima** de la carpeta, aceptando reemplazar.
3. Vuelve a abrir `Kofe.exe`.

**No se pierden las ventas, los usuarios ni los precios**: `pos.db` no viene en el ZIP, así
que tu base se queda como está. Y si la versión nueva agrega campos, el programa se los
agrega solo a la base al arrancar.

---

## Si algo no funciona

| Lo que ves | Qué hacer |
|---|---|
| “Windows protegió tu PC” | **Más información** → **Ejecutar de todas formas**. Pasa una sola vez. |
| El antivirus lo borró o lo bloqueó | Agrégalo a las excepciones del antivirus (la carpeta completa). Pasa con programas nuevos que no tienen certificado. |
| No abre nada al hacer doble clic | La carpeta quedó dentro del ZIP. Extráela de verdad (clic derecho → Extraer todo) y abre el `.exe` de ahí. |
| “Hay otro programa ocupando el puerto 8090” | Ya está abierto en otra ventana, o quedó corriendo de antes. Ciérralo desde el Administrador de tareas y vuelve a abrir. |
| Se abre la ventana pero queda en blanco | Espera unos segundos: todavía estaba arrancando. Si sigue así, ciérrala y vuelve a abrir. |
| **Se abrió en el navegador** y salió un aviso diciéndolo | Es el plan B: funciona igual, pero la ventana propia no pudo abrir. Cierra todo, borra la carpeta, desbloquea el ZIP (paso 1) y extrae de nuevo. Adentro de la carpeta queda `problema-ventana.txt` con el motivo: mándamelo. |
| Olvidé el PIN del dueño | Se puede resetear desde el mismo computador. Pídemelo: son dos minutos. |
| Otro equipo del local no entra | Tiene que estar en la misma red, y la primera vez pide el PIN de red (viene `2468`). |
| Las pantallas no toman los precios | Revisa que pegaste la dirección con la IP (no `127.0.0.1`) y que el computador de la caja esté encendido. |

---

## Para el que instala: la versión sin `.exe`

La carpeta también trae `INICIAR-POS.bat`, que hace lo mismo pero usando el Python del
computador (y lo instala si falta). Sirve para probar cambios en el código sin volver a
construir el ejecutable. Para el local no hace falta: `Kofe.exe` es más simple.
