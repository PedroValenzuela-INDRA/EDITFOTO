"""Servidor local (solo en tu PC, http://127.0.0.1:8765) para revisar y retocar las fotos.

La API esta documentada en docs/API.md.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, actualizador, config, modelos
from .proyecto import TIPOS_PINCEL, Proyecto

WEB = Path(__file__).resolve().parent / "web"


class Trabajo:
    """Procesado por lotes en segundo plano (uno a la vez)."""

    def __init__(self):
        self.hilo: threading.Thread | None = None
        self.cancelar = threading.Event()
        self.estado = {"activo": False, "fase": None, "actual": None, "hechas": 0, "total": 0,
                       "errores": 0, "inicio": None, "fin": None}

    def progreso(self, fase, actual, hechas, total):
        self.estado.update(fase=fase, actual=actual, hechas=hechas, total=total)


def crear_app(proyecto: Proyecto) -> FastAPI:
    app = FastAPI(title="EDITFOTO", version=__version__)
    trabajo = Trabajo()
    app.state.trabajo = trabajo
    app.state.salir = None  # lo pone escritorio.py: cerrar la app desde la interfaz

    def foto_json(id_: str) -> dict:
        f = proyecto.foto(id_)
        datos = asdict(f)
        datos["pinceles"] = proyecto.pinceles(id_)
        datos["resultado"] = str(proyecto.ruta_resultado(f)) if f.estado == "lista" else None
        return datos

    def buscar(id_: str):
        if id_ not in proyecto.fotos:
            raise HTTPException(404, f"No existe la foto {id_}")
        return proyecto.fotos[id_]

    @app.exception_handler(ValueError)
    async def _valor(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(OSError)  # incluye PIL.UnidentifiedImageError (foto corrupta)
    async def _fichero(_: Request, e: OSError):
        return JSONResponse({"detail": f"No se puede leer la foto: {e}"}, status_code=422)

    # ---------- informacion general ----------

    @app.get("/api/estado")
    def estado():
        proveedor = modelos.proveedores_preferidos()[0].replace("ExecutionProvider", "")
        return {"app": "EDITFOTO", "version": __version__, "exe": actualizador.es_exe(),
                "entrada": str(proyecto.entrada), "salida": str(proyecto.salida),
                "ejemplos": str(modelos.DATOS / "fotos" / "ejemplos"),
                "proveedor": proveedor, "gpu": proveedor != "CPU",
                "modelo_segmentacion": modelos.modelo_segmentacion(),
                "presets": config.listar_presets(), "preset_por_defecto": proyecto.preset_por_defecto,
                "referencia_fondo": proyecto.referencia_fondo() is not None}

    @app.get("/api/modelos")
    def estado_modelos():
        return modelos.estado_modelos()

    @app.get("/api/actualizacion")
    def estado_actualizacion():
        return dict(actualizador.ESTADO, version_actual=__version__)

    @app.get("/api/novedades")
    def novedades():
        notas = actualizador.leer_novedades()
        return {"version": __version__, "notas": notas} if notas else {}

    @app.post("/api/abrir_carpeta")
    def abrir_carpeta(datos: dict = Body(...)):
        rutas = {"entrada": proyecto.entrada, "salida": proyecto.salida,
                 "ejemplos": modelos.DATOS / "fotos" / "ejemplos"}
        ruta = rutas.get(datos.get("cual"))
        if ruta is None:
            raise HTTPException(400, "cual debe ser entrada, salida o ejemplos")
        ruta.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(ruta)  # noqa: S606 - abre el Explorador en la carpeta
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(ruta)])
        return {"ruta": str(ruta)}

    @app.post("/api/salir")
    def salir():
        if not app.state.salir:
            raise HTTPException(400, "Solo disponible en EDITFOTO.exe")
        threading.Timer(0.3, app.state.salir).start()
        return {"ok": True}

    # ---------- presets ----------

    @app.get("/api/presets")
    def presets():
        return [{"nombre": n, "descripcion": config.cargar_preset(n).get("descripcion", "")}
                for n in config.listar_presets()]

    @app.get("/api/presets/{nombre}")
    def preset(nombre: str):
        return config.cargar_preset(nombre)

    @app.put("/api/presets/{nombre}")
    def guardar_preset(nombre: str, cambios: dict = Body(...)):
        actual = config.cargar_preset(nombre)
        nuevo = config.fusionar(actual, cambios)
        nuevo["nombre"] = config.nombre_valido(nombre)
        config.guardar_preset(nuevo)
        return config.cargar_preset(nuevo["nombre"])

    @app.post("/api/aprender")
    def aprender(datos: dict = Body(...)):
        from .aprender import aprender as aprender_preset

        carpeta = datos.get("carpeta") or str(modelos.DATOS / "fotos" / "ejemplos")
        nombre = datos.get("nombre")
        if not nombre:
            raise HTTPException(400, "Falta el nombre del preset")
        preset_nuevo, resumen = aprender_preset(carpeta, nombre, datos.get("base") or "generico")
        return {"preset": preset_nuevo, "resumen": resumen}

    # ---------- fotos ----------

    @app.get("/api/fotos")
    def fotos():
        return {"fotos": [foto_json(f.id) for f in proyecto.lista()]}

    @app.post("/api/fotos/recargar")
    def recargar():
        with proyecto.cerrojo:
            proyecto.escanear()
        return fotos()

    @app.get("/api/fotos/{id_}")
    def foto(id_: str):
        buscar(id_)
        return foto_json(id_)

    @app.post("/api/fotos/{id_}/render")
    def render(id_: str, datos: dict = Body(default={})):
        buscar(id_)
        proyecto.ajustar(id_, datos.get("preset"), datos.get("ajustes"), bool(datos.get("reemplazar")))
        return foto_json(id_)

    @app.put("/api/fotos/{id_}/pincel/{tipo}")
    async def pincel(id_: str, tipo: str, request: Request):
        buscar(id_)
        if tipo not in TIPOS_PINCEL:
            raise HTTPException(400, f"Pincel desconocido: {tipo}")
        png = await request.body()
        if not png:
            raise HTTPException(400, "Falta el PNG del pincel")
        proyecto.guardar_pincel(id_, tipo, png)
        return foto_json(id_)

    @app.delete("/api/fotos/{id_}/pincel/{tipo}")
    def quitar_pincel(id_: str, tipo: str):
        buscar(id_)
        if tipo not in TIPOS_PINCEL:
            raise HTTPException(400, f"Pincel desconocido: {tipo}")
        proyecto.quitar_pincel(id_, tipo)
        return foto_json(id_)

    @app.post("/api/fotos/{id_}/aprobar")
    def aprobar(id_: str, datos: dict = Body(...)):
        buscar(id_)
        proyecto.aprobar(id_, bool(datos.get("aprobada", True)))
        return foto_json(id_)

    # ---------- lotes ----------

    @app.post("/api/procesar")
    def procesar(datos: dict = Body(default={})):
        if trabajo.estado["activo"]:
            raise HTTPException(409, "Ya hay un procesado en marcha")
        ids = datos.get("ids") or None
        forzar = bool(datos.get("forzar"))
        if datos.get("preset"):
            if datos["preset"] not in config.listar_presets():
                raise HTTPException(400, f"No existe el preset {datos['preset']}")
            with proyecto.cerrojo:
                for f in proyecto.lista():
                    if (ids is None or f.id in ids) and (forzar or f.estado != "lista"):
                        f.preset = datos["preset"]
        trabajo.cancelar.clear()
        trabajo.estado.update(activo=True, fase="analizando", actual=None, hechas=0, total=0, errores=0,
                              inicio=time.time(), fin=None)

        def correr():
            try:
                proyecto.procesar_lote(ids, forzar, trabajo.progreso, trabajo.cancelar)
            finally:
                trabajo.estado.update(activo=False, fase=None, actual=None, fin=time.time(),
                                      errores=sum(1 for f in proyecto.fotos.values() if f.estado == "error"))

        trabajo.hilo = threading.Thread(target=correr, daemon=True)
        trabajo.hilo.start()
        return trabajo.estado

    @app.get("/api/progreso")
    def progreso():
        return trabajo.estado

    @app.post("/api/cancelar")
    def cancelar():
        trabajo.cancelar.set()
        return trabajo.estado

    # ---------- imagenes ----------

    sin_cache = {"Cache-Control": "no-store"}

    @app.get("/img/{id_}/original")
    def img_original(id_: str, max: int = 0):
        buscar(id_)
        from .imagen import a_uint8, reducir
        from PIL import Image

        img = proyecto.imagen_trabajo(id_)
        if max > 0:
            img = reducir(img, max)
        buf = io.BytesIO()
        Image.fromarray(a_uint8(img)).save(buf, "JPEG", quality=90)
        return Response(buf.getvalue(), media_type="image/jpeg")

    @app.get("/img/{id_}/resultado")
    def img_resultado(id_: str):
        f = buscar(id_)
        ruta = proyecto.ruta_resultado(f)
        if f.estado != "lista" or not ruta.exists():
            raise HTTPException(404, "Esta foto aun no esta procesada")
        return FileResponse(ruta, media_type="image/jpeg", headers=sin_cache)

    @app.get("/img/{id_}/miniatura/{tipo}")
    def img_miniatura(id_: str, tipo: str):
        buscar(id_)
        if tipo not in ("original", "resultado"):
            raise HTTPException(400, "tipo debe ser original o resultado")
        ruta = proyecto.miniatura(id_, tipo)
        if ruta is None:
            raise HTTPException(404, "Sin miniatura")
        return FileResponse(ruta, media_type="image/jpeg", headers=sin_cache)

    @app.get("/img/{id_}/mascara")
    def img_mascara(id_: str):
        buscar(id_)
        return Response(proyecto.mascara_png(id_), media_type="image/png", headers=sin_cache)

    @app.get("/img/{id_}/pincel/{tipo}")
    def img_pincel(id_: str, tipo: str):
        buscar(id_)
        ruta = proyecto.ruta_pincel(id_, tipo)
        if tipo not in TIPOS_PINCEL or not ruta.exists():
            raise HTTPException(404, "Sin pincel")
        return FileResponse(ruta, media_type="image/png", headers=sin_cache)

    # ---------- interfaz web ----------

    if WEB.exists():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    def inicio():
        indice = WEB / "index.html"
        if not indice.exists():
            return JSONResponse({"detail": "Falta la interfaz web (editfoto/web/index.html)"}, status_code=500)
        return FileResponse(indice, headers=sin_cache)

    return app


def arrancar(entrada: str, salida: str, puerto: int = 8765, abrir: bool = False, preset: str = "generico"):
    import uvicorn

    proyecto = Proyecto(entrada, salida, preset)
    app = crear_app(proyecto)
    url = f"http://127.0.0.1:{puerto}"
    print(f"\nEDITFOTO listo en {url}")
    print(f"  Fotos de entrada: {proyecto.entrada}  ({len(proyecto.fotos)} fotos)")
    print(f"  Fotos editadas:   {proyecto.salida}")
    print(f"  Acelerador: {modelos.proveedores_preferidos()[0]}")
    print("  Cierra esta ventana para apagarlo.\n")
    if abrir:
        import webbrowser

        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning")
