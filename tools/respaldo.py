"""Respaldo de la base.

Un local que vende todos los días no puede tener su historial en un solo archivo
de un solo computador. Esto saca una copia en tres momentos naturales:

  · al abrir el programa en la mañana,
  · al cerrar la caja en la noche,
  · cuando alguien aprieta el botón.

Usa la API de respaldo de SQLite (`Connection.backup`), no una copia del archivo:
copiar el .db mientras está en uso puede dejar una copia corrupta justo cuando
más se necesita.

## La copia de afuera (desde la 2.19)

Hasta la 2.18 las 30 copias vivían en la carpeta del programa. Si el disco se
moría o se robaban el computador, se perdían las ventas CON sus respaldos. Ahora,
si el dueño eligió una carpeta de afuera en Ayuda → Ajustes —una que se
sincroniza con la nube, o un pendrive—, cada respaldo se copia también ahí, y
la copia se ABRE y se revisa entera antes de darla por buena. Un respaldo que
nadie probó abrir es una esperanza, no un respaldo.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import sqlite3
from datetime import datetime

from core.config import DB_URL, RAIZ, ZONA

CARPETA = os.getenv("POS_CARPETA_RESPALDOS") or os.path.join(RAIZ, "respaldos")
CUANTOS_GUARDAR = 30
SUBCARPETA_AFUERA = "Kofe-respaldos"


def ruta_de_la_base() -> str | None:
    """El archivo .db, o None si la base no es SQLite (ej. Postgres)."""
    if not DB_URL.startswith("sqlite"):
        return None
    return DB_URL.split("///", 1)[-1]


# ---------------------------------------------------------------------------
# Lo que el dueño eligió, leído directo de la base: esto también corre suelto,
# desde la línea de comandos, sin levantar el servidor.
# ---------------------------------------------------------------------------
def _ajuste(clave: str) -> str:
    base = ruta_de_la_base()
    if not base or not os.path.exists(base):
        return ""
    try:
        c = sqlite3.connect(base, timeout=10)
        try:
            fila = c.execute("SELECT valor FROM ajuste WHERE clave = ?", (clave,)).fetchone()
        finally:
            c.close()
        return (fila[0] if fila else "") or ""
    except sqlite3.Error:
        return ""


def _guardar_ajuste(clave: str, valor: str) -> None:
    base = ruta_de_la_base()
    if not base:
        return
    try:
        c = sqlite3.connect(base, timeout=10)
        try:
            c.execute("INSERT OR REPLACE INTO ajuste (clave, valor) VALUES (?, ?)", (clave, valor))
            c.commit()
        finally:
            c.close()
    except sqlite3.Error:
        pass


# ---------------------------------------------------------------------------
# Respaldar
# ---------------------------------------------------------------------------
def respaldar(motivo: str = "manual") -> dict:
    origen = ruta_de_la_base()
    if not origen:
        return {"ok": False, "detalle": "La base no es SQLite; el respaldo lo maneja el servidor."}
    if not os.path.exists(origen):
        return {"ok": False, "detalle": "Todavía no hay base que respaldar."}

    os.makedirs(CARPETA, exist_ok=True)
    # La identidad va ANTES de copiar: así hasta el primer respaldo dice de qué
    # caja es, y restaurar.py puede negarse a ponerlo encima de otra. Se creaba
    # al copiar afuera, después del respaldo, y el primero salía sin ella (lo
    # encontró la revisión de Codex).
    _identidad()
    hoy = datetime.now(ZONA).strftime("%Y-%m-%d")
    destino = os.path.join(CARPETA, f"pos-{hoy}.db")

    src = sqlite3.connect(origen)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)          # copia consistente aunque la caja esté vendiendo
        # La base trabaja en modo WAL, y la copia hereda ese modo: al abrirla
        # dejaría archivos -wal y -shm al lado. Un respaldo tiene que ser UN
        # archivo, que se pueda copiar y abrir solo.
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst.close()
        src.close()

    borrados = _podar(CARPETA)
    return {
        "ok": True,
        "archivo": os.path.basename(destino),
        "carpeta": CARPETA,
        "tamano_kb": round(os.path.getsize(destino) / 1024),
        "motivo": motivo,
        "borrados": borrados,
        "afuera": copiar_afuera(destino),
    }


def _identidad() -> str:
    """Ocho letras al azar que distinguen a ESTA caja, anotadas en su base.

    Dos locales pueden llamarse igual —dos sucursales de la misma cadena— y
    compartir la carpeta de afuera. Con solo el nombre, el respaldo de uno
    pisaba el del otro y los dos mostraban «copia revisada» (lo encontró la
    revisión de Codex). Va en la base y no en un archivo suelto: si se restaura
    un respaldo en un computador nuevo, sigue siendo el mismo local."""
    ident = _ajuste("instalacion_id")
    if re.fullmatch(r"[0-9a-f]{8}", ident):
        return ident
    _guardar_ajuste("instalacion_id", secrets.token_hex(4))
    ident = _ajuste("instalacion_id")
    return ident if re.fullmatch(r"[0-9a-f]{8}", ident) else ""


def _nombre_de_carpeta() -> str:
    """Una subcarpeta por local: un dueño con dos locales puede usar el mismo
    Google Drive, y los respaldos de uno no pueden pisar los del otro. El nombre
    es para que el dueño la reconozca; la identidad, para que no choquen."""
    nombre = _ajuste("local_nombre") or os.getenv("POS_LOCAL", "") or "caja"
    limpio = re.sub(r"[^A-Za-z0-9 _-]+", "", nombre).strip() or "caja"
    ident = _identidad()
    return f"{limpio} {ident}" if ident else limpio


def copiar_afuera(archivo: str) -> dict:
    carpeta = _ajuste("respaldo_afuera").strip()
    if not carpeta:
        return {"configurado": False}
    estado = {"configurado": True, "carpeta": carpeta,
              "cuando": datetime.now(ZONA).isoformat(timespec="minutes")}
    try:
        destino = os.path.join(carpeta, SUBCARPETA_AFUERA, _nombre_de_carpeta())
        os.makedirs(destino, exist_ok=True)
        copia = os.path.join(destino, os.path.basename(archivo))
        # Se copia a un archivo aparte, se revisa entero, y recién ahí reemplaza
        # a la copia del mismo día. Si el pendrive se desconecta a la mitad, lo
        # que queda roto es el aparte y no la copia buena de antes, que el primer
        # día puede ser la única fuera del computador (lo encontró la revisión
        # de Codex).
        parcial = copia + ".kofe-parcial"
        try:
            shutil.copy2(archivo, parcial)     # el respaldo local ya está cerrado y entero
            c = sqlite3.connect(f"file:{parcial}?mode=ro", uri=True)
            try:
                sano = c.execute("PRAGMA integrity_check").fetchone()[0]
                ventas = c.execute("SELECT COUNT(*) FROM venta").fetchone()[0]
            finally:
                c.close()
            if sano == "ok":
                os.replace(parcial, copia)
        finally:
            for resto in (parcial, parcial + "-wal", parcial + "-shm", parcial + "-journal"):
                if os.path.exists(resto):
                    os.remove(resto)
        estado.update(ok=sano == "ok", ventas=ventas, archivo=os.path.basename(copia),
                      detalle="" if sano == "ok" else "La copia salió dañada: " + str(sano))
        _podar(destino)
    except Exception as e:
        estado.update(ok=False, detalle=f"No se pudo copiar a {carpeta}: {e}")
    _guardar_ajuste("respaldo_afuera_estado", json.dumps(estado, ensure_ascii=False))
    return estado


def estado_afuera() -> dict:
    """Cómo salió la última copia de afuera, para mostrárselo al dueño."""
    carpeta = _ajuste("respaldo_afuera")
    try:
        estado = json.loads(_ajuste("respaldo_afuera_estado") or "{}")
    except ValueError:
        estado = {}
    # El resultado es de la carpeta en que se hizo. Si el dueño eligió otra, lo
    # de antes no dice nada de la nueva: mostrarlo haría creer que ya tiene una
    # copia revisada ahí (lo encontró la revisión de Codex).
    if (estado.get("carpeta") or "").strip() != carpeta.strip():
        estado = {}
    estado["carpeta"] = carpeta
    return estado


def _podar(carpeta: str) -> int:
    """Deja solo los últimos respaldos: si no, la carpeta crece para siempre."""
    copias = sorted(
        (f for f in os.listdir(carpeta) if f.startswith("pos-") and f.endswith(".db")),
        reverse=True,
    )
    borrados = 0
    for viejo in copias[CUANTOS_GUARDAR:]:
        try:
            os.remove(os.path.join(carpeta, viejo))
            borrados += 1
        except OSError:
            pass
    return borrados


def listar() -> list[dict]:
    if not os.path.isdir(CARPETA):
        return []
    salida = []
    for f in sorted(os.listdir(CARPETA), reverse=True):
        if not (f.startswith("pos-") and f.endswith(".db")):
            continue
        ruta = os.path.join(CARPETA, f)
        salida.append({
            "archivo": f,
            "tamano_kb": round(os.path.getsize(ruta) / 1024),
            "fecha": f[4:-3],
        })
    return salida


# ---------------------------------------------------------------------------
# Dónde conviene dejar la copia de afuera
# ---------------------------------------------------------------------------
def lugares_sugeridos() -> list[dict]:
    """Carpetas que se sincronizan solas con la nube y pendrives conectados.
    Solo sugerencias: el dueño puede escribir cualquier carpeta."""
    vistos, salida = set(), []

    def sumar(nombre: str, ruta: str) -> None:
        if ruta and os.path.isdir(ruta) and os.path.normcase(ruta) not in vistos:
            vistos.add(os.path.normcase(ruta))
            salida.append({"nombre": nombre, "ruta": ruta})

    for variable, nombre in (("OneDrive", "OneDrive"), ("OneDriveConsumer", "OneDrive"),
                             ("OneDriveCommercial", "OneDrive (trabajo)")):
        sumar(nombre, os.getenv(variable, ""))
    casa = os.path.expanduser("~")
    sumar("Dropbox", os.path.join(casa, "Dropbox"))
    sumar("Google Drive", os.path.join(casa, "Google Drive"))
    if os.name == "nt":
        import string
        try:
            import ctypes
            mascara = ctypes.windll.kernel32.GetLogicalDrives()
            for i, letra in enumerate(string.ascii_uppercase):
                if not mascara & (1 << i):
                    continue
                raiz = f"{letra}:\\"
                # Google Drive para escritorio monta una unidad con "Mi unidad" adentro.
                for sub in ("Mi unidad", "My Drive"):
                    sumar("Google Drive", os.path.join(raiz, sub))
                if ctypes.windll.kernel32.GetDriveTypeW(raiz) == 2:      # extraíble
                    sumar(f"Pendrive ({letra}:)", raiz)
        except Exception:
            pass
    return salida


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = respaldar("manual")
    print(f"  {r}")
