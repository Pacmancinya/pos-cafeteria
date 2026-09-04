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

                # `contado` nace en 0 para toda fila (ADD COLUMN no sabe de otra
                # cosa), pero los insumos que YA existían tienen su saldo de
                # compras y conteos de verdad: hay que marcarlos como contados o
                # el tope duro no los tomaría en cuenta. Los insumos que cree la
                # puesta al día DESPUÉS de esto nacen en 0 aparte, que es lo que
                # queremos: ésos todavía no se contaron.
                if nombre == "insumo" and col.name == "contado":
                    con.execute(text('UPDATE "insumo" SET "contado" = 1'))

        # `create_all` crea las tablas nuevas con sus índices, pero una tabla que
        # YA existía no recibe nunca un índice nuevo. Y el del código de barras
        # importa: con el escáner, "dame el producto de este código" pasa a ser
        # la consulta más caliente de la caja — una por venta, con la fila de
        # clientes esperando. Sin índice, cada escaneo recorre la tabla entera.
        for indice, tabla, columna in (
            ("ix_codigobarra_producto_id", "codigobarra", "producto_id"),
            ("ix_insumo_producto_id", "insumo", "producto_id"),
            ("ix_producto_nombre", "producto", "nombre"),
        ):
            if tabla not in existentes:
                continue
            columnas = {c["name"] for c in inspector.get_columns(tabla)}
            if columna not in columnas:
                continue
            con.execute(text(
                f'CREATE INDEX IF NOT EXISTS "{indice}" ON "{tabla}" ("{columna}")'))

    hechos += _amarrar_insumos_a_su_producto()
    return hechos


def _amarrar_insumos_a_su_producto() -> list[str]:
    """Le pone `producto_id` a los insumos que ya existían.

    Hasta ahora, un producto que se vendía TAL CUAL se amarraba a su insumo
    comparando NOMBRES. Eso ya no se usa, pero las bases que vienen de antes
    tienen la relación escrita solo en la receta. Acá se traduce a un id.

    Solo toca el caso que no admite duda: una receta de UNA sola línea, con
    cantidad 1, y el insumo todavía sin dueño. Si son dos líneas es una receta
    de verdad —un capuchino no "es" la leche— y no se toca.

    Es idempotente: la segunda vez no encuentra nada que hacer.
    """
    from apps.pos.db.models import Insumo, Producto, Receta
    from sqlmodel import Session, select

    hechos = []
    with Session(engine) as s:
        cuantas = {}
        for r in s.exec(select(Receta)).all():
            cuantas[r.producto_id] = cuantas.get(r.producto_id, 0) + 1
        for r in s.exec(select(Receta)).all():
            if cuantas.get(r.producto_id) != 1 or r.cantidad != 1:
                continue
            i = s.get(Insumo, r.insumo_id)
            if not i or i.producto_id:
                continue
            i.producto_id = r.producto_id
            # De paso, el nombre. En la base del local quedó un insumo llamado
            # "Producto nuevo" amarrado a "redbul 550ml": el producto se creó,
            # se marcó "se vende tal cual" con el nombre por defecto, y después
            # se le cambió el nombre solo a la ficha. El dueño abre la bodega,
            # no reconoce nada, y termina creando otro.
            p = s.get(Producto, r.producto_id)
            if p and p.nombre and i.nombre != p.nombre:
                hechos.append(f"insumo {i.id}: «{i.nombre}» → «{p.nombre}»")
                i.nombre = p.nombre
            s.add(i)
            hechos.append(f"insumo {i.id} → producto {r.producto_id}")
        if hechos:
            s.commit()
    return hechos
