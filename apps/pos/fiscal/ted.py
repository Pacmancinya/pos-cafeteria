"""Timbre local de boleta; el llamador entrega fecha/hora y folio ya reservado.

Anexo 2: https://www.sii.cl/servicios_online/docs/instructivo_emision.pdf
No altera el CAF ni serializa nuevamente un TED firmado.
"""

import base64
import re
from dataclasses import dataclass
from datetime import date, datetime

from .caf import CAF
from .rsa import firmar


@dataclass(frozen=True)
class TED:
    xml: str
    ted64: str


def _contenido(valor: str, campo: str, maximo: int | None = None) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"El campo {campo} del TED debe ser texto no vacío.")
    # No sustituimos caracteres ni normalizamos silenciosamente saltos de
    # línea (XML normaliza CR). Se validan incluso los caracteres truncados.
    if any(ord(c) < 32 for c in valor):
        raise ValueError(f"El campo {campo} del TED no admite caracteres de control.")
    try:
        valor.encode("iso-8859-1")
    except UnicodeEncodeError:
        raise ValueError(f"El campo {campo} del TED contiene caracteres fuera de ISO-8859-1.") from None
    if maximo is not None:
        valor = valor[:maximo]
        if not valor.strip():
            raise ValueError(f"El campo {campo} del TED queda vacío al limitarlo a {maximo} caracteres.")
    return (valor.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def _fecha(valor: str, campo: str, con_hora: bool = False) -> str:
    patron = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    if con_hora:
        patron += r"T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    try:
        if not isinstance(valor, str) or not re.fullmatch(patron, valor):
            raise ValueError
        (datetime if con_hora else date).fromisoformat(valor)
    except ValueError:
        formato = "AAAA-MM-DDTHH:MM:SS" if con_hora else "AAAA-MM-DD"
        raise ValueError(f"El campo {campo} del TED debe ser una fecha válida en formato {formato}.") from None
    return valor


def _bytes_para_firma(dd: str) -> bytes:
    # Instructivo SII, anexo 2: se conserva el CAF en el XML entregado pero
    # para el digest se quitan blancos ENTRE etiquetas, nunca en hojas como M.
    # El parser CAF rechaza namespaces; aquí no hay que quitarlos.
    compacto = re.sub(r">[ \t\r\n]+<", "><", dd)
    try:
        return compacto.encode("iso-8859-1")
    except UnicodeEncodeError:
        raise ValueError("El CAF contiene caracteres fuera de ISO-8859-1 y no puede timbrarse.") from None


def generar_ted(caf: CAF, *, tipo_documento: int, folio: int,
                fecha_emision: str, rut_receptor: str, razon_social_receptor: str,
                monto_total: int, primer_item: str, timestamp: str) -> TED:
    """Devuelve XML y ted64; fechas explícitas, monto en pesos enteros.

    El timestamp es hora local ya resuelta por el llamador, sin zona ni
    fracciones. Se exige receptor explícito: no se inventa uno genérico.
    RSR/IT1 se truncan a 40 caracteres ANTES de escapar XML.
    sin verificar: aceptación final de ted64 por Lioren y XSD de boleta
    vigente; fuentes: docs/BOLETA-ETAPA1-LIOREN.md y https://www.lioren.cl/docs.
    """
    if not isinstance(caf, CAF):
        raise ValueError("Se requiere un CAF previamente leído y validado.")
    if type(tipo_documento) is not int or tipo_documento != caf.tipo_documento:
        raise ValueError("El tipo de documento del TED no coincide con el CAF.")
    if tipo_documento not in (39, 41):
        raise ValueError("El TED de boleta requiere tipo de documento 39 o 41.")
    if type(folio) is not int or not caf.desde <= folio <= caf.hasta:
        raise ValueError(f"El folio debe estar dentro del rango del CAF ({caf.desde} a {caf.hasta}).")
    if type(monto_total) is not int or monto_total < 0:
        raise ValueError("El monto total del TED debe ser un entero no negativo en pesos.")
    if not isinstance(rut_receptor, str) or not re.fullmatch(r"[0-9]{1,8}-[0-9Kk]", rut_receptor):
        raise ValueError("El RUT receptor debe tener formato sin puntos y con guion.")
    campos = (
        ("RE", _contenido(caf.rut_emisor, "RE")),
        ("TD", str(tipo_documento)),
        ("F", str(folio)),
        ("FE", _fecha(fecha_emision, "FE")),
        ("RR", _contenido(rut_receptor, "RR")),
        ("RSR", _contenido(razon_social_receptor, "RSR", 40)),
        ("MNT", str(monto_total)),
        ("IT1", _contenido(primer_item, "IT1", 40)),
    )
    dd = ("<DD>" + "".join(f"<{tag}>{valor}</{tag}>" for tag, valor in campos)
          + caf.xml + "<TSTED>" + _fecha(timestamp, "TSTED", con_hora=True) + "</TSTED></DD>")
    firma = base64.b64encode(firmar(caf.llave_privada, _bytes_para_firma(dd))).decode("ascii")
    xml = '<TED version="1.0">' + dd + '<FRMT algoritmo="SHA1withRSA">' + firma + "</FRMT></TED>"
    return TED(xml, base64.b64encode(xml.encode("iso-8859-1")).decode("ascii"))
