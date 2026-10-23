"""Correccion de color usando el fondo del set como referencia.

Idea: el fondo de tu set es siempre el mismo, asi que si en una foto sale mas
oscuro o mas azulado es culpa de la camara (exposicion y balance automaticos),
no de la prenda. Corregir la foto entera para que el fondo vuelva a su valor de
referencia deja la prenda con su color real y todas las fotos del lote iguales.
"""

from __future__ import annotations

import cv2
import numpy as np

from .imagen import lineal_a_srgb, srgb_a_lineal


def medir_fondo(img: np.ndarray, prenda: np.ndarray) -> dict | None:
    """Color mediano (en luz lineal) del fondo, lejos de la prenda."""
    h, w = prenda.shape
    margen = max(5, int(0.03 * np.sqrt(prenda.sum())))
    cerca = cv2.dilate(prenda.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margen + 1,) * 2))
    zona = cerca == 0
    if zona.sum() < 0.03 * h * w:
        return None
    lineal = srgb_a_lineal(img[zona])
    mediana = np.median(lineal, axis=0)
    uniforme = float(np.median(np.abs(lineal - mediana))) < 0.06
    return {"rgb": [float(c) for c in mediana], "uniforme": uniforme}


def es_neutro(rgb_lineal) -> bool:
    rgb = np.asarray(rgb_lineal)
    return rgb.max() > 0.02 and rgb.max() / max(rgb.min(), 1e-4) < 1.25


def referencia_de_lote(medidas: list[dict]) -> list[float] | None:
    """Referencia del lote: mediana de los fondos medidos."""
    validas = [m["rgb"] for m in medidas if m]
    if len(validas) < 3:
        return None
    return [float(c) for c in np.median(np.array(validas), axis=0)]


def mismo_set(medido, referencia) -> bool:
    """Si el fondo es muy distinto al de referencia, la foto es de otro set: no se iguala."""
    medido, referencia = np.asarray(medido, np.float32), np.asarray(referencia, np.float32)
    exposicion = float(np.exp(np.mean(np.log(np.maximum(referencia, 1e-4) / np.maximum(medido, 1e-4)))))
    tono = np.abs(medido / max(medido.mean(), 1e-4) - referencia / max(referencia.mean(), 1e-4)).max()
    return 0.55 < exposicion < 1.8 and tono < 0.15


def ganancias(fondo: dict | None, referencia: list[float] | None, igualar: bool, balance: bool) -> np.ndarray:
    """Multiplicadores por canal (en luz lineal) para esta foto."""
    if not fondo:
        return np.ones(3, dtype=np.float32)
    medido = np.array(fondo["rgb"], dtype=np.float32)
    objetivo = medido.copy()
    if igualar and referencia and mismo_set(medido, referencia):
        objetivo = np.array(referencia, dtype=np.float32)
    if balance and es_neutro(objetivo):
        objetivo = np.full(3, objetivo.mean(), dtype=np.float32)
    # Un fondo con un canal a cero (un fondo de color puro) daria log(0): se acota.
    g = np.maximum(objetivo, 1e-4) / np.maximum(medido, 1e-4)
    # Limites prudentes: corrige la camara, no reinventa la foto.
    exposicion = float(np.clip(np.exp(np.mean(np.log(g))), 0.6, 1.8))
    tinte = np.clip(g / np.exp(np.mean(np.log(g))), 0.85, 1.18)
    resultado = (tinte * exposicion).astype(np.float32)
    return resultado if np.isfinite(resultado).all() else np.ones(3, dtype=np.float32)


def aplicar(img: np.ndarray, g: np.ndarray, brillo: float = 0.0, contraste: float = 0.0,
            saturacion: float = 1.0) -> np.ndarray:
    g = g * (2.0 ** brillo)
    if np.allclose(g, 1) and contraste == 0 and saturacion == 1:
        return img
    lineal = srgb_a_lineal(img) * g
    # Las luces se comprimen suavemente en vez de quemarse.
    techo = 0.85
    alto = lineal > techo
    lineal[alto] = techo + (1 - techo) * np.tanh((lineal[alto] - techo) / (1 - techo))
    salida = lineal_a_srgb(lineal).astype(np.float32)
    if contraste:
        salida = np.clip(0.5 + (salida - 0.5) * (1 + contraste), 0, 1)
    if saturacion != 1:
        gris = salida.mean(axis=2, keepdims=True)
        salida = np.clip(gris + (salida - gris) * saturacion, 0, 1)
    return salida.astype(np.float32)
