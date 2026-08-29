# Punto de venta — cafetería

> Caja registradora para una cafetería chilena. Registra ventas, cuadra el turno, y
> **es el dueño de la carta**: las pantallas del local leen los precios de acá, así que
> no hay dos listas que mantener.
>
> Fuente de verdad técnica: **[`docs/CONTRATO.md`](docs/CONTRATO.md)**.
> Para el dueño del local, sin tecnicismos: **[`LEEME.md`](LEEME.md)**.

---

## Arrancar

Doble clic en **`INICIAR-POS.bat`**. La primera vez crea el entorno, instala lo necesario
y siembra una carta de ejemplo; después abre solo en <http://127.0.0.1:8090>.

Manual:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m tools.demo.seed
.venv/Scripts/python -m uvicorn apps.pos.main:app --port 8090
```

Tests:

```bash
.venv/Scripts/python -m pytest -q          # 70 tests, corren contra una base aparte
```

> ⚠️ Los scripts que importan `apps/` o `core/` se corren con **`-m` desde la raíz**
> (`python -m tools.demo.seed`), nunca como archivo suelto: si no, fallan los imports.

---

## Cómo está organizado

```
pos-cafeteria/
├── INICIAR-POS.bat        ← lanzador (doble clic)
├── conftest.py            ← pytest: fija una base de prueba ANTES de importar nada
├── pos.db                 ← la base (SQLite). No va a git.
│
├── core/
│   ├── config.py          ← puerto, red, PIN, zona horaria, IVA, permisos, unidades
│   ├── planilla.py        ← lee Excel y CSV sin dependencias; precios chilenos
│   └── schemas.py         ← contratos de entrada (Pydantic)
│
├── apps/pos/
│   ├── main.py            ← arma la app FastAPI, CORS, candado y sirve la caja
│   ├── acceso.py          ← candado de red: la caja no puede quedar abierta al wifi
│   ├── actualizar.py      ← descarga y reemplaza código, jamás los datos
│   ├── db/models.py       ← 10 tablas. Fuente de verdad del modelo.
│   ├── db/migraciones.py  ← agrega columnas nuevas sin perder las ventas
│   ├── sesion.py          ← candado de IDENTIDAD: quién está frente a la pantalla
│   ├── api/
│   │   ├── catalogo.py    ← carta, categorías y productos (incluye /carta)
│   │   ├── ventas.py      ← registrar, listar, anular, resumen del día
│   │   ├── turnos.py      ← abrir y cerrar caja, arqueo por denominación
│   │   ├── usuarios.py    ← login por PIN, permisos y presencia en el turno
│   │   ├── inventario.py  ← insumos, recetas y el libro de movimientos
│   │   ├── importar.py    ← traer la carta desde un Excel, CSV o pegada
│   │   ├── datos.py       ← respaldo y CSV para el contador
│   │   └── impresion.py   ← comprobante y cierre imprimibles (80 mm)
│   ├── static/            ← la pantalla del cajero (HTML+JS plano, sin build)
│   │   ├── dibujos.js     ← los mismos dibujos de las pantallas del local
│   │   ├── teclado.js     ← teclado numérico en pantalla (táctil)
│   │   └── guias.js       ← las guías que se leen dentro de la caja
│   └── tests/
│
├── Kofe.py                ← el lanzador: abre la ventana y levanta el servidor
├── despliegue/
│   ├── construir_exe.py   ← arma Kofe.exe + la carpeta que se entrega (~56 MB)
│   ├── empaquetar.py      ← arma el ZIP de ACTUALIZACIÓN (~170 KB)
│   ├── ordenar_carpeta.py ← arma D:\Kofe, todo ordenado para una persona
│   └── icono/             ← kofe.svg y el .ico que usa el ejecutable
├── tools/
│   ├── demo/seed.py       ← carta de ejemplo (la misma de las pantallas)
│   ├── demo/ventas.py     ← ventas de ejemplo para mostrar los informes
│   ├── buscar_actualizacion.py  ← el mismo actualizador, desde la terminal
│   ├── respaldo.py        ← copias de la base (arranque, cierre de caja, botón)
│   ├── registro.py        ← una fila por cierre en un CSV, sin apretar nada
│   ├── acceso_directo.py  ← el icono en el escritorio (NO va en Kofe.py: mira por qué)
│   └── datos_de_red.py    ← imprime la IP y el PIN al arrancar
├── respaldos/             ← copias de pos.db. No va a git.
└── docs/CONTRATO.md       ← modelo de datos + API
```

---

## Cómo se conecta con las pantallas del local

El proyecto `menu-cafeteria` (las dos pantallas del local) lee la carta desde acá:

```
http://<ip-del-pc-de-la-caja>:8090/api/v1/carta
```

En la pantalla: tecla `C` → **Punto de venta** → pegar esa dirección → **Probar la conexión**.
Desde ahí, cambiar un precio en la caja lo cambia en la pantalla en la siguiente revisión.
Verificado de punta a punta: subí el Espresso de $1.900 a $2.100 en la caja y la pantalla
lo tomó sola.

---

## Actualizaciones

La caja se actualiza sola desde el número de versión de la barra, o con
`BUSCAR-ACTUALIZACIONES.bat`. Reemplaza el código y **nunca** toca `pos.db`,
`respaldos/` ni `.venv/`; guarda lo que pisa en `_version_anterior/` y se
reinicia sola: `Kofe.py` le pasa al actualizador su propia función `relanzar`, que lanza
la copia nueva desprendida antes de morir. En el plan B del navegador —donde se corre
uvicorn sin pasar por `Kofe.py`— el que la levanta de nuevo es el bucle de
`INICIAR-POS.bat`, que mira el código de salida 3.

Cómo publicar una versión: [`docs/PUBLICAR-ACTUALIZACIONES.md`](docs/PUBLICAR-ACTUALIZACIONES.md).
Historial: [`VERSIONES.md`](VERSIONES.md).

> ⚠️ El canal apunta a `github.com/Pacmancinya/pos-cafeteria`, que **todavía no
> existe**. Hasta que se cree (o se apunte a otra dirección con `POS_URL_VERSION`),
> "Buscar actualizaciones" dice que no pudo conectarse. La actualización a mano
> —descomprimir el ZIP encima— funciona igual.

Probado de punta a punta: se instaló la v1.0, se hizo una venta, se publicó una
v1.1 con un archivo nuevo en `apps/pos/api/`, y tras actualizar la venta seguía
ahí, el archivo nuevo respondía y la caja volvió sola en 6 segundos.

---

## Entregar el programa al local

Mismo patrón que Gesfact: se entrega una carpeta **chica** y en el primer doble clic se
convierte en la app completa.

```bash
.venv/Scripts/python -m despliegue.empaquetar
```

Deja `despliegue/Punto-de-venta.zip` (~60 KB, 38 archivos). Adentro va solo el código y
los documentos: **no** viajan `.venv/` (cientos de MB, se regenera), `pos.db` (la base del
local: si viajara, el local heredaría ventas ajenas) ni `respaldos/`.

`INICIAR-POS.bat` en el equipo del local: crea el entorno, instala las dependencias,
siembra la carta de ejemplo, muestra la IP y el PIN, y levanta el servidor. **Si no hay
Python, lo instala solo** (descarga el instalador oficial y lo corre por-usuario, sin pedir
administrador). Sigue el patrón de `INICIAR-APP-GESFACT.bat` de Gesfact, que ya resolvió
esto en PCs de clientes reales.

**Probado en frío**: extraje el ZIP en una carpeta vacía y a los 30 segundos el servidor
respondía, con `.venv`, `pos.db` y `respaldos/` creados solos.

Guía para el local: [`docs/INSTALACION.md`](docs/INSTALACION.md).

**Actualizar una instalación existente:** descomprimir el ZIP nuevo encima. `pos.db` no
viene en el ZIP, así que las ventas y los precios quedan intactos, y
`apps/pos/db/migraciones.py` agrega solas al arrancar las columnas nuevas que traiga la
versión.

---

## Trampas que ya mordieron (leer antes de tocar)

0. **`where python` encuentra un Python que NO existe.** Windows trae alias de la Microsoft
   Store: un `python.exe` de mentira que solo abre la tienda. `where python` lo encuentra y
   devuelve 0, así que cualquier chequeo por PATH da un falso positivo y después
   `python -m venv` falla. **Hay que verificar por resultado**: intentar crear el entorno y
   revisar si el archivo quedó. El orden que funciona es `py -3` → `python` → la ruta donde
   lo instalamos antes → instalarlo. Y después usar la **ruta completa**, porque el PATH de
   esa ventana ya quedó viejo.
0b. **`data-vista` está en el `<main>` de cada vista, no solo en las pestañas.** El manejador
   de clics preguntaba `t.closest("[data-vista]")` primero y se tragaba **todos** los clics
   de adentro: no se podía ni agregar un producto al pedido. Va
   `t.closest(".tab[data-vista]")`. Los selectores de un manejador delegado tienen que ser
   específicos o se comen media aplicación en silencio.

1. **Windows no trae la base de zonas horarias.** Sin el paquete `tzdata`, `ZoneInfo`
   revienta con `America/Santiago`. Está en `requirements.txt` y `core/config.py` falla
   con un mensaje claro a propósito: caer a UTC en silencio partiría el cierre de caja
   en dos días distintos.
2. **`from __future__ import annotations` rompe SQLModel.** En `apps/pos/db/models.py`
   **no va**: con esa importación las anotaciones quedan como texto y SQLAlchemy no
   puede resolver `Relationship`. Revienta recién al abrir la base, no al importar.
3. **`list["Producto"]` en minúscula tampoco lo resuelve.** Hay que usar `List` de
   `typing` en las relaciones.
4. **La carta necesita CORS.** Las pantallas corren en otro puerto = otro origen; sin la
   cabecera `Access-Control-Allow-Origin` el navegador rechaza la respuesta y el menú se
   queda con los precios viejos, sin avisar. Hay un test que lo cuida.
5. **El puerto 8090 es fijo a propósito.** El navegador guarda cosas por origen: si el
   puerto baila, se pierde lo guardado.
6. **La zona horaria no es decorativa.** El día del local no es el día UTC: a las 21:00
   de Santiago ya es el día siguiente en UTC. Por eso las consultas del día pasan por
   `rango_utc_del_dia()` y no por un `date()` pelado.
7. **La consola de Windows llega en cp1252 y revienta con acentos.** Cualquier script que
   imprima texto en una consola tiene que hacer
   `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` primero. Ya mordió en
   `tools/datos_de_red.py`. Desde la 2.0 el arranque normal ya no deja consola abierta
   (el lanzador suelta la caja y se va), así que esto aplica a los scripts de desarrollo
   y al plan B del navegador, que sí la conserva.
8. **Escuchar en `0.0.0.0` sin candado sería un agujero.** El wifi de invitados del local
   está en la misma red que la caja. Por eso existe `apps/pos/acceso.py`: local entra
   directo, la red pide PIN, y la carta queda libre. Hay 8 tests que lo cuidan.
9. **`cd /d "%~dp0"` en un `.bat` está roto.** La barra final de `%~dp0` se come la
   comilla y cmd dice "no se puede encontrar la ruta especificada" — pero sigue corriendo,
   así que el error pasa piola. Va `cd /d "%~dp0."`, con punto. Y nada de bloques
   `if ( ... )` con `goto` adentro: labels planos.
10. **El respaldo NO se hace copiando el archivo.** Copiar `pos.db` mientras la caja vende
   puede dejar una copia corrupta. Se usa `sqlite3.Connection.backup`, y hay un test que
   abre la copia y verifica que los datos estén adentro.

---

## Estado real

**Funciona:** login por PIN con permisos de dueño y cajero, y registro de quién abrió,
quién cerró, quién cobró y quién estuvo en cada turno; inventario con insumos, recetas,
compras, mermas, conteo a ciegas y libro de movimientos (el stock se descuenta al vender y
nunca bloquea el cobro); caja táctil con azulejos cuadrados que muestran el dibujo de cada
producto, rail de categorías con color, buscador que ignora tildes y teclado numérico en
pantalla; carta con categorías y productos (crear, editar y sacar de la venta desde la
misma pantalla), venta con efectivo (con vuelto y botones de billetes) / débito / crédito /
transferencia, descuentos, propina, anulación con motivo, resumen por día con neto e IVA y
lo más vendido, historial por fecha, apertura y cierre de turno con arqueo por denominación
(conteo a ciegas, cuadre al final, fondo del día siguiente y retiro calculado), comprobante
y cierre imprimibles en 80 mm, respaldo automático de la base, exportación a Excel para el
contador, importación de la carta desde Excel/CSV con previsualización, candado de red con PIN,
actualización desde la misma caja, aplicación de Windows
propia (`Kofe.exe`, sin instalar Python) y el endpoint de carta que alimenta las pantallas
del local. **175 tests en verde.**

**No hace (a propósito, ver CONTRATO sección 6):** boleta electrónica, cobro de tarjetas,
proveedores y órdenes de compra, costeo promedio ponderado.

**Lo siguiente que hay que decidir:**

- **Boleta electrónica.** Es la única pieza que falta para que sea el sistema de venta
  oficial del local, y es la que no se puede elegir sin saber qué usa hoy la cafetería
  para emitir boletas. En Chile los caminos habituales son Bsale, Nubox y LibreDTE, y
  difieren bastante en precio y en trabajo de integración. Mientras tanto el comprobante
  dice **NO ES BOLETA** en grande, a propósito.
- **Dónde dejar los respaldos.** Hoy quedan en `respaldos/`, en el mismo disco. Si el
  disco muere, mueren con él. Copiarlos a un pendrive o a la nube es el siguiente paso.
- **Identificar al cajero.** Hoy el turno guarda un nombre escrito a mano. Si el local
  quiere saber quién vendió qué, eso es un PIN por cajero.
