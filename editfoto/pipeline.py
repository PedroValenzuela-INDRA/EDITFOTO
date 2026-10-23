"""Cadena completa de edicion de una foto.

Se divide en dos fases para poder retocar rapido:
1. analizar(): la parte lenta (IA de recorte). Se hace una vez y se guarda.
2. renderizar(): todo lo demas. Tarda uno o dos segundos y se repite cada vez
   que cambias un ajuste o pintas con un pincel.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import arrugas, color, composicion, forma, inpaint, mascara, segmentar
from .config import AJUSTES_FOTO, fusionar
from .imagen import cargar, reducir


@dataclass
class Capas:
    """Pinceles del usuario, mapas en [0, 1] del tamano de la imagen de trabajo."""
    borrar: np.ndarray | None = None     # objetos a borrar con IA (LaMa)
    proteger: np.ndarray | None = None   # defectos que no se deben suavizar nunca
    sumar: np.ndarray | None = None      # zonas que SI son prenda
    restar: np.ndarray | None = None     # zonas que NO son prenda (percha, mano, pinza...)


def cargar_trabajo(ruta, preset: dict) -> np.ndarray:
    return reducir(cargar(ruta), int(preset["salida"]["max_lado_trabajo"]))


def analizar(img: np.ndarray, preset: dict) -> tuple[np.ndarray, dict | None]:
    """Recorte con IA y medida del fondo. Devuelve (alfa_bruto, medida_fondo)."""
    alfa = segmentar.segmentar(img, preset["segmentacion"]["modelo"])
    m = preset["mascara"]
    _, prenda = mascara.limpiar(alfa, m["min_componente"], m["max_hueco"], m["quitar_cables"])
    return alfa, color.medir_fondo(img, prenda)


def mascara_final(alfa_bruto: np.ndarray, preset: dict, capas: Capas) -> np.ndarray:
    m = preset["mascara"]
    alfa, prenda = mascara.limpiar(alfa_bruto, m["min_componente"], m["max_hueco"], m["quitar_cables"])
    if capas.borrar is not None and capas.borrar.max() > 0.3:
        # Si un cable cruzaba el borde de la prenda, el recorte tiene una muesca: se cierra.
        zona = capas.borrar > 0.3
        k = max(9, int(0.04 * np.sqrt(prenda.sum())) | 1)
        cerrada = cv2.morphologyEx(prenda.astype(np.uint8), cv2.MORPH_CLOSE,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(bool)
        alfa[zona & cerrada] = 1.0
    return mascara.aplicar_pinceles(alfa, capas.sumar, capas.restar)


def renderizar(img: np.ndarray, alfa_bruto: np.ndarray, preset: dict, ajustes: dict | None = None,
               capas: Capas | None = None, medida_fondo: dict | None = None,
               referencia_fondo: list[float] | None = None) -> tuple[np.ndarray, dict]:
    ajustes = fusionar(AJUSTES_FOTO, ajustes)
    capas = capas or Capas()
    info: dict = {}

    alfa = mascara_final(alfa_bruto, preset, capas)
    img = inpaint.borrar(img, capas.borrar)

    c = preset["color"]
    g = color.ganancias(medida_fondo, referencia_fondo, c["igualar_con_fondo"], c["balance_blancos"])
    info["ganancias_color"] = [round(float(v), 3) for v in g]
    img = color.aplicar(img, g, c["brillo"], c["contraste"], c["saturacion"])

    a = preset["arrugas"]
    img = arrugas.suavizar(img, alfa, a["fuerza"], a["escala"], a["respeto_bordes"], capas.proteger)

    # Despues de las arrugas: asi los pinceles (pintados sobre la foto sin deformar) siguen alineados.
    f = preset.get("forma") or {}
    if f.get("contorno") is not None and float(f.get("fuerza") or 0) > 0:
        img, alfa, info_forma = forma.adaptar(img, alfa, f["contorno"], float(f["fuerza"]))
        info.update(info_forma)

    fondo_original = preset["fondo"]["tipo"] == "original"
    frente = img if fondo_original else mascara.color_frente(img, alfa)

    angulo = float(ajustes["rotacion"])
    e = preset["enderezar"]
    if e["activo"] and ajustes["enderezar_auto"]:
        auto = composicion.angulo_enderezado(alfa > 0.5, float(e["max_grados"]))
        info["angulo_auto"] = auto
        angulo += auto

    enc = preset["encuadre"]
    lienzo = (int(preset["lienzo"]["ancho"]), int(preset["lienzo"]["alto"]))
    frente_l, alfa_l, info_enc = composicion.encuadrar(
        frente, alfa, lienzo, float(enc["relleno"]), float(enc["centro_x"]), float(enc["centro_y"]),
        angulo, float(ajustes["escala"]), float(ajustes["mover_x"]), float(ajustes["mover_y"]),
        borde_reflejo=fondo_original, relleno_x=enc.get("relleno_x"), relleno_y=enc.get("relleno_y"))
    info.update(info_enc)

    if fondo_original:
        resultado = frente_l
    else:
        resultado = composicion.componer(frente_l, alfa_l, preset["fondo"], preset["sombra"])
    resultado = composicion.enfocar(resultado, alfa_l, float(preset["nitidez"]))
    return resultado, info


def procesar(ruta, preset: dict, ajustes: dict | None = None, capas: Capas | None = None,
             referencia_fondo: list[float] | None = None) -> tuple[np.ndarray, dict]:
    """Atajo para una foto suelta, sin cache."""
    img = cargar_trabajo(ruta, preset)
    alfa, medida = analizar(img, preset)
    return renderizar(img, alfa, preset, ajustes, capas, medida, referencia_fondo)
