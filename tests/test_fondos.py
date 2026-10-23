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


def test_fotos_pequenas_e_identicas_se_alinean_sin_moverse(sin_lama):
    """Regresion: con fotos pequenas, el nivel fino ampliaba la imagen y la alineacion divergia."""
    yy, xx = np.mgrid[0:300, 0:400].astype(np.float32)
    suelo = np.dstack([0.5 + 0.2 * np.sin(xx / 9 + yy / 40)] * 3).astype(np.float32)
    tapas = [np.zeros((300, 400), bool) for _ in range(3)]
    for k, t in enumerate(tapas):
        t[80:220, 60 + 90 * k:200 + 90 * k] = True
    placa, info = fondos.reconstruir([suelo.copy() for _ in tapas], tapas)
    assert info["alineadas"] == 2
    assert np.abs(placa - suelo).mean() < 0.002


def moqueta(alto=800, ancho=600, semilla=3) -> np.ndarray:
    """Moqueta gris: textura fina aleatoria y un degradado de luz suave."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:alto, 0:ancho].astype(np.float32)
    grano = cv2.GaussianBlur(rng.normal(0, 0.06, (alto, ancho)).astype(np.float32), (0, 0), 1.2)
    luz = 0.5 + 0.06 * (xx / ancho) - 0.05 * (yy / alto)
    return np.clip(np.dstack([luz + grano] * 3) * np.array([1.0, 0.98, 0.95], np.float32), 0, 1).astype(np.float32)


def test_relleno_de_textura_sin_manchas_ni_decoracion(sin_lama):
    suelo = moqueta()
    img = suelo.copy()
    img[620:800, 150:450] = (0.45, 0.6, 0.85)  # pantalon vaquero de decoracion
    hueco = np.zeros((800, 600), np.uint8)
    cv2.ellipse(hueco, (300, 330), (250, 230), 0, 0, 360, 1, -1)  # prenda grande: ~40 % de la foto
    hueco = hueco.astype(bool)
    img[hueco] = (0.25, 0.15, 0.1)  # la prenda que se borra

    placa = fondos.rellenar_textura(img, hueco)
    dentro = cv2.erode(hueco.astype(np.uint8), np.ones((21, 21), np.uint8)).astype(bool)
    # Luz y color del suelo, no de la prenda borrada ni del vaquero.
    assert np.abs(placa[dentro].mean(0) - suelo[dentro].mean(0)).max() < 0.02
    assert (placa[dentro][:, 2] - placa[dentro][:, 0]).mean() < 0.01, "se ha copiado azul del vaquero"

    def grano(x):
        return np.std((x - cv2.GaussianBlur(x, (0, 0), 3))[..., 1][dentro])

    assert 0.6 < grano(placa) / grano(suelo) < 1.6, "la textura rellenada no se parece a la moqueta"
    # Sin manchas: la luz rellenada varia tan suave como la real.
    def manchas(x):
        return np.std(cv2.GaussianBlur(x, (0, 0), 12)[..., 1][dentro])

    assert manchas(placa) < 2.5 * manchas(suelo) + 0.005
    assert np.array_equal(placa[700:800, 200:400], img[700:800, 200:400]), "la decoracion no se toca"


def test_encuadre_en_caja_deja_sitio_abajo():
    from editfoto import composicion

    alfa = np.zeros((900, 1200), np.float32)
    alfa[100:800, 200:1000] = 1  # prenda casi cuadrada
    _, alfa_l, _ = composicion.encuadrar(np.zeros((900, 1200, 3), np.float32), alfa, (600, 800), 0.84, 0.5, 0.39,
                                         relleno_x=0.91, relleno_y=0.6)
    ys, xs = np.nonzero(alfa_l > 0.5)
    assert ys.max() < 0.39 * 800 + 0.3 * 800 + 2, "la prenda invade la zona de la decoracion"
    assert (ys.max() - ys.min()) / 800 == pytest.approx(0.6, abs=0.01)  # la limita el alto


def test_giro_inicial_del_preset_para_fotos_nuevas(tmp_path, monkeypatch):
    from editfoto.proyecto import Proyecto

    monkeypatch.setattr(config, "CARPETA_PRESETS_USUARIO", tmp_path / "presets")
    config.guardar_preset(config.fusionar(config.cargar_preset("generico"), {"nombre": "chaqueta", "giro_inicial": 3}))
    entrada = tmp_path / "entrada"
    (entrada / "chaqueta").mkdir(parents=True)
    imagen.guardar_jpg(np.full((30, 40, 3), 0.5, np.float32), entrada / "chaqueta" / "a.jpg")
    imagen.guardar_jpg(np.full((30, 40, 3), 0.5, np.float32), entrada / "suelta.jpg")
    p = Proyecto(entrada, tmp_path / "salida")
    assert p.foto("chaqueta__a").ajustes == {"giro90": 3}
    assert p.foto("suelta").ajustes == {}
    assert p.imagen_trabajo("chaqueta__a").shape[:2] == (40, 30)  # ya tumbada a vertical


def test_aprender_de_un_solo_ejemplo_conserva_la_decoracion(tmp_path, monkeypatch, sin_lama):
    monkeypatch.setattr(config, "CARPETA_PRESETS_USUARIO", tmp_path / "datos" / "presets")
    monkeypatch.setattr(modelos, "DATOS", tmp_path / "datos")
    img = moqueta()
    img[620:800, 150:450] = (0.45, 0.6, 0.85)  # vaquero de decoracion
    prenda = np.zeros((800, 600), bool)
    prenda[60:545, 30:575] = True  # chaqueta: 91 % del ancho, 60 % del alto, arriba
    img[prenda] = (0.25, 0.15, 0.1)
    decoracion = np.zeros((800, 600), bool)
    decoracion[620:800, 150:450] = True
    monkeypatch.setattr("editfoto.segmentar.segmentar",
                        lambda im, modelo="auto": (prenda | decoracion).astype(np.float32))
    raiz = tmp_path / "ejemplos"
    (raiz / "chaqueta").mkdir(parents=True)
    imagen.guardar_jpg(img, raiz / "chaqueta" / "favorita.jpg", 95)

    presets, resumen = aprender.aprender_por_tipo(raiz, avisar=lambda *_: None)
    enc = presets[0]["encuadre"]
    assert enc["relleno_x"] == pytest.approx(0.91, abs=0.01) and enc["relleno_y"] == pytest.approx(0.61, abs=0.01)
    assert enc["centro_y"] == pytest.approx(0.38, abs=0.01)
    assert resumen["fondo"]["origen"] == "un_ejemplo"
    placa = imagen.cargar(tmp_path / "datos" / presets[0]["fondo"]["imagen"])
    assert placa[680:780, 200:400, 2].mean() > 0.75, "el vaquero de decoracion debe seguir en el fondo"
    assert np.abs(placa[200:400, 150:450].mean((0, 1)) - img[0:50, 0:600].mean((0, 1))).max() < 0.06
