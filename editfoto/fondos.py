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
        if modelos._ruta_destino("lama").exists():
            placa = inpaint.borrar(placa, huecos.astype(np.float32))
            relleno = "LaMa"
        else:
            placa = cv2.inpaint(imagen.a_uint8(placa), huecos.astype(np.uint8), 7, cv2.INPAINT_TELEA)
            placa = placa.astype(np.float32) / 255.0
            relleno = "OpenCV"
    info = {"fotos_usadas": len(imgs), "descartadas_por_proporcion": len(imagenes) - len(imgs),
            "alineadas": alineadas, "hueco_rellenado": round(float(huecos.mean()), 4), "relleno": relleno}
    return np.clip(placa, 0, 1).astype(np.float32), info


def guardar(placa: np.ndarray, nombre: str) -> str:
    """Guarda la placa en DATOS/fondos y devuelve la ruta relativa que va en el preset."""
    relativa = f"fondos/{nombre}.jpg"
    imagen.guardar_jpg(placa, modelos.DATOS / relativa, 95)
    return relativa


def ruta_absoluta(ruta: str) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else modelos.DATOS / p
