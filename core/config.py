"""Configuración del punto de venta. Todo se puede pisar con variables de entorno."""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# La versión tiene que coincidir con la de version.json cuando se publica.
# Regla heredada de la Biblioteca Láser: nunca repetir el nombre ni el texto de
# novedades entre versiones, o nadie distingue una de otra.
APP_VERSION = "1.6"
APP_NOMBRE = "Nada se pierde"
VERSION = APP_VERSION          # nombre viejo, se mantiene por compatibilidad

# De dónde se enteran las cajas de que hay una versión nueva.
# Tiene que ser un archivo público: el actualizador no maneja claves.
URL_VERSION = os.getenv(
    "POS_URL_VERSION",
    "https://raw.githubusercontent.com/Pacmancinya/pos-cafeteria/main/version.json",
)

# Puerto fijo a propósito: el navegador guarda cosas por origen y si el puerto
# baila, el cajero pierde la sesión. Ver docs/CONTRATO.md sección 4.
PUERTO = int(os.getenv("POS_PUERTO", "8090"))

# Escuchamos en toda la red del local porque las pantallas del menú suelen vivir
# en OTRO computador y necesitan alcanzar /api/v1/carta.
HOST = os.getenv("POS_HOST", "0.0.0.0")

# ...y justamente por eso hay PIN: en una cafetería el wifi de invitados está en
# la misma red. Sin PIN, cualquier cliente conectado al wifi podría abrir la caja
# y registrar o anular ventas. Las peticiones desde el propio PC de la caja
# (127.0.0.1) no lo piden, así que el cajero no tiene fricción.
PIN = os.getenv("POS_PIN", "2468")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_URL = os.getenv("POS_DB_URL", f"sqlite:///{os.path.join(RAIZ, 'pos.db')}")

# El local vive en Chile: guardamos UTC y mostramos hora local.
# Windows NO trae la base de zonas horarias: sin el paquete `tzdata` esto revienta.
# Preferimos que reviente acá, con un mensaje claro, antes que caer a UTC en
# silencio y entregar cierres de caja con las ventas partidas en dos días.
try:
    ZONA = ZoneInfo(os.getenv("POS_ZONA", "America/Santiago"))
except Exception as e:  # ZoneInfoNotFoundError y parientes
    raise RuntimeError(
        "No se encontró la zona horaria del local. En Windows falta el paquete "
        "de zonas horarias: instálalo con  .venv/Scripts/python -m pip install tzdata"
    ) from e

IVA = 0.19
MEDIOS_PAGO = ("efectivo", "debito", "credito", "transferencia")

# Las claves van sin tildes porque viajan por la API y se guardan en la base.
# Esto es cómo se escriben cuando las lee una persona.
NOMBRE_MEDIO = {
    "efectivo": "Efectivo",
    "debito": "Débito",
    "credito": "Crédito",
    "transferencia": "Transferencia",
}

# La plata que circula en Chile, de mayor a menor. Se usa para contar la caja
# por denominación: es mucho más difícil equivocarse contando billetes que
# escribiendo un total de memoria.
DENOMINACIONES = (20000, 10000, 5000, 2000, 1000, 500, 100, 50, 10)

# ---------------------------------------------------------------------------
# Quién puede hacer qué
# ---------------------------------------------------------------------------
# Los permisos viven acá y no en la base a propósito: cambiar quién puede anular
# una venta tiene que ser un cambio de programa que queda escrito, no algo que
# alguien pueda editar desde la caja un sábado apurado.
#
# Las claves van sin tildes ni ñ porque viajan por la API y se guardan.
ROLES = ("dueno", "cajero")

NOMBRE_ROL = {"dueno": "Dueño", "cajero": "Cajero"}

PERMISOS = {
    "dueno": (
        "vender", "anular", "anular_pasado",
        "turno_abrir", "turno_cerrar",
        "ver_dia", "ver_informes", "editar_carta",
        "inventario", "inventario_ajustar",
        "usuarios", "config",
    ),
    # El cajero vende y cuadra su caja. No edita precios ni corrige el pasado:
    # no es desconfianza, es que un error suyo ahí no lo puede deshacer nadie.
    "cajero": (
        "vender", "anular",
        "turno_abrir", "turno_cerrar",
        "ver_dia", "inventario",
    ),
}


def puede(rol: str, permiso: str) -> bool:
    return permiso in PERMISOS.get(rol, ())


# Cuántos segundos de no tocar nada antes de que la caja se bloquee sola.
# Existe para que la presencia sea honesta: una sesión que alguien dejó abierta
# y se fue diría que esa persona estuvo toda la tarde.
BLOQUEO_SEGUNDOS = int(os.getenv("POS_BLOQUEO", "90"))

# Con qué se firma la galleta de la sesión. Si no se define, se deriva de la
# base de datos del local: así cada caja tiene su propia firma sin que nadie
# tenga que inventar una clave, y reiniciar el programa no desloguea a nadie.
SECRETO = os.getenv("POS_SECRETO", "")

# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
# Las tres unidades base. Todo se guarda ENTERO en estas unidades: 200 ml de
# leche es 200, 18 g de café es 18. Un litro y un kilo son formas de comprar,
# no formas de guardar (ver docs/CONTRATO.md, sección de inventario).
UNIDADES = ("g", "ml", "un")

NOMBRE_UNIDAD = {"g": "gramos", "ml": "mililitros", "un": "unidades"}

TIPOS_MOVIMIENTO = ("compra", "venta", "merma", "ajuste", "devolucion", "carga")


def mostrar_cantidad(cantidad: int, unidad: str) -> str:
    """3400 ml -> "3,4 L". Para que el dueño lea litros y kilos, no miles.

    El guardado sigue siendo entero: esto es solo cómo se escribe en pantalla.
    """
    signo = "-" if cantidad < 0 else ""
    n = abs(int(cantidad))
    if unidad == "ml" and n >= 1000:
        return f"{signo}{n / 1000:.1f}".replace(".", ",").replace(",0", "") + " L"
    if unidad == "g" and n >= 1000:
        return f"{signo}{n / 1000:.1f}".replace(".", ",").replace(",0", "") + " kg"
    if unidad == "un":
        return f"{signo}{n}"
    return f"{signo}{n} {unidad}"


def costo_de(cantidad: int, compra_costo: int, compra_contenido: int) -> int:
    """Cuánto vale esa cantidad, en pesos enteros.

    La división va SIEMPRE al final: el costo por unidad no se guarda porque la
    leche sale $1,2 el mililitro y redondear eso a $1 le quita un 17% al valor
    del inventario.
    """
    if compra_contenido <= 0:
        return 0
    return int(cantidad) * int(compra_costo) // int(compra_contenido)


def total_del_conteo(conteo: dict) -> int:
    """{'1000': 4, '500': 3} -> 5500. Ignora lo que no reconozca."""
    total = 0
    for valor, cantidad in (conteo or {}).items():
        try:
            v, c = int(valor), int(cantidad)
        except (TypeError, ValueError):
            continue
        if v in DENOMINACIONES and c > 0:
            total += v * c
    return total

NOMBRE_LOCAL = os.getenv("POS_LOCAL", "Kofe")
AVISOS = [
    "Lunes a sábado de 8:00 a 20:00",
    "Pedidos para llevar en la barra",
]


def ip_en_la_red() -> str:
    """La IP del PC en la red del local, para saber qué dirección poner en las
    pantallas. No abre conexión: solo le pregunta al sistema por dónde saldría."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def token_de_acceso() -> str:
    """Token derivado del PIN: reiniciar el programa no desloguea al tablet."""
    import hashlib
    return hashlib.sha256(("pos-cafeteria:" + PIN).encode()).hexdigest()[:32]


def ahora() -> datetime:
    """Instante actual en UTC, con tzinfo. Nunca uses datetime.now() pelado."""
    return datetime.now(timezone.utc)


def hoy_local() -> date:
    return ahora().astimezone(ZONA).date()


def como_utc(dt: datetime) -> datetime:
    """Lo guardado, con su zona puesta.

    SQLite devuelve los datetime SIN tzinfo, y restarle uno de esos a `ahora()`
    —que sí la tiene— revienta. Todo lo que se guarda está en UTC, así que acá
    se le pone la etiqueta que le corresponde. Úsalo siempre antes de restar.
    """
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def a_local(dt: datetime) -> datetime:
    """SQLite devuelve datetimes sin tzinfo; asumimos que lo guardado es UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZONA)


def rango_utc_del_dia(fecha: date) -> tuple[datetime, datetime]:
    """Un día del calendario chileno, traducido al rango UTC que hay que consultar.

    Existe porque el día del local no es el día UTC: a las 21:00 de Santiago ya es
    el día siguiente en UTC, y el cuadre del turno saldría partido en dos.
    """
    inicio = datetime.combine(fecha, time.min, tzinfo=ZONA)
    fin = inicio + timedelta(days=1)
    return inicio.astimezone(timezone.utc), fin.astimezone(timezone.utc)


def neto_iva(bruto: int) -> tuple[int, int]:
    """Descompone un monto bruto en (neto, iva) sin perder ni ganar un peso.

    El IVA se calcula por diferencia justamente para que neto + iva == bruto
    siempre, incluso cuando el redondeo del neto tira para abajo.
    """
    neto = round(bruto / (1 + IVA))
    return neto, bruto - neto
