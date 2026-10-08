; Instalador de Gespoint (Inno Setup 6).
;
; Se arma con `python -m despliegue.construir_instalador`, que le pasa por la linea de
; comandos lo que cambia en cada version:
;     /DVersionApp=2.31    la version, leida de core/config.py (APP_VERSION)
;     /DOrigen=<ruta>      la carpeta despliegue\Gespoint que deja construir_exe.py
;     /DSalida=<ruta>      donde queda Gespoint-Instalar-vX.Y.exe
; La version NO se escribe a mano aqui: asi no se puede olvidar de subirla.
;
; CODIFICACION. Este archivo es el unico del repositorio que lleva BOM (UTF-8 con marca):
; Inno Setup 6 lee como ANSI un script sin BOM, y las tildes y la enie de los textos
; quedarian mal en la pantalla del instalador. No se lo quites al guardar.
;
; DONDE SE INSTALA. Por usuario, sin pedir administrador, en
; %LOCALAPPDATA%\Programs\Gespoint. No es capricho: el actualizador de la caja
; (apps/pos/actualizar.py) reemplaza codigo dentro de esa carpeta y pos.db vive ahi
; mismo; en "Archivos de programa" una cuenta normal no podria escribir.
; Un computador que ya tenia la caja instalada de antes (Caja Clara, carpeta CajaClara)
; la conserva donde esta: UsePreviousAppDir=yes reutiliza esa carpeta, porque el AppId
; es el mismo, y ahi quedan sus datos.

#ifndef VersionApp
  #error Falta /DVersionApp=X.Y (usa: python -m despliegue.construir_instalador)
#endif
#ifndef Origen
  #error Falta /DOrigen=<carpeta despliegue\Gespoint>
#endif
#ifndef Salida
  #define Salida "."
#endif

[Setup]
; NO CAMBIAR NUNCA este AppId. Es lo que le dice a Windows (y al instalador) que una
; instalacion nueva es la MISMA aplicacion: instalar encima actualiza y conserva los
; datos del local. Si cambia, cada instalacion queda como un programa distinto.
AppId={{A6409110-0F01-4DF9-8EA1-BE63F8ACDCE9}
AppName=Gespoint
AppVersion={#VersionApp}
AppVerName=Gespoint {#VersionApp}
AppPublisher=Gespoint
AppPublisherURL=https://gespoint.site
DefaultDirName={autopf}\Gespoint
DefaultGroupName=Gespoint
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
OutputBaseFilename=Gespoint-Instalar-v{#VersionApp}
SetupIconFile=..\icono\gespoint.ico
UninstallDisplayIcon={app}\Gespoint.exe
UninstallDisplayName=Gespoint
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
; Apagada por defecto: no todos los locales quieren que la caja se abra sola.
Name: "inicio"; Description: "Abrir Gespoint al prender el computador"; Flags: unchecked

[Files]
; La misma carpeta que va dentro del zip de instalacion. Los Excludes son una red de
; seguridad: si alguien probo Gespoint.exe dentro de la carpeta de armado, su pos.db
; (ventas ajenas), su .secreto o sus respaldos NO viajan en el instalador.
Source: "{#Origen}\*"; DestDir: "{app}"; \
  Excludes: "pos.db,pos.db-wal,pos.db-shm,.secreto,.env,.acceso-directo,problema-ventana.txt,respaldos\*,registros\*,datos-ventana\*,_version_anterior\*"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; El escritorio se crea solo en la primera instalacion: si el dueno lo borro, al
; actualizar no se vuelve a poner (la propia caja tambien respeta eso).
Name: "{autodesktop}\Gespoint"; Filename: "{app}\Gespoint.exe"; WorkingDir: "{app}"; \
  IconFilename: "{app}\despliegue\icono\gespoint.ico"; Check: not YaEstabaInstalada
Name: "{autoprograms}\Gespoint"; Filename: "{app}\Gespoint.exe"; WorkingDir: "{app}"; \
  IconFilename: "{app}\despliegue\icono\gespoint.ico"
Name: "{userstartup}\Gespoint"; Filename: "{app}\Gespoint.exe"; WorkingDir: "{app}"; \
  IconFilename: "{app}\despliegue\icono\gespoint.ico"; Tasks: inicio

[Run]
Filename: "{app}\Gespoint.exe"; Description: "Abrir Gespoint"; WorkingDir: "{app}"; \
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

var
  { Se fija UNA vez, en InitializeSetup, antes de instalar nada. Preguntarle al registro
    despues no sirve: al terminar de instalar Inno ya creo la clave de desinstalacion y
    siempre diria que si. }
  HabiaInstalacionPrevia: Boolean;

function YaEstabaInstalada: Boolean;
begin
  Result := HabiaInstalacionPrevia;
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

(* ---------------------------------------------------------------------------
  PASAR UNA CAJA INSTALADA CON ZIP A LA APLICACION.
  Las cajas de antes viven en una carpeta suelta (Kofe.exe o CajaClara.exe y, al lado, la
  base de ventas). Este instalador NO copia esa base: solo anota de donde hay que traerla
  en {app}\mudar-desde.txt, y la aplicacion la trae al abrir con el respaldo de SQLite
  (apps/pos/mudanza.py). Lo unico que este script borra son accesos directos (.lnk) cuyo
  destino esta dentro de la carpeta vieja: nunca archivos de datos ni la carpeta.
  --------------------------------------------------------------------------- *)
var
  PaginaMudanza: TInputOptionWizardPage;
  EtiquetaCarpeta: TNewStaticText;
  CarpetaVieja: String;          { '' = ninguna elegida }
  ArrancabaSola: Boolean;        { la caja vieja se abria al prender el computador }

function EsExeDeCaja(const Ruta: String): Boolean;
var
  N: String;
begin
  N := Lowercase(ExtractFileName(Ruta));
  Result := (N = 'kofe.exe') or (N = 'cajaclara.exe') or (N = 'gespoint.exe');
end;

{ La caja vieja trae el bloqueo de la mudanza (la version que ya sabe avisar «esta caja se
  mudo»). Sin eso, seguiria pudiendo vender despues de mudarse y se separarian los historiales. }
function TieneElBloqueo(const Carpeta: String): Boolean;
begin
  Result := FileExists(AddBackslash(Carpeta) + 'apps\pos\mudanza.py');
end;

const
  AvisoVersion = 'Primero abre la caja vieja y deja que se actualice a la ultima version; ' +
    'despues vuelve a correr este instalador.';

{ Es una caja de verdad: tiene su base y uno de los ejecutables. }
function EsCarpetaDeCaja(const Carpeta: String): Boolean;
begin
  Result := DirExists(Carpeta) and FileExists(AddBackslash(Carpeta) + 'pos.db') and
    (FileExists(AddBackslash(Carpeta) + 'Kofe.exe') or
     FileExists(AddBackslash(Carpeta) + 'CajaClara.exe') or
     FileExists(AddBackslash(Carpeta) + 'Gespoint.exe'));
end;

{ Carpeta esta igual o dentro de Raiz. }
function EstaDentro(const Carpeta, Raiz: String): Boolean;
begin
  Result := (Raiz <> '') and
    (Pos(Lowercase(AddBackslash(Raiz)), Lowercase(AddBackslash(Carpeta))) = 1);
end;

function DestinoDeAcceso(const Lnk: String): String;
var
  Shell, Acceso: Variant;
begin
  Result := '';
  try
    Shell := CreateOleObject('WScript.Shell');
    Acceso := Shell.CreateShortcut(Lnk);
    Result := Acceso.TargetPath;
  except
    Log('No se pudo leer el acceso directo ' + Lnk);
  end;
end;

{ Recorre los .lnk de una carpeta (y un nivel de subcarpetas).
  Modo 0: busca la primera caja vieja que no sea esta aplicacion.
  Modo 1: borra los accesos cuyo destino esta dentro de CarpetaVieja.
  Modo 2: solo anota si alguno de ellos esta en Inicio (arrancaba sola). }
procedure RevisarAccesos(const Dir: String; Modo, Nivel: Integer);
var
  Busqueda: TFindRec;
  Ruta, Destino, Carpeta: String;
begin
  if not DirExists(Dir) then Exit;
  if not FindFirst(AddBackslash(Dir) + '*', Busqueda) then Exit;
  try
    repeat
      if (Busqueda.Name <> '.') and (Busqueda.Name <> '..') then
      begin
        Ruta := AddBackslash(Dir) + Busqueda.Name;
        if (Busqueda.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          if Nivel < 1 then RevisarAccesos(Ruta, Modo, Nivel + 1);
        end
        else if CompareText(ExtractFileExt(Ruta), '.lnk') = 0 then
        begin
          Destino := DestinoDeAcceso(Ruta);
          if Destino <> '' then
          begin
            Carpeta := ExtractFileDir(Destino);
            if EstaDentro(Carpeta, WizardDirValue) then
              { es de esta aplicacion: no se toca }
            else if Modo = 0 then
            begin
              { La primera que sirva; pero una que ya trae el bloqueo le gana a otra que no. }
              if EsExeDeCaja(Destino) and EsCarpetaDeCaja(Carpeta) and
                 ((CarpetaVieja = '') or
                  (not TieneElBloqueo(CarpetaVieja) and TieneElBloqueo(Carpeta))) then
              begin
                CarpetaVieja := Carpeta;
                Log('Caja anterior detectada por el acceso ' + Ruta + ': ' + Carpeta);
              end;
            end
            else if (CarpetaVieja <> '') and EstaDentro(Carpeta, CarpetaVieja) then
            begin
              if Modo = 2 then
              begin
                if EstaDentro(Dir, ExpandConstant('{userstartup}')) or
                   EstaDentro(Dir, ExpandConstant('{commonstartup}')) then
                  ArrancabaSola := True;
              end
              else if DeleteFile(Ruta) then
                Log('Acceso directo de la caja vieja borrado: ' + Ruta)
              else
                Log('No se pudo borrar el acceso directo de la caja vieja (sin permiso): ' + Ruta);
            end;
          end;
        end;
      end;
    until not FindNext(Busqueda);
  finally
    FindClose(Busqueda);
  end;
end;

procedure RecorrerAccesos(Modo: Integer);
begin
  RevisarAccesos(ExpandConstant('{userdesktop}'), Modo, 0);
  RevisarAccesos(ExpandConstant('{userprograms}'), Modo, 0);
  RevisarAccesos(ExpandConstant('{userstartup}'), Modo, 0);
  RevisarAccesos(ExpandConstant('{commondesktop}'), Modo, 0);
  RevisarAccesos(ExpandConstant('{commonprograms}'), Modo, 0);
  RevisarAccesos(ExpandConstant('{commonstartup}'), Modo, 0);
end;

procedure MostrarCarpeta;
begin
  if (CarpetaVieja <> '') and not TieneElBloqueo(CarpetaVieja) then
  begin
    EtiquetaCarpeta.Caption := 'Carpeta: ' + CarpetaVieja + #13#10 + AvisoVersion;
    PaginaMudanza.CheckListBox.ItemEnabled[0] := False;
    PaginaMudanza.Values[0] := False;
    PaginaMudanza.Values[1] := True;
  end
  else if CarpetaVieja = '' then
  begin
    EtiquetaCarpeta.Caption := 'No encontre una caja anterior en este computador. ' +
      'Si tenias una, usa el boton para elegir su carpeta.';
    PaginaMudanza.CheckListBox.ItemEnabled[0] := False;
    PaginaMudanza.Values[0] := False;
    PaginaMudanza.Values[1] := True;
  end
  else
  begin
    EtiquetaCarpeta.Caption := 'Carpeta: ' + CarpetaVieja;
    PaginaMudanza.CheckListBox.ItemEnabled[0] := True;
    PaginaMudanza.Values[0] := True;
  end;
end;

procedure ElegirOtraCarpeta(Sender: TObject);
var
  Dir: String;
begin
  Dir := CarpetaVieja;
  if BrowseForFolder('Elige la carpeta donde estaba la caja anterior (la que tiene el ejecutable y la base de ventas):', Dir, False) then
  begin
    Dir := RemoveBackslashUnlessRoot(Dir);
    if EstaDentro(Dir, WizardDirValue) then
      MsgBox('Esa carpeta es la de la aplicacion nueva.', mbError, MB_OK)
    else if not EsCarpetaDeCaja(Dir) then
      MsgBox('En esa carpeta no hay una caja (falta la base de ventas o el programa de la caja).', mbError, MB_OK)
    else
    begin
      CarpetaVieja := Dir;
      MostrarCarpeta;
    end;
  end;
end;

procedure InitializeWizard;
var
  Boton: TNewButton;
begin
  PaginaMudanza := CreateInputOptionPage(wpWelcome,
    'Caja anterior',
    'Este computador ya tenia la caja?',
    'Cierra la caja anterior antes de seguir. No se borra nada de ella: sus ventas, ' +
    'usuarios y ajustes se COPIAN a la aplicacion nueva.',
    True, False);
  PaginaMudanza.Add('Si, traer las ventas, usuarios y ajustes de la caja anterior');
  PaginaMudanza.Add('No, es una caja nueva');
  PaginaMudanza.CheckListBox.Height := ScaleY(60);

  EtiquetaCarpeta := TNewStaticText.Create(PaginaMudanza);
  EtiquetaCarpeta.Parent := PaginaMudanza.Surface;
  EtiquetaCarpeta.AutoSize := False;
  EtiquetaCarpeta.WordWrap := True;
  EtiquetaCarpeta.Left := 0;
  EtiquetaCarpeta.Width := PaginaMudanza.SurfaceWidth;
  EtiquetaCarpeta.Top := PaginaMudanza.CheckListBox.Top + PaginaMudanza.CheckListBox.Height + ScaleY(10);
  EtiquetaCarpeta.Height := ScaleY(48);

  Boton := TNewButton.Create(PaginaMudanza);
  Boton.Parent := PaginaMudanza.Surface;
  Boton.Caption := 'Elegir otra carpeta...';
  Boton.Left := 0;
  Boton.Top := EtiquetaCarpeta.Top + EtiquetaCarpeta.Height + ScaleY(6);
  Boton.Width := ScaleX(160);
  Boton.Height := ScaleY(25);
  Boton.OnClick := @ElegirOtraCarpeta;

  { Una caja instalada de antes: se la busca por sus accesos directos. }
  if not YaEstabaInstalada then
  begin
    RecorrerAccesos(0);
    Log('Caja anterior detectada: ' + CarpetaVieja);
  end;
  MostrarCarpeta;
end;

{ La pagina no sale al reinstalar la aplicacion, ni en instalacion silenciosa. }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PaginaMudanza <> nil) and (PageID = PaginaMudanza.ID) then
    Result := YaEstabaInstalada or (ExpandConstant('{param:MUDARDESDE|}') <> '');
end;

{ Si la caja vieja arrancaba sola, la nueva tambien (el dueno lo puede desmarcar). }
procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpSelectTasks) and (CarpetaVieja <> '') and PaginaMudanza.Values[0] then
  begin
    ArrancabaSola := False;
    RevisarAccesos(ExpandConstant('{userstartup}'), 2, 0);
    RevisarAccesos(ExpandConstant('{commonstartup}'), 2, 0);
    if ArrancabaSola then WizardSelectTasks('inicio');
  end;
end;

function QuiereMudar: Boolean;
var
  Param: String;
begin
  Param := ExpandConstant('{param:MUDARDESDE|}');
  if Param <> '' then
    Result := TieneElBloqueo(CarpetaVieja)
  else
  begin
    { Instalacion silenciosa sin el parametro: solo si se pide la deteccion (pruebas). }
    if WizardSilent then
      Result := ExpandConstant('{param:MUDARDETECTADA|}') <> ''
    else
      Result := True;
    Result := Result and (not HabiaInstalacionPrevia) and (CarpetaVieja <> '') and
      TieneElBloqueo(CarpetaVieja) and PaginaMudanza.Values[0];
  end;
end;

procedure PrepararMudanza;
var
  Pedido: String;
begin
  Pedido := ExpandConstant('{app}\mudar-desde.txt');
  if not SaveStringToFile(Pedido, UTF8Encode(CarpetaVieja), False) then
  begin
    Log('No se pudo escribir ' + Pedido + ': no se borra ningun acceso directo.');
    Exit;
  end;
  Log('Mudanza pedida desde ' + CarpetaVieja + ' (' + Pedido + ')');
  { Que nadie abra la caja vieja por costumbre ni arranque sola al prender el PC. }
  RecorrerAccesos(1);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and QuiereMudar then
    PrepararMudanza;
end;

{ Instalar un instalador mas viejo encima de una caja ya actualizada la dejaria atras. }
function InitializeSetup: Boolean;
var
  Instalada, Param: String;
begin
  Result := True;
  HabiaInstalacionPrevia := RegKeyExists(HKCU, ClaveDesinstalar);
  Param := ExpandConstant('{param:MUDARDESDE|}');
  if Param <> '' then
  begin
    CarpetaVieja := RemoveBackslashUnlessRoot(Param);
    if not EsCarpetaDeCaja(CarpetaVieja) then
    begin
      Log('/MUDARDESDE no apunta a una caja (falta la base o el programa): ' + Param);
      SuppressibleMsgBox('La carpeta indicada en /MUDARDESDE no es una caja: ' + Param,
        mbError, MB_OK, IDOK);
      Result := False;
      Exit;
    end;
    if not TieneElBloqueo(CarpetaVieja) then
    begin
      Log('/MUDARDESDE: la caja vieja no trae el bloqueo de la mudanza: ' + Param);
      SuppressibleMsgBox(AvisoVersion, mbError, MB_OK, IDOK);
      Result := False;
      Exit;
    end;
  end;
  Instalada := VersionDelCodigoInstalado;
  if (Instalada <> '') and (CompararVersiones(Instalada, '{#VersionApp}') > 0) then
    Result := SuppressibleMsgBox(
      'Este computador ya tiene Gespoint ' + Instalada + ', mas nueva que la ' +
      '{#VersionApp} de este instalador.' + #13#10#13#10 +
      'Seguir la dejaria en una version anterior (las ventas y los datos se conservan). ' +
      'Quieres seguir de todos modos?',
      mbConfirmation, MB_YESNO, IDNO) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usDone then
    SuppressibleMsgBox(
      'Gespoint se quito de este computador.' + #13#10#13#10 +
      'Las ventas y los datos del local NO se borraron: siguen en ' +
      ExpandConstant('{app}') + '. Si algun dia la vuelves a instalar, aparecen tal como estaban.',
      mbInformation, MB_OK, IDOK);
end;
