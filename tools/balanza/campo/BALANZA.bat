@echo off
chcp 65001 >nul
title La balanza del local
cd /d "%~dp0"

REM No necesita Python, ni el repositorio, ni permisos de administrador: solo lo que
REM Windows ya trae. Se copia esta carpeta a un pendrive y se corre en el computador
REM de la caja del local.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0balanza.ps1"
if errorlevel 1 (
  echo.
  echo No pudo correr. Prueba: clic derecho en balanza.ps1 ^> Ejecutar con PowerShell
  pause
)
