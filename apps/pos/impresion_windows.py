"""Impresión por el driver de Windows, aislada del proceso y de las ventas.

Solo recibe texto construido por el servidor. El script es fijo; nombres y texto
viajan como JSON por stdin, nunca como comandos. No reintenta: tras un timeout el
spooler puede haber aceptado el papel aunque no hayamos recibido su respuesta.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading


class ErrorImpresion(Exception):
    def __init__(self, mensaje: str, estado: int = 503):
        super().__init__(mensaje)
        self.estado = estado


# Un driver trabado no puede llenar el threadpool ni acumular papeles atrasados.
_ocupado = threading.Lock()
_consultando = threading.Lock()
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $dato = [Console]::In.ReadToEnd() | ConvertFrom-Json
    Add-Type -AssemblyName System.Drawing
    # Los puertos de archivo / PDF necesitan un diálogo: no son una caja térmica.
    $dispositivos = @(Get-CimInstance -ClassName Win32_Printer)
    $instaladas = @([System.Drawing.Printing.PrinterSettings]::InstalledPrinters)
    $lista = @($dispositivos | Where-Object { $instaladas -ccontains $_.Name } | ForEach-Object {
        $virtual = $_.PortName -match '^(FILE:|PORTPROMPT:|NUL:|SHRFAX:|Microsoft\.Office\.OneNote)' -or
                   $_.DriverName -match 'Microsoft Print To PDF|XPS Document|OneNote|Fax' -or
                   $_.Name -match 'OneNote|Microsoft Print To PDF|Microsoft XPS Document Writer'
        @{nombre = $_.Name; disponible = -not $virtual}
    })
    if ($dato.accion -eq 'listar') {
        @{impresoras = $lista} | ConvertTo-Json -Compress -Depth 4
        exit 0
    }
    $elegida = @($lista | Where-Object { $_.nombre -ceq $dato.impresora })
    if ($elegida.Count -ne 1) {
        @{error = 'ausente'} | ConvertTo-Json -Compress
        exit 0
    }
    if (-not $elegida[0].disponible) {
        @{error = 'archivo'} | ConvertTo-Json -Compress
        exit 0
    }
    Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Printing;
public static class ReciboCaja {
    public static void Imprimir(string nombre, int papel, string[] lineas) {
        using (var doc = new PrintDocument())
        using (var font = new Font("Consolas", 8, FontStyle.Regular))
        using (var formato = new StringFormat(StringFormat.GenericTypographic)) {
            doc.PrinterSettings.PrinterName = nombre;
            if (!doc.PrinterSettings.IsValid) throw new InvalidOperationException();
            doc.PrinterSettings.Copies = 1;
            doc.PrinterSettings.PrintToFile = false;
            doc.PrinterSettings.Duplex = Duplex.Simplex;
            doc.PrintController = new StandardPrintController();
            doc.DocumentName = "Comprobante interno Kofe";
            // PaperSize / Margins usan centésimas de pulgada, no milímetros.
            int ancho = (int)Math.Round(papel * 100.0 / 25.4);
            int alto = Math.Min(1102, Math.Max(160, lineas.Length * 15 + 32));
            doc.DefaultPageSettings.PaperSize = new PaperSize("Recibo", ancho, alto);
            doc.DefaultPageSettings.Margins = new Margins(12, 12, 12, 12);
            doc.DefaultPageSettings.Landscape = false;
            int fila = 0, offset = 0, paginas = 0;
            formato.FormatFlags |= StringFormatFlags.MeasureTrailingSpaces;
            doc.PrintPage += (sender, e) => {
                if (++paginas > 20) throw new InvalidOperationException();
                var g = e.Graphics;
                g.PageUnit = GraphicsUnit.Display;
                g.TranslateTransform(-e.PageSettings.HardMarginX, -e.PageSettings.HardMarginY);
                var area = RectangleF.Intersect(e.MarginBounds, e.PageSettings.PrintableArea);
                // Algunos drivers ignoran el papel personalizado. Nunca se usa
                // un ancho mayor al elegido ni se corta lo que no cabe: se pagina.
                area.Width = Math.Min(area.Width, ancho - 24);
                float paso = font.GetHeight(g) * 1.25f;
                if (area.Width < 40 || area.Height < paso) throw new InvalidOperationException();
                float y = area.Top;
                while (fila < lineas.Length && y + paso <= area.Bottom) {
                    string resto = lineas[fila].Substring(offset);
                    int n = resto.Length;
                    while (n > 0 && g.MeasureString(resto.Substring(0, n), font,
                            Int32.MaxValue, formato).Width > area.Width) n--;
                    if (n > 0 && n < resto.Length && Char.IsHighSurrogate(resto[n - 1])) n--;
                    if (n == 0 && resto.Length > 0) throw new InvalidOperationException();
                    g.DrawString(resto.Substring(0, n), font, Brushes.Black, area.Left, y, formato);
                    offset += n;
                    if (offset == lineas[fila].Length) { fila++; offset = 0; }
                    y += paso;
                }
                e.HasMorePages = fila < lineas.Length;
            };
            doc.Print();
        }
    }
}
'@
    [ReciboCaja]::Imprimir([string]$dato.impresora, [int]$dato.papel, [string[]]$dato.lineas)
    @{ok = $true} | ConvertTo-Json -Compress
} catch {
    @{error = 'driver'} | ConvertTo-Json -Compress
}
"""


def disponible() -> bool:
    return sys.platform == "win32"


def _ejecutar(datos: dict) -> dict:
    if not disponible():
        raise ErrorImpresion("La impresión directa requiere Windows en el computador de la caja.")
    imprimir = datos["accion"] == "imprimir"
    cerrojo = _ocupado if imprimir else _consultando
    if not cerrojo.acquire(blocking=False):
        raise ErrorImpresion("La impresora está atendiendo otra solicitud. No se envió este papel.", 409)
    try:
        ejecutable = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                  "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        resultado = subprocess.run(
            [ejecutable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")],
            input=json.dumps(datos, ensure_ascii=True), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=20 if imprimir else 10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )
        salida = json.loads(resultado.stdout.lstrip("\ufeff")) if resultado.returncode == 0 else {}
        if not isinstance(salida, dict):
            raise ValueError("Respuesta de impresora inválida")
        error = salida.get("error")
        if error == "ausente":
            raise ErrorImpresion("La impresora elegida ya no está instalada. Revisa Configurar.", 409)
        if error == "archivo":
            raise ErrorImpresion("Elige una impresora de papel: PDF, XPS y fax requieren un diálogo.", 422)
        if error or (imprimir and salida.get("ok") is not True) or (not imprimir and "impresoras" not in salida):
            raise ValueError("El driver no confirmó la solicitud")
        return salida
    except ErrorImpresion:
        raise
    except (subprocess.TimeoutExpired, OSError, ValueError):
        if imprimir:
            raise ErrorImpresion("Windows no confirmó la impresión. El papel podría estar en la cola; "
                                 "revísala antes de volver a imprimir. No se reintentó.") from None
        raise ErrorImpresion("No se pudo consultar las impresoras de Windows. Revisa el servicio "
                             "de impresión e intenta actualizar la lista.") from None
    finally:
        cerrojo.release()


def listar() -> dict:
    if not disponible():
        return {"disponible": False, "impresoras": [],
                "detalle": "La impresión directa requiere Windows en el computador de la caja."}
    salida = _ejecutar({"accion": "listar"})
    return {"disponible": True, "impresoras": salida["impresoras"]}


def imprimir(impresora: str, papel: int, lineas: list[str]) -> dict:
    if papel not in (58, 80) or not impresora or len(impresora) > 256:
        raise ErrorImpresion("Elige una impresora y papel de 58 u 80 mm.", 422)
    if not lineas or len(lineas) > 1000 or sum(map(len, lineas)) > 32000:
        raise ErrorImpresion("Este comprobante es demasiado largo para la impresión directa.", 422)
    _ejecutar({"accion": "imprimir", "impresora": impresora, "papel": papel, "lineas": lineas})
    return {"ok": True, "detalle": "Enviado a la cola de Windows. Revisa que haya salido el papel."}
