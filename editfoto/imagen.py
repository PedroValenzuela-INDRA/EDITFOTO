"""Lectura y escritura de imagenes. Internamente todo es float32 RGB en [0, 1]."""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps

try:  # Fotos HEIC del iPhone (opcional).
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp"}
_SRGB = ImageCms.createProfile("sRGB")


def es_imagen(ruta: Path) -> bool:
    return ruta.suffix.lower() in EXTENSIONES and not ruta.name.startswith(".")


def cargar(ruta: str | Path) -> np.ndarray:
    im = Image.open(ruta)
    im = ImageOps.exif_transpose(im)  # gira segun la orientacion del movil
    icc = im.info.get("icc_profile")
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    if icc:  # p. ej. Display P3 del iPhone: convertir a sRGB para que los colores no cambien
        try:
            perfil = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, perfil, _SRGB, outputMode=im.mode)
        except Exception:
            pass
    if im.mode == "RGBA":  # transparencia sobre blanco
        fondo = Image.new("RGB", im.size, (255, 255, 255))
        fondo.paste(im, mask=im.getchannel("A"))
        im = fondo
    return np.asarray(im, dtype=np.float32) / 255.0


def reducir(img: np.ndarray, max_lado: int) -> np.ndarray:
    h, w = img.shape[:2]
    escala = max_lado / max(h, w)
    if escala >= 1:
        return img
    return cv2.resize(img, (round(w * escala), round(h * escala)), interpolation=cv2.INTER_AREA)


def a_uint8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def guardar_jpg(img: np.ndarray, ruta: str | Path, calidad: int = 92) -> None:
    """Guarda en sRGB sin metadatos (no se filtra la ubicacion GPS del movil)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.stem + ".tmp.jpg")
    Image.fromarray(a_uint8(img)).save(tmp, "JPEG", quality=calidad, subsampling=0, optimize=True)
    tmp.replace(ruta)


def guardar_png_gris(mapa: np.ndarray, ruta: str | Path) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a_uint8(mapa), mode="L").save(ruta)


def cargar_png_gris(ruta: str | Path, tamano: tuple[int, int] | None = None) -> np.ndarray:
    """Carga una capa en gris [0, 1]; si se da tamano (ancho, alto) se reescala."""
    im = Image.open(ruta).convert("L")
    if tamano and im.size != tamano:
        im = im.resize(tamano, Image.BILINEAR)
    return np.asarray(im, dtype=np.float32) / 255.0


def miniatura(img: np.ndarray, ruta: str | Path, lado: int = 480) -> None:
    guardar_jpg(reducir(img, lado), ruta, calidad=85)


def luminancia(img: np.ndarray) -> np.ndarray:
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722


def srgb_a_lineal(img: np.ndarray) -> np.ndarray:
    return np.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4)


def lineal_a_srgb(img: np.ndarray) -> np.ndarray:
    img = np.clip(img, 0, None)
    return np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(img, 1 / 2.4) - 0.055)


def color_hex(texto: str) -> np.ndarray:
    texto = texto.lstrip("#")
    return np.array([int(texto[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def a_hex(color: np.ndarray) -> str:
    return "#" + "".join(f"{int(round(float(c) * 255)):02X}" for c in np.clip(color, 0, 1))
