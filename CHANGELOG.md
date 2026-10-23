# Novedades de EDITFOTO

Cada entrada es lo que ves en "Novedades" al actualizarse la app. El formato de la
cabecera es `## vX.Y.Z · AAAA-MM-DD · Titulo`.

## v0.4.1 · 2026-10-23 · Guía del retoque generativo a un clic

- En el retoque generativo (tecla G), el botón **Abrir la guía de instalación** abre en el navegador los pasos para instalar ComfyUI y el modelo en tu PC.

## v0.4.0 · 2026-10-23 · Aprende de ti, bordes limpios y retoque generativo

- **Bordes limpios en puños y bajos**: si fotografías sobre una alfombra de pelo, los pelos que tapan el borde de la prenda ya no se quedan pegados ni muerden los puños o el final de la cremallera. Se quitan y el hueco se tapa con la propia prenda, continuando su canalé. Además, el borde se afina a resolución completa con una IA de matting (ViTMatte, 100 MB más la primera vez).
- **Me gusta (tecla F) y Mis favoritas**: guarda las fotos que te gustan, o sube las tuyas, y la app aprende de ellas el fondo, el encuadre, la forma y tu estilo. Cuantas más, mejor.
- **Ver opciones (tecla O)**: 4 versiones de la foto ordenadas por parecido con tus favoritas. La que eliges se aplica y las siguientes fotos de ese tipo de prenda se acercan a ella. En Mis favoritas ves lo que ha aprendido de tus elecciones.
- **Retoque generativo (opcional, tecla G)**: doblar el bajo enseñando el forro o abrir las mangas con una IA que corre en tu tarjeta gráfica (ComfyUI con Qwen-Image-Edit). Solo cambia la zona que eliges y te da varias versiones; revisa siempre lo generado. Necesita instalar ComfyUI y el modelo: sigue la guía docs/GENERATIVO.md.
- **Menos memoria sin tarjeta gráfica**: el recorte en el procesador usa la mitad de memoria.

## v0.3.0 · 2026-10-23 · La prenda se pone derecha sola y sale con más vida

- **La prenda se pone derecha sola**: aunque hagas la foto con el móvil girado o la prenda del revés, la app la gira para que el cuello (o la cintura) quede arriba. Lo decide un modelo de visión que corre en tu PC, comparando con tus ejemplos y con prendas fotografiadas derechas. Si duda, no la toca, y si la giras tú a mano, manda tu giro. La primera vez descarga 85 MB más.
- **Más contraste y brillo de verdad**: al quitar las arrugas, la prenda ya no se queda gris y plana. Se suavizan las sombras suaves (las arrugas) y se respetan los negros, los pliegues hondos y el satinado del nylon.
- **Fondo más limpio con un solo ejemplo**: donde estaba la prenda del ejemplo ya no queda una zona más clara, ni manchas, ni el contorno de su sombra, y la decoración (el vaquero de abajo) sale entera.
- **La forma del ejemplo solo se aplica con la prenda derecha**: antes podía intentar adaptar una prenda tumbada.

## v0.2.0 · 2026-10-23 · EDITFOTO.exe: se instala y se actualiza solo

- **Un solo programa, EDITFOTO.exe**, como INDRA HUB: no hace falta instalar Python ni nada mas. Cada vez que lo abres comprueba si hay una version nueva, la descarga y se reinicia solo.
- **Ventana propia** en vez del navegador.
- **Tus fotos y presets en Documentos\EDITFOTO**: las actualizaciones nunca los tocan. Los botones de la app abren las carpetas de entrada, salida y ejemplos.
- **Los modelos de IA se descargan solos** la primera vez, con su progreso en pantalla. Mientras baja el modelo grande puedes trabajar con el pequeno.
- **Tarjeta grafica AMD, NVIDIA o Intel** a traves de DirectML; si falla, la app sigue con el procesador.
- **Girar fotos 90 grados** (botones y tecla R / Mayus+R), tambien desde la rejilla. El giro se guarda: no se pierde al restablecer los ajustes ni al cerrar la app.
- **Tu fondo de verdad**: "Aprender de mis fotos favoritas" reconstruye el fondo de tus fotos de ejemplo (madera, tela...) combinandolas, en vez de poner un color liso. Si anades una foto del fondo vacio llamada fondo.jpg, se usa tal cual.
- **Un estilo por tipo de prenda**: pon tus ejemplos en subcarpetas (sudadera, pantalon, jersey...) y se crea un preset para cada una, con su encuadre y su sombra.
- **Basta una foto de ejemplo**: se borra su prenda y se queda todo lo demas, incluida la decoracion (por ejemplo, el pantalon que pones abajo). El hueco se rellena con la textura de tu propio suelo, sin manchas.
- **Encuadre en caja**: la prenda ocupa el mismo ancho y alto que en tus ejemplos, asi queda sitio para la decoracion.
- **Girar las fotos nuevas**: cada preset puede girar solas las fotos que entran (si siempre disparas en horizontal).
- **La forma de tus ejemplos**: la app dobla la foto real de la prenda para que tome la silueta de tus fotos favoritas (por ejemplo, mangas abiertas en arco). No inventa nada: el tejido, los logos y los desperfectos son los de verdad. Se regula con "Forma del ejemplo" (0 = como en la foto). Lo que no se ve en tu foto, como el forro de un bajo doblado, no puede aparecer.
