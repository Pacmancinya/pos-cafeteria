@echo off
chcp 65001 >nul
title Buscar actualizaciones - Punto de venta
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo    BUSCAR ACTUALIZACIONES
echo ============================================================
echo.
echo  (Tambien se puede desde la caja: el numero de version
echo   arriba a la derecha.)
echo.

if not exist ".venv\Scripts\python.exe" goto sin_entorno
.venv\Scripts\python -m tools.buscar_actualizacion
echo.
pause
goto fin

:sin_entorno
echo   El programa todavia no esta instalado en este computador.
echo   Abre primero INICIAR-POS.bat.
echo.
pause

:fin
endlocal
