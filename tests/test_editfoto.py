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
    lx, ly = d["logo"]
    zona[ly - 80:ly + 80, lx - 130:lx + 130] = False

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

    def contraste_logo(x):
        L = imagen.luminancia(x)
        dentro = L[ly - 25:ly + 25, lx - 80:lx + 80].mean()
        fuera = np.concatenate([L[ly - 65:ly - 45, lx - 80:lx + 80].ravel(), L[ly + 45:ly + 65, lx - 80:lx + 80].ravel()])
        return dentro - fuera.mean()
    assert contraste_logo(salida) > 0.9 * contraste_logo(img), "el logo (estampado) no se difumina"
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


@pytest.mark.parametrize("lienzo", [(1500, 2000), (600, 800)])  # ampliar y reducir mucho (prerreduccion)
def test_encuadre_centra_y_rellena(lienzo):
    img, alfa, d = foto_sintetica()
    _, alfa_l, info = composicion.encuadrar(img, d["prenda"].astype(np.float32), lienzo, 0.8, 0.5, 0.5)
    if lienzo[0] == 600:
        assert info["escala"] < 0.75, "este caso debe pasar por la reduccion previa"
    ys, xs = np.nonzero(alfa_l > 0.5)
    ancho, alto = xs.max() - xs.min(), ys.max() - ys.min()
    assert max(ancho / lienzo[0], alto / lienzo[1]) == pytest.approx(0.8, abs=0.01)
    assert (xs.min() + xs.max()) / 2 == pytest.approx(lienzo[0] / 2, abs=3)
    assert (ys.min() + ys.max()) / 2 == pytest.approx(lienzo[1] / 2, abs=3)


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


def test_si_la_grafica_falla_se_repite_en_cpu(monkeypatch, tmp_path):
    from editfoto import modelos

    monkeypatch.setattr(modelos, "CARPETA_MODELOS", tmp_path)
    completo = modelos._ruta_destino("birefnet")
    completo.parent.mkdir(parents=True)
    completo.write_bytes(b"x")  # el modelo completo ya esta descargado

    class SesionGraficaRota:
        def get_providers(self):
            return ["DmlExecutionProvider", "CPUExecutionProvider"]

        def run(self, *_):
            raise RuntimeError("operacion no soportada")

    class SesionCpu:
        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, *_):
            return ["ok"]

    def sesion_falsa(nombre):
        return SesionCpu() if nombre in modelos._solo_cpu else SesionGraficaRota()

    monkeypatch.setattr(modelos, "sesion", sesion_falsa)
    monkeypatch.setattr(modelos, "_solo_cpu", set())
    monkeypatch.setattr(modelos, "hay_gpu", lambda: True)
    assert modelos.modelo_segmentacion() == "birefnet"
    assert modelos.ejecutar("birefnet", {}) == ["ok"]
    assert "birefnet" in modelos._solo_cpu
    # A partir de ahi se usa el modelo ligero, que es el adecuado para la CPU.
    assert modelos.modelo_segmentacion() == "birefnet_lite"


def test_error_de_windows_en_espanol_se_lee():
    from editfoto import modelos

    crudo = 'LoadLibrary failed with error 126 "No se puede encontrar el m\u00f3dulo especificado."'.encode("cp1252")
    try:
        crudo.decode("utf-8")
    except UnicodeDecodeError as e:
        texto = modelos.texto_error(e)
    assert "m\u00f3dulo especificado" in texto and "126" in texto
    assert modelos.texto_error(ValueError("otro")) == "ValueError: otro"


def test_presets_propios_sobreviven_a_una_actualizacion(tmp_path, monkeypatch):
    import shutil

    programa_v1 = tmp_path / "app_v1" / "presets"
    shutil.copytree(config.CARPETA_PRESETS, programa_v1)
    propios = tmp_path / "datos" / "presets"
    monkeypatch.setattr(config, "CARPETA_PRESETS", programa_v1)
    monkeypatch.setattr(config, "CARPETA_PRESETS_USUARIO", propios)

    sudadera = config.cargar_preset("sudadera")
    sudadera["arrugas"]["fuerza"] = 0.93
    ruta = config.guardar_preset(sudadera)
    assert ruta.parent == propios
    config.guardar_preset(config.fusionar(config.cargar_preset("generico"), {"nombre": "mi_estilo"}))

    # La actualizacion reemplaza la carpeta del programa entera (con un preset nuevo).
    programa_v2 = tmp_path / "app_v2" / "presets"
    shutil.copytree(programa_v1, programa_v2)
    (programa_v2 / "abrigo.json").write_text('{"descripcion": "nuevo"}', encoding="utf-8")
    shutil.rmtree(tmp_path / "app_v1")
    monkeypatch.setattr(config, "CARPETA_PRESETS", programa_v2)

    assert config.cargar_preset("sudadera")["arrugas"]["fuerza"] == 0.93
    assert config.cargar_preset("pantalon")["arrugas"]["escala"] == 0.12  # del programa
    assert {"mi_estilo", "abrigo", "sudadera"} <= set(config.listar_presets())


def test_giro_de_90_grados_se_conserva(tmp_path, ia_falsa):
    from fastapi.testclient import TestClient

    from editfoto.proyecto import Proyecto
    from editfoto.servidor import crear_app

    entrada = tmp_path / "entrada"
    entrada.mkdir()
    img, alfa, _ = foto_sintetica()
    tumbada = np.ascontiguousarray(np.rot90(img, 1))  # foto que llega girada
    imagen.guardar_jpg(tumbada, entrada / "tumbada.jpg", 95)
    ia_falsa(imagen.cargar(entrada / "tumbada.jpg"), np.ascontiguousarray(np.rot90(alfa, 1)))
    p = Proyecto(entrada, tmp_path / "salida")
    c = TestClient(crear_app(p))
    f = c.post("/api/fotos/tumbada/render", json={}).json()
    assert (f["ancho"], f["alto"]) == (900, 1200)

    # Un trazo de pincel en la esquina superior izquierda de la foto tumbada.
    capa = Image.new("L", (900, 1200), 0)
    capa.paste(255, (0, 0, 100, 50))
    buf = io.BytesIO()
    capa.save(buf, "PNG")
    c.put("/api/fotos/tumbada/pincel/proteger", content=buf.getvalue(), headers={"content-type": "image/png"})

    f = c.post("/api/fotos/tumbada/girar", json={"sentido": 1}).json()
    assert f["ajustes"]["giro90"] == 1 and (f["ancho"], f["alto"]) == (1200, 900) and f["estado"] == "lista"
    # La foto de trabajo ya esta derecha y el pincel ha girado con ella (ahora arriba a la derecha).
    assert np.abs(p.imagen_trabajo("tumbada") - img).mean() < 0.02
    girada = np.asarray(Image.open(p.ruta_pincel("tumbada", "proteger")))
    assert girada.shape == (900, 1200) and girada[:100, -50:].mean() > 200 and girada[:100, :50].mean() < 5

    # Restablecer los ajustes no deshace el giro, y se conserva al reabrir la app.
    c.post("/api/fotos/tumbada/render", json={"ajustes": {"giro90": 3, "rotacion": 4}})
    f = c.post("/api/fotos/tumbada/render", json={"ajustes": {}, "reemplazar": True}).json()
    assert f["ajustes"] == {"giro90": 1}
    assert Proyecto(entrada, tmp_path / "salida").foto("tumbada").ajustes["giro90"] == 1
    # Cuatro giros a la derecha vuelven al principio.
    for _ in range(3):
        f = c.post("/api/fotos/tumbada/girar", json={"sentido": 1}).json()
    assert f["ajustes"]["giro90"] == 0 and (f["ancho"], f["alto"]) == (900, 1200)


def test_pulir_bordes_quita_pelos_de_alfombra_y_respeta_el_puno():
    """Pelos claros de la alfombra que tapan el borde de una prenda oscura se quitan; un puno
    del mismo color que el suelo (pieza grande, de la prenda) se queda."""
    rng = np.random.default_rng(3)
    h, w = 700, 700
    suelo = np.clip(0.8 + rng.normal(0, 0.03, (h, w, 1)), 0, 1) * np.array([1.0, 0.95, 0.85], np.float32)
    img = suelo.astype(np.float32).copy()
    prenda = np.zeros((h, w), bool)
    prenda[100:560, 120:580] = True
    img[prenda] = (0.22, 0.15, 0.12)  # sudadera marron oscura
    puno = np.zeros((h, w), bool)
    puno[500:560, 120:300] = True  # puno claro, del color del suelo, de 60 px de alto
    img[puno] = suelo[puno]
    pelos = np.zeros((h, w), np.uint8)
    for x in range(330, 560, 23):  # hebras que entran desde abajo
        cv2.line(pelos, (x, 575), (x + 6, 551), 1, 2)  # entran ~2 % del tamano, como en la foto real
    pelos = pelos.astype(bool) & prenda
    img[pelos] = suelo[pelos]
    alfa = prenda.astype(np.float32)  # el recorte se ha tragado los pelos como prenda

    img2, alfa2, info = mascara.pulir_bordes(img, alfa)
    assert alfa2[puno].mean() > 0.99, "el puno claro es prenda"
    assert (alfa2[pelos] > 0.5).mean() > 0.95, "lo tapado sigue siendo prenda (sin mordiscos)"
    # Donde estaban los pelos ahora hay color de prenda, no de alfombra.
    assert np.abs(img2[pelos] - np.array([0.22, 0.15, 0.12])).max(axis=1).mean() < 0.08
    assert np.array_equal(img2[150:450, 200:500], img[150:450, 200:500]), "dentro de la prenda no se toca"


def test_pulir_bordes_no_borra_el_tope_de_la_cremallera():
    """Una pieza maciza y clara en el borde (tope metalico) no es pelusa: se queda."""
    h, w = 600, 600
    img = np.full((h, w, 3), (0.78, 0.74, 0.66), np.float32)  # alfombra beige lisa
    prenda = np.zeros((h, w), bool)
    prenda[80:500, 100:500] = True
    img[prenda] = (0.2, 0.14, 0.11)
    tope = np.zeros((h, w), bool)
    tope[484:500, 292:308] = True  # 16 x 16 px, plateado, pegado al bajo
    img[tope] = (0.72, 0.72, 0.7)
    _, alfa2, _ = mascara.pulir_bordes(img, prenda.astype(np.float32))
    assert alfa2[tope].mean() > 0.99


def test_refinar_bordes_arregla_el_mordisco_y_descarta_zonas_malas(monkeypatch):
    from editfoto import segmentar

    img = np.full((800, 800, 3), 0.8, np.float32)
    prenda = np.zeros((800, 800), bool)
    prenda[150:650, 200:600] = True
    img[prenda] = 0.2
    con_mordisco = prenda.copy()
    con_mordisco[625:650, 575:600] = False  # la esquina del puno que el recorte general pierde (5 % del tamano)

    # A mas resolucion el "modelo" ve bien la prenda...
    monkeypatch.setattr(segmentar, "segmentar", lambda im, modelo="auto": (im.mean(axis=2) < 0.5).astype(np.float32))
    alfa, zonas = segmentar.refinar_bordes(img, con_mordisco.astype(np.float32))
    assert zonas > 0 and alfa[625:650, 575:600].mean() > 0.95
    assert np.abs(alfa - prenda).mean() < 0.002  # fuera de la esquina, nada cambia

    # ...pero si en una zona se confunde (sin el resto de la foto), esa zona no se usa.
    monkeypatch.setattr(segmentar, "segmentar", lambda im, modelo="auto": np.zeros(im.shape[:2], np.float32))
    alfa, zonas = segmentar.refinar_bordes(img, con_mordisco.astype(np.float32))
    assert zonas == 0 and np.array_equal(alfa, con_mordisco.astype(np.float32))
