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

# iex no tiene carpeta de script; el Escritorio permite encontrar el informe en el local.
$carpeta = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($carpeta)) {
    $carpeta = [Environment]::GetFolderPath('Desktop')
    if (-not $carpeta -or -not [System.IO.Directory]::Exists($carpeta)) { $carpeta = $env:TEMP }
}
$salida = Join-Path $carpeta ("balanza-" + (Get-Date -Format "yyyy-MM-dd-HHmmss-fff") + ".txt")
$lineas = New-Object System.Collections.ArrayList

function Anotar($texto) {
    Write-Host $texto
    [void]$lineas.Add($texto)
}

$errorPuertoAnotado = $false
function Probar-Puerto($direccion, [int]$puerto, [int]$espera = 1500) {
    $cliente = $null
    try {
        $cliente = New-Object System.Net.Sockets.TcpClient
        # Un puerto filtrado no debe dejar esperando al encargado durante 20 segundos.
        $tarea = $cliente.ConnectAsync($direccion, $puerto)
        if (-not $tarea.Wait($espera)) { return $false }
        return $cliente.Connected
    } catch {
        # Wait envuelve el error del socket; mostrar el primero evita confundir una
        # falla del diagnostico con todos los puertos cerrados, sin llenar el informe.
        $causa = $_.Exception.GetBaseException()
        $normal = ($causa -is [System.Net.Sockets.SocketException]) -and
            ($causa.SocketErrorCode -in @('ConnectionRefused', 'TimedOut'))
        if (-not $normal -and -not $script:errorPuertoAnotado) {
            Anotar ("   Error al probar ${direccion}:${puerto}: " + $causa.Message)
            $script:errorPuertoAnotado = $true
        }
        return $false
    } finally {
        if ($null -ne $cliente) { $cliente.Close() }
    }
}

function Es-Privada($direccion) {
    return $direccion -match '^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)'
}

function Leer-Conexiones {
    try {
        return @(Get-NetTCPConnection -ErrorAction Stop | Where-Object { $_.State -notin @('Listen', 'Bound') })
    } catch {
        Anotar ("   Get-NetTCPConnection no disponible: " + $_.Exception.Message)
        Anotar "   Se intenta con netstat -ano."
    }
    try {
        $datos = netstat -ano 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($datos -join ' ') }
        foreach ($fila in $datos) {
            # Las consultas breves quedan cerradas antes de abrir esta herramienta.
            if ($fila -match '^\s*TCP\s+(\d+\.\d+\.\d+\.\d+):(\d+)\s+(\d+\.\d+\.\d+\.\d+):(\d+)\s+(\S+)\s+(\d+)\s*$') {
                if ($matches[5] -in @('LISTENING', 'ESCUCHANDO', 'Listen', 'Bound')) { continue }
                [pscustomobject]@{ LocalAddress = $matches[1]; LocalPort = [int]$matches[2]; RemoteAddress = $matches[3]; RemotePort = [int]$matches[4]; State = $matches[5]; OwningProcess = [int]$matches[6] }
            }
        }
    } catch {
        Anotar ("   No se pudieron leer las conexiones: " + $_.Exception.Message)
    }
}

Anotar "============================================================"
Anotar " LA BALANZA DEL LOCAL - que habla y por donde"
Anotar " $(Get-Date -Format 'dd-MM-yyyy HH:mm')"
Anotar "============================================================"
Anotar ""

# ---------------------------------------------------------------- 0) descubrir sin IP
Anotar "0) CONEXIONES DE ESTE COMPUTADOR A LA RED DEL LOCAL"
Anotar "Si el sistema de la caja esta abierto y recien escaneaste un ticket,"
Anotar "la balanza suele ser una de las conexiones marcadas como CANDIDATA."
Anotar "La marca orienta la busqueda; no confirma que sea la balanza."
# Puertos comunes que no bastan para proponer una balanza: web, bases de datos, impresion,
# y los de los aparatos de la casa o la oficina (Chromecast 8008/8009, descubrimiento de
# red 1900/5353). Probado en un computador con Chromecast en la red: sin este filtro la
# IP propuesta era la del Chromecast.
$puertosComunes = @(53, 80, 139, 443, 445, 1433, 1434, 1521, 1900, 3050, 3306, 3389, 5432, 5353, 7000, 8008, 8009, 9100)
# Programas que abren conexiones en la red local y no son el sistema de la caja.
$programasComunes = @('chrome', 'msedge', 'firefox', 'opera', 'brave', 'iexplore', 'Spotify',
    'ChatGPT', 'Teams', 'ms-teams', 'OneDrive', 'Dropbox', 'GoogleDriveFS', 'WhatsApp',
    'Discord', 'Zoom', 'AnyDesk', 'TeamViewer', 'svchost', 'System', 'explorer', 'lsass',
    'SearchHost', 'PhoneExperienceHost', 'CrossDeviceService')

$vistas = @{}
$candidatas = @()
# La caja puede hablar consigo misma por su IP de red, por ejemplo con su base de datos.
$ipsPropias = @('127.0.0.1')
try {
    $ipsPropias += @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | ForEach-Object { $_.IPAddress })
} catch {
    try {
        $ipsPropias += @([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | ForEach-Object {
            $_.GetIPProperties().UnicastAddresses | ForEach-Object { $_.Address.ToString() }
        })
    } catch { Anotar ("   No se pudieron identificar todas las IPs propias: " + $_.Exception.Message) }
}
$conexionesLocales = @(Leer-Conexiones | Where-Object { Es-Privada $_.RemoteAddress })
foreach ($conexion in $conexionesLocales) {
    $nombre = "desconocido"
    try {
        $nombre = (Get-Process -Id $conexion.OwningProcess -ErrorAction Stop).ProcessName
    } catch { }
    # La misma conexion aparece varias veces (una por socket); se muestra una sola.
    $clave = "{0}:{1}:{2}:{3}:{4}" -f $conexion.RemoteAddress, $conexion.RemotePort, $nombre, $conexion.LocalPort, $conexion.State
    if ($vistas.ContainsKey($clave)) { continue }
    $vistas[$clave] = $true

    $comunPuerto = ($conexion.RemotePort -in $puertosComunes) -or ($conexion.RemotePort -ge 49152)
    $comunPrograma = ($conexion.OwningProcess -ne 0) -and (@($programasComunes | Where-Object { $nombre -like "$_*" }).Count -gt 0)
    $propia = ($conexion.RemoteAddress -in $ipsPropias) -or ($conexion.LocalAddress -eq $conexion.RemoteAddress)
    $entrante = ($conexion.LocalPort -gt 0) -and ($conexion.LocalPort -lt 49152) -and ($conexion.RemotePort -ge 49152)
    $marca = ""
    if (-not $propia -and -not $comunPrograma -and (-not $comunPuerto -or $entrante)) {
        $marca = " CANDIDATA"
        $candidatas += $conexion
    }
    # El puerto LOCAL tambien va: si es la balanza la que se conecta al computador, el
    # puerto que importa es el de este lado y el de alla es uno cualquiera.
    $estado = [string]$conexion.State
    if ($estado -match '^(TimeWait|TIME_WAIT)$') { $estado += ' (recien cerrada)' }
    if ($estado -match '^(SynSent|SYN_SENT)$') { $estado += ' (intentando conectar)' }
    Anotar ("   {0}:{1}  (local {5}:{6})  proceso: {2} (PID {3}){4}  estado: {7}" -f $conexion.RemoteAddress, $conexion.RemotePort, $nombre, $conexion.OwningProcess, $marca, $conexion.LocalAddress, $conexion.LocalPort, $estado)
    if ($marca -and $entrante) { Anotar ("      la balanza se conectaria a este PC en el puerto " + $conexion.LocalPort) }
}
if ($conexionesLocales.Count -eq 0) { Anotar "   (ninguna conexion privada visible ahora mismo)" }
elseif ($candidatas.Count -eq 0) {
    Anotar "   Ninguna cumple el filtro: pueden ser conexiones propias o de servicios comunes."
    Anotar "   Con el sistema de la caja abierto y un ticket recien escaneado deberia"
    Anotar "   aparecer una marcada CANDIDATA. Si no, puede que hable solo en el momento."
}
Anotar ""

# ---------------------------------------------------------------- la IP
# Una IP con varios sockets sigue siendo una sola opcion; con varias no se adivina.
$opciones = @($candidatas | Sort-Object @{Expression = { if ($_.RemotePort -eq 2000 -or $_.LocalPort -eq 2000) { 0 } else { 1 } }}, RemoteAddress | ForEach-Object { $_.RemoteAddress } | Select-Object -Unique)
$predeterminada = if ($opciones.Count -eq 1) { $opciones[0] } else { "" }
if ($opciones.Count -gt 1) {
    for ($i = 0; $i -lt $opciones.Count; $i++) { Anotar ("   {0}) {1}" -f ($i + 1), $opciones[$i]) }
}
$pregunta = if ($predeterminada) { "IP o IP:puerto (Enter acepta $predeterminada; v busca vecinos)" } elseif ($opciones.Count -gt 1) { "Numero de candidata, IP o IP:puerto (v busca vecinos)" } else { "IP o IP:puerto (Enter o v busca vecinos)" }
$puertoEscrito = 0
while ($true) {
    $ip = (Read-Host $pregunta).Trim()
    if ($ip -eq 'v') { $ip = ''; break }
    if (-not $ip) {
        if ($opciones.Count -gt 1) { Anotar "Elige un numero o escribe v para buscar vecinos."; continue }
        $ip = $predeterminada
        if (-not $ip) { break }
    }
    $numero = 0
    if ($opciones.Count -gt 1 -and [int]::TryParse($ip, [ref]$numero) -and $numero -ge 1 -and $numero -le $opciones.Count) { $ip = $opciones[$numero - 1] }
    $partes = $ip.Split(':')
    $direccionValidada = $null
    $puertoEscrito = 0
    $valida = $partes.Count -le 2 -and $partes[0] -match '^\d{1,3}(\.\d{1,3}){3}$' -and [System.Net.IPAddress]::TryParse($partes[0], [ref]$direccionValidada)
    if ($partes.Count -eq 2) { $valida = $valida -and [int]::TryParse($partes[1], [ref]$puertoEscrito) -and $puertoEscrito -ge 1 -and $puertoEscrito -le 65535 }
    if ($valida) { $ip = $direccionValidada.ToString(); break }
    Anotar "IP no valida. Escribe cuatro octetos, por ejemplo 192.168.1.50 o 192.168.1.50:2000 (puerto de 1 a 65535)."
}

if ([string]::IsNullOrWhiteSpace($ip)) {
    Anotar "No se dio una IP. Estos son los equipos que este computador ha visto en la red:"
    Anotar ""
    $direcciones = @()
    try {
        $tabla = arp -a 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($tabla -join ' ') }
        # El punto admite la vocal acentuada incluso con otra pagina de codigos.
        $vecinos = @($tabla | Select-String 'din.mic|dynamic')
        foreach ($v in $vecinos) {
            Anotar ("   " + $v.ToString().Trim())
            if ($v.ToString() -match '^\s*(\d+\.\d+\.\d+\.\d+)\s+') { $direcciones += $matches[1] }
        }
    } catch {
        Anotar ("   No se pudo leer ARP: " + $_.Exception.Message)
    }
    $direcciones = @($direcciones | Select-Object -Unique | Select-Object -First 60)
    Anotar ""
    Anotar "Probando 2000, 80 y 21 en hasta 60 vecinos dinamicos (puede tardar unos 90 segundos)."
    $respuestas = 0
    foreach ($direccion in $direcciones) {
        foreach ($puerto in @(2000, 80, 21)) {
            if (Probar-Puerto $direccion $puerto 500) {
                Anotar "   ${direccion}:${puerto}  ABIERTO"
                $respuestas++
            }
        }
    }
    if ($respuestas -eq 0) { Anotar "   Ningun vecino contesto en esos puertos." }
    Anotar ""
    Anotar "La balanza suele aparecer con una MAC que empieza distinto al resto."
    Anotar "Buscala tambien en el menu de red de la balanza, o en la lista de equipos"
    Anotar "conectados del router (a veces sale como DIGI o con su numero de serie)."
} else {

Anotar "Balanza: $ip"
Anotar ""

# ---------------------------------------------------------------- 1) el atajo
Anotar "------------------------------------------------------------"
Anotar "1) POR QUE PUERTO LE HABLA EL PUNTO DE VENTA ACTUAL"
Anotar "------------------------------------------------------------"
Anotar "Si el sistema de la caja esta abierto y recien escaneaste un ticket,"
Anotar "aca deberia aparecer su conexion a la balanza."
Anotar ""
$conexiones = @()
try {
    $datos = netstat -n 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($datos -join ' ') }
    # Comparar el extremo completo evita confundir .1 con .10 o con la IP local.
    $conexiones = @($datos | Where-Object { $_ -match ('^\s*TCP\s+\S+\s+' + [regex]::Escape($ip) + ':\d+\s+') })
} catch {
    Anotar ("   No se pudieron leer las conexiones de la balanza: " + $_.Exception.Message)
}
if ($conexiones) {
    foreach ($c in $conexiones) { Anotar ("   " + $c.ToString().Trim()) }
    Anotar ""
    Anotar "   Si la caja inicia la conexion, interesa el puerto del lado de la balanza."
    Anotar "   Si la balanza inicia la conexion, interesa el puerto local del PC."
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
if ($puertoEscrito -gt 0 -and -not $puertos.Contains($puertoEscrito)) { $puertos.Add($puertoEscrito, 'puerto indicado junto a la IP') }
# 13 intentos de 1500 ms dan margen a la retransmision de Wi-Fi sin superar unos 25 s.
Anotar "Probando puertos (hasta unos 20 segundos)."

# GetEnumerator y no $puertos[$p]: en un diccionario ordenado, indexar con un numero
# lo toma como POSICION y no como clave, asi que la descripcion salia vacia.
$abiertos = @()
foreach ($par in $puertos.GetEnumerator()) {
    $r = Probar-Puerto $ip $par.Key
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
        $w = Invoke-WebRequest -Uri $url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        $titulo = ""
        if ($w.Content -match "<title>(.*?)</title>") { $titulo = $matches[1].Trim() }
        Anotar ("   $url  ->  HTTP " + $w.StatusCode + "  " + $titulo)
        Anotar "   >>> Abrela en el navegador: ahi suele estar la configuracion de la"
        Anotar "       etiqueta y, con suerte, una forma de exportar las ventas."
    } catch {
        Anotar ("   $url  ->  contesta, pero pide clave o no tiene pagina en la raiz")
        Anotar ("   Detalle: " + $_.Exception.Message)
    }
}
if (-not $hubo) { Anotar "   No hay ningun puerto web abierto." }
Anotar ""

# ---------------------------------------------------------------- que significa
Anotar "------------------------------------------------------------"
Anotar "QUE SIGNIFICA LO QUE SALIO"
Anotar "------------------------------------------------------------"
foreach ($entrada in @($candidatas | Where-Object { $_.RemoteAddress -eq $ip -and $_.RemotePort -ge 49152 -and $_.LocalPort -gt 0 -and $_.LocalPort -lt 49152 } | Select-Object -Property LocalPort -Unique)) {
    Anotar ("   La balanza se conectaria a este PC en el puerto " + $entrada.LocalPort + ".")
    Anotar "   Ese puerto se escucha en la caja; la balanza puede no tener puertos abiertos."
}
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

}

# Estos datos permiten distinguir informes de varias cajas despues de la visita.
Anotar "DATOS DE ESTE COMPUTADOR"
Anotar "   Nombre: $env:COMPUTERNAME"
try {
    $ipsLocales = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -notmatch '^127\.' })
    foreach ($local in $ipsLocales) { Anotar ("   IPv4: " + $local.IPAddress + " (" + $local.InterfaceAlias + ")") }
} catch {
    Anotar ("   No se pudieron leer las IPs locales: " + $_.Exception.Message)
    # Algunos computadores bloquean CIM incluso sin elevacion; .NET consulta las interfaces directamente.
    try {
        foreach ($interfaz in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
            foreach ($direccionLocal in $interfaz.GetIPProperties().UnicastAddresses) {
                if ($direccionLocal.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and -not [System.Net.IPAddress]::IsLoopback($direccionLocal.Address)) {
                    Anotar ("   IPv4: " + $direccionLocal.Address + " (" + $interfaz.Name + ")")
                }
            }
        }
    } catch {
        Anotar ("   Tampoco se pudieron consultar las interfaces: " + $_.Exception.Message)
    }
}
try {
    $windows = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    Anotar ("   Windows: " + $windows.Caption + " - " + $windows.Version + " (build " + $windows.BuildNumber + ")")
} catch {
    Anotar ("   No se pudo consultar Windows: " + $_.Exception.Message)
    Anotar ("   Version disponible: " + [Environment]::OSVersion.VersionString)
}
Anotar ""
Anotar "============================================================"
Anotar " Informe: $salida"
Anotar "============================================================"
try {
    # UTF-8 sin BOM tambien permite abrir el archivo fuera de Windows.
    [System.IO.File]::WriteAllLines($salida, [string[]]$lineas, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host " Guardado en: $salida"
    Write-Host " Mandame ese archivo y te digo que cuesta conectar la caja."
} catch {
    Anotar (" No se pudo guardar el informe: " + $_.Exception.Message)
}
Read-Host "Enter para cerrar"
