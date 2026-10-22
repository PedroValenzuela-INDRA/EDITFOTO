"""Linea de comandos: python -m editfoto <comando> --help"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .modelos import DATOS

ENTRADA = str(DATOS / "fotos" / "entrada")
SALIDA = str(DATOS / "fotos" / "salida")
EJEMPLOS = str(DATOS / "fotos" / "ejemplos")


def cmd_servidor(a):
    from .servidor import arrancar

    arrancar(a.entrada, a.salida, a.puerto, a.abrir, a.preset)


def cmd_procesar(a):
    from .proyecto import Proyecto

    p = Proyecto(a.entrada, a.salida, a.preset or "generico")
    if a.preset:
        for f in p.lista():
            if a.forzar or f.estado != "lista":
                f.preset = a.preset
    if not p.fotos:
        print(f"No hay fotos en {p.entrada}")
        return
    inicio = time.time()

    def progreso(fase, actual, hechas, total):
        if fase:
            print(f"  [{hechas + 1}/{total}] {fase} {actual}", flush=True)

    print(f"Procesando {len(p.fotos)} fotos de {p.entrada}")
    p.procesar_lote(None, a.forzar, progreso)
    errores = [f for f in p.lista() if f.estado == "error"]
    print(f"\nHecho en {time.time() - inicio:.0f} s. Fotos editadas en {p.salida}")
    for f in errores:
        print(f"  ERROR en {f.ruta}: {f.error}")
    if errores:
        sys.exit(1)


def cmd_aprender(a):
    from .aprender import aprender, aprender_por_tipo

    print(f"Aprendiendo el estilo de {a.ejemplos} ...")
    if a.nombre:
        _, resumen = aprender(a.ejemplos, a.nombre, a.base)
    else:
        _, resumen = aprender_por_tipo(a.ejemplos)
    print(f"\nPresets guardados ({', '.join(resumen['presets'])}) con {resumen['ejemplos']} ejemplos:")
    for linea in resumen["texto"]:
        print("  - " + linea)


def cmd_descargar(a):
    from . import modelos

    print("Descargando modelos (solo la primera vez)...")
    modelos.descargar_todos(a.completo or None)


def cmd_info(a):
    from . import __version__, config, modelos

    print(f"EDITFOTO {__version__}")
    print(f"Python {sys.version.split()[0]}")
    print(f"Aceleradores disponibles: {', '.join(modelos.proveedores_disponibles())}")
    print(f"Se usara: {modelos.proveedores_preferidos()[0]}")
    print(f"Presets: {', '.join(config.listar_presets())}")
    if a.sin_prueba:
        return
    print("Probando el recorte con IA...", flush=True)
    r = modelos.probar_acelerador()
    print(f"Prueba OK: modelo {r['modelo']} en {r['proveedor']}, {r['segundos']:.1f} s por foto")
    if r["proveedor"] == "CPUExecutionProvider" and modelos.proveedores_preferidos()[0] != "CPUExecutionProvider":
        print("AVISO: la tarjeta grafica no ha funcionado y se usara la CPU. Actualiza el driver de la tarjeta.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="editfoto", description="Editor local de fotos de ropa para Vinted")
    sub = ap.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("servidor", help="Abre la interfaz web para revisar y retocar")
    s.add_argument("--entrada", default=ENTRADA)
    s.add_argument("--salida", default=SALIDA)
    s.add_argument("--puerto", type=int, default=8765)
    s.add_argument("--preset", default="generico", help="Preset para fotos que no esten en una subcarpeta con nombre de preset")
    s.add_argument("--abrir", action="store_true", help="Abre el navegador")
    s.set_defaults(func=cmd_servidor)

    s = sub.add_parser("procesar", help="Procesa todas las fotos sin interfaz")
    s.add_argument("--entrada", default=ENTRADA)
    s.add_argument("--salida", default=SALIDA)
    s.add_argument("--preset", default=None)
    s.add_argument("--forzar", action="store_true", help="Rehace tambien las ya procesadas")
    s.set_defaults(func=cmd_procesar)

    s = sub.add_parser("aprender", help="Crea un preset a partir de fotos editadas que te gustan")
    s.add_argument("--ejemplos", default=EJEMPLOS)
    s.add_argument("--nombre", default=None,
                   help="Un solo preset con todas las fotos. Sin --nombre: un preset por subcarpeta (sudadera, pantalon...)")
    s.add_argument("--base", default="generico", help="Preset del que se copian el resto de ajustes")
    s.set_defaults(func=cmd_aprender)

    s = sub.add_parser("descargar-modelos", help="Descarga los modelos de IA")
    s.add_argument("--completo", action="store_true", help="Incluye BiRefNet completo (mejor con GPU)")
    s.set_defaults(func=cmd_descargar)

    s = sub.add_parser("info", help="Muestra el hardware detectado y hace un recorte de prueba")
    s.add_argument("--sin-prueba", action="store_true", help="No hace el recorte de prueba")
    s.set_defaults(func=cmd_info)

    a = ap.parse_args(argv)
    try:
        a.func(a)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        import traceback

        from .modelos import texto_error

        traceback.print_exc()
        print(f"\nERROR: {texto_error(e)}", file=sys.stderr)
        print("Copia todo el texto de esta ventana y pasaselo a Claude.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
