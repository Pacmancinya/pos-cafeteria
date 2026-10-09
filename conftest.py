"""Configuración de pytest.

La base de prueba se define ANTES de importar cualquier cosa del proyecto,
porque `core.config` lee POS_DB_URL al importarse. Si se hace después, los
tests escriben en la base real del local — que es exactamente el accidente
que no queremos.
"""
import os
import shutil
import tempfile

# Todo lo que las pruebas escriben va a una carpeta temporal PROPIA de esta
# corrida: la base, los respaldos y los registros. Hasta la 2.18 la base de
# prueba tenía un nombre fijo —dos corridas a la vez se pisaban la misma— y los
# respaldos y cierres de prueba caían en las carpetas de verdad del local.
_CARPETA_PRUEBAS = os.path.join(tempfile.gettempdir(), f"kofe-pruebas-{os.getpid()}")
os.makedirs(_CARPETA_PRUEBAS, exist_ok=True)
os.environ.setdefault("POS_DB_URL", "sqlite:///" + os.path.join(_CARPETA_PRUEBAS, "pos_test.db"))
os.environ.setdefault("POS_CARPETA_RESPALDOS", os.path.join(_CARPETA_PRUEBAS, "respaldos"))
os.environ.setdefault("POS_CARPETA_REGISTROS", os.path.join(_CARPETA_PRUEBAS, "registros"))
os.environ.setdefault("POS_SIN_ACCESO_DIRECTO", "1")
for _variable in ("POS_PIN", "POS_CLAVE_DESCARGA", "POS_LOCAL"):
    os.environ.pop(_variable, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _limpiar_al_final():
    yield
    shutil.rmtree(_CARPETA_PRUEBAS, ignore_errors=True)


@pytest.fixture(autouse=True)
def _config_por_sesion(monkeypatch):
    """Config pide el PIN de nuevo (apps/pos/api/config.py). Las pruebas del resto de la caja no
    son sobre eso: les basta con que la puerta mire la sesión, como antes de existir el PIN de
    Config. Las que SÍ son sobre eso (test_config.py) piden la fixture `config_real`.

    Y la caja nunca se reinicia de verdad desde una prueba: cerraría pytest."""
    from apps.pos.api import config
    monkeypatch.setattr(config, "autoridad", config.autoridad_de_sesion)
    monkeypatch.setattr(config, "programar_reinicio", lambda: None)


@pytest.fixture()
def config_real(_config_por_sesion, monkeypatch):
    """La puerta de Config de verdad: PIN reciente, amarrado a la sesión."""
    from apps.pos.api import config
    monkeypatch.setattr(config, "autoridad", config.autoridad_real)


@pytest.fixture()
def cliente():
    from apps.pos import freno
    from apps.pos.db.session import engine
    from apps.pos.main import app

    freno.PIN.olvidar_todo()          # un test que falla PIN no frena al siguiente
    from apps.pos import pantallas
    pantallas._visto.clear()          # «visto hace…» de los televisores es de la corrida anterior

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    # client=... simula que entramos desde el propio PC de la caja
    with TestClient(app, client=("127.0.0.1", 5000)) as c:
        yield c
    SQLModel.metadata.drop_all(engine)


@pytest.fixture()
def caja(cliente):
    """Una caja abierta. Desde la 2.5, vender sin esto responde 409.

    Es una fixture aparte y no algo que haga `carta` porque las pruebas de
    turnos necesitan justamente lo contrario: empezar con la caja cerrada para
    poder abrirla ellas. Que un test PIDA la caja abierta es además la
    documentación de la regla: si vende, la necesita.
    """
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Prueba", "monto_inicial": 0})
    return cliente


@pytest.fixture()
def carta(cliente):
    """Dos categorías con productos, creadas por la API (como en la vida real)."""
    cafe = cliente.post("/api/v1/categorias", json={"nombre": "Café", "orden": 0}).json()
    dulce = cliente.post("/api/v1/categorias", json={"nombre": "Dulce", "orden": 1}).json()

    def prod(cat_id, nombre, precio, **extra):
        cuerpo = {"categoria_id": cat_id, "nombre": nombre, "precio": precio, **extra}
        return cliente.post("/api/v1/productos", json=cuerpo).json()

    return {
        "cafe": cafe,
        "dulce": dulce,
        "espresso": prod(cafe["id"], "Espresso", 1900),
        "latte": prod(cafe["id"], "Latte", 3400),
        "mocha": prod(cafe["id"], "Mocha", 3900, destacado=True, badge="Hoy"),
        "alfajor": prod(dulce["id"], "Alfajor", 1900),
    }
