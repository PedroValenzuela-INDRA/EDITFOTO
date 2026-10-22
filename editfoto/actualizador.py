"""Auto-actualizacion desde GitHub Releases (mismo mecanismo que INDRA HUB, solo stdlib).

- Consulta la API publica del repo de releases (sin token ni login).
- Si hay version mas nueva, descarga el .exe AL LADO del actual como
  "<nombre>.new.exe" (no a %TEMP%, que algunos antivirus bloquean).
- Reemplazo sin scripts: lanza el .exe nuevo con "--apply-update <exe actual>";
  ese proceso espera a que el viejo se cierre, se copia encima, relanza la app y
  termina. Al arrancar se limpian los restos "<nombre>.new.exe".
- Guarda las notas de la version para ensenar "Novedades" tras reiniciar.

Diferencia con INDRA HUB: aqui NUNCA se desactiva la verificacion del certificado.
Alli existe para una red corporativa que inspecciona TLS; en casa solo abriria la
puerta a que alguien en la red te colara un .exe. Python en Windows ya confia en
los certificados del sistema, asi que los antivirus que inspeccionan HTTPS siguen
funcionando.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import version as ver

FLAG_APLICAR = "--apply-update"
API = "https://api.github.com"
_CABECERAS = {"User-Agent": f"{ver.APP_NAME}/{ver.__version__}", "Accept": "application/vnd.github+json"}
TIEMPO_CONSULTA = 8
TIEMPO_DESCARGA = 900

_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000

# Estado que la interfaz consulta (GET /api/actualizacion).
ESTADO: dict = {"fase": "inactivo", "version": None, "progreso": 0, "mensaje": ""}


def es_exe() -> bool:
    """True si corremos como EDITFOTO.exe (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def ruta_exe() -> Path:
    return Path(sys.executable).resolve()


def carpeta_config() -> Path:
    base = os.environ.get("APPDATA") if sys.platform == "win32" else os.path.expanduser("~/.config")
    carpeta = Path(base or os.path.expanduser("~")) / "EDITFOTO"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


class Actualizacion:
    def __init__(self, version: str, notas: str, url: str | None, tamano: int, pagina: str):
        self.version, self.notas, self.url, self.tamano, self.pagina = version, notas or "", url, tamano, pagina

    def __repr__(self):
        return f"<Actualizacion {self.version} url={bool(self.url)}>"


def _abrir(url: str, tiempo: float):
    return urllib.request.urlopen(urllib.request.Request(url, headers=_CABECERAS), timeout=tiempo)


def ultima_release(tiempo: float = TIEMPO_CONSULTA) -> dict | None:
    url = f"{API}/repos/{ver.RELEASES_OWNER}/{ver.RELEASES_REPO}/releases/latest"
    try:
        with _abrir(url, tiempo) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, TimeoutError, OSError):
        return None


def _elegir_asset(release: dict) -> dict | None:
    assets = release.get("assets") or []
    for a in assets:
        if a.get("name") == ver.ASSET_NAME:
            return a
    for a in assets:
        if str(a.get("name", "")).lower().endswith(".exe"):
            return a
    return None


def buscar_actualizacion(tiempo: float = TIEMPO_CONSULTA, release: dict | None = None) -> Actualizacion | None:
    """Actualizacion si hay una version mas nueva publicada; None si al dia, sin red o error."""
    release = release if release is not None else ultima_release(tiempo)
    if not release or release.get("draft"):
        return None
    tag = release.get("tag_name") or release.get("name") or ""
    if not tag or not ver.es_mas_nueva(tag):
        return None
    asset = _elegir_asset(release)
    return Actualizacion(tag.lstrip("vV"), release.get("body", ""),
                         asset.get("browser_download_url") if asset else None,
                         int(asset.get("size", 0)) if asset else 0, release.get("html_url", ""))


def _ruta_nueva() -> Path:
    actual = ruta_exe()
    return actual.with_name(actual.stem + ".new.exe")


def descargar(url: str, destino: Path | None = None, progreso=None, tiempo: float = TIEMPO_DESCARGA) -> Path:
    """Descarga a un .part y lo renombra al final (nunca deja un .exe a medias)."""
    destino = Path(destino or _ruta_nueva())
    parcial = destino.with_name(destino.name + ".part")
    parcial.unlink(missing_ok=True)
    with _abrir(url, tiempo) as r, open(parcial, "wb") as f:
        total = int(r.headers.get("Content-Length", 0) or 0)
        hecho = 0
        while bloque := r.read(256 * 1024):
            f.write(bloque)
            hecho += len(bloque)
            if progreso:
                try:
                    progreso(hecho, total)
                except Exception:
                    pass
    if total and hecho != total:
        parcial.unlink(missing_ok=True)
        raise OSError(f"Descarga incompleta ({hecho} de {total} bytes)")
    destino.unlink(missing_ok=True)
    os.replace(parcial, destino)
    return destino


def guardar_novedades(version: str, notas: str) -> None:
    try:
        (carpeta_config() / "novedades.json").write_text(
            json.dumps({"version": version, "notas": notas or ""}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def leer_novedades(version: str = ver.__version__) -> str | None:
    """Notas de la version recien instalada (una sola vez), o None."""
    ruta = carpeta_config() / "novedades.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if ver.version_tuple(datos.get("version", "")) != ver.version_tuple(version):
            return None
        ruta.unlink(missing_ok=True)
        return datos.get("notas", "")
    except (OSError, ValueError):
        return None


def _lanzar_desacoplado(args, carpeta=None):
    flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen([str(a) for a in args], creationflags=flags, close_fds=True,
                            cwd=str(carpeta) if carpeta else None)


def aplicar_y_reiniciar(exe_nuevo: Path) -> None:
    """Lanza el .exe nuevo en modo aplicador y cierra este proceso. No retorna."""
    if not es_exe():
        raise RuntimeError("La auto-actualizacion solo funciona en EDITFOTO.exe.")
    nuevo = Path(exe_nuevo).resolve()
    if not nuevo.exists():
        raise RuntimeError("No se encuentra el ejecutable descargado.")
    _lanzar_desacoplado([nuevo, FLAG_APLICAR, ruta_exe()], nuevo.parent)
    os._exit(0)


def modo_aplicar_si_toca(argv=None) -> None:
    """Si este proceso es el '<nombre>.new.exe' lanzado con --apply-update, hace el cambio y
    termina (no retorna). Llamar al principio, antes de abrir ventanas."""
    argv = sys.argv if argv is None else argv
    if FLAG_APLICAR not in argv:
        return
    try:
        destino = Path(argv[argv.index(FLAG_APLICAR) + 1]).resolve()
    except (IndexError, ValueError):
        return
    yo = ruta_exe()
    limite = time.time() + 120
    copiado = False
    while time.time() < limite:
        try:
            shutil.copy2(yo, destino)
            copiado = True
            break
        except OSError:
            time.sleep(0.4)  # el exe viejo aun no ha soltado el fichero
    try:
        _lanzar_desacoplado([destino], destino.parent)
    except OSError:
        pass
    os._exit(0 if copiado else 1)


def limpiar_restos() -> None:
    """Borra '<nombre>.new.exe' y descargas a medias de actualizaciones anteriores."""
    if not es_exe():
        return
    nuevo = _ruta_nueva()

    def _borrar():
        for _ in range(15):
            pendientes = False
            for p in (nuevo, nuevo.with_name(nuevo.name + ".part")):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pendientes = True
            if not pendientes:
                return
            time.sleep(1.0)

    threading.Thread(target=_borrar, daemon=True).start()


def comprobar_y_actualizar(trabajo_activo=lambda: False) -> None:
    """Al abrir la app: si hay version nueva, la descarga y reinicia sola (como INDRA HUB).
    Sin red, en modo desarrollo o con un lote en marcha, la app sigue sin mas."""
    if not es_exe():
        ESTADO.update(fase="desarrollo", mensaje="Actualizaciones desactivadas fuera del .exe")
        return
    try:
        ESTADO.update(fase="buscando")
        info = buscar_actualizacion()
        if not info or not info.url:
            ESTADO.update(fase="al_dia")
            return
        ESTADO.update(fase="detectada", version=info.version, progreso=0)
        time.sleep(1.2)  # que se pueda leer el aviso

        def _progreso(hecho, total):
            if total:
                ESTADO["progreso"] = hecho * 100 // total

        ESTADO["fase"] = "descargando"
        ruta = descargar(info.url, progreso=_progreso)
        guardar_novedades(info.version, info.notas)
        while trabajo_activo():  # no cortar un procesado por lotes a medias
            ESTADO.update(fase="esperando", mensaje="Se instalara al terminar el procesado")
            time.sleep(2)
        ESTADO.update(fase="instalando", progreso=100)
        time.sleep(1.8)
        aplicar_y_reiniciar(ruta)
    except Exception as e:  # noqa: BLE001 - nunca impedir que la app arranque
        from .modelos import texto_error

        ESTADO.update(fase="error", mensaje=f"Actualizacion omitida: {texto_error(e)}")
