"""Ventas de ejemplo, para mostrar cómo se ven los informes antes de usarlo de verdad.

NO se corre solo. Sirve para enseñarle el programa a alguien sin esperar a que
pase una semana vendiendo. Se borra todo con `--borrar`.

    .venv/Scripts/python -m tools.demo.ventas            # crea 7 días de ventas
    .venv/Scripts/python -m tools.demo.ventas --borrar   # deja la base limpia
"""
from __future__ import annotations

import random
import sys
from datetime import timedelta

from sqlmodel import Session, select

from apps.pos.db.models import Producto, Turno, Venta, VentaLinea
from apps.pos.db.session import crear_tablas, engine
from core.config import ZONA, ahora

DIAS = 7
MEDIOS = ["efectivo"] * 5 + ["debito"] * 3 + ["credito"] * 2 + ["transferencia"]


def borrar() -> None:
    with Session(engine) as s:
        for tabla in (VentaLinea, Venta, Turno):
            for fila in s.exec(select(tabla)).all():
                s.delete(fila)
        s.commit()
    print("Listo: no quedan ventas ni turnos.")


def crear() -> None:
    crear_tablas()
    azar = random.Random(7)          # semilla fija: siempre el mismo ejemplo
    with Session(engine) as s:
        productos = s.exec(select(Producto).where(Producto.activo == True)).all()  # noqa: E712
        if not productos:
            print("Primero hay que sembrar la carta: python -m tools.demo.seed")
            return
        if s.exec(select(Venta)).first():
            print("Ya hay ventas. Usa --borrar si quieres partir de cero.")
            return

        numero = 1
        hoy = ahora().astimezone(ZONA)
        for atras in range(DIAS - 1, -1, -1):
            dia = (hoy - timedelta(days=atras)).replace(hour=8, minute=0, second=0, microsecond=0)
            turno = Turno(
                cajero=azar.choice(["Ruperto", "Ana", "Javi"]),
                abierto_at=dia.astimezone(ZONA).astimezone(tz=None).replace(tzinfo=None),
                monto_inicial=20000,
            )
            # guardamos en UTC, como todo el resto
            turno.abierto_at = dia.astimezone(ahora().tzinfo)
            s.add(turno)
            s.commit()
            s.refresh(turno)

            efectivo = 0
            cuantas = azar.randint(14, 34)
            for _ in range(cuantas):
                momento = dia + timedelta(minutes=azar.randint(0, 660))
                medio = azar.choice(MEDIOS)
                lineas, total = [], 0
                for _ in range(azar.randint(1, 3)):
                    p = azar.choice(productos)
                    cant = azar.choice([1, 1, 1, 2])
                    sub = p.precio * cant
                    total += sub
                    lineas.append(VentaLinea(producto_id=p.id, nombre=p.nombre,
                                             precio_unitario=p.precio, cantidad=cant, subtotal=sub))
                propina = azar.choice([0, 0, 0, 0, 500, 1000]) if medio == "efectivo" else 0
                v = Venta(numero=numero, turno_id=turno.id, total=total, propina=propina,
                          medio_pago=medio, creada_at=momento.astimezone(ahora().tzinfo))
                v.lineas = lineas
                numero += 1
                if medio == "efectivo":
                    efectivo += total + propina
                s.add(v)
            s.commit()

            # una anulada de vez en cuando, para que se vea cómo queda
            if azar.random() < 0.4:
                alguna = s.exec(select(Venta).where(Venta.turno_id == turno.id)).first()
                if alguna:
                    alguna.estado = "anulada"
                    alguna.anulada_motivo = "se equivocó el cajero"
                    alguna.anulada_at = alguna.creada_at
                    if alguna.medio_pago == "efectivo":
                        efectivo -= alguna.total + alguna.propina
                    s.add(alguna)
                    s.commit()

            if atras > 0:            # el día de hoy queda con la caja abierta
                esperado = turno.monto_inicial + efectivo
                turno.efectivo_contado = esperado + azar.choice([0, 0, 0, -500, 500, -1000])
                turno.diferencia = turno.efectivo_contado - esperado
                turno.cerrado_at = (dia + timedelta(hours=12)).astimezone(ahora().tzinfo)
                s.add(turno)
                s.commit()

        print(f"Listo: {numero - 1} ventas de ejemplo en {DIAS} días.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    borrar() if "--borrar" in sys.argv else crear()
