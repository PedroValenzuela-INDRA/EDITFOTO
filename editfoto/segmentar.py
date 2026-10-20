"""Recorte de la prenda con BiRefNet (IA local). Devuelve un mapa alfa en [0, 1]."""

from __future__ import annotations

import cv2
import numpy as np

from . import modelos

_MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DESV = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_LADO = 1024


def segmentar(img: np.ndarray, modelo: str = "auto") -> np.ndarray:
    h, w = img.shape[:2]
    s = modelos.sesion(modelos.modelo_segmentacion(modelo))
    x = cv2.resize(img, (_LADO, _LADO), interpolation=cv2.INTER_AREA if max(h, w) > _LADO else cv2.INTER_LINEAR)
    x = ((x - _MEDIA) / _DESV).transpose(2, 0, 1)[None].astype(np.float32)
    salida = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    alfa = 1.0 / (1.0 + np.exp(-salida))  # el modelo devuelve logits
    return np.clip(cv2.resize(alfa.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR), 0, 1)
