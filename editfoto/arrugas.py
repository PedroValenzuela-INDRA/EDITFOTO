"""Suavizado de arrugas por separacion de frecuencias con filtro guiado.

Una arruga es sobre todo una sombra suave: cambia la luminosidad de una zona
media sin cambiar el color del tejido. Se separa la luminosidad en tres capas:

- textura fina (punto, trama, bolitas, manchas pequenas, costuras) -> intacta
- sombras de tamano medio (arrugas) -> se atenuan segun la fuerza
- iluminacion general y zonas de distinto color (estampados, logos) -> intactas

El filtro de dominio (domain transform) guiado por el color impide que el
suavizado cruce bordes de color, asi que un logo o una mancha con color propio
no se difuminan. Lo que marques con el pincel "proteger" no se toca nunca.
"""

from __future__ import annotations

import cv2
import numpy as np


def suavizar(img: np.ndarray, alfa: np.ndarray, fuerza: float, escala: float = 0.10,
             respeto_bordes: float = 0.5, proteger: np.ndarray | None = None) -> np.ndarray:
    if fuerza <= 0:
        return img
    prenda = (alfa > 0.5).astype(np.float32)
    area = prenda.sum()
    if area < 1000:
        return img
    tam = float(np.sqrt(area))

    lab = cv2.cvtColor(img, cv2.COLOR_RGB2Lab)  # L en [0, 100]
    L = lab[..., 0] / 100.0

    s_fino = max(1.5, 0.004 * tam)
    s_medio = max(8.0, escala * tam)
    # La guia usa la luminosidad atenuada y el color completo: las sombras (solo luminosidad)
    # se suavizan con facilidad y los bordes de color frenan el suavizado.
    peso_l = 0.35 + 0.65 * respeto_bordes
    guia = np.dstack([
        cv2.GaussianBlur(lab[..., 0] * 2.55 * peso_l, (0, 0), s_fino),
        cv2.GaussianBlur(lab[..., 1] + 128, (0, 0), s_fino),
        cv2.GaussianBlur(lab[..., 2] + 128, (0, 0), s_fino),
    ]).astype(np.float32)
    sigma_color = 30.0

    def suavizado(sigma):
        filtro = cv2.ximgproc.createDTFilter(guia, sigma, sigma_color, mode=cv2.ximgproc.DTF_NC, numIters=3)
        # Convolucion normalizada: el fondo no contamina el borde de la prenda.
        num = filtro.filter((L * prenda).astype(np.float32))
        den = filtro.filter(prenda)
        return num / np.maximum(den, 1e-4)

    bajo = suavizado(s_fino)     # sin textura fina
    plano = suavizado(s_medio)   # sin arrugas
    sombras = np.clip(bajo - plano, -0.25, 0.25)

    peso = cv2.GaussianBlur(cv2.erode(prenda, np.ones((3, 3), np.uint8)), (0, 0), 2.0)
    if proteger is not None:
        peso *= 1.0 - cv2.GaussianBlur(proteger.astype(np.float32), (0, 0), 3.0)
    L_nueva = np.clip(L - float(fuerza) * peso * sombras, 0, 1)

    lab[..., 0] = L_nueva * 100.0
    nueva = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1)
    # Fuera de la zona tratada, los pixeles originales exactos (sin error de ida y vuelta a Lab).
    return np.where((peso > 1e-3)[..., None], nueva, img).astype(np.float32)
