#!/usr/bin/env bash
# Arranca el servidor de EDITFOTO (equivalente a iniciar.bat).
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "No se encuentra el entorno de EDITFOTO."
  echo "Ejecuta primero ./instalar.sh."
  exit 1
fi

echo "Arrancando EDITFOTO. Se abrirá el navegador con la aplicación."
echo "Para cerrar el servidor, pulsa Ctrl+C."
exec .venv/bin/python -m editfoto servidor --entrada fotos/entrada --salida fotos/salida --abrir
