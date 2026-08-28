"""Conexión a la base. SQLite por defecto; Postgres cambiando POS_DB_URL."""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from core.config import DB_URL

# check_same_thread=False: uvicorn atiende en varios hilos y SQLite por defecto
# se niega a que el mismo archivo se toque desde otro hilo.
_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, echo=False, connect_args=_args)


def crear_tablas() -> None:
    # Importar los modelos antes de create_all, si no SQLModel no los conoce.
    from apps.pos.db import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    # create_all no agrega columnas nuevas a tablas que ya existen: eso rompería
    # una caja que ya vendió cada vez que se actualiza el programa.
    from apps.pos.db.migraciones import poner_al_dia
    poner_al_dia()


def get_session():
    with Session(engine) as session:
        yield session
