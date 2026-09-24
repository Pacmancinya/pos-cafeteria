"""RSA mínimo para el TED: PKCS#1 de dos primos y SHA1withRSA.

RFC 8017, A.1.2 y 9.2: https://www.rfc-editor.org/rfc/rfc8017.html
Solo módulos que ya trae el proyecto. No genera llaves ni cifra; no es de
tiempo constante. SHA1 se usa exclusivamente por el formato del timbre SII.
"""

import base64
import hashlib
import re
from dataclasses import dataclass, field


# Límites locales para acotar entradas y trabajo; no son límites del SII.
_MIN_BITS = 512
_MAX_BITS = 8192
_MAX_PEM = 20000
_SHA1_DIGEST_INFO = bytes.fromhex("3021300906052b0e03021a05000414")


def _validar_publica(modulo: int, exponente: int) -> int:
    if type(modulo) is not int or type(exponente) is not int:
        raise ValueError("El módulo y el exponente RSA deben ser enteros.")
    if not _MIN_BITS <= modulo.bit_length() <= _MAX_BITS or modulo % 2 != 1:
        raise ValueError("El módulo RSA debe ser impar y tener entre 512 y 8192 bits.")
    if not 3 <= exponente < modulo or exponente % 2 != 1:
        raise ValueError("El exponente público RSA no es válido.")
    return (modulo.bit_length() + 7) // 8


@dataclass(frozen=True)
class LlavePrivada:
    modulo: int
    exponente: int
    d: int = field(repr=False)
    p: int = field(repr=False)
    q: int = field(repr=False)
    dp: int = field(repr=False)
    dq: int = field(repr=False)
    q_inv: int = field(repr=False)

    def __post_init__(self):
        _validar_publica(self.modulo, self.exponente)
        valores = (self.d, self.p, self.q, self.dp, self.dq, self.q_inv)
        if any(type(v) is not int or not 0 < v < self.modulo for v in valores):
            raise ValueError("La llave privada RSA contiene enteros fuera de rango.")
        if (self.p <= 2 or self.q <= 2 or self.p == self.q
                or self.p % 2 != 1 or self.q % 2 != 1
                or self.p * self.q != self.modulo):
            raise ValueError("Los factores de la llave privada RSA no corresponden al módulo.")
        a, b = self.p - 1, self.q - 1
        while b:
            a, b = b, a % b
        multiplo = (self.p - 1) // a * (self.q - 1)
        if (self.d * self.exponente % multiplo != 1
                or self.dp != self.d % (self.p - 1)
                or self.dq != self.d % (self.q - 1)
                or not self.q_inv < self.p
                or self.q_inv * self.q % self.p != 1):
            raise ValueError("Los exponentes o el coeficiente de la llave privada RSA no corresponden.")


class _DER:
    """TLV DER acotado: longitudes definidas y representación mínima."""

    def __init__(self, datos: bytes):
        self.datos = datos
        self.pos = 0

    def leer(self, etiqueta: int) -> bytes:
        datos, pos = self.datos, self.pos
        if pos + 2 > len(datos) or datos[pos] != etiqueta:
            raise ValueError("DER RSA mal formado: etiqueta incorrecta o datos truncados.")
        largo = datos[pos + 1]
        pos += 2
        if largo & 0x80:
            cantidad = largo & 0x7f
            if cantidad == 0 or cantidad > 2 or pos + cantidad > len(datos):
                raise ValueError("DER RSA mal formado: longitud inválida.")
            if datos[pos] == 0:
                raise ValueError("DER RSA mal formado: longitud no mínima.")
            largo = int.from_bytes(datos[pos:pos + cantidad], "big")
            pos += cantidad
            if largo < 128:
                raise ValueError("DER RSA mal formado: longitud no mínima.")
        if pos + largo > len(datos):
            raise ValueError("DER RSA mal formado: contenido truncado.")
        self.pos = pos + largo
        return datos[pos:self.pos]

    def entero(self) -> int:
        datos = self.leer(0x02)
        if not datos or datos[0] & 0x80:
            raise ValueError("DER RSA mal formado: INTEGER vacío o negativo.")
        if len(datos) > 1 and datos[0] == 0 and datos[1] < 0x80:
            raise ValueError("DER RSA mal formado: INTEGER no mínimo.")
        if len(datos) > _MAX_BITS // 8 + 1:
            raise ValueError("DER RSA mal formado: INTEGER demasiado grande.")
        return int.from_bytes(datos, "big")

    def terminar(self):
        if self.pos != len(self.datos):
            raise ValueError("DER RSA mal formado: sobran datos.")


def leer_privada(pem: str | bytes) -> LlavePrivada:
    """Lee exclusivamente PEM RSA PRIVATE KEY sin cifrar, PKCS#1 versión 0."""
    if not isinstance(pem, (str, bytes)) or len(pem) > _MAX_PEM:
        raise ValueError("La llave privada PEM es inválida o demasiado grande.")
    if isinstance(pem, bytes):
        try:
            pem = pem.decode("ascii")
        except UnicodeDecodeError:
            raise ValueError("La llave privada PEM debe contener solo caracteres ASCII.") from None
    bloque = re.fullmatch(
        r"[ \t\r\n]*-----BEGIN RSA PRIVATE KEY-----[ \t\r\n]+"
        r"([A-Za-z0-9+/= \t\r\n]+)"
        r"-----END RSA PRIVATE KEY-----[ \t\r\n]*", pem,
    )
    if bloque is None:
        raise ValueError("Se esperaba una llave PEM RSA PRIVATE KEY (PKCS#1 sin cifrar).")
    contenido = re.sub(r"[ \t\r\n]", "", bloque[1])
    try:
        der = base64.b64decode(contenido, validate=True)
    except ValueError:
        raise ValueError("La llave privada PEM contiene base64 inválido.") from None
    if base64.b64encode(der).decode("ascii") != contenido:
        raise ValueError("La llave privada PEM contiene base64 no canónico.")
    exterior = _DER(der)
    secuencia = _DER(exterior.leer(0x30))
    exterior.terminar()
    valores = [secuencia.entero() for _ in range(9)]
    secuencia.terminar()
    if valores[0] != 0:
        raise ValueError("Solo se admite PKCS#1 versión 0 (RSA de dos primos).")
    return LlavePrivada(*valores[1:])


def _emsa(mensaje: bytes, largo: int) -> bytes:
    if not isinstance(mensaje, bytes):
        raise ValueError("El mensaje RSA debe entregarse como bytes.")
    digest_info = _SHA1_DIGEST_INFO + hashlib.sha1(mensaje).digest()
    relleno = largo - len(digest_info) - 3
    if relleno < 8:
        raise ValueError("La llave RSA es demasiado corta para SHA1withRSA.")
    return b"\x00\x01" + b"\xff" * relleno + b"\x00" + digest_info


def firmar(llave: LlavePrivada, mensaje: bytes) -> bytes:
    """Firma determinista RSASSA-PKCS1-v1_5, como openssl dgst -sha1 -sign."""
    if not isinstance(llave, LlavePrivada):
        raise ValueError("Se requiere una llave privada RSA parseada.")
    largo = _validar_publica(llave.modulo, llave.exponente)
    bloque = _emsa(mensaje, largo)
    firma = pow(int.from_bytes(bloque, "big"), llave.d, llave.modulo)
    resultado = firma.to_bytes(largo, "big")
    if not verificar(llave.modulo, llave.exponente, mensaje, resultado):
        raise ValueError("La llave privada RSA no produce una firma válida con su llave pública.")
    return resultado


def verificar(modulo: int, exponente: int, mensaje: bytes, firma: bytes) -> bool:
    """Compara el bloque EMSA completo; entradas mal formadas devuelven False."""
    try:
        largo = _validar_publica(modulo, exponente)
        if not isinstance(firma, bytes) or len(firma) != largo:
            return False
        entero = int.from_bytes(firma, "big")
        if entero >= modulo:
            return False
        obtenido = pow(entero, exponente, modulo).to_bytes(largo, "big")
        return obtenido == _emsa(mensaje, largo)
    except (ValueError, TypeError):
        return False
