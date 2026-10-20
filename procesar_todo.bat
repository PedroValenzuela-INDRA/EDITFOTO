@echo off
setlocal
title EDITFOTO - Procesado por lotes
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :procesar
echo No se encuentra el entorno de EDITFOTO.
echo Ejecuta primero instalar.bat.
pause
exit /b 1

:procesar
echo Procesando las fotos de fotos\entrada y guardando en fotos\salida ...
echo.
".venv\Scripts\python.exe" -m editfoto procesar --entrada fotos\entrada --salida fotos\salida
if errorlevel 1 echo El procesado ha terminado con errores.
echo.
echo Proceso terminado.
pause
endlocal
