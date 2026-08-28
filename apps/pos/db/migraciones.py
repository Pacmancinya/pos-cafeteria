"""Migraciones mínimas para SQLite.

`SQLModel.metadata.create_all` crea las tablas que faltan, pero **no** agrega
columnas nuevas a una tabla que ya existe. En una caja que ya vendió, eso
significa que actualizar el programa la rompe: el código pide una columna que
el archivo no tiene.

Esto revisa, al arrancar, que cada tabla tenga las columnas que el modelo dice,
y agrega las que falten con `ALTER TABLE ... ADD COLUMN`. Es lo único que SQLite
permite hacer sin reescribir la tabla, y alcanza para el 95% de los casos
(agregar un campo con valor por defecto).

Lo que NO cubre, y hay que hacer a mano si algún día pasa: renombrar columnas,
cambiar tipos, o borrar columnas.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from apps.pos.db.session import engine


def _sql_del_tipo(col) -> str:
    tipo = col.type.compile(engine.dialect)
    if col.default is not None and getattr(col.default, "arg", None) is not None:
        arg = col.default.arg
        if isinstance(arg, bool):
            return f"{tipo} DEFAULT {1 if arg else 0}"
        if isinstance(arg, (int, float)):
            return f"{tipo} DEFAULT {arg}"
        if isinstance(arg, str):
            return f"{tipo} DEFAULT '{arg}'"
    # sin default explícito: 0 para números, cadena vacía para texto, NULL si acepta
    if col.nullable:
        return tipo
    if "INT" in tipo.upper() or "FLOAT" in tipo.upper() or "NUMERIC" in tipo.upper():
        return f"{tipo} DEFAULT 0"
    return f"{tipo} DEFAULT ''"


def poner_al_dia() -> list[str]:
    """Agrega las columnas que falten. Devuelve lo que hizo, para poder mirarlo."""
    if not engine.url.drivername.startswith("sqlite"):
        return []          # en Postgres esto se hace con una herramienta de verdad

    hechos: list[str] = []
    inspector = inspect(engine)
    existentes = set(inspector.get_table_names())

    with engine.begin() as con:
        for nombre, tabla in SQLModel.metadata.tables.items():
            if nombre not in existentes:
                continue                     # create_all se encarga de las tablas nuevas
            ya = {c["name"] for c in inspector.get_columns(nombre)}
            for col in tabla.columns:
                if col.name in ya:
                    continue
                con.execute(text(
                    f'ALTER TABLE "{nombre}" ADD COLUMN "{col.name}" {_sql_del_tipo(col)}'
                ))
                hechos.append(f"{nombre}.{col.name}")
    return hechos
