"""Reconstruccion del fondo real a partir de ejemplos y aprendizaje por tipo de prenda."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editfoto import aprender, config, fondos, imagen, modelos, pipeline  # noqa: E402


def suelo_de_madera(alto=940, ancho=1240, semilla=1) -> np.ndarray:
    """Fondo con textura (vetas de madera y tablas): una media de color no lo representa."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    vetas = 0.5 + 0.25 * np.sin(xx / 6.0 + 3 * np.sin(yy / 90.0)) + 0.1 * np.sin(xx / 23.0)
    tablas = ((xx // 180) % 2) * 0.08
    ruido = cv2.GaussianBlur(rng.normal(0, 0.05, (alto, ancho)).astype(np.float32), (0, 0), 1.5)
    base = np.clip(vetas + tablas + ruido, 0, 1)[..., None]
    return np.clip(np.array([0.55, 0.38, 0.24], np.float32) * (0.6 + 0.6 * base), 0, 1).astype(np.float32)


def ejemplo_en_suelo(suelo, semilla, forma="sudadera"):
    """Foto de ejemplo: la camara se mueve unos pixeles, cambia algo la exposicion y la prenda
    tapa una zona distinta del suelo. Devuelve (img, prenda, desplazamiento, exposicion)."""
    rng = np.random.default_rng(semilla)
    alto, ancho = 900, 1200
    dx, dy = rng.integers(0, 40, 2)
    expo = float(rng.uniform(0.9, 1.1))
    img = suelo[dy:dy + alto, dx:dx + ancho] * expo
    prenda = np.zeros((alto, ancho), np.uint8)
    cx, cy = ancho // 2 + int(rng.integers(-150, 150)), alto // 2 + int(rng.integers(-80, 80))
    if forma == "sudadera":
        cv2.ellipse(prenda, (cx, cy), (int(rng.integers(150, 260)), int(rng.integers(130, 220))), 0, 0, 360, 1, -1)
    else:  # pantalon: alto y estrecho
        cv2.rectangle(prenda, (cx - 90, cy - 330), (cx + 90, cy + 330), 1, -1)
    prenda = prenda.astype(bool)
    color = np.array(rng.uniform(0.1, 0.9, 3), np.float32)
    img = np.where(prenda[..., None], color, img).astype(np.float32)
    return np.clip(img, 0, 1), prenda, (int(dx), int(dy)), expo


@pytest.fixture
def sin_lama(tmp_path, monkeypatch):
    monkeypatch.setattr(modelos, "CARPETA_MODELOS", tmp_path / "sin_modelos")  # relleno con OpenCV


def test_reconstruye_el_fondo_con_textura(sin_lama):
    suelo = suelo_de_madera()
    datos = [ejemplo_en_suelo(suelo, s) for s in range(8)]
    imgs, prendas = [d[0] for d in datos], [d[1] for d in datos]
    placa, info = fondos.reconstruir(imgs, prendas)
    assert info["fotos_usadas"] == 8 and info["alineadas"] >= 6

    # La placa queda en el encuadre y exposicion de la foto de referencia (la que mas fondo ve).
    r = int(np.argmax([fondos._zona_fondo(p).mean() for p in prendas]))
    (dx, dy), expo = datos[r][2], datos[r][3]
    verdad = np.clip(suelo[dy:dy + 900, dx:dx + 1200] * expo, 0, 1)
    vista = ~np.logical_and.reduce([~fondos._zona_fondo(p) for p in prendas])
    vista = cv2.erode(vista.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    error = np.abs(placa - verdad)[vista].mean()
    assert error < 0.03, error

    # Sin alinear, las vetas se emborronan: la alineacion es lo que da un fondo nitido.
    placa_sin, _ = fondos.reconstruir(imgs, prendas, alinear=False)
    assert np.abs(placa_sin - verdad)[vista].mean() > 1.5 * error
    assert np.isfinite(placa).all() and placa.min() >= 0 and placa.max() <= 1


def test_aprender_por_tipo_crea_presets_y_fondo(tmp_path, monkeypatch, sin_lama):
    monkeypatch.setattr(config, "CARPETA_PRESETS_USUARIO", tmp_path / "datos" / "presets")
    monkeypatch.setattr(modelos, "DATOS", tmp_path / "datos")
    registro = {}

    def segmentar_falso(img, modelo="auto"):
        return registro[round(float(img[::40, ::40].mean()), 4)].astype(np.float32)

    monkeypatch.setattr("editfoto.segmentar.segmentar", segmentar_falso)
    suelo = suelo_de_madera()
    raiz = tmp_path / "ejemplos"
    for tipo, n, forma in (("sudadera", 4, "sudadera"), ("pantalon", 3, "pantalon")):
        (raiz / tipo).mkdir(parents=True)
        for k in range(n):
            img, prenda, _, _ = ejemplo_en_suelo(suelo, 100 * len(tipo) + k, forma)
            ruta = raiz / tipo / f"{k}.jpg"
            imagen.guardar_jpg(img, ruta, 95)
            leida = imagen.reducir(imagen.cargar(ruta), aprender.LADO_EJEMPLOS)
            registro[round(float(leida[::40, ::40].mean()), 4)] = prenda

    presets, resumen = aprender.aprender_por_tipo(raiz, avisar=lambda *_: None)
    por_nombre = {p["nombre"]: p for p in presets}
    assert set(por_nombre) == {"sudadera", "pantalon"}
    # El pantalon es alto y estrecho: ocupa casi todo el alto; la sudadera menos.
    assert por_nombre["pantalon"]["encuadre"]["relleno"] > por_nombre["sudadera"]["encuadre"]["relleno"]
    # Fondo con textura reconstruido y compartido; el preset de sudadera conserva sus ajustes de fabrica.
    fondo = por_nombre["sudadera"]["fondo"]
    assert fondo["tipo"] == "imagen" and fondo == por_nombre["pantalon"]["fondo"]
    assert (tmp_path / "datos" / fondo["imagen"]).exists()
    assert config.cargar_preset("sudadera")["arrugas"]["escala"] == 0.12
    assert resumen["fondo"]["origen"] == "reconstruido"

    # Una foto nueva sale con el suelo de madera, no con fondo liso.
    img, prenda, _, _ = ejemplo_en_suelo(suelo, 999)
    res, _ = pipeline.renderizar(img, prenda.astype(np.float32), config.cargar_preset("sudadera"))
    esquina = res[:150, :150]
    assert esquina.std() > 0.02, "el fondo deberia tener la textura de la madera"


def test_foto_del_fondo_vacio_tiene_prioridad(tmp_path, monkeypatch, sin_lama):
    monkeypatch.setattr(modelos, "DATOS", tmp_path / "datos")
    suelo = suelo_de_madera()
    raiz = tmp_path / "ejemplos"
    raiz.mkdir()
    imagen.guardar_jpg(suelo[:900, :1200], raiz / "fondo.jpg", 95)
    ej = [aprender.Ejemplo(Path("x.jpg"), *ejemplo_en_suelo(suelo, k)[:2],
                           {"fondo": [0.5, 0.4, 0.3], "fondo_uniforme": False}) for k in range(3)]
    cambios, frase, info = aprender.aprender_fondo(ej, raiz, "mi_fondo", avisar=lambda *_: None)
    assert info["origen"] == "foto_vacia" and cambios["tipo"] == "imagen" and "fondo.jpg" in frase
