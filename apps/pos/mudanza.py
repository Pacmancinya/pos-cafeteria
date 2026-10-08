"""Pasar una caja instalada con zip (carpeta suelta) a la aplicación instalada.

El instalador (despliegue/instalador/gespoint.iss) NO copia la base: solo deja en la
carpeta de la aplicación un archivo, `mudar-desde.txt`, con la ruta de la caja vieja. Al
abrir, `main.py` llama a `ejecutar()` ANTES de que nada abra o cree la base, y acá se hace
el traslado con el mecanismo de respaldo de SQLite (`Connection.backup`), nunca copiando
el archivo: la base vieja puede tener ventas sin pasar al .db todavía (modo WAL).

## Reglas (el dueño las puso en este orden de importancia)

  1. NADA se pierde ni se separa. La carpeta vieja queda intacta: se lee en solo lectura y
     lo único que se le agrega es `ESTA-CAJA-SE-MUDO.txt`. Nada se borra ni se mueve solo.
  2. Solo se muda desde una caja vieja que ya tenga este bloqueo (`apps/pos/mudanza.py`
     en su carpeta): así, desde que se pone la marca, esa caja no puede vender aunque la
     abran, y los historiales no se separan.
  3. Solo se muda con la caja vieja CERRADA de verdad: el puerto libre y el mutex de
     instancia única libre (que se toma durante toda la mudanza).
  4. ORDEN: (a) comprobar que la vieja está cerrada; (b) poner la marca en la vieja;
     (c) respaldo «antes-de-mudar», copia a un temporal y verificación completa
     (integrity_check + cantidad y contenido de TODAS las tablas) contra la vieja ya
     bloqueada; (d) instalar la base, copiar lo demás y terminar. Si algo falla en
     (b)-(c), la marca se quita (la vieja vuelve a funcionar) y la mudanza queda pendiente.
  5. Mientras la mudanza esté pendiente la caja NO abre (ver main.py): no se pueden crear
     usuarios ni ventas que separen los historiales.
  6. Cada fase queda en `mudanza-estado.json` (escritura atómica) con la huella de lo
     importado: si se corta a la mitad, al volver a abrir se retoma, y la base ya
     instalada se reconoce como «nuestra copia», no como datos propios.
  7. `mudar-desde.txt` no se borra hasta que todo terminó, incluidos los auxiliares.
  8. `.secreto` también viaja (firma las sesiones y la galleta de los equipos de la red).
     `%USERPROFILE%\\.kofe` y `Kofe-respaldos` NO se tocan: son compartidos.

## Archivos que deja

  mudar-desde.txt       el pedido (lo escribe el instalador). Queda hasta el final.
  mudanza-estado.json   la fase en que va y la huella de lo importado.
  mudanza-error.txt     por qué falló la última vez (se borra al lograrlo).
  mudado-desde.txt      se logró todo: de dónde, cuándo, cuántas filas. (JSON)
  mudanza-no-hecha.txt  la base nueva ya tenía datos propios: no se pisó. (JSON)
  ESTA-CAJA-SE-MUDO.txt en la carpeta VIEJA. Con él, esa caja no deja vender. Es
                        reversible: borrando ese archivo vuelve a funcionar como antes.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import threading
from datetime import datetime

from core.config import DB_URL, RAIZ, ZONA

ARCHIVO_PEDIDO = "mudar-desde.txt"
ARCHIVO_HECHO = "mudado-desde.txt"
ARCHIVO_NO_HECHA = "mudanza-no-hecha.txt"
ARCHIVO_ERROR = "mudanza-error.txt"
ARCHIVO_ESTADO = "mudanza-estado.json"
MARCA_VIEJA = "ESTA-CAJA-SE-MUDO.txt"
NOMBRE_MUTEX = "Kofe-punto-de-venta-8090"      # el mismo de Kofe.py (CERROJO)

# Las fases, en orden. Desde «instalada» la base nueva ya es la copia: no se vuelve atrás.
FASES = ("marca", "respaldo", "verificada", "instalada", "auxiliares")
FASES_INSTALADA = ("instalada", "auxiliares")

# Solo para las pruebas: nombre de una fase en la que se simula un corte.
_CORTAR_EN: str | None = None


class MudanzaFallida(Exception):
    """Algo impidió la mudanza; el mensaje se le muestra al dueño tal cual.

    `tipo`: «vieja_abierta», «version» u «otro» (para elegir el texto de la pantalla)."""

    def __init__(self, mensaje: str, tipo: str = "otro"):
        super().__init__(mensaje)
        self.tipo = tipo


def _punto(fase: str) -> None:
    if _CORTAR_EN == fase:
        raise RuntimeError(f"corte simulado después de «{fase}»")


def _log():
    try:
        from apps.pos import diagnostico
        return diagnostico.log
    except Exception:           # pragma: no cover
        import logging
        return logging.getLogger("kofe")


def _ahora() -> datetime:
    return datetime.now(ZONA)


def _ruta_base_nueva() -> str | None:
    if not DB_URL.startswith("sqlite"):
        return None
    return DB_URL.split("///", 1)[-1]


# ---------------------------------------------------------------------------
# Lecturas y escrituras de papeles
# ---------------------------------------------------------------------------
def bloqueada(raiz: str | None = None) -> bool:
    """¿Esta carpeta ya se mudó? Entonces la caja no puede vender desde acá."""
    return os.path.isfile(os.path.join(raiz or RAIZ, MARCA_VIEJA))


def _leer_texto(ruta: str) -> str:
    with open(ruta, "rb") as f:
        crudo = f.read()
    for codec in ("utf-8-sig", "cp1252"):
        try:
            return crudo.decode(codec)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", "replace")


def _leer_json(ruta: str) -> dict:
    try:
        d = json.loads(_leer_texto(ruta))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir_json(ruta: str, datos: dict) -> None:
    """Atómico: se escribe a un temporal y se reemplaza. Un corte no deja medio archivo."""
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def _leer_estado(raiz: str) -> dict:
    return _leer_json(os.path.join(raiz, ARCHIVO_ESTADO))


def _guardar_estado(raiz: str, st: dict) -> None:
    _escribir_json(os.path.join(raiz, ARCHIVO_ESTADO), st)


def _borrar(*rutas: str) -> None:
    for r in rutas:
        try:
            os.remove(r)
        except OSError:
            pass


def pendiente(raiz: str | None = None) -> bool:
    """¿Hay una mudanza sin terminar de traer la base? Entonces la caja no abre."""
    raiz = raiz or RAIZ
    if not os.path.isfile(os.path.join(raiz, ARCHIVO_PEDIDO)):
        return False
    return _leer_estado(raiz).get("fase") not in FASES_INSTALADA


def estado(raiz: str | None = None) -> dict:
    """Lo que la pantalla necesita saber. Solo lee archivos."""
    raiz = raiz or RAIZ
    if os.path.isfile(os.path.join(raiz, ARCHIVO_PEDIDO)):
        st = _leer_estado(raiz)
        e = _leer_json(os.path.join(raiz, ARCHIVO_ERROR))
        if st.get("fase") in FASES_INSTALADA:
            # La base ya está; falta algo de lo auxiliar. No bloquea, pero no se termina.
            return {"estado": "hecha", "completo": False, "aviso_visto": False,
                    "desde": st.get("desde", ""), "fecha": st.get("fecha", ""),
                    "ventas": st.get("ventas"), "usuarios": st.get("usuarios"),
                    "faltan": st.get("aux_faltan", []), "mensaje": e.get("mensaje", "")}
        return {"estado": "error" if e else "pendiente", "bloquea": True,
                "tipo": e.get("tipo", "otro"), "aviso_visto": False,
                "desde": e.get("desde", "") or st.get("desde", ""),
                "mensaje": e.get("mensaje", ""), "fecha": e.get("fecha", "")}
    for archivo, nombre in ((ARCHIVO_HECHO, "hecha"), (ARCHIVO_NO_HECHA, "no_hecha")):
        d = _leer_json(os.path.join(raiz, archivo))
        if d:
            d["estado"] = nombre
            d["aviso_visto"] = bool(d.get("aviso_visto"))
            d.setdefault("completo", True)
            return d
    return {"estado": "ninguna", "aviso_visto": True}


def marcar_visto(raiz: str | None = None) -> None:
    raiz = raiz or RAIZ
    for archivo in (ARCHIVO_HECHO, ARCHIVO_NO_HECHA):
        ruta = os.path.join(raiz, archivo)
        d = _leer_json(ruta)
        if d and not d.get("aviso_visto"):
            d["aviso_visto"] = True
            try:
                _escribir_json(ruta, d)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def _comillas(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


def _tablas(c: sqlite3.Connection) -> list[str]:
    return [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")]


def _contar(c: sqlite3.Connection) -> dict[str, int]:
    return {t: c.execute(f"SELECT COUNT(*) FROM {_comillas(t)}").fetchone()[0]
            for t in _tablas(c)}


def _huellas(c: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    """(filas, huella del contenido) de CADA tabla: compara fila por fila."""
    salida = {}
    for t in _tablas(c):
        h = hashlib.sha256()
        n = 0
        try:
            filas = c.execute(f"SELECT * FROM {_comillas(t)} ORDER BY rowid")
            for fila in filas:
                h.update(repr(fila).encode("utf-8", "replace"))
                n += 1
        except sqlite3.OperationalError:       # tabla WITHOUT ROWID
            h, n = hashlib.sha256(), 0
            for fila in sorted(repr(f) for f in c.execute(f"SELECT * FROM {_comillas(t)}")):
                h.update(fila.encode("utf-8", "replace"))
                n += 1
        salida[t] = (n, h.hexdigest())
    return salida


def _abrir_solo_lectura(ruta: str) -> sqlite3.Connection:
    # Una URI de archivo a mano (sin pathlib): «file:///C:/ruta/pos.db?mode=ro».
    absoluta = os.path.abspath(ruta).replace("\\", "/")
    from urllib.parse import quote
    uri = "file:///" + quote(absoluta.lstrip("/"), safe="/:") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def _huella_de(ruta: str) -> dict[str, list]:
    """Las huellas de una base ya escrita, en forma que cabe en JSON."""
    c = _abrir_solo_lectura(ruta)
    try:
        return {t: [n, h] for t, (n, h) in _huellas(c).items()}
    finally:
        c.close()


def _datos_de(ruta: str) -> tuple[int, int]:
    """(ventas, usuarios) de una base. Lanza sqlite3.Error si no se puede leer."""
    c = sqlite3.connect(ruta, timeout=10)
    try:
        cuentas = _contar(c)
    finally:
        c.close()
    return cuentas.get("venta", 0), cuentas.get("usuario", 0)


def _quitar_temporal(ruta: str) -> None:
    for sufijo in ("", "-wal", "-shm", "-journal"):
        _borrar(ruta + sufijo)


def _copiar_base(origen: sqlite3.Connection, destino_ruta: str) -> None:
    """Copia consistente (Connection.backup) a un archivo suelto, sin -wal ni -shm."""
    _quitar_temporal(destino_ruta)
    dst = sqlite3.connect(destino_ruta)
    try:
        origen.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst.close()


def _verificar(ruta: str, esperado: dict[str, tuple[int, str]], que: str) -> None:
    c = _abrir_solo_lectura(ruta)
    try:
        sano = c.execute("PRAGMA integrity_check").fetchone()[0]
        if sano != "ok":
            raise MudanzaFallida(f"{que} salió dañada al copiarla ({sano}). No se movió nada.")
        tiene = _huellas(c)
    finally:
        c.close()
    if set(tiene) != set(esperado):
        raise MudanzaFallida(f"{que} no tiene las mismas tablas que la caja vieja. "
                             "No se movió nada.")
    for t, (n, h) in esperado.items():
        if tiene[t][0] != n:
            raise MudanzaFallida(f"En {que} la tabla «{t}» tiene {tiene[t][0]} filas y en la "
                                 f"caja vieja {n}. No se movió nada.")
        if tiene[t][1] != h:
            raise MudanzaFallida(f"En {que} el contenido de la tabla «{t}» no es igual al de "
                                 "la caja vieja. No se movió nada.")


# ---------------------------------------------------------------------------
# La caja vieja tiene que estar cerrada de verdad
# ---------------------------------------------------------------------------
def _puerto_libre(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            s.bind(("0.0.0.0", puerto))
            return True
        except OSError:
            return False


@contextlib.contextmanager
def caja_vieja_cerrada(puerto: int | None, mutex: str | None = None):
    """Deja pasar solo si nadie escucha en el puerto y el mutex de instancia única está
    libre; y mientras dure, el mutex es nuestro (la vieja no puede abrirse a la mitad).

    Si este mismo proceso ya lo tiene (Kofe.py lo toma antes de importar la caja y por eso
    sabemos que nadie más lo tenía), no se vuelve a pedir: nos bloquearíamos nosotros.
    `puerto=None` omite el puerto (cuando ya estamos escuchando nosotros)."""
    nombre = mutex or NOMBRE_MUTEX
    if puerto is not None and not _puerto_libre(puerto):
        raise MudanzaFallida(
            f"Parece que la caja anterior sigue abierta (el puerto {puerto} está ocupado). "
            "Ciérrala y vuelve a intentarlo.", "vieja_abierta")
    handle = None
    k32 = None
    if sys.platform == "win32":
        propio = getattr(sys.modules.get("__main__"), "_handle_cerrojo", None)
        if propio is None:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = k32.CreateMutexW(None, False, nombre)
            if ctypes.get_last_error() == 183:       # ERROR_ALREADY_EXISTS
                if handle:
                    k32.CloseHandle(handle)
                raise MudanzaFallida(
                    "La caja anterior sigue abierta. Ciérrala y vuelve a intentarlo.",
                    "vieja_abierta")
    try:
        yield
    finally:
        if handle and k32 is not None:
            k32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# Lo auxiliar: .secreto, respaldos y registros
# ---------------------------------------------------------------------------
def _sha(ruta: str, hasta: int | None = None) -> str:
    """Huella de un archivo (o de sus primeros `hasta` bytes)."""
    h = hashlib.sha256()
    restante = hasta
    with open(ruta, "rb") as f:
        while True:
            n = 1 << 20 if restante is None else min(1 << 20, restante)
            bloque = f.read(n) if n else b""
            if not bloque:
                break
            h.update(bloque)
            if restante is not None:
                restante -= len(bloque)
    return h.hexdigest()


SUFIJO_COPIA = ".desde-caja-vieja"


def _igual(o: str, d: str) -> bool:
    """¿Es `d` una copia fiel de `o`? Tamaño y huella, no solo que exista."""
    try:
        return os.path.getsize(o) == os.path.getsize(d) and _sha(o) == _sha(d)
    except OSError:
        return False


def _es_copia_cortada(o: str, d: str) -> bool:
    """¿`d` es el comienzo de `o` (una copia nuestra que se cortó a la mitad)?"""
    try:
        tam = os.path.getsize(d)
        return tam < os.path.getsize(o) and _sha(o, tam) == _sha(d)
    except OSError:
        return False


def _copiar_verificado(o: str, d: str) -> bool:
    """Copia `o` a `d` por un temporal (`.copiando`) y lo renombra SOLO después de
    comprobar tamaño y huella contra el origen. Nunca deja `d` a medias."""
    tmp = d + ".copiando"
    _borrar(tmp)
    try:
        shutil.copy2(o, tmp)
        if not _igual(o, tmp):
            _borrar(tmp)
            return False
        os.replace(tmp, d)
        return True
    except OSError:
        _borrar(tmp)
        return False


def _traer_archivo(o: str, d: str) -> bool:
    """Deja una copia VERIFICADA de `o`. True si lo logró.

    · `d` no existe, o es una copia nuestra cortada: se copia a `d`.
    · `d` ya es igual: nada que hacer.
    · `d` existe y es otra cosa: NO se pisa; la copia va a `d + .desde-caja-vieja`, y si
      ese nombre también está ocupado por otra cosa, a `.desde-caja-vieja-2`, `-3`…
      (nunca se reemplaza un archivo que no sabemos de quién es)."""
    if not os.path.exists(d) or _es_copia_cortada(o, d):
        return _copiar_verificado(o, d)
    if _igual(o, d):
        return True
    for i in range(1, 100):
        lado = d + SUFIJO_COPIA + ("" if i == 1 else f"-{i}")
        if not os.path.exists(lado) or _es_copia_cortada(o, lado):
            return _copiar_verificado(o, lado)
        if _igual(o, lado):
            return True
    return False


def _copiar_sin_pisar(origen: str, destino: str) -> tuple[int, list[str]]:
    """Trae una carpeta entera sin pisar nada y sin tocar el origen. Cada archivo se
    verifica; lo que no quedó verificado cuenta como faltante."""
    if not os.path.isdir(origen):
        return 0, []
    copiados, faltan = 0, []
    nombre = os.path.basename(os.path.normpath(origen))

    # os.walk se salta EN SILENCIO las carpetas que no puede leer (permisos de
    # Windows): sus archivos nunca llegarían a `faltan` y la mudanza se daría por
    # completa. Cada carpeta ilegible cuenta como faltante.
    def no_se_pudo_leer(err: OSError) -> None:
        ruta = getattr(err, "filename", None) or origen
        faltan.append(os.path.normpath(os.path.join(nombre, os.path.relpath(ruta, origen))) + os.sep)

    for raiz, _dirs, nombres in os.walk(origen, onerror=no_se_pudo_leer):
        rel = os.path.relpath(raiz, origen)
        carpeta = destino if rel == "." else os.path.join(destino, rel)
        try:
            os.makedirs(carpeta, exist_ok=True)
        except OSError:
            faltan.extend(os.path.join(nombre, rel, n) for n in nombres)
            continue
        for n in nombres:
            o, d = os.path.join(raiz, n), os.path.join(carpeta, n)
            visible = os.path.normpath(os.path.join(nombre, "" if rel == "." else rel, n))
            if _traer_archivo(o, d):
                copiados += 1
            else:
                faltan.append(visible)
    return copiados, faltan


def _copiar_auxiliares(raiz: str, desde: str) -> tuple[dict, list[str]]:
    faltan: list[str] = []
    copiado = {}
    secreto = os.path.join(desde, ".secreto")
    if os.path.isfile(secreto):
        if not _traer_archivo(secreto, os.path.join(raiz, ".secreto")):
            faltan.append(".secreto")
        sesion = sys.modules.get("apps.pos.sesion")
        if sesion is not None:
            sesion._secreto_en_memoria = ""
    for carpeta in ("respaldos", "registros"):
        n, f = _copiar_sin_pisar(os.path.join(desde, carpeta), os.path.join(raiz, carpeta))
        copiado[carpeta] = n
        faltan.extend(f)
    return copiado, faltan


# ---------------------------------------------------------------------------
# La marca en la caja vieja
# ---------------------------------------------------------------------------
def _mismo_lugar(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _texto_marca(raiz_nueva: str, fecha: str) -> str:
    return (
        "ESTA CAJA SE MUDO\r\n"
        "=================\r\n\r\n"
        f"El {fecha} las ventas, los usuarios y los ajustes de esta carpeta se pasaron (o se\r\n"
        "estan pasando) a la aplicacion Gespoint, que ahora vive en:\r\n\r\n"
        f"    {raiz_nueva}\r\n\r\n"
        "Para vender, abre Gespoint desde el icono del escritorio. Esta carpeta ya no\r\n"
        "abre la caja: si la abres, solo muestra un aviso.\r\n\r\n"
        "NO SE BORRO NADA. Todo lo de esta carpeta sigue exactamente como estaba.\r\n\r\n"
        "Cuando abras Gespoint y compruebes que estan las ventas de hoy y de ayer y tus\r\n"
        "usuarios, puedes borrar esta carpeta completa. Hazlo despues de comprobar, no antes.\r\n\r\n"
        "SI LA APLICACION NUEVA NO ABRE (salida de emergencia):\r\n"
        "borra SOLO este archivo (ESTA-CAJA-SE-MUDO.txt) y esta caja vieja vuelve a\r\n"
        "funcionar igual que antes. Ojo: lo que se venda en la nueva despues de mudarse no\r\n"
        "esta aca; avisa a soporte antes de volver a vender en esta.\r\n"
    )


def _poner_marca(desde: str, raiz: str) -> None:
    with open(os.path.join(desde, MARCA_VIEJA), "w", encoding="utf-8-sig", newline="") as f:
        f.write(_texto_marca(raiz, _ahora().strftime("%d-%m-%Y a las %H:%M")))
        f.flush()
        os.fsync(f.fileno())


def _quitar_marca(desde: str) -> None:
    """La caja vieja vuelve a funcionar. Es lo ÚNICO que se borra de la carpeta vieja, y
    solo la marca que pusimos nosotros."""
    _borrar(os.path.join(desde, MARCA_VIEJA))


# ---------------------------------------------------------------------------
# La mudanza
# ---------------------------------------------------------------------------
class MudanzaEnCurso(Exception):
    """Otra petición está ejecutando, reintentando o descartando la mudanza."""


# UN solo bloqueo para toda operación sobre la mudanza (ejecutar, reintentar, descartar y
# lo que se haga con la base justo después). Reentrante: el hilo que lo tiene puede llamar
# a ejecutar/descartar sin trabarse; otro hilo, en la API, no entra (409).
_CERROJO = threading.RLock()


@contextlib.contextmanager
def operacion():
    """Para la API: toma el bloqueo sin esperar. Si está tomado, `MudanzaEnCurso`."""
    if not _CERROJO.acquire(blocking=False):
        raise MudanzaEnCurso("Hay una mudanza en curso. Espera a que termine.")
    try:
        yield
    finally:
        _CERROJO.release()


def ejecutar(raiz: str | None = None, base_nueva: str | None = None,
             puerto: int | None = None, mutex: str | None = None) -> dict | None:
    with _CERROJO:
        return _ejecutar(raiz, base_nueva, puerto, mutex)


def _ejecutar(raiz, base_nueva, puerto, mutex) -> dict | None:
    """Hace (o retoma) la mudanza pedida, si hay una. Nunca lanza: devuelve lo que pasó.

    None si no había nada que hacer. Si no, un dict con `estado`: «hecha» (con
    `completo` falso si faltó copiar algo auxiliar), «no_hecha» (la base nueva ya tenía
    datos propios) o «error» (queda pendiente para reintentar).
    `puerto`: el que debe estar libre (None = no revisarlo, porque ya estamos escuchando)."""
    raiz = raiz or RAIZ
    pedido = os.path.join(raiz, ARCHIVO_PEDIDO)
    if not os.path.isfile(pedido):
        return None
    log = _log()
    try:
        return _mudar(raiz, pedido, base_nueva, puerto, mutex)
    except MudanzaFallida as e:
        mensaje, tipo = str(e), e.tipo
    except Exception as e:                      # lo inesperado también se avisa claro
        log.exception("Mudanza: falló sin esperarlo")
        mensaje, tipo = f"No se pudo traer la caja anterior ({type(e).__name__}: {e}).", "otro"
    try:
        desde = _leer_texto(pedido).strip().strip('"')
    except OSError:
        desde = ""
    log.error("Mudanza pendiente: %s", mensaje)
    error = {"desde": desde, "mensaje": mensaje, "tipo": tipo,
             "fecha": _ahora().isoformat(timespec="seconds")}
    try:
        _escribir_json(os.path.join(raiz, ARCHIVO_ERROR), error)
    except OSError:
        pass
    return {"estado": "error", **error}


def _es_nuestra_copia(nueva: str, st: dict) -> bool:
    """¿La base de esta caja coincide con lo que importamos? Falso si no hay base ni huella."""
    if not os.path.exists(nueva) or not st.get("huella"):
        return False
    try:
        return _huella_de(nueva) == st["huella"]
    except sqlite3.Error:
        return False


def descartar(raiz: str | None = None, base_nueva: str | None = None) -> dict:
    with _CERROJO:
        return _descartar(raiz, base_nueva)


def _descartar(raiz, base_nueva) -> dict:
    """«Esta caja es nueva, no traer nada»: solo mientras la base no se haya instalado.
    Quita la marca que pusimos en la vieja (vuelve a funcionar) y abre la caja normal.

    Se rechaza ante la MENOR duda de que la base importada ya esté acá (aunque la fase
    «instalada» no haya alcanzado a guardarse): quitar la marca con la base importada
    dejaría dos cajas con el mismo historial. En ese caso solo sirve «Reintentar»."""
    raiz = raiz or RAIZ
    pedido = os.path.join(raiz, ARCHIVO_PEDIDO)
    st = _leer_estado(raiz)
    if not os.path.isfile(pedido):
        return {"ok": True, "nada": True}
    if st.get("fase") in FASES_INSTALADA:
        return {"ok": False, "detalle": "La base de la caja anterior ya se trajo; no se "
                                        "puede descartar. Reintenta la copia."}
    nueva = base_nueva or _ruta_base_nueva()
    if nueva and os.path.exists(nueva):
        duda = False
        try:
            if _es_nuestra_copia(nueva, st):
                duda = True
            elif st.get("marca_escrita") and any(_datos_de(nueva)):
                duda = True              # hay datos y no sabemos de quién son
        except Exception:
            duda = True                  # no se pudo comprobar: ante la duda, no
        if duda:
            return {"ok": False, "detalle": "La base de la caja anterior ya está en esta "
                                            "caja. No se puede descartar: toca Reintentar "
                                            "para terminar la mudanza."}
    desde = st.get("desde") or _leer_texto(pedido).strip().strip('"')
    if st.get("marca_escrita") and desde:
        _quitar_marca(desde)
    _borrar(pedido, os.path.join(raiz, ARCHIVO_ERROR), os.path.join(raiz, ARCHIVO_ESTADO))
    if _ruta_base_nueva():
        _quitar_temporal(_ruta_base_nueva() + ".mudando")
    _log().warning("Mudanza descartada por el dueño (desde %s)", desde)
    return {"ok": True}


def _mudar(raiz: str, pedido: str, base_nueva: str | None, puerto: int | None,
           mutex: str | None) -> dict:
    log = _log()
    desde = _leer_texto(pedido).strip().strip('"').strip()
    if not desde:
        raise MudanzaFallida("El instalador dejó el pedido de mudanza vacío.")
    if not os.path.isdir(desde):
        raise MudanzaFallida(f"No encuentro la carpeta de la caja anterior ({desde}). "
                             "¿Se movió o está en un disco que no está conectado?")
    if _mismo_lugar(desde, raiz):
        raise MudanzaFallida("La carpeta anterior es la misma de esta aplicación.")
    viejo_db = os.path.join(desde, "pos.db")
    if not os.path.isfile(viejo_db):
        raise MudanzaFallida(f"En {desde} no hay base de datos (pos.db). No se trajo nada.")
    if not os.path.isfile(os.path.join(desde, "apps", "pos", "mudanza.py")):
        raise MudanzaFallida(
            "La caja anterior todavía no está en la última versión. Primero abre la caja "
            "vieja y deja que se actualice a la última versión; después vuelve a correr "
            "este instalador (o a abrir esta caja).", "version")
    nueva = base_nueva or _ruta_base_nueva()
    if not nueva:
        raise MudanzaFallida("Esta caja no usa una base SQLite; no se puede traer la anterior.")
    os.makedirs(os.path.dirname(os.path.abspath(nueva)), exist_ok=True)

    st = _leer_estado(raiz)
    if st.get("desde") != desde:
        st = {}                                   # estado de otro pedido: no vale

    # Instalación CONFIRMADA (la fase quedó guardada): la caja ya pudo vender, así que la
    # base no se compara ni se toca. Solo se retoman los auxiliares y el cierre.
    if st.get("fase") in FASES_INSTALADA:
        return _finalizar(raiz, desde, nueva, st)

    # ¿La base nueva YA es nuestra copia (un corte justo después de reemplazarla, antes
    # de guardar la fase)? Solo en ese caso se comparan las huellas.
    if _es_nuestra_copia(nueva, st):
        st["fase"] = "instalada"
        _guardar_estado(raiz, st)
        return _finalizar(raiz, desde, nueva, st)

    # Datos propios: no se pisan jamás.
    if os.path.exists(nueva):
        try:
            ventas, usuarios = _datos_de(nueva)
        except sqlite3.Error as e:
            raise MudanzaFallida(f"No se pudo leer la base de esta caja ({e}); "
                                 "por eso no se tocó.")
        if ventas or usuarios:
            motivo = (f"Esta caja ya tiene datos propios ({ventas} ventas, {usuarios} usuarios). "
                      "No se trajo nada de la anterior para no pisarlos.")
            log.warning("Mudanza no hecha desde %s: %s", desde, motivo)
            if st.get("marca_escrita"):
                _quitar_marca(desde)
            datos = {"desde": desde, "fecha": _ahora().isoformat(timespec="seconds"),
                     "motivo": motivo, "aviso_visto": False}
            _escribir_json(os.path.join(raiz, ARCHIVO_NO_HECHA), datos)
            _borrar(pedido, os.path.join(raiz, ARCHIVO_ESTADO), os.path.join(raiz, ARCHIVO_ERROR))
            return {"estado": "no_hecha", **datos}

    marca = _ahora().strftime("%Y%m%d-%H%M%S")
    temporal = nueva + ".mudando"
    respaldo = os.path.join(raiz, "respaldos", f"antes-de-mudar-{marca}.db")
    marca_puesta = False
    # a) la caja vieja tiene que estar cerrada de verdad (y la tomamos mientras dura).
    with caja_vieja_cerrada(puerto, mutex):
        try:
            # b) la marca PRIMERO: desde acá la vieja ya no puede vender.
            if bloqueada(desde) and not st.get("marca_escrita"):
                raise MudanzaFallida("Esa carpeta ya se mudó a otra parte (tiene el aviso "
                                     f"{MARCA_VIEJA}). No se trajo nada.")
            if not bloqueada(desde):
                _poner_marca(desde, raiz)
            marca_puesta = True
            st = {"desde": desde, "marca_escrita": True, "fase": "marca",
                  "fecha": _ahora().isoformat(timespec="seconds")}
            _guardar_estado(raiz, st)
            _punto("marca")

            # c) el respaldo «antes-de-mudar», el temporal y la verificación completa.
            origen = _abrir_solo_lectura(viejo_db)
            try:
                try:
                    sano = origen.execute("PRAGMA integrity_check").fetchone()[0]
                except sqlite3.Error as e:
                    raise MudanzaFallida(f"La base de la caja anterior no se puede leer ({e}). "
                                         "No se trajo nada.")
                if sano != "ok":
                    raise MudanzaFallida("La base de la caja anterior tiene un daño "
                                         f"({sano}). No se trajo nada; hay que revisarla antes.")
                esperado = _huellas(origen)
                os.makedirs(os.path.dirname(respaldo), exist_ok=True)
                try:
                    _copiar_base(origen, respaldo)
                except (sqlite3.Error, OSError) as e:
                    raise MudanzaFallida(f"No se pudo sacar el respaldo previo ({e}). "
                                         "No se trajo nada.")
            finally:
                origen.close()
            _verificar(respaldo, esperado, "el respaldo previo")
            st.update(fase="respaldo", huella={t: [n, h] for t, (n, h) in esperado.items()},
                      respaldo_previo=respaldo)
            _guardar_estado(raiz, st)
            _punto("respaldo")

            origen = _abrir_solo_lectura(viejo_db)
            try:
                _copiar_base(origen, temporal)
            finally:
                origen.close()
            _verificar(temporal, esperado, "la base nueva")
            origen = _abrir_solo_lectura(viejo_db)
            try:
                if _huellas(origen) != esperado:
                    raise MudanzaFallida("La caja anterior siguió cambiando mientras se copiaba "
                                         "(¿quedó abierta?). Ciérrala y se vuelve a intentar.")
            finally:
                origen.close()
            st["fase"] = "verificada"
            _guardar_estado(raiz, st)
            _punto("verificada")
            # Última comprobación, ya dentro del bloqueo y justo antes de reemplazar: si la
            # base de esta caja recibió datos mientras se preparaba todo, no se pisa.
            if os.path.exists(nueva):
                try:
                    ventas, usuarios = _datos_de(nueva)
                except sqlite3.Error as e:
                    raise MudanzaFallida(f"No se pudo leer la base de esta caja ({e}); "
                                         "por eso no se tocó.")
                if ventas or usuarios:
                    raise MudanzaFallida(
                        "Esta caja recibió datos propios mientras se preparaba la mudanza "
                        f"({ventas} ventas, {usuarios} usuarios). No se pisó nada.")
        except Exception:
            # Nada se instaló todavía: la vieja vuelve a funcionar y se descarta el temporal.
            _quitar_temporal(temporal)
            if marca_puesta:
                _quitar_marca(desde)
            _borrar(os.path.join(raiz, ARCHIVO_ESTADO))
            raise

        # d) instalar la base. Una base vacía anterior se conserva aparte.
        try:
            if os.path.exists(nueva):
                c = sqlite3.connect(nueva, timeout=10)
                try:
                    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    c.close()
                os.replace(nueva, os.path.join(raiz, f"pos.db.vacia-antes-de-mudar-{marca}"))
            for sufijo in ("-wal", "-shm"):
                _borrar(nueva + sufijo)
            os.replace(temporal, nueva)
        except Exception:
            _quitar_temporal(temporal)
            if not os.path.exists(nueva):
                # No quedó ninguna base: la vieja vuelve a funcionar.
                _quitar_marca(desde)
                _borrar(os.path.join(raiz, ARCHIVO_ESTADO))
            raise
        st.update(fase="instalada", ventas=esperado.get("venta", (0,))[0],
                  usuarios=esperado.get("usuario", (0,))[0],
                  fecha=_ahora().isoformat(timespec="seconds"))
        _guardar_estado(raiz, st)
        _punto("instalada")
    return _finalizar(raiz, desde, nueva, st)


def _finalizar(raiz: str, desde: str, nueva: str, st: dict) -> dict:
    """La base ya es nuestra copia: se copia lo demás y, solo si todo está completo y
    verificado, se cierra la mudanza."""
    log = _log()
    pedido = os.path.join(raiz, ARCHIVO_PEDIDO)
    if not bloqueada(desde):                      # por si se la quitaron en medio
        _poner_marca(desde, raiz)
    copiado, faltan = _copiar_auxiliares(raiz, desde)
    st["aux_faltan"] = faltan
    st["copiado"] = copiado
    _guardar_estado(raiz, st)
    if faltan:
        mensaje = ("Se trajeron las ventas, pero no se pudo copiar: " + ", ".join(faltan) +
                   ". No borres la carpeta anterior todavía.")
        _escribir_json(os.path.join(raiz, ARCHIVO_ERROR),
                       {"desde": desde, "mensaje": mensaje, "tipo": "auxiliares",
                        "fecha": _ahora().isoformat(timespec="seconds")})
        log.warning("Mudanza incompleta desde %s: faltan %s", desde, faltan)
        return {"estado": "hecha", "completo": False, "desde": desde, "faltan": faltan,
                "ventas": st.get("ventas"), "usuarios": st.get("usuarios"), "mensaje": mensaje}
    st["fase"] = "auxiliares"
    _guardar_estado(raiz, st)
    _punto("auxiliares")
    hecho = {
        "desde": desde,
        "fecha": st.get("fecha") or _ahora().isoformat(timespec="seconds"),
        "ventas": st.get("ventas"),
        "usuarios": st.get("usuarios"),
        "filas_por_tabla": {t: n for t, (n, _) in (st.get("huella") or {}).items()},
        "respaldo_previo": st.get("respaldo_previo", ""),
        "copiado": copiado,
        "completo": True,
        "aviso_visto": False,
    }
    _escribir_json(os.path.join(raiz, ARCHIVO_HECHO), hecho)
    _borrar(pedido, os.path.join(raiz, ARCHIVO_ERROR))
    log.info("Mudanza hecha desde %s: %s ventas, %s usuarios", desde,
             hecho["ventas"], hecho["usuarios"])
    return {"estado": "hecha", **hecho}


# ---------------------------------------------------------------------------
# Las pantallas
# ---------------------------------------------------------------------------
PAGINA_MUDADA = """<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Esta caja se mudó</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F6F2EA;
       color:#2B2118;font-family:system-ui,"Segoe UI",sans-serif;padding:24px}
  main{max-width:560px;text-align:center}
  h1{font-size:30px;margin:0 0 14px}
  p{font-size:19px;line-height:1.5;margin:0 0 12px}
  small{display:block;margin-top:26px;font-size:14px;color:#6D5F52;line-height:1.5}
</style></head>
<body><main>
  <h1>Esta caja se mudó</h1>
  <p>Ahora se usa la aplicación <b>Gespoint</b>.<br>Ábrela desde el ícono del escritorio.</p>
  <p>Tus ventas, usuarios y ajustes ya están allá.</p>
  <small>Si la aplicación nueva no abre, borra el archivo
    <b>ESTA-CAJA-SE-MUDO.txt</b> de esta carpeta y esta caja vuelve a funcionar como antes.</small>
</main></body></html>"""

_TITULOS = {
    "vieja_abierta": "Cierra la caja vieja para terminar la mudanza",
    "version": "Primero hay que actualizar la caja vieja",
}

PAGINA_RECUPERACION = """<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Terminar la mudanza</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F6F2EA;
       color:#2B2118;font-family:system-ui,"Segoe UI",sans-serif;padding:24px}
  main{max-width:600px;text-align:center}
  h1{font-size:28px;margin:0 0 14px}
  p{font-size:18px;line-height:1.5;margin:0 0 12px}
  .motivo{background:#FBEAE3;color:#7A2E1B;border-radius:10px;padding:12px 16px;font-size:16px}
  button{font:inherit;font-size:18px;padding:12px 22px;border-radius:10px;border:1px solid #BBA;
         background:#fff;cursor:pointer;margin:8px}
  button.principal{background:#0E3A2D;color:#fff;border-color:#0E3A2D}
  small{display:block;margin-top:22px;font-size:14px;color:#6D5F52;line-height:1.5}
</style></head>
<body><main>
  <h1>__TITULO__</h1>
  <p>Esta caja está esperando traer las ventas de la caja anterior y todavía no se puede usar:
     así no se mezclan los datos.</p>
  <p class="motivo">__MOTIVO__</p>
  <p id="msj"></p>
  <button class="principal" id="reintentar">Reintentar</button>
  <button id="nueva">Esta caja es nueva, no traer nada</button>
  <small>Ayuda → si la caja anterior seguía abierta, ciérrala antes de reintentar.</small>
</main>
<script>
async function enviar(ruta, cuerpo){
  const r = await fetch(ruta, {method:"POST", headers:{"Content-Type":"application/json"},
                               body: JSON.stringify(cuerpo||{})});
  return r.json().catch(() => ({}));
}
document.getElementById("reintentar").onclick = async () => {
  document.getElementById("msj").textContent = "Reintentando…";
  await enviar("/api/v1/mudanza/reintentar");
  location.reload();
};
document.getElementById("nueva").onclick = async () => {
  if (!confirm("¿Seguro? No se traerá nada de la caja anterior y esta caja empezará de cero. " +
               "La caja anterior seguirá como estaba.")) return;
  const d = await enviar("/api/v1/mudanza/descartar", {confirmar: true});
  if (d.ok) location.href = "/"; else document.getElementById("msj").textContent = d.detail || "No se pudo.";
};
</script></body></html>"""


def pagina_recuperacion(raiz: str | None = None) -> str:
    from html import escape
    e = estado(raiz)
    titulo = _TITULOS.get(e.get("tipo", ""), "No se pudo traer la caja anterior")
    motivo = e.get("mensaje") or "La mudanza todavía no se hizo. Toca Reintentar."
    return (PAGINA_RECUPERACION.replace("__TITULO__", escape(titulo))
            .replace("__MOTIVO__", escape(motivo)))
