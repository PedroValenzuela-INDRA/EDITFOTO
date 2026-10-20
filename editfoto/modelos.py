"""Descarga y carga de los modelos ONNX (desde HuggingFace, en local).

Se elige automaticamente el mejor acelerador disponible:
CUDA (NVIDIA) > DirectML (cualquier GPU en Windows) > CoreML (Mac) > CPU.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

# Los modelos se guardan dentro de la carpeta de la app para que todo quede junto.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_MODELOS = Path(os.environ.get("EDITFOTO_MODELOS", RAIZ / "modelos"))


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


def ruta_modelo(nombre: str, descargar: bool = True) -> Path:
    info = MODELOS[nombre]
    destino = CARPETA_MODELOS / nombre / info.fichero
    if destino.exists():
        return destino
    if not descargar:
        raise FileNotFoundError(f"Falta el modelo {nombre}. Ejecuta: python -m editfoto descargar-modelos")
    from huggingface_hub import hf_hub_download

    print(f"Descargando {info.descripcion} desde HuggingFace ({info.repo})...", flush=True)
    return Path(hf_hub_download(info.repo, info.fichero, local_dir=CARPETA_MODELOS / nombre))


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
        proveedores = proveedores_preferidos()
        if "DmlExecutionProvider" in proveedores:
            # DirectML no admite ejecucion en paralelo ni reordenar memoria.
            opciones.enable_mem_pattern = False
            opciones.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            s = ort.InferenceSession(str(ruta_modelo(nombre)), opciones, providers=proveedores)
        except Exception as e:  # GPU mal configurada: seguimos en CPU en vez de fallar.
            print(f"Aviso: no se pudo usar la GPU ({e}). Se usa la CPU.", flush=True)
            s = ort.InferenceSession(str(ruta_modelo(nombre)), opciones, providers=["CPUExecutionProvider"])
        _sesiones[nombre] = s
        return s


def modelo_segmentacion(preferencia: str = "auto") -> str:
    if preferencia in ("birefnet", "birefnet_lite"):
        return preferencia
    return "birefnet" if hay_gpu() else "birefnet_lite"


def descargar_todos(incluir_completo: bool | None = None) -> None:
    if incluir_completo is None:
        incluir_completo = hay_gpu()
    nombres = ["birefnet_lite", "lama"] + (["birefnet"] if incluir_completo else [])
    for n in nombres:
        p = ruta_modelo(n)
        print(f"  OK {MODELOS[n].descripcion}: {p} ({p.stat().st_size // (1 << 20)} MB, licencia {MODELOS[n].licencia})")
