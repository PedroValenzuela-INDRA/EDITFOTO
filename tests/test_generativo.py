"""Retoque generativo contra un ComfyUI simulado: protocolo, zona pegada y flujo en la app."""

from __future__ import annotations

import io
import json
import sys
import threading
import time
import uuid
from email.parser import BytesParser
from email.policy import default as politica
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editfoto import config, generativo, imagen, modelos  # noqa: E402

MODELOS_OK = dict(config.POR_DEFECTO["generativo"]["modelos"])


class ComfyFalso(BaseHTTPRequestHandler):
    """Lo justo de ComfyUI: la "IA" pinta de magenta la zona de la mascara."""

    imagenes: dict = {}
    historias: dict = {}
    flujos: list = []

    def log_message(self, *a):
        pass

    def _responder(self, cuerpo, tipo="application/json", codigo=200):
        datos = json.dumps(cuerpo).encode() if tipo == "application/json" else cuerpo
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/system_stats":
            return self._responder({"devices": [{"name": "GPU simulada"}]})
        if u.path == "/object_info":
            lista = lambda clave: [[MODELOS_OK[clave], "otro.safetensors"]]  # noqa: E731
            return self._responder({
                "UnetLoaderGGUF": {"input": {"required": {"unet_name": lista("unet")}}},
                "CLIPLoader": {"input": {"required": {"clip_name": lista("clip")}}},
                "VAELoader": {"input": {"required": {"vae_name": lista("vae")}}},
                "LoraLoaderModelOnly": {"input": {"required": {"lora_name": lista("lora")}}},
                "TextEncodeQwenImageEditPlus": {}, "SetLatentNoiseMask": {}})
        if u.path.startswith("/history/"):
            pid = u.path.rsplit("/", 1)[1]
            return self._responder({pid: self.historias[pid]} if pid in self.historias else {})
        if u.path == "/view":
            return self._responder(self.imagenes[parse_qs(u.query)["filename"][0]], "image/png")
        self._responder({"error": "no"}, codigo=404)

    def do_POST(self):
        cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/upload/image":
            msg = BytesParser(policy=politica).parsebytes(
                f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + cuerpo)
            parte = next(p for p in msg.iter_parts() if p.get_param("name", header="content-disposition") == "image")
            nombre = parte.get_filename()
            self.imagenes[nombre] = parte.get_payload(decode=True)
            return self._responder({"name": nombre, "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            flujo = json.loads(cuerpo)["prompt"]
            self.flujos.append(flujo)
            foto = np.asarray(Image.open(io.BytesIO(self.imagenes[flujo["7"]["inputs"]["image"]])).convert("RGB")).copy()
            m = np.asarray(Image.open(io.BytesIO(self.imagenes[flujo["8"]["inputs"]["image"]])).convert("RGB"))[..., 0] > 127
            foto[m] = (255, 0, 255)
            salida = f"editfoto_{uuid.uuid4().hex[:6]}.png"
            buf = io.BytesIO()
            Image.fromarray(foto).save(buf, "PNG")
            self.imagenes[salida] = buf.getvalue()
            pid = uuid.uuid4().hex
            self.historias[pid] = {"status": {"status_str": "success"},
                                   "outputs": {"16": {"images": [{"filename": salida, "subfolder": "", "type": "output"}]}}}
            return self._responder({"prompt_id": pid, "number": 0, "node_errors": {}})
        self._responder({"error": "no"}, codigo=404)


@pytest.fixture
def comfy():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), ComfyFalso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


def sudadera() -> tuple[np.ndarray, np.ndarray]:
    img = np.full((500, 400, 3), 0.8, np.float32)
    alfa = np.zeros((500, 400), np.float32)
    alfa[60:440, 80:320] = 1
    img[alfa > 0] = (0.3, 0.2, 0.15)
    return img, alfa


def test_retocar_solo_cambia_la_zona(comfy):
    img, alfa = sudadera()
    ajustes = dict(config.POR_DEFECTO["generativo"], opciones=2)
    cliente = generativo.buscar_servidor(comfy)
    assert cliente.estado(ajustes["modelos"])["listo"]
    versiones = generativo.retocar(img, alfa, cliente, ajustes, "bajo", semillas=[1, 2])
    assert len(versiones) == 2
    zona = generativo.zona(alfa, "bajo") > 0
    for v in versiones:
        assert np.array_equal(v[~zona], img[~zona]), "fuera de la zona la foto queda exacta"
        dentro = v[zona][:, [0, 2]].mean(0)
        assert (dentro > 0.6).all(), "dentro de la zona se pega lo generado (magenta)"
    flujo = ComfyFalso.flujos[-1]
    assert flujo["10"]["inputs"]["prompt"] == generativo.INSTRUCCIONES["bajo"]
    assert flujo["14"]["inputs"]["seed"] == 2 and flujo["1"]["inputs"]["unet_name"] == MODELOS_OK["unet"]


def test_estado_dice_que_modelo_falta(comfy):
    cliente = generativo.buscar_servidor(comfy)
    estado = cliente.estado(dict(MODELOS_OK, unet="otro-modelo.gguf"))
    assert estado["conectado"] and not estado["listo"] and estado["faltan_modelos"] == ["unet: otro-modelo.gguf"]


def test_sin_comfyui_avisa_claro(monkeypatch):
    monkeypatch.setattr(generativo, "PUERTOS_COMUNES", ())
    with pytest.raises(generativo.ErrorGenerativo, match="ComfyUI"):
        generativo.buscar_servidor("http://127.0.0.1:9")


def test_flujo_completo_en_la_app(comfy, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from editfoto.proyecto import Proyecto
    from editfoto.servidor import crear_app

    monkeypatch.setattr(modelos, "DATOS", tmp_path / "datos")
    monkeypatch.setattr(config, "CARPETA_PRESETS_USUARIO", tmp_path / "datos" / "presets")
    monkeypatch.setattr("editfoto.segmentar.segmentar",
                        lambda im, modelo="auto": (np.abs(im - 0.8).max(axis=2) > 0.1).astype(np.float32))
    config.guardar_preset(config.fusionar(config.cargar_preset("generico"),
                                          {"nombre": "sudadera", "generativo": {"servidor": comfy, "opciones": 2}}))
    entrada = tmp_path / "entrada"
    (entrada / "sudadera").mkdir(parents=True)
    img, _ = sudadera()
    imagen.guardar_jpg(img, entrada / "sudadera" / "a.jpg", 95)
    p = Proyecto(entrada, tmp_path / "salida")
    p.procesar_lote()
    c = TestClient(crear_app(p))

    assert c.get("/api/generativo", params={"preset": "sudadera"}).json()["listo"] is True
    assert c.post("/api/fotos/sudadera__a/generativo", json={"zona": "bajo"}).json()["empezado"]
    for _ in range(200):
        e = c.get("/api/fotos/sudadera__a/generativo").json()
        if not e["activo"]:
            break
        time.sleep(0.05)
    assert e["error"] is None and e["opciones"] == [0, 1]
    assert c.get("/img/sudadera__a/generada/1").status_code == 200
    foto = c.post("/api/fotos/sudadera__a/generativo/elegir", json={"indice": 1}).json()
    assert foto["generada"] is True and foto["estado"] == "lista"
    # La foto de partida ya es la generada: el magenta de la zona pasa a la prenda.
    trabajo = p.imagen_trabajo("sudadera__a")
    assert (trabajo[..., 1] < 0.2).sum() > 1000
    foto = c.delete("/api/fotos/sudadera__a/generativo").json()
    assert foto["generada"] is False and (p.imagen_trabajo("sudadera__a")[..., 1] < 0.1).sum() == 0
    assert c.post("/api/fotos/sudadera__a/generativo", json={"zona": "inventada"}).status_code == 400
