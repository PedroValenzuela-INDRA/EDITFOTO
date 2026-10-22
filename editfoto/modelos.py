"""Descarga y carga de los modelos ONNX (desde HuggingFace, en local).

Se elige automaticamente el mejor acelerador disponible:
CUDA (NVIDIA) > DirectML (cualquier GPU en Windows) > CoreML (Mac) > CPU.
"""

from __future__ import annotations

import os
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Por defecto todo queda dentro de la carpeta de la app. El lanzador (EDITFOTO.exe) separa
# el codigo, que se reemplaza en cada actualizacion, de los modelos y de tus datos.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_MODELOS = Path(os.environ.get("EDITFOTO_MODELOS", RAIZ / "modelos"))
# Fotos y presets propios: nunca se tocan al actualizar.
DATOS = Path(os.environ.get("EDITFOTO_DATOS", RAIZ))


@dataclass(frozen=True)
class ModeloInfo:
    repo: str
    fichero: str
    descripcion: str
    licencia: str


MODELOS = {
    # Recorte de la prenda. "lite" va bien en CPU; "completo" da bordes algo mejores con GPU.
    "birefnet_lite": ModeloInfo("onnx-community/BiRefNet_lite-ONNX", "onnx/model.onnx",
                                "BiRefNet lite (recorte, rapido)", "MIT"),
    "birefnet": ModeloInfo("onnx-community/BiRefNet-ONNX", "onnx/model.onnx",
                           "BiRefNet completo (recorte, mas preciso, recomendado con GPU)", "MIT"),
    # Borrado de objetos marcados con el pincel.
    "lama": ModeloInfo("Carve/LaMa-ONNX", "lama_fp32.onnx", "LaMa (borrar objetos)", "Apache-2.0"),
}

_sesiones: dict[str, object] = {}
_cerrojo = threading.Lock()
_solo_cpu: set[str] = set()  # modelos con los que la tarjeta grafica ha fallado en esta sesion


def texto_error(e: BaseException) -> str:
    """Mensaje legible de un error.

    En Windows en espanol, ONNX Runtime pasa a Python mensajes del sistema en la
    codificacion de Windows (p. ej. "No se puede encontrar el m\xf3dulo especificado")
    y Python falla al leerlos como UTF-8. Aqui se recupera el texto original.
    """
    if isinstance(e, UnicodeDecodeError) and isinstance(e.object, (bytes, bytearray)):
        crudo = bytes(e.object)
        for codificacion in ("mbcs", "cp1252", "latin-1"):
            try:
                return "Error del sistema: " + crudo.decode(codificacion).strip()
            except (LookupError, UnicodeDecodeError):
                continue
    return f"{type(e).__name__}: {e}"


# Progreso de la descarga de modelos, para la interfaz (GET /api/modelos).
DESCARGA: dict = {"activa": False, "modelo": None, "descripcion": "", "hecho": 0, "total": 0, "error": None}
_cerrojo_descarga = threading.Lock()


def _ruta_destino(nombre: str) -> Path:
    return CARPETA_MODELOS / nombre / MODELOS[nombre].fichero


def _descargar_fichero(url: str, destino: Path) -> None:
    """Descarga con reanudacion: si se corta, la siguiente vez sigue donde se quedo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part")
    ya = parcial.stat().st_size if parcial.exists() else 0
    cabeceras = {"User-Agent": "EDITFOTO"}
    if ya:
        cabeceras["Range"] = f"bytes={ya}-"
    with urllib.request.urlopen(urllib.request.Request(url, headers=cabeceras), timeout=60) as r:
        if r.status != 206:  # el servidor no reanuda: se empieza de cero
            ya = 0
        total = ya + int(r.headers.get("Content-Length") or 0)
        DESCARGA.update(hecho=ya, total=total)
        with open(parcial, "ab" if ya else "wb") as f:
            while bloque := r.read(1 << 20):
                f.write(bloque)
                DESCARGA["hecho"] += len(bloque)
    if total and parcial.stat().st_size != total:
        raise OSError(f"Descarga incompleta de {destino.name}: {parcial.stat().st_size} de {total} bytes")
    os.replace(parcial, destino)


def ruta_modelo(nombre: str, descargar: bool = True) -> Path:
    destino = _ruta_destino(nombre)
    if destino.exists():
        return destino
    if not descargar:
        raise FileNotFoundError(f"Falta el modelo {nombre}. Ejecuta: python -m editfoto descargar-modelos")
    info = MODELOS[nombre]
    with _cerrojo_descarga:  # la descarga en segundo plano y una foto no bajan lo mismo a la vez
        if destino.exists():
            return destino
        print(f"Descargando {info.descripcion} desde HuggingFace ({info.repo})...", flush=True)
        DESCARGA.update(activa=True, modelo=nombre, descripcion=info.descripcion, hecho=0, total=0, error=None)
        try:
            _descargar_fichero(f"https://huggingface.co/{info.repo}/resolve/main/{info.fichero}", destino)
        finally:
            DESCARGA["activa"] = False
    return destino


def modelos_necesarios() -> list[str]:
    # Primero los pequenos, para poder trabajar mientras baja el grande.
    return ["birefnet_lite", "lama"] + (["birefnet"] if hay_gpu() else [])


def estado_modelos() -> dict:
    faltan = [n for n in modelos_necesarios() if not _ruta_destino(n).exists()]
    return dict(DESCARGA, listos=not faltan, faltan=faltan)


def preparar_en_segundo_plano() -> threading.Thread:
    """Descarga los modelos que falten sin bloquear la app (la primera vez son ~1,3 GB con GPU)."""
    def _preparar():
        try:
            for n in modelos_necesarios():
                ruta_modelo(n)
        except Exception as e:  # noqa: BLE001 - se ensena en la interfaz
            DESCARGA["error"] = texto_error(e)

    hilo = threading.Thread(target=_preparar, daemon=True)
    hilo.start()
    return hilo


def proveedores_disponibles() -> list[str]:
    import onnxruntime as ort

    return ort.get_available_providers()


def proveedores_preferidos() -> list:
    """Lista de proveedores para ONNX Runtime, del mas rapido al mas lento."""
    import onnxruntime as ort

    if hasattr(ort, "preload_dlls"):
        # onnxruntime-gpu instalado con [cuda,cudnn] trae las DLL por pip.
        try:
            ort.preload_dlls()
        except Exception:
            pass
    disponibles = ort.get_available_providers()
    preferidos = []
    if "CUDAExecutionProvider" in disponibles:
        preferidos.append("CUDAExecutionProvider")
    if "DmlExecutionProvider" in disponibles:
        preferidos.append("DmlExecutionProvider")
    if "CoreMLExecutionProvider" in disponibles:
        preferidos.append("CoreMLExecutionProvider")
    preferidos.append("CPUExecutionProvider")
    return preferidos


def hay_gpu() -> bool:
    return proveedores_preferidos()[0] != "CPUExecutionProvider"


def sesion(nombre: str):
    """Sesion ONNX cacheada (se carga una vez por proceso)."""
    with _cerrojo:
        if nombre in _sesiones:
            return _sesiones[nombre]
        import onnxruntime as ort

        opciones = ort.SessionOptions()
        opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        proveedores = ["CPUExecutionProvider"] if nombre in _solo_cpu else proveedores_preferidos()
        if "DmlExecutionProvider" in proveedores:
            # DirectML no admite ejecucion en paralelo ni reordenar memoria.
            opciones.enable_mem_pattern = False
            opciones.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            s = ort.InferenceSession(str(ruta_modelo(nombre)), opciones, providers=proveedores)
        except Exception as e:  # GPU mal configurada: seguimos en CPU en vez de fallar.
            print(f"Aviso: no se pudo preparar la tarjeta grafica para {nombre}. Se usa la CPU.\n"
                  f"  Motivo: {texto_error(e)}", flush=True)
            _solo_cpu.add(nombre)
            s = ort.InferenceSession(str(ruta_modelo(nombre)), opciones, providers=["CPUExecutionProvider"])
        _sesiones[nombre] = s
        return s


def ejecutar(nombre: str, entradas: dict) -> list:
    """Ejecuta el modelo; si la tarjeta grafica falla, lo repite en la CPU y lo recuerda."""
    s = sesion(nombre)
    try:
        return s.run(None, entradas)
    except Exception as e:
        if s.get_providers()[0] == "CPUExecutionProvider":
            raise
        print(f"Aviso: la tarjeta grafica ha fallado con {nombre}. Se repite en la CPU (mas lento).\n"
              f"  Motivo: {texto_error(e)}", flush=True)
        with _cerrojo:
            _solo_cpu.add(nombre)
            _sesiones.pop(nombre, None)
        return sesion(nombre).run(None, entradas)


def proveedor_de(nombre: str) -> str:
    return sesion(nombre).get_providers()[0]


def modelo_segmentacion(preferencia: str = "auto") -> str:
    if preferencia in ("birefnet", "birefnet_lite"):
        return preferencia
    # El modelo completo solo compensa con tarjeta grafica; en CPU va mejor el lite.
    # Mientras el completo se descarga, se trabaja con el lite.
    completo = hay_gpu() and "birefnet" not in _solo_cpu and _ruta_destino("birefnet").exists()
    return "birefnet" if completo else "birefnet_lite"


def probar_acelerador() -> dict:
    """Recorte de prueba con una imagen vacia: dice si la tarjeta grafica funciona y cuanto tarda."""
    import time

    import numpy as np

    nombre = modelo_segmentacion()
    s = sesion(nombre)
    x = {s.get_inputs()[0].name: np.zeros((1, 3, 1024, 1024), np.float32)}
    ejecutar(nombre, x)  # la primera vez se prepara el modelo en la tarjeta (mas lenta)
    nombre = modelo_segmentacion()  # puede haber cambiado si la tarjeta ha fallado
    inicio = time.time()
    ejecutar(nombre, x)
    return {"modelo": nombre, "proveedor": proveedor_de(nombre), "segundos": time.time() - inicio}


def descargar_todos(incluir_completo: bool | None = None) -> None:
    nombres = modelos_necesarios() if incluir_completo is None else (
        ["birefnet_lite", "lama"] + (["birefnet"] if incluir_completo else []))
    for n in nombres:
        p = ruta_modelo(n)
        print(f"  OK {MODELOS[n].descripcion}: {p} ({p.stat().st_size // (1 << 20)} MB, licencia {MODELOS[n].licencia})")
