# Cómo publicar una actualización

> Guía para **Ruperto**, no para el local.

---

## Los dos canales

Cada caja pregunta por una versión nueva en uno de dos archivos de la rama `main`:

| Canal | Archivo | Para quién |
|---|---|---|
| **Estable** | `version.json` | Todos los locales, por defecto |
| **Piloto** | `version-piloto.json` | El local que elige «Las nuevas, antes que nadie» en Ayuda → Ajustes |

Cada archivo dice qué versión hay y dónde está su zip. El zip es el de una **etiqueta**
(`https://github.com/Pacmancinya/pos-cafeteria/archive/refs/tags/v2.19.zip`), nunca el de
`main`: si apuntara a `main`, el canal estable recibiría lo que se está probando.

La idea es simple: una versión nueva va primero al piloto; si en unos días anda bien, se
copia al estable. La 2.12 tumbó El día en todos los locales el mismo día que se publicó.

---

## La llave de firma — la parte que no se puede perder

Desde la 2.19 cada versión va **firmada**, y una caja no instala nada que no esté firmado
con la llave que conoce. La llave privada vive en:

```
%USERPROFILE%\.kofe\llave-firma.txt
```

- **Guárdala también en un gestor de contraseñas.** Si se pierde, las cajas instaladas no
  aceptan más actualizaciones hasta que alguien les cambie la llave a mano, local por local.
- **Nunca la subas al repositorio**, ni la mandes por WhatsApp o correo.
- La llave pública está en `apps/pos/actualizar.py` (`LLAVES_PUBLICAS`).
- **Para cambiar de llave** (porque se filtró, por ejemplo): publica una versión, firmada
  con la llave VIEJA, cuya `LLAVES_PUBLICAS` tenga las dos. Cuando todas las cajas la
  tengan, firma con la nueva y saca la vieja de la lista.

---

## Publicar una versión nueva

1. **Haces los cambios** y corres las pruebas: `.venv/Scripts/python -m pytest apps/pos/tests -q`.
2. **Subes la versión, y tiene que coincidir en todos lados:**
   - `core/config.py` → `APP_VERSION` y `APP_NOMBRE`
   - `version-piloto.json` → `version`, `nombre`, `novedades` y `zip` (el de la etiqueta)
   - la fila en [`VERSIONES.md`](../VERSIONES.md)

   > Nunca repitas el nombre ni el texto de novedades entre versiones: si dos dicen lo
   > mismo, nadie las distingue.
3. **Commit** de todo eso.
4. **Firmas:**
   ```bash
   .venv/Scripts/python tools/firmar_version.py
   ```
   Firma lo commiteado (no la carpeta: en Windows git deja CRLF en la carpeta y guarda LF,
   y GitHub empaqueta lo guardado). Si hay cambios sin commitear, no firma.
5. **Commit de la firma, etiqueta y subida** (el script te dice los comandos exactos):
   ```bash
   git add manifiesto.json manifiesto.firma && git commit -m "Firma de la v2.19"
   git tag v2.19 && git push && git push origin v2.19
   ```
6. **Al piloto le llega sola.** Cuando haya andado bien unos días, copia el contenido de
   `version-piloto.json` a `version.json`, commit y push: ahí les llega a todos. No hay que
   volver a firmar: el zip de la etiqueta es el mismo.

> GitHub cachea los `version*.json` unos minutos. Si acabas de publicar y no aparece,
> espera un poco: no está roto.

> **La primera versión firmada (2.19) la instalan cajas 2.18, que no revisan firmas.** Desde
> la 2.19 en adelante, todas revisan.

---

## Qué hace y qué NO hace la actualización

**Revisa primero, escribe después.** Baja el zip, lee el manifiesto, comprueba la firma y la
huella de cada archivo, y recién entonces escribe. Si algo no calza, no toca nada.

**Reemplaza** el código: `.py`, `.html`, `.css`, `.js`, `.bat`, `.md`, `.txt`, `.json`. Se
salta todo lo que empieza con punto y las carpetas protegidas.

**Guarda lo que pisa** en `_version_anterior/`, solo de ESTA actualización, con la lista en
`_cambios.json`. El dueño vuelve atrás desde el aviso de versión («Volver a la vX.Y»).

**Nunca queda a medias.** Guarda los originales y anota la lista ANTES de reemplazar el
primer archivo. Si algo falla vuelve atrás al tiro; si se corta la luz, al abrir. Un zip de
más de 60 MB, o que se expande a más de 200 MB, no se abre.

**Nunca toca:**

| Qué | Por qué |
|---|---|
| `pos.db` (y `-wal`, `-shm`) | Son las ventas, los turnos y los precios del local |
| `respaldos/`, `registros/` | Las copias de esa base y el registro de errores |
| `.secreto` | La llave de las sesiones y del PIN de red de esa caja |
| `.venv/`, `_internal/` | El motor instalado en ese computador |

Después de instalar, la caja **se reinicia sola** y los televisores se recargan solos a los
pocos minutos.

---

## Si algún día el repositorio pasa a ser privado

Hoy es público: cualquiera puede bajar el código. Para cerrarlo sin cortarle las
actualizaciones a nadie, en este orden:

1. Crea una clave por local en GitHub (*fine-grained token*, solo lectura de *Contents* de
   este repositorio). Una por local: si una se filtra, se revoca esa sola.
2. En cada caja, pon la clave en la variable `POS_CLAVE_DESCARGA` (CajaClara.exe o Kofe.exe la lee al
   arrancar). Con clave, la caja baja el zip por la API de GitHub, que sí la acepta.
3. Comprueba que UN local actualiza con su clave.
4. Recién ahí, pasa el repositorio a privado.

> Esto no está probado contra un repositorio privado de verdad: se probó que la caja arma
> bien los pedidos con la clave. Hazlo primero con un local.

---

## Probar una actualización antes de publicarla

1. Arma el zip con `git archive --format=zip --prefix=pos-cafeteria-X/ HEAD > p.zip` en un
   commit ya firmado.
2. Sírvelo: `python -m http.server 9100` en esa carpeta, junto a un `version.json` que
   apunte a `http://127.0.0.1:9100/p.zip`.
3. Abre una instalación de prueba con `POS_URL_VERSION=http://127.0.0.1:9100/version.json`.

El actualizador acepta `http` **solo** hacia `127.0.0.1`; para cualquier otra dirección
exige `https`.

---

## La trampa que ya se pagó en la Biblioteca Láser

> *"Publiqué el conversor y al papá le llegó todo menos el conversor."*

El actualizador de allá copiaba **solo los archivos de la raíz** del paquete, así que un
módulo nuevo en una subcarpeta nunca llegaba. Y arreglar la lista no sirve para la versión
en curso: el que copia los archivos es el programa **ya instalado**, o sea la versión vieja.
Acá se copia el árbol completo, y `test_un_archivo_nuevo_en_una_subcarpeta_si_llega` lo
cuida. Lo mismo vale para la firma: la 2.19 la instalan cajas que no la revisan.
