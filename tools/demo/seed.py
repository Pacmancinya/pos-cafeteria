"""Siembra la carta de ejemplo.

Son los mismos productos que traen las pantallas del local, para que los dos
sistemas partan diciendo lo mismo. Se corre así, desde la raíz del proyecto:

    .venv/Scripts/python -m tools.demo.seed
    .venv/Scripts/python -m tools.demo.seed --forzar    # borra y vuelve a sembrar
"""
from __future__ import annotations

import sys

from sqlmodel import Session, select

from apps.pos.db.models import Categoria, Producto
from apps.pos.db.session import crear_tablas, engine

CARTA = [
    ("Café caliente", [
        # nombre, descripción, precio, dibujo, destacado, badge, etiqueta
        ("Espresso", "Doble carga, taza corta", 1900, "taza", False, "", ""),
        ("Cortado", "Espresso con leche vaporizada", 2300, "taza-cortado", False, "", ""),
        ("Americano", "Espresso largo, cuerpo suave", 2400, "mug", False, "", ""),
        ("Cappuccino", "Espresso, leche y espuma en tercios", 3200, "mug-espuma", False, "", ""),
        ("Latte", "Leche sedosa, arte en la superficie", 3400, "mug-arte", False, "", "Avena sin costo"),
        ("Chocolate", "Cacao 70% con leche entera", 3500, "mug-crema", False, "", ""),
        ("Mocha con crema", "Espresso, cacao amargo y crema batida", 3900, "mug-crema", True, "Recomendado de hoy", ""),
    ]),
    ("Fríos", [
        ("Cold Brew", "18 horas de infusión en frío", 3800, "vaso", False, "", "Sin amargor"),
        ("Iced Latte", "Espresso sobre leche fría y hielo", 3900, "vaso-leche", False, "", ""),
        ("Café Tónica", "Espresso, tónica y rodaja de limón", 4200, "vaso-limon", False, "", "Nuevo"),
        ("Matcha Latte", "Matcha ceremonial con leche fría", 4400, "vaso-verde", False, "", ""),
        ("Limonada", "Limón de pica con menta fresca", 3200, "vaso-menta", False, "", ""),
        ("Frappé Mocha", "Batido helado con crema y cacao", 4600, "frappe", True, "Para el calor", ""),
    ]),
    ("Pastelería", [
        ("Croissant", "Mantequilla, masa de 72 horas", 2500, "croissant", False, "", ""),
        ("Croissant de almendras", "Relleno de frangipane", 3400, "croissant-almendras", False, "", ""),
        ("Cheesecake", "Base de galleta y frambuesa", 3900, "torta", False, "", ""),
        ("Kuchen", "De manzana, con canela suave", 3400, "torta-manzana", False, "", ""),
        ("Brownie", "Chocolate 70% y nuez tostada", 2900, "brownie", False, "", ""),
        ("Alfajor", "Manjar casero y coco", 1900, "alfajor", False, "", "Hecho acá"),
        ("Torta del día", "Cambia cada mañana", 4200, "torta", True, "Hasta agotar", ""),
    ]),
    ("Promos", [
        ("Desayuno Kofe", "Café mediano + croissant", 5200, "croissant", False, "", ""),
        ("Media tarde", "Latte + alfajor", 4700, "alfajor", False, "", ""),
        ("Café + brownie", "El clásico de las cinco", 5800, "brownie", False, "", ""),
        ("Estudiantes", "Café chico + galleta, con credencial", 3500, "taza-cortado", False, "", "Lun a vie"),
    ]),
]

ANTES = {"Desayuno Kofe": 5900, "Media tarde": 5300, "Café + brownie": 6300}


def sembrar(forzar: bool = False) -> None:
    crear_tablas()
    with Session(engine) as s:
        if s.exec(select(Categoria)).first():
            if not forzar:
                print("Ya hay una carta cargada. Usa --forzar si quieres reemplazarla.")
                return
            for p in s.exec(select(Producto)).all():
                s.delete(p)
            for c in s.exec(select(Categoria)).all():
                s.delete(c)
            s.commit()

        for i, (nombre_cat, productos) in enumerate(CARTA):
            cat = Categoria(nombre=nombre_cat, orden=i)
            s.add(cat)
            s.commit()
            s.refresh(cat)
            for j, (nom, desc, precio, dib, dest, badge, etiq) in enumerate(productos):
                s.add(Producto(
                    categoria_id=cat.id, nombre=nom, descripcion=desc, precio=precio,
                    orden=j, dibujo=dib, destacado=dest, badge=badge, etiqueta=etiq,
                    antes=ANTES.get(nom),
                ))
            s.commit()

        n = len(s.exec(select(Producto)).all())
        print(f"Carta lista: {len(CARTA)} categorías, {n} productos.")


if __name__ == "__main__":
    sembrar(forzar="--forzar" in sys.argv)
