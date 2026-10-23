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
    nombre = modelos.modelo_segmentacion(modelo)
    s = modelos.sesion(nombre)
    x = cv2.resize(img, (_LADO, _LADO), interpolation=cv2.INTER_AREA if max(h, w) > _LADO else cv2.INTER_LINEAR)
    x = ((x - _MEDIA) / _DESV).transpose(2, 0, 1)[None].astype(np.float32)
    salida = modelos.ejecutar(nombre, {s.get_inputs()[0].name: x})[0][0, 0]
    alfa = 1.0 / (1.0 + np.exp(-salida))  # el modelo devuelve logits
    return np.clip(cv2.resize(alfa.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR), 0, 1)


_LADO_MATE = 1024
_SOLAPE = 96


def afinar_bordes(img: np.ndarray, alfa: np.ndarray, cambio_maximo: float = 0.12) -> tuple[np.ndarray, str]:
    """Afina el borde del recorte con ViTMatte (matting guiado).

    El recorte general trabaja a 1024 px y se le escapan detalles: la esquina de un puno
    tapada por pelos de alfombra, el final de una manga. Aqui se marca una franja de duda
    alrededor del borde (por dentro es prenda seguro, por fuera es suelo seguro) y ViTMatte
    decide pixel a pixel, a resolucion completa, mirando los colores de los dos lados.
    Si el resultado cambia demasiado la prenda, se descarta. Devuelve (alfa, explicacion)."""
    prenda = alfa > 0.5
    area = int(prenda.sum())
    if area < 2000:
        return alfa, ""
    tam = float(np.sqrt(area))
    elipse = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))  # noqa: E731
    p8 = prenda.astype(np.uint8)
    seguro = cv2.erode(p8, elipse(max(2, int(0.015 * tam)))) > 0
    fuera = ~(cv2.dilate(p8, elipse(max(4, int(0.05 * tam)))) > 0)  # cabe la esquina de un puno
    tri = np.full(prenda.shape, 0.5, np.float32)
    tri[seguro], tri[fuera] = 1.0, 0.0
    duda = tri == 0.5
    h, w = prenda.shape
    ys, xs = np.nonzero(duda)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    suma = np.zeros((h, w), np.float32)
    peso = np.zeros((h, w), np.float32)
    paso = _LADO_MATE - _SOLAPE
    for ty in range(y0, max(y0 + 1, y1 - _SOLAPE), paso):
        for tx in range(x0, max(x0 + 1, x1 - _SOLAPE), paso):
            a0, b0 = min(ty, max(0, h - _LADO_MATE)), min(tx, max(0, w - _LADO_MATE))
            a1, b1 = min(h, a0 + _LADO_MATE), min(w, b0 + _LADO_MATE)
            if not duda[a0:a1, b0:b1].any():
                continue
            th, tw = a1 - a0, b1 - b0
            H, W = (th + 31) // 32 * 32, (tw + 31) // 32 * 32
            x = np.zeros((1, 4, H, W), np.float32)
            x[0, :3, :th, :tw] = ((img[a0:a1, b0:b1] - 0.5) / 0.5).transpose(2, 0, 1)
            x[0, 3, :th, :tw] = tri[a0:a1, b0:b1]
            mate = modelos.ejecutar("vitmatte", {"pixel_values": x})[0][0, 0, :th, :tw]
            v = np.minimum(np.minimum(np.arange(th) + 1, th - np.arange(th))[:, None],
                           np.minimum(np.arange(tw) + 1, tw - np.arange(tw))[None]).astype(np.float32)
            v = np.clip(v / (_SOLAPE / 2), 0.02, 1)  # transicion suave entre trozos
            suma[a0:a1, b0:b1] += np.clip(mate, 0, 1) * v
            peso[a0:a1, b0:b1] += v
    afinada = np.where(duda & (peso > 0), suma / np.maximum(peso, 1e-6), tri).astype(np.float32)
    afinada = np.where(duda & (peso == 0), alfa, afinada)
    cambio = float(np.abs((afinada > 0.5).astype(np.int8) - prenda.astype(np.int8)).sum()) / area
    if cambio > cambio_maximo:  # algo raro (la prenda se parece mucho al suelo): mejor no tocar
        return alfa, f"bordes sin afinar (cambiaban un {cambio * 100:.0f} % de la prenda)"
    return afinada, f"bordes afinados ({cambio * 100:.1f} % de la prenda)"
