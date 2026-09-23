"""El driver se dobla: ninguna prueba manda papel a una impresora real."""
import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.pos import impresion_windows as windows


def test_datos_viajan_por_stdin_no_como_comandos(monkeypatch):
    llamadas = []

    def ejecutar(orden, **opciones):
        llamadas.append((orden, opciones))
        return SimpleNamespace(returncode=0, stdout='{"ok":true}')

    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows.subprocess, "run", ejecutar)
    nombre = 'Caja ñ " ; $(comando)'
    r = windows.imprimir(nombre, 58, ["Café $1.234", "NO ES BOLETA"])
    assert r["ok"]
    orden, opciones = llamadas[0]
    assert len(llamadas) == 1
    assert nombre not in " ".join(orden)
    assert base64.b64decode(orden[-1]).decode("utf-16-le") == windows._SCRIPT
    assert json.loads(opciones["input"]) == {
        "accion": "imprimir", "impresora": nombre, "papel": 58,
        "lineas": ["Café $1.234", "NO ES BOLETA"],
    }
    assert opciones["timeout"] == 20
    assert opciones["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert not opciones.get("shell")


@pytest.mark.parametrize("respuesta,estado,texto", [
    ('{"error":"ausente"}', 409, "ya no está instalada"),
    ('{"error":"archivo"}', 422, "PDF"),
    ('{"error":"driver"}', 503, "podría estar en la cola"),
    ('basura', 503, "No se reintentó"),
    ('[]', 503, "No se reintentó"),
])
def test_error_no_reintenta_y_suelta_el_cerrojo(monkeypatch, respuesta, estado, texto):
    llamadas = []

    def ejecutar(*args, **kwargs):
        llamadas.append(args)
        return SimpleNamespace(returncode=0, stdout=respuesta)

    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows.subprocess, "run", ejecutar)
    with pytest.raises(windows.ErrorImpresion, match=texto) as e:
        windows.imprimir("Caja", 80, ["Prueba"])
    assert e.value.estado == estado
    assert len(llamadas) == 1
    assert not windows._ocupado.locked()


def test_driver_lento_se_corta_sin_reintento(monkeypatch):
    llamadas = []

    def lento(*args, **kwargs):
        llamadas.append(args)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows.subprocess, "run", lento)
    with pytest.raises(windows.ErrorImpresion, match="podría estar en la cola"):
        windows.imprimir("Caja", 80, ["Prueba"])
    assert len(llamadas) == 1
    assert not windows._ocupado.locked()


def test_no_windows_no_abre_procesos(monkeypatch):
    monkeypatch.setattr(windows, "disponible", lambda: False)
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: pytest.fail("No ejecutar"))
    assert windows.listar()["disponible"] is False
    with pytest.raises(windows.ErrorImpresion, match="requiere Windows"):
        windows.imprimir("Caja", 80, ["Prueba"])


def test_lista_vacia_y_unicode(monkeypatch):
    monkeypatch.setattr(windows, "disponible", lambda: True)
    for lista in ([], [{"nombre": "Café térmica", "disponible": True}]):
        def ejecutar(*args, **kwargs):
            assert kwargs["timeout"] == 10
            assert json.loads(kwargs["input"]) == {"accion": "listar"}
            return SimpleNamespace(returncode=0, stdout=json.dumps({"impresoras": lista}))
        monkeypatch.setattr(windows.subprocess, "run", ejecutar)
        assert windows.listar() == {"disponible": True, "impresoras": lista}


def test_solicitudes_simultaneas_no_acumulan_procesos(monkeypatch):
    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: pytest.fail("No ejecutar"))
    with windows._ocupado:
        with pytest.raises(windows.ErrorImpresion, match="No se envió") as e:
            windows.imprimir("Caja", 80, ["Prueba"])
        assert e.value.estado == 409
    assert not windows._ocupado.locked()


def test_consultar_impresoras_no_ocupa_el_cerrojo_del_papel(monkeypatch):
    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout='{"ok":true}'))
    with windows._consultando:
        assert windows.imprimir("Caja", 80, ["Prueba"])["ok"]


@pytest.mark.parametrize("nombre,papel,lineas", [
    ("", 80, ["Prueba"]), ("Caja", 60, ["Prueba"]),
    ("x" * 257, 58, ["Prueba"]), ("Caja", 80, []),
    ("Caja", 80, ["x"] * 1001), ("Caja", 80, ["x" * 32001]),
])
def test_limites_antes_de_tocar_el_driver(monkeypatch, nombre, papel, lineas):
    monkeypatch.setattr(windows, "_ejecutar", lambda *a: pytest.fail("No ejecutar"))
    with pytest.raises(windows.ErrorImpresion) as e:
        windows.imprimir(nombre, papel, lineas)
    assert e.value.estado == 422


def test_interfaz_en_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("No hay Node en este computador")
    r = subprocess.run([node, str(Path(__file__).with_name("impresion_ui.js"))],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita Windows PowerShell")
def test_script_real_filtra_virtuales_y_compila_sin_imprimir(monkeypatch):
    # Inventario ficticio y llamada de impresión eliminada: nunca manda papel.
    script = windows._SCRIPT.replace(
        "@(Get-CimInstance -ClassName Win32_Printer)",
        "@([pscustomobject]@{Name='Caja';PortName='USB001';DriverName='Termica'},"
        "[pscustomobject]@{Name='OneNote for Windows 10';"
        "PortName='Microsoft.Office.OneNote_8wekyb3d8bbwe';DriverName='Generic'},"
        "[pscustomobject]@{Name='PDF';PortName='PORTPROMPT:';DriverName='PDF'},"
        "[pscustomobject]@{Name='Fax';PortName='SHRFAX:';DriverName='Fax'})",
    ).replace(
        "@([System.Drawing.Printing.PrinterSettings]::InstalledPrinters)",
        "@('Caja', 'OneNote for Windows 10', 'PDF', 'Fax')",
    )
    llamada = '[ReciboCaja]::Imprimir([string]$dato.impresora, [int]$dato.papel, [string[]]$dato.lineas)'
    assert script.count(llamada) == 1
    script = script.replace(llamada, "# Solo compilar C#, sin llamar a Imprimir")
    monkeypatch.setattr(windows, "_SCRIPT", script)
    lista = windows.listar()["impresoras"]
    assert {p["nombre"]: p["disponible"] for p in lista} == {
        "Caja": True, "OneNote for Windows 10": False, "PDF": False, "Fax": False,
    }
    assert windows.imprimir("Caja", 58, ["Prueba ñ"])["ok"]
    with pytest.raises(windows.ErrorImpresion) as e:
        windows.imprimir("OneNote for Windows 10", 58, ["No imprimir"])
    assert e.value.estado == 422
