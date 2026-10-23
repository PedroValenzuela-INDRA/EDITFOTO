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


def _centros_lab(lab: np.ndarray, zona: np.ndarray, k: int, rng) -> np.ndarray | None:
    muestras = lab[zona]
    if len(muestras) < 4 * k:
        return None
    if len(muestras) > 20000:
        muestras = muestras[rng.choice(len(muestras), 20000, replace=False)]
    criterio = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, _, centros = cv2.kmeans(muestras.astype(np.float32), k, None, criterio, 2, cv2.KMEANS_PP_CENTERS)
    return centros


def _distancia(lab: np.ndarray, centros: np.ndarray) -> np.ndarray:
    return np.min(np.linalg.norm(lab[..., None, :] - centros[None, None], axis=-1), axis=-1)


def pulir_bordes(img: np.ndarray, alfa: np.ndarray, respetar: np.ndarray | None = None,
                 semilla: int = 0) -> tuple[np.ndarray, np.ndarray, dict]:
    """Quita del borde de la prenda lo que es del suelo (pelos de una alfombra, hebras) y tapa
    el mordisco que deja con el color de la prenda de al lado.

    Solo mira una franja estrecha por dentro del borde, y solo quita lo que se parece mucho
    al suelo de alrededor, poco a la prenda, y esta unido al suelo de fuera: un logo o un
    detalle del color del suelo en medio de la prenda no se toca. Devuelve (img, alfa, info)."""
    prenda = alfa > 0.5
    area = int(prenda.sum())
    if area < 2000:
        return img, alfa, {}
    tam = float(np.sqrt(area))
    rng = np.random.default_rng(semilla)
    elipse = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))  # noqa: E731
    r_banda = max(3, int(0.025 * tam))
    p8 = prenda.astype(np.uint8)
    banda = prenda & ~(cv2.erode(p8, elipse(r_banda)) > 0)
    fuera = alfa < 0.1
    anillo_fondo = fuera & (cv2.dilate(p8, elipse(max(10, int(0.05 * tam)))) > 0) & ~(cv2.dilate(p8, elipse(max(3, int(0.008 * tam)))) > 0)
    anillo_prenda = (cv2.erode(p8, elipse(r_banda)) > 0) & ~(cv2.erode(p8, elipse(4 * r_banda)) > 0)
    lab = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2Lab)
    c_fondo = _centros_lab(lab, anillo_fondo, 5, rng)
    c_prenda = _centros_lab(lab, anillo_prenda, 5, rng)
    if c_fondo is None or c_prenda is None:
        return img, alfa, {}
    ys, xs = np.nonzero(banda)
    d_fondo = _distancia(lab[ys, xs][None], c_fondo)[0]
    # La prenda se compara con su color de al lado (un puno claro no es como el cuerpo oscuro).
    interior = (cv2.erode(p8, elipse(r_banda)) > 0).astype(np.float32)
    s_local = 1.5 * r_banda
    peso = cv2.GaussianBlur(interior, (0, 0), s_local)
    lab_local = cv2.GaussianBlur(lab * interior[..., None], (0, 0), s_local) / np.maximum(peso, 1e-4)[..., None]
    d_local = np.linalg.norm(lab[ys, xs] - lab_local[ys, xs], axis=1)
    d_global = _distancia(lab[ys, xs][None], c_prenda)[0]
    d_prenda = np.where(peso[ys, xs] > 0.02, d_local, d_global)
    intrusa = np.zeros_like(prenda)
    claramente_suelo = (d_fondo < 0.5 * d_prenda) & (d_fondo < 20.0)
    # Hebras finas y semitransparentes: su color es una mezcla entre el de la prenda de al
    # lado y el del suelo (un pelo blanco sobre canale marron sale gris).
    pix = lab[ys, xs]
    g = np.where(peso[ys, xs, None] > 0.02, lab_local[ys, xs], pix)
    cercano = np.argmin(np.linalg.norm(pix[:, None] - c_fondo[None], axis=2), axis=1)
    d = c_fondo[cercano] - g
    largo2 = np.maximum((d * d).sum(1), 1e-6)
    t = ((pix - g) * d).sum(1) / largo2
    perp = np.linalg.norm((pix - g) - t[:, None] * d, axis=1)
    mezcla = (np.sqrt(largo2) > 15) & (t > 0.35) & (perp < np.maximum(5.0, 0.15 * np.sqrt(largo2)))
    # El pixel justo del borde siempre es mezcla (el recorte es suave): ese lo arregla
    # color_frente; aqui solo cuentan las mezclas un poco mas adentro.
    hondo = cv2.distanceTransform(p8, cv2.DIST_L2, 3)[ys, xs] >= 2.5
    intrusa[ys, xs] = claramente_suelo | (mezcla & hondo)
    if respetar is not None:  # lo que has pintado como prenda o como defecto no se toca
        intrusa &= ~(respetar > 0.3)
    # Solo lo que esta unido al suelo de fuera (una hebra que entra desde el borde).
    # (Con 1 px de tolerancia: un pelo fino tiene tramos mas oscuros que cortan la cadena.)
    puente = (cv2.dilate(intrusa.astype(np.uint8), elipse(1)) > 0) & prenda
    _, et = cv2.connectedComponents((puente | ~prenda).astype(np.uint8), connectivity=8)
    exterior = np.unique(et[~prenda])
    intrusa &= np.isin(et, exterior[exterior > 0])
    # Y solo trozos pequenos y deshilachados (hebras, mechones, pelusa). Una pieza grande del
    # color del suelo (un puno blanco sobre suelo blanco) o maciza (el tope metalico de la
    # cremallera) es prenda y no se toca.
    n, et, stats, _ = cv2.connectedComponentsWithStats(intrusa.astype(np.uint8), connectivity=8)
    area_c = stats[:, cv2.CC_STAT_AREA].astype(np.float64)
    r_o = max(2, int(0.004 * tam))
    abierta = cv2.morphologyEx(intrusa.astype(np.uint8), cv2.MORPH_OPEN, elipse(r_o)) > 0
    maciza = np.bincount(et[abierta], minlength=n) / np.maximum(area_c, 1)
    # Un mechon de pelos tiene mucho contraste por dentro (hebras claras y huecos oscuros);
    # una pieza de metal o de tela es mas lisa.
    L = lab[..., 0][intrusa]
    e = et[intrusa]
    media = np.bincount(e, L, minlength=n) / np.maximum(area_c, 1)
    desv = np.sqrt(np.maximum(np.bincount(e, L * L, minlength=n) / np.maximum(area_c, 1) - media ** 2, 0))
    lisa = (maciza > 0.5) & (desv < 8.0)
    descartar = (area_c > (0.04 * tam) ** 2) | (lisa & (area_c > (4 * r_o) ** 2))
    descartar[0] = False
    intrusa &= ~descartar[et]
    if intrusa.sum() < 20:
        return img, alfa, {}

    sin = prenda & ~intrusa
    # Cerrar solo alrededor de lo quitado: asi se tapan los mordiscos de las hebras sin
    # rellenar huecos de verdad (la axila, el espacio entre manga y cuerpo).
    k = max(2, int(0.02 * tam))
    cerrada = cv2.morphologyEx(sin.astype(np.uint8), cv2.MORPH_CLOSE, elipse(k)) > 0
    # El cierre deja sin tapar la ultima fila del mordisco en un borde recto: 2 px de margen.
    cerrada |= (cv2.dilate(cerrada.astype(np.uint8), elipse(2)) > 0) & intrusa
    cerca = cv2.dilate(intrusa.astype(np.uint8), elipse(k)) > 0
    tapar = cerrada & ~sin & cerca
    nueva_prenda = sin | tapar

    # Color de lo tapado: el de la prenda de al lado, propagado, con su textura (el canale,
    # la trama) copiada en espejo desde justo dentro, para que no quede una mancha lisa.
    s = max(2.0, k / 2)
    m = sin.astype(np.float32)
    num = cv2.GaussianBlur(img * m[..., None], (0, 0), s)
    den = cv2.GaussianBlur(m, (0, 0), s)[..., None]
    propagado = num / np.maximum(den, 1e-4)
    fuente = (cv2.erode(sin.astype(np.uint8), elipse(1)) > 0) & ~(cv2.dilate(intrusa.astype(np.uint8), elipse(2)) > 0)
    ty, tx = np.nonzero(tapar)
    if len(ty) and fuente.any():
        _, cercano = cv2.distanceTransformWithLabels((~fuente).astype(np.uint8), cv2.DIST_L2, 5,
                                                    labelType=cv2.DIST_LABEL_PIXEL)
        fy, fx = np.nonzero(fuente)
        coords = np.zeros((cercano.max() + 1, 2), np.int64)
        coords[cercano[fy, fx]] = np.stack([fy, fx], 1)
        cy, cx = coords[cercano[ty, tx]].T
        my = np.clip(2 * cy - ty, 0, img.shape[0] - 1)  # el punto simetrico, ya dentro de la prenda
        mx = np.clip(2 * cx - tx, 0, img.shape[1] - 1)
        detalle = img - cv2.GaussianBlur(img, (0, 0), 2.0)
        img = img.copy()
        img[ty, tx] = propagado[ty, tx] + np.where(sin[my, mx, None], detalle[my, mx], 0)
    img = np.clip(img, 0, 1).astype(np.float32)
    alfa = alfa.copy()
    quitar = intrusa & ~nueva_prenda
    alfa[quitar] = 0.0
    alfa[tapar] = 1.0
    # Borde de lo tocado algo suave, como el del recorte.
    tocado = cv2.dilate((quitar | tapar).astype(np.uint8), elipse(2)) > 0
    suave = cv2.GaussianBlur(nueva_prenda.astype(np.float32), (0, 0), 1.0)
    alfa = np.where(tocado & ~nueva_prenda, np.minimum(alfa, suave), alfa)
    alfa = np.where(tocado & nueva_prenda, np.maximum(alfa, suave), alfa).astype(np.float32)
    return img, alfa, {"bordes": f"{int(intrusa.sum())} px de suelo quitados del borde, {int(tapar.sum())} tapados"}
