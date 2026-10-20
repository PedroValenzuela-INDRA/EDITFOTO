# EDITFOTO

Editor de fotos de ropa para Vinted que funciona **entero en tu PC**, sin suscripciones ni envío de fotos a internet. Está pensado para editar unas 200 fotos al día del mismo set: metes las fotos en una carpeta, le das a procesar y revisas en el navegador.

## Qué hace con cada foto

1. **Recorta la prenda** con IA local (BiRefNet). Todo lo que no es prenda desaparece al poner el fondo nuevo: cables, trípode, enchufes, el suelo, la caja de los zapatos...
2. **Iguala la exposición y el color** usando el fondo de tu set como referencia. El móvil cambia la exposición según la prenda (una negra sale lavada, una blanca sale gris); como el fondo del set siempre es el mismo, se corrige cada foto para que el fondo vuelva a su valor y todas quedan iguales.
3. **Suaviza las arrugas** sin inventar nada: atenúa las sombras de tamaño medio (las arrugas) y deja intactas la textura del tejido, los estampados, los logos y los desperfectos.
4. **Endereza** la prenda buscando su eje de simetría (solo si la prenda es simétrica y el giro es pequeño).
5. **Encuadra** siempre igual: mismo tamaño de foto, misma proporción de prenda, centrada.
6. **Pone tu fondo** (color liso o una imagen tuya) con una sombra suave para que no parezca pegada.
7. **Guarda** en JPG sRGB **sin metadatos** (no se filtra la ubicación GPS del móvil).

Y para retocar a mano, cuatro pinceles:

| Pincel | Para qué |
|---|---|
| Borrar objeto | La IA (LaMa) borra lo que pintes: un cable o una pinza que cruza **por encima** de la prenda |
| Proteger defecto | Una mancha, un roto o bolitas que no se deben suavizar nunca |
| Es prenda | Si el recorte se ha comido un trozo (un cordón, un tirante) |
| No es prenda | Percha, mano, pinza que el recorte ha tomado como prenda |

## Por qué no hay un botón de "planchar con IA"

Las IA generativas (Stable Diffusion, Flux...) pueden "planchar" una prenda, pero lo hacen **redibujándola**: cambian el tejido, los estampados, los logos y borran los desperfectos. En Vinted eso es un problema serio: la foto tiene que mostrar el artículo tal como es, y si el comprador recibe algo distinto puede abrir una reclamación.

Por eso aquí la IA solo hace dos cosas que no tocan la prenda: **recortar** y **borrar lo que tú marques**. Todo lo demás son algoritmos deterministas que no pueden inventar detalles. Los desperfectos se ven tal cual están.

## Instalación (Windows)

1. Instala **Python 3.12** desde [python.org](https://www.python.org/downloads/). Durante la instalación marca **"Add python.exe to PATH"**.
2. Descarga esta carpeta (botón verde "Code" > "Download ZIP" en GitHub) y descomprímela donde quieras.
3. Doble clic en **`instalar.bat`**. Te preguntará qué tarjeta gráfica tienes:
   - **NVIDIA**: la opción más rápida.
   - **AMD, Intel o no lo sé**: DirectML, funciona con cualquier tarjeta gráfica moderna.
   - **Solo CPU**: funciona en cualquier PC, más lento.
4. La primera vez descarga los modelos de IA: unos 400 MB, o unos 1.350 MB si detecta tarjeta gráfica (añade el modelo de recorte completo, más preciso).

En Linux o Mac: `./instalar.sh` y luego `./iniciar.sh`.

## Uso diario

1. Copia las fotos del día en `fotos/entrada/`. Si las separas en subcarpetas con el nombre de un preset, cada una usa su preset automáticamente:
   ```
   fotos/entrada/sudadera/IMG_001.jpg
   fotos/entrada/pantalon/IMG_014.jpg
   fotos/entrada/jersey/IMG_027.jpg
   ```
   Las fotos que estén sueltas usan el preset `generico`. Valen JPG, PNG, WEBP y HEIC del iPhone.
2. Doble clic en **`iniciar.bat`**: se abre el navegador con la aplicación.
3. Pulsa **Procesar pendientes**. Primero pasa la IA por todas (la parte lenta) y luego aplica el resto.
4. Revisa: abre cada foto, ajusta si hace falta (arrugas, brillo, giro, tamaño, pinceles) y apruébala con la tecla **A** (pasa a la siguiente).
5. Las fotos terminadas están en `fotos/salida/`, con la misma estructura de carpetas.

Si no quieres revisar, **`procesar_todo.bat`** procesa todo sin abrir el navegador.

Los retoques se guardan: puedes cerrar y volver otro día, o cambiar un ajuste y rehacer una foto en un par de segundos sin volver a pasar la IA.

## Presets: tu estilo por tipo de prenda

Un preset guarda cómo quieres que quede un tipo de prenda: tamaño de la foto final, cuánto ocupa la prenda y dónde, color o imagen de fondo, sombra, fuerza del suavizado de arrugas, enderezado y nitidez. Vienen `generico`, `sudadera`, `pantalon`, `jersey`, `camiseta` y `calzado`, y se editan desde la pestaña **Presets** de la aplicación (se guardan en `presets/*.json`).

Si un ajuste te gusta para una foto concreta, el botón **Guardar estos ajustes en el preset** lo convierte en el nuevo valor por defecto.

### Aprender de tus fotos favoritas

Pon de 5 a 15 fotos ya editadas que te gusten en `fotos/ejemplos/` y, desde la pestaña Presets (o con `python -m editfoto aprender --nombre mi_estilo`), se crea un preset que copia su estilo: proporción de la foto, cuánto ocupa la prenda, dónde queda, color de fondo e intensidad de la sombra.

No es un entrenamiento de IA, no hace falta: el estilo de una foto de producto se reduce a esas medidas. Se ha comprobado pasándole fotos generadas con valores conocidos (prenda al 84 %, centrada, fondo #F4F4F2, sombra 0,22): recupera el encuadre y el fondo exactos y la sombra con 0,21.

## Velocidad

Medido en el equipo de desarrollo (CPU de 4 núcleos, sin tarjeta gráfica):

| Paso | Tiempo por foto |
|---|---|
| Recorte con IA (solo la primera vez) | unos 8 s |
| Resto de la edición (cada vez que cambias algo) | 1 a 5 s |
| Borrar un objeto con el pincel | unos 4 s por zona pequeña; un cable que cruza toda la prenda, unos 40 s |

Con CPU, 200 fotos tardan del orden de 30-40 minutos en segundo plano. Con una tarjeta gráfica la IA debería ser mucho más rápida (no lo he podido medir aquí); el resto de pasos no usa la gráfica. Para ver qué acelerador detecta tu PC: `python -m editfoto info`.

## Cómo funciona por dentro

| Paso | Técnica | Fichero |
|---|---|---|
| Recorte | BiRefNet (ONNX Runtime); limpieza de la máscara: se queda con la prenda, rellena agujeros pequeños y quita hilos finos que salen hasta el borde de la foto (cables, patas de trípode) | `segmentar.py`, `mascara.py` |
| Bordes limpios | Estimación del color de primer plano (Forte y Pitié, 2021) para que no quede halo del fondo antiguo | `mascara.py` |
| Color | Ganancias por canal en luz lineal para devolver el fondo del set a la mediana del lote; si el fondo es gris o blanco, además quita dominantes. Si una foto es de otro set, no se fuerza | `color.py` |
| Arrugas | Separación de frecuencias de la luminosidad con filtro de dominio guiado por el color: textura fina intacta, sombras medias atenuadas, bordes de color (estampados, manchas) intactos | `arrugas.py` |
| Borrar objetos | LaMa (ONNX), por teselas para conservar resolución | `inpaint.py` |
| Enderezado | Busca el giro que maximiza la simetría izquierda-derecha de la silueta | `composicion.py` |
| Encuadre, fondo, sombra | Transformación afín única (giro + escala + posición), sombra difuminada de la silueta | `composicion.py` |

Hay un documento con la API del servidor local en [`docs/API.md`](docs/API.md).

## Limitaciones conocidas

- **"Corregir la forma"** se limita a enderezar, centrar y escalar. Deformar la prenda (licuar) no se puede automatizar sin riesgo de falsearla.
- La **perspectiva** (foto tomada en diagonal) no se corrige: dispara con el móvil paralelo al suelo.
- La **percha** se mantiene, porque el recorte la considera parte de la prenda. Si no la quieres, píntala con "No es prenda" (o cuelga sin percha).
- Las arrugas muy marcadas (pliegues con sombra dura) se atenúan pero no desaparecen. Es deliberado: un pliegue duro se parece demasiado a una costura o a un defecto.
- La igualación de exposición necesita al menos 3 fotos del mismo set en el lote.

## Línea de comandos

```
python -m editfoto servidor   [--entrada fotos/entrada] [--salida fotos/salida] [--preset generico] [--abrir]
python -m editfoto procesar   [--entrada ...] [--salida ...] [--preset sudadera] [--forzar]
python -m editfoto aprender   --nombre mi_estilo [--ejemplos fotos/ejemplos] [--base sudadera]
python -m editfoto descargar-modelos [--completo]
python -m editfoto info
```

## Tests

```
python -m pytest tests -q                                  # rápidos, sin modelos
EDITFOTO_TEST_MODELOS=1 python -m pytest tests -q          # incluye los modelos reales
```

Los tests usan fotos sintéticas con la respuesta conocida: una sudadera con textura de punto, arrugas, una mancha, un logo, un cordón, un cable y la pata de un trípode. Comprueban que el cable desaparece y el cordón no, que las arrugas bajan a menos de la mitad mientras la textura y la mancha se conservan, que el enderezado recupera el giro, que el encuadre es exacto y que todo el flujo del servidor funciona.

## Modelos y licencias

| Modelo | Uso | Licencia | Origen |
|---|---|---|---|
| BiRefNet lite / BiRefNet | Recorte | MIT | [onnx-community en HuggingFace](https://huggingface.co/onnx-community/BiRefNet_lite-ONNX) |
| LaMa | Borrar objetos | Apache 2.0 | [Carve/LaMa-ONNX](https://huggingface.co/Carve/LaMa-ONNX) |

Ambas licencias permiten el uso comercial. Los modelos se descargan en `modelos/` la primera vez.
