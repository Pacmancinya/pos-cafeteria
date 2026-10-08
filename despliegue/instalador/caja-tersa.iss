; Instalador de Caja Tersa (Inno Setup 6).
;
; Se arma con `python -m despliegue.construir_instalador`, que le pasa por la linea de
; comandos lo que cambia en cada version:
;     /DVersionApp=2.31    la version, leida de core/config.py (APP_VERSION)
;     /DOrigen=<ruta>      la carpeta despliegue\CajaTersa que deja construir_exe.py
;     /DSalida=<ruta>      donde queda CajaTersa-Instalar-vX.Y.exe
; La version NO se escribe a mano aqui: asi no se puede olvidar de subirla.
;
; CODIFICACION. Este archivo es el unico del repositorio que lleva BOM (UTF-8 con marca):
; Inno Setup 6 lee como ANSI un script sin BOM, y las tildes y la enie de los textos
; quedarian mal en la pantalla del instalador. No se lo quites al guardar.
;
; DONDE SE INSTALA. Por usuario, sin pedir administrador, en
; %LOCALAPPDATA%\Programs\CajaTersa. No es capricho: el actualizador de la caja
; (apps/pos/actualizar.py) reemplaza codigo dentro de esa carpeta y pos.db vive ahi
; mismo; en "Archivos de programa" una cuenta normal no podria escribir.
; Un computador que ya tenia la caja instalada de antes (Caja Clara, carpeta CajaClara)
; la conserva donde esta: UsePreviousAppDir=yes reutiliza esa carpeta, porque el AppId
; es el mismo, y ahi quedan sus datos.

#ifndef VersionApp
  #error Falta /DVersionApp=X.Y (usa: python -m despliegue.construir_instalador)
#endif
#ifndef Origen
  #error Falta /DOrigen=<carpeta despliegue\CajaTersa>
#endif
#ifndef Salida
  #define Salida "."
#endif

[Setup]
; NO CAMBIAR NUNCA este AppId. Es lo que le dice a Windows (y al instalador) que una
; instalacion nueva es la MISMA aplicacion: instalar encima actualiza y conserva los
; datos del local. Si cambia, cada instalacion queda como un programa distinto.
AppId={{A6409110-0F01-4DF9-8EA1-BE63F8ACDCE9}
AppName=Caja Tersa
AppVersion={#VersionApp}
AppVerName=Caja Tersa {#VersionApp}
AppPublisher=Tersa
DefaultDirName={autopf}\CajaTersa
DefaultGroupName=Caja Tersa
DisableProgramGroupPage=yes
DisableDirPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
; Si la caja esta abierta, el instalador lo avisa y pide cerrarla. Es el mismo nombre
; del mutex que crea Kofe.py (CERROJO): la caja abre una sola vez por computador.
AppMutex=Kofe-punto-de-venta-8090
; Sin cerrar programas "a la fuerza": a media venta seria peor que avisar.
CloseApplications=no
RestartApplications=no
OutputDir={#Salida}
OutputBaseFilename=CajaTersa-Instalar-v{#VersionApp}
SetupIconFile=..\icono\caja-tersa.ico
UninstallDisplayIcon={app}\CajaTersa.exe
UninstallDisplayName=Caja Tersa
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
; Apagada por defecto: no todos los locales quieren que la caja se abra sola.
Name: "inicio"; Description: "Abrir Caja Tersa al prender el computador"; Flags: unchecked

[Files]
; La misma carpeta que va dentro del zip de instalacion. Los Excludes son una red de
; seguridad: si alguien probo CajaTersa.exe dentro de la carpeta de armado, su pos.db
; (ventas ajenas), su .secreto o sus respaldos NO viajan en el instalador.
Source: "{#Origen}\*"; DestDir: "{app}"; \
  Excludes: "pos.db,pos.db-wal,pos.db-shm,.secreto,.env,.acceso-directo,problema-ventana.txt,respaldos\*,registros\*,datos-ventana\*,_version_anterior\*"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; El escritorio se crea solo en la primera instalacion: si el dueno lo borro, al
; actualizar no se vuelve a poner (la propia caja tambien respeta eso).
Name: "{autodesktop}\Caja Tersa"; Filename: "{app}\CajaTersa.exe"; WorkingDir: "{app}"; \
  IconFilename: "{app}\despliegue\icono\caja-tersa.ico"; Check: not YaEstabaInstalada
Name: "{autoprograms}\Caja Tersa"; Filename: "{app}\CajaTersa.exe"; WorkingDir: "{app}"; \
  IconFilename: "{app}\despliegue\icono\caja-tersa.ico"
Name: "{userstartup}\Caja Tersa"; Filename: "{app}\CajaTersa.exe"; WorkingDir: "{app}"; \
  IconFilename: "{app}\despliegue\icono\caja-tersa.ico"; Tasks: inicio

[Run]
Filename: "{app}\CajaTersa.exe"; Description: "Abrir Caja Tersa"; WorkingDir: "{app}"; \
  Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; DESINSTALAR NUNCA TOCA LOS DATOS DEL LOCAL.
; Por eso no hay [UninstallDelete] ni [InstallDelete] en este script: Inno solo borra
; lo que el mismo instalo (el programa y los accesos directos). Siguen en la carpeta
; pos.db (y -wal, -shm), respaldos\, registros\, .secreto, datos-ventana\,
; .acceso-directo, .env y _version_anterior\ (lo que guarda el actualizador para
; "volver a la version anterior"). Son las ventas del local: un desinstalar apretado
; por error no puede llevarselas. Si algun dia se agrega una limpieza, que NUNCA
; nombre esas rutas ni use una carpeta entera de {app}.
; ---------------------------------------------------------------------------

[Code]
const
  ClaveDesinstalar = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A6409110-0F01-4DF9-8EA1-BE63F8ACDCE9}_is1';

function YaEstabaInstalada: Boolean;
begin
  Result := RegKeyExists(HKCU, ClaveDesinstalar);
end;

function SiguienteNumero(var Texto: String): Integer;
var
  P: Integer;
begin
  P := Pos('.', Texto);
  if P = 0 then
  begin
    Result := StrToIntDef(Texto, 0);
    Texto := '';
  end
  else
  begin
    Result := StrToIntDef(Copy(Texto, 1, P - 1), 0);
    Texto := Copy(Texto, P + 1, Length(Texto));
  end;
end;

{ -1 si A es menor que B, 0 si son iguales, 1 si A es mayor. "2.10" es mayor que "2.9". }
function CompararVersiones(A, B: String): Integer;
var
  NA, NB: Integer;
begin
  Result := 0;
  while (Result = 0) and ((A <> '') or (B <> '')) do
  begin
    NA := SiguienteNumero(A);
    NB := SiguienteNumero(B);
    if NA < NB then Result := -1
    else if NA > NB then Result := 1;
  end;
end;

{ La version que de verdad tiene la caja instalada: la lee de core\config.py, porque el
  actualizador cambia el codigo sin pasar por este instalador. }
function VersionDelCodigoInstalado: String;
var
  Ruta: String;
  Crudo: AnsiString;
  Texto: String;
  P, Q: Integer;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, ClaveDesinstalar, 'Inno Setup: App Path', Ruta) then Exit;
  if not LoadStringFromFile(AddBackslash(Ruta) + 'core\config.py', Crudo) then Exit;
  Texto := String(Crudo);
  P := Pos('APP_VERSION = "', Texto);
  if P = 0 then Exit;
  Texto := Copy(Texto, P + Length('APP_VERSION = "'), 20);
  Q := Pos('"', Texto);
  if Q > 0 then Result := Copy(Texto, 1, Q - 1);
end;

{ Instalar un instalador mas viejo encima de una caja ya actualizada la dejaria atras. }
function InitializeSetup: Boolean;
var
  Instalada: String;
begin
  Result := True;
  Instalada := VersionDelCodigoInstalado;
  if (Instalada <> '') and (CompararVersiones(Instalada, '{#VersionApp}') > 0) then
    Result := SuppressibleMsgBox(
      'Este computador ya tiene Caja Tersa ' + Instalada + ', mas nueva que la ' +
      '{#VersionApp} de este instalador.' + #13#10#13#10 +
      'Seguir la dejaria en una version anterior (las ventas y los datos se conservan). ' +
      'Quieres seguir de todos modos?',
      mbConfirmation, MB_YESNO, IDNO) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usDone then
    SuppressibleMsgBox(
      'Caja Tersa se quito de este computador.' + #13#10#13#10 +
      'Las ventas y los datos del local NO se borraron: siguen en ' +
      ExpandConstant('{app}') + '. Si algun dia la vuelves a instalar, aparecen tal como estaban.',
      mbInformation, MB_OK, IDOK);
end;
