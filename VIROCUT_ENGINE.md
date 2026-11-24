# Motor de clips de Virocut — análisis y port a Clipwise

Fecha: 2026-11-23

## 1. Qué se analizó

Se descargaron los 63 chunks JS que carga `virocut.com`, incluidos los lazy chunks del editor y del render. Los relevantes para el motor:

| Archivo | Tamaño | Papel |
|---|---:|---|
| `src-CXqmzSPF.js` | 761 KB | Mediabunny 1.66.0 bundleado: muxing, demuxing, WebCodecs, `CanvasSource`, `AudioBufferSource`, `Mp4OutputFormat`. |
| `clips--31T975K.js` | 93 KB | Export final del clip: render offline frame a frame, audio, remux y fallback. |
| `layout-CX_6d-8M.js` | 22 KB | Plantillas de layout, geometría de recorte, detección de caras y elección de plantilla. |
| `emoji-picker-DtkHsXar.js` | 10.7 KB | Render de subtítulos por palabra, estilos y agrupación. |
| `reframe-v2-DGIiVAnp.js` | 19.7 KB | Pipeline de reencuadre: muestreo de frames, percepción Gemini, verificación de webcams, caché. |
| `face-detect-browser-C_0pEBQd.js` + `vision_bundle-2L-jcaNF.js` | 24.8 + 153 KB | Detección de caras en navegador con MediaPipe. |
| `inline-process-C840Aa4z.js` | 37 KB | Pipeline del job: VOD, audio, transcripción, candidatos virales, alineación, hook. |
| `hls-audio-YnY7q8IX.js` | 5.4 KB | Extracción y ensamblado de audio HLS. |
| `fix-webm-duration-DST5_b5M.js` | 13.6 KB | Fallback de grabación WebM. |
| `editor-demo-DXGP9vOc.js` | 105 KB | Preview del editor y controles de estilo. |

Los bundles están minificados; se beautificaron a `*.pretty.js` para leer las funciones exactas.

## 2. Pipeline completo de Virocut

```
URL de Twitch/Kick/YouTube
  -> resolución del VOD y playlist HLS
  -> extracción de audio HLS
  -> transcripción por chunks (Gemini)
  -> detección de momentos virales (Gemini)
  -> alineación de palabras
  -> generación de hook
  -> análisis de layout/reframe (MediaPipe + Gemini)
  -> render offline en el navegador
  -> MP4 H.264 + AAC
```

### 2.1 Resolución del VOD y audio

- El servidor resuelve la URL del VOD y devuelve una playlist HLS.
- `hls-audio` descarga los segmentos de audio y los ensambla.
- El audio se decodifica con `OfflineAudioContext.decodeAudioData` a un `AudioBuffer`.
- El clip usa solo el rango `[start, end]`; el audio se recorta con precisión de muestra.

### 2.2 Transcripción y selección viral

- El audio se parte en chunks de ~60 s.
- Se transcribe con `gemini-3.5-transcribe` (nombre observado en los server functions).
- La selección de momentos virales usa `gemini-3.1-flash-lite` con el transcript y devuelve candidatos con `start`, `end`, título, score y razón.
- Las palabras se alinean al rango del clip para que los subtítulos caigan en el tiempo correcto.
- El hook se genera a partir del diálogo del clip.

En el cliente no hay API keys: todo pasa por server functions. En Clipwise esto se sustituye por Groq Whisper/Gemini + Turso.

### 2.3 Reencuadre (reframe v2)

- Se muestrean 5 frames del clip, escalados a un máximo de 1280 px y JPEG calidad 0.85.
- Cada frame se manda a `perceiveFrame` (Gemini 3.1 Flash Lite), que devuelve webcams, regiones de contenido y tipo de escena.
- Cada webcam se verifica con `verifyWebcam` usando un crop con 15 % de margen y contexto.
- Los veredictos se cachean en `localStorage` bajo `virocut.reframe.v2.cache`.
- La plantilla se elige según:
  - número de webcams verificadas,
  - escena `irl` (si domina, horizontal),
  - regiones de contenido (si la webcam cae dentro del gameplay, se descarta),
  - aspect ratio del VOD,
  - webcam principal anterior y principal del canal.
- La geometría usa `inset`, `headroom`, `maxFaceShare`, `minHeadShare`, `minArea`, `maxArea`, `edgeWindow` y refinamiento de bordes por contraste de píxeles.
- La detección local de caras usa MediaPipe (`vision_bundle`), no un modelo remoto.

### 2.4 Render offline

Archivo: `clips--31T975K.js`, función `fn`.

Constantes exactas:

- Canvas: `1080 × 1920`.
- FPS: `30` (`1 / 30` por frame).
- Códec de vídeo: `avc` (H.264).
- Bitrate de vídeo: `4,000,000` bps.
- `keyFrameInterval: 2`.
- `latencyMode: "quality"`.
- Contenedor: `Mp4OutputFormat({ fastStart: "in-memory" })`.
- Target: `BufferTarget`.
- Audio: `aac` si `canEncodeAudio("aac")`; si no, `opus`.
- Bitrate de audio: `160,000` bps.
- Se comprueba `canEncodeVideo("avc", { width: 1080, height: 1920 })` antes de empezar.

Flujo:

1. Crear `Output` con `Mp4OutputFormat` y `BufferTarget`.
2. Crear `CanvasSource` con el canvas de 1080×1920.
3. `output.addVideoTrack(canvasSource, { frameRate: 30 })`.
4. Extraer/decodificar el audio del rango y crear `AudioBufferSource`.
5. `output.addAudioTrack(audioSource)`.
6. `output.start()`.
7. Para cada frame:
   - `video.currentTime = start + frame / 30`,
   - esperar el frame,
   - dibujar layout + subtítulos + hook + watermark,
   - `canvasSource.add(frame / 30, 1 / 30)`.
8. `canvasSource.close()`.
9. `audioSource.add(audioBuffer)` y `audioSource.close()`.
10. `output.finalize()`.
11. `new Blob([target.buffer], { type: "video/mp4" })`.

El audio se extrae con `AudioBufferSink` o con el audio HLS; si el audio no está disponible, el vídeo se exporta sin pista de audio.

Remux opcional: si el audio se decodificó por separado, Virocut puede volver a mezclar vídeo ya codificado + audio usando `EncodedVideoPacketSource` + `EncodedPacketSink`, sin recodificar el vídeo.

Fallback: si el navegador no soporta WebCodecs, usa `MediaRecorder` + `canvas.captureStream(0)` + `AudioWorklet`/`ScriptProcessor` en tiempo real. Es el camino lento y de menor calidad; el camino principal es offline.

### 2.5 Plantillas de layout

Definidas en `layout-CX_6d-8M.js`:

- `vertical`: un slot a pantalla completa, crop 9:16.
- `dividido`: dos slots verticales 50/50.
- `cam_juego`: cámara arriba (43 %), gameplay abajo (57 %).
- `dos_cams_juego`: dos cámaras arriba (25 %), gameplay abajo (75 %).
- `tres_cams_juego`: cámara arriba (49 %), gameplay abajo (51 %).
- `trio`: tres filas.
- `cuarteto`: cuatro slots.
- `horizontal`: vídeo centrado con fondo blur.
- `spotlight`: slot principal 62 %, detalle 32 %.
- `centrado`: vídeo centrado al 50 %.

Cada slot tiene `canvas: { x, y, w, h }` normalizado y `kind: main | cam | game`.

La posición de los subtítulos se calcula según la plantilla en `caption-layout`:

- `vertical` -> arriba del borde inferior.
- `dividido`, `cam_juego`, `tres_cams_juego` -> unión de los slots de cámara.
- `dos_cams_juego`, `trio_juego` -> debajo de la banda de cámaras.
- `trio`, `cuarteto` -> primera fila.
- `horizontal` -> sin banda.

### 2.6 Subtítulos

Archivo: `emoji-picker-DtkHsXar.js`.

- Agrupa palabras de 3 en 3 (`words_per_group` configurable).
- Corta el grupo antes de puntuación fuerte (`.!?¡¿…`) o si hay un silencio > 0.6 s.
- Duración mínima por grupo: 0.9 s.
- Estilos: `default`, `minimal`, `caja`, `pildora`, `neon`, `amarillo`.
- `default`: mayúsculas, peso 800, relleno blanco, resaltado `#FFD400`, stroke 0.12.
- `minimal`: sin mayúsculas, peso 600, resaltado blanco, stroke 0.07.
- `caja`: caja negra semitransparente, resaltado amarillo.
- `pildora`: píldora violeta para la palabra activa.
- `neon`: mayúsculas, peso 900, resaltado verde `#39FF88`.
- `amarillo`: mayúsculas, peso 900, resaltado amarillo, stroke grueso.
- Tamaño base: 3.8 % de la altura del canvas.
- Ancho máximo: 90 % del canvas; si no cabe, se reduce la fuente.
- La palabra activa se calcula con un adelanto de 0.15 s.
- Soporta emoji con fuentes de emoji y segmentación por grafemas.

### 2.7 Hook

Archivo: `clips--31T975K.js`, función `Xt`.

- Estilos: `impact`, `bar`, `pill`, `clean`.
- Tamaños: `impact` 6.6 % de la altura; `bar` 4.6 %; `pill`/`clean` 5.2 %.
- `impact`: mayúsculas, Impact/Arial Black, relleno blanco, stroke negro grueso.
- `bar`: barra blanca a todo el ancho, texto negro.
- `pill`: píldora blanca redondeada, texto negro.
- `clean`: texto blanco con stroke negro.
- El texto se envuelve a un máximo de 80–86 % del ancho.
- Se dibuja en la zona superior y se evita que choque con la banda de subtítulos.

## 3. Qué se portó a Clipwise

Archivo nuevo: `web/src/lib/virocutEngine.ts`.

Incluye:

- Export offline con `CanvasSource` + `AudioBufferSource` + `Mp4OutputFormat`.
- 1080×1920, 30 fps, H.264 4 Mbps, keyframe 2, `latencyMode: "quality"`.
- Audio AAC/Opus 160 kbps.
- Extracción de audio por rango con `AudioBufferSink`.
- Plantillas: `vertical`, `dividido`, `cam_juego`, `dos_cams_juego`, `tres_cams_juego`, `trio`, `cuarteto`, `horizontal`, `spotlight`, `centrado`.
- Crop con foco X/Y y fondo blur.
- Subtítulos por grupos de 3 palabras, estilos y resaltado.
- Hook con 4 estilos.
- Watermark.
- Progreso de render.

UI actualizada: `web/src/components/BrowserClipStudio.tsx`.

Controles añadidos:

- plantilla,
- estilo de subtítulos,
- activar/desactivar subtítulos,
- texto y estilo del hook,
- foco X/Y,
- watermark,
- cues manuales `inicio|fin|texto`.

## 4. Prueba real

Archivo de entrada: `clipwise-test.mp4` (5 s, 1280×720).

Render de prueba: 0–4 s, plantilla `cam_juego`, subtítulos `default`, hook `impact`.

Resultado con `ffprobe`:

```
video: h264, 1080x1920, 30/1 fps
audio: aac, 44100 Hz, stereo, 160 kb/s
duration: 4.017052 s
size: 1,031,358 bytes
bitrate: 2,053,959 bps
```

Frame extraído: layout de cámara + gameplay, hook arriba, subtítulo con palabra activa en amarillo y watermark. Audio con señal (`mean_volume -21.1 dB`, `max_volume -17.6 dB`).

## 5. Lo que falta para igualar a Virocut

1. **Transcripción automática**: Groq Whisper o Gemini desde el servidor, con timestamps por palabra.
2. **Selección viral**: prompt + esquema JSON para devolver `start`, `end`, `title`, `score`, `reason`.
3. **Hook automático**: LLM sobre el transcript del clip.
4. **Reframe IA**: MediaPipe Face Detector + verificación con Gemini; por ahora hay foco manual X/Y.
5. **Descarga de YouTube/Twitch/Kick**: no se puede hacer 100 % en Vercel sin un proxy o servicio externo; el desktop mantiene FFmpeg + Whisper.
6. **Jobs y almacenamiento**: Turso para cuentas/jobs, R2/S3 para MP4 y miniaturas.
7. **Render en worker**: mover canvas/encode a un `Worker` con `OffscreenCanvas` para no bloquear la UI.
8. **Remux sin recodificar**: usar `EncodedVideoPacketSource` + `EncodedPacketSink` cuando el audio venga de otra fuente.

## 6. Conclusión

Virocut no usa FFmpeg en el navegador para el render final. Usa Mediabunny + WebCodecs y dibuja cada frame en un canvas de 1080×1920. La calidad viene de:

- render offline frame a frame (no captura en tiempo real),
- H.264 a 4 Mbps con keyframes cada 2 s,
- audio AAC 160 kbps,
- plantillas de layout con crops precisos,
- subtítulos por palabra con resaltado y estilos,
- hook y watermark compuestos en el mismo canvas.

Eso es exactamente lo que ahora hace `virocutEngine.ts` en Clipwise.
