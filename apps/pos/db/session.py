"""Conexión a la base. SQLite por defecto; Postgres cambiando POS_DB_URL."""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from core.config import DB_URL

# check_same_thread=False: uvicorn atiende en varios hilos y SQLite por defecto
# se niega a que el mismo archivo se toque desde otro hilo.
_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, echo=False, connect_args=_args)

# Modo WAL y 10 segundos de espera, desde la 2.19. Sin WAL, una lectura larga
# —el informe del mes, un respaldo— frena las escrituras, y pasados los 5
# segundos que Python espera por defecto el cobro falla con «database is
# locked». En la caja eso se ve como un cobro que tarda o falla sin razón. Con
# WAL leer y escribir no se estorban. `synchronous` se queda como viene (FULL):
# una venta confirmada no se pierde ni con un corte de luz.
if DB_URL.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _al_conectar(conexion, _registro):
        cursor = conexion.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
        finally:
            cursor.close()


def crear_tablas() -> None:
    # Importar los modelos antes de create_all, si no SQLModel no los conoce.
    from apps.pos.db import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    # create_all no agrega columnas nuevas a tablas que ya existen: eso rompería
    # una caja que ya vendió cada vez que se actualiza el programa.
    from apps.pos.db.migraciones import poner_al_dia
    poner_al_dia()
    # Llevar cuenta es optativo: arrancar nunca crea insumos ni recetas.


def get_session():
    with Session(engine) as session:
        yield session


def reservar_escritura(session: Session) -> None:
    """Serializa comprobar y guardar, incluso entre procesos de la misma caja.

    Consultar primero y escribir después permite que dos solicitudes aprueben
    el mismo ticket (o PLU libre). El bloqueo pertenece a la transacción: un
    error lo libera al cerrar la sesión sin dejar una reserva huérfana.
    """
    conexion = session.connection()
    if conexion.dialect.name == "sqlite":
        conexion.exec_driver_sql("BEGIN IMMEDIATE")
    elif conexion.dialect.name == "postgresql":
        conexion.exec_driver_sql("SELECT pg_advisory_xact_lock(750013)")
