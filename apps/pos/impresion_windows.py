"""Impresión por el driver de Windows, aislada del proceso y de las ventas.

Solo recibe texto construido por el servidor. El script es fijo; nombres y texto
viajan como JSON por stdin, nunca como comandos. No reintenta: tras un timeout el
spooler puede haber aceptado el papel aunque no hayamos recibido su respuesta.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata


class ErrorImpresion(Exception):
    def __init__(self, mensaje: str, estado: int = 503):
        super().__init__(mensaje)
        self.estado = estado


# Un driver trabado no puede llenar el threadpool ni acumular papeles atrasados.
_ocupado = threading.Lock()
_consultando = threading.Lock()
_instalando = threading.Lock()

# También se comprueba el número de bytes: WritePrinter puede aceptar solo una
# parte. No reenviamos el resto ni el documento, porque podría duplicar el papel.
_CRUDO = r"""
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class ReciboCrudo {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct DOCINFO {
        public string pDocName, pOutputFile, pDataType;
    }
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool OpenPrinter(string nombre, out IntPtr h, IntPtr defecto);
    [DllImport("winspool.drv", SetLastError = true)]
    static extern bool ClosePrinter(IntPtr h);
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern int StartDocPrinter(IntPtr h, int nivel, ref DOCINFO doc);
    [DllImport("winspool.drv", SetLastError = true)]
    static extern bool StartPagePrinter(IntPtr h);
    [DllImport("winspool.drv", SetLastError = true)]
    static extern bool WritePrinter(IntPtr h, byte[] datos, int largo, out int escritos);
    [DllImport("winspool.drv", SetLastError = true)]
    static extern bool EndPagePrinter(IntPtr h);
    [DllImport("winspool.drv", SetLastError = true)]
    static extern bool EndDocPrinter(IntPtr h);
    [DllImport("winspool.drv", SetLastError = true)]
    static extern bool AbortPrinter(IntPtr h);
    static void Comprobar(bool ok) {
        if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public static void Enviar(string nombre, byte[] datos) {
        IntPtr h;
        Comprobar(OpenPrinter(nombre, out h, IntPtr.Zero));
        bool documento = false;
        try {
            var doc = new DOCINFO { pDocName = "Comprobante interno Kofe", pDataType = "RAW" };
            Comprobar(StartDocPrinter(h, 1, ref doc) != 0);
            documento = true;
            Comprobar(StartPagePrinter(h));
            int escritos;
            Comprobar(WritePrinter(h, datos, datos.Length, out escritos));
            if (escritos != datos.Length) throw new InvalidOperationException("Envío incompleto");
            Comprobar(EndPagePrinter(h));
            Comprobar(EndDocPrinter(h));
            documento = false;
        } finally {
            if (documento) AbortPrinter(h);
            ClosePrinter(h);
        }
    }
}
"""
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
        @{nombre = $_.Name; puerto = $_.PortName; disponible = -not $virtual}
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
    if ($dato.accion -eq 'crudo') {
        Add-Type -TypeDefinition @'
__CRUDO__
'@
        [ReciboCrudo]::Enviar([string]$dato.impresora, [Convert]::FromBase64String($dato.bytes))
        @{ok = $true} | ConvertTo-Json -Compress
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
""".replace("__CRUDO__", _CRUDO)


_PUERTOS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $usados = @(Get-Printer | ForEach-Object { $_.PortName -split ',' } | ForEach-Object { $_.Trim() })
    # Solo puertos donde puede haber una impresora enchufada. COM, LPT, FILE y los
    # virtuales estan siempre ahi aunque no haya nada: ofrecerlos haria instalar una
    # impresora que no existe. Un USB con descripcion es el aparato que Windows vio.
    $libres = @(Get-PrinterPort | Where-Object {
        $usados -notcontains $_.Name -and
        ($_.Name -match '^(USB|WSD|IP_|TCPPort|\\)' -or
         ($_.Description -and $_.Description -notmatch '^(Puerto local|Local Port|Local Monitor)$')) -and
        $_.Name -notmatch '^(FILE:|PORTPROMPT:|NUL:|SHRFAX:|COM\d+:|LPT\d+:|Microsoft\.)'
    } | ForEach-Object {
        @{nombre = $_.Name; descripcion = $_.Description}
    })
    @{puertos = $libres} | ConvertTo-Json -Compress -Depth 4
} catch { @{error = 'consulta'} | ConvertTo-Json -Compress }
"""

# RunAs no permite redirigir stdin. Un canal local entrega el JSON DESPUÉS del
# permiso de Windows; no dejamos scripts ni datos de instalación en archivos.
# Solo el GUID creado aquí entra al comando elevado, nunca el puerto o nombre.
_INSTALAR = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$canal = 'KofeImpresora-' + [guid]::NewGuid().ToString('N')
$elevado = @'
$ErrorActionPreference = 'Stop'
$cliente = New-Object System.IO.Pipes.NamedPipeClientStream('.', $canal, [System.IO.Pipes.PipeDirection]::InOut)
try {
    # Si la caja dejó de esperar mientras el dueño decidía, no se instala nada.
    $cliente.Connect(5000)
    $lector = New-Object System.IO.StreamReader($cliente)
    $escritor = New-Object System.IO.StreamWriter($cliente)
    $escritor.AutoFlush = $true
    $dato = $lector.ReadLine() | ConvertFrom-Json
    $respuesta = @{error = 'instalacion'}
    if ($null -eq $dato) { throw 'Solicitud cerrada' }
    if ([string]$dato.nombre -cnotmatch '\A[A-Za-z0-9 ._()-]{1,60}\z' -or
            -not ([string]$dato.nombre).Trim()) {
        $respuesta = @{error = 'nombre'}
    } else {
        $impresoras = @(Get-Printer)
        $usados = @($impresoras | ForEach-Object { $_.PortName -split ',' } | ForEach-Object { $_.Trim() })
        $puerto = @(Get-PrinterPort | Where-Object { $_.Name -ceq $dato.puerto })
        if ($puerto.Count -ne 1 -or $usados -contains $dato.puerto) {
            $respuesta = @{error = 'puerto'}
        } elseif (@($impresoras | Where-Object { $_.Name -eq $dato.nombre }).Count) {
            $respuesta = @{error = 'existe'}
        } else {
            if (-not @(Get-PrinterDriver | Where-Object { $_.Name -eq 'Generic / Text Only' }).Count) {
                Add-PrinterDriver -Name 'Generic / Text Only'
            }
            # Se vuelve a comprobar el puerto tras instalar el driver, por si
            # Windows terminó de reconocer la impresora durante el permiso.
            $usados = @(Get-Printer | ForEach-Object { $_.PortName -split ',' } | ForEach-Object { $_.Trim() })
            if ($usados -contains $dato.puerto) {
                $respuesta = @{error = 'puerto'}
            } else {
                Add-Printer -Name $dato.nombre -DriverName 'Generic / Text Only' -PortName $dato.puerto
                $respuesta = @{ok = $true; nombre = $dato.nombre}
            }
        }
    }
    $escritor.WriteLine(($respuesta | ConvertTo-Json -Compress))
} catch {
    if ($escritor) {
        $escritor.WriteLine((@{error = 'instalacion'} | ConvertTo-Json -Compress))
    }
} finally { $cliente.Dispose() }
'@
$servidor = $null
try {
    $dato = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $seguridad = New-Object System.IO.Pipes.PipeSecurity
    $usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $administradores = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
    foreach ($identidad in @($usuario, $administradores)) {
        $regla = New-Object System.IO.Pipes.PipeAccessRule($identidad, 'FullControl', 'Allow')
        $seguridad.AddAccessRule($regla)
    }
    $servidor = New-Object System.IO.Pipes.NamedPipeServerStream($canal, 'InOut', 1,
        'Byte', 'Asynchronous', 4096, 4096, $seguridad)
    $codigo = "`$canal = '$canal'`n" + $elevado
    $codificado = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($codigo))
    $proceso = Start-Process -FilePath "$PSHOME\powershell.exe" -Verb RunAs -WindowStyle Hidden -PassThru `
        -ArgumentList @('-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', $codificado)
    $conexion = $servidor.BeginWaitForConnection($null, $null)
    if (-not $conexion.AsyncWaitHandle.WaitOne(100000)) { throw 'Tiempo agotado' }
    $servidor.EndWaitForConnection($conexion)
    $lector = New-Object System.IO.StreamReader($servidor)
    $escritor = New-Object System.IO.StreamWriter($servidor)
    $escritor.AutoFlush = $true
    $escritor.WriteLine(($dato | ConvertTo-Json -Compress))
    $respuesta = $lector.ReadLine()
    if (-not $respuesta) { throw 'Sin respuesta' }
    [Console]::WriteLine($respuesta)
} catch {
    $excepcion = $_.Exception
    while ($excepcion.InnerException) { $excepcion = $excepcion.InnerException }
    if ($excepcion.NativeErrorCode -eq 1223) {
        @{error = 'cancelado'} | ConvertTo-Json -Compress
    } else { @{error = 'instalacion'} | ConvertTo-Json -Compress }
} finally { if ($servidor) { $servidor.Dispose() } }
"""


def disponible() -> bool:
    return sys.platform == "win32"


def _ejecutar(datos: dict, espera: float | None = None) -> dict:
    if not disponible():
        raise ErrorImpresion("La impresión directa requiere Windows en el computador de la caja.")
    accion = datos["accion"]
    imprimir = accion in ("imprimir", "crudo")
    instalando = accion == "instalar"
    cerrojo = _ocupado if imprimir else _instalando if instalando else _consultando
    if not cerrojo.acquire(blocking=False):
        if instalando:
            raise ErrorImpresion("Ya hay una instalación en curso. Espera a que termine.", 409)
        raise ErrorImpresion("La impresora está atendiendo otra solicitud. No se envió este papel.", 409)
    try:
        ejecutable = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                  "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        script = _PUERTOS if accion == "puertos" else _INSTALAR if instalando else _SCRIPT
        resultado = subprocess.run(
            [ejecutable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
            input=json.dumps(datos, ensure_ascii=True), capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            # La PRIMERA llamada de PowerShell en un equipo recien instalado tarda en
            # preparar sus modulos ("Preparando modulos para el primer uso"): con 10 s,
            # la primera consulta del local fallaba con un error que no decia nada.
            timeout=espera if espera is not None else 120 if instalando else 20 if imprimir else 30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )
        salida = json.loads(resultado.stdout.lstrip("\ufeff")) if resultado.returncode == 0 else {}
        if not isinstance(salida, dict):
            raise ValueError("Respuesta de impresora inválida")
        error = salida.get("error")
        errores_instalacion = {
            "cancelado": ("Se canceló el permiso de Windows. No se instaló la impresora.", 409),
            "puerto": ("El puerto ya no está libre. Actualiza la lista de impresoras.", 409),
            "existe": ("Ya existe una impresora con ese nombre. Actualiza la lista.", 409),
            "nombre": ("El nombre de la impresora no es válido.", 422),
        }
        if instalando and error in errores_instalacion:
            raise ErrorImpresion(*errores_instalacion[error])
        if error == "ausente":
            raise ErrorImpresion("La impresora elegida ya no está instalada. Revisa Configurar.", 409)
        if error == "archivo":
            raise ErrorImpresion("Elige una impresora de papel: PDF, XPS y fax requieren un diálogo.", 422)
        if instalando and error == "instalacion":
            raise ErrorImpresion("Windows no pudo completar la instalación con Generic / Text Only. "
                                 "Revisa el servicio de impresión y actualiza la lista antes de repetir.")
        clave = "puertos" if accion == "puertos" else "impresoras"
        if error or ((imprimir or instalando) and salida.get("ok") is not True) or (
                not imprimir and not instalando and not isinstance(salida.get(clave), list)):
            raise ValueError("El driver no confirmó la solicitud")
        return salida
    except ErrorImpresion:
        raise
    except (subprocess.TimeoutExpired, OSError, ValueError):
        if instalando:
            raise ErrorImpresion("Windows no confirmó la instalación en el plazo de 120 segundos. "
                                 "Actualiza la lista antes de intentarlo otra vez; no se reintentó.") from None
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


def _validar(impresora: str, papel: int, lineas: list[str]):
    if papel not in (58, 80) or not impresora or len(impresora) > 256:
        raise ErrorImpresion("Elige una impresora y papel de 58 u 80 mm.", 422)
    if not lineas or len(lineas) > 1000 or sum(map(len, lineas)) > 32000:
        raise ErrorImpresion("Este comprobante es demasiado largo para la impresión directa.", 422)


def imprimir(impresora: str, papel: int, lineas: list[str]) -> dict:
    _validar(impresora, papel, lineas)
    _ejecutar({"accion": "imprimir", "impresora": impresora, "papel": papel, "lineas": lineas})
    return {"ok": True, "detalle": "Enviado a la cola de Windows. Revisa que haya salido el papel."}


def _texto_cp850(texto: str) -> str:
    partes = []
    for caracter in unicodedata.normalize("NFC", texto):
        if caracter == "·":
            caracter = "-"
        # Ni ESC, ni saltos incrustados, ni otros controles de la impresora
        # pueden venir de un producto. Solo nuestras órdenes llegan al spooler.
        if not caracter.isprintable():
            partes.append(" ")
            continue
        try:
            caracter.encode("cp850")
        except UnicodeEncodeError:
            base = "".join(c for c in unicodedata.normalize("NFD", caracter)
                           if unicodedata.category(c) != "Mn")
            caracter = base if len(base) == 1 and base.isascii() and base.isalpha() else " "
        partes.append(caracter)
    return "".join(partes)


def _en_columnas(izquierda: str, derecha: str, ancho: int) -> list[str]:
    """El importe entero a la derecha; si no cabe todo, se abrevia el nombre."""
    espacio = ancho - len(derecha) - 1
    if espacio < 3:
        texto = (izquierda + " " + derecha).strip()
        return [texto[i:i + ancho] for i in range(0, len(texto), ancho)]
    if len(izquierda) > espacio:
        izquierda = izquierda[:espacio - 1] + "."
    return [izquierda + " " * (ancho - len(izquierda) - len(derecha)) + derecha]


def _bloque_a_bytes(bloque, ancho: int) -> bytes:
    """Un bloque del comprobante como bytes ESC/POS, ya en su tamaño y alineación.

    Cada bloque termina volviendo a lo normal (tamaño, negrita, fuente y
    alineación): así un título grande no se le pega al siguiente comprobante si
    algo se corta a la mitad.
    """
    if isinstance(bloque, str):
        bloque = {"tipo": "texto", "texto": bloque}
    tipo = bloque.get("tipo", "texto")
    salida = bytearray()

    if tipo == "blanco":
        return b"\n"
    if tipo == "separador":
        return _texto_cp850("-" * ancho).encode("cp850") + b"\n"

    if tipo == "titulo":            # nombre del local: doble alto y ancho, centrado
        salida.extend(b"\x1ba\x01\x1d!\x11\x1bE\x01")
        filas = [_texto_cp850(bloque["texto"])[: max(1, ancho // 2)]]
    elif tipo == "centro":
        salida.extend(b"\x1ba\x01")
        filas = [_texto_cp850(bloque["texto"])[:ancho]]
    elif tipo == "aviso":           # NO ES BOLETA: centrado, doble alto y negrita
        salida.extend(b"\x1ba\x01\x1d!\x01\x1bE\x01")
        filas = [_texto_cp850(bloque["texto"])[:ancho]]
    elif tipo == "chico":           # la fuente B entra casi al doble por línea
        salida.extend(b"\x1bM\x01")
        chico = ancho * 4 // 3
        texto = _texto_cp850(bloque["texto"])
        filas = [texto[i:i + chico] for i in range(0, len(texto), chico)] or [""]
        if bloque.get("centrado"):
            salida.extend(b"\x1ba\x01")
    elif tipo == "total":           # TOTAL: doble ALTO (el ancho no cambia)
        salida.extend(b"\x1d!\x01\x1bE\x01")
        filas = _en_columnas(_texto_cp850(bloque["izq"]), _texto_cp850(bloque["der"]), ancho)
    elif tipo == "cols":
        filas = _en_columnas(_texto_cp850(bloque["izq"]), _texto_cp850(bloque["der"]), ancho)
    else:
        texto = _texto_cp850(bloque.get("texto", ""))
        filas = [texto[i:i + ancho] for i in range(0, len(texto), ancho)] or [""]

    for fila in filas:
        salida.extend(fila.encode("cp850") + b"\n")
    salida.extend(b"\x1d!\x00\x1bE\x00\x1bM\x00\x1ba\x00")
    return bytes(salida)


def _bytes_escpos(papel: int, lineas: list, cortar: bool = True) -> bytes:
    ancho = 32 if papel == 58 else 48
    salida = bytearray(b"\x1b@\x1bt\x02")  # CP850, verificada en la Sewoo.
    if any(isinstance(b, dict) for b in lineas):
        # Comprobante armado por el servidor: cada bloque sabe cómo se ve.
        for bloque in lineas:
            salida.extend(_bloque_a_bytes(bloque, ancho))
        salida.extend(b"\x1bd\x06")
        if cortar:
            salida.extend(b"\x1dVB\x00")
        return bytes(salida)
    for indice, original in enumerate(lineas):
        texto = _texto_cp850(original)
        # Las dos columnas vienen de los </td> de NUESTRA plantilla. El precio
        # ya está calculado; se conserva entero y se abrevia solo el nombre.
        columnas = texto.rsplit("  ", 1)
        if len(columnas) == 2 and re.fullmatch(r"-?\$[\d.]+", columnas[1]):
            nombre, importe = columnas
            espacio = ancho - len(importe) - 1
            if espacio >= 3:
                if len(nombre) > espacio:
                    nombre = nombre[:espacio - 3] + "..."
                filas = [nombre + " " * (ancho - len(nombre) - len(importe)) + importe]
            else:
                # Un importe extraordinario tampoco se pierde ni se trunca.
                filas = [texto[i:i + ancho] for i in range(0, len(texto), ancho)]
        else:
            filas = [texto[i:i + ancho] for i in range(0, len(texto), ancho)] or [""]
        aviso = original == "NO ES BOLETA"
        if indice == 0 or aviso:
            salida.extend(b"\x1ba\x01")
        if aviso:
            salida.extend(b"\x1d!\x01")
        for fila in filas:
            salida.extend(fila.encode("cp850") + b"\n")
        # Cada bloque vuelve a alineación izquierda y tamaño normal, también
        # cuando no se corta, para no contaminar el siguiente comprobante.
        salida.extend(b"\x1d!\x00\x1ba\x00")
    salida.extend(b"\x1bd\x06")
    if cortar:
        salida.extend(b"\x1dVB\x00")
    return bytes(salida)


def imprimir_crudo(impresora: str, papel: int, lineas: list[str], cortar: bool = True) -> dict:
    _validar(impresora, papel, lineas)
    datos = _bytes_escpos(papel, lineas, cortar)
    _ejecutar({"accion": "crudo", "impresora": impresora,
               "bytes": base64.b64encode(datos).decode("ascii")})
    return {"ok": True, "detalle": "Enviado a la impresora de tickets. Revisa que haya salido el papel."}


def puertos_sin_impresora() -> dict:
    if not disponible():
        return {"disponible": False, "puertos": []}
    return {"disponible": True, "puertos": _ejecutar({"accion": "puertos"})["puertos"]}


def instalar(puerto: str, nombre: str) -> dict:
    inicio = time.monotonic()
    if not re.fullmatch(r"[A-Za-z0-9 ._()-]{1,60}", nombre) or not nombre.strip():
        raise ErrorImpresion("Usa un nombre de 1 a 60 letras sin tildes, números, espacios o ._()-.", 422)
    if not any(p["nombre"] == puerto for p in puertos_sin_impresora()["puertos"]):
        raise ErrorImpresion("El puerto ya no está libre. Actualiza la lista de impresoras.", 409)
    # Los 120 segundos incluyen consultar el puerto, el permiso y la instalación.
    restante = 120 - (time.monotonic() - inicio)
    if restante <= 0:
        raise ErrorImpresion("Se agotó el tiempo para consultar el puerto. No se inició la instalación.")
    _ejecutar({"accion": "instalar", "puerto": puerto, "nombre": nombre}, espera=restante)
    return {"ok": True, "nombre": nombre, "detalle": "Impresora instalada. Imprime una prueba."}
