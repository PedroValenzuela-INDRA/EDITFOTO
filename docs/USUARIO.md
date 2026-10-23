# EDITFOTO

EDITFOTO es un editor de fotos de ropa para Vinted que funciona entero en tu PC. Recorta la prenda, iguala la luz y el color, suaviza las arrugas y pone tu fondo, sin enviar tus fotos a internet.

## Cómo descargarla y abrirla

1. Entra en **Releases**, en la columna de la derecha de esta página, y abre la última versión.
2. En **Assets**, descarga **EDITFOTO.exe**.
3. Guárdalo en una carpeta tuya, por ejemplo el Escritorio, y ábrelo con doble clic.

## Aviso de Windows

La primera vez que lo abras, Windows puede mostrar "Windows protegió su PC". Es normal: el programa no tiene firma digital. Pulsa **Más información** y después **Ejecutar de todas formas**. Algún antivirus también puede marcarlo por error.

## La primera vez

La app descarga los modelos de IA que necesita: unos 500 MB, o unos 1,4 GB si tienes tarjeta gráfica (AMD, NVIDIA o Intel). Verás el progreso en pantalla. Mientras baja el modelo grande, puedes trabajar con el pequeño. Esta descarga necesita conexión.

## Dónde están tus fotos

Todo va en la carpeta `Documentos\EDITFOTO`. Si tienes Documentos en OneDrive, está dentro de OneDrive.

- `fotos\entrada`: las fotos que quieres editar.
- `fotos\salida`: las fotos terminadas.
- `fotos\ejemplos`: tus fotos favoritas ya editadas, para que la app aprenda tu estilo.
- `presets`: tus propios presets.

La app tiene botones para abrir las carpetas de entrada, salida y ejemplos. Tus fotos y presets no se tocan al actualizar.

## Actualizaciones

Al abrir la app comprueba si hay una versión nueva. Si la hay, la descarga, se reinicia sola y enseña las novedades. No tienes que hacer nada.

## Si algo falla

El registro de la app está en `%LOCALAPPDATA%\EDITFOTO\registro.txt`. Para abrirlo, pega esa ruta en la barra de direcciones del Explorador de archivos. Ahí quedan los mensajes y los errores de la app.
