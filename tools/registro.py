"""Deja por escrito cada cierre de caja, sin que nadie tenga que acordarse.

El punto de venta ya deja exportar a Excel cuando alguien aprieta el botón. El
problema es justamente ese: hay que acordarse. Esto escribe una fila por cada
cierre en el momento en que ocurre, en un CSV por mes que se abre con doble
clic.

Es un archivo aparte de la base a propósito: `pos.db` es del programa y hay que
saber abrirla; esto es del dueño y se lee en Excel. Si algún día el programa
desaparece, el historial de cierres sigue siendo legible.

Separador `;` y `utf-8-sig`, igual que el resto de las exportaciones, porque así
el Excel en español los abre en columnas y con los acentos derechos.
"""
from __future__ import annotations

import csv
import io
import os

from core.config import NOMBRE_MEDIO, RAIZ, a_local

CARPETA = os.path.join(RAIZ, "registros")

CABECERA = [
    # "Cerró otra persona" es una columna aparte y no un detalle que se saque
    # comparando "Abrió" y "Cerró" a ojo: es la excepción a la regla de que la
    # caja la cierra quien la abrió, y en un Excel de 30 filas una columna que
    # dice SÍ se filtra en un clic. Dos columnas que hay que comparar, no.
    "Fecha", "Abrió", "Cerró", "Cerró otra persona", "Quiénes estuvieron",
    "Fondo inicial", "Ventas en efectivo", "Efectivo esperado",
    "Efectivo contado", "Diferencia",
    "Queda de fondo", "Se retira",
    "Propinas efectivo", "Propinas tarjeta",
    "Ventas del turno", "Total vendido",
    "Detalle por medio de pago", "Descuadre de tarjetas", "Nota",
    # "Sacado en el turno" va AL FINAL a propósito, aunque su lugar natural sería
    # junto a "Ventas en efectivo": el CSV del mes ya existe en el local y se le
    # agregan filas sin reescribir la cabecera. Una columna metida en el medio
    # correría todas las de la derecha y dejaría el mes en curso desalineado; al
    # final, las filas viejas quedan con esa celda vacía y nada más se mueve.
    "Sacado en el turno",
]


def _texto_medios(medios: list[dict]) -> tuple[str, str]:
    """Lo vendido por medio, y el descuadre contra el banco si se escribió."""
    detalle, descuadres = [], []
    for m in medios:
        detalle.append(f"{m['nombre']}: {m['esperado']}")
        if m.get("declarado") is not None and m.get("diferencia"):
            signo = "+" if m["diferencia"] > 0 else ""
            descuadres.append(f"{m['nombre']} {signo}{m['diferencia']}")
    return " · ".join(detalle), " · ".join(descuadres)


def anotar_cierre(turno: dict) -> str:
    """Agrega la fila del cierre. Devuelve el archivo, o "" si no se pudo.

    Nunca lanza: un registro que falla no puede impedir que la caja cierre.
    """
    try:
        os.makedirs(CARPETA, exist_ok=True)
        cerrado = turno.get("cerrado_at") or turno.get("abierto_at") or ""
        mes = cerrado[:7] or "sin-fecha"
        ruta = os.path.join(CARPETA, f"cierres-{mes}.csv")
        nuevo = not os.path.exists(ruta)

        por_medio = turno.get("por_medio") or {}
        vendido = sum(d.get("ventas", 0) for d in por_medio.values())
        cuantas = sum(d.get("cantidad", 0) for d in por_medio.values())
        propinas = turno.get("propinas") or {}
        detalle, descuadre = _texto_medios(turno.get("medios") or [])
        estuvieron = ", ".join(
            f"{g['nombre']} ({g['minutos']} min)" for g in (turno.get("estuvieron") or []))

        fila = [
            cerrado[:16].replace("T", " "),
            turno.get("abrio", ""), turno.get("cerro", ""),
            "SÍ" if (turno.get("cerro") and turno.get("abrio")
                     and turno["cerro"] != turno["abrio"]) else "",
            estuvieron,
            turno.get("monto_inicial", 0), turno.get("ventas_efectivo", 0),
            turno.get("efectivo_esperado", 0), turno.get("efectivo_contado", 0),
            turno.get("diferencia", 0),
            turno.get("fondo_siguiente", 0), turno.get("retiro", 0),
            propinas.get("efectivo", 0), propinas.get("tarjeta", 0),
            cuantas, vendido,
            detalle, descuadre, turno.get("nota", ""),
            turno.get("retiros_total", 0),          # al final: ver CABECERA
        ]

        with io.open(ruta, "a", encoding="utf-8-sig", newline="") as f:
            escritor = csv.writer(f, delimiter=";")
            if nuevo:
                escritor.writerow(CABECERA)
            escritor.writerow(fila)
        return ruta
    except Exception:
        return ""


def cierres_del_mes(mes: str) -> str:
    """La ruta del archivo de ese mes ("2026-08"), exista o no."""
    return os.path.join(CARPETA, f"cierres-{mes}.csv")
