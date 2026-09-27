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

## La propina es el mismo problema al revés

Al cerrar también hay que **sacar la propina en efectivo** para repartirla. Ahí la
preferencia se da vuelta: conviene sacarla en **billetes grandes**, porque las monedas
tienen que quedarse en la caja para dar vuelto mañana. Misma cuenta, objetivo opuesto:
minimizar piezas en vez de maximizarlas.

Y el orden importa. La propina sale **primero**, del cajón completo: si saliera después de
apartar el fondo se quedaría sin billetes medianos con qué formarse. El sobre es lo que
queda, y no tiene preferencia: le da lo mismo con qué esté hecho.

## La regla que no se puede romper

`dejar` + `sobre` tiene que dar **exactamente** el conteo, moneda por moneda. Esto es plata
que alguien contó a mano: acá no se puede inventar ni perder una pieza, y hay un test que
lo comprueba en cada caso.
"""

from __future__ import annotations

from functools import reduce
from math import gcd

# Lo que de verdad cuesta no son las piezas sino los MONTOS que hay que recorrer. Con dos
# piezas basta para reventar si una denominación es absurda: {1: 1, 100000000000000000000: 1}
# pedía una lista de 10^20 posiciones y se caía con OverflowError. Así que el tope es sobre
# los estados del recorrido, y por encima se responde con el reparto simple —peor, pero
# instantáneo— en vez de dejar la caja pensando mientras el cajero espera para irse.
MAX_ESTADOS = 2_000_000
MAX_PIEZAS_EXACTO = 20_000


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


def _aproximado(conteo: dict[int, int], objetivo: int, preferir: str = "sencillo") -> dict:
    """Reparto de emergencia, cuando el recorrido exacto saldría carísimo.

    Antes de rendirse prueba lo obvio: que el objetivo salga con una sola denominación. Es
    el caso más común de los que el recorrido simple tiraba a la basura —4.000 monedas de
    50 y un objetivo de 50 daban «no se puede»— y cuesta nada comprobarlo.
    """
    for den in sorted(conteo, reverse=(preferir == "grande")):
        if objetivo % den == 0 and conteo[den] >= objetivo // den:
            return _resultado(conteo, {den: objetivo // den}, objetivo)

    dejar: dict[int, int] = {}
    falta = objetivo
    for den in sorted(conteo, reverse=(preferir == "grande")):
        if falta <= 0:
            break
        usar = min(conteo[den], falta // den)
        if usar:
            dejar[den] = usar
            falta -= den * usar
    return _resultado(conteo, dejar, objetivo)


def repartir_fondo(conteo: dict | None, objetivo: int) -> dict:
    """Qué dejar en la caja y qué va al sobre. Se queda con el sencillo."""
    return repartir(conteo, objetivo, preferir="sencillo")


def repartir(conteo: dict | None, objetivo: int, preferir: str = "sencillo") -> dict:
    """Aparta `objetivo` del conteo. Devuelve `dejar`, `sobre`, `total_dejado` y `exacto`.

    `preferir="sencillo"` aparta la mayor cantidad de piezas posible: es lo que se quiere
    para el fondo de la caja, porque el sencillo es lo que sirve para dar vuelto.
    `preferir="grande"` aparta las menos piezas posibles: es lo que se quiere para sacar la
    propina, porque las monedas tienen que quedarse.

    Cuando no se puede formar el monto justo, `sencillo` se pasa para arriba (quedarse
    corto de vuelto mañana es peor) y `grande` se queda abajo (no se regala plata que no
    era propina).
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
    # De cada denominación no puede hacer falta más de lo que cabe en el objetivo: para
    # juntar 50 pesos sobran 3.999 de las 4.000 monedas de 50 que haya en el cajón. Recortar
    # antes de recorrer no cambia ninguna respuesta —lo recortado nunca entraría— y evita
    # que un cajón muy cargado caiga al reparto simple, que ahí tiraba a la basura
    # soluciones exactas y decía «no se puede» cuando sí se podía.
    util = {den: min(cant, objetivo // den + 1) for den, cant in conteo.items()}
    dens = sorted(util)
    paso_util = reduce(gcd, dens)
    tope_util = min(sum(d * c for d, c in util.items()), objetivo + dens[-1])
    if (sum(util.values()) > MAX_PIEZAS_EXACTO
            or tope_util // paso_util > MAX_ESTADOS):
        return _aproximado(conteo, objetivo, preferir)

    conteo_original, conteo = conteo, util
    # Todas las denominaciones son múltiplos de su máximo común divisor (con pesos chilenos,
    # 10). Trabajar en esa unidad divide por diez los estados a recorrer.
    paso = reduce(gcd, dens)
    tope = min(total, objetivo + dens[-1])   # más allá no puede estar lo más cercano
    n = tope // paso

    # piezas[s] = las piezas que cuesta juntar s*paso, con el criterio pedido.
    # None = ese monto no se puede armar con lo que hay.
    mas_piezas = preferir != "grande"
    piezas: list[int | None] = [None] * (n + 1)
    piezas[0] = 0
    usados: list[list[int]] = []

    for den in dens:
        salto = den // paso
        nueva = list(piezas)
        usa = [0] * (n + 1)
        for s in range(n + 1):
            base = piezas[s]
            if base is None:
                continue
            for k in range(1, conteo[den] + 1):
                s2 = s + k * salto
                if s2 > n:
                    break
                actual = nueva[s2]
                if actual is None or (base + k > actual if mas_piezas else base + k < actual):
                    nueva[s2] = base + k
                    usa[s2] = k
        piezas = nueva
        usados.append(usa)

    # De todo lo que se puede armar, lo más cercano al objetivo. En un empate, para el
    # fondo gana el de arriba (quedarse corto de vuelto mañana es peor) y para la propina
    # el de abajo (no se regala plata que no era propina).
    mejor_s, mejor_dist = 0, objetivo
    for s in range(n + 1):
        if piezas[s] is None:
            continue
        dist = abs(s * paso - objetivo)
        if dist < mejor_dist:
            mejor_s, mejor_dist = s, dist
        elif dist == mejor_dist and mas_piezas and s * paso > mejor_s * paso:
            mejor_s = s

    dejar: dict[int, int] = {}
    s = mejor_s
    for den, usa in zip(reversed(dens), reversed(usados)):
        k = usa[s]
        if k:
            dejar[den] = k
            s -= k * (den // paso)
    # Contra el conteo original, no contra el recortado: lo que se recortó sigue en el
    # cajón y tiene que aparecer en el sobre. Es la regla que no se puede romper.
    return _resultado(conteo_original, dict(sorted(dejar.items())), objetivo)


def plan_de_cierre(conteo: dict | None, propina: int = 0, fondo: int = 0) -> dict:
    """Las tres pilas del cierre: la propina que sale, el fondo que queda y el sobre.

    La propina se aparta PRIMERO, del cajón completo: si se apartara después del fondo se
    quedaría sin billetes medianos con qué formarse. Después se arma el fondo con lo que
    queda, quedándose con el sencillo. Y el sobre es, literalmente, lo que sobra.

    Devuelve cada pila con su detalle y su total, y si cada una se pudo formar justa.
    """
    conteo = _limpio(conteo)
    prop = repartir(conteo, propina, preferir="grande")
    resto = prop["sobre"]
    caja = repartir(resto, fondo, preferir="sencillo")
    return {
        "contado": sum(d * c for d, c in conteo.items()),
        "propina": {"detalle": prop["dejar"], "total": prop["total_dejado"],
                    "exacto": prop["exacto"]},
        "fondo": {"detalle": caja["dejar"], "total": caja["total_dejado"],
                  "exacto": caja["exacto"]},
        "sobre": {"detalle": caja["sobre"],
                  "total": sum(d * c for d, c in caja["sobre"].items())},
    }
