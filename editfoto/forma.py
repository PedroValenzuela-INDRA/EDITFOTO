"""Adaptar la forma de la prenda a la de tus fotos de ejemplo (mangas en arco, cuerpo mas ancho...).

No se inventa nada: se deforma la foto real de la prenda, como el "licuar" de Photoshop
pero automatico. Los pixeles (tejido, logos, desperfectos) son los de verdad, solo
doblados. Lo que no estaba en la foto (p. ej. el forro de un bajo doblado) no puede
aparecer: para eso hay que colocar la prenda asi al hacer la foto.

Como funciona:
1. Se saca la silueta de la prenda y la del ejemplo, suavizadas (sin los picos de un
   bajo ondulado) y con el mismo numero de puntos.
2. Se emparejan los puntos (cuello con cuello, puno con puno) buscando el giro de la
   lista que mejor encaja, y la silueta del ejemplo se escala para tener la misma area:
   la prenda cambia de forma, no de tamano.
3. Se calcula una deformacion "lo mas rigida posible" (Moving Least Squares, Schaefer
   2006) que lleva una silueta a la otra, se suaviza y se aplica a la foto y a su recorte.
"""

from __future__ import annotations

import cv2
import numpy as np

PUNTOS = 64
ARMONICOS = 20       # detalle que se conserva de la silueta (menos = mas suave)
DISTANCIA_MAXIMA = 0.10  # siluetas mas distintas que esto no se adaptan (p. ej. sudadera sobre pantalon o prenda tumbada)


def _cruz(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def silueta(mascara: np.ndarray, n: int = PUNTOS) -> np.ndarray | None:
    """Contorno exterior de la pieza mas grande: n puntos suavizados, en sentido horario."""
    cs, _ = cv2.findContours(mascara.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)
    if len(c) < 20:
        return None
    if _cruz(c - c.mean(0), np.roll(c, -1, 0) - c.mean(0)).sum() < 0:
        c = c[::-1]
    # Remuestreo uniforme por longitud de arco y suavizado de Fourier.
    cerrado = np.vstack([c, c[:1]])
    largo = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cerrado, axis=0), axis=1))]
    t = np.linspace(0, largo[-1], 256, endpoint=False)
    z = np.interp(t, largo, cerrado[:, 0]) + 1j * np.interp(t, largo, cerrado[:, 1])
    f = np.fft.fft(z)
    f[ARMONICOS + 1:-ARMONICOS] = 0
    z = np.fft.ifft(f)
    z = z[:: 256 // n][:n]
    return np.stack([z.real, z.imag], 1)


def normalizar(c: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Centrada en su caja y escalada a lado 1. Devuelve (normalizada, centro, escala)."""
    x0, y0 = c.min(0)
    x1, y1 = c.max(0)
    centro = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    escala = float(max(x1 - x0, y1 - y0, 1e-6))
    return (c - centro) / escala, centro, escala


def emparejar(referencia: np.ndarray, otra: np.ndarray) -> tuple[np.ndarray, float]:
    """Gira la lista de puntos de `otra` para que cada punto caiga junto a su pareja en
    `referencia` (ambas normalizadas). Devuelve (otra emparejada, distancia media)."""
    errores = [np.mean(np.linalg.norm(np.roll(otra, k, 0) - referencia, axis=1)) for k in range(len(otra))]
    k = int(np.argmin(errores))
    return np.roll(otra, k, 0), float(errores[k])


def area(c: np.ndarray) -> float:
    return abs(_cruz(c, np.roll(c, -1, 0)).sum()) / 2


def media_de_siluetas(siluetas: list[np.ndarray]) -> np.ndarray:
    """Silueta tipo de varios ejemplos (normalizadas y emparejadas con la primera)."""
    base = normalizar(siluetas[0])[0]
    alineadas = [base] + [emparejar(base, normalizar(s)[0])[0] for s in siluetas[1:]]
    return normalizar(np.mean(alineadas, axis=0))[0]


def _mls_rigido(p: np.ndarray, q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Moving Least Squares rigido: deformacion de los puntos v que lleva p a q."""
    d = v[:, None, :] - p[None]
    w = 1.0 / (np.sum(d * d, axis=2) + 1e-8)
    ws = w.sum(1, keepdims=True)
    p_e = (w[..., None] * p[None]).sum(1) / ws
    q_e = (w[..., None] * q[None]).sum(1) / ws
    ph = p[None] - p_e[:, None]
    qh = q[None] - q_e[:, None]
    r = v - p_e
    perp = lambda a: np.stack([-a[..., 1], a[..., 0]], -1)  # noqa: E731
    rp = perp(r)
    php = perp(ph)
    a = (ph * r[:, None]).sum(-1)
    b = -(ph * rp[:, None]).sum(-1)
    c = -(php * r[:, None]).sum(-1)
    e = (php * rp[:, None]).sum(-1)
    fx = (w * (qh[..., 0] * a + qh[..., 1] * c)).sum(1)
    fy = (w * (qh[..., 0] * b + qh[..., 1] * e)).sum(1)
    fr = np.stack([fx, fy], 1)
    fr *= np.linalg.norm(r, axis=1, keepdims=True) / (np.linalg.norm(fr, axis=1, keepdims=True) + 1e-8)
    return fr + q_e


def adaptar(img: np.ndarray, alfa: np.ndarray, forma_ejemplo, fuerza: float,
            distancia_maxima: float = DISTANCIA_MAXIMA):
    """Deforma la foto y su recorte para que la prenda tome la silueta del ejemplo.

    Devuelve (img, alfa, info). Si no procede (varias piezas, silueta muy distinta), los
    devuelve sin tocar y lo explica en info["forma"]."""
    if fuerza <= 0 or forma_ejemplo is None or len(forma_ejemplo) == 0:
        return img, alfa, {}
    prenda = alfa > 0.5
    n, _ = cv2.connectedComponents(prenda.astype(np.uint8))
    if n > 2:
        return img, alfa, {"forma": "no aplicada: la prenda tiene varias piezas"}
    origen = silueta(prenda)
    if origen is None:
        return img, alfa, {}
    o_norm, centro, escala = normalizar(origen)
    ejemplo = np.asarray(forma_ejemplo, np.float64)
    ejemplo, distancia = emparejar(o_norm, ejemplo)
    if distancia > distancia_maxima:
        return img, alfa, {"forma": f"no aplicada: silueta muy distinta del ejemplo ({distancia:.2f})"}
    ejemplo *= np.sqrt(area(o_norm) / max(area(ejemplo), 1e-9))  # misma area: cambia la forma, no el tamano
    destino = origen + float(np.clip(fuerza, 0, 1)) * ((ejemplo * escala + centro) - origen)

    # Hacia atras: para cada pixel de salida, de que punto de la foto viene.
    h, w = prenda.shape
    paso = max(6, int(max(h, w) / 160))
    gy, gx = np.mgrid[0:h + paso:paso, 0:w + paso:paso].astype(np.float64)
    rejilla = np.stack([gx.ravel(), gy.ravel()], 1)
    fuente = _mls_rigido(destino, origen, rejilla)
    dx = (fuente[:, 0] - rejilla[:, 0]).reshape(gx.shape).astype(np.float32)
    dy = (fuente[:, 1] - rejilla[:, 1]).reshape(gx.shape).astype(np.float32)
    sigma = max(1.0, 0.015 * np.sqrt(prenda.sum()) / paso)  # sin dientes ni pliegues bruscos
    dx = cv2.GaussianBlur(dx, (0, 0), sigma)
    dy = cv2.GaussianBlur(dy, (0, 0), sigma)
    tam = (gx.shape[1] * paso, gx.shape[0] * paso)
    mapa_x = (cv2.resize(dx, tam, interpolation=cv2.INTER_CUBIC)[:h, :w] + np.arange(w, dtype=np.float32)[None])
    mapa_y = (cv2.resize(dy, tam, interpolation=cv2.INTER_CUBIC)[:h, :w] + np.arange(h, dtype=np.float32)[:, None])
    img_d = cv2.remap(img, mapa_x, mapa_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
    alfa_d = cv2.remap(alfa, mapa_x, mapa_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return (np.clip(img_d, 0, 1).astype(np.float32), np.clip(alfa_d, 0, 1).astype(np.float32),
            {"forma": f"adaptada al ejemplo (fuerza {fuerza:.2f}, parecido {1 - distancia:.2f})"})
