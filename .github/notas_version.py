"""Notas de una version para la pagina de descargas, sacadas de su entrada en CHANGELOG.md.

    python .github/notas_version.py 0.2.0 CHANGELOG.md > release_notes.md

Sale con 1 si el CHANGELOG no tiene esa version: sin notas no se publica.
"""

import re
import sys

_CABECERA = re.compile(r"^##\s+v?(\d+(?:\.\d+)+)\b(.*)$")


def notas(version: str, texto: str) -> str | None:
    version = version.strip().lstrip("vV")
    lineas = texto.splitlines()
    inicio = fin = None
    titulo = ""
    for i, linea in enumerate(lineas):
        m = _CABECERA.match(linea.strip())
        if not m:
            continue
        if inicio is not None:
            fin = i
            break
        if m.group(1) == version:
            inicio = i + 1
            partes = [p.strip() for p in re.split(r"\s+·\s+", m.group(2).strip()) if p.strip()]
            titulo = partes[-1] if len(partes) > 1 else ""
    if inicio is None:
        return None
    cuerpo = "\n".join(lineas[inicio:fin]).strip()
    if not cuerpo:
        return None
    return (f"## {titulo}\n\n" if titulo else "") + cuerpo + "\n"


if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as f:
        resultado = notas(sys.argv[1], f.read())
    if resultado is None:
        sys.exit(1)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(resultado)
