# CLAUDE.md — Kofe, el punto de venta

Guía para cualquier sesión de Claude que abra este repositorio. Léela entera antes de
tocar algo: acá está lo que no sale en las pruebas y que ya rompió cajas de verdad.

> **Nombre.** El producto se va a llamar **Caja Clara**. Hoy el programa, el repositorio y
> los archivos todavía dicen «Kofe». El cambio de nombre se hace con cuidado: cada caja
> instalada busca sus actualizaciones en una dirección fija (ver «Cómo llega una versión»).

---

## Qué es

Punto de venta para cafeterías y locales chicos en Chile: caja táctil, usuarios con PIN,
turnos con arqueo, cuadre de tarjetas, bodega opcional, carta que alimenta los televisores
del local, impresora de tickets y balanza. **Ya lo usan locales reales**, y cada caja se
actualiza sola desde este repositorio, que es **público** a propósito (las cajas leen
`version.json` sin clave; lo que protege las actualizaciones es la firma, no el secreto).

Corre en el computador del local: un servidor FastAPI en `127.0.0.1:8090` y una ventana
propia (`Kofe.exe`, pywebview). Los datos del local viven en su `pos.db` (SQLite) y no
salen de ahí.

---

## Reglas duras

1. **Este repositorio es público.** Nunca `git add -A` ni `git add .`: siempre rutas
   exactas, y mirar `git status` y el diff antes de cada commit. No entra nada de un local
   ni del negocio: nombres de clientes, direcciones, redes, precios reales, correos.
2. **Nunca entra al repositorio** (el `.gitignore` lo cuida, pero no confíes solo en él):
   `pos.db` y sus `-wal`/`-shm` (las ventas del local), `respaldos/`, `registros/`,
   `.secreto` (firma las sesiones de esa caja), `datos-ventana/` (cookies del navegador
   incrustado), `.acceso-directo`, `.env`, y **la llave de firma**
   (`%USERPROFILE%\.kofe\llave-firma.txt`), que no va a ningún lado.
3. **Main es lo que termina en las cajas.** Si no eres Ruperto (el dueño del proyecto):
   trabaja en una rama y abre un pull request. No toques `version.json`,
   `version-piloto.json`, `manifiesto.json` ni `manifiesto.firma`, y no publiques versiones.
4. **Una versión va siempre primero al canal piloto**, nunca directo al estable.
5. **Antes de dar algo por terminado, corre las pruebas.**

---

## Correr y probar

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m tools.demo.seed        # carta de ejemplo
.venv/Scripts/python -m tools.demo.ventas      # ventas de ejemplo (opcional)
.venv/Scripts/python -m uvicorn apps.pos.main:app --port 8090
```

O doble clic en `INICIAR-POS.bat`. Pruebas, desde la raíz:

```bash
.venv/Scripts/python -m pytest apps core tools -q
```

Con las carpetas, no `pytest` pelado: en un equipo donde se armó el exe, pytest entra a
`despliegue/Kofe/_internal` y se cae recogiendo las pruebas de las librerías empaquetadas.
`conftest.py` fija una base de prueba **antes** de importar nada: las pruebas nunca tocan
`pos.db`. Algunas pruebas corren el JavaScript de la pantalla con Node (`*.cjs` en
`apps/pos/tests`); sin Node se saltan.

Los scripts que importan `apps/` o `core/` se corren con `-m` desde la raíz
(`python -m tools.demo.seed`), nunca como archivo suelto.

---

## Mapa del código

```
Kofe.py                 lanzador: abre la ventana (pywebview) y levanta el servidor
INICIAR-POS.bat         plan B sin exe: crea el entorno y levanta uvicorn
core/                   config (puerto, zona horaria, IVA, versión), esquemas, planillas,
                        códigos de barra y de balanza
apps/pos/main.py        arma la app FastAPI y sirve la caja
apps/pos/api/           ventas, turnos, catálogo, usuarios, inventario, importar, datos,
                        impresión, ajustes, actualizaciones, códigos, diagnóstico
apps/pos/db/            modelos (SQLModel) y migraciones que agregan columnas sin perder ventas
apps/pos/static/        el front: HTML + JS plano, sin build
    index.html, app.js    la pantalla del cajero
    pantallas.html        los televisores del local (vitrina y carta)
    pantallas-simple.html para smart TV con navegadores viejos (ES5, sin CSS moderno)
    guias.js              las guías que se leen dentro de la caja (y el manual del local)
apps/pos/acceso.py      candado de red: desde el mismo PC entra directo, desde la red pide PIN
apps/pos/sesion.py      quién está frente a la pantalla (PIN con PBKDF2)
apps/pos/actualizar.py  el actualizador: baja, verifica la firma y reemplaza código
apps/pos/firma.py, vuelta.py   firma y «volver a la versión anterior» (solo biblioteca estándar)
apps/pos/balanza.py     cobro de etiquetas de balanza
apps/pos/impresion_windows.py  impresión por el driver de Windows y ESC/POS en crudo
tools/                  demo, respaldo, restaurar, firmar_version, auditar pantallas, balanza
despliegue/             construir Kofe.exe (construir_exe.py) y los zips
docs/                   contrato, instalación, publicar actualizaciones, SII
```

`docs/CONTRATO.md` es la fuente de verdad técnica (modelo de datos, API y el porqué de cada
regla). El «Estado real» del README quedó atrás en algunos puntos; lo actual está en
`VERSIONES.md`.

---

## Cómo llega una versión a los locales

Resumen de `docs/PUBLICAR-ACTUALIZACIONES.md` (léelo antes de publicar):

- **Dos canales** en la rama `main`: `version-piloto.json` (el local de prueba) y
  `version.json` (todos). Cada uno apunta al zip de una **etiqueta** (`vX.Y`), nunca al de
  `main`.
- Una versión va **primero al piloto** y pasa al estable después de unos días andando.
  Existe porque la 2.12 dejó sin funcionar una pantalla en todos los locales el mismo día.
- **Van firmadas** desde la 2.19 (`tools/firmar_version.py`, firma lo commiteado). La caja
  no instala nada sin firma válida. La llave pública está en `apps/pos/actualizar.py`
  (`LLAVES_PUBLICAS`); la privada solo la tiene quien publica (hoy Ruperto).
- La versión tiene que coincidir en `core/config.py` (`APP_VERSION`, `APP_NOMBRE`),
  `version-piloto.json` y `VERSIONES.md`. Nunca repetir nombre ni texto de novedades.
- **La etiqueta se sube ANTES que main.** El json apunta al zip de la etiqueta: si main
  llega primero, una caja que revise entre medio recibe un 404.
- La actualización reemplaza código y nunca toca `pos.db`, `respaldos/`, `registros/`,
  `.secreto`, `.venv/` ni `_internal/`. Guarda lo que pisa y el dueño puede volver atrás.
- **Cambiar la dirección del repositorio** (renombrarlo, pasarlo a otra cuenta u
  organización) o **pasarlo a privado** se planifica: las cajas leen `URL_VERSION`
  (`core/config.py`), y un repositorio privado necesita `POS_CLAVE_DESCARGA` configurada en
  cada caja ANTES del cambio (el procedimiento está en `docs/PUBLICAR-ACTUALIZACIONES.md`).

---

## Trampas que rompen a todos los locales a la vez

Ninguna de estas sale en las pruebas.

**Módulos dentro de Kofe.exe.** El exe trae solo los módulos de la biblioteca estándar que
PyInstaller vio en los imports de `Kofe.py`; el código de la caja vive afuera y nunca se
analizó. Un import nuevo de la biblioteca estándar en `apps/`, `core/` o `tools/` que no
esté en el exe hace caer la caja justo después de actualizarse. Antes de publicar, revisar
con `.venv/Scripts/pyi-archive_viewer.exe -l -r -b despliegue/Kofe/Kofe.exe` (más los
`_internal/*.pyd` y `sys.builtin_module_names`: `math`, `time` y `sys` vienen incluidos).

**Caché del navegador.** `main.py` reemplaza `__VERSION__` por el número de versión en los
HTML, y cada archivo del front se pide como `archivo.js?v=__VERSION__`. Sin eso, la caja se
actualiza y sigue mostrando la pantalla vieja (pasó en la 2.29). Todo archivo nuevo del
front tiene que pedirse así; `test_cache_estaticos.py` lo cuida.

**Pantallas chicas.** Las cajas de los locales tienen 1024x768, 1366x768 o 1920x1080 con
Windows al 125-150%. Con la ventana maximizada, los casos justos quedan entre 543 y 700 px
de alto útil. Todo cambio de pantalla se mide con `tools/pantallas/auditar.py` (Playwright
con el Edge del equipo, en un entorno aparte, contra una caja de PRUEBA) antes de publicar.
`test_pantallas_chicas.py` cuida los cortes de la hoja de estilos. El computador de
desarrollo (1920x1080 al 100%) no muestra el problema.

**Televisores.** Uno suele ir vertical (1080x1920) como vitrina y **no es táctil**, aunque
la gente igual lo toca: nada que parezca botón. Direcciones: `/pantallas?p=1` fija la
vitrina, `?p=2` fija la carta, `?tv=1` pone el modo kiosco y muestra lo elegido para ese TV
en Configurar (por defecto, las dos turnándose). `?o=vertical|horizontal` fuerza la
orientación. El TV se recarga solo a los ~5 min cuando la caja cambia de versión
(`vigilarVersion`), salvo con Configurar abierto. En la carta vertical la lista va justa:
cualquier alto extra en la cabecera tapa el último producto.

**Zips de prueba.** Este computador tiene `core.autocrlf=true` y GitHub sirve los archivos
con LF; la firma cubre lo guardado. Los zips para probar una actualización se arman con
`git -c core.autocrlf=false archive`.

**Impresora de tickets.** Se imprime en crudo (ESC/POS) por `winspool` con un trabajo
`RAW`, en página de códigos CP850 (tildes y ñ), a 32 columnas en rollo de 58 mm y 48 en
80 mm, con corte al final. Solo recibe texto armado por el servidor.

**Balanza.** Kofe cobra etiquetas de balanza en tres modos (ticket + total, PLU + peso,
PLU + precio). El precio lo decide siempre el servidor (`apps/pos/balanza.py`), nunca el
navegador. Viene apagada: se prende por local en Ayuda → Ajustes → Balanza.

**Otras que ya mordieron** (detalle en el README, «Trampas que ya mordieron»): sin `tzdata`
no hay `America/Santiago` en Windows; `from __future__ import annotations` rompe SQLModel en
`models.py`; el día del local no es el día UTC (`rango_utc_del_dia()`); el respaldo se hace
con `sqlite3.Connection.backup`, nunca copiando el archivo; en un `.bat` va
`cd /d "%~dp0."` con punto.

---

## Cómo se trabaja

- Commits en español, con el estilo de `git log`: una primera línea que dice qué cambia
  para el local («La caja deja de quedarse con la pantalla vieja») y un cuerpo que explica
  por qué.
- Cambios chicos y probados. Si tocas pantallas, míralas en una caja de prueba (con
  `tools.demo.seed` y `tools.demo.ventas`), no solo en las pruebas.
- Nunca pruebes contra la base de un local de verdad.
- Si trabajas desde una rama: pull request hacia `main`, con qué cambia y cómo se probó.

---

## Kofe y Gesfact

Gesfact es otro producto, de otra empresa: usa las cámaras del local para ver cada venta
y la cruza con las boletas. **En este repositorio no hay ninguna conexión implementada con
Gesfact** (solo se lo nombra en comentarios). Del lado de Gesfact existe un modo «Con POS:
Kofe», que lee las ventas de Kofe desde el mismo computador del local, sin que salgan de
ahí; el conector completo está pendiente.

---

## Para entender el proyecto, en este orden

1. `LEEME.md`: Kofe explicado para el dueño de un local, sin tecnicismos.
2. `README.md`: cómo arrancarlo, cómo está organizado y las trampas conocidas.
3. `docs/CONTRATO.md`: el modelo de datos, la API y el porqué de cada decisión.
4. `VERSIONES.md`: qué trajo cada versión; es la mejor historia del producto.
5. `docs/PUBLICAR-ACTUALIZACIONES.md`: cómo llega una versión a las cajas.
6. `docs/INSTALACION.md`: cómo se instala en un local.
7. `docs/SII.md`: lo que falta para emitir boleta electrónica.
8. `docs/BOLETA-ELECTRONICA.md`: diseño de emisión con software propio, sin proveedor.

---

## Pendiente técnico

- **Boleta electrónica (DTE 39).** Es lo más importante que falta: hoy el comprobante dice
  «NO ES BOLETA». Se hará con software propio, sin proveedor; se emite sin internet y
  queda en cola el envío. Ver `docs/BOLETA-ELECTRONICA.md`.
- **El cambio de nombre** a Caja Clara en el programa, el instalador, el icono y los
  documentos, sin cortar las actualizaciones.
- **El repositorio a privado o a una organización**, siguiendo el procedimiento de arriba.
