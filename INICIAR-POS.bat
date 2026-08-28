@echo off
chcp 65001 >nul
REM ============================================================
REM  Punto de venta - lanzador (doble clic)
REM  Sigue el patron de INICIAR-APP-GESFACT.bat, que ya resolvio
REM  esto en PCs de clientes reales:
REM   - No confia en "where python": Windows trae un Python FALSO
REM     (alias de la Microsoft Store) que existe pero no sirve.
REM     Por eso se verifica por RESULTADO: se intenta crear el
REM     entorno y se revisa si el archivo quedo creado.
REM   - Si no hay Python, lo instala solo, por-usuario (sin pedir
REM     administrador) y despues usa su RUTA COMPLETA, porque el
REM     PATH de esta ventana ya quedo viejo.
REM ============================================================
setlocal
cd /d "%~dp0"
title Punto de venta - Cafeteria

echo.
echo ============================================================
echo    PUNTO DE VENTA
echo ============================================================
echo.

REM --- 0. La carpeta tiene que estar completa (no ejecutar desde el ZIP) ---
if not exist "requirements.txt" goto sin_carpeta
if not exist "apps\pos\main.py" goto sin_carpeta

REM --- 1. Entorno de Python ---
if exist ".venv\Scripts\python.exe" goto venv_ok
echo [1/3] Es la primera vez: preparando el programa.
echo       Demora un par de minutos y necesita internet. NO cierres esta ventana.
echo.

REM 1a. El lanzador "py" es el mas confiable: la Store no lo suplanta.
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m venv .venv >nul 2>&1
    if exist ".venv\Scripts\python.exe" goto venv_ok
)
REM 1b. Un python de verdad en el PATH.
where python >nul 2>&1
if %errorlevel%==0 (
    python -m venv .venv >nul 2>&1
    if exist ".venv\Scripts\python.exe" goto venv_ok
)
REM 1c. Uno que haya instalado este mismo lanzador antes.
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv .venv >nul 2>&1
    if exist ".venv\Scripts\python.exe" goto venv_ok
)

REM 1d. No hay ninguno: lo instalamos nosotros.
echo       Este computador no tiene Python. Lo instalo yo, una sola vez.
echo       Son unos 25 MB. No pide permiso de administrador.
echo.
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\pos-python.exe'"
if not exist "%TEMP%\pos-python.exe" goto no_internet
echo       Instalando Python...
"%TEMP%\pos-python.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
if not exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" goto no_python
echo       Python instalado.
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv .venv
if not exist ".venv\Scripts\python.exe" goto no_python

:venv_ok
set "PYTHON=.venv\Scripts\python.exe"
"%PYTHON%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto python_viejo

REM --- 2. Dependencias (solo si falta alguna: asi arranca sin internet) ---
"%PYTHON%" -c "import fastapi, uvicorn, sqlmodel, tzdata" >nul 2>&1
if not errorlevel 1 goto deps_ok
echo [2/3] Instalando lo que falta...
"%PYTHON%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto sin_deps
"%PYTHON%" -c "import fastapi, uvicorn, sqlmodel, tzdata" >nul 2>&1
if errorlevel 1 goto sin_deps
:deps_ok

REM --- 3. Carta de ejemplo la primera vez ---
if exist "pos.db" goto carta_ok
echo [3/3] Cargando la carta de ejemplo...
"%PYTHON%" -m tools.demo.seed
:carta_ok

"%PYTHON%" -m tools.datos_de_red

REM El navegador se abre SOLO cuando el servidor ya responde.
start "" powershell -NoProfile -WindowStyle Hidden -Command ^
  "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8090/api/v1/salud -TimeoutSec 1 | Out-Null; Start-Process 'http://127.0.0.1:8090'; break}catch{Start-Sleep -Milliseconds 500}}"

:arrancar
"%PYTHON%" -m uvicorn apps.pos.main:app --host 0.0.0.0 --port 8090
REM Si el programa se cerro para actualizarse (codigo 3), lo levantamos de nuevo
REM sin que el dueno tenga que hacer nada.
if %errorlevel%==3 (
    echo.
    echo   Actualizando... el programa se vuelve a abrir solo.
    timeout /t 2 >nul
    goto arrancar
)
echo.
echo   El punto de venta se detuvo.
pause
goto fin

:sin_carpeta
echo   Falta parte del programa en esta carpeta.
echo.
echo   Casi siempre es porque se ejecuto el archivo DESDE ADENTRO del ZIP.
echo   Cierra esto, haz clic derecho en el ZIP, elige "Extraer todo",
echo   y recien ahi abre INICIAR-POS.bat de la carpeta extraida.
echo.
pause
goto fin

:no_internet
echo.
echo   No pude descargar Python: parece que no hay internet.
echo   Conectate y vuelve a abrir este archivo.
echo.
pause
goto fin

:no_python
echo.
echo   No pude instalar Python solo. Instalalo a mano desde:
echo        https://www.python.org/downloads/
echo   IMPORTANTE: marca la casilla "Add Python to PATH" antes de instalar.
echo   Despues vuelve a abrir este archivo.
echo.
pause
goto fin

:python_viejo
echo.
echo   El Python de este computador es muy antiguo (se necesita 3.10 o mas).
echo   Instala uno nuevo desde https://www.python.org/downloads/,
echo   BORRA la carpeta .venv de aca, y vuelve a abrir este archivo.
echo.
pause
goto fin

:sin_deps
echo.
echo   Fallo la instalacion. Casi siempre es que no hay internet.
echo   Conectate y vuelve a abrir este archivo.
echo.
pause

:fin
endlocal
