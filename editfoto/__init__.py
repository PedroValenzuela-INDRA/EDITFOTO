"""EDITFOTO: editor local de fotos de ropa para Vinted.

Todo se ejecuta en tu PC. La IA solo se usa para recortar la prenda (BiRefNet)
y para borrar objetos que tu marques con el pincel (LaMa). El resto son
algoritmos deterministas que nunca inventan detalles de la prenda.
"""

from .version import __version__  # noqa: F401
