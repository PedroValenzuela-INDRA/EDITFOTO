"""Retoque generativo (opcional): una IA de imagen local recoloca una parte de la prenda.

Por ejemplo, doblar el bajo de una sudadera ensenando el forro, o abrir las mangas. Eso no
se puede hacer deformando la foto (el forro no sale en ella): hay que generarlo. Lo hace un
modelo de edicion de imagenes (Qwen-Image-Edit-2511, licencia Apache 2.0, se puede usar
para vender) que corre en tu tarjeta grafica dentro de ComfyUI, un programa aparte. Esta
app le manda la foto, la zona a cambiar y la instruccion, y recibe varias versiones.

Para que lo demas siga siendo tu prenda de verdad, solo se pega la zona marcada; fuera de
ella la foto queda pixel a pixel como estaba. Aun asi, lo generado es inventado: revisalo
siempre, porque el forro o una costura pueden no ser como los de tu prenda.

Guia de instalacion: docs/GENERATIVO.md.
"""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import cv2
import numpy as np
from PIL import Image

INSTRUCCIONES = {
    "bajo": ("Fold the bottom hem of the garment upward and outward so that the inside lining is visible, "
             "like a neat second-hand clothing product photo. Keep the fabric, colour, texture, logos, "
             "zipper and every other part of the garment exactly the same."),
    "mangas": ("Open the sleeves of the garment outward in a gentle arc, laid flat and symmetrical, like a "
               "neat product photo. Keep the fabric, colour, texture, logos and every other part exactly the same."),
    "todo": ("Neatly rearrange the garment as a flat-lay product photo, symmetrical and smooth. Keep the fabric, "
             "colour, texture, logos, labels and any defects exactly the same."),
}
NODOS_NECESARIOS = ("UnetLoaderGGUF", "TextEncodeQwenImageEditPlus", "SetLatentNoiseMask")
PUERTOS_COMUNES = ("http://127.0.0.1:8188", "http://127.0.0.1:8000")


class ErrorGenerativo(RuntimeError):
    pass


class Cliente:
    """Lo minimo de la API HTTP de ComfyUI: subir imagenes, encolar un flujo y recoger el resultado."""

    def __init__(self, url: str, timeout: float = 15.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.cliente_id = uuid.uuid4().hex

    def _pedir(self, metodo: str, ruta: str, datos: bytes | None = None, tipo: str | None = None) -> bytes:
        cab = {"Content-Type": tipo} if tipo else {}
        req = urllib.request.Request(self.url + ruta, data=datos, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")[:500]
            raise ErrorGenerativo(f"ComfyUI respondio {e.code}: {cuerpo}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise ErrorGenerativo(f"No se puede conectar con ComfyUI en {self.url}. Abre ComfyUI y vuelve a probar.") from e

    def _json(self, metodo: str, ruta: str, cuerpo: dict | None = None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        return json.loads(self._pedir(metodo, ruta, datos, "application/json" if datos else None) or b"null")

    def estado(self, modelos: dict) -> dict:
        """Comprueba que ComfyUI responde y tiene los nodos y modelos necesarios."""
        sistema = self._json("GET", "/system_stats")
        info = self._json("GET", "/object_info")
        faltan_nodos = [n for n in NODOS_NECESARIOS if n not in info]
        disponibles = {
            "unet": _opciones(info, "UnetLoaderGGUF", "unet_name"),
            "clip": _opciones(info, "CLIPLoader", "clip_name"),
            "vae": _opciones(info, "VAELoader", "vae_name"),
            "lora": _opciones(info, "LoraLoaderModelOnly", "lora_name"),
        }
        faltan_modelos = [f"{k}: {v}" for k, v in modelos.items() if v and k in disponibles and v not in disponibles[k]]
        dispositivos = [d.get("name", "") for d in (sistema or {}).get("devices", [])]
        return {"conectado": True, "servidor": self.url, "dispositivos": dispositivos,
                "faltan_nodos": faltan_nodos, "faltan_modelos": faltan_modelos,
                "listo": not faltan_nodos and not faltan_modelos}

    def subir(self, nombre: str, png: bytes) -> str:
        frontera = uuid.uuid4().hex
        partes = []
        for campo, valor in (("type", "input"), ("overwrite", "true")):
            partes.append(f"--{frontera}\r\nContent-Disposition: form-data; name=\"{campo}\"\r\n\r\n{valor}\r\n".encode())
        partes.append(f"--{frontera}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{nombre}\"\r\n"
                      "Content-Type: image/png\r\n\r\n".encode() + png + b"\r\n")
        partes.append(f"--{frontera}--\r\n".encode())
        r = json.loads(self._pedir("POST", "/upload/image", b"".join(partes), f"multipart/form-data; boundary={frontera}"))
        return (r.get("subfolder") + "/" if r.get("subfolder") else "") + r["name"]

    def encolar(self, flujo: dict) -> str:
        r = self._json("POST", "/prompt", {"prompt": flujo, "client_id": self.cliente_id})
        if r.get("node_errors"):
            raise ErrorGenerativo(f"ComfyUI no acepta el flujo: {json.dumps(r['node_errors'])[:500]}")
        return r["prompt_id"]

    def esperar(self, prompt_id: str, tiempo_max: float = 900, cancelar=None) -> list[dict]:
        limite = time.time() + tiempo_max
        while time.time() < limite:
            if cancelar is not None and cancelar.is_set():
                raise ErrorGenerativo("Cancelado")
            historia = self._json("GET", f"/history/{prompt_id}")
            if historia and prompt_id in historia:
                h = historia[prompt_id]
                estado = h.get("status", {})
                if estado.get("status_str") == "error":
                    mensajes = [m for m in estado.get("messages", []) if m and m[0] == "execution_error"]
                    detalle = mensajes[0][1].get("exception_message", "") if mensajes else ""
                    raise ErrorGenerativo(f"ComfyUI ha fallado al generar: {detalle}".strip())
                return [img for salida in h.get("outputs", {}).values() for img in salida.get("images", [])]
            time.sleep(1.0)
        raise ErrorGenerativo("ComfyUI tarda demasiado (mas de 15 minutos)")

    def descargar(self, img: dict) -> bytes:
        q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output")})
        return self._pedir("GET", f"/view?{q}")


def _opciones(info: dict, nodo: str, entrada: str) -> list[str]:
    try:
        valor = info[nodo]["input"]["required"][entrada][0]
        return list(valor) if isinstance(valor, list) else []
    except (KeyError, IndexError, TypeError):
        return []


def buscar_servidor(preferido: str) -> Cliente:
    """El servidor configurado o, si no responde, los puertos habituales de ComfyUI."""
    for url in dict.fromkeys([preferido, *PUERTOS_COMUNES]):
        c = Cliente(url, timeout=3)
        try:
            c._json("GET", "/system_stats")
            c.timeout = 30
            return c
        except ErrorGenerativo:
            continue
    raise ErrorGenerativo("No encuentro ComfyUI abierto en este PC. Abrelo y vuelve a probar (mira docs/GENERATIVO.md).")


def flujo_qwen(imagen: str, mascara: str, instruccion: str, semilla: int, ajustes: dict) -> dict:
    """Flujo de ComfyUI (formato API) para editar la zona marcada con Qwen-Image-Edit-2511."""
    m = ajustes["modelos"]
    modelo = ["1", 0]
    flujo = {"1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": m["unet"]}}}
    if m.get("lora"):
        flujo["2"] = {"class_type": "LoraLoaderModelOnly",
                      "inputs": {"model": modelo, "lora_name": m["lora"], "strength_model": 1.0}}
        modelo = ["2", 0]
    flujo.update({
        "3": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": modelo, "shift": 3.1}},
        "4": {"class_type": "CFGNorm", "inputs": {"model": ["3", 0], "strength": 1.0}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": m["clip"], "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": m["vae"]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": imagen}},
        "8": {"class_type": "LoadImageMask", "inputs": {"image": mascara, "channel": "red"}},
        "9": {"class_type": "GrowMask", "inputs": {"mask": ["8", 0], "expand": 8, "tapered_corners": True}},
        "10": {"class_type": "TextEncodeQwenImageEditPlus",
               "inputs": {"clip": ["5", 0], "prompt": instruccion, "vae": ["6", 0], "image1": ["7", 0]}},
        "11": {"class_type": "TextEncodeQwenImageEditPlus",
               "inputs": {"clip": ["5", 0], "prompt": "", "vae": ["6", 0], "image1": ["7", 0]}},
        "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["7", 0], "vae": ["6", 0]}},
        "13": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["12", 0], "mask": ["9", 0]}},
        "14": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": int(semilla), "steps": int(ajustes["pasos"]), "cfg": float(ajustes["cfg"]),
            "sampler_name": "euler", "scheduler": "simple", "positive": ["10", 0], "negative": ["11", 0],
            "latent_image": ["13", 0], "denoise": 1.0}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["6", 0]}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": "editfoto"}},
    })
    return flujo


def zona(alfa: np.ndarray, cual: str) -> np.ndarray:
    """Zona a regenerar (0 a 1), en coordenadas de la foto: lo que puede cambiar, con margen
    para que la prenda pueda cambiar de silueta (el bajo doblado sube, las mangas se abren)."""
    prenda = alfa > 0.5
    h, w = prenda.shape
    if prenda.sum() < 100:
        raise ValueError("No hay prenda en la foto")
    ys, xs = np.nonzero(prenda)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    alto, ancho = y1 - y0, x1 - x0
    m = np.zeros((h, w), np.float32)
    if cual == "bajo":
        m[int(y1 - 0.32 * alto):int(min(h, y1 + 0.08 * alto)), int(max(0, x0 - 0.04 * ancho)):int(min(w, x1 + 0.04 * ancho))] = 1
    elif cual == "mangas":
        franja = int(0.3 * ancho)
        m[y0:y1 + 1, int(max(0, x0 - 0.12 * ancho)):x0 + franja] = 1
        m[y0:y1 + 1, x1 - franja:int(min(w, x1 + 0.12 * ancho))] = 1
    elif cual == "todo":
        m[int(max(0, y0 - 0.05 * alto)):int(min(h, y1 + 0.05 * alto)), int(max(0, x0 - 0.05 * ancho)):int(min(w, x1 + 0.05 * ancho))] = 1
    else:
        raise ValueError(f"Zona desconocida: {cual}")
    return m


def _caja(alfa: np.ndarray, margen: float = 0.12) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(alfa > 0.5)
    h, w = alfa.shape
    alto, ancho = ys.max() - ys.min(), xs.max() - xs.min()
    return (int(max(0, ys.min() - margen * alto)), int(min(h, ys.max() + margen * alto)),
            int(max(0, xs.min() - margen * ancho)), int(min(w, xs.max() + margen * ancho)))


def _png(img: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def retocar(img: np.ndarray, alfa: np.ndarray, cliente: Cliente, ajustes: dict, zona_cual: str,
            instruccion: str | None = None, semillas: list[int] | None = None, avisar=None, cancelar=None) -> list[np.ndarray]:
    """Devuelve varias versiones de la foto entera con la zona regenerada (el resto, intacto)."""
    instruccion = (instruccion or "").strip() or INSTRUCCIONES[zona_cual]
    semillas = semillas or [int(s) for s in np.random.default_rng().integers(1, 2**31 - 1, int(ajustes["opciones"]))]
    m_zona = zona(alfa, zona_cual)
    y0, y1, x0, x1 = _caja(np.maximum(alfa, m_zona))
    trozo, trozo_m = img[y0:y1, x0:x1], m_zona[y0:y1, x0:x1]
    # El modelo trabaja a ~1 megapixel con lados multiplos de 16: se gasta en la prenda.
    e = np.sqrt(1024 * 1024 / (trozo.shape[0] * trozo.shape[1]))
    tam = (max(16, int(round(trozo.shape[1] * e / 16)) * 16), max(16, int(round(trozo.shape[0] * e / 16)) * 16))
    nombre_img = cliente.subir(f"editfoto_{uuid.uuid4().hex[:8]}.png", _png(cv2.resize(trozo, tam, interpolation=cv2.INTER_AREA)))
    m_peq = cv2.resize(trozo_m, tam, interpolation=cv2.INTER_LINEAR)
    nombre_m = cliente.subir(f"editfoto_{uuid.uuid4().hex[:8]}_mascara.png", _png(np.dstack([m_peq] * 3)))
    # Pegar solo la zona, con el borde fundido: fuera, la foto original exacta.
    fundido = cv2.GaussianBlur(trozo_m, (0, 0), max(2.0, 0.01 * max(trozo_m.shape)))
    fundido = np.minimum(fundido, trozo_m)[..., None]
    versiones = []
    for i, semilla in enumerate(semillas):
        if avisar:
            avisar(i, len(semillas))
        pid = cliente.encolar(flujo_qwen(nombre_img, nombre_m, instruccion, semilla, ajustes))
        salidas = cliente.esperar(pid, cancelar=cancelar)
        if not salidas:
            raise ErrorGenerativo("ComfyUI no ha devuelto ninguna imagen")
        with Image.open(io.BytesIO(cliente.descargar(salidas[0]))) as im:
            generada = np.asarray(im.convert("RGB"), np.float32) / 255.0
        generada = cv2.resize(generada, (trozo.shape[1], trozo.shape[0]), interpolation=cv2.INTER_CUBIC)
        nueva = img.copy()
        nueva[y0:y1, x0:x1] = trozo * (1 - fundido) + np.clip(generada, 0, 1) * fundido
        versiones.append(nueva.astype(np.float32))
    return versiones
