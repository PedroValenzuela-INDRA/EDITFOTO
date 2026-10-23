# Novedades de EDITFOTO

Cada entrada es lo que ves en "Novedades" al actualizarse la app. El formato de la
cabecera es `## vX.Y.Z · AAAA-MM-DD · Titulo`.

## v0.2.0 · 2026-10-22 · EDITFOTO.exe: se instala y se actualiza solo

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
