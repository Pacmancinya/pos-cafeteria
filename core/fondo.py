"""Qué billetes y monedas dejar en la caja al cerrar.

## El problema, tal como pasa en el mostrador

Al cerrar se cuenta el cajón, se sacan las propinas y hay que **dejar un fondo** para el
día siguiente (en un local que conocemos, 60.000). El resto va en un sobre a los jefes.

Lo que nadie te dice es que la parte difícil no es el monto, es **qué dejar**: ¿diez
billetes de mil?, ¿dos de diez mil? Se arma un montón, se vuelve a contar, no cuadra, y se
cuenta de nuevo. Todas las noches.

Y hay una preferencia clara: en la caja sirve el **sencillo** —monedas y billetes chicos—
porque con eso se da vuelto al día siguiente. Los de 20.000 y 10.000 no sirven en el
mostrador y sí sirven en el sobre.

## Cómo se resuelve

Entre todas las formas de juntar el fondo con lo que hay en el cajón, se elige la que deje
**más piezas**. Maximizar piezas es, en la práctica, quedarse con todo el sencillo: 45
monedas de 50 son 45 piezas y 2.250 pesos, contra 2 billetes de mil que son 2 piezas y
2.000. Lo que sobra —que son los billetes grandes— se va al sobre solo.

No se aproxima: son pocas denominaciones y cantidades chicas, así que se recorren todas las
combinaciones con programación dinámica y se sabe la respuesta exacta. Si el fondo **no se
puede formar** con lo que hay (pasa: quedaron puros billetes de 20.000), devuelve lo más
cercano y lo dice, en vez de fingir que cuadró.

## La regla que no se puede romper

`dejar` + `sobre` tiene que dar **exactamente** el conteo, moneda por moneda. Esto es plata
que alguien contó a mano: acá no se puede inventar ni perder una pieza, y hay un test que
lo comprueba en cada caso.
"""

from __future__ import annotations

from functools import reduce
from math import gcd

# Si alguien cuenta un cajón con muchísimas piezas (una feria, una caja que no se vació en
# semanas), el recorrido crece. Por encima de esto se responde con el reparto simple —de
# la denominación más chica hacia arriba— que es peor pero instantáneo, en vez de dejar la
# caja pensando mientras el cajero espera para irse.
MAX_PIEZAS_EXACTO = 4000


def _limpio(conteo: dict | None) -> dict[int, int]:
    """Solo denominaciones y cantidades positivas, como enteros."""
    salida: dict[int, int] = {}
    for den, cant in (conteo or {}).items():
        den, cant = int(den), int(cant)
        if den > 0 and cant > 0:
            salida[den] = salida.get(den, 0) + cant
    return salida


def _sobre(conteo: dict[int, int], dejar: dict[int, int]) -> dict[int, int]:
    """Lo que no se queda. Se calcula restando, nunca sumando aparte: así no hay forma de
    que `dejar` + `sobre` deje de dar el conteo."""
    return {den: cant - dejar.get(den, 0)
            for den, cant in conteo.items() if cant - dejar.get(den, 0) > 0}


def _resultado(conteo: dict[int, int], dejar: dict[int, int], objetivo: int) -> dict:
    total = sum(den * cant for den, cant in dejar.items())
    return {"dejar": dejar, "sobre": _sobre(conteo, dejar),
            "total_dejado": total, "exacto": total == objetivo}


def _aproximado(conteo: dict[int, int], objetivo: int) -> dict:
    """Reparto de emergencia: sencillo primero, sin buscar el exacto."""
    dejar: dict[int, int] = {}
    falta = objetivo
    for den in sorted(conteo):
        if falta <= 0:
            break
        usar = min(conteo[den], falta // den)
        if usar:
            dejar[den] = usar
            falta -= den * usar
    return _resultado(conteo, dejar, objetivo)


def repartir_fondo(conteo: dict | None, objetivo: int) -> dict:
    """Qué dejar en la caja y qué va al sobre.

    `conteo` es {denominación: cantidad} de lo que se contó. Devuelve `dejar`, `sobre`,
    `total_dejado` y `exacto` (si se pudo juntar el objetivo justo).
    """
    conteo = _limpio(conteo)
    total = sum(den * cant for den, cant in conteo.items())
    objetivo = max(0, int(objetivo))

    if not conteo or objetivo == 0:
        return _resultado(conteo, {}, objetivo)
    if objetivo >= total:
        # No alcanza para el fondo: se deja todo y el sobre va vacío. Es exacto solo si
        # justo daba.
        return _resultado(conteo, dict(conteo), objetivo)
    if sum(conteo.values()) > MAX_PIEZAS_EXACTO:
        return _aproximado(conteo, objetivo)

    dens = sorted(conteo)
    # Todas las denominaciones son múltiplos de su máximo común divisor (con pesos chilenos,
    # 10). Trabajar en esa unidad divide por diez los estados a recorrer.
    paso = reduce(gcd, dens)
    tope = min(total, objetivo + dens[-1])   # más allá no puede estar lo más cercano
    n = tope // paso

    # piezas[s] = máximo de piezas para juntar s*paso. -1 = no se puede armar.
    piezas = [-1] * (n + 1)
    piezas[0] = 0
    usados: list[list[int]] = []

    for den in dens:
        salto = den // paso
        nueva = list(piezas)
        usa = [0] * (n + 1)
        for s in range(n + 1):
            if piezas[s] < 0:
                continue
            base = piezas[s]
            for k in range(1, conteo[den] + 1):
                s2 = s + k * salto
                if s2 > n:
                    break
                if base + k > nueva[s2]:
                    nueva[s2] = base + k
                    usa[s2] = k
        piezas = nueva
        usados.append(usa)

    # De todo lo que se puede armar, lo más cercano al objetivo. En un empate gana el de
    # arriba: quedarse corto de sencillo mañana es peor que mandar un poco menos al sobre.
    mejor_s, mejor_dist = 0, objetivo
    for s in range(n + 1):
        if piezas[s] < 0:
            continue
        dist = abs(s * paso - objetivo)
        if dist < mejor_dist or (dist == mejor_dist and s * paso > mejor_s * paso):
            mejor_s, mejor_dist = s, dist

    dejar: dict[int, int] = {}
    s = mejor_s
    for den, usa in zip(reversed(dens), reversed(usados)):
        k = usa[s]
        if k:
            dejar[den] = k
            s -= k * (den // paso)
    return _resultado(conteo, dict(sorted(dejar.items())), objetivo)
