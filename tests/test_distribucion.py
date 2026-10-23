"""Tests de la distribucion: version, actualizador, descarga de modelos y notas de version."""

from __future__ import annotations

import http.server
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from editfoto import actualizador, modelos, version  # noqa: E402


class _Servidor(http.server.BaseHTTPRequestHandler):
    """Sirve un fichero en memoria con soporte de Range (como el CDN de HuggingFace)."""
    datos = b""
    cortar_en = None  # simula una descarga cortada

    def do_GET(self):  # noqa: N802
        inicio = 0
        rango = self.headers.get("Range")
        if rango:
            inicio = int(rango.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        cuerpo = self.datos[inicio:]
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        if self.cortar_en is not None and not rango:
            self.wfile.write(cuerpo[: self.cortar_en])
            return
        self.wfile.write(cuerpo)

    def log_message(self, *a):
        pass


@pytest.fixture
def servidor_http():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def test_comparar_versiones():
    assert version.version_tuple("v1.2") == (1, 2, 0)
    assert version.version_tuple("0.10.1-beta") == (0, 10, 1)
    assert version.es_mas_nueva("v0.10.0", "0.9.9")
    assert not version.es_mas_nueva("0.2.0", "0.2.0")
    assert not version.es_mas_nueva("v0.1.9", "0.2.0")


def test_buscar_actualizacion_elige_el_exe():
    release = {"tag_name": "v99.0.0", "body": "Notas", "html_url": "x",
               "assets": [{"name": "otro.zip", "browser_download_url": "z", "size": 1},
                          {"name": "EDITFOTO.exe", "browser_download_url": "https://e/EDITFOTO.exe", "size": 5}]}
    info = actualizador.buscar_actualizacion(release=release)
    assert info.version == "99.0.0" and info.url.endswith("EDITFOTO.exe") and info.tamano == 5
    assert actualizador.buscar_actualizacion(release={"tag_name": "v0.0.1", "assets": []}) is None
    assert actualizador.buscar_actualizacion(release={"tag_name": "v99.0.0", "draft": True}) is None


def test_descarga_del_exe_no_deja_ficheros_a_medias(servidor_http, tmp_path):
    _Servidor.datos, _Servidor.cortar_en = b"MZ" + b"x" * 100_000, None
    url = f"http://127.0.0.1:{servidor_http.server_port}/EDITFOTO.exe"
    vistos = []
    destino = actualizador.descargar(url, tmp_path / "EDITFOTO.new.exe", lambda h, t: vistos.append((h, t)))
    assert destino.read_bytes() == _Servidor.datos and vistos[-1] == (len(_Servidor.datos),) * 2
    assert not (tmp_path / "EDITFOTO.new.exe.part").exists()


def test_novedades_se_ensenan_una_vez(tmp_path, monkeypatch):
    monkeypatch.setattr(actualizador, "carpeta_config", lambda: tmp_path)
    actualizador.guardar_novedades(version.__version__, "- Cosa nueva")
    assert actualizador.leer_novedades() == "- Cosa nueva"
    assert actualizador.leer_novedades() is None


def test_fuera_del_exe_no_se_actualiza():
    actualizador.comprobar_y_actualizar()
    assert actualizador.ESTADO["fase"] == "desarrollo"


def test_descarga_de_modelos_se_reanuda(servidor_http, tmp_path, monkeypatch):
    datos = bytes(range(256)) * 4000
    _Servidor.datos, _Servidor.cortar_en = datos, 300_000
    destino = tmp_path / "modelo.onnx"
    url = f"http://127.0.0.1:{servidor_http.server_port}/modelo.onnx"
    with pytest.raises(OSError):
        modelos._descargar_fichero(url, destino)  # se corta a mitad
    assert not destino.exists() and destino.with_name("modelo.onnx.part").stat().st_size == 300_000
    _Servidor.cortar_en = None
    modelos._descargar_fichero(url, destino)  # sigue donde se quedo
    assert destino.read_bytes() == datos


def test_mientras_baja_el_modelo_grande_se_usa_el_lite(tmp_path, monkeypatch):
    monkeypatch.setattr(modelos, "CARPETA_MODELOS", tmp_path)
    monkeypatch.setattr(modelos, "hay_gpu", lambda: True)
    monkeypatch.setattr(modelos, "_solo_cpu", set())
    assert modelos.modelo_segmentacion() == "birefnet_lite"
    completo = modelos._ruta_destino("birefnet")
    completo.parent.mkdir(parents=True)
    completo.write_bytes(b"x")
    assert modelos.modelo_segmentacion() == "birefnet"
    assert modelos.estado_modelos()["faltan"] == ["birefnet_lite", "dinov2", "vitmatte", "lama"]


def test_notas_de_version_salen_del_changelog():
    spec = importlib.util.spec_from_file_location("notas_version", RAIZ / ".github" / "notas_version.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    texto = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    notas = mod.notas(version.__version__, texto)
    assert notas, f"CHANGELOG.md no tiene la entrada de v{version.__version__}"
    assert mod.notas("9.9.9", texto) is None
