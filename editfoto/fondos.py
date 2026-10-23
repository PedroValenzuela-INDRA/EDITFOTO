"""Reconstruir tu fondo real (suelo, tela, madera...) a partir de tus fotos de ejemplo.

En cada foto la prenda tapa una parte distinta del fondo. Si se alinean las fotos
(por si la camara se movio un poco), se igualan de exposicion y se toma la mediana
de cada pixel solo entre las fotos donde ese pixel es fondo, sale el fondo limpio,
sin prendas. Lo poco que ninguna foto deja ver (normalmente el centro) se rellena
con LaMa, y de todas formas queda tapado por la prenda nueva.

Si entre los ejemplos hay una foto del fondo vacio (un fichero que empiece por
"fondo"), se usa esa directamente: es lo mas exacto.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import cv2
import numpy as np

from . import imagen, inpaint, modelos

LADO_MAX = 1400  # resolucion de trabajo de la placa de fondo


def es_foto_de_fondo(ruta: Path) -> bool:
    return ruta.stem.lower().startswith("fondo")


def _zona_fondo(prenda: np.ndarray) -> np.ndarray:
    """Pixeles que son fondo con seguridad: lejos de la prenda y de su sombra."""
    tam = float(np.sqrt(max(prenda.sum(), 1)))
    k = max(5, int(0.05 * tam)) | 1
    return ~(cv2.dilate(prenda.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0)


def _gris_sin_prenda(img: np.ndarray, zona_fondo: np.ndarray, tam: tuple[int, int]):
    """Luminancia reducida con la prenda rellenada de fondo plausible, para que sus bordes
    no dominen la alineacion. Devuelve (gris, mascara_fondo)."""
    g = cv2.resize(imagen.luminancia(img), tam, interpolation=cv2.INTER_AREA)
    z = cv2.resize(zona_fondo.astype(np.uint8), tam, interpolation=cv2.INTER_NEAREST) > 0
    g8 = cv2.inpaint(imagen.a_uint8(g), (~z).astype(np.uint8), 5, cv2.INPAINT_TELEA)
    return cv2.GaussianBlur(g8.astype(np.float32) / 255.0, (0, 0), 1.0), z


def _ecc(g_ref, z_ref, g_img, z_img, M, tipo):
    criterio = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
    if hasattr(cv2, "findTransformECCWithMask"):  # OpenCV 5: ignora la prenda en las dos fotos
        return cv2.findTransformECCWithMask(g_ref, g_img, z_ref.astype(np.uint8), z_img.astype(np.uint8),
                                            M, tipo, criterio, 3)[1]
    return cv2.findTransformECC(g_ref, g_img, M, tipo, criterio, z_img.astype(np.uint8), 3)[1]


def _sensata(M: np.ndarray, h: int, w: int) -> bool:
    """Una camara movida a mano: poco giro, casi sin cambio de escala ni deformacion."""
    A = M[:, :2]
    escala = np.sqrt(abs(np.linalg.det(A)))
    deformacion = abs(A[0, 0] - A[1, 1]) + abs(A[0, 1] + A[1, 0])
    return 0.9 < escala < 1.1 and deformacion < 0.08 and np.abs(M[:, 2]).max() < 0.1 * max(h, w)


def _alinear(ref: np.ndarray, ref_fondo: np.ndarray, img: np.ndarray, fondo: np.ndarray):
    """Alinea img con ref usando solo el fondo (ECC de grueso a fino). Devuelve (img, fondo, ok).

    Primero a muy baja resolucion, donde un dibujo repetitivo (vetas de madera, cuadros de
    una tela) no engana, y despues se afina con mas detalle. Si un nivel fino da un resultado
    absurdo, se queda el del nivel anterior."""
    h, w = ref.shape[:2]
    niveles = [lado for lado in (160, 320, 640) if lado < max(h, w)] or [max(h, w)]
    M = np.eye(2, 3, dtype=np.float32)
    for nivel, lado in enumerate(niveles):
        e = lado / max(h, w)
        tam = (max(1, round(w * e)), max(1, round(h * e)))
        g_ref, z_ref = _gris_sin_prenda(ref, ref_fondo, tam)
        g_img, z_img = _gris_sin_prenda(img, fondo, tam)
        Me = M.copy()
        Me[:, 2] *= e
        tipo = cv2.MOTION_TRANSLATION if nivel == 0 else cv2.MOTION_AFFINE
        try:
            Me = _ecc(g_ref, z_ref, g_img, z_img, Me, tipo)
        except cv2.error:
            if nivel == 0:
                return img, fondo, False
            break
        candidata = Me.copy()
        candidata[:, 2] /= e
        if not _sensata(candidata, h, w):
            if nivel == 0:
                return img, fondo, False
            break
        M = candidata
    img_a = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                           borderMode=cv2.BORDER_REFLECT_101)
    fondo_a = cv2.warpAffine(fondo.astype(np.uint8), M, (w, h), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                             borderValue=0) > 0
    return img_a, fondo_a, True


def reconstruir(imagenes: list[np.ndarray], prendas: list[np.ndarray], alinear: bool = True) -> tuple[np.ndarray, dict]:
    """Placa de fondo limpia a partir de fotos del mismo set. Devuelve (placa, info)."""
    if not imagenes:
        raise ValueError("No hay fotos para reconstruir el fondo")
    aspectos = np.array([i.shape[1] / i.shape[0] for i in imagenes])
    objetivo = float(np.median(aspectos))
    elegidas = [k for k, a in enumerate(aspectos) if abs(a / objetivo - 1) < 0.02]
    h0, w0 = imagenes[elegidas[0]].shape[:2]
    e = min(1.0, LADO_MAX / max(h0, w0))
    w, h = round(w0 * e), round(h0 * e)

    imgs, fondos = [], []
    for k in elegidas:
        img = cv2.resize(imagenes[k], (w, h), interpolation=cv2.INTER_AREA)
        prenda = cv2.resize(prendas[k].astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        imgs.append(img)
        fondos.append(_zona_fondo(prenda))

    # Referencia: la foto que mas fondo deja ver.
    r = int(np.argmax([f.mean() for f in fondos]))
    alineadas = 0
    if alinear:
        for k in range(len(imgs)):
            if k != r:
                imgs[k], fondos[k], ok = _alinear(imgs[r], fondos[r], imgs[k], fondos[k])
                alineadas += ok

    # Igualar exposicion de cada foto con la referencia en el fondo que comparten.
    for k in range(len(imgs)):
        comun = fondos[k] & fondos[r]
        if k != r and comun.sum() > 500:
            g = np.median(imgs[r][comun], axis=0) / np.maximum(np.median(imgs[k][comun], axis=0), 1e-3)
            imgs[k] = np.clip(imgs[k] * np.clip(g, 0.7, 1.4), 0, 1)

    # Mediana por pixel solo donde es fondo (por franjas para no gastar mucha memoria).
    placa = np.zeros((h, w, 3), np.float32)
    vistas = np.zeros((h, w), np.int32)
    paso = 128
    for y in range(0, h, paso):
        pila = np.stack([np.where(f[y:y + paso, :, None], i[y:y + paso], np.nan) for i, f in zip(imgs, fondos)])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            placa[y:y + paso] = np.nan_to_num(np.nanmedian(pila, axis=0))
        vistas[y:y + paso] = np.sum([f[y:y + paso] for f in fondos], axis=0)

    huecos = vistas == 0
    relleno = "ninguno"
    if huecos.any():
        placa, relleno = rellenar_hueco(placa, huecos)
    info = {"fotos_usadas": len(imgs), "descartadas_por_proporcion": len(imagenes) - len(imgs),
            "alineadas": alineadas, "hueco_rellenado": round(float(huecos.mean()), 4), "relleno": relleno}
    return np.clip(placa, 0, 1).astype(np.float32), info


def _suelo_liso(img: np.ndarray, valido: np.ndarray) -> np.ndarray:
    """Pixeles que son el suelo del set (color tipico del fondo): fuera quedan sombras fuertes y
    decoraciones, que no deben copiarse al rellenar."""
    lab = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2Lab)
    tipico = np.median(lab[valido], axis=0)
    distancia = np.sqrt((((lab - tipico) * np.array([0.6, 1.0, 1.0], np.float32)) ** 2).sum(axis=2))
    umbral = max(10.0, float(np.percentile(distancia[valido], 80)) * 1.3)
    return valido & (distancia < umbral)


def rellenar_textura(img: np.ndarray, hueco: np.ndarray, semilla: int = 0) -> np.ndarray:
    """Rellena un hueco grande de un fondo con textura (moqueta, fieltro, tela, madera...).

    LaMa va muy bien para huecos pequenos, pero en uno que ocupa media foto deja manchas.
    Aqui se separan dos capas: la luz (variaciones suaves), que se interpola desde el fondo
    visible, y la textura, que se rellena con trozos copiados del propio suelo y mezclados
    con bordes suaves. Solo se copia de zonas que son suelo de verdad, asi una decoracion
    (otra prenda) o una sombra no se repiten por el hueco."""
    h, w = hueco.shape
    rng = np.random.default_rng(semilla)
    suelo = _suelo_liso(img, ~hueco)
    if suelo.sum() < 0.02 * h * w:
        suelo = ~hueco

    # 1. Luz: interpolacion suave del suelo visible, hecha a baja resolucion.
    e = 128 / max(h, w)
    peq = (max(4, round(w * e)), max(4, round(h * e)))
    img_p = cv2.resize(img, peq, interpolation=cv2.INTER_AREA)
    suelo_p = cv2.resize(suelo.astype(np.float32), peq, interpolation=cv2.INTER_AREA)
    sigma = 0.06 * max(peq)
    peso = cv2.GaussianBlur(suelo_p, (0, 0), sigma)
    luz_p = cv2.GaussianBlur(img_p * suelo_p[..., None], (0, 0), sigma) / np.maximum(peso, 1e-4)[..., None]
    for _ in range(6):  # donde el hueco es muy ancho, se extiende con un desenfoque mas amplio
        lejos = peso < 0.05
        if not lejos.any():
            break
        sigma *= 2
        peso2 = cv2.GaussianBlur(suelo_p, (0, 0), sigma)
        luz2 = cv2.GaussianBlur(img_p * suelo_p[..., None], (0, 0), sigma) / np.maximum(peso2, 1e-6)[..., None]
        luz_p[lejos] = luz2[lejos]
        peso = np.maximum(peso, peso2)
    luz = cv2.resize(luz_p, (w, h), interpolation=cv2.INTER_CUBIC)

    # 2. Textura: residuo (foto - luz) copiado a trozos desde el suelo liso.
    residuo = img - luz
    P = int(np.clip(0.08 * min(h, w), 24, 160)) // 2 * 2
    paso = P // 2
    origen = cv2.erode(suelo.astype(np.uint8), np.ones((P, P), np.uint8), anchor=(0, 0)) > 0  # esquina sup-izq
    origen[h - P:, :] = False
    origen[:, w - P:] = False
    ys, xs = np.nonzero(origen)
    if len(ys) == 0:
        return img
    ventana = np.outer(np.hanning(P + 2)[1:-1], np.hanning(P + 2)[1:-1]).astype(np.float32) + 1e-3
    acumulado = np.zeros_like(img)
    pesos = np.zeros((h, w), np.float32)
    hy, hx = np.nonzero(cv2.dilate(hueco.astype(np.uint8), np.ones((P, P), np.uint8)))
    for y in range(max(0, hy.min() - paso), min(h - 1, hy.max()) + 1, paso):
        for x in range(max(0, hx.min() - paso), min(w - 1, hx.max()) + 1, paso):
            k = rng.integers(len(ys))
            sy, sx = ys[k], xs[k]
            alto, ancho = min(P, h - y), min(P, w - x)
            v = ventana[:alto, :ancho]
            acumulado[y:y + alto, x:x + ancho] += residuo[sy:sy + alto, sx:sx + ancho] * v[..., None]
            pesos[y:y + alto, x:x + ancho] += v
    textura = acumulado / np.maximum(pesos, 1e-6)[..., None]
    # Mezclar trozos con pesos suaves reduce el contraste: se devuelve al del suelo original.
    std_suelo = residuo[suelo].std(axis=0)
    zona = pesos > 1e-3
    std_relleno = textura[zona].std(axis=0) if zona.any() else std_suelo
    textura *= np.clip(std_suelo / np.maximum(std_relleno, 1e-4), 1.0, 2.0)

    relleno = np.clip(luz + textura, 0, 1)
    borde = cv2.GaussianBlur(hueco.astype(np.float32), (0, 0), max(2.0, P / 8))[..., None]
    borde = np.maximum(borde, hueco[..., None].astype(np.float32))
    return (img * (1 - borde) + relleno * borde).astype(np.float32)


def placa_de_un_ejemplo(img: np.ndarray, prenda: np.ndarray) -> tuple[np.ndarray, dict]:
    """Fondo a partir de una sola foto: se borra la prenda principal y se rellena con LaMa.

    Lo demas se queda tal cual, incluidas las decoraciones (otra prenda de atrezo, una
    planta...), asi la foto nueva sale con la misma composicion."""
    tam = float(np.sqrt(max(prenda.sum(), 1)))
    k = max(5, int(0.07 * tam)) | 1  # la prenda y su sombra
    hueco = cv2.dilate(prenda.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    placa, relleno = rellenar_hueco(img, hueco)
    return np.clip(placa, 0, 1).astype(np.float32), {"fotos_usadas": 1, "alineadas": 0,
                                                       "hueco_rellenado": round(float(hueco.mean()), 4),
                                                       "relleno": relleno}


def rellenar_hueco(img: np.ndarray, hueco: np.ndarray) -> tuple[np.ndarray, str]:
    """Huecos pequenos con LaMa (si esta); los grandes, con relleno de textura."""
    if hueco.mean() < 0.03 and modelos._ruta_destino("lama").exists():
        return inpaint.borrar(img, hueco.astype(np.float32)), "LaMa"
    return rellenar_textura(img, hueco), "textura"


def guardar(placa: np.ndarray, nombre: str) -> str:
    """Guarda la placa en DATOS/fondos y devuelve la ruta relativa que va en el preset."""
    relativa = f"fondos/{nombre}.jpg"
    imagen.guardar_jpg(placa, modelos.DATOS / relativa, 95)
    return relativa


def ruta_absoluta(ruta: str) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else modelos.DATOS / p
