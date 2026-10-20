"""Crear un preset a partir de fotos ya editadas que te gustan.

No es un entrenamiento de IA: se mide en tus ejemplos lo que define el estilo
(proporcion de la foto, cuanto ocupa la prenda, donde queda, color del fondo,
intensidad de la sombra) y se guarda como preset. Con 5 a 15 ejemplos basta.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config, imagen, mascara, segmentar

_CALIBRADO_SOMBRA = 6.5


def medir_ejemplo(img: np.ndarray, modelo: str = "auto", ancho_original: int | None = None) -> dict | None:
    alfa = segmentar.segmentar(img, modelo)
    _, prenda = mascara.limpiar(alfa)
    if prenda.sum() < 0.01 * prenda.size:
        return None
    h, w = prenda.shape
    ys, xs = np.nonzero(prenda)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    tam = np.sqrt(prenda.sum())

    def anillo(r_in, r_out):
        k_in = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_in + 1,) * 2)
        k_out = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_out + 1,) * 2)
        p = prenda.astype(np.uint8)
        return (cv2.dilate(p, k_out) > 0) & ~(cv2.dilate(p, k_in) > 0)

    lejos = ~(cv2.dilate(prenda.astype(np.uint8), cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (int(0.25 * tam) | 1,) * 2)) > 0)
    if lejos.sum() < 0.02 * prenda.size:  # prenda que llena casi toda la foto
        lejos = anillo(int(0.08 * tam), int(0.15 * tam))
    fondo = np.median(img[lejos], axis=0)
    variacion = float(np.median(np.abs(img[lejos] - fondo)))
    cerca = anillo(max(2, int(0.01 * tam)), max(4, int(0.05 * tam)))
    lum_cerca = float(np.median(imagen.luminancia(img[cerca][None])[0])) if cerca.any() else 0.0
    lum_lejos = float(imagen.luminancia(fondo[None, None])[0, 0])
    sombra = float(np.clip(1 - lum_cerca / max(lum_lejos, 1e-3), 0, 0.6))
    return {
        "aspecto": w / h,
        "ancho": ancho_original or w,
        "relleno": float(max((x1 - x0) / w, (y1 - y0) / h)),
        "centro_x": float((x0 + x1) / 2 / w),
        "centro_y": float((y0 + y1) / 2 / h),
        "fondo": [float(c) for c in fondo],
        "fondo_uniforme": variacion < 0.03,
        "sombra": sombra,
    }


def aprender(carpeta: str | Path, nombre: str, base: str = "generico", modelo: str = "auto",
             avisar=print) -> tuple[dict, dict]:
    carpeta = Path(carpeta)
    rutas = sorted(p for p in carpeta.rglob("*") if p.is_file() and imagen.es_imagen(p))
    if not rutas:
        raise ValueError(f"No hay fotos de ejemplo en {carpeta}")
    medidas = []
    for i, ruta in enumerate(rutas, 1):
        avisar(f"  [{i}/{len(rutas)}] {ruta.name}")
        try:
            original = imagen.cargar(ruta)
            m = medir_ejemplo(imagen.reducir(original, 1600), modelo, original.shape[1])
        except Exception as e:
            avisar(f"    no se pudo leer: {e}")
            continue
        if m:
            m["foto"] = ruta.name
            medidas.append(m)
    if not medidas:
        raise ValueError("No se ha podido medir ningun ejemplo")

    def med(clave):
        return float(np.median([m[clave] for m in medidas]))

    aspecto = med("aspecto")
    ancho = int(np.clip(round(med("ancho") / 50) * 50, 1000, 2000))
    alto = int(round(ancho / aspecto))
    fondo = np.median(np.array([m["fondo"] for m in medidas]), axis=0)
    uniforme = sum(m["fondo_uniforme"] for m in medidas) >= len(medidas) / 2
    sombra = med("sombra")

    preset_base = config.cargar_preset(base)
    cambios = {
        "nombre": config.nombre_valido(nombre),
        "descripcion": f"Aprendido de {len(medidas)} ejemplos en {carpeta.name} (base: {base})",
        "lienzo": {"ancho": ancho, "alto": alto},
        "encuadre": {"relleno": round(float(np.clip(med("relleno"), 0.5, 0.97)), 3),
                     "centro_x": round(med("centro_x"), 3), "centro_y": round(med("centro_y"), 3)},
        "fondo": {"tipo": "color", "color": imagen.a_hex(fondo)},
        # La sombra difuminada solo oscurece el borde en parte: el factor se ha calibrado
        # midiendo fotos generadas con una opacidad conocida.
        "sombra": {"opacidad": round(float(np.clip(sombra * _CALIBRADO_SOMBRA, 0, 0.5)), 3)},
    }
    preset = config.fusionar(preset_base, cambios)
    config.guardar_preset(preset)

    resumen = {
        "ejemplos": len(medidas),
        "medidas": medidas,
        "texto": [
            f"Foto final: {ancho} x {alto} px (proporcion {aspecto:.2f})",
            f"La prenda ocupa el {cambios['encuadre']['relleno'] * 100:.0f}% del lienzo,"
            f" centrada en x={cambios['encuadre']['centro_x']:.2f}, y={cambios['encuadre']['centro_y']:.2f}",
            f"Fondo {cambios['fondo']['color']}" + ("" if uniforme else
                " (tus ejemplos tienen fondo con textura: si quieres ese fondo exacto, guarda una foto del"
                " fondo vacio y usala como fondo tipo imagen)"),
            f"Sombra: opacidad {cambios['sombra']['opacidad']:.2f}",
        ],
    }
    return preset, resumen
