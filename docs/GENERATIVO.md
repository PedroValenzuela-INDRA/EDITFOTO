# Retoque generativo: doblar el bajo, abrir las mangas

EDITFOTO puede pedir a una IA de imagen que funciona en tu PC que recoloque una parte de la prenda. Por ejemplo, doblar el bajo de una sudadera enseñando el forro o abrir las mangas en arco. Esto no se puede hacer solo deformando la foto, porque el forro no sale en ella: hay que generarlo.

- **Modelo:** Qwen-Image-Edit-2511. Licencia Apache 2.0, así que puedes usar las fotos para vender.
- **Dónde corre:** dentro de **ComfyUI**, un programa gratuito aparte que usa tu tarjeta gráfica.
- **Qué hace EDITFOTO:** le manda la foto y la zona que quieres cambiar, recibe varias versiones y tú eliges una.
- **Qué no toca:** fuera de la zona marcada, la foto queda exactamente igual, píxel a píxel.

> **Revisa siempre lo generado.** Dentro de la zona, la IA inventa: el forro, una costura o una etiqueta pueden no ser como los de tu prenda. En Vinted la foto tiene que mostrar el artículo real. Si algo no coincide, descarta esa versión o dobla la prenda al hacer la foto.

## Lo que necesitas

- Tu tarjeta AMD Radeon RX 9070 XT de 16 GB vale.
- Recomendado: 32 GB de memoria RAM. Con 16 GB puede ir muy lento.
- Unos 30 GB libres en el disco.
- Tiempo: unos 20 minutos de instalación, más lo que tarden en bajar 24 GB de modelos.

## Paso 1. Instalar ComfyUI

1. Ve a https://www.comfy.org/download y descarga **ComfyUI Desktop** para Windows.
2. Instálalo. Cuando pregunte por la tarjeta gráfica, elige **AMD**.
3. Fíjate en la carpeta donde lo instalas. Por defecto suele ser `Documentos\ComfyUI`, y aquí la llamamos *la carpeta de ComfyUI*.
4. Ábrelo una vez y espera a que termine de prepararse.

Si ComfyUI Desktop te da problemas, prueba la versión portable para AMD:

1. Descárgala de https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_amd.7z
2. Descomprímela.
3. Abre `run_amd_gpu.bat`.

## Paso 2. Instalar el nodo GGUF

El modelo viene comprimido en formato GGUF para que quepa en 16 GB, y ComfyUI necesita un complemento para leerlo.

1. En ComfyUI, abre **Manager** y después **Custom Nodes Manager**.
2. Busca **ComfyUI-GGUF** (autor: city96) y pulsa **Install**.
3. Reinicia ComfyUI cuando te lo pida.

## Paso 3. Descargar los 4 ficheros del modelo

Descarga cada fichero y guárdalo en la subcarpeta indicada, dentro de la carpeta de ComfyUI:

| Fichero | Tamaño | Dónde va |
|---|---|---|
| [qwen-image-edit-2511-Q4_K_M.gguf](https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q4_K_M.gguf) | 13,2 GB | `models\unet` |
| [qwen_2.5_vl_7b_fp8_scaled.safetensors](https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors) | 9,4 GB | `models\text_encoders` |
| [qwen_image_vae.safetensors](https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors) | 0,3 GB | `models\vae` |
| [Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors) | 0,9 GB | `models\loras` |

Después, reinicia ComfyUI.

## Paso 4. Usarlo desde EDITFOTO

1. Deja ComfyUI abierto. EDITFOTO lo busca solo en este PC, en los puertos 8188 y 8000.
2. En EDITFOTO, abre una foto y pulsa **Retoque generativo**.
   - La app comprueba que ComfyUI está abierto y que tiene el nodo y los 4 ficheros. Si falta algo, te dice qué.
3. Elige la zona:
   - **Doblar el bajo**
   - **Abrir las mangas**
   - **Toda la prenda**

   Si quieres, cambia la instrucción. Funciona mejor en inglés.
4. Pulsa **Generar**. Saldrán 3 versiones, de unos segundos a un minuto cada una. Elige la que más te guste o descártalas todas.
5. La versión elegida pasa a ser la foto de partida: la app vuelve a recortarla y la edita como siempre (fondo, encuadre...).
   - **Quitar retoque generativo** vuelve a la foto original.

## Si algo falla

- **Salen imágenes negras o con ruido.** Es un fallo conocido de ComfyUI con las AMD de la serie 9000. Arranca ComfyUI con la opción `--disable-dynamic-vram`:
  - Portable: añádela al final de la línea de `run_amd_gpu.bat`.
  - Desktop: añádela en la configuración del servidor.
- **Error de memoria** (out of memory):
  1. Cambia el primer fichero por [qwen-image-edit-2511-Q3_K_M.gguf](https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q3_K_M.gguf) (9,9 GB, misma carpeta).
  2. En EDITFOTO, en la pestaña Presets, cambia `generativo.modelos.unet` al nombre del fichero nuevo.
- **"No encuentro ComfyUI abierto".**
  - Comprueba que ComfyUI está abierto y ha terminado de arrancar.
  - Si usa otro puerto, ponlo en el preset, en `generativo.servidor` (por ejemplo `http://127.0.0.1:8188`).
- **Va muy lento.** Es normal la primera vez, mientras carga el modelo. Si siempre va lento, cierra otros programas que usen la gráfica y comprueba que tienes 32 GB de RAM.

## Detalles técnicos

- El flujo de ComfyUI está en `editfoto/generativo.py` (`flujo_qwen`). Usa cargador GGUF, LoRA Lightning de 4 pasos, el codificador de texto Qwen2.5-VL y una máscara con `SetLatentNoiseMask`. El modelo trabaja a 1 megapíxel sobre un recorte de la prenda, para no perder detalle.
- Ajustes por preset, en el bloque `generativo`: `servidor`, `zona`, `opciones`, `pasos`, `cfg` y `modelos`.
- API: `GET /api/generativo`, `POST/GET/DELETE /api/fotos/{id}/generativo`, `POST /api/fotos/{id}/generativo/elegir`, `POST /api/fotos/{id}/generativo/cancelar` y `GET /img/{id}/generada/{i}`.
