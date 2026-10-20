@echo off
setlocal
title EDITFOTO - Instalacion
cd /d "%~dp0"

echo ============================================
echo  EDITFOTO - Instalacion
echo ============================================
echo.

rem --- 1. Buscar Python (orden: 3.12, 3.13, 3.11, python) ---
set "PY="
py -3.12 --version >nul 2>&1 && set "PY=py -3.12" && goto :pyok
py -3.13 --version >nul 2>&1 && set "PY=py -3.13" && goto :pyok
py -3.11 --version >nul 2>&1 && set "PY=py -3.11" && goto :pyok
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python" && goto :pyok

echo No se ha encontrado Python 3.11, 3.12 o 3.13.
echo.
echo Instala Python 3.12 desde python.org.
echo Durante la instalacion marca la casilla "Add python.exe to PATH".
echo Cuando termines, vuelve a ejecutar instalar.bat.
echo.
pause
exit /b 1

:pyok
echo Python encontrado: %PY%
echo.

rem --- 2. Crear el entorno virtual .venv si no existe ---
if exist ".venv\Scripts\python.exe" goto :venvok
echo Creando el entorno virtual .venv ...
%PY% -m venv .venv
if errorlevel 1 (
  echo ERROR: no se ha podido crear el entorno virtual .venv.
  pause
  exit /b 1
)
:venvok

set "VPY=.venv\Scripts\python.exe"

rem --- 3. Actualizar pip e instalar dependencias comunes ---
echo Actualizando pip ...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo ERROR: no se ha podido actualizar pip.
  pause
  exit /b 1
)

echo Instalando dependencias comunes (requirements.txt) ...
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: la instalacion de requirements.txt ha fallado.
  pause
  exit /b 1
)

rem --- 4. Elegir el runtime de IA segun el hardware ---
echo.
echo Elige el tipo de aceleracion para la IA:
echo   1^) Tarjeta grafica NVIDIA ^(recomendado si tienes NVIDIA^)
echo   2^) Otra tarjeta grafica ^(AMD/Intel^) o no estoy seguro: DirectML
echo   3^) Solo procesador ^(CPU, mas lento^)
echo.
choice /c 123 /d 2 /t 30 /m "Elige una opcion"
set "OPCION=%errorlevel%"

if "%OPCION%"=="1" goto :nvidia
if "%OPCION%"=="2" goto :directml
goto :cpu

:nvidia
set "PAQUETE=onnxruntime-gpu[cuda,cudnn]"
goto :runtime

:directml
set "PAQUETE=onnxruntime-directml"
goto :runtime

:cpu
set "PAQUETE=onnxruntime"

:runtime
echo.
echo Instalando el runtime de IA: %PAQUETE%
rem Se desinstalan los tres runtimes (son incompatibles entre si); los errores se ignoran.
"%VPY%" -m pip uninstall -y onnxruntime onnxruntime-gpu onnxruntime-directml >nul 2>&1
"%VPY%" -m pip install "%PAQUETE%"
if errorlevel 1 (
  echo ERROR: no se ha podido instalar el runtime de IA.
  pause
  exit /b 1
)

rem --- 5. Crear las carpetas de trabajo ---
echo.
echo Creando carpetas de trabajo ...
if not exist "fotos\entrada" mkdir "fotos\entrada"
if not exist "fotos\salida" mkdir "fotos\salida"
if not exist "fotos\ejemplos" mkdir "fotos\ejemplos"

rem --- 6. Descargar modelos y comprobar la instalacion ---
echo.
echo Descargando los modelos de IA (puede tardar varios minutos) ...
"%VPY%" -m editfoto descargar-modelos
if errorlevel 1 (
  echo ERROR: no se han podido descargar los modelos.
  pause
  exit /b 1
)

echo.
echo Comprobando la instalacion ...
"%VPY%" -m editfoto info
if errorlevel 1 (
  echo ERROR: la comprobacion final ha fallado.
  pause
  exit /b 1
)

echo.
echo ============================================
echo  Instalacion completada.
echo  Siguiente paso: haz doble clic en iniciar.bat
echo ============================================
echo.
pause
endlocal
