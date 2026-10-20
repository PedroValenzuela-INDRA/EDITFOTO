"""Fotos sinteticas de prueba con la mascara real conocida.

Simulan una sudadera en el suelo del set: fondo gris con algo de ruido, la
prenda con textura de punto, arrugas (sombras suaves), una mancha (defecto que
debe conservarse), un cordon que cuelga (debe conservarse), un cable que sale
hasta el borde de la foto y la pata de un tripode (deben desaparecer).
"""

from __future__ import annotations

import cv2
import numpy as np


def silueta_sudadera(alto: int = 900, ancho: int = 1200, angulo: float = 0.0) -> np.ndarray:
    m = np.zeros((alto, ancho), np.uint8)
    cx, cy = ancho // 2, alto // 2
    cuerpo = np.array([[cx - 180, cy - 250], [cx + 180, cy - 250], [cx + 190, cy + 280], [cx - 190, cy + 280]])
    manga_i = np.array([[cx - 180, cy - 250], [cx - 400, cy + 120], [cx - 330, cy + 160], [cx - 180, cy - 80]])
    manga_d = manga_i.copy()
    manga_d[:, 0] = 2 * cx - manga_d[:, 0]
    for p in (cuerpo, manga_i, manga_d):
        cv2.fillPoly(m, [p.astype(np.int32)], 1)
    cv2.ellipse(m, (cx, cy - 250), (70, 40), 0, 0, 180, 0, -1)  # cuello
    if angulo:
        R = cv2.getRotationMatrix2D((cx, cy), angulo, 1.0)
        m = cv2.warpAffine(m, R, (ancho, alto), flags=cv2.INTER_NEAREST)
    return m.astype(bool)


def foto_sintetica(semilla: int = 0, angulo: float = 0.0, exposicion: float = 1.0):
    """Devuelve (img float32 RGB, alfa_verdadero, datos) con las posiciones de mancha, cable, etc."""
    rng = np.random.default_rng(semilla)
    alto, ancho = 900, 1200
    fondo = np.full((alto, ancho, 3), 0.62, np.float32) + rng.normal(0, 0.01, (alto, ancho, 1)).astype(np.float32)
    prenda = silueta_sudadera(alto, ancho, angulo)

    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    color = np.array([0.20, 0.35, 0.60], np.float32)  # azul
    punto = 0.04 * np.sin(xx * 1.9) * np.sin(yy * 1.7)  # textura fina
    arrugas = 0.12 * np.sin(xx / 38.0 + yy / 55.0)      # sombras de tamano medio
    luz = (1 + punto + arrugas)[..., None]
    tela = np.clip(color * luz, 0, 1)

    img = np.where(prenda[..., None], tela, fondo)
    # Cordon de la capucha: fino, cuelga sobre la prenda y algo fuera, sin llegar al borde.
    cv2.line(img, (ancho // 2 + 30, alto // 2 - 230), (ancho // 2 + 30, alto // 2 + 330), (0.9, 0.9, 0.9), 7)
    cordon = np.zeros((alto, ancho), np.uint8)
    cv2.line(cordon, (ancho // 2 + 30, alto // 2 - 230), (ancho // 2 + 30, alto // 2 + 330), 1, 7)
    # Mancha (defecto real): circulo marron claro.
    mancha_c = (ancho // 2 - 90, alto // 2 + 60)
    cv2.circle(img, mancha_c, 14, (0.45, 0.38, 0.25), -1, cv2.LINE_AA)
    # Cable que sale de la prenda hasta el borde derecho.
    cv2.line(img, (ancho // 2 + 150, alto // 2 + 200), (ancho - 1, alto // 2 + 300), (0.05, 0.05, 0.05), 6)
    cable = np.zeros((alto, ancho), np.uint8)
    cv2.line(cable, (ancho // 2 + 150, alto // 2 + 200), (ancho - 1, alto // 2 + 300), 1, 6)
    # Pata de tripode en la esquina (fuera de la prenda).
    cv2.rectangle(img, (40, 600), (70, alto - 1), (0.3, 0.3, 0.32), -1)

    img = np.clip(img * exposicion, 0, 1).astype(np.float32)
    # El "modelo" ve prenda + cordon + cable (el peor caso): la limpieza debe quitar solo el cable.
    alfa_modelo = (prenda | (cordon > 0) | (cable > 0)).astype(np.float32)
    alfa_modelo = cv2.GaussianBlur(alfa_modelo, (0, 0), 1.0)
    datos = {"prenda": prenda, "cordon": cordon > 0, "cable": (cable > 0) & ~prenda, "mancha": mancha_c,
             "color": color}
    return img, alfa_modelo, datos
