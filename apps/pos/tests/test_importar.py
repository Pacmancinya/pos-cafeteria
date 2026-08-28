"""Traer la carta que el local ya tenía.

Lo que se prueba acá es sobre todo lo que NO tiene que pasar: que un archivo
raro no ensucie la carta, que nada se escriba sin confirmar, y que importar dos
veces no duplique nada.
"""
import io
import zipfile

import pytest

from core import planilla


# ------------------------------------------------------------------ precios
@pytest.mark.parametrize("texto,esperado", [
    ("$3.500", 3500),
    ("3.500", 3500),
    ("3500", 3500),
    ("1.234.567", 1234567),
    ("12,500", 12500),
    ("3.500,00", 3500),
    ("$ 2.900 c/u", 2900),
    ("2900.5", 2900),
    # Excel guarda esto cuando la celda tenía una fórmula. Sin tratarlo aparte,
    # entra a la caja como cuarenta mil billones de pesos. Pasó de verdad.
    ("4.0365000000000005", 4),
    ("", None),
    ("Consultar", None),
    ("-500", None),
])
def test_los_precios_chilenos_se_entienden(texto, esperado):
    assert planilla.a_precio(texto) == esperado


def test_un_numero_dentro_de_un_texto_no_es_un_precio():
    """«CAFETERÍA LA ESQUINA — CARTA 2026» no vale $2.026."""
    assert planilla.parece_precio("$3.500")
    assert not planilla.parece_precio("CARTA 2026")
    assert not planilla.parece_precio("Torta 3 leches")


# ------------------------------------------------------------------ leer
CARTA = """CAFETERIA LA ESQUINA - CARTA 2026

CAFES
Espresso;$1.900;doble carga
Cortado;$2.300;
Latte;3.500;

PASTELERIA
Croissant;$2.400;
Torta de zanahoria;$4.500;porcion
Croissant;$2.400;repetido
"""


def test_las_secciones_de_la_carta_se_vuelven_categorias():
    r = planilla.interpretar(planilla.desde_texto(CARTA))
    porcategoria = {p["nombre"]: p["categoria"] for p in r["productos"]}
    assert porcategoria["Espresso"] == "CAFES"
    assert porcategoria["Croissant"] == "PASTELERIA"


def test_el_titulo_de_la_carta_no_entra_como_producto():
    r = planilla.interpretar(planilla.desde_texto(CARTA))
    assert not any("ESQUINA" in p["nombre"] for p in r["productos"])


def test_un_producto_repetido_se_avisa_y_no_se_duplica():
    r = planilla.interpretar(planilla.desde_texto(CARTA))
    assert [p["nombre"] for p in r["productos"]].count("Croissant") == 1
    assert any("más de una vez" in a for a in r["avisos"])


def test_el_dibujo_se_adivina_por_el_nombre():
    """Es mucho más rápido corregir tres dibujos que elegir cuarenta."""
    r = {p["nombre"]: p["dibujo"]
         for p in planilla.interpretar(planilla.desde_texto(CARTA))["productos"]}
    assert r["Espresso"] == "taza"
    assert r["Latte"] == "mug"
    assert r["Croissant"] == "croissant"
    assert r["Torta de zanahoria"] == "torta"


def test_con_encabezado_manda_el_encabezado():
    tabla = "Producto;Categoria;Precio\nLatte;Cafés;3400\nAlfajor;Dulces;1900\n"
    r = planilla.interpretar(planilla.desde_texto(tabla))
    assert r["columnas_detectadas"] == {"nombre": 0, "categoria": 1, "precio": 2}
    assert r["productos"][0]["categoria"] == "Cafés"


def test_se_lee_lo_pegado_con_tabulaciones():
    """Copiar y pegar desde Excel entrega columnas separadas por tabulador."""
    r = planilla.interpretar(planilla.desde_texto("Latte\t3400\nEspresso\t1900"))
    assert [(p["nombre"], p["precio"]) for p in r["productos"]] == [
        ("Latte", 3400), ("Espresso", 1900)]


def _xlsx(filas: list[list[str]]) -> bytes:
    """Un .xlsx mínimo pero de verdad, para probar el lector sin openpyxl."""
    def celda(col, fila, valor):
        letra = chr(65 + col)
        return (f'<c r="{letra}{fila}" t="inlineStr"><is><t>{valor}</t></is></c>')
    filas_xml = "".join(
        f'<row r="{i}">' + "".join(celda(j, i, v) for j, v in enumerate(f)) + "</row>"
        for i, f in enumerate(filas, start=1))
    hoja = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
            f'spreadsheetml/2006/main"><sheetData>{filas_xml}</sheetData></worksheet>')
    libro = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
             'officeDocument/2006/relationships"><sheets>'
             '<sheet name="Carta" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'worksheet"/></Relationships>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/workbook.xml", libro)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", hoja)
    return b.getvalue()


def test_se_lee_un_excel_de_verdad():
    datos = _xlsx([["Producto", "Precio"], ["Latte", "3400"], ["Alfajor", "1900"]])
    r = planilla.interpretar(planilla.leer("carta.xlsx", datos))
    assert [(p["nombre"], p["precio"]) for p in r["productos"]] == [
        ("Latte", 3400), ("Alfajor", 1900)]


def test_un_archivo_que_no_es_planilla_no_revienta():
    assert planilla.leer("foto.xlsx", b"esto no es un zip") == []


# ------------------------------------------------------------------ la API
def test_previsualizar_no_escribe_nada(cliente, carta):
    antes = cliente.get("/api/v1/categorias").json()
    r = cliente.post("/api/v1/importar/texto", json={"texto": CARTA}).json()
    assert r["resumen"]["total"] == 5
    # Ni un producto nuevo antes de confirmar.
    assert cliente.get("/api/v1/categorias").json() == antes


def test_dice_que_va_a_pasar_con_cada_producto(cliente, carta):
    texto = "Latte;5000\nCosa Nueva;2000\n"
    r = cliente.post("/api/v1/importar/texto", json={"texto": texto}).json()
    porque = {p["nombre"]: p for p in r["productos"]}
    assert porque["Latte"]["que_pasa"] == "cambia_precio"
    assert porque["Latte"]["precio_anterior"] == 3400
    assert porque["Cosa Nueva"]["que_pasa"] == "nuevo"


def test_aplicar_crea_actualiza_y_crea_la_categoria(cliente, carta):
    r = cliente.post("/api/v1/importar/texto", json={"texto": CARTA}).json()
    ap = cliente.post("/api/v1/importar/aplicar",
                      json={"productos": r["productos"]}).json()
    # La carta de prueba ya tenía Espresso y Latte: esos dos se actualizan,
    # y entran Cortado, Croissant y Torta de zanahoria.
    assert ap["creados"] == 3 and ap["actualizados"] == 2

    cats = cliente.get("/api/v1/categorias").json()
    nombres = {c["nombre"] for c in cats}
    assert "CAFES" in nombres and "PASTELERIA" in nombres
    latte = [p for c in cats for p in c["productos"] if p["nombre"] == "Latte"][0]
    assert latte["precio"] == 3500


def test_importar_dos_veces_no_duplica(cliente, carta):
    for _ in range(2):
        r = cliente.post("/api/v1/importar/texto", json={"texto": CARTA}).json()
        cliente.post("/api/v1/importar/aplicar", json={"productos": r["productos"]})
    cats = cliente.get("/api/v1/categorias").json()
    todos = [p["nombre"] for c in cats for p in c["productos"]]
    assert todos.count("Croissant") == 1


def test_lo_que_no_viene_en_el_archivo_no_se_toca_solo(cliente, carta):
    """Un archivo incompleto no puede borrar la carta del local."""
    r = cliente.post("/api/v1/importar/texto", json={"texto": "Latte;3400"}).json()
    assert "Espresso" in r["no_estan_en_el_archivo"]
    cliente.post("/api/v1/importar/aplicar", json={"productos": r["productos"]})
    cats = cliente.get("/api/v1/categorias").json()
    espresso = [p for c in cats for p in c["productos"] if p["nombre"] == "Espresso"][0]
    assert espresso["activo"] is True


def test_pero_se_puede_pedir_expresamente(cliente, carta):
    r = cliente.post("/api/v1/importar/texto", json={"texto": "Latte;3400"}).json()
    ap = cliente.post("/api/v1/importar/aplicar", json={
        "productos": r["productos"], "sacar_lo_que_no_vino": True}).json()
    assert ap["sacados"] >= 1
    cats = cliente.get("/api/v1/categorias").json()
    espresso = [p for c in cats for p in c["productos"] if p["nombre"] == "Espresso"][0]
    assert espresso["activo"] is False       # borrado lógico, no borrado


def test_no_se_pisa_lo_que_alguien_ya_ajusto_a_mano(cliente, carta):
    """Si el dueño eligió el dibujo de un producto, el importador no lo cambia:
    esa decisión vale más que lo que adivinó el programa."""
    cliente.put(f"/api/v1/productos/{carta['latte']['id']}", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Latte", "precio": 3400,
        "dibujo": "mug-arte", "descripcion": "con arte"})
    r = cliente.post("/api/v1/importar/texto", json={"texto": "Latte;9900"}).json()
    cliente.post("/api/v1/importar/aplicar", json={"productos": r["productos"]})
    cats = cliente.get("/api/v1/categorias").json()
    latte = [p for c in cats for p in c["productos"] if p["nombre"] == "Latte"][0]
    assert latte["precio"] == 9900            # el precio sí
    assert latte["dibujo"] == "mug-arte"      # el dibujo no
    assert latte["descripcion"] == "con arte"


def test_un_archivo_sin_productos_avisa_claro(cliente, carta):
    r = cliente.post("/api/v1/importar/texto", json={"texto": "\n\n"})
    assert r.status_code == 422
    assert "no pude leer" in r.json()["detail"].lower()


def test_traer_la_carta_es_cosa_del_dueno(cliente, carta):
    d = cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": d["id"], "pin": "1234"})
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    assert cliente.post("/api/v1/importar/texto",
                        json={"texto": CARTA}).status_code == 403
