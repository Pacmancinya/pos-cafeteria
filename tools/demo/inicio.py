"""El modo demo: una caja que abre lista para mostrar, con carta, gente y ventas de ejemplo.

Lo prende SOLO un archivo `MODO-DEMO.txt` en la raíz de la instalación (al lado del
.exe; ver core.config.modo_demo). Viene en el paquete CajaClara-demo-vX.Y.zip y en
ningún otro: una caja de un local nunca lo tiene, y sin él esto no hace nada.

Con la marca, al arrancar y SOLO si la base está vacía (sin productos, ventas, gente ni
turnos), siembra:
  · la carta de ejemplo (tools.demo.seed),
  · dos personas con PIN conocido: Ana (dueña, 1111) y Luis (cajero, 2222),
  · siete días de ventas (tools.demo.ventas), con la caja de hoy abierta,
  · el nombre «Café de ejemplo» y un PIN de red, para que no aparezcan las preguntas
    del primer arranque.
Si ya hay datos, no toca nada: para volver a empezar está REINICIAR-DEMO.bat, que borra
la base (solo si está la marca) y la caja vuelve a sembrar al abrir.
"""
from __future__ import annotations

from sqlmodel import Session, select

from apps.pos.db.models import Producto, Turno, Usuario, Venta
from apps.pos.db.session import engine
from core.config import modo_demo

NOMBRE_DEMO = "Café de ejemplo"
PIN_RED_DEMO = "246801"
GENTE = (("Ana", "1111", "dueno", "#C9552B"), ("Luis", "2222", "cajero", "#4E7C5B"))


def base_vacia() -> bool:
    with Session(engine) as s:
        return all(s.exec(select(t.id).limit(1)).first() is None
                   for t in (Producto, Venta, Usuario, Turno))


def preparar() -> bool:
    """True si sembró. Nunca siembra sin la marca ni sobre datos existentes."""
    if not modo_demo() or not base_vacia():
        return False
    # Los generadores se importan recién acá: una caja normal ni los carga.
    from apps.pos import local, sesion
    from tools.demo import seed, ventas

    seed.sembrar()
    with Session(engine) as s:
        for orden, (nombre, pin, rol, color) in enumerate(GENTE):
            s.add(Usuario(nombre=nombre, rol=rol, pin_hash=sesion.cifrar_pin(pin),
                          color=color, orden=orden))
        local.guardar(s, local_nombre=NOMBRE_DEMO, pin_red=PIN_RED_DEMO)
    ventas.crear()
    return True
