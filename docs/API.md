# API del servidor local de EDITFOTO

Servidor: `python -m editfoto servidor` en `http://127.0.0.1:8765`. Todo es local; no hay autenticacion.
Las respuestas son JSON salvo las rutas `/img/...`. Errores: codigo HTTP 4xx/5xx con `{"detail": "texto"}`.

## Objeto Foto

```json
{
  "id": "sudadera__IMG_1234",
  "ruta": "sudadera/IMG_1234.jpg",
  "nombre": "IMG_1234",
  "carpeta": "sudadera",
  "preset": "sudadera",
  "estado": "pendiente | lista | error",
  "aprobada": false,
  "error": null,
  "version": 3,
  "ajustes": {"rotacion": 2.0, "preset": {"arrugas": {"fuerza": 0.8}}},
  "medida_fondo": {"rgb": [0.8, 0.8, 0.78], "uniforme": true},
  "analizada": true,
  "info": {"angulo_auto": 1.5, "angulo": 3.5, "escala": 1.2, "ganancias_color": [1, 1, 1], "segundos": 1.4},
  "ancho": 2400,
  "alto": 1800,
  "pinceles": {"borrar": false, "proteger": true, "sumar": false, "restar": false},
  "resultado": "/ruta/absoluta/salida/sudadera/IMG_1234.jpg"
}
```

- `version` sube en cada render: usala como `?v=` para evitar la cache del navegador.
- `ancho`/`alto`: tamano de la imagen de trabajo (0 si aun no se ha analizado). Los pinceles se pintan
  sobre esta imagen (`/img/{id}/original`).

### `ajustes` de una foto (todos opcionales, se fusionan con lo que ya tenga)

| clave | rango | efecto |
|---|---|---|
| `rotacion` | -15 a 15 (grados) | giro manual, se suma al automatico |
| `enderezar_auto` | bool | enderezado automatico por simetria |
| `escala` | 0.6 a 1.4 | tamano de la prenda respecto al preset |
| `mover_x`, `mover_y` | -0.25 a 0.25 | desplazamiento (fraccion del lienzo) |
| `preset` | objeto | cambios del preset solo para esta foto, misma forma que un preset. Los utiles en la interfaz: `arrugas.fuerza` (0 a 1), `color.brillo` (-1 a 1), `color.contraste` (-0.5 a 0.5), `color.saturacion` (0.5 a 1.5), `nitidez` (0 a 1), `enderezar.activo` (bool) |

## Rutas

### General
- `GET /api/estado` -> `{version, entrada, salida, proveedor: "CPU"|"CUDA"|"Dml"|"CoreML", gpu: bool, modelo_segmentacion, presets: [nombres], preset_por_defecto, referencia_fondo: bool}`

### Presets
- `GET /api/presets` -> `[{nombre, descripcion}]`
- `GET /api/presets/{nombre}` -> preset completo (ver `editfoto/config.py`, `POR_DEFECTO`)
- `PUT /api/presets/{nombre}` body: preset parcial o completo -> guarda (fusionando) y devuelve el preset. Sirve tambien para crear uno nuevo.
- `POST /api/aprender` body `{nombre, carpeta?, base?}` -> `{preset, resumen: {ejemplos, texto: [lineas]}}`. Tarda unos segundos por ejemplo.

### Fotos
- `GET /api/fotos` -> `{fotos: [Foto]}`
- `POST /api/fotos/recargar` -> vuelve a mirar la carpeta de entrada -> `{fotos: [Foto]}`
- `GET /api/fotos/{id}` -> Foto
- `POST /api/fotos/{id}/render` body `{preset?: "nombre", ajustes?: {...}, reemplazar?: bool}` -> rehace la foto (1-5 s; si no estaba analizada, unos segundos mas) -> Foto. Con `reemplazar: true` los ajustes sustituyen a los anteriores (para "restablecer" manda `{"ajustes": {}, "reemplazar": true}`).
- `PUT /api/fotos/{id}/pincel/{tipo}` cuerpo: PNG en bruto (`Content-Type: image/png`) -> guarda la capa y rehace la foto -> Foto.
  - `tipo`: `borrar` (la IA borra lo pintado: cables, pinzas que tapan la prenda), `proteger` (defectos que no se deben suavizar), `sumar` (esto SI es prenda), `restar` (esto NO es prenda: percha, mano, pinza).
  - El PNG puede ser de cualquier tamano (se reescala a ancho x alto de trabajo). Cuenta como pintado el canal alfa si el PNG tiene transparencia, si no el blanco. Un PNG vacio borra la capa.
- `DELETE /api/fotos/{id}/pincel/{tipo}` -> borra la capa y rehace -> Foto
- `POST /api/fotos/{id}/aprobar` body `{aprobada: bool}` -> Foto

### Lotes
- `POST /api/procesar` body `{ids?: [..], forzar?: bool, preset?: "nombre"}` -> arranca en segundo plano (sin `ids`: todas las pendientes; con `forzar`: rehace tambien las listas; con `preset`: se lo asigna antes). 409 si ya hay uno en marcha.
- `GET /api/progreso` -> `{activo, fase: "analizando"|"renderizando"|null, actual: id|null, hechas, total, errores, inicio, fin}`
- `POST /api/cancelar` -> para al terminar la foto en curso

### Imagenes
- `GET /img/{id}/original?max=1600` -> JPEG de la imagen de trabajo (sin `max`: tamano de trabajo completo)
- `GET /img/{id}/resultado` -> JPEG final (404 si no esta lista)
- `GET /img/{id}/miniatura/original` y `/miniatura/resultado` -> JPEG de 480 px
- `GET /img/{id}/mascara` -> PNG gris (tamano de trabajo): blanco = prenda. Util para superponerlo al pintar.
- `GET /img/{id}/pincel/{tipo}` -> PNG gris de la capa (404 si no hay)

### Interfaz
- `GET /` sirve `editfoto/web/index.html`; `GET /static/...` sirve el resto de `editfoto/web/`.
