"""Firma de los paquetes de actualización: Ed25519, según el RFC 8032.

Por qué existe: la caja se actualiza sola desde internet, y hasta la 2.18
confiaba en cualquier cosa que publicara la cuenta de GitHub. Si esa cuenta
caía, cada local instalaba lo que el atacante quisiera, todos a la vez. Ahora
cada paquete trae un manifiesto con la huella de cada archivo, firmado con una
llave que NO está en el repositorio: vive en el computador de quien publica.
La caja trae adentro la llave pública y rechaza el paquete si la firma no
calza o si un solo archivo no es el que se firmó.

Solo biblioteca estándar, y a propósito. Lo que viaja en una actualización es
el código, no las librerías que Kofe.exe trae empaquetadas. Si esto usara
`cryptography`, una caja con el .exe viejo no la tendría, y la primera
actualización firmada la dejaría sin poder actualizar nunca más.

Es la implementación de referencia del RFC 8032 (sección 6), sin cambios de
fondo, con los nombres en castellano. No es rápida —verificar toma unos
milisegundos— y no hace falta: se verifica una vez por actualización. Tampoco
es de tiempo constante, y tampoco hace falta: verificar trabaja sobre datos
públicos, y firmar ocurre en el computador de quien publica.
"""
from __future__ import annotations

import hashlib

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_RAIZ_MENOS_UNO = pow(2, (_P - 1) // 4, _P)


def _h(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


# Los puntos van en coordenadas extendidas (X, Y, Z, T), como en el RFC.
def _sumar(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _por(n: int, punto):
    q = (0, 1, 1, 0)               # el neutro
    while n > 0:
        if n & 1:
            q = _sumar(q, punto)
        punto = _sumar(punto, punto)
        n >>= 1
    return q


def _iguales(a, b) -> bool:
    if (a[0] * b[2] - b[0] * a[2]) % _P != 0:
        return False
    return (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recuperar_x(y: int, signo: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if signo else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RAIZ_MENOS_UNO % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != signo:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recuperar_x(_GY, 0)
_BASE = (_GX, _GY, 1, _GX * _GY % _P)


def _comprimir(punto) -> bytes:
    zinv = _inv(punto[2])
    x = punto[0] * zinv % _P
    y = punto[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    signo = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, signo)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _expandir(secreto: bytes):
    if len(secreto) != 32:
        raise ValueError("La llave privada tiene que medir 32 bytes.")
    h = _h(secreto)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publica_de(secreto: bytes) -> bytes:
    """La llave pública (32 bytes) de una llave privada (32 bytes)."""
    a, _ = _expandir(secreto)
    return _comprimir(_por(a, _BASE))


def firmar(secreto: bytes, mensaje: bytes) -> bytes:
    """La firma (64 bytes). Es determinista: el mismo mensaje da la misma firma."""
    a, prefijo = _expandir(secreto)
    publica = _comprimir(_por(a, _BASE))
    r = int.from_bytes(_h(prefijo + mensaje), "little") % _L
    R = _comprimir(_por(r, _BASE))
    k = int.from_bytes(_h(R + publica + mensaje), "little") % _L
    s = (r + k * a) % _L
    return R + int.to_bytes(s, 32, "little")


_NEUTRO = (0, 1, 1, 0)


def _orden_chico(punto) -> bool:
    """¿Es uno de los 8 puntos de orden chico de la curva? Con uno de ellos como
    llave pública, una firma de puros ceros «verifica» para cualquier mensaje:
    lo encontró una prueba. La caja nunca usa otra llave que la suya, que es
    legítima, pero una verificación no puede aceptar eso nunca. Una llave o un
    R de verdad son múltiplos del punto base y jamás caen acá."""
    return _iguales(_por(8, punto), _NEUTRO)


def verificar(publica: bytes, mensaje: bytes, firma: bytes) -> bool:
    """¿Esta firma la hizo la llave privada de `publica`, sobre este mensaje?
    Nunca lanza: una firma rota es simplemente una firma que no vale."""
    try:
        if len(publica) != 32 or len(firma) != 64:
            return False
        A = _descomprimir(publica)
        R_bytes = firma[:32]
        R = _descomprimir(R_bytes)
        if not A or not R or _orden_chico(A) or _orden_chico(R):
            return False
        s = int.from_bytes(firma[32:], "little")
        if s >= _L:
            return False
        k = int.from_bytes(_h(R_bytes + publica + mensaje), "little") % _L
        return _iguales(_por(s, _BASE), _sumar(R, _por(k, A)))
    except Exception:
        return False
