"""Un proyecto = una carpeta de entrada (fotos sin editar) y una de salida.

En salida/.editfoto/fotos/<id>/ se guarda todo lo de cada foto, para poder
retocarla despues sin volver a pasar la IA:
  estado.json   preset, ajustes, aprobada, medida del fondo, info del ultimo render
  alfa.png      recorte de la IA (la parte lenta)
  pincel_<tipo>.png   capas pintadas a mano
  mini_original.jpg / mini_resultado.jpg   miniaturas para la interfaz
La foto final se escribe en salida/<subcarpeta>/<nombre>.jpg
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
import traceback
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import color, config, imagen, modelos, pipeline

TIPOS_PINCEL = ("borrar", "proteger", "sumar", "restar")


@dataclass
class Foto:
    id: str
    ruta: str              # relativa a la carpeta de entrada
    nombre: str
    carpeta: str
    preset: str
    estado: str = "pendiente"   # pendiente | lista | error
    aprobada: bool = False
    error: str | None = None
    version: int = 0
    ajustes: dict = field(default_factory=dict)
    medida_fondo: dict | None = None
    analizada: bool = False
    info: dict = field(default_factory=dict)
    ancho: int = 0
    alto: int = 0


def _id_de(ruta_rel: Path) -> str:
    texto = str(ruta_rel.with_suffix("")).replace("\\", "/")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", texto.replace("/", "__")).strip("_") or "foto"


class Proyecto:
    def __init__(self, entrada: str | Path, salida: str | Path, preset_por_defecto: str = "generico"):
        self.entrada = Path(entrada).resolve()
        self.salida = Path(salida).resolve()
        self.dir_estado = self.salida / ".editfoto"
        self.preset_por_defecto = preset_por_defecto
        self.cerrojo = threading.RLock()
        self.fotos: dict[str, Foto] = {}
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self.entrada.mkdir(parents=True, exist_ok=True)
        self.salida.mkdir(parents=True, exist_ok=True)
        self.escanear()

    # ---------- inventario ----------

    def _dir(self, id_: str) -> Path:
        return self.dir_estado / "fotos" / id_

    def _guardar_estado(self, f: Foto) -> None:
        d = self._dir(f.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "estado.json.tmp"
        tmp.write_text(json.dumps(asdict(f), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "estado.json")

    def escanear(self) -> list[Foto]:
        """Busca fotos nuevas en la carpeta de entrada (incluidas subcarpetas)."""
        with self.cerrojo:
            vistas = set()
            for ruta in sorted(self.entrada.rglob("*")):
                if not ruta.is_file() or not imagen.es_imagen(ruta):
                    continue
                if any(p.startswith(".") for p in ruta.relative_to(self.entrada).parts):
                    continue
                rel = ruta.relative_to(self.entrada)
                id_ = _id_de(rel)
                while id_ in vistas:  # foto.jpg y foto.png en la misma carpeta
                    id_ += "_" + rel.suffix.lstrip(".").lower()
                vistas.add(id_)
                if id_ in self.fotos:
                    continue
                guardado = self._dir(id_) / "estado.json"
                if guardado.exists():
                    try:
                        datos = json.loads(guardado.read_text(encoding="utf-8"))
                        self.fotos[id_] = Foto(**{k: v for k, v in datos.items() if k in Foto.__dataclass_fields__})
                        continue
                    except Exception:
                        pass
                carpeta = str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else ""
                preset = config.preset_para_carpeta(carpeta) or self.preset_por_defecto
                self.fotos[id_] = Foto(id=id_, ruta=str(rel).replace("\\", "/"), nombre=rel.stem,
                                       carpeta=carpeta, preset=preset)
            # Fotos que ya no estan en la carpeta de entrada desaparecen de la lista.
            for id_ in list(self.fotos):
                if id_ not in vistas:
                    del self.fotos[id_]
            return self.lista()

    def lista(self) -> list[Foto]:
        return sorted(self.fotos.values(), key=lambda f: f.ruta.lower())

    def foto(self, id_: str) -> Foto:
        if id_ not in self.fotos:
            raise KeyError(id_)
        return self.fotos[id_]

    def ruta_resultado(self, f: Foto) -> Path:
        return self.salida / f.carpeta / f"{f.nombre}.jpg"

    # ---------- datos de trabajo ----------

    def preset_de(self, f: Foto) -> dict:
        return config.fusionar(config.cargar_preset(f.preset), f.ajustes.get("preset"))

    @staticmethod
    def giro(f: Foto) -> int:
        """Cuartos de vuelta en sentido horario que el usuario ha girado la foto (0 a 3)."""
        return int(f.ajustes.get("giro90", 0)) % 4

    def _imagen(self, f: Foto, preset: dict) -> np.ndarray:
        clave = (f.id, int(preset["salida"]["max_lado_trabajo"]), self.giro(f))
        if clave in self._cache:
            self._cache.move_to_end(clave)
            return self._cache[clave]
        img = pipeline.cargar_trabajo(self.entrada / f.ruta, preset)
        if self.giro(f):
            img = np.ascontiguousarray(np.rot90(img, -self.giro(f)))
        self._cache[clave] = img
        while len(self._cache) > 6:
            self._cache.popitem(last=False)
        return img

    def imagen_trabajo(self, id_: str) -> np.ndarray:
        f = self.foto(id_)
        return self._imagen(f, self.preset_de(f))

    def _alfa(self, f: Foto, img: np.ndarray) -> np.ndarray | None:
        ruta = self._dir(f.id) / "alfa.png"
        if not ruta.exists():
            return None
        return imagen.cargar_png_gris(ruta, (img.shape[1], img.shape[0]))

    def _capas(self, f: Foto, img: np.ndarray) -> pipeline.Capas:
        capas = pipeline.Capas()
        for tipo in TIPOS_PINCEL:
            ruta = self._dir(f.id) / f"pincel_{tipo}.png"
            if ruta.exists():
                setattr(capas, tipo, imagen.cargar_png_gris(ruta, (img.shape[1], img.shape[0])))
        return capas

    def referencia_fondo(self) -> list[float] | None:
        return color.referencia_de_lote([f.medida_fondo for f in self.fotos.values() if f.analizada])

    # ---------- operaciones ----------

    def analizar(self, id_: str, forzar: bool = False) -> Foto:
        with self.cerrojo:
            f = self.foto(id_)
            if f.analizada and not forzar and (self._dir(id_) / "alfa.png").exists():
                return f
            preset = self.preset_de(f)
            img = self._imagen(f, preset)
            alfa, medida = pipeline.analizar(img, preset)
            imagen.guardar_png_gris(alfa, self._dir(id_) / "alfa.png")
            imagen.miniatura(img, self._dir(id_) / "mini_original.jpg")
            f.medida_fondo, f.analizada = medida, True
            f.alto, f.ancho = img.shape[:2]
            self._guardar_estado(f)
            return f

    def renderizar(self, id_: str) -> Foto:
        with self.cerrojo:
            f = self.foto(id_)
            try:
                if not f.analizada:
                    self.analizar(id_)
                preset = self.preset_de(f)
                img = self._imagen(f, preset)
                alfa = self._alfa(f, img)
                if alfa is None:
                    self.analizar(id_, forzar=True)
                    alfa = self._alfa(f, img)
                t = time.time()
                resultado, info = pipeline.renderizar(img, alfa, preset, f.ajustes, self._capas(f, img),
                                                      f.medida_fondo, self.referencia_fondo())
                info["segundos"] = round(time.time() - t, 2)
                imagen.guardar_jpg(resultado, self.ruta_resultado(f), int(preset["salida"]["calidad_jpg"]))
                imagen.miniatura(resultado, self._dir(id_) / "mini_resultado.jpg")
                f.info, f.estado, f.error = info, "lista", None
                f.version += 1
            except Exception as e:
                traceback.print_exc()
                f.estado, f.error = "error", modelos.texto_error(e)
            self._guardar_estado(f)
            return f

    def ajustar(self, id_: str, preset: str | None = None, ajustes: dict | None = None,
                reemplazar: bool = False) -> Foto:
        with self.cerrojo:
            f = self.foto(id_)
            if preset:
                if preset not in config.listar_presets():
                    raise ValueError(f"No existe el preset {preset}")
                f.preset = preset
            if ajustes is not None:
                # El giro de 90 grados es de la foto, no un ajuste: solo lo cambia girar(),
                # que gira tambien el recorte y los pinceles. Restablecer no lo deshace.
                giro = self.giro(f)
                ajustes = {k: v for k, v in ajustes.items() if k != "giro90"}
                f.ajustes = ajustes if reemplazar else config.fusionar(f.ajustes, ajustes)
                if giro:
                    f.ajustes["giro90"] = giro
            self._guardar_estado(f)
            return self.renderizar(id_)

    def girar(self, id_: str, sentido: int) -> Foto:
        """Gira la foto 90 grados (1 = horario, -1 = antihorario) y lo recuerda.

        El recorte de la IA y las capas de pincel se giran con ella, asi no hay que
        volver a analizar ni se descuadra nada de lo ya pintado."""
        if sentido not in (1, -1):
            raise ValueError("sentido debe ser 1 (horario) o -1 (antihorario)")
        with self.cerrojo:
            f = self.foto(id_)
            d = self._dir(id_)
            for ruta in [d / "alfa.png"] + [d / f"pincel_{t}.png" for t in TIPOS_PINCEL]:
                if ruta.exists():
                    with Image.open(ruta) as im:
                        girada = im.transpose(Image.Transpose.ROTATE_270 if sentido == 1 else Image.Transpose.ROTATE_90)
                    girada.save(ruta)
            (d / "mini_original.jpg").unlink(missing_ok=True)  # se regenera ya girada
            f.ajustes["giro90"] = (self.giro(f) + sentido) % 4
            if f.ancho and f.alto:
                f.ancho, f.alto = f.alto, f.ancho
            self._guardar_estado(f)
            return self.renderizar(id_)

    def guardar_pincel(self, id_: str, tipo: str, png: bytes) -> Foto:
        if tipo not in TIPOS_PINCEL:
            raise ValueError(f"Pincel desconocido: {tipo}")
        with self.cerrojo:
            f = self.foto(id_)
            img = self.imagen_trabajo(id_)
            im = Image.open(io.BytesIO(png))
            # Se acepta PNG en gris o con transparencia: cuenta lo pintado (blanco u opaco).
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                capa = im.convert("RGBA").getchannel("A")
            else:
                capa = im.convert("L")
            capa = capa.resize((img.shape[1], img.shape[0]), Image.BILINEAR)
            ruta = self._dir(id_) / f"pincel_{tipo}.png"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            if np.asarray(capa).max() < 8:
                ruta.unlink(missing_ok=True)
            else:
                capa.save(ruta)
            return self.renderizar(id_)

    def quitar_pincel(self, id_: str, tipo: str) -> Foto:
        with self.cerrojo:
            (self._dir(id_) / f"pincel_{tipo}.png").unlink(missing_ok=True)
            return self.renderizar(id_)

    def pinceles(self, id_: str) -> dict[str, bool]:
        return {t: (self._dir(id_) / f"pincel_{t}.png").exists() for t in TIPOS_PINCEL}

    def ruta_pincel(self, id_: str, tipo: str) -> Path:
        return self._dir(id_) / f"pincel_{tipo}.png"

    def aprobar(self, id_: str, aprobada: bool) -> Foto:
        with self.cerrojo:
            f = self.foto(id_)
            f.aprobada = bool(aprobada)
            self._guardar_estado(f)
            return f

    def mascara_png(self, id_: str) -> bytes:
        """Mascara final (con pinceles) a tamano de trabajo, para superponerla al pintar."""
        with self.cerrojo:
            f = self.foto(id_)
            if not f.analizada:
                self.analizar(id_)
            preset = self.preset_de(f)
            img = self._imagen(f, preset)
            alfa = pipeline.mascara_final(self._alfa(f, img), preset, self._capas(f, img))
            ok, datos = cv2.imencode(".png", imagen.a_uint8(alfa))
            return datos.tobytes()

    def miniatura(self, id_: str, tipo: str) -> Path | None:
        ruta = self._dir(id_) / f"mini_{tipo}.jpg"
        if ruta.exists():
            return ruta
        if tipo == "original":
            imagen.miniatura(self.imagen_trabajo(id_), ruta)
            return ruta
        return None

    def procesar_lote(self, ids: list[str] | None = None, forzar: bool = False, progreso=None,
                      cancelar: threading.Event | None = None) -> None:
        """Dos fases: primero la IA en todas (lento), luego el resto con la referencia de fondo comun."""
        ids = ids or [f.id for f in self.lista()]
        if not forzar:
            ids = [i for i in ids if self.fotos[i].estado != "lista"]
        pendientes = [i for i in ids if forzar or not self.fotos[i].analizada]
        total = len(pendientes) + len(ids)
        hechas = 0
        for i in pendientes:
            if cancelar and cancelar.is_set():
                return
            if progreso:
                progreso("analizando", i, hechas, total)
            try:
                self.analizar(i, forzar=forzar)
            except Exception as e:
                traceback.print_exc()
                f = self.fotos[i]
                f.estado, f.error = "error", modelos.texto_error(e)
                self._guardar_estado(f)
            hechas += 1
        for i in ids:
            if cancelar and cancelar.is_set():
                return
            if progreso:
                progreso("renderizando", i, hechas, total)
            if self.fotos[i].analizada:
                self.renderizar(i)
            hechas += 1
        if progreso:
            progreso(None, None, hechas, total)
