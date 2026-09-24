"""Lectura local de AUTORIZACION, como XML o como su contenido en base64.

Formato: anexo 1 de https://www.sii.cl/servicios_online/docs/instructivo_emision.pdf
No consume la API ni recibe el objeto JSON de Lioren: recibe el valor del XML.
"""

import base64
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

from .rsa import LlavePrivada, firmar, leer_privada


_MAX_ENTRADA = 1024 * 1024  # Límite local, no un límite del SII.
_BLANCOS = " \t\r\n"


@dataclass(frozen=True)
class CAF:
    rut_emisor: str
    razon_social: str
    tipo_documento: int
    desde: int
    hasta: int
    fecha_autorizacion: date
    modulo: int
    exponente: int
    llave_privada: LlavePrivada = field(repr=False)
    xml: str


def _decodificar(entrada: str | bytes) -> str:
    if not isinstance(entrada, (str, bytes)) or not entrada or len(entrada) > _MAX_ENTRADA:
        raise ValueError("El CAF está vacío, no es texto/bytes o excede el tamaño permitido.")
    inicio = (entrada.lstrip(b" \t\r\n\xef\xbb\xbf") if isinstance(entrada, bytes)
              else entrada.lstrip(_BLANCOS + "\ufeff"))
    es_xml = inicio.startswith(b"<" if isinstance(inicio, bytes) else "<")
    if not es_xml:
        try:
            texto = entrada.decode("ascii") if isinstance(entrada, bytes) else entrada
            entrada = base64.b64decode(re.sub(r"[ \t\r\n]", "", texto), validate=True)
        except (ValueError, UnicodeError):
            raise ValueError("El CAF no contiene XML ni base64 válido.") from None
    if isinstance(entrada, str):
        return entrada.lstrip("\ufeff")
    # XML sin declaración usa UTF-8; no adivinamos Latin-1 si el UTF-8 falla.
    declaracion = re.match(br"(?:\xef\xbb\xbf)?<\?xml\s+[^?]*\?>", entrada)
    codificacion = "utf-8-sig"
    if declaracion:
        encoding = re.search(br"encoding\s*=\s*(['\"])([^'\"]+)\1", declaracion[0])
        if encoding:
            nombre = encoding[2].lower()
            if nombre not in (b"utf-8", b"iso-8859-1"):
                raise ValueError("El XML del CAF debe usar UTF-8 o ISO-8859-1.")
            codificacion = "utf-8-sig" if nombre == b"utf-8" else "iso-8859-1"
    try:
        return entrada.decode(codificacion)
    except UnicodeDecodeError:
        raise ValueError("La codificación del CAF no coincide con su declaración XML.") from None


def _estructura(elemento, etiquetas: tuple, atributos: tuple = ()):
    if tuple(hijo.tag for hijo in elemento) != etiquetas:
        raise ValueError(f"Estructura del CAF inválida en {elemento.tag}: campos faltantes, repetidos o fuera de orden.")
    if any(nombre not in atributos for nombre in elemento.attrib):
        raise ValueError(f"El elemento {elemento.tag} del CAF tiene atributos no admitidos.")
    if etiquetas:
        if elemento.text and elemento.text.strip(_BLANCOS):
            raise ValueError(f"El elemento {elemento.tag} del CAF contiene texto fuera de sus campos.")
        if any(hijo.tail and hijo.tail.strip(_BLANCOS) for hijo in elemento):
            raise ValueError(f"El elemento {elemento.tag} del CAF contiene texto entre campos.")


def _texto(elemento) -> str:
    _estructura(elemento, (), ("algoritmo",) if elemento.tag == "FRMA" else ())
    texto = elemento.text or ""
    if not texto.strip(_BLANCOS):
        raise ValueError(f"El campo {elemento.tag} del CAF está vacío.")
    return texto


def _entero(elemento, minimo=1) -> int:
    texto = _texto(elemento).strip(_BLANCOS)
    if not re.fullmatch(r"[0-9]{1,18}", texto) or int(texto) < minimo:
        raise ValueError(f"El campo {elemento.tag} del CAF no es un entero válido.")
    return int(texto)


def _entero_base64(elemento) -> int:
    texto = re.sub(r"[ \t\r\n]", "", _texto(elemento))
    try:
        datos = base64.b64decode(texto, validate=True)
    except ValueError:
        raise ValueError(f"El campo RSA {elemento.tag} del CAF no es base64 válido.") from None
    if not datos or len(datos) > 1025:
        raise ValueError(f"El campo RSA {elemento.tag} del CAF tiene un tamaño inválido.")
    return int.from_bytes(datos, "big")


def leer_caf(entrada: str | bytes, tipo_documento: int) -> CAF:
    """Valida estructura, tipo, rango y par RSA, preservando el fragmento CAF.

    Los errores no incluyen el XML de entrada ni el contenido de la llave.
    RSAPUBK se exige como campo externo; la pública autoritativa es DA/RSAPK.
    No verifica autenticidad, ambiente ni pertenencia a un local configurado.
    """
    if type(tipo_documento) is not int or tipo_documento <= 0:
        raise ValueError("El tipo de documento pedido debe ser un entero positivo.")
    texto = _decodificar(entrada)
    sin_declaracion = re.sub(r"\A<\?xml\s+[^?]*\?>", "", texto, count=1)
    # Perfil deliberadamente acotado: no se expanden DTD/entidades ni se
    # admiten comentarios, CDATA o instrucciones que oculten un segundo CAF.
    # sin verificar: variantes con namespaces/CDATA de CAF reales de Lioren.
    # Fuente del perfil simple: instructivo SII, anexo 1, URL del módulo.
    if "<!" in sin_declaracion or "<?" in sin_declaracion:
        raise ValueError("El CAF no admite DTD, entidades declaradas, comentarios, CDATA ni instrucciones XML.")
    try:
        raiz = ET.fromstring(texto)
    except (ET.ParseError, ValueError):
        raise ValueError("El CAF contiene XML mal formado.") from None
    if raiz.tag != "AUTORIZACION":
        raise ValueError("Se esperaba AUTORIZACION sin espacios de nombres como raíz del CAF.")
    _estructura(raiz, ("CAF", "RSASK", "RSAPUBK"))
    caf, privada, publica = raiz
    _estructura(caf, ("DA", "FRMA"), ("version",))
    if caf.get("version") != "1.0":
        raise ValueError("La versión del CAF debe ser 1.0.")
    da, frma = caf
    _estructura(da, ("RE", "RS", "TD", "RNG", "FA", "RSAPK", "IDK"))
    re_emisor, rs, td, rango, fa, rsapk, idk = da
    _estructura(rango, ("D", "H"))
    _estructura(rsapk, ("M", "E"))
    rut = _texto(re_emisor)
    if not re.fullmatch(r"[0-9]{1,8}-[0-9Kk]", rut):
        raise ValueError("El RUT emisor del CAF debe tener formato sin puntos y con guion.")
    razon = _texto(rs)
    tipo = _entero(td)
    if tipo != tipo_documento:
        raise ValueError(f"El tipo de documento del CAF ({tipo}) no coincide con el pedido ({tipo_documento}).")
    desde, hasta = _entero(rango[0]), _entero(rango[1])
    if desde > hasta:
        raise ValueError("El rango del CAF es incoherente: desde es mayor que hasta.")
    fecha_texto = _texto(fa).strip(_BLANCOS)
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fecha_texto):
            raise ValueError
        fecha = date.fromisoformat(fecha_texto)
    except ValueError:
        raise ValueError("La fecha de autorización del CAF debe ser válida y tener formato AAAA-MM-DD.") from None
    _entero(idk, minimo=0)
    _texto(frma)
    # FRMA autentica el CAF con la llave del SII, que no tenemos en esta fase.
    # NO se valida esa firma: comprobar el par RSA no acredita origen SII.
    _texto(publica)
    modulo, exponente = (_entero_base64(campo) for campo in rsapk)
    llave = leer_privada(_texto(privada))
    if (llave.modulo, llave.exponente) != (modulo, exponente):
        raise ValueError("La llave privada del CAF no corresponde al módulo y exponente de RSAPK.")
    firmar(llave, b"Validacion local del par RSA del CAF")  # Incluye verificación pública.
    # El árbol se usa solo para validar. ET.tostring cambiaría entidades,
    # comillas y finales de línea; el CAF se extrae del texto original.
    fragmento = re.search(r"<CAF\s[^<>]*>.*?</CAF\s*>", texto, re.DOTALL)
    if fragmento is None:
        raise ValueError("No se pudo conservar el fragmento XML original del CAF.")
    return CAF(rut, razon, tipo, desde, hasta, fecha, modulo, exponente, llave, fragmento[0])
