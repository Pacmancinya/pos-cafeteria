"""Códigos de barra: limpiarlos, validarlos y saber cuáles NO sirven.

Todo lo de acá es aritmética y reglas del estándar GS1. No toca la base ni la
red: se puede leer, probar y entender solo.

## Las tres trampas que resuelve

**1. El mismo producto con dos números.** Un UPC-A de 12 dígitos (lo gringo) ES
un EAN-13 con un cero adelante. Si se guardan como vienen, la misma Coca-Cola
queda dos veces según qué lector la leyó. Se normaliza SIEMPRE a 13.

**2. El mal escaneo que crea un producto fantasma.** Una etiqueta arrugada
devuelve dígitos cambiados. El dígito verificador atrapa eso antes de que nadie
cree un producto que no existe.

**3. Los códigos de balanza.** El pan, el jamón, el queso laminado: la balanza
del local imprime en el momento una etiqueta cuyo código **cambia con el peso**.
Si la caja los tratara como códigos normales, cada trozo de pan sería un producto
nuevo — cien productos llamados "Pan" al final del mes. Empiezan con 2 y hay que
reconocerlos para negarse.
"""
from __future__ import annotations

from decimal import Decimal

LARGOS = (8, 12, 13, 14)


def limpiar(codigo: str) -> str:
    """Deja solo los dígitos 0-9. Los lectores mandan espacios, guiones y un Enter final.

    ASCII a propósito: `str.isdigit()` acepta también dígitos de otros alfabetos
    (٣, ³) y `int()` los convierte sin chistar, así que un escaneo corrupto podría
    pasar por un código válido. Acá nunca son legítimos.
    """
    return "".join(c for c in str(codigo or "") if c in "0123456789")


def digito_verificador(sin_verificador: str) -> int:
    """El último dígito, calculado. Módulo 10 con pesos 1 y 3.

    Se recorre de DERECHA a IZQUIERDA a propósito: así la misma función sirve
    para EAN-8, UPC-A, EAN-13 e ITF-14 sin un caso por largo. El peso 3 siempre
    le toca al dígito que va justo a la izquierda del verificador.

    El `% 10` de afuera no sobra: si la suma termina en 0, el verificador es 0 y
    no 10. Es el error clásico de esta cuenta.
    """
    suma = 0
    for i, d in enumerate(reversed(str(sin_verificador))):
        suma += int(d) * (3 if i % 2 == 0 else 1)
    return (10 - (suma % 10)) % 10


def es_valido(codigo: str) -> bool:
    c = limpiar(codigo)
    if len(c) not in LARGOS:
        return False
    return digito_verificador(c[:-1]) == int(c[-1])


def normalizar(codigo: str) -> str:
    """El código como se guarda. Cadena vacía si no sirve.

    Un UPC-A de 12 se convierte en el EAN-13 que de verdad es. Un EAN-8 se deja
    de 8: rellenarlo con ceros daría OTRO número, no el mismo.
    """
    c = limpiar(codigo)
    if not es_valido(c):
        return ""
    if len(c) == 12:
        return "0" + c
    return c


def es_de_balanza(codigo: str) -> bool:
    """¿Lo imprimió la balanza del local, con el peso o el precio adentro?

    GS1 reserva el prefijo 2 para "distribución restringida": vale solo dentro
    de este local. No está en ninguna base de datos del mundo y **cambia con
    cada etiqueta**, porque lleva el peso o el precio adentro.
    """
    c = limpiar(codigo)
    return len(c) == 13 and c.startswith("2")


def es_una_caja(codigo: str) -> bool:
    """ITF-14: el cartón, no la unidad.

    Aparece impreso en la caja de una docena de cervezas. Si alguien escanea el
    cartón en vez de la lata, no va a encontrar el producto — y conviene decirlo
    con esas palabras en vez de "código desconocido".
    """
    return len(limpiar(codigo)) == 14


def por_que_no_sirve(codigo: str) -> str:
    """Por qué este código no se puede guardar como producto. "" si sí se puede.

    Devuelve una frase para leer en el mostrador, no un código de error: quien la
    lee está con la fila esperando.
    """
    c = limpiar(codigo)
    if not c:
        return "Eso no parece un código de barras."
    if len(c) not in LARGOS:
        return (f"Ese código tiene {len(c)} números y los códigos de barra tienen "
                "8, 12, 13 o 14. Puede que se haya leído a medias: escanéalo de nuevo.")
    if not es_valido(c):
        return ("Ese código está mal leído: el número de control no calza. "
                "Pásalo de nuevo, más lento y más derecho.")
    if es_de_balanza(c):
        return ("Ese código lo imprimió una balanza y lleva el peso adentro, así que "
                "cambia con cada trozo. No sirve para identificar un producto: si lo "
                "guardaras, tendrías un producto nuevo por cada pan que vendas.")
    if es_una_caja(c):
        return ("Ese es el código de la CAJA, no el de la unidad. Escanea una botella "
                "suelta, no el cartón.")
    return ""


# --------------------------------------------------------------- el ticket de la balanza
#
# Medido en el local, con una DIGI SM-300 y su ticket en la mano:
#
#     RCT# 3976   TOTAL 197        codigo: 2 5 3976 000197 5
#                                          | |  |     |    |
#           prefijo GS1 restringido --------  |  |     |    verificador
#           subtipo de la balanza ------------  |     |
#           numero de ticket (RCT#) ------------      |
#           total en pesos ---------------------------
#
# Lo importante es lo que NO viene: ni que producto es, ni el peso. El codigo identifica
# UN TICKET, no una mercaderia. Por eso `por_que_no_sirve` sigue teniendo razon en negarse
# a guardarlo como codigo de un producto: son dos usos distintos del mismo numero.
FORMATO_DIGI_SM300 = {"prefijo": "25", "ticket": (2, 6), "total": (6, 12)}


def validar_formato_balanza(formato: dict) -> dict:
    """Valida y devuelve una copia en el formato JSON actual; no corrige errores."""
    if not isinstance(formato, dict):
        raise ValueError("El formato de balanza debe ser un objeto.")
    f = dict(formato)
    if "modo" not in f and set(f) == {"prefijo", "ticket", "total"}:
        f = {"modo": "ticket", "prefijo": f["prefijo"],
             "codigo": f["ticket"], "valor": f["total"], "divisor_peso": 1000}
    if not isinstance(f.get("modo"), str) or f["modo"] not in ("ticket", "plu_peso", "plu_precio"):
        raise ValueError("Modo de balanza desconocido.")
    prefijo = f.get("prefijo")
    if not isinstance(prefijo, str) or not prefijo or any(c not in "0123456789" for c in prefijo):
        raise ValueError("El prefijo tiene que ser solo números.")
    if not prefijo.startswith("2"):
        # GS1 reserva los códigos que empiezan con 2 para uso interno del local. Con
        # otro prefijo —780, el de Chile— los productos de verdad se leerían como
        # tickets, con el monto sacado de sus propios dígitos.
        raise ValueError("El prefijo tiene que empezar con 2: los códigos de balanza "
                         "empiezan así y los de los productos no.")
    rangos = []
    for campo in ("codigo", "valor"):
        rango = f.get(campo)
        if (not isinstance(rango, (list, tuple)) or len(rango) != 2
                or any(type(i) is not int for i in rango)
                or not len(prefijo) <= rango[0] < rango[1] <= 12):
            raise ValueError("Las posiciones del número y del valor tienen que quedar "
                             "después del prefijo y antes del último dígito.")
        rangos.append(list(rango))
    codigo, valor = rangos
    if max(codigo[0], valor[0]) < min(codigo[1], valor[1]):
        raise ValueError("El número y el valor no pueden ocupar los mismos dígitos.")
    divisor = f.get("divisor_peso")
    if type(divisor) is not int or divisor <= 0:
        raise ValueError("El divisor del peso tiene que ser un número entero mayor que 0.")
    return {"modo": f["modo"], "prefijo": prefijo, "codigo": codigo,
            "valor": valor, "divisor_peso": divisor}


FORMATO_BALANZA_POR_DEFECTO = validar_formato_balanza(FORMATO_DIGI_SM300)


def leer_balanza(codigo: str, formato: dict | None = None) -> dict | None:
    """Interpreta PLU/peso, PLU/precio o ticket/total. None si no es una etiqueta.

    El reparto de los digitos es configurable porque cada balanza se programa distinto; el
    de fabrica es el que se midio en el local (DIGI SM-300). Si el prefijo no calza o el
    codigo esta mal leido se devuelve None en vez de inventar un monto: cobrar de mas por
    leer mal una etiqueta es peor que no leerla. El peso se expresa en kilos
    usando Decimal; el total siempre son pesos enteros. No busca productos ni cobra.
    """
    if formato is None:
        f = FORMATO_BALANZA_POR_DEFECTO
    else:
        try:
            f = validar_formato_balanza(formato)
        except ValueError:
            # Antes caía al de fábrica. Desde que las etiquetas se COBRAN, leer con
            # un reparto de dígitos que no es el de la balanza cobra otro monto: es
            # justo lo que dice arriba que no hay que hacer.
            return None
    # Se limpia: el lector manda un Enter al final y a veces espacios, y sin quitarlos
    # la etiqueta no se lee. `limpiar` es ASCII, así que no puede convertir un escaneo
    # corrupto en uno válido — que era el riesgo real.
    c = limpiar(codigo)
    if len(c) != 13 or not es_valido(c) or not c.startswith(f["prefijo"]):
        return None
    identificador = c[slice(*f["codigo"])]
    valor = int(c[slice(*f["valor"])])
    if f["modo"] == "ticket":
        return {"modo": "ticket", "ticket": identificador.lstrip("0") or "0", "total": valor}
    if f["modo"] == "plu_precio":
        return {"modo": "plu_precio", "plu": identificador, "total": valor}
    return {"modo": "plu_peso", "plu": identificador,
            "peso_kg": Decimal(valor) / Decimal(f["divisor_peso"])}
