"""Freno de intentos para los PIN.

Hasta la 2.18 no había ninguno: un PIN de 4 dígitos son diez mil
combinaciones, y sin freno se prueban todas en poco rato — desde la misma caja
o desde el Wi-Fi de clientes, que en una cafetería suele compartir router con
la caja. Ahora, después de cinco fallos seguidos hay que esperar, y la espera
se dobla con cada fallo nuevo hasta un tope.

Vive en memoria y no en la base, a propósito: reiniciar el programa lo
limpia, y está bien — quien puede reiniciar la caja ya está parado frente a
ella. Lo que importa es que nadie pueda probar diez mil PIN desde un celular.
"""
from __future__ import annotations

import math
import time
from threading import Lock


class Freno:
    def __init__(self, libres: int = 5, espera: int = 30, maximo: int = 900,
                 reloj=time.monotonic):
        self.libres = libres          # fallos que se perdonan antes de frenar
        self.espera = espera          # segundos de la primera espera
        self.maximo = maximo          # nunca más de esto
        self._reloj = reloj
        self._estado: dict[str, list] = {}   # llave -> [fallos, hasta cuándo]
        self._candado = Lock()

    def cuanto_falta(self, llave: str) -> int:
        """Segundos que faltan para poder volver a probar. 0 si ya se puede."""
        with self._candado:
            e = self._estado.get(llave)
            if not e:
                return 0
            return max(0, math.ceil(e[1] - self._reloj()))

    def fallo(self, llave: str) -> int:
        """Anota un fallo y devuelve cuántos segundos hay que esperar ahora."""
        with self._candado:
            self._limpiar()
            e = self._estado.setdefault(llave, [0, 0.0])
            e[0] += 1
            if e[0] < self.libres:
                return 0
            espera = min(self.espera * 2 ** (e[0] - self.libres), self.maximo)
            e[1] = self._reloj() + espera
            return math.ceil(espera)

    def acierto(self, llave: str) -> None:
        with self._candado:
            self._estado.pop(llave, None)

    def olvidar_todo(self) -> None:
        with self._candado:
            self._estado.clear()

    def _limpiar(self) -> None:
        """Que un barrido de miles de llaves distintas no llene la memoria."""
        if len(self._estado) < 2000:
            return
        ahora = self._reloj()
        for llave in [k for k, (n, hasta) in self._estado.items()
                      if n < self.libres or hasta < ahora]:
            self._estado.pop(llave, None)


def mensaje_de_espera(segundos: int) -> str:
    if segundos < 90:
        return f"Demasiados intentos. Espera {segundos} segundos y vuelve a probar."
    return f"Demasiados intentos. Espera {math.ceil(segundos / 60)} minutos y vuelve a probar."


# Uno solo para todo el programa: el PIN de las personas y el PIN de la red.
PIN = Freno()
