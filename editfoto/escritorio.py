"""Arranque de EDITFOTO.exe: ventana propia, servidor local, modelos y auto-actualizacion.

Igual que INDRA HUB: un unico .exe que se actualiza solo desde GitHub Releases.
- Tus fotos y presets: Documentos\\EDITFOTO (nunca se tocan al actualizar).
- Modelos de IA y registro: %LOCALAPPDATA%\\EDITFOTO.

    EDITFOTO.exe                        abre la app
    EDITFOTO.exe --autoprueba r.json    comprobacion sin ventana (la usa GitHub Actions)
    EDITFOTO.exe --apply-update <exe>   uso interno de la actualizacion
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

PUERTO = 8765


def _documentos() -> Path:
    """Carpeta Documentos real (respeta si Windows la tiene en OneDrive o en otro disco)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            documentos = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                              (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            ruta = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(documentos), 0, None, ctypes.byref(ruta)) == 0:
                valor = ruta.value
                ctypes.windll.ole32.CoTaskMemFree(ruta)
                return Path(valor)
        except Exception:
            pass
    return Path.home() / "Documents"


def carpeta_local() -> Path:
    base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else os.path.expanduser("~/.local/share")
    return Path(base or Path.home()) / "EDITFOTO"


def configurar_rutas() -> None:
    """Antes de importar el resto de editfoto: fija donde viven datos y modelos."""
    os.environ.setdefault("EDITFOTO_DATOS", str(_documentos() / "EDITFOTO"))
    os.environ.setdefault("EDITFOTO_MODELOS", str(carpeta_local() / "modelos"))


def redirigir_salida() -> Path:
    """El .exe no tiene consola: los mensajes y errores van a un registro que se puede mandar."""
    registro = carpeta_local() / "registro.txt"
    if sys.stdout is not None and sys.stderr is not None and not getattr(sys, "frozen", False):
        return registro
    registro.parent.mkdir(parents=True, exist_ok=True)
    try:
        if registro.exists() and registro.stat().st_size > 5 * 1024 * 1024:
            registro.replace(registro.with_suffix(".anterior.txt"))
    except OSError:
        pass  # otro proceso lo tiene abierto: se sigue escribiendo en el mismo
    try:
        f = open(registro, "a", encoding="utf-8", buffering=1)
    except OSError:
        f = open(os.devnull, "w", encoding="utf-8")
    f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    sys.stdout = f
    sys.stderr = f
    return registro


_candado = None  # se mantiene mientras viva el proceso


def _ya_abierta() -> bool:
    """True si otra copia de EDITFOTO ya se esta ejecutando (candado con nombre de Windows)."""
    global _candado
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _candado = kernel32.CreateMutexW(None, False, "Local\\EDITFOTO_instancia_unica")
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def _fichero_puerto() -> Path:
    return carpeta_local() / "puerto.txt"


def _servidor_existente(puerto: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/estado", timeout=1) as r:
            return json.loads(r.read()).get("app") == "EDITFOTO"
    except (OSError, ValueError):
        return False


def _puerto_libre(preferido: int) -> int:
    for p in range(preferido, preferido + 30):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def arrancar_servidor(entrada: Path, salida: Path, puerto: int):
    """Servidor en un hilo. Devuelve (servidor_uvicorn, app)."""
    import uvicorn

    from .proyecto import Proyecto
    from .servidor import crear_app

    app = crear_app(Proyecto(entrada, salida))
    # log_config=None: la configuracion de uvicorn falla sin consola (sys.stderr de un .exe).
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning",
                                             log_config=None))
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    limite = time.time() + 30
    while not servidor.started:
        if not hilo.is_alive() or time.time() > limite:
            raise RuntimeError("El servidor interno no ha arrancado")
        time.sleep(0.05)
    return servidor, app


def _recurso(nombre: str) -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    ruta = base / nombre
    return ruta if ruta.exists() else None


def abrir_ventana(url: str, al_abrir=None) -> None:
    """Ventana nativa con la interfaz. Si falta WebView2, se abre el navegador."""
    try:
        import webview

        webview.create_window("EDITFOTO", url, width=1440, height=920, min_size=(1000, 680),
                              background_color="#1E1E1E")
        opciones = {"private_mode": False, "storage_path": str(carpeta_local() / "ventana")}
        icono = _recurso("editfoto.ico")
        if icono:
            opciones["icon"] = str(icono)
        try:
            webview.start(al_abrir, **opciones) if al_abrir else webview.start(**opciones)
        except TypeError:  # pywebview antiguo sin icon/storage_path
            webview.start(al_abrir) if al_abrir else webview.start()
    except Exception as e:  # noqa: BLE001
        print(f"No se pudo abrir la ventana ({e}); se usa el navegador.", flush=True)
        import webbrowser

        webbrowser.open(url)
        if al_abrir:
            threading.Thread(target=al_abrir, daemon=True).start()
        while True:  # sin ventana, la app vive hasta que se pulse Salir en la interfaz
            time.sleep(3600)


def autoprueba(ruta_resultado: str | None) -> int:
    """Comprobacion completa sin ventana. GitHub Actions la ejecuta sobre el .exe recien
    compilado antes de publicarlo: si algo no viaja dentro del .exe, falla aqui y no en tu PC."""
    resultado: dict = {"pasos": {}}
    fallos = []

    def paso(nombre, fn):
        try:
            resultado["pasos"][nombre] = fn() or "ok"
        except Exception as e:  # noqa: BLE001
            from .modelos import texto_error

            resultado["pasos"][nombre] = "ERROR " + texto_error(e)
            fallos.append(nombre)

    def _imports():
        import cv2
        import fastapi  # noqa: F401
        import numpy
        import onnxruntime
        import PIL
        import pillow_heif  # noqa: F401
        import uvicorn  # noqa: F401

        from . import __version__

        assert hasattr(cv2, "ximgproc"), "falta opencv-contrib (cv2.ximgproc)"
        try:
            import webview  # noqa: F401
            ventana = "ok"
        except Exception as e:  # noqa: BLE001
            ventana = f"sin pywebview: {e}"
        return {"editfoto": __version__, "onnxruntime": onnxruntime.__version__, "cv2": cv2.__version__,
                "numpy": numpy.__version__, "pillow": PIL.__version__, "ventana": ventana}

    def _proveedores():
        from . import modelos

        return modelos.proveedores_disponibles()

    def _servidor():
        base = Path(tempfile.mkdtemp(prefix="editfoto_prueba_"))
        puerto = _puerto_libre(PUERTO + 100)
        servidor, _ = arrancar_servidor(base / "entrada", base / "salida", puerto)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/estado", timeout=10) as r:
                estado = json.loads(r.read())
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=10) as r:
                assert b"EDITFOTO" in r.read(), "la interfaz web no viaja en el .exe"
            return {"app": estado.get("app"), "presets": estado.get("presets")}
        finally:
            servidor.should_exit = True

    def _edicion():
        import numpy as np

        from . import config, modelos, pipeline

        img = np.full((600, 800, 3), 0.6, np.float32)
        img[150:450, 250:550] = (0.2, 0.3, 0.6)
        alfa = np.zeros((600, 800), np.float32)
        alfa[150:450, 250:550] = 1
        preset = config.cargar_preset("sudadera")
        info = {}
        if modelos._ruta_destino("birefnet_lite").exists():
            from . import segmentar

            alfa = segmentar.segmentar(img, "birefnet_lite")
            info["recorte"] = "ok (BiRefNet lite)"
            if modelos._ruta_destino("vitmatte").exists() and (alfa > 0.5).sum() > 2000:
                _, texto = segmentar.afinar_bordes(img, alfa)
                info["bordes"] = f"ok (ViTMatte: {texto or 'sin cambios'})"
        capas = pipeline.Capas()
        if modelos._ruta_destino("lama").exists():
            capas.borrar = np.zeros((600, 800), np.float32)
            capas.borrar[290:310, 300:500] = 1
            info["borrado"] = "ok (LaMa)"
        res, datos = pipeline.renderizar(img, alfa, preset, None, capas, None, None)
        assert res.shape[:2] == (preset["lienzo"]["alto"], preset["lienzo"]["ancho"])
        info["render"] = f"ok ({datos.get('segundos', '-')})"

        # Poner la prenda derecha: las referencias tienen que viajar dentro del exe.
        from . import orientacion

        refs = orientacion.referencias_genericas()
        assert refs.shape[0] >= 40, "faltan las referencias de orientacion dentro del exe"
        info["orientacion_refs"] = f"ok ({refs.shape[0]})"
        if modelos._ruta_destino("dinov2").exists():
            k, margen = orientacion.giro_probable(img, alfa)
            info["orientacion"] = f"ok (DINOv2, giro {k}, margen {margen:.3f})"

        # Aprender el fondo usa funciones de OpenCV (alineacion ECC, relleno) que no usa el resto.
        from . import fondos

        yy, xx = np.mgrid[0:300, 0:400].astype(np.float32)
        suelo = np.dstack([0.5 + 0.2 * np.sin(xx / 9 + yy / 40)] * 3).astype(np.float32)
        tapas = [np.zeros((300, 400), bool) for _ in range(3)]
        for k, t in enumerate(tapas):
            t[80:220, 60 + 90 * k:200 + 90 * k] = True
        placa, datos_fondo = fondos.reconstruir([suelo.copy() for _ in tapas], tapas)
        assert placa.shape == suelo.shape and np.isfinite(placa).all()
        assert datos_fondo["alineadas"] == 2, f"la alineacion de fondos no funciona: {datos_fondo}"
        info["fondo"] = f"ok ({datos_fondo['alineadas']} alineadas, relleno {datos_fondo['relleno']})"
        return info

    paso("imports", _imports)
    paso("proveedores", _proveedores)
    paso("servidor", _servidor)
    paso("edicion", _edicion)
    resultado["ok"] = not fallos
    texto = json.dumps(resultado, ensure_ascii=False, indent=1)
    if ruta_resultado:
        Path(ruta_resultado).write_text(texto, encoding="utf-8")
    print(texto, flush=True)
    return 0 if not fallos else 1


def main(argv=None) -> None:
    argv = sys.argv if argv is None else argv
    from . import actualizador

    actualizador.modo_aplicar_si_toca(argv)  # si toca, reemplaza el exe y no vuelve
    configurar_rutas()
    if "--autoprueba" in argv:
        i = argv.index("--autoprueba")
        destino = argv[i + 1] if i + 1 < len(argv) else None
        sys.exit(autoprueba(destino))
    registro = redirigir_salida()
    actualizador.limpiar_restos()

    if _ya_abierta():
        # Ya hay una EDITFOTO (quiza aun arrancando): se espera a su servidor y se abre otra
        # ventana sobre la misma app, en vez de un segundo servidor sobre los mismos ficheros.
        for _ in range(240):
            try:
                puerto = int(_fichero_puerto().read_text().strip())
            except (OSError, ValueError):
                puerto = PUERTO
            if _servidor_existente(puerto):
                abrir_ventana(f"http://127.0.0.1:{puerto}")
                return
            time.sleep(0.5)
        print("Otra EDITFOTO parece abierta pero no responde.", flush=True)
        return

    from . import modelos

    datos = modelos.DATOS
    for sub in ("entrada", "salida", "ejemplos"):
        (datos / "fotos" / sub).mkdir(parents=True, exist_ok=True)
    print(f"EDITFOTO {actualizador.ver.__version__} | datos: {datos} | registro: {registro}", flush=True)
    servidor, app = arrancar_servidor(datos / "fotos" / "entrada", datos / "fotos" / "salida", _puerto_libre(PUERTO))
    app.state.salir = lambda: os._exit(0)
    try:
        _fichero_puerto().write_text(str(servidor.config.port))
    except OSError:
        pass
    modelos.preparar_en_segundo_plano()

    def al_abrir():
        actualizador.comprobar_y_actualizar(lambda: app.state.trabajo.estado["activo"])

    abrir_ventana(f"http://127.0.0.1:{servidor.config.port}", al_abrir)
    servidor.should_exit = True
    os._exit(0)  # cierra hilos de lotes o descargas en curso junto con la ventana


if __name__ == "__main__":
    main()
