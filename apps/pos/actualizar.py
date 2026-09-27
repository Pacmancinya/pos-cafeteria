"""Sistema de actualizaciones.

Copiado del que ya funciona en la Biblioteca Láser, con las lecciones que
quedaron escritas en su `CONTEXTO-para-otro-agente.md`:

  · **Un archivo NUEVO tiene que llegar.** Allá el actualizador tomaba solo los
    archivos de la raíz del paquete, y un módulo nuevo nunca llegaba. Acá se
    copia el árbol completo (`apps/pos/api/...` incluido), porque este proyecto
    vive en subcarpetas.
  · **Nunca tocar los datos.** `pos.db`, `respaldos/` y `.venv/` quedan intactos:
    lo que se reemplaza es solo el código.
  · **Guardar la versión anterior** antes de pisar nada, por si hay que volver.
  · Los mensajes son para el dueño del local, no para un programador.

## Desde la 2.19: firmado, por canal y con vuelta atrás

  · **Cada paquete viene firmado.** Trae `manifiesto.json` con la huella de cada
    archivo que se instala y `manifiesto.firma`, hecha con una llave que NO está
    en el repositorio (ver `tools/firmar_version.py`). Antes, si la cuenta de
    GitHub caía, cada local instalaba lo que el atacante quisiera. Ahora un
    paquete sin firma, con otra firma, o con UN archivo distinto del firmado, no
    se instala: se revisa todo ANTES de escribir nada.
  · **Dos canales.** `estable` (version.json) y `piloto` (version-piloto.json):
    una versión nueva va primero a un local de confianza y días después al
    resto. La 2.12 tumbó El día en todos los locales el mismo día.
  · **Vuelta atrás.** `_version_anterior/` guarda SOLO lo que pisó la última
    actualización, con la lista en `_cambios.json`, y el dueño puede volver con
    un botón. Antes se iban acumulando copias de varias versiones, y volver con
    eso habría mezclado versiones.
  · **Nunca a medias.** Los originales se guardan y la lista se anota ANTES de
    reemplazar el primer archivo. Si algo falla se vuelve atrás al tiro, y si
    se corta la luz, al abrir (ver vuelta.py).

Después de actualizar hay que reiniciar el programa. Si se abrió con Kofe.exe o
con INICIAR-POS.bat, se reinicia solo.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import urllib.request
import zipfile

from apps.pos import firma, vuelta
from core.config import APP_NOMBRE, APP_VERSION, RAIZ, URL_VERSION

# Nunca se reemplazan: son del local, no del programa.
PROTEGIDOS = {"pos.db", "pos.db-wal", "pos.db-shm", ".env",
              # La llave que firma las sesiones es de ESTA caja: si se
              # reemplazara, todos tendrían que marcar su PIN de nuevo.
              ".secreto"}
CARPETAS_PROTEGIDAS = ("respaldos", "registros", ".venv", "__pycache__", ".git",
                       "despliegue",
                       # datos de la ventana (sesión del navegador incrustado)
                       "datos-ventana", "_internal",
                       # la copia de la versión anterior no se pisa con un paquete
                       "_version_anterior")
EXTENSIONES = (".py", ".html", ".css", ".js", ".bat", ".md", ".txt", ".json")

RESPALDO = vuelta.RESPALDO
CAMBIOS = vuelta.CAMBIOS
MANIFIESTO = "manifiesto.json"
FIRMA_ARCHIVO = "manifiesto.firma"

# Un paquete de verdad pesa menos de 1 MB y trae unos cien archivos. Los topes
# son holgados a propósito: están para que un paquete hecho para reventar la
# memoria se rechace ANTES de abrirlo, sin llave ni firma de por medio (lo
# encontró la revisión de Codex), no para ajustar al byte.
TOPE_DESCARGA = 60 * 1024 * 1024
TOPE_EXPANDIDO = 200 * 1024 * 1024
TOPE_ARCHIVOS = 5000
TOPE_AVISO = 1024 * 1024            # version.json

# La llave pública con que se firman las versiones. La privada vive en el
# computador de quien publica (%USERPROFILE%\.kofe\llave-firma.txt), nunca acá.
# Es una tupla para poder cambiar de llave algún día: se publica una versión
# que conoce la nueva y la vieja, y recién después se firma con la nueva.
LLAVES_PUBLICAS = ("68f01ffe9ebc9e29434dfd3f30daeb13cb6ab3f9582913cb94df76e6c8dd10dd",)


def _tupla(v: str) -> tuple:
    """'2.10' es MAYOR que '2.9': hay que comparar por número, no por texto."""
    partes = []
    for t in str(v).split("."):
        try:
            partes.append(int(t))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def se_instala(rel: str) -> bool:
    """¿Este archivo del paquete es del programa? La misma regla la usa quien
    firma (tools/firmar_version.py): si fueran dos reglas, un día no calzarían."""
    partes = rel.split("/")
    if not rel or partes[0] in CARPETAS_PROTEGIDAS or partes[-1] in PROTEGIDOS:
        return False
    if any(p.startswith(".") for p in partes):
        return False
    return rel.lower().endswith(EXTENSIONES)


# ---------------------------------------------------------------------------
# Descargar
# ---------------------------------------------------------------------------
_GITHUB = {"github.com", "raw.githubusercontent.com", "api.github.com"}


def _por_la_api(url: str) -> str:
    """Con un repositorio privado, el zip de una etiqueta no se baja por
    github.com con una clave: se baja por la API, que sí la acepta."""
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+)/archive/(refs/(?:tags|heads)/[^/]+)\.zip$", url)
    if not m:
        return url
    return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/zipball/{m.group(3)}"


def _pedir(url: str, espera: int, tope: int | None = None) -> bytes:
    """Si el repositorio es privado, cada local trae su clave de descarga en
    POS_CLAVE_DESCARGA: una por local, para poder revocar la de uno sin tocar a
    los demás. Sin clave, se baja como siempre, de un repositorio público."""
    cabeceras = {"User-Agent": "PuntoDeVenta"}
    clave = os.getenv("POS_CLAVE_DESCARGA", "").strip()
    host = (url.split("/")[2] if url.count("/") >= 2 else "").lower()
    if clave and host in _GITHUB:
        cabeceras["Authorization"] = f"token {clave}"
        url = _por_la_api(url)
    req = urllib.request.Request(url, headers=cabeceras)
    tope = TOPE_DESCARGA if tope is None else tope
    with urllib.request.urlopen(req, timeout=espera) as r:
        datos = r.read(tope + 1)
    if len(datos) > tope:
        raise ValueError("pesa más de lo que pesa una actualización de verdad")
    return datos


def url_del_canal(canal: str) -> str:
    if canal == "piloto":
        return (os.getenv("POS_URL_VERSION_PILOTO")
                or URL_VERSION.replace("version.json", "version-piloto.json"))
    return URL_VERSION


def revisar() -> dict:
    """¿Hay una versión nueva publicada en el canal de este local?"""
    try:
        from apps.pos import local
        canal = local.canal()
    except Exception:
        canal = "estable"
    url = url_del_canal(canal)
    if not url:
        return {"error": "Todavía no hay un canal de actualizaciones configurado."}
    try:
        info = json.loads(_pedir(url, 8, TOPE_AVISO).decode("utf-8"))
    except Exception as e:
        return {"error": "No pude conectarme para revisar. ¿Hay internet?", "detalle": str(e)}

    nueva = str(info.get("version", "0"))
    return {
        "ok": True,
        "canal": canal,
        "actual": APP_VERSION,
        "actual_nombre": APP_NOMBRE,
        "disponible": nueva,
        "disponible_nombre": info.get("nombre", ""),
        "hay_nueva": _tupla(nueva) > _tupla(APP_VERSION),
        "novedades": info.get("novedades", ""),
        "zip": info.get("zip", ""),
    }


def _ruta_segura(rel: str) -> str | None:
    """Evita que un ZIP con '../' escriba fuera de la carpeta del programa."""
    return vuelta.ruta_segura(RAIZ, rel)


# Solo https: sin cifrar, cualquiera en la red del local podría meter código
# propio en la caja. La excepción es el mismo computador, que se usa para probar
# una actualización antes de publicarla (quien pueda servir ahí ya tiene la máquina).
def _origen_confiable(url: str) -> bool:
    if url.startswith("https://"):
        return True
    return url.startswith(("http://127.0.0.1", "http://localhost"))


# ---------------------------------------------------------------------------
# Revisar la firma: TODO antes de escribir nada
# ---------------------------------------------------------------------------
def _problema_de_firma(contenido: dict, manifiesto: bytes | None, firma_hex: str | None,
                       version_esperada: str | None) -> str | None:
    if manifiesto is None or not firma_hex:
        return ("Este paquete no viene firmado por Caja Clara, así que no se instala. "
                "Tu caja quedó como estaba.")
    try:
        sello = bytes.fromhex(firma_hex)
    except ValueError:
        return "La firma del paquete está rota. No se instala nada."
    if not any(firma.verificar(bytes.fromhex(k), manifiesto, sello) for k in LLAVES_PUBLICAS):
        return ("La firma del paquete no es la de Caja Clara. No se instala nada: puede ser "
                "un paquete adulterado. Avísale a soporte.")
    try:
        datos = json.loads(manifiesto.decode("utf-8"))
        version = str(datos["version"])
        huellas = dict(datos["archivos"])
    except (ValueError, KeyError, TypeError):
        return "El manifiesto del paquete está roto. No se instala nada."
    if version_esperada and version != str(version_esperada):
        return (f"El paquete dice ser la v{version} y se esperaba la v{version_esperada}. "
                "No se instala nada.")
    if _tupla(version) <= _tupla(APP_VERSION):
        return (f"El paquete es de la v{version}, que no es más nueva que la tuya "
                f"(v{APP_VERSION}). No se instala.")
    for rel, datos_archivo in contenido.items():
        esperada = huellas.get(rel)
        if esperada is None:
            return f"El paquete trae un archivo que no se firmó ({rel}). No se instala nada."
        if hashlib.sha256(datos_archivo).hexdigest() != esperada:
            return f"Un archivo del paquete no es el que se firmó ({rel}). No se instala nada."
    faltan = [r for r in huellas if r not in contenido]
    if faltan:
        return f"Al paquete le faltan archivos firmados ({faltan[0]}). No se instala nada."
    return None


def aplicar(url_zip: str, version_esperada: str | None = None) -> dict:
    """Descarga el paquete, revisa la firma y reemplaza SOLO el código."""
    if not _origen_confiable(url_zip):
        return {"error": "La dirección de descarga no es segura (tiene que ser https)."}
    try:
        crudo = _pedir(url_zip, 120)
    except Exception as e:
        return {"error": f"No se pudo descargar la actualización: {e}"}

    contenido: dict[str, bytes] = {}
    manifiesto = None
    firma_hex = None
    try:
        with zipfile.ZipFile(io.BytesIO(crudo)) as z:
            infos = [i for i in z.infolist() if not i.filename.endswith("/")]
            if not infos:
                return {"error": "El paquete descargado venía vacío."}
            if len(infos) > TOPE_ARCHIVOS:
                return {"error": "El paquete trae demasiados archivos para ser una "
                                 "actualización. No se instala nada."}
            # Los ZIP traen todo colgando de una carpeta ("pos-cafeteria-2.19/"
            # si viene de GitHub). Se la sacamos.
            primeras = {i.filename.split("/")[0] for i in infos if "/" in i.filename}
            prefijo = (primeras.pop() + "/") if len(primeras) == 1 else ""
            a_leer = []
            for i in infos:
                n = i.filename
                rel = n[len(prefijo):] if prefijo and n.startswith(prefijo) else n
                if rel in (MANIFIESTO, FIRMA_ARCHIVO) or (se_instala(rel) and _ruta_segura(rel)):
                    a_leer.append((i, rel))
            # Cuánto dice pesar lo que se va a leer, ANTES de leerlo. zipfile
            # nunca entrega más de lo que el paquete declara para cada archivo,
            # así que el tope vale aunque el paquete mienta.
            if sum(i.file_size for i, _ in a_leer) > TOPE_EXPANDIDO:
                return {"error": "El paquete es demasiado grande para ser una "
                                 "actualización. No se instala nada."}
            for i, rel in a_leer:
                if rel == MANIFIESTO:
                    manifiesto = z.read(i)
                elif rel == FIRMA_ARCHIVO:
                    firma_hex = z.read(i).decode("ascii", "replace").strip()
                else:
                    contenido[rel] = z.read(i)
    except zipfile.BadZipFile:
        return {"error": "El archivo descargado no es un paquete válido."}
    except Exception as e:
        return {"error": f"No se pudo leer la actualización: {e}"}

    problema = _problema_de_firma(contenido, manifiesto, firma_hex, version_esperada)
    if problema:
        return {"error": problema}
    version = str(json.loads(manifiesto.decode("utf-8"))["version"])
    return _instalar(contenido, version)


def _instalar(contenido: dict, version: str) -> dict:
    """Reemplaza el código en tres pasos, y el orden es lo que importa:

      1. mirar qué cambia, sin tocar nada;
      2. guardar los originales y anotar la lista, marcada «a medias»;
      3. recién ahí reemplazar, y al terminar marcar la lista como completa.

    Si algo falla en el paso 3, se vuelve atrás al tiro. Si se corta la luz, la
    lista quedó «a medias» y la caja se vuelve atrás sola al abrir (vuelta.py).
    Antes la lista se escribía al final: un corte a mitad de camino dejaba
    código de dos versiones y ninguna forma de volver (lo encontró la revisión
    de Codex).
    """
    respaldo = os.path.join(RAIZ, RESPALDO)
    previo = _cambios()
    a_medias = bool(previo) and previo.get("completo", True) is False

    # 1. Qué cambia. Solo mirar.
    plan = []
    for rel, datos in sorted(contenido.items()):
        destino = _ruta_segura(rel)
        existe = os.path.exists(destino)
        if existe:
            with open(destino, "rb") as f:
                if f.read() == datos:
                    continue                      # ya está igual
        plan.append((rel, destino, datos, existe))
    if not plan:
        # Nada que hacer, y la vuelta atrás de la actualización anterior se
        # conserva: reinstalar lo mismo no puede costar el poder volver.
        if a_medias:
            vuelta.anotar(RAIZ, dict(previo, hacia=version, completo=True))
        return {"ok": True, "archivos": [], "sin_cambios": True,
                "aviso": "Ya tenías todos los archivos al día."}

    # 2. Los originales a salvo y la lista anotada, ANTES del primer reemplazo.
    if a_medias:
        # Un intento anterior quedó a medias y no se pudo deshacer. Lo que ya
        # instaló ahora está «igual» y se saltaría, pero su original sigue en la
        # carpeta: se conserva, y se suma lo nuevo. Empezar de cero perdería
        # esos originales.
        desde = previo.get("desde", APP_VERSION)
        cambiados = list(previo.get("cambiados", []))
        nuevos = list(previo.get("nuevos", []))
    else:
        # La carpeta guarda SOLO lo que pisa esta actualización: si se
        # acumularan copias de varias, volver atrás mezclaría versiones.
        shutil.rmtree(respaldo, ignore_errors=True)
        desde, cambiados, nuevos = APP_VERSION, [], []
    originales = dict(previo.get("originales") or {}) if a_medias else {}
    try:
        for rel, destino, _, existe in plan:
            if rel in cambiados or rel in nuevos:
                continue                          # su original ya está a salvo
            if existe:
                with open(destino, "rb") as f:
                    original = f.read()
                copia = os.path.join(respaldo, rel)
                os.makedirs(os.path.dirname(copia), exist_ok=True)
                # A disco de verdad y con su huella, ANTES del primer reemplazo:
                # la vuelta atrás revisa cada copia antes de ponerla. Una copia
                # que el corte de luz dejó a medias dejaría la caja sin arrancar
                # (lo encontró la revisión de Codex).
                vuelta.escribir(copia, original)
                originales[rel] = hashlib.sha256(original).hexdigest()
                cambiados.append(rel)
            else:
                nuevos.append(rel)
        vuelta.anotar(RAIZ, {"desde": desde, "hacia": version, "cambiados": cambiados,
                             "nuevos": nuevos, "originales": originales, "completo": False})
    except Exception as e:
        return {"error": f"No se pudo preparar la actualización (¿queda espacio en el "
                         f"disco?): {e}. No se cambió nada."}

    # 3. Recién ahora se reemplaza, cada archivo con un temporal que se renombra:
    #    un archivo nunca queda escrito a medias.
    hechos: list[str] = []
    try:
        for rel, destino, datos, _ in plan:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            temporal = destino + vuelta.TEMPORAL
            try:
                vuelta.escribir(temporal, datos)
                os.replace(temporal, destino)
            except Exception:
                try:
                    os.remove(temporal)
                except OSError:
                    pass
                raise
            hechos.append(rel)
    except Exception as e:
        # A mitad de camino la caja tendría código de dos versiones: se vuelve
        # atrás al tiro, con los originales del paso 2.
        if vuelta.volver(RAIZ).get("ok"):
            return {"error": f"No se pudo instalar la actualización: {e}. "
                             "Se dejó todo como estaba.", "archivos": []}
        return {"error": f"No se pudo instalar la actualización: {e}. Tampoco se pudo "
                         "volver atrás todavía: cierra el programa y ábrelo de nuevo, "
                         "que al abrir lo intenta otra vez.", "archivos": hechos}
    try:
        vuelta.anotar(RAIZ, {"desde": desde, "hacia": version, "cambiados": cambiados,
                             "nuevos": nuevos, "originales": originales, "completo": True})
    except Exception as e:
        return {"error": f"Se instaló, pero no se pudo anotar la instalación ({e}). Al "
                         f"reiniciar, la caja vuelve a la v{desde}: libera espacio en el "
                         "disco y actualiza de nuevo.", "archivos": hechos}
    return {
        "ok": True,
        "archivos": hechos,
        "aviso": "Listo. Hay que reiniciar el programa para usar la versión nueva.",
    }


# ---------------------------------------------------------------------------
# Volver a la versión anterior
# ---------------------------------------------------------------------------
def _cambios() -> dict | None:
    return vuelta.leer(RAIZ)


def hay_vuelta() -> dict:
    datos = _cambios()
    if not datos:
        return {"disponible": False}
    return {"disponible": True, "version": datos.get("desde", ""),
            "desde_la": datos.get("hacia", "")}


def volver_atras() -> dict:
    r = vuelta.volver(RAIZ)
    if r.get("ok"):
        r["aviso"] = f"Listo. La caja vuelve a la v{r.get('version', '')} al reiniciarse."
    return r
