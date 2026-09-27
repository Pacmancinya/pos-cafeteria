"""Leer la lista de productos que ya tiene el cliente.

Ningún local llega con la carta escrita como la queremos nosotros: llega un
Excel que hizo alguien, con los precios en `$3.500`, las categorías como
títulos en medio de la tabla, filas en blanco y una columna de más. Este
archivo se hace cargo de eso.

**El .xlsx se lee con biblioteca estándar.** Un .xlsx es un ZIP con XML adentro,
así que no hace falta `openpyxl`: agregar una dependencia obligaría a que el
local descargue los 29 MB del ejecutable otra vez, en vez de una actualización
de 140 KB. Leer celdas es lo único que necesitamos y son cien líneas.

Nada de acá toca la base de datos: esto solo convierte un archivo en filas y
las interpreta. Quien decide qué se guarda es la persona, mirando la
previsualización.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

HOJA = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Hasta acá leemos. Una carta de cafetería no tiene 5.000 productos, y si el
# archivo trae eso es que no es una carta.
TOPE_FILAS = 3000


# ---------------------------------------------------------------------------
# Leer el archivo
# ---------------------------------------------------------------------------
def leer(nombre: str, datos: bytes) -> list[list[str]]:
    """Cualquier archivo → una tabla de texto. Vacía si no se entiende."""
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        return _leer_xlsx(datos)
    return desde_texto(_decodificar(datos))


def _decodificar(datos: bytes) -> str:
    """Excel en español guarda CSV en latin-1 tan seguido como en UTF-8."""
    for codigo in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return datos.decode(codigo)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", errors="replace")


def desde_texto(texto: str) -> list[list[str]]:
    """Texto pegado o CSV. Adivina el separador.

    El orden importa: primero el punto y coma, que es lo que usa el Excel en
    español, y después el tabulador, que es lo que sale al copiar y pegar
    desde una planilla.
    """
    texto = texto.replace("\r\n", "\n").strip("\n")
    if not texto:
        return []
    muestra = "\n".join(texto.split("\n")[:20])
    separador = max((";", "\t", ",", "|"), key=muestra.count)
    if muestra.count(separador) == 0:
        separador = ";"          # una sola columna: da lo mismo cuál
    filas = list(csv.reader(io.StringIO(texto), delimiter=separador))
    return [[(c or "").strip() for c in fila] for fila in filas[:TOPE_FILAS]]


def _leer_xlsx(datos: bytes) -> list[list[str]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile:
        return []

    compartidas = _textos_compartidos(z)
    ruta = _primera_hoja(z)
    if not ruta:
        return []

    filas: list[list[str]] = []
    with z.open(ruta) as f:
        for _, elemento in ET.iterparse(f, events=("end",)):
            if elemento.tag != HOJA + "row":
                continue
            fila: list[str] = []
            for celda in elemento.findall(HOJA + "c"):
                # La referencia (A1, C1…) es lo que permite respetar las celdas
                # vacías: sin esto, una columna en blanco corre todo a la
                # izquierda y los precios terminan en la columna del nombre.
                columna = _numero_de_columna(celda.get("r", ""))
                while len(fila) < columna:
                    fila.append("")
                fila.append(_valor(celda, compartidas))
            filas.append(fila)
            elemento.clear()
            if len(filas) >= TOPE_FILAS:
                break
    return filas


def _primera_hoja(z: zipfile.ZipFile) -> str:
    """La primera hoja del libro, en el orden en que la ve la persona."""
    try:
        libro = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        destino = {r.get("Id"): r.get("Target") for r in rels}
        for hoja in libro.iter(HOJA + "sheet"):
            objetivo = destino.get(hoja.get(REL + "id"), "")
            if objetivo:
                objetivo = objetivo.lstrip("/")
                return objetivo if objetivo.startswith("xl/") else "xl/" + objetivo
    except (KeyError, ET.ParseError):
        pass
    hojas = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
    return hojas[0] if hojas else ""


def _textos_compartidos(z: zipfile.ZipFile) -> list[str]:
    try:
        raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except (KeyError, ET.ParseError):
        return []
    # Un texto con formato viene partido en varios <t>: hay que pegarlos.
    return ["".join(t.text or "" for t in si.iter(HOJA + "t"))
            for si in raiz.iter(HOJA + "si")]


def _valor(celda, compartidas: list[str]) -> str:
    tipo = celda.get("t", "")
    if tipo == "inlineStr":
        return "".join(t.text or "" for t in celda.iter(HOJA + "t")).strip()
    v = celda.find(HOJA + "v")
    if v is None or v.text is None:
        return ""
    if tipo == "s":
        try:
            return compartidas[int(v.text)].strip()
        except (ValueError, IndexError):
            return ""
    texto = v.text.strip()
    # Excel guarda 3500 como "3500" pero a veces como "3500.0".
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def _numero_de_columna(referencia: str) -> int:
    """'C7' → 2 (base cero). Sin letras, va al final."""
    letras = "".join(c for c in referencia if c.isalpha()).upper()
    if not letras:
        return 0
    n = 0
    for c in letras:
        n = n * 26 + (ord(c) - 64)
    return n - 1


# ---------------------------------------------------------------------------
# Entender la tabla
# ---------------------------------------------------------------------------
def sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                   if unicodedata.category(c) != "Mn").lower().strip()


PALABRAS = {
    "nombre": ("producto", "nombre", "descripcion corta", "item", "articulo",
               "detalle", "menu"),
    "precio": ("precio", "valor", "monto", "p. venta", "precio venta",
               "pvp", "total", "$"),
    "categoria": ("categoria", "familia", "rubro", "tipo", "grupo", "seccion",
                  "linea"),
    "descripcion": ("descripcion", "detalle largo", "observacion", "ingredientes"),
}


def a_precio(texto: str) -> int | None:
    """'$3.500' → 3500. En CLP no hay centavos, así que se descartan.

    El punto y la coma son ambiguos y hay que resolverlos por la forma, no por
    el símbolo: en Chile `3.500` son tres mil quinientos, pero el mismo Excel
    guarda `4.0365000000000005` cuando la celda tenía una fórmula. Sin separar
    esos casos, ese precio entra a la caja como cuarenta mil billones de pesos
    — pasó con una planilla real.

    Devuelve None si no hay ningún número: eso distingue "no traía precio" de
    "el precio es cero", que en una carta son cosas distintas.
    """
    t = str(texto or "").strip()
    if not t:
        return None
    if t.startswith("-"):
        return None                      # un precio negativo no es un precio

    nucleo = re.sub(r"[^\d.,]", "", t)   # fuera el $, los espacios, el "c/u"
    if not nucleo:
        return None

    # Con los DOS separadores (3.500,00) el de más a la derecha es el decimal:
    # se corta ahí y lo de la izquierda son miles.
    if "." in nucleo and "," in nucleo:
        corte = max(nucleo.rfind("."), nucleo.rfind(","))
        entero = re.sub(r"\D", "", nucleo[:corte])
        return int(entero) if entero else None

    # Miles: grupos de exactamente tres, repetidos. 1.234.567 · 3.500 · 12,500
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", nucleo):
        return int(re.sub(r"\D", "", nucleo))

    # Un solo separador con 1 o 2 decimales: son centavos, y acá no existen.
    if re.fullmatch(r"\d+[.,]\d{1,2}", nucleo):
        return int(nucleo.split(".")[0].split(",")[0])

    # Cuatro decimales o más: es basura de coma flotante de la planilla.
    if re.fullmatch(r"\d+[.,]\d{4,}", nucleo):
        return round(float(nucleo.replace(",", ".")))

    digitos = re.sub(r"\D", "", nucleo)
    return int(digitos) if digitos else None


def parece_precio(texto: str) -> bool:
    """¿Esta celda ES un precio, o solo tiene números adentro?

    Distinción necesaria: "CAFETERÍA LA ESQUINA - CARTA 2026" tiene un número y
    no es un precio. Sin esto, el título de la carta entra como producto de
    $2.026 en vez de como nombre de sección.
    """
    if a_precio(texto) is None:
        return False
    return not re.search(r"[^\W\d_]{3,}", str(texto or ""))


def _es_encabezado(fila: list[str]) -> bool:
    """¿Esta fila son títulos de columna y no un producto?"""
    limpias = [sin_tildes(c) for c in fila if str(c).strip()]
    if not limpias:
        return False
    conocidas = sum(1 for c in limpias
                    if any(p in c for grupo in PALABRAS.values() for p in grupo))
    # Y que no tenga precios: "Café 3500" no es un encabezado por más que
    # diga algo parecido a "precio".
    con_numero = sum(1 for c in limpias if parece_precio(c))
    return conocidas >= 1 and con_numero == 0


def _mapear(encabezado: list[str]) -> dict:
    """Qué columna es cada cosa, según cómo la tituló el cliente."""
    mapa: dict[str, int] = {}
    for i, celda in enumerate(encabezado):
        limpio = sin_tildes(celda)
        if not limpio:
            continue
        for campo, palabras in PALABRAS.items():
            if campo in mapa:
                continue
            if any(limpio == p or limpio.startswith(p) or p in limpio for p in palabras):
                mapa[campo] = i
                break
    return mapa


# Con qué se dibuja cada cosa en la caja y en las pantallas del local. Es una
# adivinanza a propósito: es mucho más rápido corregir tres dibujos que elegir
# cuarenta.
DIBUJOS = [
    (("capuchino", "cappu", "latte", "mocha", "moka", "americano", "chocolate caliente"), "mug"),
    (("espresso", "expreso", "ristretto", "cortado", "macchiato"), "taza"),
    (("frappe", "frapp", "smoothie", "batido", "milkshake"), "frappe"),
    (("jugo", "limonada", "naranja", "berri", "frutilla"), "vaso-limon"),
    (("te ", "te verde", "matcha", "menta", "hierba", "infusion"), "vaso-verde"),
    (("helado", "iced", "frio", "cold brew", "granizado"), "vaso"),
    (("leche", "malteada", "vainilla"), "vaso-leche"),
    (("croissant", "cruasan", "medialuna"), "croissant"),
    (("brownie",), "brownie"),
    (("alfajor", "galleta", "cookie"), "alfajor"),
    (("torta", "tarta", "kuchen", "pie", "cheesecake", "queque", "pastel"), "torta"),
    (("cafe",), "mug"),
]


def adivinar_dibujo(nombre: str, categoria: str = "") -> str:
    texto = sin_tildes(nombre + " " + categoria)
    for palabras, dibujo in DIBUJOS:
        if any(p in texto for p in palabras):
            return dibujo
    return "mug"


def interpretar(filas: list[list[str]]) -> dict:
    """De una tabla cruda a una carta que se puede revisar antes de guardar."""
    productos: list[dict] = []
    avisos: list[str] = []
    mapa: dict[str, int] = {}
    categoria_actual = ""
    encabezado_visto = False

    for numero, fila in enumerate(filas, start=1):
        if not any(str(c).strip() for c in fila):
            continue                                   # fila en blanco

        if not encabezado_visto and _es_encabezado(fila):
            mapa = _mapear(fila)
            encabezado_visto = True
            continue

        celdas = [str(c).strip() for c in fila]
        con_texto = [c for c in celdas if c]

        # Una fila con una sola celda y sin precio es un título de sección:
        # así vienen escritas casi todas las cartas ("CAFÉS", "PASTELERÍA").
        if len(con_texto) == 1 and not parece_precio(con_texto[0]):
            categoria_actual = con_texto[0]
            continue

        def columna(campo: str) -> str:
            """La celda de esa columna, o vacío si el archivo no la traía."""
            i = mapa.get(campo)
            return celdas[i] if i is not None and i < len(celdas) else ""

        # Con encabezado NO basta: puede haber traído "Precio" y no una columna
        # de nombre. Solo se usa el mapa si sabemos dónde está el nombre.
        if "nombre" in mapa:
            nombre = columna("nombre")
            crudo = columna("precio")
            categoria = columna("categoria") or categoria_actual
            descripcion = columna("descripcion")
        else:
            # Sin encabezado: el nombre es la primera celda con letras y el
            # precio, la ÚLTIMA celda que sea un número. La última y no la
            # primera porque en las cartas suele haber un código antes.
            nombre = next((c for c in celdas if c and not c.replace(" ", "").isdigit()), "")
            numeros = [c for c in celdas if c != nombre and parece_precio(c)]
            crudo = numeros[-1] if numeros else ""
            categoria, descripcion = categoria_actual, ""

        nombre = nombre.strip()
        if not nombre:
            continue
        if parece_precio(nombre):
            continue                                   # era un número suelto

        precio = a_precio(crudo)
        if precio is None:
            avisos.append(f"Fila {numero}: «{nombre}» no traía precio, quedó en $0.")
        productos.append({
            "fila": numero,
            "nombre": nombre[:80],
            "precio": precio or 0,
            "categoria": (categoria or "Carta").strip()[:40],
            "descripcion": descripcion[:120],
            "dibujo": adivinar_dibujo(nombre, categoria),
        })

    # Nombres repetidos: se queda el primero y se avisa.
    vistos: dict[str, int] = {}
    limpios: list[dict] = []
    for p in productos:
        clave = sin_tildes(p["nombre"])
        if clave in vistos:
            avisos.append(f"«{p['nombre']}» aparece más de una vez; se dejó el primero.")
            continue
        vistos[clave] = p["fila"]
        limpios.append(p)

    return {
        "productos": limpios,
        "avisos": avisos[:25],
        "columnas_detectadas": {k: v for k, v in mapa.items()},
        "con_encabezado": encabezado_visto,
    }
