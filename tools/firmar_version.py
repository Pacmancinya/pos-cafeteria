"""Firma una versión antes de publicarla. Lo corre QUIEN PUBLICA, en su computador.

    .venv/Scripts/python tools/firmar_version.py

Lee lo que está COMMITEADO (HEAD), no la carpeta. En Windows git guarda los
archivos con saltos de línea LF y los deja en la carpeta con CRLF, y GitHub
empaqueta lo commiteado: si se firmara la carpeta, ninguna huella calzaría y
ninguna caja aceptaría la actualización.

Escribe `manifiesto.json` (la versión y la huella de cada archivo que se
instala) y `manifiesto.firma`. Después se commitean esos dos, se pone la
etiqueta de la versión y se sube todo: ver docs/PUBLICAR-ACTUALIZACIONES.md.

La llave privada NO está en el repositorio. Vive en
%USERPROFILE%\\.kofe\\llave-firma.txt (o donde diga KOFE_LLAVE_FIRMA). Si se
pierde, las cajas instaladas no aceptan más actualizaciones hasta que alguien
les cambie la llave a mano. Guarda una copia en un gestor de contraseñas.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from apps.pos import firma  # noqa: E402
from apps.pos.actualizar import (FIRMA_ARCHIVO, LLAVES_PUBLICAS,  # noqa: E402
                                 MANIFIESTO, se_instala)
from core.config import APP_VERSION  # noqa: E402


def ruta_de_la_llave() -> str:
    return (os.getenv("KOFE_LLAVE_FIRMA")
            or os.path.join(os.path.expanduser("~"), ".kofe", "llave-firma.txt"))


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, check=True).stdout


def archivos_commiteados() -> dict[str, bytes]:
    """Cada archivo que la caja instalaría, tal como está en HEAD."""
    salida: dict[str, bytes] = {}
    for crudo in _git("ls-files", "-z").split(b"\0"):
        if not crudo:
            continue
        rel = crudo.decode("utf-8")
        if rel in (MANIFIESTO, FIRMA_ARCHIVO) or not se_instala(rel):
            continue
        salida[rel] = _git("show", f"HEAD:{rel}")
    return salida


def manifiesto_de(archivos: dict[str, bytes], version: str) -> bytes:
    cuerpo = {"version": version,
              "archivos": {rel: hashlib.sha256(datos).hexdigest()
                           for rel, datos in sorted(archivos.items())}}
    return json.dumps(cuerpo, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8") + b"\n"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ruta = ruta_de_la_llave()
    try:
        with open(ruta, encoding="utf-8") as f:
            secreto = bytes.fromhex(f.read().strip())
    except (OSError, ValueError):
        print(f"  No encontré la llave de firma en {ruta}.")
        return 1
    publica = firma.publica_de(secreto).hex()
    if publica not in LLAVES_PUBLICAS:
        print("  Esa llave no es la que conocen las cajas (LLAVES_PUBLICAS en apps/pos/actualizar.py).")
        return 1

    sucios = [linea[3:] for linea in _git("status", "--porcelain").decode("utf-8").splitlines()
              if se_instala(linea[3:].strip('"')) and linea[3:] not in (MANIFIESTO, FIRMA_ARCHIVO)]
    if sucios:
        print("  Hay cambios sin commitear que NO quedarían firmados:")
        for s in sucios[:10]:
            print("    " + s)
        print("  Commitea primero y vuelve a correr esto.")
        return 1

    # El guardian existe para no firmar una version que no se anuncio en ningun lado.
    # Anunciarla en el canal PILOTO alcanza: el proceso dice que una version nueva va
    # primero ahi y se copia al estable cuando lleva unos dias andando (docs/PUBLICAR-
    # ACTUALIZACIONES.md). Exigir version.json obligaba a publicarle a TODOS los locales
    # el mismo dia, que es justo lo que la 2.12 dejo como leccion.
    canales = {}
    for archivo in ("version.json", "version-piloto.json"):
        with open(os.path.join(RAIZ, archivo), encoding="utf-8") as f:
            canales[archivo] = json.load(f).get("version")
    if APP_VERSION not in canales.values():
        dichos = ", ".join(f"{a} dice {v}" for a, v in canales.items())
        print(f"  core/config.py dice {APP_VERSION} y ningun canal la anuncia ({dichos}).")
        print("  Pon la version en version-piloto.json (o en version.json) y vuelve a correr esto.")
        return 1
    if canales["version.json"] != APP_VERSION:
        print(f"  Se firma para el canal PILOTO: el estable sigue en {canales['version.json']}.")
        print("  Cuando lleve unos dias andando, copia version-piloto.json a version.json.")

    archivos = archivos_commiteados()
    crudo = manifiesto_de(archivos, APP_VERSION)
    sello = firma.firmar(secreto, crudo)
    if not firma.verificar(bytes.fromhex(publica), crudo, sello):
        print("  La firma no se pudo comprobar. No se escribió nada.")
        return 1

    with open(os.path.join(RAIZ, MANIFIESTO), "wb") as f:
        f.write(crudo)
    with open(os.path.join(RAIZ, FIRMA_ARCHIVO), "w", encoding="utf-8", newline="\n") as f:
        f.write(sello.hex() + "\n")

    print(f"  Firmada la v{APP_VERSION}: {len(archivos)} archivos.")
    print("  Ahora:")
    print(f'    git add {MANIFIESTO} {FIRMA_ARCHIVO} && git commit -m "Firma de la v{APP_VERSION}"')
    print(f"    git tag v{APP_VERSION} && git push && git push origin v{APP_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
