"""Busca e instala una versión nueva desde la ventana negra.

Sirve cuando la caja no está abierta, o cuando algo quedó a medias. Lo mismo
se puede hacer desde la propia caja, tocando el número de versión.

    .venv/Scripts/python -m tools.buscar_actualizacion
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from apps.pos import actualizar  # noqa: E402


def main() -> int:
    info = actualizar.revisar()
    if not info.get("ok"):
        print("  " + info.get("error", "No se pudo revisar."))
        print()
        print("  Si no hay internet, pídele el ZIP nuevo a Ruperto y")
        print("  descomprímelo encima de esta carpeta: no se pierde nada.")
        return 1

    print(f"  Tu versión       : {info['actual']}  ({info['actual_nombre']})")
    print(f"  Versión publicada: {info['disponible']}  ({info['disponible_nombre']})")
    print()

    if not info.get("hay_nueva"):
        print("  Estás al día, no hay nada que instalar.")
        return 0

    print("  HAY UNA VERSIÓN NUEVA")
    if info.get("novedades"):
        print()
        for linea in _envolver(info["novedades"], 66):
            print("    " + linea)
    print()

    if input("  ¿Instalarla ahora? (s/n): ").strip().lower() not in ("s", "si", "sí", "y"):
        print("  Cancelado, no se cambió nada.")
        return 0

    print("  Descargando e instalando...")
    r = actualizar.aplicar(info["zip"])
    print()
    if not r.get("ok"):
        print("  ERROR: " + r.get("error", "no se pudo actualizar"))
        return 1
    if r.get("sin_cambios"):
        print("  " + r["aviso"])
        return 0
    print(f"  LISTO: se actualizaron {len(r['archivos'])} archivos.")
    print("  Tus ventas, precios y respaldos NO se tocaron.")
    print()
    print("  Abre de nuevo el punto de venta para usar la versión nueva.")
    return 0


def _envolver(texto: str, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        if len(actual) + len(palabra) + 1 > ancho:
            lineas.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    if actual:
        lineas.append(actual)
    return lineas


if __name__ == "__main__":
    sys.exit(main())
