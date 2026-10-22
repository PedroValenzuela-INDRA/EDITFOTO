# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller: EDITFOTO.exe en un solo fichero, con ventana propia y sin consola.

    pyinstaller --noconfirm --clean EDITFOTO.spec

Los modelos de IA NO viajan dentro (pesan ~1,3 GB): la app los descarga la primera vez.
Si anades un modulo que se importa dentro de una funcion, comprueba que la autoprueba del
workflow lo cubre: si falta en el .exe, falla alli y no en el PC.
"""
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

hiddenimports = (
    collect_submodules("editfoto")
    + collect_submodules("uvicorn")  # carga sus protocolos por nombre
    + ["webview", "pillow_heif", "onnxruntime", "cv2"]
)

# ONNX Runtime con DirectML (DirectML.dll) y la libreria de HEIC del iPhone.
binaries = collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("pillow_heif")

datas = [
    ("editfoto/web", "editfoto/web"),  # la interfaz
    ("presets", "presets"),            # presets de fabrica (los tuyos van a Documentos\EDITFOTO)
    ("assets/editfoto.ico", "."),
]

a = Analysis(
    ["EDITFOTO.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EDITFOTO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="assets/editfoto.ico",
)
