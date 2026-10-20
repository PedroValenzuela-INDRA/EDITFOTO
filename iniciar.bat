@echo off
setlocal
title EDITFOTO - Servidor
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :arrancar
echo No se encuentra el entorno de EDITFOTO.
echo Ejecuta primero instalar.bat.
pause
exit /b 1

:arrancar
echo Arrancando EDITFOTO. Se abrira el navegador con la aplicacion.
echo Para cerrar el servidor, pulsa Ctrl+C en esta ventana.
echo.
".venv\Scripts\python.exe" -m editfoto servidor --entrada fotos\entrada --salida fotos\salida --abrir
if errorlevel 1 echo El servidor se ha cerrado con un error.
echo.
pause
endlocal
