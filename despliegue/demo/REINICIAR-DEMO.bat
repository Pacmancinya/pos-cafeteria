@echo off
REM Deja la demo de Caja Tersa como nueva: cierra la caja, borra su base de ejemplo y
REM la vuelve a abrir (al abrir, la caja siembra de nuevo carta, gente y ventas).
REM
REM Solo borra si esta al lado de MODO-DEMO.txt Y de un ejecutable de la caja (CajaTersa.exe;
REM tambien se reconocen los de antes, CajaClara.exe y Kofe.exe): en la carpeta de un
REM local de verdad no hay MODO-DEMO.txt, asi que se niega sin tocar nada.
REM (cd con punto al final: "%~dp0" solo se come la comilla. Ver README, trampa 9.)
setlocal
cd /d "%~dp0."

if not exist "MODO-DEMO.txt" goto no_es_demo
set "EXE="
if exist "CajaTersa.exe" set "EXE=CajaTersa.exe"
if not defined EXE if exist "CajaClara.exe" set "EXE=CajaClara.exe"
if not defined EXE if exist "Kofe.exe" set "EXE=Kofe.exe"
if not defined EXE goto no_es_demo

echo Reiniciando la demo de Caja Tersa...
taskkill /IM "%EXE%" /F >nul 2>&1
timeout /t 2 /nobreak >nul
del /q "pos.db" "pos.db-wal" "pos.db-shm" >nul 2>&1
if exist "pos.db" goto no_se_pudo

start "" "%EXE%"
exit /b 0

:no_es_demo
echo.
echo Esta carpeta no es una demo de Caja Tersa: no se borra nada.
echo.
pause
exit /b 1

:no_se_pudo
echo.
echo No se pudo borrar la base de ejemplo. Cierra Caja Tersa y vuelve a intentarlo.
echo.
pause
exit /b 1
