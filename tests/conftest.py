"""Comun a todos los tests: el modelo de orientacion (DINOv2) no se descarga en las pruebas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editfoto import orientacion  # noqa: E402

GIRO_PROBABLE = orientacion.giro_probable
HUELLA = orientacion.huella


def huella_foto_simulada(img):
    """Sustituto de DINOv2 para las fotos enteras: la foto reducida (parecida si se parece)."""
    import cv2
    import numpy as np

    v = cv2.resize(img.astype(np.float32), (16, 8), interpolation=cv2.INTER_AREA).ravel()
    v = v - v.mean()
    return (v / max(np.linalg.norm(v), 1e-6)).astype(np.float32)


@pytest.fixture(autouse=True)
def sin_modelo_de_orientacion(monkeypatch):
    """Por defecto la prenda no se gira sola; los tests de orientacion usan un modelo simulado."""
    monkeypatch.setattr(orientacion, "giro_probable", lambda *a, **k: (0, 0.0))
    monkeypatch.setattr(orientacion, "huella", lambda *a, **k: None)
    monkeypatch.setattr(orientacion, "huella_foto", huella_foto_simulada)
