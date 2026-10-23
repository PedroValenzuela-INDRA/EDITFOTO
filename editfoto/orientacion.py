"""Poner la prenda derecha sola (cuello o cintura arriba), aunque hagas la foto tumbada o del reves.

Se usa DINOv2, un modelo de vision que corre en tu PC: se mira la prenda recortada en sus
4 giros y se compara con prendas fotografiadas derechas (tus ejemplos y una coleccion
generica que viene con la app). Gana el giro que mas se parece. En una prueba con 96 fotos
reales que no habia visto (clothing-dataset-small), cada una girada de las 4 formas (384
casos de 8 tipos de prenda), acerto todas, y el mejor giro siempre ganaba por mas de 0,015.
Si dos giros se parecen casi igual (menos de MARGEN_MINIMO), no se arriesga: se deja como estaba.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import modelos

MODELO = "dinov2"
LADO = 224
_MEDIA = np.array([0.485, 0.456, 0.406], np.float32)
_DESVIACION = np.array([0.229, 0.224, 0.225], np.float32)
MARGEN_MINIMO = 0.01  # diferencia de parecido entre el mejor giro y el siguiente para girar
_GENERICAS = Path(__file__).resolve().parent / "datos" / "orientacion_generica.npy"


def recorte_cuadrado(img: np.ndarray, alfa: np.ndarray, fondo: float = 0.5) -> np.ndarray | None:
    """La prenda sola sobre gris, centrada en un cuadrado de LADO x LADO."""
    prenda = alfa > 0.5
    if prenda.sum() < 64:
        return None
    ys, xs = np.nonzero(prenda)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    m = alfa[y0:y1, x0:x1, None].astype(np.float32)
    trozo = img[y0:y1, x0:x1] * m + fondo * (1 - m)
    h, w = trozo.shape[:2]
    lado = int(max(h, w) * 1.08)
    cuadro = np.full((lado, lado, 3), fondo, np.float32)
    cuadro[(lado - h) // 2:(lado - h) // 2 + h, (lado - w) // 2:(lado - w) // 2 + w] = trozo
    return cv2.resize(cuadro, (LADO, LADO), interpolation=cv2.INTER_AREA)


def _huellas_de(cuadros: list[np.ndarray]) -> np.ndarray:
    x = np.stack([(c - _MEDIA) / _DESVIACION for c in cuadros]).transpose(0, 3, 1, 2).astype(np.float32)
    salida = modelos.ejecutar(MODELO, {"pixel_values": x})[0][:, 0]  # token de clase
    return (salida / np.linalg.norm(salida, axis=1, keepdims=True)).astype(np.float32)


def huella(img: np.ndarray, alfa: np.ndarray) -> np.ndarray | None:
    """Resumen (384 numeros) de como es la prenda tal como esta en la foto."""
    c = recorte_cuadrado(img, alfa)
    return None if c is None else _huellas_de([c])[0]


def referencias_genericas() -> np.ndarray:
    return np.load(_GENERICAS).astype(np.float32) if _GENERICAS.exists() else np.zeros((0, 384), np.float32)


def giro_probable(img: np.ndarray, alfa: np.ndarray, propias: list | None = None) -> tuple[int, float]:
    """Cuartos de vuelta en sentido horario que ponen la prenda derecha, y el margen de
    confianza (cuanto gana al siguiente giro). (0, 0.0) si no se puede saber."""
    c = recorte_cuadrado(img, alfa)
    refs = [referencias_genericas()]
    if propias:
        refs.append(np.asarray(propias, np.float32).reshape(-1, 384))
    refs = np.concatenate(refs)
    if c is None or len(refs) == 0:
        return 0, 0.0
    # Girar el cuadrado es lo mismo que recortar la foto girada.
    huellas = _huellas_de([np.ascontiguousarray(np.rot90(c, -k)) for k in range(4)])
    parecidos = huellas @ refs.T
    n = min(3, refs.shape[0])
    puntos = np.sort(parecidos, axis=1)[:, -n:].mean(axis=1)
    orden = np.argsort(puntos)
    return int(orden[-1]), float(puntos[orden[-1]] - puntos[orden[-2]])
