"""Fuente unica de la version y del canal de actualizacion (mismo metodo que INDRA HUB).

No importa nada pesado: lo usan la app, el actualizador y el workflow de release.

COMO PUBLICAR UNA VERSION NUEVA
-------------------------------
1. Sube __version__ aqui (p. ej. "0.3.0") y escribe su entrada en CHANGELOG.md.
2. Commit y tag que coincida:  git tag v0.3.0 && git push origin v0.3.0
3. GitHub Actions compila EDITFOTO.exe en Windows y publica la Release en el repo
   PUBLICO de descargas. La app la instala sola la proxima vez que se abra.
"""

__version__ = "0.4.1"

APP_NAME = "EDITFOTO"

# Repo PUBLICO que solo contiene los .exe en Releases (el codigo vive en el privado).
# La app consulta su API publica, asi que no hace falta token en el PC.
RELEASES_OWNER = "PedroValenzuela-INDRA"
RELEASES_REPO = "EDITFOTO-Releases"

# Nombre exacto del .exe adjunto a cada release (lo fija release.yml).
ASSET_NAME = "EDITFOTO.exe"


def version_tuple(v: str) -> tuple[int, int, int]:
    """'0.2.0', 'v0.2.0' o '0.2.0-beta' -> (0, 2, 0)."""
    v = (v or "").strip().lstrip("vV")
    for sep in ("-", "+"):
        v = v.split(sep, 1)[0]
    partes = []
    for trozo in v.split("."):
        digitos = "".join(c for c in trozo if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    partes += [0] * (3 - len(partes))
    return tuple(partes[:3])


def es_mas_nueva(remota: str, local: str = __version__) -> bool:
    return version_tuple(remota) > version_tuple(local)
