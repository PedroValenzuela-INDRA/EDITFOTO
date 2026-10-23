# Mantenimiento de EDITFOTO

Guía para el mantenedor: cómo está montado el reparto de la app, cómo se publica una versión y qué hacer cuando algo falla. Lo que lee quien descarga la app está en [`USUARIO.md`](USUARIO.md).

## Arquitectura de 2 repositorios

EDITFOTO usa dos repositorios de GitHub, igual que INDRA HUB.

| | `EDITFOTO` (privado) | `EDITFOTO-Releases` (público) |
|---|---|---|
| Qué contiene | Todo el código, `CHANGELOG.md`, los tests, este documento y el workflow de release | Un README para descargar la app y las Releases, cada una con su `EDITFOTO.exe` |
| Quién entra | Solo tú y las personas a las que des acceso | Cualquiera (es público) |
| Para qué sirve | Desarrollar y publicar | Que se pueda descargar la app y que la app busque ahí las versiones nuevas |

El flujo es este: subes un tag `vX.Y.Z` al repositorio privado, GitHub Actions compila `EDITFOTO.exe` en Windows y lo publica como Release en el repositorio público, y la app de cada usuario mira ahí al abrirse.

La app consulta la última Release del repositorio público sin token, así que en el PC del usuario no hay que configurar nada. El token `RELEASES_TOKEN` solo lo usa el workflow para escribir en el repositorio público.

## Configuración inicial (una sola vez)

1. **Mantén privado el repositorio `EDITFOTO`.** Ahí vive el código.

2. **Crea el repositorio público `EDITFOTO-Releases`.**
   - Dueño: `PedroValenzuela-INDRA`.
   - Márcalo como **Public** y activa **Add a README**. GitHub necesita al menos un commit para poder crear Releases.
   - No subas código. Ese repositorio solo contiene el README y las Releases.

3. **Crea un token fine-grained.** Ve a GitHub > Settings (de tu perfil) > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token, y configúralo así:
   - Resource owner: `PedroValenzuela-INDRA`.
   - Repository access: Only select repositories, y marca solo `EDITFOTO-Releases`.
   - Permissions > Repository permissions > Contents: **Read and write**.
   - Copia el token. Empieza por `github_pat_` y GitHub no lo vuelve a mostrar.
   - Mejor un token nuevo que reutilizar el de INDRA HUB: de ese ya no puedes volver a ver el valor, y regenerarlo rompería la publicación de INDRA HUB.
   - El token no se comparte con nadie (tampoco con Claude): solo se pega en el secreto del paso 4. Si se filtra, bórralo en GitHub y crea otro.

4. **Guarda el token como secreto en `EDITFOTO`.** Ve a Settings > Secrets and variables > Actions > New repository secret. El nombre tiene que ser `RELEASES_TOKEN` y el valor, el token del paso anterior.

   Opcional: si el repositorio de descargas tiene otro dueño o nombre, crea en la pestaña **Variables** de esa misma página `RELEASES_OWNER` y `RELEASES_REPO`. Sin ellas, el workflow usa el dueño de `EDITFOTO` y `EDITFOTO-Releases`.

   Importante: esas variables solo cambian dónde publica el workflow. La app busca las versiones en las constantes `RELEASES_OWNER` y `RELEASES_REPO` de `editfoto/version.py`, así que si cambias el destino, cambia también esas dos constantes.

5. **Pega en el README del repositorio público el contenido de [`docs/USUARIO.md`](USUARIO.md).** Edita el `README.md` de `EDITFOTO-Releases` desde GitHub y sustituye su contenido por el de ese fichero.

## Publicar una versión

1. **Sube la versión** en `editfoto/version.py`, en `__version__` (por ejemplo, `"0.3.0"`).

2. **Escribe la entrada en `CHANGELOG.md`.** La cabecera tiene este formato:

   ```
   ## v0.3.0 · 2026-11-03 · Título corto
   ```

   Los separadores son ` · ` (con espacios). Debajo va el texto que verán los usuarios en "Novedades", con al menos una línea. Si falta la entrada o no tiene texto debajo, el workflow no publica nada.

3. **Haz commit, pon el tag y súbelo:**

   ```
   git add editfoto/version.py CHANGELOG.md
   git commit -m "Versión 0.3.0"
   git push
   git tag v0.3.0
   git push origin v0.3.0
   ```

   El tag tiene que ser `v` seguido del mismo número que `__version__`. Si no coincide, el workflow falla a propósito.

### Qué pasa después

- GitHub Actions (Build & Release) tarda unos 5 minutos. Pasa los tests en Windows, compila `EDITFOTO.exe` y lo prueba: la autoprueba abre el .exe sin ventana, comprueba que las librerías viajan dentro, que arranca el servidor y que una edición de prueba sale bien.
- Si todo va bien, crea la Release `EDITFOTO vX.Y.Z` en `EDITFOTO-Releases`, con el texto del CHANGELOG y el `EDITFOTO.exe` adjunto, marcada como la última.
- Cada usuario la recibe la próxima vez que abra la app. Al abrirse, la app busca la última Release, descarga el `.exe` nuevo junto al actual, espera si hay un lote de fotos procesándose, reemplaza el .exe, se reinicia y enseña "Novedades".

## Probar sin publicar

Para comprobar un cambio sin publicar nada:

1. Ve a Actions > Build & Release > Run workflow.
2. Elige la rama y deja **publicar** sin marcar. Márcalo solo si quieres publicar de verdad.
3. Cuando termine, abre esa ejecución y descarga el artefacto `EDITFOTO-vX.Y.Z`, en la parte de abajo de la página (Artifacts). GitHub lo baja como un .zip con `EDITFOTO.exe` dentro. Se conserva 14 días.

Esta ejecución compila y prueba igual que una publicación, pero no crea tag ni Release. Además, cada push a una rama lanza CI (`ci.yml`): comprueba que el Python compila y pasa los tests en Linux, sin generar el .exe.

## Si algo falla

Cuando un paso del workflow falla, el log dice por qué. Estos son los mensajes que da el workflow:

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| El tag no coincide con `editfoto/version.py` | El tag no es `v` seguido de `__version__` | Sube `__version__` o rehaz el tag (ver abajo) |
| CHANGELOG.md no tiene la entrada de la versión | Falta la cabecera, está mal escrita o no tiene texto debajo | Escribe la entrada con el formato de arriba |
| Falta el secreto RELEASES_TOKEN | El secreto no existe en `EDITFOTO` o tiene otro nombre | Pasos 3 y 4 de la configuración inicial |
| La autoprueba del .exe ha fallado, "pywebview no viaja en el .exe" o "La autoprueba no ha escrito resultado" | El .exe compilado no arranca bien o le falta algo | Abre el paso "Autoprueba del .exe compilado". Muestra en JSON el resultado de cada prueba; la que dice `ERROR` indica qué falta |

Otros casos:

- Si falla un test, el log muestra cuál. Arréglalo, sube el cambio y repite el tag.
- Si falla el paso de publicar, lo habitual es que el token haya caducado o no tenga **Contents: Read and write** sobre `EDITFOTO-Releases`. Revísalo y, si hace falta, sigue los pasos 3 y 4.
- Si el tag estaba mal, bórralo y crea el bueno sobre el commit correcto:

  ```
  git tag -d v0.3.0
  git push origin :refs/tags/v0.3.0
  git tag v0.3.0
  git push origin v0.3.0
  ```

  Si la Release ya se había publicado en `EDITFOTO-Releases`, bórrala allí antes de volver a subir el tag.

Registro de la app: el .exe no tiene consola, así que sus mensajes y errores van a `%LOCALAPPDATA%\EDITFOTO\registro.txt`. Si un usuario tiene un problema, pídele ese fichero.

El aviso de SmartScreen la primera vez que se abre el .exe es normal, porque no está firmado. Está explicado en `USUARIO.md`.
