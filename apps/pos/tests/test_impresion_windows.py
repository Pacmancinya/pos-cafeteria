"""El driver se dobla: ninguna prueba manda papel a una impresora real."""
import base64
import json
import re
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
            # 30 s y no 10: la primera llamada a PowerShell en un equipo recién
            # instalado se va preparando sus módulos y no alcanzaba a contestar.
            assert kwargs["timeout"] == 30
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
    llamada_cruda = '[ReciboCrudo]::Enviar([string]$dato.impresora, [Convert]::FromBase64String($dato.bytes))'
    assert script.count(llamada_cruda) == 1
    script = script.replace(llamada_cruda, "# Solo compilar C#, sin llamar a Enviar")
    monkeypatch.setattr(windows, "_SCRIPT", script)
    lista = windows.listar()["impresoras"]
    assert {p["nombre"]: p["disponible"] for p in lista} == {
        "Caja": True, "OneNote for Windows 10": False, "PDF": False, "Fax": False,
    }
    assert windows.imprimir("Caja", 58, ["Prueba ñ"])["ok"]
    assert windows.imprimir_crudo("Caja", 80, ["Prueba ñ"])["ok"]
    with pytest.raises(windows.ErrorImpresion) as e:
        windows.imprimir("OneNote for Windows 10", 58, ["No imprimir"])
    assert e.value.estado == 422


@pytest.mark.parametrize("cortar", [True, False])
def test_crudo_secuencia_tabla_estilos_y_datos_por_stdin(monkeypatch, cortar):
    llamadas = []

    def ejecutar(orden, **opciones):
        llamadas.append((orden, opciones))
        return SimpleNamespace(returncode=0, stdout='{"ok":true}')

    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows.subprocess, "run", ejecutar)
    nombre = 'Caja ñ " ; $(comando)'
    assert windows.imprimir_crudo(nombre, 80, ["Café", "azúcar niño ¿ ¡", "NO ES BOLETA"], cortar)["ok"]
    assert len(llamadas) == 1
    orden, opciones = llamadas[0]
    assert nombre not in " ".join(orden)
    assert base64.b64decode(orden[-1]).decode("utf-16-le") == windows._SCRIPT
    assert opciones["timeout"] == 20
    datos = json.loads(opciones["input"])
    assert datos["impresora"] == nombre and datos["accion"] == "crudo"
    salida = base64.b64decode(datos["bytes"])
    assert salida.startswith(b"\x1b@\x1bt\x02\x1ba\x01" + "Café\n".encode("cp850"))
    assert "azúcar niño ¿ ¡".encode("cp850") in salida
    assert b"\x1ba\x01\x1d!\x01NO ES BOLETA\n\x1d!\x00\x1ba\x00" in salida
    assert salida.endswith(b"\x1bd\x06\x1dVB\x00" if cortar else b"\x1bd\x06")
    assert salida.count(b"\x1dVB\x00") == int(cortar)


def texto_crudo(datos):
    # Se quitan solo las órdenes que el generador conoce, para medir el papel.
    for orden in (b"\x1b@", b"\x1bt\x02", b"\x1ba\x01", b"\x1ba\x00",
                  b"\x1d!\x01", b"\x1d!\x00", b"\x1bd\x06", b"\x1dVB\x00"):
        datos = datos.replace(orden, b"")
    return datos.decode("cp850").splitlines()


@pytest.mark.parametrize("papel,ancho", [(58, 32), (80, 48)])
def test_ancho_importes_completos_y_nombre_largo(papel, ancho):
    lineas = ["Mi local", "2 x Café  $12.345", "1 x " + "Nombre largo " * 12 + "  $9.876",
              "Descuento  -$500", "TOTAL  $21.721", "Dirección " * 12, "NO ES BOLETA"]
    salida = texto_crudo(windows._bytes_escpos(papel, lineas))
    assert all(len(linea) <= ancho for linea in salida)
    for posicion, importe in ((1, "$12.345"), (2, "$9.876"), (3, "-$500"), (4, "$21.721")):
        assert len(salida[posicion]) == ancho
        assert salida[posicion].endswith(importe)
    assert re.search(r"\.\.\. +\$9.876$", salida[2])
    assert salida[1].startswith("2 x Café")


def test_caracteres_raros_y_controles_no_inyectan_ordenes():
    texto = "Café azúcar niño ¿¡ · Ć Ł 🙂 漢 \x1b\x1d\x00\x7f\n\t\ud800"
    limpio = windows._texto_cp850(texto)
    assert limpio.startswith("Café azúcar niño ¿¡ - C  ")
    assert all(c.isprintable() for c in limpio)
    limpio.encode("cp850")
    assert windows._texto_cp850("Cafe\u0301") == "Café"
    # Cada carácter Unicode, incluidos sustitutos aislados, tiene salida válida.
    for inicio in range(0, 0x110000, 4096):
        windows._texto_cp850("".join(chr(n) for n in range(inicio, min(inicio + 4096, 0x110000)))).encode("cp850")
    datos = windows._bytes_escpos(80, ["Local", texto], cortar=False)
    assert datos.count(b"\x1b") == 6  # inicializar, tabla, centro, dos restauraciones y avance
    assert b"\x1dVB\x00" not in datos


def test_crudo_comparte_cerrojo_y_no_reintenta(monkeypatch):
    monkeypatch.setattr(windows, "disponible", lambda: True)
    llamadas = []

    def lento(*args, **kwargs):
        llamadas.append(args)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(windows.subprocess, "run", lento)
    with windows._ocupado:
        with pytest.raises(windows.ErrorImpresion) as e:
            windows.imprimir_crudo("Caja", 80, ["Local"])
        assert e.value.estado == 409
    assert not llamadas
    with pytest.raises(windows.ErrorImpresion, match="No se reintentó"):
        windows.imprimir_crudo("Caja", 80, ["Local"])
    assert len(llamadas) == 1 and not windows._ocupado.locked()


@pytest.mark.parametrize("nombre", ["", "x" * 61, "Café", "Caja\n", "$(comando)", "   "])
def test_instalar_rechaza_nombre_antes_de_ejecutar(monkeypatch, nombre):
    monkeypatch.setattr(windows, "_ejecutar", lambda *a: pytest.fail("No ejecutar"))
    with pytest.raises(windows.ErrorImpresion) as e:
        windows.instalar("USB001", nombre)
    assert e.value.estado == 422


def test_instalar_valida_puerto_y_rechazo_de_permisos(monkeypatch):
    monkeypatch.setattr(windows, "disponible", lambda: True)
    llamadas = []

    def ejecutar(orden, **opciones):
        datos = json.loads(opciones["input"])
        llamadas.append(datos)
        if datos["accion"] == "puertos":
            return SimpleNamespace(returncode=0, stdout='{"puertos":[{"nombre":"USB001","descripcion":"USB"}]}')
        assert 0 < opciones["timeout"] <= 120
        assert base64.b64decode(orden[-1]).decode("utf-16-le") == windows._INSTALAR
        assert "USB001" not in " ".join(orden)
        return SimpleNamespace(returncode=0, stdout='{"error":"cancelado"}')

    monkeypatch.setattr(windows.subprocess, "run", ejecutar)
    with pytest.raises(windows.ErrorImpresion) as e:
        windows.instalar("USB999", "Kofe Tickets")
    assert e.value.estado == 409 and len(llamadas) == 1
    with pytest.raises(windows.ErrorImpresion, match="No se instaló") as e:
        windows.instalar("USB001", "Kofe Tickets")
    assert e.value.estado == 409
    assert llamadas[-1] == {"accion": "instalar", "puerto": "USB001", "nombre": "Kofe Tickets"}
    assert not windows._instalando.locked()


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita Windows PowerShell")
def test_puertos_reales_del_script_con_inventario_ficticio(monkeypatch):
    prefijo = r"""
function Get-Printer { @([pscustomobject]@{PortName='USB001'}, [pscustomobject]@{PortName='LPT1:, LPT2:'}) }
function Get-PrinterPort {
    @('USB001','USB002','LPT1:','LPT2:') | ForEach-Object {
        [pscustomobject]@{Name=$_;Description='Puerto de impresora'}
    }
}
"""
    monkeypatch.setattr(windows, "_PUERTOS", prefijo + windows._PUERTOS)
    assert windows.puertos_sin_impresora() == {"disponible": True, "puertos": [
        {"nombre": "USB002", "descripcion": "Puerto de impresora"}]}


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita Windows PowerShell")
def test_script_instalacion_cancelada_sin_elevacion(monkeypatch):
    prefijo = r"""
function Start-Process { throw (New-Object System.ComponentModel.Win32Exception(1223)) }
"""
    monkeypatch.setattr(windows, "_INSTALAR", prefijo + windows._INSTALAR)
    with pytest.raises(windows.ErrorImpresion, match="Se canceló") as e:
        windows._ejecutar({"accion": "instalar", "puerto": "USB001", "nombre": "Kofe Tickets"})
    assert e.value.estado == 409


@pytest.mark.skipif(sys.platform != "win32", reason="Necesita Windows PowerShell")
@pytest.mark.parametrize("situacion,error", [("libre", None), ("ocupado", 409), ("existe", 409), ("nombre", 422)])
def test_instalador_comunica_y_revalida_sin_tocar_windows(monkeypatch, situacion, error):
    # El hijo usa el canal real, pero TODAS las operaciones de impresoras están
    # dobladas y se lanza sin RunAs. Nunca pide permisos ni modifica una cola.
    inventario = {
        "ocupado": "[pscustomobject]@{Name='Otra';PortName='USB001'}",
        "existe": "[pscustomobject]@{Name='Kofe Tickets';PortName='USB002'}",
    }.get(situacion, "")
    dobles = r"""
function Get-Printer { __INVENTARIO__ }
function Get-PrinterPort { [pscustomobject]@{Name='USB001';Description='USB'} }
function Get-PrinterDriver { }
function Add-PrinterDriver {
    param($Name)
    if ($Name -ne 'Generic / Text Only') { throw 'Driver incorrecto' }
    $script:driverPreparado = $true
}
function Add-Printer {
    param($Name, $DriverName, $PortName)
    if (-not $script:driverPreparado -or $Name -ne 'Kofe Tickets' -or
        $DriverName -ne 'Generic / Text Only' -or $PortName -ne 'USB001') { throw 'Cola incorrecta' }
}
""".replace("__INVENTARIO__", inventario)
    prefijo = r"""
function Start-Process {
    param($FilePath, $Verb, $WindowStyle, [switch]$PassThru, $ArgumentList)
    $codigo = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($ArgumentList[-1]))
    $dobles = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__DOBLES__'))
    $ArgumentList[-1] = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($dobles + $codigo))
    Microsoft.PowerShell.Management\Start-Process -FilePath $FilePath -WindowStyle Hidden -PassThru -ArgumentList $ArgumentList
}
""".replace("__DOBLES__", base64.b64encode(dobles.encode()).decode())
    monkeypatch.setattr(windows, "_INSTALAR", prefijo + windows._INSTALAR)
    datos = {"accion": "instalar", "puerto": "USB001",
             "nombre": "$(comando)" if situacion == "nombre" else "Kofe Tickets"}
    if error:
        with pytest.raises(windows.ErrorImpresion) as e:
            windows._ejecutar(datos, espera=20)
        assert e.value.estado == error
    else:
        assert windows._ejecutar(datos, espera=20) == {"ok": True, "nombre": "Kofe Tickets"}


def test_instalar_timeout_total_y_sin_reintentos(monkeypatch):
    tiempos = iter([10, 17])
    monkeypatch.setattr(windows.time, "monotonic", lambda: next(tiempos))
    monkeypatch.setattr(windows, "disponible", lambda: True)
    monkeypatch.setattr(windows, "puertos_sin_impresora", lambda: {"puertos": [{"nombre": "USB001"}]})
    llamadas = []

    def lento(orden, **opciones):
        llamadas.append(opciones)
        assert opciones["timeout"] == 113
        raise subprocess.TimeoutExpired(orden, opciones["timeout"])

    monkeypatch.setattr(windows.subprocess, "run", lento)
    with pytest.raises(windows.ErrorImpresion, match="120 segundos"):
        windows.instalar("USB001", "Kofe Tickets")
    assert len(llamadas) == 1 and not windows._instalando.locked()


# --------------------------------------------------------------- forma del comprobante
def _ordenes(bloque, ancho=48):
    return windows._bloque_a_bytes(bloque, ancho)


def test_el_titulo_va_centrado_y_grande():
    salida = _ordenes({"tipo": "titulo", "texto": "Cafe Renni"})
    assert salida.startswith(b"\x1ba\x01\x1d!\x11")          # centrado + doble alto y ancho
    assert b"Cafe Renni\n" in salida
    assert salida.endswith(b"\x1d!\x00\x1bE\x00\x1bM\x00\x1ba\x00")  # vuelve a lo normal


def test_el_total_ocupa_el_ancho_entero_en_doble_alto():
    salida = _ordenes({"tipo": "total", "izq": "TOTAL", "der": "$7.090"})
    assert salida.startswith(b"\x1d!\x01")                   # doble alto, ancho normal
    fila = salida.split(b"\n")[0][len(b"\x1d!\x01\x1bE\x01"):]
    assert len(fila) == 48 and fila.startswith(b"TOTAL") and fila.endswith(b"$7.090")


def test_el_importe_no_se_recorta_nunca():
    fila = _ordenes({"tipo": "cols", "izq": "1 x Torta de mil hojas con manjar y nueces",
                     "der": "$13.500"}).split(b"\n")[0]
    assert len(fila) == 48 and fila.endswith(b"$13.500") and b"." in fila[:40]


def test_el_separador_llena_la_linea_segun_el_papel():
    assert _ordenes({"tipo": "separador"}, ancho=32) == b"-" * 32 + b"\n"
    assert _ordenes({"tipo": "separador"}, ancho=48) == b"-" * 48 + b"\n"


def test_la_letra_chica_usa_la_fuente_b_y_entra_mas_texto():
    salida = _ordenes({"tipo": "chico", "texto": "N" * 60})
    assert salida.startswith(b"\x1bM\x01")
    assert salida.count(b"\n") == 1                          # 60 caracteres caben en una fila


def test_los_bloques_conviven_con_los_renglones_de_siempre():
    crudo = windows._bytes_escpos(80, ["una linea", {"tipo": "aviso", "texto": "NO ES BOLETA"}])
    assert b"una linea\n" in crudo and b"NO ES BOLETA\n" in crudo
    assert crudo.endswith(b"\x1bd\x06\x1dVB\x00")            # avance y corte
