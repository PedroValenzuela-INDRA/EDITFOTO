"""Que la app aprenda de ti: un banco de fotos favoritas y las opciones que vas eligiendo.

- Favoritas: las fotos que te gustan (las que edita la app o las que subas) se guardan en
  Documentos\\EDITFOTO\\fotos\\ejemplos\\<tipo de prenda> y la app vuelve a aprender de todas:
  fondo, encuadre, forma, orientacion y estilo. Cuantas mas pongas, mejor.
- Opciones: para una foto se preparan 4 versiones distintas (mas o menos forma del ejemplo,
  alisado, tamano, contraste), ordenadas por parecido con tus favoritas. La que eliges se
  aplica a esa foto y los ajustes del tipo de prenda se mueven un poco hacia ella, asi las
  siguientes fotos ya salen mas a tu gusto.

No es magia: aprende "hacia donde" te gusta cada ajuste (y lo cuenta en el resumen), no
entiende la foto como una persona.
"""

from __future__ import annotations

import io
import re
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import config, imagen, modelos, orientacion, pipeline

RITMO = 0.3  # cuanto se mueve el ajuste del tipo de prenda hacia la opcion elegida
MAX_HISTORIAL = 50
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}


def carpeta_ejemplos() -> Path:
    return modelos.DATOS / "fotos" / "ejemplos"


def _nombre_fichero(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(nombre).stem).strip("_") or "foto"
    return base[:80]


# ---------- banco de favoritas ----------

def guardar_favorita(proyecto, id_: str) -> Path:
    """Copia la foto editada al banco de favoritas de su tipo de prenda."""
    f = proyecto.foto(id_)
    origen = proyecto.ruta_resultado(f)
    if f.estado != "lista" or not origen.exists():
        raise ValueError("Esta foto aun no esta editada")
    destino = carpeta_ejemplos() / config.nombre_valido(f.preset) / f"fav_{_nombre_fichero(f.id)}.jpg"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    return destino


def guardar_ejemplo(preset: str, nombre: str, datos: bytes) -> Path:
    """Guarda una foto que te gusta (subida desde la app) en el banco de su tipo de prenda."""
    ext = Path(nombre).suffix.lower()
    if ext not in EXTENSIONES:
        raise ValueError("Solo fotos JPG, PNG o WEBP")
    try:
        with Image.open(io.BytesIO(datos)) as im:
            im.verify()
    except Exception as e:
        raise ValueError("El fichero no es una foto valida") from e
    base = _nombre_fichero(nombre)
    if base.lower().startswith("fondo"):
        base = "fondo"  # una foto del fondo vacio: se usa tal cual como fondo
    destino = carpeta_ejemplos() / config.nombre_valido(preset) / f"{base}{'.jpg' if ext == '.jpeg' else ext}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    return destino


def listar_ejemplos() -> dict[str, list[str]]:
    raiz = carpeta_ejemplos()
    if not raiz.exists():
        return {}
    return {d.name: sorted(p.name for p in d.iterdir() if p.suffix.lower() in EXTENSIONES)
            for d in sorted(raiz.iterdir()) if d.is_dir() and not d.name.startswith(".")}


def ruta_ejemplo(preset: str, nombre: str) -> Path:
    ruta = (carpeta_ejemplos() / preset / nombre).resolve()
    if carpeta_ejemplos().resolve() not in ruta.parents or ruta.suffix.lower() not in EXTENSIONES:
        raise ValueError("Ruta no valida")
    return ruta


def borrar_ejemplo(preset: str, nombre: str) -> None:
    ruta_ejemplo(preset, nombre).unlink(missing_ok=True)


# ---------- opciones para elegir ----------

def _valores(preset: dict, ajustes: dict) -> dict:
    """Los ajustes que se varian, tal como estan ahora para esta foto."""
    tiene_forma = (preset.get("forma") or {}).get("contorno") is not None
    v = {"arrugas": float(preset["arrugas"]["fuerza"]), "escala": float(ajustes.get("escala", 1.0)),
         "contraste": float(preset["color"]["contraste"])}
    if tiene_forma:
        v["forma"] = float(preset["forma"]["fuerza"])
    return v


def _propuestas(v: dict) -> list[tuple[str, dict]]:
    c = lambda x, lo=0.0, hi=1.0: round(float(np.clip(x, lo, hi)), 3)  # noqa: E731
    otras = []
    if "forma" in v:
        otras.append(("Más forma del ejemplo y menos alisado",
                      dict(v, forma=c(v["forma"] + 0.3), arrugas=c(v["arrugas"] - 0.2))))
        otras.append(("Menos forma, más alisado y algo más grande",
                      dict(v, forma=c(v["forma"] - 0.3), arrugas=c(v["arrugas"] + 0.2),
                           escala=c(v["escala"] * 1.06, 0.6, 1.4))))
    else:
        otras.append(("Menos alisado", dict(v, arrugas=c(v["arrugas"] - 0.3))))
        otras.append(("Más alisado y algo más grande",
                      dict(v, arrugas=c(v["arrugas"] + 0.3), escala=c(v["escala"] * 1.06, 0.6, 1.4))))
    otras.append(("Más pequeña y con más contraste",
                  dict(v, escala=c(v["escala"] * 0.94, 0.6, 1.4), contraste=c(v["contraste"] + 0.1, -0.5, 0.5))))
    return [("Como ahora", dict(v))] + otras


def _cambios(valores: dict) -> tuple[dict, dict]:
    """(cambios del preset, cambios de la foto) que producen esos valores."""
    p = {"arrugas": {"fuerza": valores["arrugas"]}, "color": {"contraste": valores["contraste"]}}
    if "forma" in valores:
        p["forma"] = {"fuerza": valores["forma"]}
    return p, {"escala": valores["escala"]}


def opciones(proyecto, id_: str) -> dict:
    """Prepara 4 versiones de la foto y las puntua por parecido con tus favoritas."""
    with proyecto.cerrojo:
        f = proyecto.foto(id_)
        if not f.analizada:
            proyecto.analizar(id_)
        preset = proyecto.preset_de(f)
        img = proyecto._imagen(f, preset)
        alfa = proyecto._alfa(f, img)
        capas = proyecto._capas(f, img)
        favoritas = (preset.get("estilo") or {}).get("huellas")
        lista = []
        for i, (nombre, valores) in enumerate(_propuestas(_valores(preset, f.ajustes))):
            cambios_p, cambios_f = _cambios(valores)
            resultado, _ = pipeline.renderizar(img, alfa, config.fusionar(preset, cambios_p),
                                               config.fusionar(f.ajustes, cambios_f), capas,
                                               f.medida_fondo, proyecto.referencia_fondo())
            imagen.guardar_jpg(resultado, proyecto._dir(id_) / f"opcion_{i}.jpg", 90)
            try:
                nota = orientacion.parecido(orientacion.huella_foto(resultado), favoritas)
            except Exception as e:  # sin el modelo, sin puntuacion
                print(f"Aviso: no se ha podido puntuar la opcion: {modelos.texto_error(e)}", flush=True)
                nota = None
            lista.append({"indice": i, "nombre": nombre, "valores": valores,
                          "parecido": None if nota is None else round(nota, 4)})
        notas = [o["parecido"] for o in lista]
        recomendada = int(np.argmax(notas)) if all(n is not None for n in notas) else 0
        f.opciones = lista
        proyecto._guardar_estado(f)
        return {"opciones": lista, "recomendada": recomendada, "con_favoritas": bool(favoritas)}


def _aprender_de(preset: dict, elegida: dict, otras: list[dict]) -> dict:
    """Mueve los ajustes del tipo de prenda hacia la opcion elegida y lo anota."""
    cambios: dict = {}
    v = elegida["valores"]
    mover = lambda actual, objetivo: round(float(actual + RITMO * (objetivo - actual)), 3)  # noqa: E731
    cambios["arrugas"] = {"fuerza": mover(preset["arrugas"]["fuerza"], v["arrugas"])}
    cambios["color"] = {"contraste": mover(preset["color"]["contraste"], v["contraste"])}
    if "forma" in v:
        cambios["forma"] = {"fuerza": mover(preset["forma"]["fuerza"], v["forma"])}
    if abs(v["escala"] - 1.0) > 1e-3:  # el tamano elegido pasa poco a poco al encuadre
        factor = v["escala"] ** RITMO
        enc = preset["encuadre"]
        cambios["encuadre"] = {k: round(float(np.clip(enc[k] * factor, 0.2, 0.97)), 3)
                               for k in ("relleno", "relleno_x", "relleno_y") if enc.get(k) is not None}
    a = preset.get("aprendizaje") or {}
    historial = list(a.get("historial") or [])
    historial.append({"fecha": time.strftime("%Y-%m-%d %H:%M"), "elegida": v,
                      "otras": [o["valores"] for o in otras]})
    cambios["aprendizaje"] = {"elecciones": int(a.get("elecciones") or 0) + 1,
                              "historial": historial[-MAX_HISTORIAL:]}
    return cambios


def elegir(proyecto, id_: str, indice: int):
    """Aplica la opcion elegida a la foto y aprende de la eleccion."""
    with proyecto.cerrojo:
        f = proyecto.foto(id_)
        if not f.opciones or not 0 <= indice < len(f.opciones):
            raise ValueError("Primero pide las opciones de esta foto")
        elegida = f.opciones[indice]
        otras = [o for o in f.opciones if o is not elegida]
        cambios_p, cambios_f = _cambios(elegida["valores"])
        base = config.cargar_preset(f.preset)
        config.guardar_preset(config.fusionar(base, _aprender_de(base, elegida, otras)))
        f.opciones = []
        ajustes = config.fusionar(f.ajustes, dict(cambios_f, preset=config.fusionar(f.ajustes.get("preset") or {},
                                                                                     cambios_p)))
        return proyecto.ajustar(id_, ajustes=ajustes, reemplazar=True)


def resumen(preset: dict) -> list[str]:
    """Lo que ha aprendido de tus elecciones, en frases."""
    historial = (preset.get("aprendizaje") or {}).get("historial") or []
    if not historial:
        return []
    frases = [f"Has elegido entre opciones {len(historial)} veces en las fotos de {preset['nombre']}."]
    nombres = {"forma": ("más forma del ejemplo", "menos forma del ejemplo"),
               "arrugas": ("más alisado", "menos alisado"),
               "escala": ("la prenda más grande", "la prenda más pequeña"),
               "contraste": ("más contraste", "menos contraste")}
    for clave, (mas, menos) in nombres.items():
        difs = [h["elegida"][clave] - np.mean([o[clave] for o in h["otras"]])
                for h in historial if clave in h["elegida"] and h["otras"]]
        if len(difs) >= 3 and abs(np.mean(difs)) > 0.03:
            veces = sum(d > 0 for d in difs) if np.mean(difs) > 0 else sum(d < 0 for d in difs)
            frases.append(f"Sueles preferir {mas if np.mean(difs) > 0 else menos} ({veces} de {len(difs)} veces).")
    return frases
