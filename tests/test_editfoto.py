"""Tests rapidos: la IA de recorte se sustituye por la mascara sintetica conocida.

    python -m pytest tests -q
Para probar tambien los modelos reales (descarga ~450 MB): EDITFOTO_TEST_MODELOS=1 python -m pytest tests -q
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from editfoto import arrugas, color, composicion, config, imagen, mascara, pipeline  # noqa: E402
from sinteticas import foto_sintetica, silueta_sudadera  # noqa: E402

MODELOS = os.environ.get("EDITFOTO_TEST_MODELOS") == "1"


@pytest.fixture
def ia_falsa(monkeypatch):
    """Sustituye BiRefNet: devuelve la mascara de la foto sintetica guardada en un registro."""
    registro = {}

    def segmentar_falso(img, modelo="auto"):
        clave = round(float(img[::50, ::50].mean()), 5)
        return registro[clave]

    monkeypatch.setattr("editfoto.segmentar.segmentar", segmentar_falso)

    def registrar(img, alfa):
        registro[round(float(img[::50, ::50].mean()), 5)] = alfa

    return registrar


def test_limpieza_quita_cable_y_respeta_cordon():
    img, alfa, d = foto_sintetica()
    limpio, prenda = mascara.limpiar(alfa)
    cable_restante = (limpio > 0.5) & d["cable"]
    assert cable_restante.sum() < 0.1 * d["cable"].sum(), "el cable que llega al borde debe desaparecer"
    cordon_fuera = d["cordon"] & ~d["prenda"]
    assert (limpio > 0.5)[cordon_fuera].mean() > 0.9, "el cordon no llega al borde: se conserva"
    assert (limpio > 0.5)[d["prenda"]].mean() > 0.99


def test_arrugas_se_suavizan_y_la_mancha_se_conserva():
    img, alfa, d = foto_sintetica()
    _, prenda = mascara.limpiar(alfa)
    alfa_p = prenda.astype(np.float32)
    salida = arrugas.suavizar(img, alfa_p, fuerza=1.0, escala=0.15, respeto_bordes=0.5)

    zona = cv2.erode(d["prenda"].astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
    zona &= ~cv2.dilate(d["cordon"].astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
    mx, my = d["mancha"]
    zona[my - 40:my + 40, mx - 40:mx + 40] = False

    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]].astype(np.float32)
    onda = np.stack([np.sin(xx / 38 + yy / 55)[zona], np.cos(xx / 38 + yy / 55)[zona], np.ones(zona.sum())], 1)

    def sombras(x):  # amplitud de la onda de arrugas sintetica
        coef = np.linalg.lstsq(onda, imagen.luminancia(x)[zona], rcond=None)[0]
        return np.hypot(coef[0], coef[1])

    def textura(x):
        L = imagen.luminancia(x)
        return np.std((L - cv2.GaussianBlur(L, (0, 0), 2))[zona])

    assert sombras(salida) < 0.5 * sombras(img), "las arrugas deben atenuarse"
    assert textura(salida) > 0.8 * textura(img), "la textura del punto se conserva"
    # Contraste de la mancha respecto a su entorno: se mantiene.
    def contraste_mancha(x):
        dentro = x[my - 6:my + 6, mx - 6:mx + 6].mean(axis=(0, 1))
        anillo = np.concatenate([x[my - 30:my - 20, mx - 30:mx + 30].reshape(-1, 3),
                                 x[my + 20:my + 30, mx - 30:mx + 30].reshape(-1, 3)]).mean(0)
        return np.abs(dentro - anillo).sum()
    assert contraste_mancha(salida) > 0.85 * contraste_mancha(img), "la mancha (defecto) no se borra"
    # Fuera de la prenda no cambia nada.
    fuera = ~cv2.dilate(prenda.astype(np.uint8), np.ones((21, 21), np.uint8)).astype(bool)
    assert np.abs(salida - img)[fuera].max() < 1e-3


def test_proteger_impide_suavizar():
    img, alfa, d = foto_sintetica()
    proteger = np.zeros(alfa.shape, np.float32)
    proteger[300:600, 450:750] = 1
    salida = arrugas.suavizar(img, (alfa > 0.5).astype(np.float32), 1.0, proteger=proteger)
    assert np.abs(salida - img)[320:580, 470:730].max() < 0.02


@pytest.mark.parametrize("girado", [4.0, -3.0])
def test_enderezado_por_simetria(girado):
    m = silueta_sudadera(angulo=girado)
    corregir = composicion.angulo_enderezado(m, 6.0)
    assert abs(corregir + girado) < 0.6, f"esperado {-girado}, obtenido {corregir}"


def test_enderezado_no_toca_prendas_asimetricas():
    m = silueta_sudadera()
    m[:, : m.shape[1] // 2 - 150] = False  # media prenda: no hay simetria fiable
    assert composicion.angulo_enderezado(m, 6.0) == 0.0


def test_encuadre_centra_y_rellena():
    img, alfa, d = foto_sintetica()
    _, alfa_l, info = composicion.encuadrar(img, d["prenda"].astype(np.float32), (1500, 2000), 0.8, 0.5, 0.5)
    ys, xs = np.nonzero(alfa_l > 0.5)
    ancho, alto = xs.max() - xs.min(), ys.max() - ys.min()
    assert max(ancho / 1500, alto / 2000) == pytest.approx(0.8, abs=0.01)
    assert (xs.min() + xs.max()) / 2 == pytest.approx(750, abs=4)
    assert (ys.min() + ys.max()) / 2 == pytest.approx(1000, abs=4)


def test_color_iguala_exposicion_del_mismo_set():
    ref = [0.4, 0.4, 0.4]
    g = color.ganancias({"rgb": [0.28, 0.28, 0.28]}, ref, True, True)
    assert g == pytest.approx([0.4 / 0.28] * 3, rel=0.01)
    # Otro set (fondo de otro color): no se fuerza.
    g2 = color.ganancias({"rgb": [0.5, 0.3, 0.1]}, ref, True, True)
    assert g2 == pytest.approx([1, 1, 1], abs=1e-3)


def test_pipeline_completo(ia_falsa):
    img, alfa, d = foto_sintetica()
    ia_falsa(img, alfa)
    preset = config.cargar_preset("sudadera")
    a, medida = pipeline.analizar(img, preset)
    res, info = pipeline.renderizar(img, a, preset, {"rotacion": 0}, None, medida, None)
    assert res.shape == (2000, 1500, 3)
    esquina = res[:20, :20].reshape(-1, 3).mean(0)
    assert esquina == pytest.approx(imagen.color_hex(preset["fondo"]["color"]), abs=0.01)
    # El cable y el tripode no aparecen: el borde derecho es fondo limpio.
    assert np.abs(res[:, -60:] - imagen.color_hex(preset["fondo"]["color"])).max() < 0.03
    # El color de la prenda se mantiene (azul), sin dominantes.
    centro = res[900:1100, 600:700].reshape(-1, 3).mean(0)
    assert centro[2] > centro[0] + 0.2


def test_proyecto_y_servidor(tmp_path, ia_falsa):
    from fastapi.testclient import TestClient

    from editfoto.proyecto import Proyecto
    from editfoto.servidor import crear_app

    entrada = tmp_path / "entrada"
    (entrada / "sudadera").mkdir(parents=True)
    for i, expo in enumerate([1.0, 0.8, 1.15]):
        img, alfa, _ = foto_sintetica(semilla=i, exposicion=expo)
        imagen.guardar_jpg(img, entrada / "sudadera" / f"foto{i}.jpg", 95)
        ia_falsa(imagen.cargar(entrada / "sudadera" / f"foto{i}.jpg"), alfa)

    p = Proyecto(entrada, tmp_path / "salida")
    assert {f.preset for f in p.lista()} == {"sudadera"}
    p.procesar_lote()
    assert all(f.estado == "lista" for f in p.lista()), [f.error for f in p.lista()]
    assert (tmp_path / "salida" / "sudadera" / "foto0.jpg").exists()
    # La foto subexpuesta se corrige hacia la referencia del lote.
    g = p.foto("sudadera__foto1").info["ganancias_color"]
    assert np.mean(g) > 1.1

    c = TestClient(crear_app(p))
    assert c.get("/api/estado").status_code == 200
    r = c.post("/api/fotos/sudadera__foto0/render", json={"ajustes": {"preset": {"arrugas": {"fuerza": 0.2}}}})
    assert r.status_code == 200 and r.json()["version"] == 2
    lienzo = Image.new("RGBA", (300, 225), (0, 0, 0, 0))
    lienzo.paste((255, 0, 0, 255), (0, 0, 60, 60))
    buf = io.BytesIO()
    lienzo.save(buf, "PNG")
    r = c.put("/api/fotos/sudadera__foto0/pincel/restar", content=buf.getvalue(), headers={"content-type": "image/png"})
    assert r.json()["pinceles"]["restar"] is True
    assert c.get("/img/sudadera__foto0/mascara").status_code == 200
    assert c.delete("/api/fotos/sudadera__foto0/pincel/restar").json()["pinceles"]["restar"] is False
    assert c.post("/api/fotos/sudadera__foto0/aprobar", json={"aprobada": True}).json()["aprobada"] is True
    assert c.get("/api/fotos/no_existe").status_code == 404

    # El estado sobrevive a reiniciar la app.
    p2 = Proyecto(entrada, tmp_path / "salida")
    assert p2.foto("sudadera__foto0").aprobada is True
    assert p2.foto("sudadera__foto0").ajustes["preset"]["arrugas"]["fuerza"] == 0.2


@pytest.mark.skipif(not MODELOS, reason="EDITFOTO_TEST_MODELOS=1 para probar los modelos reales")
def test_modelos_reales():
    from editfoto import inpaint, segmentar

    img, _, d = foto_sintetica()
    alfa = segmentar.segmentar(img)
    iou = ((alfa > 0.5) & d["prenda"]).sum() / ((alfa > 0.5) | d["prenda"]).sum()
    assert iou > 0.8
    pincel = np.zeros(alfa.shape, np.float32)
    mx, my = d["mancha"]
    pincel[my - 20:my + 20, mx - 20:mx + 20] = 1
    limpia = inpaint.borrar(img, pincel)
    assert np.abs(limpia[my - 5:my + 5, mx - 5:mx + 5] - img[my - 5:my + 5, mx - 5:mx + 5]).max() > 0.05
