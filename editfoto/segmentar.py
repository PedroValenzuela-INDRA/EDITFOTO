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


def refinar_bordes(img: np.ndarray, alfa: np.ndarray, modelo: str = "auto", max_zonas: int = 12,
                   acuerdo_minimo: float = 0.95) -> tuple[np.ndarray, int]:
    """Segundo recorte por zonas a mas resolucion, solo para el borde de la prenda.

    En una foto entera el modelo trabaja a 1024 px y se le escapan detalles (la esquina de un
    puno tapada por pelos de alfombra). Aqui se recortan trozos del borde y se vuelven a
    pasar por el modelo. Un trozo sin el resto de la foto a veces confunde que es la prenda,
    asi que solo se acepta si coincide con el recorte general lejos del borde, y solo se usa
    en la franja del borde. Devuelve (alfa, zonas aceptadas)."""
    prenda = alfa > 0.5
    if prenda.sum() < 1000:
        return alfa, 0
    h, w = prenda.shape
    ys, xs = np.nonzero(prenda)
    lado = int(np.clip(0.45 * max(np.ptp(ys), np.ptp(xs)), 256, max(h, w)))
    tam = float(np.sqrt(prenda.sum()))
    banda_r = max(4, int(0.06 * tam))  # cabe la esquina entera de un puno
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * banda_r + 1, 2 * banda_r + 1))
    p8 = prenda.astype(np.uint8)
    banda = (cv2.dilate(p8, k) > 0) & ~(cv2.erode(p8, k) > 0)

    contornos, _ = cv2.findContours(p8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    puntos = max(contornos, key=cv2.contourArea).reshape(-1, 2)
    largo = np.r_[0, np.cumsum(np.linalg.norm(np.diff(puntos, axis=0), axis=1))]
    centros = [puntos[np.searchsorted(largo, d)] for d in np.arange(0, largo[-1], lado / 2)][:max_zonas]

    suma = np.zeros((h, w), np.float32)
    peso = np.zeros((h, w), np.float32)
    v = np.hanning(lado + 2)[1:-1].astype(np.float32)
    ventana = np.outer(v, v) + 1e-3
    aceptadas = 0
    for cx, cy in centros:
        x0 = int(np.clip(cx - lado // 2, 0, max(0, w - lado)))
        y0 = int(np.clip(cy - lado // 2, 0, max(0, h - lado)))
        x1, y1 = min(w, x0 + lado), min(h, y0 + lado)
        a = segmentar(img[y0:y1, x0:x1], modelo)
        lejos = ~banda[y0:y1, x0:x1]
        g, t = prenda[y0:y1, x0:x1][lejos], (a > 0.5)[lejos]
        union = (g | t).sum()
        if union == 0 or (g & t).sum() / union < acuerdo_minimo:
            continue
        aceptadas += 1
        vz = ventana[:y1 - y0, :x1 - x0]
        suma[y0:y1, x0:x1] += a * vz
        peso[y0:y1, x0:x1] += vz
    if not aceptadas:
        return alfa, 0
    nueva = np.where(peso > 1e-3, suma / np.maximum(peso, 1e-6), alfa)
    # Solo en la franja del borde, con transicion suave.
    mezcla = cv2.GaussianBlur((banda & (peso > 1e-3)).astype(np.float32), (0, 0), banda_r / 3)
    return np.clip(alfa + mezcla * (nueva - alfa), 0, 1).astype(np.float32), aceptadas
