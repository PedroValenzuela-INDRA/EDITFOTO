"""Presets de edicion (uno por tipo de prenda) guardados como JSON.

Hay dos carpetas: la del programa (presets/ del repositorio, se actualiza sola) y
la tuya (DATOS/presets). Lo que guardas va siempre a la tuya y tiene prioridad,
asi una actualizacion nunca pisa tus ajustes.

Un preset solo necesita indicar lo que cambia respecto a POR_DEFECTO.
Los ajustes de una foto concreta se fusionan encima del preset con la misma forma.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .modelos import DATOS, RAIZ

CARPETA_PRESETS = RAIZ / "presets"
CARPETA_PRESETS_USUARIO = DATOS / "presets"

POR_DEFECTO: dict = {
    "nombre": "generico",
    "descripcion": "Ajustes generales para cualquier prenda",
    # Tamano de la foto final. 3:4 vertical encaja bien en la rejilla de Vinted.
    "lienzo": {"ancho": 1500, "alto": 2000},
    # relleno: fraccion del lienzo que ocupa la prenda en su dimension mas ajustada.
    # relleno_x / relleno_y (opcionales): caja con ancho y alto por separado; las aprende
    # "aprender" de tus ejemplos (p. ej. ancha pero baja para dejar sitio a una decoracion).
    # centro_x / centro_y: donde queda el centro de la prenda (0.5 = centrada).
    "encuadre": {"relleno": 0.84, "relleno_x": None, "relleno_y": None, "centro_x": 0.5, "centro_y": 0.5},
    # Adaptar la forma de la prenda a la silueta de tus ejemplos (mangas en arco...). Deforma la
    # foto real, no inventa nada. "contorno" lo rellena "aprender"; fuerza 0 = como en la foto.
    "forma": {"contorno": None, "fuerza": 0.7},
    # Cuartos de vuelta (en sentido horario) que se aplican a las fotos nuevas de este preset.
    # Util si siempre disparas con el movil en horizontal y la prenda sale tumbada.
    "giro_inicial": 0,
    # Poner la prenda derecha sola (cuello o cintura arriba) con un modelo de vision local.
    # "huellas" las rellena "aprender" con tus ejemplos; sin ellas se usa una coleccion generica.
    "orientacion": {"auto": True, "huellas": None},
    # Tus fotos favoritas enteras (las rellena "aprender"): para puntuar las opciones de una foto.
    "estilo": {"huellas": None},
    # Lo que la app va aprendiendo de las opciones que eliges (lo rellena "elegir").
    "aprendizaje": {"elecciones": 0, "historial": []},
    # Retoque generativo (opcional, necesita ComfyUI abierto en este PC: docs/GENERATIVO.md).
    "generativo": {
        "servidor": "http://127.0.0.1:8188",
        "zona": "bajo",
        "opciones": 3,
        "pasos": 4,
        "cfg": 1.0,
        "modelos": {
            "unet": "qwen-image-edit-2511-Q4_K_M.gguf",
            "clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "vae": "qwen_image_vae.safetensors",
            "lora": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
        },
    },
    # tipo: "color" (fondo liso), "imagen" (tu fondo favorito) u "original" (se deja el fondo de la foto).
    "fondo": {"tipo": "color", "color": "#F4F4F2", "imagen": ""},
    # Sombra suave bajo la prenda para que no parezca pegada. Valores relativos al tamano de la prenda.
    "sombra": {"opacidad": 0.22, "desenfoque": 0.03, "desplazamiento_x": 0.0, "desplazamiento_y": 0.008},
    "color": {
        # Iguala exposicion y tono de todas las fotos del lote usando el fondo del set como referencia
        # (el movil cambia la exposicion segun si la prenda es clara u oscura).
        "igualar_con_fondo": True,
        # Si el fondo del set es gris o blanco, lo usa para quitar dominantes de color.
        "balance_blancos": True,
        "brillo": 0.0,       # en pasos de diafragma (-1 a 1)
        "contraste": 0.0,    # -0.5 a 0.5
        "saturacion": 1.0,   # 1 = sin cambios
    },
    # Suavizado de arrugas: separacion de frecuencias con filtro guiado. Solo toca la luminosidad
    # de la prenda; la textura fina, estampados, manchas y rotos se conservan.
    # escala: tamano maximo de arruga que se aplana (fraccion del tamano de la prenda).
    "arrugas": {"fuerza": 0.5, "escala": 0.10, "respeto_bordes": 0.5},
    # Endereza la prenda buscando su eje de simetria (como mucho max_grados).
    "enderezar": {"activo": True, "max_grados": 6.0},
    "mascara": {"min_componente": 0.08, "max_hueco": 0.004, "quitar_cables": True, "pulir_bordes": True,
                "refinar_bordes": "auto"},
    "nitidez": 0.3,
    "segmentacion": {"modelo": "auto"},
    "salida": {"calidad_jpg": 92, "max_lado_trabajo": 2400},
}

# Ajustes por foto que no existen en el preset.
AJUSTES_FOTO: dict = {"rotacion": 0.0, "escala": 1.0, "mover_x": 0.0, "mover_y": 0.0, "enderezar_auto": True}


def fusionar(base: dict, cambios: dict | None) -> dict:
    salida = copy.deepcopy(base)
    for clave, valor in (cambios or {}).items():
        if isinstance(valor, dict) and isinstance(salida.get(clave), dict):
            salida[clave] = fusionar(salida[clave], valor)
        else:
            salida[clave] = copy.deepcopy(valor)
    return salida


def nombre_valido(nombre: str) -> str:
    limpio = re.sub(r"[^a-z0-9_-]+", "_", nombre.strip().lower()).strip("_")
    if not limpio:
        raise ValueError("Nombre de preset vacio")
    return limpio


def listar_presets() -> list[str]:
    nombres = {p.stem for carpeta in (CARPETA_PRESETS, CARPETA_PRESETS_USUARIO) for p in carpeta.glob("*.json")}
    nombres.add("generico")
    return sorted(nombres)


def _ruta_preset(nombre: str) -> Path:
    propia = CARPETA_PRESETS_USUARIO / f"{nombre}.json"
    return propia if propia.exists() else CARPETA_PRESETS / f"{nombre}.json"


def cargar_preset(nombre: str | None) -> dict:
    """Preset completo (POR_DEFECTO + lo que diga el fichero). Si no existe, el generico."""
    nombre = nombre or "generico"
    ruta = _ruta_preset(nombre)
    if not ruta.exists():
        return fusionar(POR_DEFECTO, {"nombre": nombre} if nombre != "generico" else {})
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    preset = fusionar(POR_DEFECTO, datos)
    preset["nombre"] = nombre
    return preset


def guardar_preset(preset: dict) -> Path:
    nombre = nombre_valido(preset.get("nombre", ""))
    CARPETA_PRESETS_USUARIO.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA_PRESETS_USUARIO / f"{nombre}.json"
    datos = dict(preset, nombre=nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    return ruta


def preset_para_carpeta(carpeta: str) -> str | None:
    """Si la foto esta en una subcarpeta con nombre de preset (p. ej. entrada/sudadera/), se usa ese."""
    if not carpeta:
        return None
    nombre = Path(carpeta).parts[0].lower()
    return nombre if nombre in listar_presets() else None
