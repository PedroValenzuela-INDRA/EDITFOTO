"""Limpieza de la mascara de la prenda y colores limpios en los bordes.

Todo lo que queda fuera de la mascara (cables, tripode, enchufes, el suelo...)
desaparece al poner el fondo nuevo, asi que aqui solo hay que asegurarse de que
la mascara contiene la prenda y nada mas.
"""

from __future__ import annotations

import cv2
import numpy as np


def _componentes(binaria: np.ndarray):
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(binaria.astype(np.uint8), connectivity=8)
    return n, etiquetas, stats


def _quitar_hilos_al_borde(binaria: np.ndarray, grosor: int) -> np.ndarray:
    """Quita partes finas y alargadas que salen de la prenda hasta el borde de la foto.

    Un cable o la pata del tripode suelen cruzar hasta el borde; un cordon de
    sudadera o un tirante no, asi que esos se respetan.
    """
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grosor, grosor))
    abierta = cv2.morphologyEx(binaria.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)
    finas = binaria & ~abierta
    n, etiquetas, stats = _componentes(finas)
    h, w = binaria.shape
    salida = binaria.copy()
    for i in range(1, n):
        x, y, ancho, alto, area = stats[i]
        toca_borde = x <= 1 or y <= 1 or x + ancho >= w - 1 or y + alto >= h - 1
        alargada = max(ancho, alto) >= 4 * grosor and area < 0.6 * max(ancho, alto) * grosor * 2
        if toca_borde and alargada:
            salida[etiquetas == i] = False
    return salida


def limpiar(alfa: np.ndarray, min_componente: float = 0.08, max_hueco: float = 0.004,
            quitar_cables: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (alfa_limpio, prenda_binaria).

    - Se queda con la pieza principal y las que sean al menos `min_componente`
      de su tamano (dos zapatillas, un conjunto de dos piezas...).
    - Rellena agujeros pequenos (menos de `max_hueco` del area): se ve el pixel
      original, asi un roto real sigue viendose tal cual.
    """
    binaria = alfa > 0.5
    n, etiquetas, stats = _componentes(binaria)
    if n <= 1:
        return alfa, binaria
    areas = stats[1:, cv2.CC_STAT_AREA]
    mayor = areas.max()
    conservar = np.zeros(n, dtype=bool)
    conservar[1:] = areas >= min_componente * mayor
    prenda = conservar[etiquetas]

    if quitar_cables:
        grosor = max(7, int(0.03 * np.sqrt(prenda.sum())))
        prenda = _quitar_hilos_al_borde(prenda, grosor)
        # Quitar el hilo puede dejar islas sueltas: volver a filtrar.
        n, etiquetas, stats = _componentes(prenda)
        if n > 1:
            areas = stats[1:, cv2.CC_STAT_AREA]
            conservar = np.zeros(n, dtype=bool)
            conservar[1:] = areas >= min_componente * areas.max()
            prenda = conservar[etiquetas]

    # Agujeros pequenos: componentes del fondo que no tocan el borde.
    fondo = ~prenda
    n, etiquetas, stats = _componentes(fondo)
    h, w = prenda.shape
    area_prenda = prenda.sum()
    rellenos = np.zeros_like(prenda)
    for i in range(1, n):
        x, y, ancho, alto, area = stats[i]
        toca_borde = x == 0 or y == 0 or x + ancho == w or y + alto == h
        if not toca_borde and area < max_hueco * area_prenda:
            rellenos |= etiquetas == i
    prenda |= rellenos

    # El alfa suave del modelo se respeta solo cerca de lo que hemos conservado.
    cerca = cv2.dilate(prenda.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))).astype(bool)
    alfa_limpio = np.where(cerca, alfa, 0.0).astype(np.float32)
    alfa_limpio[rellenos] = 1.0
    return alfa_limpio, prenda


def aplicar_pinceles(alfa: np.ndarray, sumar: np.ndarray | None, restar: np.ndarray | None) -> np.ndarray:
    """Correcciones manuales: pintar zonas que son prenda o que no lo son."""
    alfa = alfa.copy()
    if sumar is not None:
        alfa = np.maximum(alfa, sumar)
    if restar is not None:
        alfa = alfa * (1.0 - restar)
    return alfa


def _fusion_desenfoque(img, alfa, frente, fondo, radio):
    a = alfa[..., None]
    a_suave = cv2.blur(alfa, (radio, radio))[..., None]
    f_suave = cv2.blur(frente * a, (radio, radio)) / (a_suave + 1e-5)
    b_suave = cv2.blur(fondo * (1 - a), (radio, radio)) / ((1 - a_suave) + 1e-5)
    frente = f_suave + a * (img - a * f_suave - (1 - a) * b_suave)
    return np.clip(frente, 0, 1), b_suave


def color_frente(img: np.ndarray, alfa: np.ndarray) -> np.ndarray:
    """Quita el color del fondo antiguo que se cuela en los bordes (halo).

    Metodo "Approximate Fast Foreground Colour Estimation" (Forte y Pitie, 2021).
    """
    r1 = max(15, int(0.045 * max(img.shape[:2])))
    frente, fondo = _fusion_desenfoque(img, alfa, img, img, r1)
    frente, _ = _fusion_desenfoque(img, alfa, frente, fondo, 6)
    # Dentro de la prenda los pixeles se quedan exactamente como estaban.
    solido = (alfa > 0.98)[..., None]
    return np.where(solido, img, frente).astype(np.float32)
