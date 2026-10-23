# EDITFOTO

Editor de fotos de ropa para Vinted que funciona **entero en tu PC**, sin suscripciones ni envío de fotos a internet. Está pensado para editar unas 200 fotos al día del mismo set: metes las fotos en una carpeta, le das a procesar y revisas en el navegador.

## Qué hace con cada foto

1. **Pone la prenda derecha** (cuello o cintura arriba) aunque hagas la foto con el móvil girado o la prenda del revés. Lo decide un modelo de visión local (DINOv2) comparando la prenda con tus ejemplos y con prendas fotografiadas derechas; en una prueba con 960 fotos reales de 8 tipos de prenda acertó el 98,8 %. Si duda, no la toca, y si la giras tú a mano, manda tu giro.
2. **Recorta la prenda** con IA local (BiRefNet). Todo lo que no es prenda desaparece al poner el fondo nuevo: cables, trípode, enchufes, el suelo, la caja de los zapatos...
3. **Iguala la exposición y el color** usando el fondo de tu set como referencia. El móvil cambia la exposición según la prenda (una negra sale lavada, una blanca sale gris); como el fondo del set siempre es el mismo, se corrige cada foto para que el fondo vuelva a su valor y todas quedan iguales.
4. **Suaviza las arrugas** sin inventar nada: atenúa las sombras suaves de tamaño medio (las arrugas) y deja intactas la textura del tejido, el satinado del nylon, los pliegues hondos, los estampados, los logos y los desperfectos. Así la prenda no sale gris ni plana.
5. **Endereza** la prenda buscando su eje de simetría (solo si la prenda es simétrica y el giro es pequeño).
6. **Encuadra** siempre igual: mismo tamaño de foto, misma proporción de prenda, centrada.
7. **Pone tu fondo** (color liso o una imagen tuya) con una sombra suave para que no parezca pegada.
8. **Guarda** en JPG sRGB **sin metadatos** (no se filtra la ubicación GPS del móvil).

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

La forma normal es descargar **EDITFOTO.exe** de la última versión publicada en [EDITFOTO-Releases](https://github.com/PedroValenzuela-INDRA/EDITFOTO-Releases/releases) y abrirlo con doble clic. No hace falta instalar Python.

- **Aviso de Windows (SmartScreen)**: la primera vez, Windows puede mostrar "Windows protegió su PC". Pulsa **Más información** y después **Ejecutar de todas formas**. Como el programa no tiene firma digital, algún antivirus también puede marcarlo por error.
- **Primera vez**: descarga los modelos de IA, unos 500 MB, o unos 1,4 GB si hay tarjeta gráfica (añade el modelo de recorte completo, más preciso). El progreso se ve en pantalla.
- **Actualizaciones**: al abrirlo comprueba si hay una versión nueva, la descarga, se reinicia sola y enseña las novedades.
- **Tus datos**: las fotos y los presets están en `Documentos\EDITFOTO`, y las actualizaciones no los tocan. Los modelos de IA y el registro de la app (`registro.txt`) están en `%LOCALAPPDATA%\EDITFOTO`.

### Instalación para desarrollo

Para trabajar con el código en vez de usar el .exe:

1. Instala **Python 3.12** desde [python.org](https://www.python.org/downloads/). Durante la instalación marca **"Add python.exe to PATH"**.
2. Descarga el código (botón verde "Code" > "Download ZIP" en GitHub) y descomprímelo donde quieras.
3. Doble clic en **`instalar.bat`**. Te preguntará qué tarjeta gráfica tienes:
   - **NVIDIA**: la opción más rápida.
   - **AMD, Intel o no lo sé**: DirectML, funciona con cualquier tarjeta gráfica moderna.
   - **Solo CPU**: funciona en cualquier PC, más lento.

   Después descarga los modelos de IA, lo que puede tardar varios minutos.
4. Doble clic en **`iniciar.bat`**: arranca el servidor local y se abre la aplicación en el navegador.

En Linux o Mac: `./instalar.sh` y luego `./iniciar.sh`.

## Uso diario

1. Copia las fotos del día en `Documentos\EDITFOTO\fotos\entrada\`. La app tiene botones para abrir las carpetas de entrada, salida y ejemplos. Si las separas en subcarpetas con el nombre de un preset, cada una usa su preset automáticamente:
   ```
   Documentos\EDITFOTO\fotos\entrada\sudadera\IMG_001.jpg
   Documentos\EDITFOTO\fotos\entrada\pantalon\IMG_014.jpg
   Documentos\EDITFOTO\fotos\entrada\jersey\IMG_027.jpg
   ```
   Las fotos que estén sueltas usan el preset `generico`. Valen JPG, PNG, WEBP y HEIC del iPhone.
2. Abre **EDITFOTO.exe** con doble clic. Se abre la aplicación en su propia ventana.
3. Pulsa **Procesar pendientes**. Primero pasa la IA por todas (la parte lenta) y luego aplica el resto.
4. Revisa: abre cada foto, ajusta si hace falta (arrugas, brillo, giro, tamaño, pinceles) y apruébala con la tecla **A** (pasa a la siguiente).
5. Las fotos terminadas están en `Documentos\EDITFOTO\fotos\salida\`, con la misma estructura de carpetas.

En la instalación para desarrollo, **`procesar_todo.bat`** procesa todo sin abrir la interfaz.

Los retoques se guardan: puedes cerrar y volver otro día, o cambiar un ajuste y rehacer una foto en un par de segundos sin volver a pasar la IA.

## Presets: tu estilo por tipo de prenda

Un preset guarda cómo quieres que quede un tipo de prenda: tamaño de la foto final, cuánto ocupa la prenda y dónde, color o imagen de fondo, sombra, fuerza del suavizado de arrugas, enderezado y nitidez. Vienen `generico`, `sudadera`, `pantalon`, `jersey`, `camiseta` y `calzado`, y se editan desde la pestaña **Presets** de la aplicación. Los que vienen de fábrica se actualizan con la app; los que creas o cambias tú se guardan en `Documentos\EDITFOTO\presets` y tienen prioridad.

Si un ajuste te gusta para una foto concreta, el botón **Guardar estos ajustes en el preset** lo convierte en el nuevo valor por defecto. Para borrar un preset tuyo, borra su fichero en `Documentos\EDITFOTO\presets`.

### Aprender de tus fotos favoritas

Organiza tus fotos favoritas ya editadas en `Documentos\EDITFOTO\fotos\ejemplos`, una subcarpeta por tipo de prenda, y pulsa **Aprender** en la pestaña Presets:

```
ejemplos\fondo.jpg          opcional: una foto del fondo vacío (así el fondo sale exacto)
ejemplos\sudadera\...       de 5 a 20 fotos que te gusten
ejemplos\pantalon\...
ejemplos\jersey\...
```

Cada subcarpeta crea o actualiza el preset con su nombre, copiando su estilo: proporción de la foto, cuánto ocupa la prenda, dónde queda e intensidad de la sombra. Además **aprende tu fondo real**: si es liso, su color; si tiene textura (madera, tela...), lo reconstruye combinando los ejemplos. En cada foto la prenda tapa una zona distinta del fondo, así que se alinean las fotos (por si la cámara se movió), se igualan de luz y se toma, píxel a píxel, lo que se ve de fondo. Lo que ninguna foto deja ver lo rellena la IA, y de todas formas queda debajo de la prenda nueva.

No es un entrenamiento de IA, no hace falta: el estilo de una foto de producto se reduce a esas medidas y a ese fondo. Se ha comprobado con fotos generadas con valores conocidos: recupera el encuadre exacto, la sombra con un error de 0,01 y un fondo de madera con un error medio del 0,1 %, a partir de 8 fotos movidas entre sí hasta unos 20 píxeles.

Además aprende la **forma** de la prenda en tus ejemplos (por ejemplo, mangas abiertas en arco) y **dobla la foto real** de cada prenda nueva para que se parezca, como el "licuar" de Photoshop pero automático. No se inventa nada: el tejido, los logos y los desperfectos son los de verdad, solo deformados. Se regula con "Forma del ejemplo" (0 = como en la foto; por defecto 0,7, porque a más fuerza más puede cambiar la apariencia del corte). Lo que no aparece en tu foto no puede aparecer en el resultado: si quieres el bajo doblado enseñando el forro, dóblalo al hacer la foto. Si la prenda es muy distinta del ejemplo (un pantalón con la forma de una chaqueta), no se aplica y la app lo avisa.

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
| Orientación | DINOv2 small (ONNX): la prenda recortada en sus 4 giros se compara con tus ejemplos y con una colección genérica de prendas derechas; gana el giro más parecido si saca ventaja suficiente | `orientacion.py` |
| Arrugas | Separación de frecuencias de la luminosidad con filtro de dominio guiado por el color: textura fina intacta, sombras medias suaves atenuadas, sombras fuertes (satinado, pliegues hondos) y bordes de color (estampados, manchas) intactos | `arrugas.py` |
| Forma del ejemplo | Silueta tipo de tus ejemplos (Fourier) y deformación rígida por mínimos cuadrados móviles (Schaefer, 2006) de la foto real hacia ella | `forma.py` |
| Fondo de un ejemplo | Se borra la prenda y su sombra respetando la decoración; la luz se ajusta con una superficie suave y el grano del suelo se sintetiza con sus propias estadísticas (spot noise, Galerne et al., 2011) | `fondos.py` |
| Borrar objetos | LaMa (ONNX), por teselas para conservar resolución | `inpaint.py` |
| Enderezado | Busca el giro que maximiza la simetría izquierda-derecha de la silueta | `composicion.py` |
| Encuadre, fondo, sombra | Transformación afín única (giro + escala + posición), sombra difuminada de la silueta | `composicion.py` |

Hay un documento con la API del servidor local en [`docs/API.md`](docs/API.md).

## Limitaciones conocidas

- **La forma** se adapta doblando la foto real hacia la de tus ejemplos, pero lo que no sale en tu foto no puede aparecer: si quieres el bajo doblado enseñando el forro, dóblalo al hacer la foto.
- La **perspectiva** (foto tomada en diagonal) no se corrige: dispara con el móvil paralelo al suelo.
- La **percha** se mantiene, porque el recorte la considera parte de la prenda. Si no la quieres, píntala con "No es prenda" (o cuelga sin percha).
- Las arrugas muy marcadas (pliegues con sombra dura) se atenúan pero no desaparecen. Es deliberado: un pliegue duro se parece demasiado a una costura o a un defecto.
- La igualación de exposición necesita al menos 3 fotos del mismo set en el lote.
- El pincel **Borrar objeto** píntalo solo donde el cable cruza por encima de la prenda. Si pintas un hueco junto a la prenda (axila, entre las perneras), ese trozo de suelo rellenado puede acabar formando parte de la prenda.

## Si algo falla

- **"Se usará: CPUExecutionProvider" aunque elegiste NVIDIA**: actualiza el driver de NVIDIA (el paquete de IA usa CUDA 13, que necesita un driver reciente) y vuelve a ejecutar `instalar.bat`.
- **Errores al procesar con la tarjeta gráfica**: ejecuta `instalar.bat` otra vez, elige la opción 3 (solo CPU) y comprueba que funciona. Así sabremos si el problema es del acelerador.
- **Una foto sale con error en la rejilla**: ábrela, el mensaje aparece en el panel derecho. Una foto corrupta o a medio copiar se arregla volviendo a copiarla y pulsando "Recargar carpeta".

## Línea de comandos

```
python -m editfoto servidor   [--entrada fotos/entrada] [--salida fotos/salida] [--preset generico] [--abrir]
python -m editfoto procesar   [--entrada ...] [--salida ...] [--preset sudadera] [--forzar]
python -m editfoto aprender   [--ejemplos carpeta] [--nombre mi_estilo] [--base sudadera]   # sin --nombre: un preset por subcarpeta
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

Ambas licencias permiten el uso comercial. Los modelos se descargan la primera vez en `%LOCALAPPDATA%\EDITFOTO\modelos` (en la instalación para desarrollo, en `modelos/`).

## Publicar versiones

Las versiones se publican con un tag `vX.Y.Z` en este repositorio. GitHub Actions compila `EDITFOTO.exe` y lo publica en [EDITFOTO-Releases](https://github.com/PedroValenzuela-INDRA/EDITFOTO-Releases). Los pasos, y cómo probar sin publicar, están en [`docs/MANTENIMIENTO.md`](docs/MANTENIMIENTO.md).
