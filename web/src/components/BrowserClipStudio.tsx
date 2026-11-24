import { useEffect, useMemo, useState } from "react";
import {
  probeVideo,
  renderClip,
  type CaptionStyle,
  type Cue,
  type LayoutTemplate,
  type OverlayStyle,
} from "../lib/virocutEngine";

function parseCues(text: string): Cue[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [startRaw, endRaw, ...rest] = line.split("|");
      const start = Number(startRaw);
      const end = Number(endRaw);
      const value = rest.join("|").trim();
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || !value) {
        return null;
      }
      return { start, end, text: value };
    })
    .filter((cue): cue is Cue => cue !== null);
}

const LAYOUTS: Array<{ value: LayoutTemplate; label: string }> = [
  { value: "vertical", label: "Vertical 9:16" },
  { value: "cam_juego", label: "Cámara + juego" },
  { value: "dos_cams_juego", label: "2 cámaras + juego" },
  { value: "tres_cams_juego", label: "3 cámaras + juego" },
  { value: "dividido", label: "Dividido 2" },
  { value: "trio", label: "Trío vertical" },
  { value: "cuarteto", label: "Cuarteto" },
  { value: "horizontal", label: "Horizontal centrado" },
  { value: "spotlight", label: "Spotlight" },
  { value: "centrado", label: "Centrado" },
];

const CAPTION_STYLES: Array<{ value: CaptionStyle; label: string }> = [
  { value: "default", label: "Impacto amarillo" },
  { value: "minimal", label: "Minimalista" },
  { value: "caja", label: "Caja" },
  { value: "pildora", label: "Píldora" },
  { value: "neon", label: "Neón" },
  { value: "amarillo", label: "Amarillo grueso" },
];

const HOOK_STYLES: Array<{ value: OverlayStyle; label: string }> = [
  { value: "impact", label: "Impact" },
  { value: "bar", label: "Barra" },
  { value: "pill", label: "Píldora" },
  { value: "clean", label: "Limpio" },
];

export function BrowserClipStudio() {
  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState(0);
  const [sourceSize, setSourceSize] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [cuesText, setCuesText] = useState("");
  const [template, setTemplate] = useState<LayoutTemplate>("vertical");
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>("default");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  const [hook, setHook] = useState("");
  const [hookStyle, setHookStyle] = useState<OverlayStyle>("impact");
  const [focusX, setFocusX] = useState(0.5);
  const [focusY, setFocusY] = useState(0.42);
  const [watermark, setWatermark] = useState("Clipwise");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [resultUrl, setResultUrl] = useState("");

  useEffect(() => {
    return () => {
      if (resultUrl) URL.revokeObjectURL(resultUrl);
    };
  }, [resultUrl]);

  const cues = useMemo(() => parseCues(cuesText), [cuesText]);
  const canRender = Boolean(file) && end > start && !busy;

  async function chooseFile(next: File | null) {
    setFile(next);
    setError("");
    setResultUrl("");
    setProgress(0);
    setSourceSize("");
    if (!next) {
      setDuration(0);
      setStart(0);
      setEnd(0);
      return;
    }
    try {
      const info = await probeVideo(next);
      setDuration(info.duration);
      setSourceSize(`${info.width}×${info.height}`);
      setStart(0);
      setEnd(Math.min(info.duration, Math.max(1, info.duration)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo leer el vídeo.");
    }
  }

  async function render() {
    if (!file || end <= start) return;
    setBusy(true);
    setError("");
    setProgress(0);
    if (resultUrl) URL.revokeObjectURL(resultUrl);
    setResultUrl("");
    try {
      const blob = await renderClip(file, {
        start,
        end,
        template,
        captionStyle,
        captionsEnabled,
        hook,
        hookStyle,
        focusX,
        focusY,
        watermark,
        cues,
        onProgress: (value) => setProgress(Math.round(value * 100)),
      });
      setResultUrl(URL.createObjectURL(blob));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falló el render en el navegador.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-900">
      <div className="mx-auto w-full max-w-6xl">
        <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">
              Clipwise · motor de clips en navegador
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              De vídeo largo a clip vertical
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-500">
              Pipeline portado de Virocut: <code>CanvasSource</code> +{" "}
              <code>AudioBufferSource</code> + <code>Mp4OutputFormat</code>. Render
              frame a frame en WebCodecs, sin FFmpeg y sin servidor de render.
            </p>
          </div>
          <a href="/" className="text-sm font-medium text-blue-600 hover:underline">
            Volver a Clipwise
          </a>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <label className="block text-sm font-medium">Archivo de vídeo (MP4/MOV)</label>
            <input
              type="file"
              accept="video/*"
              onChange={(event) => void chooseFile(event.target.files?.[0] ?? null)}
              className="mt-2 block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-white"
            />
            {duration > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                Duración: {duration.toFixed(2)} s
                {sourceSize ? ` · Fuente: ${sourceSize}` : ""}
              </p>
            )}

            <div className="mt-5 grid grid-cols-2 gap-4">
              <label className="text-sm">
                <span className="block font-medium">Inicio (s)</span>
                <input
                  type="number"
                  min={0}
                  max={end}
                  step={0.1}
                  value={start}
                  onChange={(event) => setStart(Number(event.target.value))}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="text-sm">
                <span className="block font-medium">Fin (s)</span>
                <input
                  type="number"
                  min={start}
                  max={duration}
                  step={0.1}
                  value={end}
                  onChange={(event) => setEnd(Number(event.target.value))}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
            </div>

            <details className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4" open>
              <summary className="cursor-pointer text-sm font-semibold">
                Motor Virocut: layout, subtítulos y hook
              </summary>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="text-sm">
                  <span className="block font-medium">Plantilla</span>
                  <select
                    value={template}
                    onChange={(event) => setTemplate(event.target.value as LayoutTemplate)}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                  >
                    {LAYOUTS.map((layout) => (
                      <option key={layout.value} value={layout.value}>
                        {layout.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-sm">
                  <span className="block font-medium">Estilo de subtítulos</span>
                  <select
                    value={captionStyle}
                    onChange={(event) => setCaptionStyle(event.target.value as CaptionStyle)}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                  >
                    {CAPTION_STYLES.map((style) => (
                      <option key={style.value} value={style.value}>
                        {style.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="flex items-center gap-2 text-sm sm:col-span-2">
                  <input
                    type="checkbox"
                    checked={captionsEnabled}
                    onChange={(event) => setCaptionsEnabled(event.target.checked)}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                  <span className="font-medium">Dibujar subtítulos por palabra</span>
                </label>

                <label className="text-sm">
                  <span className="block font-medium">Hook (texto superior)</span>
                  <input
                    type="text"
                    value={hook}
                    onChange={(event) => setHook(event.target.value)}
                    placeholder="ESTO CAMBIA TODO"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>

                <label className="text-sm">
                  <span className="block font-medium">Estilo del hook</span>
                  <select
                    value={hookStyle}
                    onChange={(event) => setHookStyle(event.target.value as OverlayStyle)}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                  >
                    {HOOK_STYLES.map((style) => (
                      <option key={style.value} value={style.value}>
                        {style.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-sm">
                  <span className="block font-medium">
                    Encuadre horizontal: {Math.round(focusX * 100)}%
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={focusX}
                    onChange={(event) => setFocusX(Number(event.target.value))}
                    className="mt-2 w-full"
                  />
                </label>

                <label className="text-sm">
                  <span className="block font-medium">
                    Encuadre vertical: {Math.round(focusY * 100)}%
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={focusY}
                    onChange={(event) => setFocusY(Number(event.target.value))}
                    className="mt-2 w-full"
                  />
                </label>

                <label className="text-sm sm:col-span-2">
                  <span className="block font-medium">Marca de agua</span>
                  <input
                    type="text"
                    value={watermark}
                    onChange={(event) => setWatermark(event.target.value)}
                    placeholder="Clipwise"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
              </div>
            </details>

            <label className="mt-5 block text-sm">
              <span className="font-medium">Subtítulos manuales</span>
              <span className="mt-1 block text-xs text-slate-500">
                Una línea por frase: <code>inicio|fin|texto</code>. Se dividen en grupos
                de 3 palabras con resaltado. Ejemplo: <code>0|2|ESTO NO ES TODO</code>
              </span>
              <textarea
                rows={5}
                value={cuesText}
                onChange={(event) => setCuesText(event.target.value)}
                placeholder={"0|2|PRIMER GANCHO\n2|5|SEGUNDA FRASE"}
                className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs"
              />
            </label>

            <button
              type="button"
              disabled={!canRender}
              onClick={() => void render()}
              className="mt-5 w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-40"
            >
              {busy ? `Renderizando… ${progress}%` : "Generar clip 1080×1920"}
            </button>
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Vista previa</h2>
              <span className="text-xs text-slate-400">1080×1920 · 30 fps · 4 Mbps</span>
            </div>
            {resultUrl ? (
              <>
                <video
                  src={resultUrl}
                  controls
                  playsInline
                  className="mx-auto mt-4 max-h-[560px] rounded-xl bg-black"
                />
                <a
                  href={resultUrl}
                  download="clipwise-browser.mp4"
                  className="mt-4 block rounded-lg bg-slate-900 px-4 py-3 text-center text-sm font-semibold text-white"
                >
                  Descargar MP4
                </a>
              </>
            ) : (
              <div className="mt-4 flex aspect-[9/16] max-h-[560px] items-center justify-center rounded-xl bg-slate-100 text-center text-xs text-slate-400">
                {busy ? `Procesando… ${progress}%` : "El clip aparecerá aquí"}
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
