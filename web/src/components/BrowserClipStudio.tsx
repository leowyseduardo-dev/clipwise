import { useEffect, useMemo, useState } from "react";
import { probeDuration, renderClip, type Cue } from "../lib/browserRender";

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

export function BrowserClipStudio() {
  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState(0);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [cuesText, setCuesText] = useState("");
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
    if (!next) {
      setDuration(0);
      setStart(0);
      setEnd(0);
      return;
    }
    try {
      const seconds = await probeDuration(next);
      setDuration(seconds);
      setStart(0);
      setEnd(Math.min(seconds, Math.max(1, seconds)));
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
        cues,
        onProgress: (value) => setProgress(Math.round(value * 100)),
      });
      setResultUrl(URL.createObjectURL(blob));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falló el render en el navegador.");
    } finally {
      setProgress(100);
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-900">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">
              Clipwise · render en navegador
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              Convierte un vídeo en clip vertical
            </h1>
            <p className="mt-2 max-w-xl text-sm text-slate-500">
              Mediabunny + WebCodecs. Sin FFmpeg, sin Whisper y sin servidor de render:
              el trabajo lo hace tu navegador.
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
                Duración detectada: {duration.toFixed(1)} s
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

            <label className="mt-5 block text-sm">
              <span className="font-medium">Subtítulos</span>
              <span className="mt-1 block text-xs text-slate-500">
               Una línea por frase: <code>inicio|fin|texto</code>. Ejemplo:{" "}
                <code>0|2|ESTO NO ES TODO</code>
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
              {busy ? `Renderizando… ${progress}%` : "Generar clip 9:16"}
            </button>
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold">Vista previa</h2>
            {resultUrl ? (
              <>
                <video
                  src={resultUrl}
                  controls
                  playsInline
                  className="mx-auto mt-4 max-h-[520px] rounded-xl bg-black"
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
              <div className="mt-4 flex aspect-[9/16] max-h-[520px] items-center justify-center rounded-xl bg-slate-100 text-center text-xs text-slate-400">
                {busy ? `Procesando… ${progress}%` : "El clip aparecerá aquí"}
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
