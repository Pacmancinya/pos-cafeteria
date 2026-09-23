"""La caja no puede quedarse con el JavaScript de la versión anterior.

Pasó dos veces: en la 2.5 (el teclado en pantalla que se apagó y seguía saliendo) y en
la 2.29 (la impresión térmica nueva que nunca se usó, porque el navegador tenía guardado
el app.js de la 2.28). Las dos veces la causa fue la misma: el `?v=` de los archivos se
escribía a mano en el HTML y se olvidó subirlo. Ahora lo pone el servidor con la versión
de la caja, y estas pruebas cuidan que siga siendo así.
"""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from apps.pos.main import app
from core.config import VERSION

ESTATICOS = Path(__file__).resolve().parents[1] / "static"
HTML = ("index.html", "pantallas.html")


def test_ningun_html_trae_un_numero_de_version_a_mano():
    # Los HTML de la carpeta static y también el de «Entrar», que vive dentro del
    # código (apps/pos/acceso.py) y ya se había quedado en ?v=10.
    archivos = [ESTATICOS / n for n in HTML] + [Path(__file__).resolve().parents[1] / "acceso.py"]
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        a_mano = re.findall(r'\.(?:js|css)\?v=(?!__VERSION__)([^"\']+)', texto)
        assert not a_mano, f"{archivo.name} tiene ?v= escritos a mano: {a_mano}"


def test_el_servidor_pone_la_version_en_cada_pantalla():
    cliente = TestClient(app)
    # «/» sin sesión muestra la pantalla de entrar: también lleva estilos.
    paginas = [cliente.get("/"), cliente.get("/pantallas"), cliente.get("/entrar")]
    for r in paginas:
        assert r.status_code == 200
        assert re.search(r'\.(?:js|css)\?v=' + re.escape(VERSION), r.text), r.url
        assert "__VERSION__" not in r.text, f"{r.url} quedó con la marca sin reemplazar"


def test_el_html_de_la_caja_nunca_se_guarda_en_cache():
    # Es el que LLEVA los ?v= de los demás: si se guarda, la caja se queda pegada.
    for ruta in ("/", "/pantallas"):
        r = TestClient(app).get(ruta)
        assert "no-store" in r.headers.get("cache-control", ""), ruta


def test_cada_archivo_que_carga_la_caja_existe():
    texto = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    for archivo in re.findall(r'/static/([\w.-]+\.(?:js|css))\?v=', texto):
        assert (ESTATICOS / archivo).is_file(), f"index.html pide {archivo} y no está"
