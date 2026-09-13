# Averiguar que habla la balanza del local, sin instalar nada.
#
# Esta pensado para correrse EN EL LOCAL, en el computador de la caja, sin repositorio, sin
# Python y sin permisos de administrador: solo usa lo que Windows ya trae. Guarda todo en un
# archivo de texto para poder mandarlo despues.
#
# Lo que busca, en orden de lo que mas ahorra:
#   1. Por que puerto le habla el punto de venta actual a la balanza. Es el atajo: ese
#      sistema ya lo hace todos los dias, asi que no hay que adivinar.
#   2. Que puertos tiene abiertos, de una lista corta de los habituales.
#   3. Si tiene pagina web propia, que suele traer la configuracion.

$ErrorActionPreference = "SilentlyContinue"
$salida = Join-Path $PSScriptRoot ("balanza-" + (Get-Date -Format "yyyy-MM-dd-HHmm") + ".txt")
$lineas = New-Object System.Collections.ArrayList

function Anotar($texto) {
    Write-Host $texto
    [void]$lineas.Add($texto)
}

Anotar "============================================================"
Anotar " LA BALANZA DEL LOCAL - que habla y por donde"
Anotar " $(Get-Date -Format 'dd-MM-yyyy HH:mm')"
Anotar "============================================================"
Anotar ""

# ---------------------------------------------------------------- la IP
$ip = Read-Host "Escribe la IP de la balanza (Enter si no la sabes)"

if ([string]::IsNullOrWhiteSpace($ip)) {
    Anotar "No se dio una IP. Estos son los equipos que este computador ha visto en la red:"
    Anotar ""
    $vecinos = arp -a | Select-String "dinámic|dynamic"
    foreach ($v in $vecinos) { Anotar ("   " + $v.ToString().Trim()) }
    Anotar ""
    Anotar "La balanza suele aparecer con una MAC que empieza distinto al resto."
    Anotar "Buscala tambien en el menu de red de la balanza, o en la lista de equipos"
    Anotar "conectados del router (a veces sale como DIGI o con su numero de serie)."
    $lineas | Set-Content -Path $salida -Encoding utf8
    Anotar ""
    Anotar "Guardado en: $salida"
    Read-Host "Enter para cerrar"
    exit
}

Anotar "Balanza: $ip"
Anotar ""

# ---------------------------------------------------------------- 1) el atajo
Anotar "------------------------------------------------------------"
Anotar "1) POR QUE PUERTO LE HABLA EL PUNTO DE VENTA ACTUAL"
Anotar "------------------------------------------------------------"
Anotar "Si el sistema de la caja esta abierto y recien escaneaste un ticket,"
Anotar "aca deberia aparecer su conexion a la balanza."
Anotar ""
$conexiones = netstat -n | Select-String ([regex]::Escape($ip))
if ($conexiones) {
    foreach ($c in $conexiones) { Anotar ("   " + $c.ToString().Trim()) }
    Anotar ""
    Anotar "   >>> El numero despues de los dos puntos, del lado de la balanza, es EL PUERTO."
    Anotar "       Con ese dato no hay que adivinar nada mas."
} else {
    Anotar "   (ninguna conexion ahora mismo)"
    Anotar ""
    Anotar "   No significa que no exista: puede que hable solo al escanear. Deja el"
    Anotar "   sistema abierto, escanea un ticket de la balanza y vuelve a correr esto."
}
Anotar ""

# ---------------------------------------------------------------- 2) los puertos
Anotar "------------------------------------------------------------"
Anotar "2) QUE PUERTOS TIENE ABIERTOS"
Anotar "------------------------------------------------------------"

$puertos = [ordered]@{
    21   = "FTP - archivos (el mejor caso: se bajan las ventas)"
    22   = "SSH"
    23   = "Telnet - consola de configuracion"
    80   = "web - pagina de configuracion"
    443  = "web segura"
    515  = "impresion LPR"
    631  = "impresion IPP"
    2000 = "puerto propio (DIGI y otras marcas lo usan)"
    3001 = "puerto propio"
    8000 = "web alternativa"
    8080 = "web alternativa"
    9100 = "impresion directa"
}

# GetEnumerator y no $puertos[$p]: en un diccionario ordenado, indexar con un numero
# lo toma como POSICION y no como clave, asi que la descripcion salia vacia.
$abiertos = @()
foreach ($par in $puertos.GetEnumerator()) {
    $r = Test-NetConnection -ComputerName $ip -Port $par.Key -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($r) {
        $abiertos += $par.Key
        Anotar ("   {0,5}  ABIERTO   {1}" -f $par.Key, $par.Value)
    }
}
if ($abiertos.Count -eq 0) {
    Anotar "   Ninguno de los habituales."
    Anotar ""
    Anotar "   Revisa que estes en la MISMA red que la balanza (no en la de invitados),"
    Anotar "   que este encendida, y que la IP sea la suya y no la de otro equipo."
}
Anotar ""

# ---------------------------------------------------------------- 3) la pagina
Anotar "------------------------------------------------------------"
Anotar "3) TIENE PAGINA WEB PROPIA?"
Anotar "------------------------------------------------------------"
$hubo = $false
foreach ($p in @(80, 8000, 8080, 443)) {
    if ($abiertos -notcontains $p) { continue }
    $hubo = $true
    $esquema = if ($p -eq 443) { "https" } else { "http" }
    $url = "${esquema}://${ip}:${p}/"
    try {
        $w = Invoke-WebRequest -Uri $url -TimeoutSec 5 -UseBasicParsing
        $titulo = ""
        if ($w.Content -match "<title>(.*?)</title>") { $titulo = $matches[1].Trim() }
        Anotar ("   $url  ->  HTTP " + $w.StatusCode + "  " + $titulo)
        Anotar "   >>> Abrela en el navegador: ahi suele estar la configuracion de la"
        Anotar "       etiqueta y, con suerte, una forma de exportar las ventas."
    } catch {
        Anotar ("   $url  ->  contesta, pero pide clave o no tiene pagina en la raiz")
    }
}
if (-not $hubo) { Anotar "   No hay ningun puerto web abierto." }
Anotar ""

# ---------------------------------------------------------------- que significa
Anotar "------------------------------------------------------------"
Anotar "QUE SIGNIFICA LO QUE SALIO"
Anotar "------------------------------------------------------------"
if ($abiertos -contains 21) {
    Anotar "   Hay FTP: es el mejor caso. Probablemente deja bajar las ventas como"
    Anotar "   archivo, y conectar la caja seria leer ese archivo. Dias de trabajo."
} elseif ($abiertos | Where-Object { @(80, 443, 8000, 8080) -contains $_ }) {
    Anotar "   Tiene pagina web propia. Hay donde mirar: entra y busca si se pueden"
    Anotar "   exportar las ventas o cambiar el codigo que imprime."
} elseif ($abiertos.Count -gt 0) {
    Anotar "   Solo puertos propios. El detalle del ticket viaja en un protocolo de la"
    Anotar "   marca: hay que sacarlo del manual o pedirselo al proveedor de la balanza."
} else {
    Anotar "   Sin puertos abiertos no se puede concluir nada todavia."
}
Anotar ""
Anotar "------------------------------------------------------------"
Anotar "LAS DOS PREGUNTAS DEL MENU DE LA BALANZA"
Anotar "------------------------------------------------------------"
Anotar "   Estas NO se contestan desde el computador, se miran en la balanza:"
Anotar ""
Anotar "   a) Puede imprimir un QR (o un Code 128) en vez del codigo de barras?"
Anotar "      Es la que mas ahorra. En el papel YA sale el detalle impreso, pero en"
Anotar "      un EAN-13 caben 13 digitos y se van en el prefijo, el numero de ticket"
Anotar "      y el total. En un QR si cabe el detalle completo. Si se puede, la caja"
Anotar "      lee todo del papel: sin red de por medio y con un solo escaneo."
Anotar ""
Anotar "   b) Puede imprimir una etiqueta POR PRODUCTO, con su codigo y el peso?"
Anotar "      Es el otro camino sin programar nada contra la balanza. El costo es de"
Anotar "      mostrador: una etiqueta por producto en vez de una por cliente."
Anotar ""
Anotar "   Se miran en la configuracion de la ETIQUETA o del CODIGO IMPRESO."
Anotar ""

$lineas | Set-Content -Path $salida -Encoding utf8
Anotar "============================================================"
Anotar " Guardado en: $salida"
Anotar " Mandame ese archivo y te digo que cuesta conectar la caja."
Anotar "============================================================"
Read-Host "Enter para cerrar"
