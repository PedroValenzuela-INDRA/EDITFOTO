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


def _luz(img: np.ndarray, valido: np.ndarray) -> np.ndarray:
    """Luz del suelo (variaciones suaves) a partir de los pixeles validos.

    Es una superficie de grado 2 ajustada al suelo visible, que extrapola bien debajo de un
    hueco que ocupa media foto, mas una correccion local cerca del suelo visible."""
    h, w = valido.shape
    e = 128 / max(h, w)
    peq = (max(8, round(w * e)), max(8, round(h * e)))
    img_p = cv2.resize(img, peq, interpolation=cv2.INTER_AREA)
    v_p = cv2.resize(valido.astype(np.float32), peq, interpolation=cv2.INTER_AREA) > 0.99
    if v_p.sum() < 12:
        v_p = cv2.resize(valido.astype(np.float32), peq, interpolation=cv2.INTER_AREA) > 0.5
    if v_p.sum() < 6:
        media = img[valido].mean(0) if valido.any() else img.reshape(-1, 3).mean(0)
        return np.broadcast_to(media.astype(np.float32), img.shape).copy()
    yy, xx = np.mgrid[0:peq[1], 0:peq[0]].astype(np.float32)
    xx, yy = xx / peq[0] - 0.5, yy / peq[1] - 0.5
    A = np.stack([np.ones_like(xx), xx, yy, xx * xx, xx * yy, yy * yy], -1)
    Av = A[v_p]
    # Un poco de freno en los terminos curvos: si solo se ve una franja de suelo, no se dispara.
    freno = np.diag([0, 0, 0, 1, 1, 1]).astype(np.float32) * 0.05 * len(Av)
    coef = np.linalg.solve(Av.T @ Av + freno, Av.T @ img_p[v_p])
    poli = A @ coef
    sigma = 0.06 * max(peq)
    peso = cv2.GaussianBlur(v_p.astype(np.float32), (0, 0), sigma)
    corr = cv2.GaussianBlur((img_p - poli) * v_p[..., None], (0, 0), sigma) / np.maximum(peso, 1e-4)[..., None]
    corr *= np.clip(peso / 0.3, 0, 1)[..., None]  # lejos del suelo visible, solo la superficie
    luz = poli + corr
    bajo, alto = np.percentile(img_p[v_p], 1, axis=0), np.percentile(img_p[v_p], 99, axis=0)
    luz = np.clip(luz, bajo - 0.03, alto + 0.03)
    return cv2.resize(luz.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)


def _igualar_histograma(x: np.ndarray, muestra: np.ndarray) -> np.ndarray:
    orden = np.argsort(x.ravel())
    salida = np.empty(x.size, np.float32)
    salida[orden] = np.interp(np.linspace(0, 1, x.size), np.linspace(0, 1, muestra.size), np.sort(muestra))
    return salida.reshape(x.shape)


def _grano(residuo: np.ndarray, region: np.ndarray, T: int, rng, piezas: int = 8) -> np.ndarray | None:
    """Grano nuevo con las mismas estadisticas que el del suelo (spot noise, Galerne et al. 2011).

    Se toman trozos de suelo de muestra y se convoluciona ruido aleatorio con ellos: sale
    una textura con la misma "trama" y el mismo color, sin costuras ni trozos repetidos.
    Va muy bien con moquetas, fieltros, telas y cemento."""
    h, w, _ = residuo.shape
    while True:  # el trozo de muestra mas grande que quepa entero en el suelo visible
        ok = cv2.erode(region.astype(np.uint8), np.ones((T, T), np.uint8), anchor=(0, 0)) > 0
        ok[h - T + 1:, :] = False
        ok[:, w - T + 1:] = False
        ys, xs = np.nonzero(ok)
        if len(ys) >= 20 or T <= 16:
            break
        T = max(16, int(T * 0.8) // 2 * 2)
    if len(ys) == 0:
        return None
    ventana = np.outer(np.hanning(T), np.hanning(T)).astype(np.float32)
    ventana /= np.sqrt((ventana ** 2).sum())
    H, W = h + T, w + T
    suma = np.zeros((H, W, 3), np.float32)
    for _ in range(piezas):
        j = rng.integers(len(ys))
        trozo = residuo[ys[j]:ys[j] + T, xs[j]:xs[j] + T]
        nucleo = (trozo - trozo.mean((0, 1))) * ventana[..., None]
        ruido = np.fft.rfft2(rng.standard_normal((H, W)).astype(np.float32))  # mismo ruido en los 3 canales
        for c in range(3):
            k = np.zeros((H, W), np.float32)
            k[:T, :T] = nucleo[..., c]
            suma[..., c] += np.fft.irfft2(ruido * np.fft.rfft2(k), s=(H, W))
    grano = suma[T:T + h, T:T + w] / np.sqrt(piezas)  # sin el borde circular
    muestra = residuo[region]
    if len(muestra) > 300000:
        muestra = muestra[rng.integers(len(muestra), size=300000)]
    for c in range(3):  # mismo reparto de claros y oscuros que el suelo real
        grano[..., c] = _igualar_histograma(grano[..., c], muestra[:, c])
    return grano


def rellenar_textura(img: np.ndarray, hueco: np.ndarray, semilla: int = 0,
                     decoracion: np.ndarray | None = None) -> np.ndarray:
    """Rellena un hueco grande de un fondo con textura (moqueta, fieltro, tela, madera...).

    LaMa va muy bien para huecos pequenos, pero en uno que ocupa media foto deja manchas.
    Aqui se separan dos capas: la luz (variaciones suaves), que se ajusta al suelo visible,
    y el grano, que se sintetiza con las estadisticas del propio suelo. Solo se mira el suelo
    de verdad, asi una decoracion (otra prenda) o una sombra no se repiten por el hueco."""
    h, w = hueco.shape
    rng = np.random.default_rng(semilla)
    suelo = _suelo_liso(img, ~hueco)
    if decoracion is not None:
        suelo &= ~decoracion
    if suelo.sum() < 0.02 * h * w:
        suelo = ~hueco
    luz = _luz(img, suelo)
    T = int(np.clip(0.12 * min(h, w), 32, 192)) // 2 * 2
    region = (cv2.GaussianBlur(suelo.astype(np.float32), (0, 0), 3) > 0.6) & ~hueco
    # Solo el grano, sin restos de luz. El desenfoque mira solo el suelo: si mezclara la prenda
    # o la decoracion, el grano de alrededor saldria aclarado u oscurecido.
    residuo = img - luz
    m = region.astype(np.float32)
    suave = cv2.GaussianBlur(residuo * m[..., None], (0, 0), T / 2) / \
        np.maximum(cv2.GaussianBlur(m, (0, 0), T / 2), 1e-4)[..., None]
    residuo = residuo - suave
    grano = _grano(residuo, region, T, rng) if region.any() else None
    relleno = np.clip(luz + (grano if grano is not None else 0), 0, 1)
    borde = cv2.GaussianBlur(hueco.astype(np.float32), (0, 0), max(2.0, T / 16))[..., None]
    borde = np.maximum(borde, hueco[..., None].astype(np.float32))
    return (img * (1 - borde) + relleno * borde).astype(np.float32)


def _hueco_de_un_ejemplo(img: np.ndarray, prenda: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lo que hay que borrar de un ejemplo: la prenda, su sombra y los restos de su borde,
    sin tocar la decoracion (p. ej. el pantalon de abajo). Devuelve (hueco, decoracion)."""
    h, w = prenda.shape
    tam = float(np.sqrt(max(prenda.sum(), 1)))
    elipse = lambda k: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))  # noqa: E731
    zona = cv2.dilate(prenda.astype(np.uint8), elipse(max(5, int(0.07 * tam)) | 1)) > 0
    decoracion = np.zeros_like(prenda)
    fuera = ~zona
    if fuera.sum() < 0.02 * h * w:
        return zona, decoracion
    lab = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2Lab)
    tipico = np.median(lab[fuera], axis=0)
    croma = np.linalg.norm(lab[..., 1:] - tipico[1:], axis=2)
    parece_suelo = (croma < max(4.0, 3 * float(np.median(croma[fuera])))) & \
                   (lab[..., 0] < float(np.percentile(lab[..., 0][fuera], 95)) + 5)
    # Lo que no parece suelo y sale bastante fuera de la zona es decoracion: se respeta.
    # Lo que no parece suelo pero queda dentro son restos de la prenda: se borran.
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats((~parece_suelo).astype(np.uint8), connectivity=8)
    dentro = np.bincount(etiquetas[zona], minlength=n)
    de_decoracion = np.nonzero(dentro < 0.6 * stats[:, cv2.CC_STAT_AREA])[0]
    decoracion = np.isin(etiquetas, de_decoracion[de_decoracion > 0]) & ~prenda
    hueco = (zona & ~decoracion) | prenda

    # La sombra de la prenda llega mas lejos que la zona: suelo mas oscuro de lo que
    # tocaria por la luz, pegado al hueco. Si se dejara, se veria el contorno de la prenda vieja.
    zona2 = cv2.dilate(prenda.astype(np.uint8), elipse(max(7, int(0.2 * tam)) | 1)) > 0
    suelo0 = _suelo_liso(img, ~zona2) & ~decoracion
    if suelo0.sum() > 0.01 * h * w:
        luz = cv2.cvtColor(_luz(img, suelo0), cv2.COLOR_RGB2Lab)[..., 0]
        diferencia = cv2.GaussianBlur(lab[..., 0], (0, 0), 2.0) - luz
        ruido = float(np.std(diferencia[suelo0]))
        sombra = zona2 & parece_suelo & ~decoracion & (diferencia < -max(2.0, 1.5 * ruido))
        _, et = cv2.connectedComponents((sombra | hueco).astype(np.uint8))
        pegadas = np.unique(et[hueco])
        hueco |= np.isin(et, pegadas[pegadas > 0]) & sombra
        hueco = cv2.morphologyEx(hueco.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)) > 0
        hueco = (hueco & ~decoracion) | prenda
    return hueco, decoracion


def placa_de_un_ejemplo(img: np.ndarray, prenda: np.ndarray) -> tuple[np.ndarray, dict]:
    """Fondo a partir de una sola foto: se borra la prenda principal (con su sombra) y se rellena.

    Lo demas se queda tal cual, incluidas las decoraciones (otra prenda de atrezo, una
    planta...), asi la foto nueva sale con la misma composicion."""
    hueco, decoracion = _hueco_de_un_ejemplo(img, prenda)
    placa, relleno = rellenar_hueco(img, hueco, decoracion)
    return np.clip(placa, 0, 1).astype(np.float32), {"fotos_usadas": 1, "alineadas": 0,
                                                       "hueco_rellenado": round(float(hueco.mean()), 4),
                                                       "relleno": relleno}


def rellenar_hueco(img: np.ndarray, hueco: np.ndarray, decoracion: np.ndarray | None = None) -> tuple[np.ndarray, str]:
    """Huecos pequenos con LaMa (si esta); los grandes, con relleno de textura."""
    if hueco.mean() < 0.03 and modelos._ruta_destino("lama").exists():
        return inpaint.borrar(img, hueco.astype(np.float32)), "LaMa"
    return rellenar_textura(img, hueco, decoracion=decoracion), "textura"


def guardar(placa: np.ndarray, nombre: str) -> str:
    """Guarda la placa en DATOS/fondos y devuelve la ruta relativa que va en el preset."""
    relativa = f"fondos/{nombre}.jpg"
    imagen.guardar_jpg(placa, modelos.DATOS / relativa, 95)
    return relativa


def ruta_absoluta(ruta: str) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else modelos.DATOS / p
