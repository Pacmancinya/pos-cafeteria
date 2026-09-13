"""El escáner: del número del código de barras a un producto.

Lo que se prueba acá no es "el escáner funciona": es que el escáner no pueda
ensuciar el catálogo. Un código mal leído o un código de balanza que se cuele
como producto nuevo significa productos fantasma en la carta de un almacén, y
eso no lo arregla nadie después.
"""
import json
from decimal import Decimal

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


# ------------------------------------------------ el ticket de la balanza del local
def test_lee_el_ticket_y_el_total_de_una_etiqueta_real():
    """Etiqueta medida en el local: ticket RCT# 3976, TOTAL $197.

    Es la de verdad, no una inventada: si alguien cambia el reparto de los dígitos, este
    test lo caza con el caso que existe en el mostrador.
    """
    assert k.leer_balanza("2539760001975") == {"modo": "ticket", "ticket": "3976", "total": 197}


def test_el_codigo_de_la_balanza_no_dice_que_producto_es():
    """No hay producto ni peso adentro: identifica un TICKET, no una mercadería.

    De ahí que `por_que_no_sirve` siga negándose a guardarlo como código de un producto:
    son dos usos distintos del mismo número y los dos tienen razón.
    """
    leido = k.leer_balanza("2539760001975")
    assert set(leido) == {"modo", "ticket", "total"}
    assert k.por_que_no_sirve("2539760001975")


def test_un_codigo_normal_no_es_un_ticket_de_balanza():
    assert k.leer_balanza("7801610001196") is None


def test_un_codigo_mal_leido_no_inventa_un_monto():
    assert k.leer_balanza("2539760001974") is None    # verificador cambiado
    assert k.leer_balanza("253976000197") is None     # le falta un dígito
    assert k.leer_balanza("") is None


def test_el_reparto_de_digitos_se_puede_cambiar_por_balanza():
    otro = {"prefijo": "25", "ticket": (2, 7), "total": (7, 12)}
    assert k.leer_balanza("2539760001975", otro) == {"modo": "ticket", "ticket": "39760", "total": 197}


def _etiqueta(base):
    return base + str(k.digito_verificador(base))


@pytest.mark.parametrize("modo", ["ticket", "plu_peso", "plu_precio"])
def test_modos_con_prefijo_y_posiciones_distintos(modo):
    formato = {"modo": modo, "prefijo": "291", "codigo": [8, 12],
               "valor": [3, 8], "divisor_peso": 100}
    leido = k.leer_balanza(_etiqueta("291001230007"), formato)
    esperado = {"modo": modo}
    if modo == "ticket":
        esperado.update(ticket="7", total=123)
    elif modo == "plu_precio":
        esperado.update(plu="0007", total=123)
    else:
        esperado.update(plu="0007", peso_kg=Decimal("1.23"))
        assert isinstance(leido["peso_kg"], Decimal)
    assert leido == esperado
    assert k.leer_balanza(_etiqueta("292001230007"), formato) is None
    valido = _etiqueta("291001230007")
    # Estos NO se pueden leer: o no tienen 13 dígitos, o el verificador no calza.
    for malo in (valido[:-1], valido + "0",
                 valido[:-1] + str((int(valido[-1]) + 1) % 10),
                 valido.replace("2", "２"),        # dígito de otro alfabeto: se descarta
                 None, 291001230007):
        assert k.leer_balanza(malo, formato) is None, repr(malo)
    # Y estos SÍ, porque el ruido que mete el lector no cambia ningún dígito y el
    # verificador sigue calzando. Es la misma regla que usan es_valido y normalizar
    # desde siempre: limpiar y dejar que el dígito de control haga de guardia.
    for con_ruido in (" " + valido, valido + chr(13), valido[:5] + "-" + valido[5:]):
        assert k.leer_balanza(con_ruido, formato) is not None, repr(con_ruido)


FORMATOS_ROTOS = [
    None, [], "texto", 1, {},
    *[{**k.FORMATO_BALANZA_POR_DEFECTO, **cambio} for cambio in [
        {"modo": "otro"}, {"modo": []}, {"prefijo": ""}, {"prefijo": 25},
        {"prefijo": "２５"}, {"prefijo": "2x"}, {"codigo": [True, 6]},
        {"codigo": [2.0, 6]}, {"codigo": ["2", 6]}, {"codigo": [2]},
        {"codigo": None}, {"codigo": [-1, 6]}, {"codigo": [1, 6]},
        {"codigo": [6, 6]}, {"codigo": [7, 6]}, {"codigo": [2, 13]},
        {"valor": [5, 12]}, {"valor": [6, 13]}, {"valor": "6,12"},
        {"divisor_peso": 0}, {"divisor_peso": -1}, {"divisor_peso": True},
        {"divisor_peso": "1000"}, {"divisor_peso": 1000.0},
    ]],
]


@pytest.mark.parametrize("formato", FORMATOS_ROTOS)
def test_formato_roto_no_tumba_lector(formato):
    assert k.leer_balanza("2539760001975", formato) == {
        "modo": "ticket", "ticket": "3976", "total": 197}


def test_peso_en_gramos_y_cero_en_ticket():
    formato = {**k.FORMATO_BALANZA_POR_DEFECTO, "modo": "plu_peso"}
    assert k.leer_balanza("2539760001975", formato)["peso_kg"] == Decimal("0.197")
    assert k.leer_balanza(_etiqueta("250000000000"))["ticket"] == "0"


def test_formato_balanza_se_guarda_como_json_y_se_recupera(cliente):
    from apps.pos.db.models import Ajuste
    from apps.pos.db.session import engine
    from sqlmodel import Session

    formato = {"modo": "plu_peso", "prefijo": "20", "codigo": [2, 7],
               "valor": [7, 12], "divisor_peso": 1000}
    assert cliente.get("/api/v1/ajustes").json()["formato_balanza"] == k.FORMATO_BALANZA_POR_DEFECTO
    r = cliente.put("/api/v1/ajustes", json={"formato_balanza": formato})
    assert r.status_code == 200
    assert r.json()["formato_balanza"] == formato
    with Session(engine) as s:
        assert json.loads(s.get(Ajuste, "formato_balanza").valor) == formato
    assert cliente.get("/api/v1/ajustes").json()["formato_balanza"] == formato
    cliente.put("/api/v1/ajustes", json={"margen_sugerido": 30})
    assert cliente.get("/api/v1/ajustes").json()["formato_balanza"] == formato


def test_formato_roto_almacenado_no_tumba_ajustes(cliente):
    from apps.pos.db.models import Ajuste
    from apps.pos.db.session import engine
    from sqlmodel import Session

    for crudo in ["{mal json", str(k.FORMATO_DIGI_SM300), "[" * 10000 + "0" + "]" * 10000,
                  *[json.dumps(f) for f in FORMATOS_ROTOS]]:
        with Session(engine) as s:
            s.merge(Ajuste(clave="formato_balanza", valor=crudo))
            s.commit()
        r = cliente.get("/api/v1/ajustes")
        assert r.status_code == 200
        assert r.json()["formato_balanza"] == k.FORMATO_BALANZA_POR_DEFECTO


def test_api_rechaza_formatos_nuevos_invalidos(cliente):
    for formato in FORMATOS_ROTOS:
        assert cliente.put("/api/v1/ajustes", json={"formato_balanza": formato}).status_code == 422
    assert cliente.get("/api/v1/ajustes").json()["formato_balanza"] == k.FORMATO_BALANZA_POR_DEFECTO


def test_api_acepta_formato_anterior_valido(cliente):
    r = cliente.put("/api/v1/ajustes", json={"formato_balanza": k.FORMATO_DIGI_SM300})
    assert r.status_code == 200
    assert r.json()["formato_balanza"] == k.FORMATO_BALANZA_POR_DEFECTO


def test_producto_guarda_plu_y_precio_kilo(cliente, carta):
    datos = {"categoria_id": carta["cafe"]["id"], "nombre": "Pan",
             "plu": "0007", "precio_kilo": 2490}
    r = cliente.post("/api/v1/productos", json=datos)
    assert r.status_code == 200
    assert r.json()["plu"] == "0007"
    assert r.json()["precio_kilo"] == 2490
    from apps.pos.db.models import Producto
    from apps.pos.db.session import engine
    from sqlmodel import Session
    with Session(engine) as s:
        producto = s.get(Producto, r.json()["id"])
        assert producto.plu == "0007"
        assert producto.precio_kilo == 2490
    assert carta["espresso"]["plu"] == ""
    assert carta["espresso"]["precio_kilo"] == 0
    for precio in (-1, 2.5, True, False, "2490", 2490.0, 2**63):
        assert cliente.post("/api/v1/productos", json={**datos, "precio_kilo": precio}).status_code == 422
        assert cliente.put(f"/api/v1/productos/{r.json()['id']}",
                           json={**datos, "precio_kilo": precio}).status_code == 422


def test_editar_producto_sin_campos_balanza_los_conserva(cliente, carta):
    datos = {"categoria_id": carta["cafe"]["id"], "nombre": "Pan",
             "plu": "0007", "precio_kilo": 2490}
    creado = cliente.post("/api/v1/productos", json=datos)
    assert creado.status_code == 200
    ruta = f"/api/v1/productos/{creado.json()['id']}"
    legacy = {"categoria_id": datos["categoria_id"], "nombre": "Pan amasado", "precio": 500}
    r = cliente.put(ruta, json=legacy)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Pan amasado"
    assert r.json()["precio"] == 500
    assert r.json()["plu"] == "0007"
    assert r.json()["precio_kilo"] == 2490
    r = cliente.put(ruta, json={**legacy, "plu": "", "precio_kilo": 0})
    assert r.status_code == 200
    assert r.json()["plu"] == ""
    assert r.json()["precio_kilo"] == 0


def test_migracion_agrega_balanza_a_producto_existente_sin_perder_datos(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    from sqlmodel import Session

    from apps.pos.db import migraciones
    from apps.pos.db.models import Categoria, Insumo, Producto, Receta

    viejo = create_engine(f"sqlite:///{tmp_path / 'local_anterior.db'}")
    monkeypatch.setattr(migraciones, "engine", viejo)
    try:
        # Es la tabla anterior a esta funcionalidad, sin usar el modelo nuevo
        # para construirla. Una columna desconocida también debe sobrevivir.
        with viejo.begin() as con:
            con.execute(text("""
                CREATE TABLE producto (
                    id INTEGER PRIMARY KEY, categoria_id INTEGER NOT NULL,
                    nombre TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
                    precio INTEGER NOT NULL DEFAULT 0, activo BOOLEAN NOT NULL DEFAULT 1,
                    orden INTEGER NOT NULL DEFAULT 0, destacado BOOLEAN NOT NULL DEFAULT 0,
                    badge TEXT NOT NULL DEFAULT '', antes INTEGER,
                    etiqueta TEXT NOT NULL DEFAULT '', dibujo TEXT NOT NULL DEFAULT 'mug',
                    color TEXT NOT NULL DEFAULT '', nota_legacy TEXT
                )
            """))
            con.execute(text("""
                INSERT INTO producto
                    (id, categoria_id, nombre, descripcion, precio, activo, orden,
                     destacado, badge, antes, etiqueta, dibujo, color, nota_legacy)
                VALUES (17, 1, 'Pan amasado', 'Receta del local', 1550, 1, 4,
                        1, 'Hoy', 1800, 'Integral', 'croissant', '#ab1234', 'conservar')
            """))
            anterior = dict(con.execute(text("SELECT * FROM producto")).mappings().one())

        # Tablas auxiliares que la migración consulta; producto sigue siendo
        # la tabla antigua. Ningún create_all agrega las columnas bajo prueba.
        for tabla in (Categoria.__table__, Insumo.__table__, Receta.__table__):
            tabla.create(viejo)
        with Session(viejo) as s:
            s.add(Categoria(id=1, nombre="Panadería"))
            s.commit()

        assert {c["name"] for c in inspect(viejo).get_columns("producto")}.isdisjoint(
            {"plu", "precio_kilo"})
        assert set(migraciones.poner_al_dia()) == {
            "producto.plu", "producto.precio_kilo", "producto.llevar_cuenta"}
        with viejo.connect() as con:
            migrado = dict(con.execute(text("SELECT * FROM producto")).mappings().one())
        assert {clave: migrado[clave] for clave in anterior} == anterior
        assert migrado["plu"] == ""
        assert migrado["precio_kilo"] == 0
        assert migrado["llevar_cuenta"] is None

        # El ORM ya puede leer y guardar el producto que existía. Volver a
        # arrancar no debe restaurar defaults sobre lo que configuró el local.
        with Session(viejo) as s:
            producto = s.get(Producto, 17)
            assert producto.nombre == anterior["nombre"]
            assert producto.precio == anterior["precio"]
            assert producto.categoria.nombre == "Panadería"
            producto.plu = "00123"
            producto.precio_kilo = 5990
            s.add(producto)
            s.commit()
        assert migraciones.poner_al_dia() == []
        with viejo.connect() as con:
            repetido = dict(con.execute(text("SELECT * FROM producto")).mappings().one())
        assert {clave: repetido[clave] for clave in anterior} == anterior
        assert repetido["plu"] == "00123"
        assert repetido["precio_kilo"] == 5990
    finally:
        viejo.dispose()


def test_la_etiqueta_se_lee_como_la_manda_el_lector():
    """Casi todos los lectores mandan un Enter al final, y algunos espacios.

    Sin quitar eso, la etiqueta de verdad no se lee y el cajero se queda mirando la
    pantalla con la fila esperando. Es el caso normal, no el raro.
    """
    esperado = {"modo": "ticket", "ticket": "3976", "total": 197}
    variantes = [
        "2539760001975",
        "2539760001975" + chr(13),      # Enter: el sufijo por defecto de casi todo lector
        "2539760001975" + chr(10),
        "2 539760 001975",              # como viene impreso bajo las barras
        " 2539760001975 ",
        "2-539760-001975",
    ]
    for tal_cual in variantes:
        assert k.leer_balanza(tal_cual) == esperado, repr(tal_cual)


def test_un_digito_de_otro_alfabeto_no_pasa_por_valido():
    """`str.isdigit()` acepta dígitos de otros alfabetos e `int()` los convierte sin chistar.

    Si se limpiaran como dígitos, un escaneo corrupto podría quedar con el largo y el
    verificador correctos y cobrarse solo. Se limpia ASCII para que eso no pueda pasar.
    """
    arabe = "25397600019" + chr(0x0667) + "5"     # ٧ arábigo-índico en medio
    assert k.limpiar(arabe) == "253976000195"     # el raro se descarta, no se traduce
    assert k.leer_balanza(arabe) is None
    assert not k.es_valido(arabe)
