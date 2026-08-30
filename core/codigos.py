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

LARGOS = (8, 12, 13, 14)


def limpiar(codigo: str) -> str:
    """Deja solo los dígitos. Los lectores a veces mandan espacios o guiones."""
    return "".join(c for c in str(codigo or "") if c.isdigit())


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
