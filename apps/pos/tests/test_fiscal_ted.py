"""CAF ficticio y llave pública de prueba, sin red ni documentos tributarios reales.

Ejecutar desde la raíz: .venv/Scripts/python -m pytest apps/pos/tests/test_fiscal_ted.py -q
La llave y los nombres de este archivo son SOLO para pruebas.
"""

import base64
import re
import xml.etree.ElementTree as ET
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from apps.pos.fiscal.caf import leer_caf
from apps.pos.fiscal.rsa import firmar, leer_privada, verificar
from apps.pos.fiscal.ted import generar_ted


# Obtenidos de publica_caf_prueba.pem con openssl rsa -pubin -text -noout.
# No se deriva la pública de la privada bajo prueba.
MODULO = int(
    "E04BDF578AFB0D1CDBDCC8EF6DDB4784F09A040580EEE401A67792C41C862862B503"
    "4392E9AFC54239C166C2A994C3676DDEFB51995D39A31B569B2BE0BFA755467A64"
    "E76C720A9C00CE5F55268EA54D9D9038A29CD8099502A92524C0860E3E8673519"
    "A1EF39EDE8533E631676A2A293F7BD8F0021B13F8A491AD7717F509CD", 16,
)
EXPONENTE = 65537
MENSAJE_REFERENCIA = b"Caja Clara: prueba RSA-SHA1 para TED, fase 1."
# Calculada con OpenSSL 3.5.7, sin salto de línea al final del mensaje:
# printf '%s' 'Caja Clara: prueba RSA-SHA1 para TED, fase 1.' | \
#   openssl dgst -sha1 -sign apps/pos/tests/datos_fiscales/llave_caf_prueba.pem | \
#   openssl base64 -A
FIRMA_OPENSSL = (
    "HAaYvdTybhP6b1vExsWvnRxyINua65thnWtFG+bfwb8aR5cHIkMsAd0Nxc1nfO5k"
    "EbVnlgwN625yNIR5h33Bq/1Gl+YFgEfcoqMdP2vDuNWG1zlU4gPm/q8zmW4zPKX7"
    "Xuw0jgKl5w/T4WHzH7QXJ4cTLlfdYwT82ZE89F3zNa8="
)


def _archivo(nombre):
    carpeta = __file__.replace("\\", "/").rsplit("/", 1)[0]
    with open(carpeta + "/datos_fiscales/" + nombre, "rb") as archivo:
        return archivo.read().decode("ascii")


def _b64_entero(entero):
    return base64.b64encode(entero.to_bytes((entero.bit_length() + 7) // 8, "big")).decode("ascii")


def _tlv(tag, contenido):
    largo = len(contenido)
    if largo < 128:
        longitud = bytes([largo])
    else:
        representacion = largo.to_bytes((largo.bit_length() + 7) // 8, "big")
        longitud = bytes([0x80 | len(representacion)]) + representacion
    return bytes([tag]) + longitud + contenido


def _integer(entero):
    datos = entero.to_bytes(max(1, (entero.bit_length() + 7) // 8), "big")
    if datos[0] & 0x80:
        datos = b"\x00" + datos
    return _tlv(2, datos)


def _pem_der(der):
    return ("-----BEGIN RSA PRIVATE KEY-----\n" + base64.b64encode(der).decode("ascii")
            + "\n-----END RSA PRIVATE KEY-----\n")


@pytest.fixture(scope="module")
def pem():
    return _archivo("llave_caf_prueba.pem")


@pytest.fixture(scope="module")
def llave(pem):
    return leer_privada(pem)


@pytest.fixture(scope="module")
def xml_caf(pem):
    # FRMA es base64 de 'FRMA SOLO DE PRUEBA', NO una firma del SII.
    return (
        '<?xml version="1.0" encoding="ISO-8859-1"?>\r\n<AUTORIZACION>\r\n'
        '<CAF version="1.0">\r\n  <DA>\r\n'
        '    <RE>76123456-0</RE><RS>LOCAL DE PRUEBA SPA</RS><TD>39</TD>\r\n'
        '    <RNG><D>1</D><H>100</H></RNG><FA>2026-09-23</FA>\r\n'
        f'    <RSAPK><M>{_b64_entero(MODULO)}</M><E>{_b64_entero(EXPONENTE)}</E></RSAPK>\r\n'
        '    <IDK>100</IDK>\r\n  </DA>\r\n'
        '  <FRMA algoritmo="SHA1withRSA">RlJNQSBTT0xPIERFIFBSVUVCQQ==</FRMA>\r\n'
        '</CAF>\r\n<RSASK>' + pem + '</RSASK>\r\n<RSAPUBK>'
        + _archivo("publica_caf_prueba.pem") + '</RSAPUBK>\r\n</AUTORIZACION>'
    )


@pytest.fixture(scope="module")
def caf(xml_caf):
    return leer_caf(xml_caf, tipo_documento=39)


def _timbrar(caf, **cambios):
    datos = dict(tipo_documento=39, folio=7, fecha_emision="2026-09-23",
                 rut_receptor="11111111-1", razon_social_receptor="CLIENTE DE PRUEBA",
                 monto_total=2500, primer_item="Café de prueba", timestamp="2026-09-23T15:04:05")
    datos.update(cambios)
    return generar_ted(caf, **datos)


def test_publica_de_archivo_corresponde_a_la_referencia():
    pem_publica = _archivo("publica_caf_prueba.pem")
    der = base64.b64decode("".join(pem_publica.splitlines()[1:-1]))
    rsa_publica = _tlv(0x30, _integer(MODULO) + _integer(EXPONENTE))
    # SubjectPublicKeyInfo: rsaEncryption + NULL, BIT STRING sin bits sobrantes.
    algoritmo = bytes.fromhex("300d06092a864886f70d0101010500")
    assert der == _tlv(0x30, algoritmo + _tlv(3, b"\x00" + rsa_publica))


@pytest.mark.parametrize("envoltura", ["texto", "bytes", "base64", "base64_bytes"])
def test_lee_caf(xml_caf, envoltura):
    entrada = xml_caf
    if envoltura != "texto":
        entrada = xml_caf.encode("iso-8859-1")
    if envoltura.startswith("base64"):
        entrada = base64.b64encode(entrada)
        if envoltura == "base64":
            entrada = entrada.decode("ascii")
    resultado = leer_caf(entrada, 39)
    assert resultado.rut_emisor == "76123456-0"
    assert resultado.razon_social == "LOCAL DE PRUEBA SPA"
    assert resultado.tipo_documento == 39
    assert (resultado.desde, resultado.hasta) == (1, 100)
    assert resultado.fecha_autorizacion == date(2026, 9, 23)
    assert (resultado.modulo, resultado.exponente) == (MODULO, EXPONENTE)
    assert resultado.llave_privada.modulo == MODULO
    assert resultado.xml == xml_caf[xml_caf.index("<CAF "):xml_caf.index("</CAF>") + 6]
    assert "RSASK" not in resultado.xml


def test_caf_y_llave_inmutables_sin_secretos_en_repr(caf):
    with pytest.raises(FrozenInstanceError):
        caf.desde = 9
    with pytest.raises(FrozenInstanceError):
        caf.llave_privada.d = 1
    assert str(caf.llave_privada.d) not in repr(caf.llave_privada)
    assert "llave_privada=" not in repr(caf)


@pytest.mark.parametrize("encoding", ["UTF-8", "ISO-8859-1"])
@pytest.mark.parametrize("en_base64", [False, True])
def test_caf_codificacion_y_fragmento_exacto(xml_caf, encoding, en_base64):
    texto = xml_caf.replace("ISO-8859-1", encoding).replace(
        "LOCAL DE PRUEBA SPA", "CAFÉ &amp; NIÑOS &quot;PRUEBA&quot;"
    ).replace('<CAF version="1.0">', "<CAF version='1.0'>")
    entrada = texto.encode(encoding)
    if en_base64:
        entrada = base64.b64encode(entrada)
    resultado = leer_caf(entrada, 39)
    assert resultado.razon_social == 'CAFÉ & NIÑOS "PRUEBA"'
    assert "&amp;" in resultado.xml and "&quot;" in resultado.xml
    assert resultado.xml.startswith("<CAF version='1.0'>")
    assert "\r\n" in resultado.xml
    assert resultado.xml in _timbrar(resultado).xml


@pytest.mark.parametrize("campo,valor", [("M", MODULO + 2), ("E", 3)])
def test_rechaza_par_de_llaves_distinto(xml_caf, campo, valor):
    alterado = re.sub(f"<{campo}>.*?</{campo}>", f"<{campo}>{_b64_entero(valor)}</{campo}>", xml_caf)
    with pytest.raises(ValueError, match="no corresponde.*RSAPK"):
        leer_caf(alterado, 39)


def test_rechaza_tipo_caf_equivocado(xml_caf):
    with pytest.raises(ValueError, match="tipo de documento"):
        leer_caf(xml_caf, 41)


@pytest.mark.parametrize("antes,despues,error", [
    ("<D>1</D>", "<D>101</D>", "rango"),
    ("<D>1</D>", "<D>0</D>", "entero"),
    ("<H>100</H>", "<H>-1</H>", "entero"),
    ("<TD>39</TD>", "<TD>39.0</TD>", "entero"),
    ("2026-09-23", "2026-02-30", "fecha"),
    ("2026-09-23", "20260923", "fecha"),
    ('version="1.0">\r\n  <DA>', 'version="2.0">\r\n  <DA>', "versión"),
    ("<IDK>100</IDK>", "", "Estructura"),
    ("<TD>39</TD>", "<TD>39</TD><TD>39</TD>", "Estructura"),
    ("</CAF>", "<RSASK>secreto</RSASK></CAF>", "Estructura"),
    ("<RE>76123456-0</RE>", "<RE><CAF>oculto</CAF></RE>", "Estructura"),
    ("<E>AQAB</E>", "<E>!!!</E>", "base64"),
    ("</AUTORIZACION>", "", "XML mal formado"),
])
def test_rechaza_caf_mal_formado(xml_caf, antes, despues, error):
    assert antes in xml_caf
    with pytest.raises(ValueError, match=error):
        leer_caf(xml_caf.replace(antes, despues), 39)


# Con ids cortos: pytest pone el nombre del caso en una variable de entorno, y en
# Windows una de más de 32.767 caracteres revienta antes de correr la prueba.
@pytest.mark.parametrize("entrada", ["", "%%%", "a" * (1024 * 1024 + 1), b"\xff", None],
                         ids=["vacio", "basura", "demasiado_grande", "bytes_invalidos", "none"])
def test_rechaza_entrada_caf_invalida(entrada):
    with pytest.raises(ValueError):
        leer_caf(entrada, 39)


@pytest.mark.parametrize("agregado", [
    '<!DOCTYPE AUTORIZACION [<!ENTITY nombre "otro">]>',
    '<!-- <CAF version="1.0">falso</CAF> -->',
    '<?instruccion falsa?>',
])
def test_rechaza_declaraciones_ambiguas(xml_caf, agregado):
    with pytest.raises(ValueError, match="no admite"):
        leer_caf(xml_caf.replace("<AUTORIZACION>", agregado + "<AUTORIZACION>"), 39)


def test_frma_no_se_valida_como_firma_sii(xml_caf):
    assert leer_caf(xml_caf.replace("RlJNQSBTT0xPIERFIFBSVUVCQQ==", "FRMA-DE-PRUEBA"), 39)


@pytest.mark.parametrize("folio", [0, 101, -1, True, 1.5])
def test_rechaza_folio_fuera_del_rango(caf, folio):
    with pytest.raises(ValueError, match="folio.*rango"):
        _timbrar(caf, folio=folio)


@pytest.mark.parametrize("folio", [1, 100])
def test_acepta_extremos_del_rango(caf, folio):
    assert ET.fromstring(_timbrar(caf, folio=folio).xml).findtext("DD/F") == str(folio)


def test_rechaza_tipo_ted_distinto(caf):
    with pytest.raises(ValueError, match="tipo de documento"):
        _timbrar(caf, tipo_documento=41)


def test_campos_orden_largos_escape_y_base64(caf):
    item = 'Café ñ & <pan> "doble" \'rico\' ' + "x" * 50
    receptor = 'Señora & "Prueba" ' + "y" * 50
    ted = _timbrar(caf, primer_item=item, razon_social_receptor=receptor)
    raiz = ET.fromstring(ted.xml)
    assert raiz.tag == "TED" and raiz.attrib == {"version": "1.0"}
    assert [e.tag for e in raiz] == ["DD", "FRMT"]
    dd = raiz.find("DD")
    assert [e.tag for e in dd] == ["RE", "TD", "F", "FE", "RR", "RSR", "MNT", "IT1", "CAF", "TSTED"]
    assert {e.tag: e.text for e in dd if e.tag != "CAF"} == {
        "RE": "76123456-0", "TD": "39", "F": "7", "FE": "2026-09-23",
        "RR": "11111111-1", "RSR": receptor[:40], "MNT": "2500", "IT1": item[:40],
        "TSTED": "2026-09-23T15:04:05",
    }
    assert 'Café ñ &amp; &lt;pan&gt; &quot;doble&quot; &apos;rico&apos;' in ted.xml
    assert caf.xml in ted.xml
    assert "RSASK" not in ted.xml and "PRIVATE KEY" not in ted.xml and "RSAPUBK" not in ted.xml
    assert raiz.find("FRMT").attrib == {"algoritmo": "SHA1withRSA"}
    assert base64.b64decode(ted.ted64, validate=True) == ted.xml.encode("iso-8859-1")
    assert base64.b64decode(ted.ted64).decode("iso-8859-1") == ted.xml
    assert b"Caf\xe9" in base64.b64decode(ted.ted64)


def test_firma_ted_verifica_y_es_determinista(caf):
    ted = _timbrar(caf)
    assert ted == _timbrar(caf)
    # No usamos ET.tostring ni el normalizador de producción como oráculo.
    esperado = (
        '<DD><RE>76123456-0</RE><TD>39</TD><F>7</F><FE>2026-09-23</FE>'
        '<RR>11111111-1</RR><RSR>CLIENTE DE PRUEBA</RSR><MNT>2500</MNT>'
        '<IT1>Café de prueba</IT1>'
        + caf.xml.replace("\r\n", "").replace(">  <", "><").replace(">    <", "><")
        + '<TSTED>2026-09-23T15:04:05</TSTED></DD>'
    ).encode("iso-8859-1")
    firma = base64.b64decode(ET.fromstring(ted.xml).findtext("FRMT"), validate=True)
    assert verificar(MODULO, EXPONENTE, esperado, firma)
    assert not verificar(MODULO, EXPONENTE, esperado.replace(b"2500", b"2501"), firma)
    assert _timbrar(caf, timestamp="2026-09-23T15:04:06") != ted


def test_conserva_blancos_terminales_al_firmar(xml_caf):
    # M admite base64 partido en líneas; esos blancos NO se quitan del digest.
    texto = xml_caf.replace("<M>", "<M>\r\n ").replace("</M>", " \r\n</M>")
    caf = leer_caf(texto, 39)
    ted = _timbrar(caf, primer_item="  Café  con  leche  ")
    dd = ted.xml.split("<DD>", 1)[1].split("</DD>", 1)[0]
    esperado = re.sub(r">[ \t\r\n]+<", "><", "<DD>" + dd + "</DD>")
    assert "<M>\r\n " in esperado and " \r\n</M>" in esperado
    assert "<IT1>  Café  con  leche  </IT1>" in esperado
    firma = base64.b64decode(ET.fromstring(ted.xml).findtext("FRMT"))
    assert verificar(MODULO, EXPONENTE, esperado.encode("iso-8859-1"), firma)


@pytest.mark.parametrize("cambios,error", [
    ({"monto_total": 25.5}, "entero"), ({"monto_total": -1}, "entero"),
    ({"monto_total": True}, "entero"), ({"fecha_emision": "2026-02-30"}, "FE"),
    ({"timestamp": "2026-09-23T25:00:00"}, "TSTED"),
    ({"timestamp": "2026-09-23T15:04:05Z"}, "TSTED"),
    ({"fecha_emision": "20260923"}, "FE"),
    ({"primer_item": "Café ☕"}, "ISO-8859-1"),
    ({"razon_social_receptor": "Cliente 😀"}, "ISO-8859-1"),
    ({"primer_item": "a\x00b"}, "control"), ({"primer_item": "a\rb"}, "control"),
    ({"primer_item": ""}, "no vacío"), ({"rut_receptor": "1&2"}, "RUT"),
    ({"primer_item": " " * 40 + "Café"}, "queda vacío"),
])
def test_rechaza_datos_ted_invalidos(caf, cambios, error):
    with pytest.raises(ValueError, match=error):
        _timbrar(caf, **cambios)


def test_firma_coincide_con_openssl(llave):
    assert base64.b64encode(firmar(llave, MENSAJE_REFERENCIA)).decode("ascii") == FIRMA_OPENSSL
    assert verificar(MODULO, EXPONENTE, MENSAJE_REFERENCIA, base64.b64decode(FIRMA_OPENSSL))
    assert firmar(llave, MENSAJE_REFERENCIA) == firmar(llave, MENSAJE_REFERENCIA)


def test_verificacion_rechaza_firmas_y_publicas_mal_formadas(llave):
    firma = firmar(llave, MENSAJE_REFERENCIA)
    for rota in (b"", firma[:-1], b"\x00" + firma, b"\x00" * 128,
                 MODULO.to_bytes(128, "big"), bytes([firma[0] ^ 1]) + firma[1:], None):
        assert not verificar(MODULO, EXPONENTE, MENSAJE_REFERENCIA, rota)
    for n, e in ((3, 3), (MODULO, 1), (MODULO, 2), (MODULO + 1, EXPONENTE),
                 (1 << 8192, EXPONENTE), (MODULO, MODULO), (True, EXPONENTE)):
        assert not verificar(n, e, MENSAJE_REFERENCIA, firma)
    assert not verificar(MODULO, EXPONENTE, "no son bytes", firma)


def test_verificacion_exige_todo_el_relleno_pkcs1(llave):
    firma = base64.b64decode(FIRMA_OPENSSL)
    bloque = pow(int.from_bytes(firma, "big"), EXPONENTE, MODULO).to_bytes(128, "big")
    # Aun con hash correcto y firma RSA, un byte de relleno distinto debe fallar.
    roto = bloque[:10] + b"\xfe" + bloque[11:]
    firma_rota = pow(int.from_bytes(roto, "big"), llave.d, MODULO).to_bytes(128, "big")
    assert not verificar(MODULO, EXPONENTE, MENSAJE_REFERENCIA, firma_rota)


@pytest.mark.parametrize("der", [
    b"", b"\x31\x00", b"\x30\x80\x00\x00", b"\x30\x81\x00",
    b"\x30\x82\x00\x80" + b"\x00" * 128, b"\x30\x82\x01", b"\x30\x03\x02\x01",
    b"\x30\x02\x02\x00", b"\x30\x03\x02\x01\x80",
    b"\x30\x04\x02\x02\x00\x01", b"\x30\x00\x00",
    b"\x30\x03\x03\x01\x00",
])
def test_der_estricto(der):
    with pytest.raises(ValueError, match="DER"):
        leer_privada(_pem_der(der))


def test_rechaza_version_campos_sobrantes_y_componentes_inconsistentes(llave):
    valores = [0, llave.modulo, llave.exponente, llave.d, llave.p, llave.q, llave.dp, llave.dq, llave.q_inv]
    assert leer_privada(_pem_der(_tlv(0x30, b"".join(map(_integer, valores))))) == llave
    variantes = [valores + [1], valores[:-1]]
    for indice in range(9):
        copia = valores.copy()
        copia[indice] += 1
        variantes.append(copia)
    for variante in variantes:
        with pytest.raises(ValueError):
            leer_privada(_pem_der(_tlv(0x30, b"".join(map(_integer, variante)))))


def test_rechaza_pem_invalido(pem):
    for invalido in (pem.replace("RSA PRIVATE KEY", "PRIVATE KEY"),
                     pem.replace("RSA PRIVATE KEY", "ENCRYPTED PRIVATE KEY"),
                     pem + "basura", pem + pem, pem.replace("\n", "\n!", 1),
                     "", "x" * 20001, b"\xff", None):
        with pytest.raises(ValueError):
            leer_privada(invalido)
