"""Borrado de objetos marcados con el pincel (LaMa, IA local).

Solo para lo que se superpone a la prenda (un cable que la cruza, una pinza,
una etiqueta del set). Lo que esta fuera de la prenda ya desaparece al cambiar
el fondo, no hace falta marcarlo.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import modelos

_LADO = 512
_TESELA = 320  # trazos mas largos se borran por trozos para no perder resolucion


def _rellenar_zona(img: np.ndarray, zona: np.ndarray, caja: tuple[int, int, int, int]) -> np.ndarray:
    """Rellena con LaMa la parte de `zona` que cae en un recorte centrado en `caja`."""
    h, w = zona.shape
    y0, y1, x0, x1 = caja
    # Recorte cuadrado con contexto alrededor (LaMa necesita ver la textura vecina).
    lado = int(max(y1 - y0, x1 - x0) * 2.2)
    lado = max(lado, min(_LADO, max(h, w)))
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    ry0, rx0 = cy - lado // 2, cx - lado // 2
    ry1, rx1 = ry0 + lado, rx0 + lado
    # Si el recorte se sale de la foto, se rellena por reflejo.
    pad = [max(0, -ry0), max(0, ry1 - h), max(0, -rx0), max(0, rx1 - w)]
    img_p = cv2.copyMakeBorder(img, *pad, cv2.BORDER_REFLECT_101)
    zona_p = cv2.copyMakeBorder(zona.astype(np.uint8), *pad, cv2.BORDER_CONSTANT, value=0)
    ry0, ry1, rx0, rx1 = ry0 + pad[0], ry1 + pad[0], rx0 + pad[2], rx1 + pad[2]
    recorte = img_p[ry0:ry1, rx0:rx1]
    zona_r = zona_p[ry0:ry1, rx0:rx1]

    x = cv2.resize(recorte, (_LADO, _LADO), interpolation=cv2.INTER_AREA if lado > _LADO else cv2.INTER_CUBIC)
    m = cv2.resize(zona_r, (_LADO, _LADO), interpolation=cv2.INTER_NEAREST)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8)).astype(np.float32)
    salida = modelos.ejecutar("lama", {"image": x.transpose(2, 0, 1)[None].astype(np.float32), "mask": m[None, None]})[0]
    relleno = np.clip(salida[0].transpose(1, 2, 0) / 255.0, 0, 1).astype(np.float32)
    relleno = cv2.resize(relleno, (lado, lado), interpolation=cv2.INTER_CUBIC)

    mezcla = cv2.GaussianBlur(cv2.dilate(zona_r, np.ones((3, 3), np.uint8)).astype(np.float32), (0, 0), 1.5)[..., None]
    nuevo = recorte * (1 - mezcla) + relleno * mezcla
    img_p = img_p.copy()
    img_p[ry0:ry1, rx0:rx1] = nuevo
    return img_p[pad[0]:pad[0] + h, pad[2]:pad[2] + w]


def borrar(img: np.ndarray, pincel: np.ndarray | None) -> np.ndarray:
    if pincel is None or pincel.max() < 0.3:
        return img
    zona = (pincel > 0.3).astype(np.uint8)
    # Zonas separadas se procesan por separado para no perder resolucion.
    n, etiquetas = cv2.connectedComponents(cv2.dilate(zona, np.ones((25, 25), np.uint8)))
    salida = img
    for i in range(1, n):
        trozo = (etiquetas == i) & (zona > 0)
        if trozo.sum() < 4:
            continue
        ys, xs = np.nonzero(trozo)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        if max(y1 - y0, x1 - x0) <= _TESELA:
            salida = _rellenar_zona(salida, trozo, (y0, y1, x0, x1))
            continue
        # Un cable largo: se recorre por teselas; cada una ya ve rellenas las anteriores.
        for ty in range(y0, y1, _TESELA):
            for tx in range(x0, x1, _TESELA):
                celda = trozo[ty:ty + _TESELA, tx:tx + _TESELA]
                if celda.sum() >= 4:
                    cy, cx = np.nonzero(celda)
                    caja = (ty + cy.min(), ty + cy.max() + 1, tx + cx.min(), tx + cx.max() + 1)
                    salida = _rellenar_zona(salida, trozo, caja)
    return salida.astype(np.float32)
