@echo off
chcp 65001 >nul
title La balanza del local
cd /d "%~dp0"

REM No necesita Python, ni el repositorio, ni permisos de administrador: solo lo que
REM Windows ya trae. Se copia esta carpeta a un pendrive y se corre en el computador
REM de la caja del local.

if not exist "%~dp0balanza.ps1" (
  echo Falta balanza.ps1. Copia la carpeta completa y vuelve a intentar.
  pause
  exit /b 1
)
REM PowerShell 2 no puede leer el script; comprobar antes permite explicar la solucion.
powershell -NoProfile -Command "exit $PSVersionTable.PSVersion.Major"
if %errorlevel% LSS 3 (
  echo Este Windows necesita instalar WMF 5.1 ^(Windows Management Framework^).
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0balanza.ps1"
if not "%errorlevel%"=="0" (
  echo.
  echo No pudo correr. Prueba: clic derecho en balanza.ps1 ^> Ejecutar con PowerShell
  pause
)
