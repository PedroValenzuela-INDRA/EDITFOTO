"""Crear presets a partir de fotos ya editadas que te gustan.

No es un entrenamiento de IA: se mide en tus ejemplos lo que define el estilo
(proporcion de la foto, cuanto ocupa la prenda, donde queda, intensidad de la
sombra) y se reconstruye tu fondo real (ver fondos.py).

Organizacion recomendada (Documentos\\EDITFOTO\\fotos\\ejemplos):

    ejemplos/fondo.jpg          opcional: foto del fondo vacio, el fondo sale exacto
    ejemplos/sudadera/*.jpg     5 a 20 fotos que te gusten de sudaderas
    ejemplos/pantalon/*.jpg
    ejemplos/jersey/*.jpg

Cada subcarpeta crea o actualiza el preset con su nombre (si ya existia, conserva
el resto de sus ajustes, como la fuerza de las arrugas), y todas comparten el fondo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import config, fondos, imagen, mascara, segmentar

_CALIBRADO_SOMBRA = 6.5
LADO_EJEMPLOS = 1400


@dataclass
class Ejemplo:
    ruta: Path
    img: np.ndarray
    prenda: np.ndarray
    medida: dict


def medir_ejemplo(img: np.ndarray, modelo: str = "auto", ancho_original: int | None = None):
    """(medida, prenda) de una foto de ejemplo, o None si no se encuentra prenda."""
    alfa = segmentar.segmentar(img, modelo)
    _, prenda = mascara.limpiar(alfa)
    if prenda.sum() < 0.01 * prenda.size:
        return None
    # En una foto de ejemplo, la prenda que se vende es la pieza mas grande; lo demas
    # (otra prenda de decoracion, por ejemplo) forma parte del fondo.
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(prenda.astype(np.uint8), connectivity=8)
    if n > 2:
        prenda = etiquetas == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
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
    medida = {
        "aspecto": w / h,
        "ancho": ancho_original or w,
        "relleno": float(max((x1 - x0) / w, (y1 - y0) / h)),
        "ancho_rel": float((x1 - x0) / w),
        "alto_rel": float((y1 - y0) / h),
        "centro_x": float((x0 + x1) / 2 / w),
        "centro_y": float((y0 + y1) / 2 / h),
        "fondo": [float(c) for c in fondo],
        "fondo_uniforme": variacion < 0.03,
        "sombra": sombra,
    }
    return medida, prenda


def _fotos(carpeta: Path, recursivo: bool = True) -> list[Path]:
    patron = carpeta.rglob("*") if recursivo else carpeta.glob("*")
    return sorted(p for p in patron if p.is_file() and imagen.es_imagen(p))


def _cargar_ejemplos(rutas: list[Path], modelo: str, avisar) -> list[Ejemplo]:
    ejemplos = []
    for i, ruta in enumerate(rutas, 1):
        avisar(f"  [{i}/{len(rutas)}] {ruta.name}")
        try:
            original = imagen.cargar(ruta)
            img = imagen.reducir(original, LADO_EJEMPLOS)
            r = medir_ejemplo(img, modelo, original.shape[1])
        except Exception as e:  # noqa: BLE001
            avisar(f"    no se pudo leer: {e}")
            continue
        if r is None:
            avisar("    no se ha encontrado ninguna prenda, se descarta")
            continue
        medida, prenda = r
        medida["foto"] = ruta.name
        ejemplos.append(Ejemplo(ruta, img, prenda, medida))
    return ejemplos


def aprender_fondo(ejemplos: list[Ejemplo], carpeta: Path, nombre: str, avisar=print) -> tuple[dict, str, dict]:
    """Fondo comun de los ejemplos: (cambios del preset, frase para el resumen, info)."""
    color = imagen.a_hex(np.median(np.array([e.medida["fondo"] for e in ejemplos]), axis=0))
    vacios = [p for p in _fotos(carpeta) if fondos.es_foto_de_fondo(p)]
    if vacios:
        placa = imagen.reducir(imagen.cargar(vacios[0]), 2400)
        ruta = fondos.guardar(placa, nombre)
        return ({"tipo": "imagen", "imagen": ruta, "color": color},
                f"Fondo: tu foto del fondo vacio ({vacios[0].name})", {"origen": "foto_vacia"})
    if sum(e.medida["fondo_uniforme"] for e in ejemplos) >= len(ejemplos) / 2:
        return {"tipo": "color", "color": color}, f"Fondo liso {color}", {"origen": "color"}
    if len(ejemplos) >= 3:
        avisar("  Reconstruyendo tu fondo a partir de los ejemplos...")
        placa, info = fondos.reconstruir([e.img for e in ejemplos], [e.prenda for e in ejemplos])
        # Solo vale si las fotos son del mismo sitio (casi todas se alinean); si no, se mezclarian.
        if info["alineadas"] >= 0.6 * (info["fotos_usadas"] - 1):
            ruta = fondos.guardar(placa, nombre)
            frase = (f"Fondo reconstruido de {info['fotos_usadas']} fotos ({info['alineadas']} alineadas)"
                     + (f"; se ha rellenado un {info['hueco_rellenado'] * 100:.0f}% que ninguna foto dejaba ver"
                        if info["hueco_rellenado"] else ""))
            return {"tipo": "imagen", "imagen": ruta, "color": color}, frase, dict(info, origen="reconstruido")
        avisar("  Tus ejemplos no estan hechos desde el mismo sitio: se usa el fondo de uno de ellos.")
    # Una sola foto: la que mas fondo deja ver, borrando su prenda (las decoraciones se quedan).
    mejor = min(ejemplos, key=lambda e: e.prenda.mean())
    placa, info = fondos.placa_de_un_ejemplo(mejor.img, mejor.prenda)
    ruta = fondos.guardar(placa, nombre)
    frase = (f"Fondo sacado de {mejor.ruta.name}: se ha borrado su prenda ({info['hueco_rellenado'] * 100:.0f}% de"
             " la foto) y se conserva todo lo demas, decoracion incluida. Una foto del fondo vacio llamada"
             " fondo.jpg lo haria exacto")
    return {"tipo": "imagen", "imagen": ruta, "color": color}, frase, dict(info, origen="un_ejemplo")


def _preset_de(ejemplos: list[Ejemplo], nombre: str, base: str, descripcion: str, fondo: dict) -> tuple[dict, list[str]]:
    def med(clave):
        return float(np.median([e.medida[clave] for e in ejemplos]))

    aspecto = med("aspecto")
    ancho = int(np.clip(round(med("ancho") / 50) * 50, 1000, 2000))
    alto = int(round(ancho / aspecto))
    cambios = {
        "nombre": config.nombre_valido(nombre),
        "descripcion": descripcion,
        "lienzo": {"ancho": ancho, "alto": alto},
        "encuadre": {"relleno": round(float(np.clip(med("relleno"), 0.3, 0.97)), 3),
                     "relleno_x": round(float(np.clip(med("ancho_rel"), 0.2, 0.97)), 3),
                     "relleno_y": round(float(np.clip(med("alto_rel"), 0.2, 0.97)), 3),
                     "centro_x": round(med("centro_x"), 3), "centro_y": round(med("centro_y"), 3)},
        "fondo": fondo,
        # La sombra difuminada solo oscurece el borde en parte: el factor se ha calibrado
        # midiendo fotos generadas con una opacidad conocida.
        "sombra": {"opacidad": round(float(np.clip(med("sombra") * _CALIBRADO_SOMBRA, 0, 0.5)), 3)},
    }
    preset = config.fusionar(config.cargar_preset(base), cambios)
    config.guardar_preset(preset)
    texto = [
        f"{preset['nombre']}: foto final {ancho} x {alto} px, la prenda cabe en una caja del "
        f"{cambios['encuadre']['relleno_x'] * 100:.0f}% del ancho y el {cambios['encuadre']['relleno_y'] * 100:.0f}%"
        f" del alto centrada en x={cambios['encuadre']['centro_x']:.2f}, y={cambios['encuadre']['centro_y']:.2f},"
        f" sombra {cambios['sombra']['opacidad']:.2f} ({len(ejemplos)} ejemplos)",
    ]
    return preset, texto


def aprender(carpeta: str | Path, nombre: str, base: str = "generico", modelo: str = "auto",
             avisar=print) -> tuple[dict, dict]:
    """Un preset con todas las fotos de la carpeta (y sus subcarpetas)."""
    carpeta = Path(carpeta)
    rutas = [p for p in _fotos(carpeta) if not fondos.es_foto_de_fondo(p)]
    if not rutas:
        raise ValueError(f"No hay fotos de ejemplo en {carpeta}")
    ejemplos = _cargar_ejemplos(rutas, modelo, avisar)
    if not ejemplos:
        raise ValueError("No se ha podido medir ningun ejemplo")
    fondo, frase, info = aprender_fondo(ejemplos, carpeta, config.nombre_valido(nombre), avisar)
    preset, texto = _preset_de(ejemplos, nombre, base, f"Aprendido de {len(ejemplos)} ejemplos en {carpeta.name}",
                               fondo)
    return preset, {"ejemplos": len(ejemplos), "medidas": [e.medida for e in ejemplos], "fondo": info,
                    "presets": [preset["nombre"]], "texto": texto + [frase]}


def aprender_por_tipo(raiz: str | Path, modelo: str = "auto", avisar=print) -> tuple[list[dict], dict]:
    """Un preset por subcarpeta (sudadera, pantalon...) y un fondo comun hecho con todas las fotos."""
    raiz = Path(raiz)
    tipos = {}
    for sub in sorted(p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith(".")):
        rutas = [p for p in _fotos(sub) if not fondos.es_foto_de_fondo(p)]
        if rutas:
            avisar(f"{sub.name}:")
            ejemplos = _cargar_ejemplos(rutas, modelo, avisar)
            if ejemplos:
                tipos[config.nombre_valido(sub.name)] = ejemplos
    if not tipos:
        raise ValueError(f"No hay subcarpetas con fotos de ejemplo en {raiz} (p. ej. {raiz / 'sudadera'})")
    todos = [e for lista in tipos.values() for e in lista]
    fondo, frase, info = aprender_fondo(todos, raiz, "mi_fondo", avisar)
    presets, texto = [], []
    existentes = set(config.listar_presets())
    for nombre, ejemplos in tipos.items():
        base = nombre if nombre in existentes else "generico"
        preset, t = _preset_de(ejemplos, nombre, base, f"Aprendido de {len(ejemplos)} ejemplos tuyos", fondo)
        presets.append(preset)
        texto += t
    return presets, {"ejemplos": len(todos), "fondo": info, "presets": [p["nombre"] for p in presets],
                     "texto": texto + [frase]}
