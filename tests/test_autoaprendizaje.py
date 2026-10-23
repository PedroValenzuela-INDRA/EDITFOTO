"""Autoaprendizaje: banco de favoritas, opciones para elegir y lo que la app aprende de ti."""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editfoto import config, imagen, modelos  # noqa: E402


def camiseta(color, alto=600, ancho=600) -> np.ndarray:
    img = np.full((alto, ancho, 3), 0.82, np.float32)
    img[120:230, 90:510] = color  # mangas
    img[230:520, 200:400] = color  # cuerpo
    img[300:420, 230:370] *= 0.8  # una arruga grande
    return img


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from editfoto.proyecto import Proyecto
    from editfoto.servidor import crear_app

    monkeypatch.setattr(modelos, "DATOS", tmp_path / "datos")
    monkeypatch.setattr(config, "CARPETA_PRESETS_USUARIO", tmp_path / "datos" / "presets")
    monkeypatch.setattr("editfoto.segmentar.segmentar",
                        lambda im, modelo="auto": (im.mean(axis=2) < 0.6).astype(np.float32))
    config.guardar_preset(config.fusionar(config.cargar_preset("generico"), {"nombre": "camiseta"}))
    entrada = tmp_path / "entrada"
    (entrada / "camiseta").mkdir(parents=True)
    imagen.guardar_jpg(camiseta((0.2, 0.3, 0.6)), entrada / "camiseta" / "a.jpg", 95)
    imagen.guardar_jpg(camiseta((0.55, 0.15, 0.15)), entrada / "camiseta" / "b.jpg", 95)
    p = Proyecto(entrada, tmp_path / "salida")
    p.procesar_lote()
    assert all(f.estado == "lista" for f in p.lista()), [f.error for f in p.lista()]
    return p, TestClient(crear_app(p))


def esperar_aprendizaje(c):
    for _ in range(300):
        e = c.get("/api/aprendizaje").json()
        if not e["activo"]:
            return e
        time.sleep(0.1)
    raise AssertionError("el aprendizaje no termina")


def test_opciones_y_elegir_mueve_el_preset(entorno):
    p, c = entorno
    r = c.post("/api/fotos/camiseta__a/opciones").json()
    assert len(r["opciones"]) == 4 and r["opciones"][0]["nombre"] == "Como ahora"
    for o in r["opciones"]:
        assert c.get(f"/img/camiseta__a/opcion/{o['indice']}").status_code == 200
    antes = config.cargar_preset("camiseta")["arrugas"]["fuerza"]
    elegida = r["opciones"][1]
    foto = c.post("/api/fotos/camiseta__a/elegir", json={"indice": 1}).json()
    assert foto["estado"] == "lista"
    assert foto["ajustes"]["preset"]["arrugas"]["fuerza"] == pytest.approx(elegida["valores"]["arrugas"])
    despues = config.cargar_preset("camiseta")
    esperado = antes + 0.3 * (elegida["valores"]["arrugas"] - antes)
    assert despues["arrugas"]["fuerza"] == pytest.approx(esperado, abs=1e-3)
    assert despues["aprendizaje"]["elecciones"] == 1
    # Sin opciones preparadas no se puede elegir.
    assert c.post("/api/fotos/camiseta__a/elegir", json={"indice": 0}).status_code == 400
    assert c.get("/api/presets/camiseta/aprendizaje").json()["elecciones"] == 1


def test_favoritas_se_guardan_y_la_app_reaprende(entorno, tmp_path):
    p, c = entorno
    r = c.post("/api/fotos/camiseta__b/favorita").json()
    fav = Path(r["ruta"])
    assert fav.exists() and fav.parent == tmp_path / "datos" / "fotos" / "ejemplos" / "camiseta"
    assert esperar_aprendizaje(c)["error"] is None
    preset = config.cargar_preset("camiseta")
    assert preset["estilo"]["huellas"], "debe guardar como son tus favoritas"
    # Las opciones ya se puntuan por parecido con las favoritas.
    r = c.post("/api/fotos/camiseta__b/opciones").json()
    assert r["con_favoritas"] and all(o["parecido"] is not None for o in r["opciones"])

    # Subir una foto que te gusta desde la app, verla y quitarla.
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 100, 90)).save(buf, "JPEG")
    r = c.put("/api/ejemplos/camiseta/mi foto.jpg", content=buf.getvalue()).json()
    assert r["nombre"] == "mi_foto.jpg"
    assert "mi_foto.jpg" in c.get("/api/ejemplos").json()["presets"]["camiseta"]
    assert c.get("/img/ejemplo/camiseta/mi_foto.jpg").status_code == 200
    assert c.put("/api/ejemplos/camiseta/roto.jpg", content=b"no es una foto").status_code == 400
    assert c.get("/img/ejemplo/camiseta/..%2F..%2Fsecreto.jpg").status_code in (400, 404)
    assert c.delete("/api/ejemplos/camiseta/mi_foto.jpg").json()["aprendiendo"] is True
    assert "mi_foto.jpg" not in c.get("/api/ejemplos").json()["presets"]["camiseta"]
    # Quitar una favorita vuelve a aprender: hay que esperar, que escribe presets.
    assert esperar_aprendizaje(c)["error"] is None
