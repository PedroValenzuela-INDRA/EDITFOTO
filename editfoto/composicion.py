"""Enderezado, encuadre en el lienzo, fondo nuevo y sombra."""

from __future__ import annotations

import cv2
import numpy as np

from .imagen import color_hex, cargar


def _simetria(mascara: np.ndarray, angulo: float, centro) -> float:
    h, w = mascara.shape
    # Gira y lleva el centro de masas al centro horizontal, luego compara con su reflejo.
    M = cv2.getRotationMatrix2D(centro, angulo, 1.0)
    M[0, 2] += w / 2 - centro[0]
    girada = cv2.warpAffine(mascara, M, (w, h), flags=cv2.INTER_NEAREST) > 0
    espejo = girada[:, ::-1]
    union = (girada | espejo).sum()
    return float((girada & espejo).sum() / union) if union else 0.0


def angulo_enderezado(prenda: np.ndarray, max_grados: float) -> float:
    """Angulo (grados, antihorario) que hace la prenda lo mas simetrica posible."""
    if max_grados <= 0 or prenda.sum() < 500:
        return 0.0
    h, w = prenda.shape
    escala = 256 / max(h, w)
    peq = cv2.resize(prenda.astype(np.uint8), (max(1, round(w * escala)), max(1, round(h * escala))),
                     interpolation=cv2.INTER_NEAREST)
    # Margen para que al girar no se corte.
    lado = int(max(peq.shape) * 1.5)
    lienzo = np.zeros((lado, lado), np.uint8)
    oy, ox = (lado - peq.shape[0]) // 2, (lado - peq.shape[1]) // 2
    lienzo[oy:oy + peq.shape[0], ox:ox + peq.shape[1]] = peq
    m = cv2.moments(lienzo, binaryImage=True)
    centro = (m["m10"] / m["m00"], m["m01"] / m["m00"])

    base = _simetria(lienzo, 0.0, centro)
    angulos = np.arange(-max_grados, max_grados + 1e-6, 0.5)
    puntos = [_simetria(lienzo, a, centro) for a in angulos]
    mejor = float(angulos[int(np.argmax(puntos))])
    finos = np.arange(mejor - 0.4, mejor + 0.41, 0.1)
    puntos_f = [_simetria(lienzo, a, centro) for a in finos]
    mejor = float(finos[int(np.argmax(puntos_f))])
    # Solo se gira si la prenda es claramente simetrica y la mejora es real: una prenda
    # colocada asimetrica (una manga doblada, un bolso de lado) no se toca.
    if max(puntos_f) < 0.85 or max(puntos_f) - base < 0.01:
        return 0.0
    return float(np.clip(mejor, -max_grados, max_grados))


def encuadrar(img: np.ndarray, alfa: np.ndarray, lienzo: tuple[int, int], relleno: float,
              centro_x: float, centro_y: float, angulo: float = 0.0, escala_extra: float = 1.0,
              mover_x: float = 0.0, mover_y: float = 0.0, borde_reflejo: bool = False):
    """Gira, escala y coloca la prenda en el lienzo. Devuelve (img, alfa, info)."""
    ancho, alto = lienzo
    prenda = (alfa > 0.5).astype(np.uint8)
    ys, xs = np.nonzero(prenda)
    if len(xs) == 0:
        ys, xs = np.nonzero(np.ones_like(prenda))
    puntos = np.stack([xs, ys], 1).astype(np.float32)
    centro = (float((xs.min() + xs.max()) / 2), float((ys.min() + ys.max()) / 2))

    R = cv2.getRotationMatrix2D(centro, angulo, 1.0)
    # Caja de la prenda ya girada (con el contorno basta, es mas rapido).
    contornos, _ = cv2.findContours(prenda, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pts = np.concatenate([c.reshape(-1, 2) for c in contornos]).astype(np.float32) if contornos else puntos
    girados = pts @ R[:, :2].T + R[:, 2]
    x0, y0 = girados.min(0)
    x1, y1 = girados.max(0)
    bw, bh = max(x1 - x0, 1), max(y1 - y0, 1)
    escala = relleno * min(ancho / bw, alto / bh) * escala_extra
    destino = np.array([centro_x * ancho + mover_x * ancho, centro_y * alto + mover_y * alto])
    caja_centro = np.array([(x0 + x1) / 2, (y0 + y1) / 2])

    # Reducir mucho con warpAffine produce dientes de sierra: primero se reduce con INTER_AREA.
    pre = 1.0
    if escala < 0.75:
        pre = escala / 0.75
        h, w = alfa.shape
        tam = (max(1, round(w * pre)), max(1, round(h * pre)))
        img = cv2.resize(img, tam, interpolation=cv2.INTER_AREA)
        alfa = cv2.resize(alfa, tam, interpolation=cv2.INTER_AREA)
    s = escala / pre
    # p' = escala * (R p - caja_centro) + destino, expresado sobre la imagen ya prerreducida.
    A = R[:, :2] * escala
    t = escala * (R[:, 2] - caja_centro) + destino
    M = np.hstack([A / pre, t[:, None]]).astype(np.float64)
    borde = cv2.BORDER_REFLECT_101 if borde_reflejo else cv2.BORDER_CONSTANT
    img_l = cv2.warpAffine(img, M, (ancho, alto), flags=cv2.INTER_CUBIC, borderMode=borde)
    alfa_l = cv2.warpAffine(alfa, M, (ancho, alto), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    info = {"angulo": round(float(angulo), 2), "escala": round(float(escala), 4),
            "caja": [round(float(v), 1) for v in (x0, y0, x1, y1)], "ampliacion": round(float(s), 3)}
    return np.clip(img_l, 0, 1).astype(np.float32), np.clip(alfa_l, 0, 1).astype(np.float32), info


def _fondo(preset_fondo: dict, ancho: int, alto: int) -> np.ndarray:
    if preset_fondo.get("tipo") == "imagen" and preset_fondo.get("imagen"):
        try:
            img = cargar(preset_fondo["imagen"])
            h, w = img.shape[:2]
            e = max(ancho / w, alto / h)
            img = cv2.resize(img, (max(ancho, round(w * e)), max(alto, round(h * e))), interpolation=cv2.INTER_AREA)
            y, x = (img.shape[0] - alto) // 2, (img.shape[1] - ancho) // 2
            return img[y:y + alto, x:x + ancho].astype(np.float32)
        except Exception as e:
            print(f"Aviso: no se pudo cargar el fondo {preset_fondo['imagen']}: {e}")
    color = color_hex(preset_fondo.get("color", "#F4F4F2"))
    return np.broadcast_to(color, (alto, ancho, 3)).astype(np.float32).copy()


def sombra(alfa: np.ndarray, opacidad: float, desenfoque: float, dx: float, dy: float) -> np.ndarray:
    if opacidad <= 0:
        return np.zeros_like(alfa)
    tam = float(np.sqrt(max(alfa.sum(), 1.0)))
    sigma = max(1.0, desenfoque * tam)
    M = np.float32([[1, 0, dx * tam], [0, 1, dy * tam]])
    desplazada = cv2.warpAffine(alfa, M, (alfa.shape[1], alfa.shape[0]))
    return np.clip(cv2.GaussianBlur(desplazada, (0, 0), sigma) * opacidad, 0, 1)


def componer(frente: np.ndarray, alfa: np.ndarray, preset_fondo: dict, preset_sombra: dict) -> np.ndarray:
    alto, ancho = alfa.shape
    fondo = _fondo(preset_fondo, ancho, alto)
    s = sombra(alfa, preset_sombra.get("opacidad", 0), preset_sombra.get("desenfoque", 0.03),
               preset_sombra.get("desplazamiento_x", 0), preset_sombra.get("desplazamiento_y", 0))
    fondo = fondo * (1 - s[..., None])
    a = alfa[..., None]
    return (frente * a + fondo * (1 - a)).astype(np.float32)


def enfocar(img: np.ndarray, alfa: np.ndarray, cantidad: float) -> np.ndarray:
    """Enfoque suave (mascara de enfoque) solo sobre la prenda."""
    if cantidad <= 0:
        return img
    suave = cv2.GaussianBlur(img, (0, 0), 1.0)
    detalle = img + cantidad * (img - suave)
    a = alfa[..., None]
    return np.clip(img * (1 - a) + detalle * a, 0, 1).astype(np.float32)
