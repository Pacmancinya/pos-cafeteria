# Cómo publicar una actualización

> Guía para **Ruperto**, no para el local. Mismo mecanismo que la Biblioteca
> Láser, adaptado a que este proyecto vive en subcarpetas.

---

## El canal de actualizaciones

El programa busca las actualizaciones en:

```
https://raw.githubusercontent.com/Pacmancinya/pos-cafeteria/main/version.json
```

y descarga el paquete desde el zipball de la rama `main`. El repositorio es
**público a propósito**: el actualizador descarga sin credenciales, y meterle
manejo de claves a un programa que corre en el mostrador de una cafetería sería
peor. No hay secretos adentro — la llave que firma las sesiones (`.secreto`) y
la base del local (`pos.db`) están en `.gitignore` y nunca salen del equipo.

Si algún día conviene no publicar el código, sirve cualquier lugar que entregue
dos cosas por https: un `version.json` y un `.zip`. Se cambia con la variable
`POS_URL_VERSION` o editando `core/config.py`.

> **Qué viaja en una actualización.** El zipball trae el repo entero, pero
> `actualizar.py` solo copia `.py`, `.html`, `.css`, `.js`, `.bat`, `.md`,
> `.txt` y `.json`, se salta las carpetas protegidas (`respaldos/`, `.venv/`,
> `despliegue/`, `datos-ventana/`, `_internal/`) y jamás toca `pos.db` ni
> `.secreto`. Por eso una actualización pesa ~160 KB y no 29 MB.

---

## Publicar una versión nueva

1. **Haces los cambios** en el código.

2. **Subes la versión en dos lugares, y tienen que coincidir:**
   - `core/config.py` → `APP_VERSION = "1.1"` y `APP_NOMBRE = "..."`
   - `version.json` → `"version": "1.1"`, `"nombre"` y `"novedades"`

   > **Regla heredada de la Biblioteca Láser:** nunca repitas el nombre ni el
   > texto de novedades entre versiones. Si dos versiones dicen lo mismo, nadie
   > distingue una de otra — y eso ya pasó.

3. **Agregas la fila** en [`VERSIONES.md`](../VERSIONES.md).

4. **Armas el paquete y publicas:**

```bash
.venv/Scripts/python -m despliegue.empaquetar
git add -A && git commit -m "v1.1 - lo que cambiaste" && git push
```

Listo. La próxima vez que la caja se abra, el número de versión de la barra se
pone verde y dice *"Actualizar a v1.1"*.

> GitHub cachea `version.json` unos minutos. Si acabas de publicar y no aparece,
> espera un poco: no está roto.

---

## Qué hace y qué NO hace la actualización

**Reemplaza** el código: `.py`, `.html`, `.css`, `.js`, `.bat`, `.md`, `.json`.
Antes de pisar cada archivo, guarda el anterior en `_version_anterior/`.

**Nunca toca:**

| Qué | Por qué |
|---|---|
| `pos.db` | Son las ventas, los turnos y los precios del local |
| `respaldos/` | Las copias de esa base |
| `.venv/` | El motor instalado en ese computador |

Después de instalar, la caja **se reinicia sola**: `Kofe.py` le pasa al
actualizador su función `relanzar`, que lanza la copia nueva desprendida y
recién ahí sale con código 3. (En el plan B del navegador, donde no pasa por
`Kofe.py`, el que la vuelve a levantar es el bucle de `INICIAR-POS.bat`) y la pantalla se recarga cuando el
servidor responde de nuevo. El dueño no tiene que hacer nada.

---

## Si la versión nueva agrega campos a la base

No hay que hacer nada especial: `apps/pos/db/migraciones.py` compara las tablas
con el modelo al arrancar y agrega las columnas que falten. Está probado sobre
una base con 140 ventas: agregó la columna y no se perdió ninguna.

Lo que **no** cubre: renombrar columnas, cambiar tipos o borrarlas. Si algún día
hace falta, se hace a mano y se avisa en las novedades.

---

## Probar una actualización antes de publicarla

Se puede simular todo el ciclo en tu propio computador, sin tocar GitHub:

1. Arma el ZIP nuevo y déjalo en una carpeta junto a un `version.json` que
   apunte a él con `http://127.0.0.1:9100/Punto-de-venta.zip`.
2. Sirve esa carpeta: `python -m http.server 9100`
3. Abre una instalación de prueba con
   `POS_URL_VERSION=http://127.0.0.1:9100/version.json`.

El actualizador acepta `http` **solo** hacia `127.0.0.1`; para cualquier otra
dirección exige `https`, porque si no cualquiera en la red del local podría
meterle código propio a la caja.

Así se probó este mecanismo antes de entregarlo: se instaló la v1.0, se hizo una
venta, se publicó una v1.1 con un archivo nuevo en `apps/pos/api/`, y después de
actualizar la venta seguía ahí y el archivo nuevo respondía.

---

## La trampa que ya se pagó en la Biblioteca Láser

> *"Publiqué el conversor y al papá le llegó todo menos el conversor."*

El actualizador de allá copiaba **solo los archivos de la raíz** del paquete, así
que un módulo nuevo en una subcarpeta nunca llegaba. Y arreglar la lista no sirve
para la versión en curso: el que copia los archivos es el programa **ya
instalado**, o sea la versión vieja.

Acá el actualizador copia el árbol completo desde el principio, y hay un test
(`test_un_archivo_nuevo_en_una_subcarpeta_si_llega`) que lo cuida.
