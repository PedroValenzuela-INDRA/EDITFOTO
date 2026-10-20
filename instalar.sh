#!/usr/bin/env bash
# Instalacion de EDITFOTO en Linux y macOS.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Instalación de EDITFOTO ==="
echo

# 1. Buscar un Python compatible (3.12, 3.13, 3.11 o python3 >= 3.11).
PY=""
for candidato in python3.12 python3.13 python3.11 python3; do
  if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY="$candidato"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "No se ha encontrado Python 3.11, 3.12 o 3.13."
  echo "Instala Python 3.12 (con tu gestor de paquetes o desde python.org) y vuelve a ejecutar este script."
  exit 1
fi
echo "Python encontrado: $("$PY" --version)"

# 2. Crear el entorno virtual .venv si no existe.
if [[ ! -x ".venv/bin/python" ]]; then
  echo "Creando el entorno virtual .venv ..."
  "$PY" -m venv .venv || {
    echo "No se ha podido crear .venv. En Debian/Ubuntu instala el paquete python3-venv."
    exit 1
  }
fi
VENV_PY="$PWD/.venv/bin/python"

# 3. Actualizar pip e instalar las dependencias comunes.
echo "Actualizando pip ..."
"$VENV_PY" -m pip install --upgrade pip
echo "Instalando dependencias comunes (requirements.txt) ..."
"$VENV_PY" -m pip install -r requirements.txt

# 4. Runtime de IA segun el sistema (solo uno; son incompatibles entre si).
if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "macOS detectado: se instala onnxruntime (usa CoreML automáticamente)."
  RUNTIME="onnxruntime"
else
  echo
  echo "Aceleración para la IA:"
  echo "  1) NVIDIA (CUDA)"
  echo "  2) Solo procesador (CPU)"
  RESP=""
  read -r -p "Elige 1 o 2 [por defecto 2]: " RESP || true
  case "${RESP:-2}" in
    1) RUNTIME="onnxruntime-gpu[cuda,cudnn]" ;;
    *) RUNTIME="onnxruntime" ;;
  esac
fi

echo "Instalando el runtime de IA: $RUNTIME"
"$VENV_PY" -m pip uninstall -y onnxruntime onnxruntime-gpu onnxruntime-directml >/dev/null 2>&1 || true
"$VENV_PY" -m pip install "$RUNTIME"

# 5. Carpetas de trabajo.
mkdir -p fotos/entrada fotos/salida fotos/ejemplos

# 6. Descargar modelos y comprobar la instalacion.
echo "Descargando modelos de IA (puede tardar varios minutos) ..."
"$VENV_PY" -m editfoto descargar-modelos || { echo "ERROR: no se han podido descargar los modelos."; exit 1; }
echo
"$VENV_PY" -m editfoto info || { echo "ERROR: la comprobación final ha fallado."; exit 1; }

echo
echo "Instalación completada."
echo "Siguiente paso: ejecuta ./iniciar.sh para arrancar EDITFOTO."
