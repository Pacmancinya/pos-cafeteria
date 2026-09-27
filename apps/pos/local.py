"""Los datos del local y el PIN de red, guardados en la base de ESTE local.

Hasta la 2.18 salían de variables de entorno de Windows: el nombre era
`POS_LOCAL` y, si nadie lo tocaba, «Kofe». Una cafetería nueva aparecía como
Kofe en la caja, en el comprobante y en sus televisores. Y el PIN de red era
`2468` en todas las instalaciones, escrito en la guía y en el código público.
Ahora viven en la tabla `Ajuste`, se piden en el primer arranque y el dueño los
cambia desde Ayuda → Ajustes.

Las variables de entorno siguen sirviendo: el nombre como respaldo si nadie lo
escribió en la caja, y el PIN como algo que fija la instalación y la caja no
deja cambiar.
"""
from __future__ import annotations

import os
import re
import secrets

from sqlmodel import Session, select

from apps.pos.db.models import Ajuste, Producto, Venta
from apps.pos.db.session import engine

NOMBRE_POR_DEFECTO = "Mi local"
PIN_DE_FABRICA = "2468"
CANALES = ("estable", "piloto")


def conservar_nombre_instalado(base) -> None:
    """Fija el antiguo defecto antes de que una caja usada pase a «Mi local»."""
    with Session(base) as s:
        guardado = s.get(Ajuste, "local_nombre")
        if guardado and guardado.valor.strip():
            return
        usada = (s.exec(select(Producto.id).limit(1)).first() is not None
                 or s.exec(select(Venta.id).limit(1)).first() is not None)
        if usada:
            # POS_LOCAL también podía identificar una instalación antigua.
            guardar(s, local_nombre=os.getenv("POS_LOCAL", "").strip() or "Kofe")


def _leer(*claves: str) -> dict:
    try:
        with Session(engine) as s:
            filas = s.exec(select(Ajuste).where(Ajuste.clave.in_(claves))).all()
            return {f.clave: f.valor for f in filas}
    except Exception:
        # Sin base todavía (el primer segundo del primer arranque): mandan los
        # valores por defecto. Un dato del local no puede impedir que abra.
        return {}


def guardar(s: Session, **pares: str) -> None:
    for clave, valor in pares.items():
        fila = s.get(Ajuste, clave)
        if fila:
            fila.valor = str(valor)
        else:
            fila = Ajuste(clave=clave, valor=str(valor))
        s.add(fila)
    s.commit()


# ---------------------------------------------------------------------------
# Los datos del local
# ---------------------------------------------------------------------------
def datos() -> dict:
    g = _leer("local_nombre", "local_rut", "local_direccion")
    nombre = ((g.get("local_nombre") or "").strip()
              or os.getenv("POS_LOCAL", "").strip()
              or NOMBRE_POR_DEFECTO)
    return {"nombre": nombre,
            "rut": (g.get("local_rut") or "").strip(),
            "direccion": (g.get("local_direccion") or "").strip()}


def nombre() -> str:
    return datos()["nombre"]


def rut_normalizado(texto: str) -> str | None:
    """'12345678-5', '12.345.678-5' o '123456785' → '12.345.678-5'.

    None si el dígito verificador no calza. Un RUT mal escrito en el
    comprobante es peor que ninguno, y el día de la boleta electrónica tiene
    que estar bien sí o sí: el SII lo rechaza.
    """
    limpio = (texto or "").replace(".", "").replace(" ", "").upper()
    if "-" not in limpio and len(limpio) >= 2:
        limpio = limpio[:-1] + "-" + limpio[-1]
    m = re.match(r"^(\d{1,8})-([\dK])$", limpio)
    if not m:
        return None
    cuerpo, dv = m.group(1), m.group(2)
    suma, factor = 0, 2
    for c in reversed(cuerpo):
        suma += int(c) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    if dv != esperado:
        return None
    return f"{int(cuerpo):,}".replace(",", ".") + "-" + dv


# ---------------------------------------------------------------------------
# El PIN de red
# ---------------------------------------------------------------------------
def pin_por_variable() -> bool:
    """¿Lo fijó la instalación con POS_PIN? Entonces la caja no lo cambia."""
    return bool(os.getenv("POS_PIN", "").strip())


def pin_de_red() -> str:
    if pin_por_variable():
        return os.environ["POS_PIN"].strip()
    guardado = (_leer("pin_red").get("pin_red") or "").strip()
    return guardado or PIN_DE_FABRICA


def pin_es_de_fabrica() -> bool:
    return not pin_por_variable() and pin_de_red() == PIN_DE_FABRICA


def pin_nuevo() -> str:
    """Seis dígitos al azar. Seis y no cuatro porque este PIN lo escribe una vez
    cada tablet y no la gente todos los días: no hay por qué hacerlo corto."""
    return str(secrets.randbelow(900000) + 100000)


# ---------------------------------------------------------------------------
# De dónde se actualiza
# ---------------------------------------------------------------------------
def canal() -> str:
    valor = (_leer("canal_actualizaciones").get("canal_actualizaciones") or "").strip()
    return valor if valor in CANALES else "estable"
