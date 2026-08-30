"""El escáner: del número del código de barras a un producto.

Lo que se prueba acá no es "el escáner funciona": es que el escáner no pueda
ensuciar el catálogo. Un código mal leído o un código de balanza que se cuele
como producto nuevo significa productos fantasma en la carta de un almacén, y
eso no lo arregla nadie después.
"""
import pytest

from core import codigos as k


# ------------------------------------------------------------ la aritmética
@pytest.mark.parametrize("codigo", [
    "7801610001196",   # Coca-Cola 350 ml, chilena
    "7802920777542",   # Leche Colún 1 L
    "96385074",        # EAN-8
    "012000161155",    # UPC-A gringo
])
def test_los_codigos_de_verdad_pasan(codigo):
    assert k.es_valido(codigo)


def test_un_digito_cambiado_no_pasa():
    """Una etiqueta arrugada devuelve dígitos cambiados. Si eso pasara, se
    crearía un producto fantasma con el código de otro."""
    assert not k.es_valido("7801610001197")


def test_el_upc_gringo_se_guarda_como_ean13():
    """Un UPC-A de 12 ES un EAN-13 con un cero adelante. Guardarlos distinto
    deja el mismo producto dos veces según qué lector lo leyó."""
    assert k.normalizar("012000161155") == "0012000161155"
    assert len(k.normalizar("012000161155")) == 13


def test_el_ean8_no_se_rellena_con_ceros():
    """Rellenarlo daría OTRO número, no el mismo producto."""
    assert k.normalizar("96385074") == "96385074"


def test_la_suma_que_termina_en_cero_da_verificador_cero():
    """El error clásico de esta cuenta: sin el módulo de afuera, daría 10."""
    assert k.digito_verificador("4006381333") in range(10)
    assert 0 <= k.digito_verificador("00000000000") <= 9


# ------------------------------------------- los códigos que NO son productos
def test_el_codigo_de_la_balanza_se_reconoce_y_se_niega():
    """El pan pesado: el código lleva el peso adentro y CAMBIA con cada trozo.
    Si se guardara, habría un producto nuevo por cada pan vendido."""
    base = "200123403500"
    bal = base + str(k.digito_verificador(base))
    assert k.es_valido(bal)          # la balanza calcula bien su verificador
    assert k.es_de_balanza(bal)
    assert "balanza" in k.por_que_no_sirve(bal)

    otro_peso = "200123404200"
    otro = otro_peso + str(k.digito_verificador(otro_peso))
    assert otro != bal               # el MISMO pan, otro número


def test_el_codigo_de_la_caja_se_distingue_del_de_la_unidad():
    caja = "1780161000119" + str(k.digito_verificador("1780161000119"))
    assert k.es_una_caja(caja)
    assert "CAJA" in k.por_que_no_sirve(caja)


def test_lo_que_sirve_no_tiene_pero():
    assert k.por_que_no_sirve("7801610001196") == ""


# ------------------------------------------------------------------- la API
def test_escanear_un_codigo_desconocido_dice_que_se_puede_guardar(cliente, carta):
    r = cliente.get("/api/v1/codigos/7801610001196").json()
    assert r["encontrado"] is False
    assert r["se_puede_guardar"] is True


def test_escanear_un_codigo_de_balanza_dice_que_NO(cliente, carta):
    base = "200123403500"
    bal = base + str(k.digito_verificador(base))
    r = cliente.get(f"/api/v1/codigos/{bal}").json()
    assert r["encontrado"] is False
    assert r["se_puede_guardar"] is False
    assert r["de_balanza"] is True


def test_un_producto_creado_con_codigo_se_encuentra_al_escanearlo(cliente, carta):
    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Coca-Cola 350",
        "precio": 1200, "codigo": "7801610001196"}).json()
    r = cliente.get("/api/v1/codigos/7801610001196").json()
    assert r["encontrado"] is True
    assert r["producto"]["id"] == p["id"]
    assert r["cuantos"] == 1


def test_el_mismo_codigo_no_puede_ser_de_dos_productos(cliente, carta):
    cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Uno",
        "precio": 1000, "codigo": "7801610001196"})
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Otro",
        "precio": 1000, "codigo": "7801610001196"})
    assert r.status_code == 409


def test_un_codigo_mal_leido_no_crea_producto(cliente, carta):
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Fantasma",
        "precio": 1000, "codigo": "7801610001197"})
    assert r.status_code == 422
    assert "mal leído" in r.json()["detail"]


def test_el_pack_de_seis_entrega_seis(cliente, carta):
    """La lata suelta y el pack traen códigos distintos y son el mismo trago."""
    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Cerveza",
        "precio": 1500, "codigo": "7801610001196"}).json()
    pack = "780161000120" + str(k.digito_verificador("780161000120"))
    assert cliente.post(f"/api/v1/productos/{p['id']}/codigos", json={
        "codigo": pack, "cuantos": 6, "nota": "pack de 6"}).status_code == 200

    r = cliente.get(f"/api/v1/codigos/{pack}").json()
    assert r["encontrado"] is True
    assert r["producto"]["id"] == p["id"]
    assert r["cuantos"] == 6


# ------------------------------------------- el nombre que llega de afuera
@pytest.mark.parametrize("nombre,marca,cuanto,esperado", [
    # Open Food Facts los guarda por separado y sueltos no sirven.
    ("Tradición", "Nescafé", "170g", "Nescafé Tradición 170g"),
    ("Leche Entera", "Colun", "1 l", "Colun Leche Entera 1 l"),
    # La marca no se repite cuando ya está en el nombre.
    ("Coca-Cola", "Coca-Cola", "350 ml", "Coca-Cola 350 ml"),
    # Ni el contenido, si el nombre ya lo dice.
    ("Jurel 425g", "San José", "425 g", "San José Jurel 425g"),
    # Sin nada útil, no se inventa nada.
    ("", "", "", ""),
])
def test_el_nombre_sugerido_se_arma_como_lo_escribiria_una_persona(
        nombre, marca, cuanto, esperado):
    """«Tradición» sola no le dice nada a nadie parado frente a la caja: la
    marca va adelante y no es un adorno."""
    from apps.pos.api.codigos import _como_lo_escribiria_una_persona as armar
    assert armar(nombre, marca, cuanto) == esperado


def test_el_nombre_nunca_se_pierde():
    """El bug que tuvo esto: un texto siempre se contiene a sí mismo, así que la
    comprobación de «ya está incluido» descartaba SIEMPRE el nombre y devolvía
    solo el contenido — «1 l» en vez de «Colun Leche Entera 1 l»."""
    from apps.pos.api.codigos import _como_lo_escribiria_una_persona as armar
    assert "Leche Entera" in armar("Leche Entera", "Colun", "1 l")
