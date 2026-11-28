# Clipwise AI

La versión de Windows **1.3.0** se abre con `Abrir Clipwise.cmd` o se instala con `desktop/dist/installer/Clipwise-Setup-1.3.0.exe`. Consulta [las novedades, el flujo del editor y la configuración para equipos](STUDIO.md).

### Cambios de la versión 1.2.1
 La generación de varios clips usa hasta dos renders simultáneos en equipos con al menos cuatro procesadores lógicos; el análisis de escenas examina uno de cada tres fotogramas. Esto reduce el tiempo sin cambiar la resolución vertical de exportación (1080 × 1920), los subtítulos ni la evaluación de momentos. Los clips nuevos ya no muestran la etiqueta amarilla de creador y juego ni frases de relleno como «Lo mejor de Roblox». Los clips ya exportados conservan sus píxeles; vuelve a renderizarlos desde el editor para aplicar el cambio.

## IA con opciones gratuitas

Abre **IA → Conecta tu IA**. Elige un proveedor, crea tu propia clave en el enlace oficial del panel y pulsa **Guardar y probar**. No hay que modificar `.env` ni reiniciar. La prueba envía una frase de muestra; los siguientes trabajos usan el proveedor guardado para seleccionar momentos y revisar títulos y textos.

- **OpenRouter**: el preset usa `openrouter/free` y el servidor solo permite ese router o IDs terminados en `:free`. No configura fallback a modelos de pago. La selección del modelo puede variar, y hay límites de uso. [Documentación del router gratuito](https://openrouter.ai/docs/guides/routing/routers/free-router).
- **Gemini**: preset `gemini-3.1-flash-lite`, con nivel gratuito según la [tabla oficial de precios](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite). Mantén el proyecto sin facturación si quieres usar solo la cuota gratuita. Google puede usar el contenido del nivel gratuito para mejorar sus productos.
- **Ollama**: conecta con `127.0.0.1:11434` sin clave de nube. Hay que instalar Ollama y descargar el modelo indicado; el preset es `qwen3:8b`. No se instala ni descarga automáticamente. [API local](https://docs.ollama.com/api/openai-compatibility).
- **Local sin API**: mantiene el análisis de transcripción, audio y escenas sin cuenta externa.

Las claves nunca se devuelven en la API ni se guardan en el navegador. En Windows se almacenan con DPAPI, vinculadas al usuario actual, en `ai-settings.json` dentro del directorio de datos. En otros sistemas el archivo se crea con permisos de usuario. Eliminar la clave desactiva el proveedor. Cambiar de proveedor o endpoint requiere una nueva clave para evitar enviarla a otro servicio.

Las respuestas correctas se cachean en memoria y los errores de cuota abren una pausa antes de nuevos intentos. Los trabajos conservan el análisis local si la API falla. No se cambian de proveedor automáticamente ni se compran créditos. Las pruebas de integración de IA usan respuestas simuladas; no se ha verificado una llamada con una clave real del usuario.

## Enlaces de Kick y Twitch

En **Crear clips → Pegar enlace** se detecta la plataforma automáticamente. Admite repeticiones de Twitch (`twitch.tv/videos/ID`), clips compartidos (`clips.twitch.tv/ID` o `twitch.tv/canal/clip/ID`), repeticiones de Kick (`kick.com/canal/videos/UUID`) y clips (`kick.com/canal/clips/clip_ID` o `?clip=clip_ID`).

Para emisiones activas, usa **Directos** con el enlace del canal. El generador de videos terminados rechaza directos para evitar una descarga sin fin. Una repetición eliminada, privada o que requiere suscripción puede no estar disponible. La biblioteca `yt-dlp` incluye los extractores; `curl-cffi` se incluye también en el ejecutable para las conexiones de Kick.

Validación en red: descarga real de un clip público de Twitch y uno de Kick, ambos con video 1920×1080 y audio. `python tools/e2e/source_smoke.py` reproduce esta comprobación en una carpeta temporal; depende de que esas muestras sigan disponibles. Las pruebas de VOD y descarga de secciones usan dobles de prueba.

## Revisión editorial y publicación

- La selección recibe tiempos por frase, conserva contexto entre bloques y penaliza anuncios, introducciones y preguntas sin respuesta. Los cortes de escena no deben recortar palabras del inicio o el final.
- Una segunda revisión trabaja sobre el texto del **corte final**. Con `LLM_API_KEY` configurada utiliza el proveedor existente; si falla, conserva una versión local extraída de la transcripción. Comprueba coincidencia temática y cifras; esto no sustituye una revisión humana del significado.
- Títulos y captions evitan los sufijos genéricos. Los hashtags priorizan creador, juego y temas presentes en el clip, sin añadir automáticamente `#viral` o `#fyp`. No se promete un número de visualizaciones.
- En **Ver y editar → Texto** puedes guardar el título y los textos de YouTube y TikTok/Reels, copiarlos y descargarlos como TXT. Cambiar estos textos no cambia el rótulo incrustado en el video.
- El ZIP incluye un MP4, SRT cuando hay subtítulos, portada JPG cuando está disponible y TXT por clip, además de `captions.txt`.
- La eliminación de silencios conserva el tiempo de las palabras transcritas. Los clips sin transcripción conservan sus pausas visuales. Los re-renders de secciones remotas utilizan siempre el intervalo original completo.

Validación de esta revisión: 277 pruebas automatizadas, compilación TypeScript/Vite y render real de la muestra local a 1080×1920 con audio. La prueba reproducible `python tools/e2e/editorial_smoke.py` usa una base de datos temporal y verifica también el ZIP y el TXT. Las pruebas de respuestas del LLM usan proveedores simulados; no miden rendimiento viral ni calidad de un proveedor real.

---

Editor automático de clips verticales para videos largos. Convierte un enlace de YouTube, Kick o Twitch o un archivo subido en clips de 9:16 con subtítulos dinámicos, reencuadre, puntuación viral y descarga individual o en ZIP.

El procesamiento es local: Whisper transcribe, PySceneDetect y el analizador de momentos seleccionan fragmentos autocontenidos, OpenCV reencuadra y FFmpeg renderiza. El LLM es opcional; sin clave funciona el analizador heurístico.

---

## Qué incluye

- **Ingesta**: videos y clips de YouTube, Kick y Twitch mediante `yt-dlp` (con verificación de derechos) o subida de archivo MP4/MOV/MKV/WEBM/M4V/AVI.
- **Transcripción**: faster-whisper con timestamps por palabra, detección de idioma y VAD.
- **Análisis**: detección de escenas, construcción de ventanas por frases, selección de momentos autocontenidos y puntuación de 1 a 100.
- **Puntuación viral**: gancho, claridad, interés, ritmo y retención. Con LLM activo se mezcla 65 % LLM / 35 % heurística.
- **Edición automática**: recorte vertical 1080×1920, seguimiento de rostro, zoom dinámico, corrección suave de audio, eliminación opcional de silencios largos.
- **Subtítulos**: estilos Impacto, Limpio, Neón y Minimal; resaltado palabra a palabra, edición manual del texto, SRT descargable y re-render al guardar.
- **Música opcional**: se mezcla por debajo de la voz con `MUSIC_VOLUME`.
- **Resultados**: previsualización en el navegador, portada, descarga MP4, SRT y ZIP con todo el trabajo.
- **Interfaz en español**, tema oscuro, responsive, con progreso por etapas y persistencia del trabajo en la URL.

---

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | React 18, Vite 6, TypeScript, Tailwind CSS 3 |
| Backend | FastAPI, Uvicorn, SQLite, cola en memoria con un worker |
| Transcripción | faster-whisper (CTranslate2) |
| Escenas | PySceneDetect |
| Visión | OpenCV (Haar cascade para rostros) |
| Video/audio | FFmpeg 9 (H.264, AAC, ASS, silencedetect) |
| LLM opcional | Cualquier endpoint compatible con OpenAI Chat Completions |

---

## Requisitos

- Python **3.11** (recomendado).
- Node.js **20+** y npm.
- FFmpeg y ffprobe en el `PATH` o configurados en `.env`.
- 4 GB de RAM mínimo; 8 GB recomendado.
- Espacio en disco para el modelo de Whisper y los trabajos: el modelo `small` ocupa unos 500 MB; cada trabajo conserva fuente, audio y clips.
- Conexión a Internet la primera vez para descargar el modelo de Whisper. La importación de YouTube y el LLM también la necesitan.

### FFmpeg

- **Windows**: descarga una build de [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) o instala con `winget install Gyan.FFmpeg`. Si no está en el `PATH`, define `FFMPEG_BIN` y `FFPROBE_BIN`.
- **Linux**: `sudo apt install ffmpeg`
- **macOS**: `brew install ffmpeg`

El proyecto incluye una build local en `tools/ffmpeg/` para el entorno de desarrollo de Windows; no es necesario versionarla.

---

## Instalación rápida (Windows PowerShell)

Desde la carpeta `Clipwise`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r engine\requirements.txt

npm --prefix web install
npm --prefix web run build

Copy-Item engine\.env.example engine\.env
# Edita engine\.env si FFmpeg no está en el PATH o quieres cambiar el modelo.

cd engine
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre <http://127.0.0.1:8000>.

La primera transcripción descarga el modelo de Whisper y puede tardar varios minutos. Para pruebas rápidas usa `WHISPER_MODEL=tiny`; para calidad usa `small`, `medium` o `large-v3`.

### Linux / macOS

```bash
cd Clipwise
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r engine/requirements.txt
npm --prefix web install
npm --prefix web run build
cp engine/.env.example engine/.env
cd engine
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## App de escritorio (Windows)

El instalador de escritorio empaqueta el backend, el frontend, FFmpeg 9, `ffprobe` y el modelo `tiny` de faster-whisper. La máquina destino no necesita Python, Node ni FFmpeg instalados.

### Instalar

Ejecuta:

```text
desktop\dist\installer\Clipwise-Setup-1.0.0.exe
```

La instalación es por usuario, no pide administrador y deja:

- `%LOCALAPPDATA%\Programs\Clipwise\Clipwise.exe` y sus dependencias.
- Acceso directo en el menú Inicio; el del escritorio es opcional.
- Datos, base de datos, logs y `runtime.json` en `%LOCALAPPDATA%\Clipwise`.
- Microsoft Edge WebView2 Runtime. Si falta, el instalador ejecuta el bootstrapper incluido en modo silencioso.

La app abre una ventana nativa WebView2, no una pestaña del navegador. Solo permite una instancia: si se abre otra, enfoca la ventana existente. El procesamiento sigue siendo local; no se sube el video a ningún servicio.

### Ejecutar sin instalar

El bundle portable está en `desktop\dist\Clipwise\Clipwise.exe`. Se puede copiar a otra carpeta y ejecutar directamente.

```powershell
# Abrir la ventana normal
.\desktop\dist\Clipwise\Clipwise.exe

# Verificar FFmpeg, ffprobe, modelo y frontend; escribe logs\selftest.json
.\desktop\dist\Clipwise\Clipwise.exe --self-test

# Servidor local sin ventana, útil para automatización
.\desktop\dist\Clipwise\Clipwise.exe --server-only --port 8000
```

`--self-test` hace la comprobación completa de binarios. El arranque normal usa una comprobación ligera y abre la ventana en cuanto el puerto local acepta conexiones; el frontend muestra su propio estado de carga. El puerto se elige libre por defecto; `--port` lo fija.

Mientras la app corre, `%LOCALAPPDATA%\Clipwise\runtime.json` contiene `pid`, `port`, `url` y `started_at`. Al cerrar la ventana se elimina. Los logs están en `%LOCALAPPDATA%\Clipwise\logs\Clipwise.log`.

### Compilar el instalador

Requisitos de build en Windows:

- Python 3.11 con el entorno de build en `%LOCALAPPDATA%\Temp\Clipwise-venv` (o ajusta `$Python` en el script).
- Node.js 20+ y npm.
- Inno Setup 6 (`winget install --id JRSoftware.InnoSetup -e --scope user`).
- El modelo `Systran/faster-whisper-tiny` en la caché de Hugging Face, o conexión para descargarlo.
- El bootstrapper de WebView2 en `desktop\vendor\`; el script lo descarga si falta.

Desde `Clipwise`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File desktop\build_desktop.ps1 -Version 1.0.0
```

El script compila el frontend, regenera el icono, empaqueta con PyInstaller en `desktop\dist\Clipwise` y compila el setup en `desktop\dist\installer`. Para reutilizar el frontend o el bundle ya compilado:

```powershell
# Bundle y setup reutilizando el frontend ya compilado
.\desktop\build_desktop.ps1 -SkipFrontend

# Solo el bundle, sin Inno Setup
.\desktop\build_desktop.ps1 -SkipFrontend -SkipInstaller
```

Para recompilar únicamente el setup cuando `desktop\dist\Clipwise` ya está actualizado:

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" desktop\installer.iss /DAppVersion=1.0.0
```

Si cambiaste `launcher.py` o el backend, ejecuta antes el build con `-SkipFrontend -SkipInstaller`; el setup no debe empaquetar un bundle viejo.

La desinstalación elimina la carpeta de programa y los accesos directos; **no borra** `%LOCALAPPDATA%\Clipwise`, así que los trabajos y la configuración sobreviven a una actualización.

---

## Modo desarrollo

Dos procesos: API en `:8000` y Vite en `:5173` con proxy `/api` hacia el backend.

```powershell
# Terminal 1
cd engine
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
npm --prefix web run dev
```

Abre <http://127.0.0.1:5173>. Para producción, `npm --prefix web run build` y FastAPI sirve `web/dist` en la raíz.

> **Importante**: usa un solo proceso Uvicorn (`--workers 1`). La cola de trabajos y el worker viven en el proceso; varios workers no comparten la cola y además compiten por SQLite.

---

## Configuración

Copia `engine/.env.example` a `engine/.env`. Todas las variables son opcionales; estos son los valores por defecto:

| Variable | Default | Descripción |
|---|---|---|
| `DATA_DIR` | `engine/data` | Carpeta de base de datos, trabajos y clips. |
| `WEB_DIST` | `web/dist` | Build del frontend que sirve FastAPI. |
| `FFMPEG_BIN` | `ffmpeg` del PATH | Ruta al ejecutable de FFmpeg. |
| `FFPROBE_BIN` | `ffprobe` del PATH | Ruta al ejecutable de ffprobe. |
| `WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3`. |
| `WHISPER_DEVICE` | `auto` | `auto`, `cpu` o `cuda`. |
| `WHISPER_COMPUTE` | `int8` | `int8` en CPU; `float16` o `int8_float16` en GPU. |
| `LLM_API_KEY` | vacío | Si está vacío, solo se usan heurísticas. |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Endpoint compatible con OpenAI. |
| `LLM_MODEL` | `gpt-4o-mini` | Modelo a usar. También vale Ollama, p. ej. `llama3.1` en `http://localhost:11434/v1`. |
| `LLM_TIMEOUT_SECONDS` | `90` | Timeout de la llamada al LLM. |
| `MAX_UPLOAD_MB` | `2048` | Tamaño máximo del video subido. |
| `MAX_SOURCE_MINUTES` | `0` | Duración máxima del video de origen; `0` significa sin límite. |
| `SUBTITLE_FONT` | `Arial` | Fuente usada en el ASS. |
| `SUBTITLE_STYLE` | `bold` | Estilo por defecto. |
| `MUSIC_VOLUME` | `0.14` | Volumen de la música respecto a la voz. |
| `YTDLP_COOKIES` | vacío | Cookies Netscape para YouTube, solo si tienes derecho a usarlas. |
| `YTDLP_COOKIES_FROM_BROWSER` | vacío | Navegador del que leer cookies: `edge`, `chrome`, `firefox`, `brave`, `vivaldi` u `opera`. Acepta `edge:Default`. |
| `YTDLP_AUTO_COOKIES` | `true` | Si YouTube pide verificación, prueba cookies del navegador automáticamente. |
| `KEEP_WORKING_COPY` | `false` | Conserva `working.mp4` transcodeado para depuración. |

### GPU para Whisper

Con una GPU NVIDIA compatible:

```env
WHISPER_DEVICE=cuda
WHISPER_COMPUTE=float16
```

faster-whisper necesita CUDA 12 y cuDNN 9. Si falla la inicialización, vuelve a `auto` o `cpu`; la transcripción funcionará igual, más lenta. El render con OpenCV/FFmpeg es principalmente CPU.

---

## Cómo funciona

1. **Ingesta** (`ingest.py`): valida el enlace de YouTube contra una lista de hosts y el límite de duración; descarga con `yt-dlp`. En subidas valida el archivo y el límite de tamaño. Si el video tiene rotación o un códec que OpenCV no decodifica, crea una copia H.264.
2. **Audio**: extrae WAV mono 16 kHz para Whisper.
3. **Transcripción** (`transcribe.py`): faster-whisper con `word_timestamps=True`, VAD y detección de idioma. Si falla, el trabajo continúa sin voz y genera clips por escenas; el aviso queda en el log.
4. **Escenas** (`scenes.py`): PySceneDetect detecta cortes para que los clips no partan una escena.
5. **Momentos** (`moments.py`): agrupa palabras en frases, genera ventanas de 15–90 s que empiezan y terminan en frases, y descarta las que no son autocontenidas. Si hay LLM, propone candidatos y se mezcla la puntuación; si no, todo es heurístico.
6. **Puntuación**: desglose en gancho, claridad, interés, ritmo y retención; total 1–100. La selección prefiere ventanas compactas cuando hace falta para llegar al número de clips pedido.
7. **Clips** (`pipeline.py`): crea los registros, ajusta tiempos y genera subtítulos.
8. **Render** (`render.py`): OpenCV lee el video, sigue el rostro, recorta/zoom, escribe frames BGR por stdin a FFmpeg; FFmpeg quema el ASS, limpia la voz (`highpass`, `dynaudnorm`, `alimiter`), elimina silencios opcionalmente, mezcla música y exporta H.264/AAC 1080×1920. Cada render se guarda con un nombre versionado para no sobrescribir el video que el navegador tiene abierto.
9. **Resultados**: portada JPG, MP4, SRT, ASS y ZIP. La edición de subtítulos reemplaza el ASS/SRT y re-renderiza el clip completo.

### Reencuadre y subtítulos

- El crop base es 9:16 centrado. Cada ~1/8 s se detectan rostros frontales con Haar cascade; el centro se interpola suavemente y, si no hay rostro durante más de 1,2 s, vuelve al centro.
- El zoom dinámico añade hasta un 7 % de acercamiento al final del clip.
- Los subtítulos ASS usan un evento por palabra activa, con color de acento y salto de línea automático. Hay cuatro estilos y el texto se puede editar por línea en la interfaz.

---

## API

La documentación interactiva está en <http://127.0.0.1:8000/docs>.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Estado de FFmpeg, Whisper y límites. |
| `GET` | `/api/options` | Estilos de subtítulo y rango de clips. |
| `POST` | `/api/jobs` | Crea un trabajo. `multipart/form-data`. |
| `GET` | `/api/jobs` | Lista de trabajos. |
| `GET` | `/api/jobs/{id}` | Detalle con clips y subtítulos. |
| `POST` | `/api/jobs/{id}/cancel` | Cancela un trabajo en curso. |
| `DELETE` | `/api/jobs/{id}` | Borra el trabajo y sus archivos. |
| `GET` | `/api/jobs/{id}/download.zip` | ZIP con los MP4, SRT y portadas listos. |
| `GET` | `/api/clips/{id}` | Detalle de un clip. |
| `GET` | `/api/clips/{id}/video.mp4` | MP4 del clip. |
| `GET` | `/api/clips/{id}/thumb.jpg` | Portada. |
| `GET` | `/api/clips/{id}/subtitles.srt` | SRT. |
| `PUT` | `/api/clips/{id}/subtitles` | Guarda cues y re-renderiza. |
| `POST` | `/api/clips/{id}/render` | Reintenta el render de un clip. |

### Crear un trabajo

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F source_type=upload \
  -F video=@video.mp4 \
  -F 'options={"max_clips":5,"subtitle_style":"bold","remove_silences":true,"dynamic_zoom":true,"language":"es"}'
```

Para YouTube el formulario exige `rights_accepted=true`:

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F source_type=youtube \
  -F url=https://www.youtube.com/watch?v=VIDEO_ID \
  -F rights_accepted=true \
  -F 'options={"max_clips":5,"subtitle_style":"bold"}'
```

`max_clips` admite `5`–`15`; `null` o ausente significa automático. `subtitle_style` es `bold`, `clean`, `neon` o `minimal`. `language` es un código ISO o `null` para detección automática.

### Editar subtítulos

```json
PUT /api/clips/{id}/subtitles
{
  "cues": [
    { "start": 0.0, "end": 1.8, "text": "Texto corregido" }
  ]
}
```

Máximo 250 cues; cada texto, 300 caracteres. El clip pasa a `queued`/`rendering` y conserva su `video_url` anterior hasta que el nuevo render termina.

---

## Estructura del proyecto

```text
Clipwise/
├─ engine/
│  ├─ app/
│  │  ├─ main.py          API FastAPI y montaje del SPA
│  │  ├─ pipeline.py      Orquestación del trabajo
│  │  ├─ jobs.py          Cola y worker en segundo plano
│  │  ├─ ingest.py        YouTube, subida y copia de trabajo
│  │  ├─ transcribe.py    faster-whisper
│  │  ├─ scenes.py        PySceneDetect
│  │  ├─ moments.py       Selección, scoring y LLM opcional
│  │  ├─ subtitles.py     Cues, ASS y SRT
│  │  ├─ render.py        OpenCV + FFmpeg
│  │  ├─ db.py            SQLite
│  │  └─ config.py        Variables de entorno
│  ├─ tests/              pytest
│  ├─ data/               Base de datos y trabajos (no versionar)
│  └─ requirements.txt
├─ web/
│  ├─ src/                React + TypeScript + Tailwind
│  └─ dist/               Build servido por FastAPI
├─ tools/
│  ├─ ffmpeg/             Build local de FFmpeg (no versionar)
│  └─ e2e/                Fuente sintética y pruebas end-to-end
├─ desktop/
│  ├─ launcher.py         Ventana WebView2, servidor local y runtime
│  ├─ Clipwise.spec      Receta de PyInstaller
│  ├─ installer.iss       Instalador de Inno Setup
│  ├─ build_desktop.ps1   Build de frontend, bundle e instalador
│  ├─ make_icon.py        Generación del icono
│  └─ assets/             Iconos generados (no versionar)
└─ README.md
```

Cada trabajo en `engine/data/jobs/<job_id>/` conserva:

- `source.mp4` (o el archivo original), `audio.wav`, `working.mp4` si hubo transcode.
- `clips/<clip_id>/video.mp4`, `thumb.jpg`, `subs.ass`, `subs.srt`, `audio.wav`, `silences.json`, `render.log`.

La base de datos está en `engine/data/Clipwise.db`. Borrar un trabajo desde la interfaz elimina su carpeta y sus registros.

---

## Pruebas

```powershell
& "$env:LOCALAPPDATA\Temp\Clipwise-venv\Scripts\python.exe" -m pytest Clipwise/engine/tests -q
```

O desde el entorno activado:

```powershell
cd engine
pytest -q
```

La suite cubre ingestión, modelos, selección de momentos, scoring, subtítulos, mapeo de silencios, limpieza de renders y grafo de audio. Estado actual: **52 tests pasando**.

### Prueba end-to-end

Con el servidor en `:8000` y el modelo `tiny`:

```powershell
$env:WHISPER_MODEL="tiny"
& "$env:LOCALAPPDATA\Temp\Clipwise-venv\Scripts\python.exe" Clipwise\tools\e2e\run_e2e.py
```

El script usa la fuente sintética de 136 s incluida en `tools/e2e/`, comprueba el bloqueo de YouTube sin derechos, sube el video, espera los clips, verifica 1080×1920 con audio, descarga MP4/SRT/ZIP y edita subtítulos para provocar un re-render. Los artefactos quedan en `tools/e2e/` (`sample_clip.mp4`, `sample_frame.jpg`, `sample_clip_edited.mp4`, etc.).

---

## Rendimiento y límites

- **Un trabajo a la vez**: un único worker procesa la cola. Los trabajos enviados mientras hay otro en curso esperan.
- **Duración**: sin límite de minutos de origen; subida máxima de 2 GB. Los vídeos largos usan el modo audio-first por tramos.
- **Clips**: 5–15 por trabajo; cada clip dura entre 15 y 90 s.
- **Resolución de salida**: 1080×1920, H.264 High, AAC 160 kbps, `+faststart`.
- **Transcripción**: `tiny` es el más rápido; `small` mejora la calidad. En CPU, 136 s de audio con `tiny` tardaron ~57 s en el entorno de desarrollo.
- **Render**: OpenCV procesa cada fotograma y FFmpeg codifica en CPU; 5 clips de una fuente de 136 s tardaron ~7 minutos. Fuentes 1080p o clips más largos tardan más.
- **Disco**: cada clip terminado ocupa varios MB; los trabajos se conservan hasta que se borran. Limpia `engine/data/jobs` periódicamente si haces muchas pruebas.

Si necesitas más velocidad: usa `WHISPER_MODEL=tiny`, mantén el render en CPU con `-preset veryfast` (ya es el valor por defecto) y evita videos de más de 1080p. Para producción, separa la cola en un servicio dedicado y usa almacenamiento externo.

---

## Derechos y cumplimiento

- La importación de YouTube exige marcar la confirmación de derechos; el backend rechaza la petición si `rights_accepted` no es `true`.
- Solo se admiten hosts de YouTube y videos públicos o accesibles; no se elude DRM, autenticación ni restricciones de acceso.
- Si un video requiere inicio de sesión o cookies, la vía recomendada es subir un archivo propio.
- La música de fondo debe ser propia o tener licencia.
- El procesamiento es local. Si activas `LLM_API_KEY`, solo se envían fragmentos de la transcripción al endpoint configurado para puntuar momentos; no se suben los videos.
- La interfaz no añade marcas de agua a los clips.

---

## Solución de problemas

**`faster-whisper no esta instalado` o error de importación**  
`faster-whisper` necesita `requests` para descargar el modelo. Está fijado en `requirements.txt`; si actualizas el entorno, ejecuta `pip install -r engine/requirements.txt`. El mensaje ahora incluye la excepción real.

**FFmpeg no disponible**  
Comprueba `FFMPEG_BIN` y `FFPROBE_BIN` en `engine/.env` o instala FFmpeg en el `PATH`. La cabecera de la interfaz muestra el estado del motor.

**La primera transcripción tarda mucho**  
Está descargando el modelo de Whisper. Usa `WHISPER_MODEL=tiny` para pruebas y deja `small` para la versión final. La caché queda en `~/.cache/huggingface`.

**Error de CUDA / cuDNN**  
Vuelve a `WHISPER_DEVICE=cpu` y `WHISPER_COMPUTE=int8`. La GPU solo acelera Whisper, no el render.

**YouTube no descarga**  
Puede requerir cookies, edad o región. Configura `YTDLP_COOKIES` solo si tienes derecho a usar esa cuenta, o sube el archivo directamente. No se admiten directos.

**El render se queda corto o FFmpeg cierra el pipe**  
El código actual limita los frames al `-t` del render y tolera el cierre normal del pipe. Si aparece un error, revisa `clips/<id>/render.log`; el clip se puede reintentar desde la tarjeta o el modal.

**`[WinError 5] Acceso denegado` al guardar subtítulos**  
Era el fallo de sobrescribir `video.mp4` mientras el navegador lo reproducía. Ahora cada render usa `video-<id>.mp4` y `thumb-<id>.jpg`, actualiza la base de datos y limpia las versiones anteriores cuando Windows lo permite. Si un archivo antiguo sigue bloqueado, se puede borrar al cerrar la pestaña o el proceso que lo retiene; no afecta al clip activo.

**El puerto 8000 está ocupado**  
Cambia el puerto en Uvicorn y, si usas Vite, actualiza el proxy en `web/vite.config.ts`.

**Quiero empezar de cero**  
Detén el servidor, borra `engine/data/Clipwise.db` y `engine/data/jobs`, y vuelve a arrancar. Se perderán todos los trabajos.

---

## Roadmap

- Diarización y seguimiento de interlocutor para podcasts con varias personas.
- Render con GPU (NVENC) y proceso paralelo de clips.
- Más idiomas y modelos de subtítulos con estilos personalizados.
- Editor de timeline por clip (recorte manual, música por clip).
- Cola persistente y workers distribuidos.
- Dockerfile y despliegue con volumen para `data/`.

---

Procesado local con Whisper + FFmpeg. Sin marcas de agua. Clips verticales 1080×1920.
