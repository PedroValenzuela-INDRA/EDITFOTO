"""Comun a todos los tests: el modelo de orientacion (DINOv2) no se descarga en las pruebas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editfoto import orientacion  # noqa: E402

GIRO_PROBABLE = orientacion.giro_probable
HUELLA = orientacion.huella


@pytest.fixture(autouse=True)
def sin_modelo_de_orientacion(monkeypatch):
    """Por defecto la prenda no se gira sola; los tests de orientacion usan un modelo simulado."""
    monkeypatch.setattr(orientacion, "giro_probable", lambda *a, **k: (0, 0.0))
    monkeypatch.setattr(orientacion, "huella", lambda *a, **k: None)
