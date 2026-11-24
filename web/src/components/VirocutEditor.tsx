import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import { clipSourceUrl, uploadBrowserRender } from "../lib/api";
import { downloadName, formatTime } from "../lib/format";
import type { Clip, SubtitleCue } from "../lib/types";
import {
  createFrameRenderer,
  renderClip,
  type CaptionStyle,
  type LayoutTemplate,
  type OverlayStyle,
  type Word,
} from "../lib/virocutEngine";
import {
  IconArrowLeft,
  IconCheck,
  IconDownload,
  IconFilm,
  IconLoader,
  IconPlay,
  IconRefresh,
  IconScissors,
  IconWand,
} from "./icons";

type VirocutSaved = {
  template?: string;
  caption_style?: string;
  hook?: string;
  hook_style?: string;
  watermark?: string;
  focus_x?: number;
  focus_y?: number;
  captions_enabled?: boolean;
  background?: string;
};

type Props = {
  clip: Clip;
  onClose: () => void;
  onUpdated: (clip: Clip, message?: string) => void;
  onError: (message: string) => void;
};

const PREVIEW_WIDTH = 540;
const PREVIEW_HEIGHT = 960;

const LAYOUTS: Array<{ value: LayoutTemplate; label: string }> = [
  { value: "vertical", label: "Vertical" },
  { value: "dividido", label: "Dividido" },
  { value: "cam_juego", label: "Cámara + juego" },
  { value: "dos_cams_juego", label: "2 cámaras + juego" },
  { value: "tres_cams_juego", label: "3 cámaras + juego" },
  { value: "trio", label: "Trío" },
  { value: "cuarteto", label: "Cuarteto" },
  { value: "horizontal", label: "Horizontal" },
  { value: "spotlight", label: "Spotlight" },
  { value: "centrado", label: "Centrado" },
];

const CAPTION_STYLES: Array<{ value: CaptionStyle; label: string }> = [
  { value: "default", label: "Impacto" },
  { value: "minimal", label: "Minimal" },
  { value: "caja", label: "Caja" },
  { value: "pildora", label: "Píldora" },
  { value: "neon", label: "Neón" },
  { value: "amarillo", label: "Amarillo" },
];

const HOOK_STYLES: Array<{ value: OverlayStyle; label: string }> = [
  { value: "impact", label: "Impacto" },
  { value: "bar", label: "Barra" },
  { value: "pill", label: "Píldora" },
  { value: "clean", label: "Limpio" },
];

const LAYOUT_ALIASES: Record<string, LayoutTemplate> = {
  auto: "vertical",
  vertical: "vertical",
  split: "dividido",
  dividido: "dividido",
  cam_juego: "cam_juego",
  dos_cams_juego: "dos_cams_juego",
  tres_cams_juego: "tres_cams_juego",
  trio: "trio",
  cuarteto: "cuarteto",
  horizontal: "horizontal",
  spotlight: "spotlight",
  centrado: "centrado",
};

const CAPTION_ALIASES: Record<string, CaptionStyle> = {
  default: "default",
  shorts: "default",
  impact: "default",
  bold: "default",
  minimal: "minimal",
  clean: "minimal",
  caja: "caja",
  box: "caja",
  pildora: "pildora",
  pill: "pildora",
  neon: "neon",
  amarillo: "amarillo",
  yellow: "amarillo",
};

function mapLayout(value: string | undefined): LayoutTemplate {
  return LAYOUT_ALIASES[value ?? ""] ?? "vertical";
}

function mapCaption(value: string | undefined): CaptionStyle {
  return CAPTION_ALIASES[value ?? ""] ?? "default";
}

function cuesToWords(cues: SubtitleCue[]): Word[] {
  const words: Word[] = [];
  for (const cue of cues) {
    if (cue.words?.length) {
      for (const word of cue.words) {
        const text = String(word.w ?? "").trim();
        if (!text) continue;
        words.push({ start: word.start, end: word.end, text });
      }
      continue;
    }
    const tokens = String(cue.text ?? "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!tokens.length) continue;
    const span = Math.max(0.08, (cue.end - cue.start) / tokens.length);
    tokens.forEach((text, index) => {
      words.push({
        start: cue.start + index * span,
        end: cue.start + (index + 1) * span,
        text,
      });
    });
  }
  return words.sort((a, b) => a.start - b.start);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

async function sourceErrorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    // The server may return an HTML error page.
  }
  return `No se pudo cargar el video original (${response.status}).`;
}

export function VirocutEditor({ clip, onClose, onUpdated, onError }: Props) {
  const saved = useMemo(() => {
    const render = clip.overlay?.render_options as
      | (Record<string, unknown> & { virocut?: VirocutSaved })
      | undefined;
    return (render?.virocut ?? {}) as VirocutSaved;
  }, [clip.overlay]);

  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceOffset, setSourceOffset] = useState(0);
  const [loadingSource, setLoadingSource] = useState(true);
  const [sourceError, setSourceError] = useState("");
  const [ready, setReady] = useState(false);

  const [template, setTemplate] = useState<LayoutTemplate>(() =>
    mapLayout(saved.template ?? clip.overlay?.render_options?.layout),
  );
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>(() =>
    mapCaption(saved.caption_style ?? clip.style),
  );
  const [hook, setHook] = useState(saved.hook ?? clip.hook ?? clip.title ?? "");
  const [hookStyle, setHookStyle] = useState<OverlayStyle>(
    (saved.hook_style as OverlayStyle) ?? "impact",
  );
  const [focusX, setFocusX] = useState(clamp(saved.focus_x ?? 0.5, 0, 1));
  const [focusY, setFocusY] = useState(clamp(saved.focus_y ?? 0.42, 0, 1));
  const [watermark, setWatermark] = useState(
    saved.watermark ?? clip.overlay?.render_options?.brand_text ?? "clipwise",
  );
  const [captionsEnabled, setCaptionsEnabled] = useState(
    saved.captions_enabled ?? true,
  );
  const [background, setBackground] = useState<"blur" | "black">(
    saved.background === "black" ? "black" : "blur",
  );

  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [exportError, setExportError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveProgress, setSaveProgress] = useState(0);
  const [resultUrl, setResultUrl] = useState("");
  const [resultBlob, setResultBlob] = useState<Blob | null>(null);
  const [savedMessage, setSavedMessage] = useState("");

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timeRef = useRef(0);
  const lastUiTime = useRef(0);

  const words = useMemo(
    () => cuesToWords(clip.subtitles.cues ?? []),
    [clip.subtitles.cues],
  );
  const clipDuration = Math.max(0.1, Number(clip.end) - Number(clip.start));
  const baseStart = Math.max(0, Number(clip.start) - sourceOffset);

  const renderer = useMemo(
    () =>
      createFrameRenderer({
        start: 0,
        end: clipDuration,
        template,
        focusX,
        focusY,
        words,
        captionStyle,
        captionsEnabled,
        hook,
        hookStyle,
        watermark,
        background,
      }),
    [
      template,
      focusX,
      focusY,
      words,
      captionStyle,
      captionsEnabled,
      hook,
      hookStyle,
      watermark,
      background,
      clipDuration,
    ],
  );

  const drawAt = useCallback(
    (value: number) => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video || video.readyState < 2) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      renderer(ctx, video, canvas.width, canvas.height, clamp(value, 0, clipDuration));
    },
    [renderer, clipDuration],
  );

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoadingSource(true);
    setSourceError("");
    setReady(false);
    setSourceFile(null);
    setSourceUrl("");
    setTime(0);
    timeRef.current = 0;
    lastUiTime.current = 0;
    setResultUrl("");
    setResultBlob(null);
    setSavedMessage("");
    setExportError("");

    (async () => {
      try {
        const response = await fetch(clipSourceUrl(clip.id), {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(await sourceErrorMessage(response));
        }
        const offset = Number(
          response.headers.get("X-Clipwise-Source-Offset") ?? "0",
        );
        const blob = await response.blob();
        if (!alive) return;
        const file = new File([blob], `clip-${clip.id}-source.mp4`, {
          type: blob.type || "video/mp4",
        });
        const url = URL.createObjectURL(file);
        setSourceOffset(Number.isFinite(offset) ? offset : 0);
        setSourceFile(file);
        setSourceUrl(url);
      } catch (error) {
        if (!alive || controller.signal.aborted) return;
        setSourceError(
          error instanceof Error
            ? error.message
            : "No se pudo cargar el video original.",
        );
      } finally {
        if (alive) setLoadingSource(false);
      }
    })();

    return () => {
      alive = false;
      controller.abort();
    };
  }, [clip.id]);

  useEffect(() => {
    return () => {
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    };
  }, [sourceUrl]);

  useEffect(() => {
    return () => {
      if (resultUrl) URL.revokeObjectURL(resultUrl);
    };
  }, [resultUrl]);

  useEffect(() => {
    if (!ready) return;
    drawAt(timeRef.current);
  }, [ready, drawAt]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const video = videoRef.current;
      if (!video) return;
      const value = clamp(video.currentTime - baseStart, 0, clipDuration);
      timeRef.current = value;
      if (Math.abs(value - lastUiTime.current) > 0.04) {
        lastUiTime.current = value;
        setTime(value);
      }
      drawAt(value);
      if (video.ended || value >= clipDuration - 0.02) {
        setPlaying(false);
        setTime(clipDuration);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, baseStart, clipDuration, drawAt]);

  function handleLoaded() {
    const video = videoRef.current;
    if (!video) return;
    setReady(true);
    timeRef.current = 0;
    setTime(0);
    const drawFirst = () => drawAt(0);
    video.currentTime = baseStart;
    if (video.readyState >= 2) drawFirst();
    video.addEventListener("seeked", drawFirst, { once: true });
    window.setTimeout(drawFirst, 300);
  }

  async function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (playing) {
      video.pause();
      setPlaying(false);
      return;
    }
    if (timeRef.current >= clipDuration - 0.05) {
      timeRef.current = 0;
      setTime(0);
      video.currentTime = baseStart;
    }
    try {
      await video.play();
      setPlaying(true);
    } catch {
      onError("El navegador bloqueó la reproducción. Pulsa otra vez.");
    }
  }

  function handleSeek(value: number) {
    const video = videoRef.current;
    const next = clamp(value, 0, clipDuration);
    timeRef.current = next;
    lastUiTime.current = next;
    setTime(next);
    if (!video) {
      drawAt(next);
      return;
    }
    video.currentTime = baseStart + next;
    video.addEventListener("seeked", () => drawAt(next), { once: true });
  }

  function handleCanvasPoint(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    setFocusX(clamp((event.clientX - rect.left) / rect.width, 0, 1));
    setFocusY(clamp((event.clientY - rect.top) / rect.height, 0, 1));
  }

  function resetLook() {
    setTemplate(mapLayout(clip.overlay?.render_options?.layout));
    setCaptionStyle(mapCaption(clip.style));
    setHook(clip.hook ?? clip.title ?? "");
    setHookStyle("impact");
    setFocusX(0.5);
    setFocusY(0.42);
    setWatermark(clip.overlay?.render_options?.brand_text ?? "clipwise");
    setCaptionsEnabled(true);
    setBackground("blur");
  }

  async function handleExport() {
    if (!sourceFile) return;
    setExporting(true);
    setProgress(0);
    setExportError("");
    setResultBlob(null);
    setResultUrl("");
    setSavedMessage("");
    try {
      const blob = await renderClip(sourceFile, {
        start: baseStart,
        end: baseStart + clipDuration,
        template,
        focusX,
        focusY,
        words,
        captionStyle,
        captionsEnabled,
        hook: hook.trim(),
        hookStyle,
        watermark: watermark.trim(),
        background,
        onProgress: setProgress,
      });
      const url = URL.createObjectURL(blob);
      setResultBlob(blob);
      setResultUrl(url);
      setProgress(1);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "El navegador no pudo renderizar el clip.";
      setExportError(message);
      onError(message);
    } finally {
      setExporting(false);
    }
  }

  async function handleSave() {
    if (!resultBlob) return;
    setSaving(true);
    setSaveProgress(0);
    setSavedMessage("");
    try {
      const updated = await uploadBrowserRender(
        clip.id,
        resultBlob,
        {
          template,
          caption_style: captionStyle,
          hook: hook.trim(),
          hook_style: hookStyle,
          watermark: watermark.trim(),
          focus_x: focusX,
          focus_y: focusY,
          captions_enabled: captionsEnabled,
          background,
        },
        setSaveProgress,
      );
      onUpdated(updated, "Render de Virocut guardado en el clip.");
      setSavedMessage("Render guardado. El clip ya usa este MP4.");
    } catch (error) {
      onError(
        error instanceof Error
          ? error.message
          : "No se pudo guardar el render en el clip.",
      );
    } finally {
      setSaving(false);
    }
  }

  const canRender = ready && Boolean(sourceFile) && !loadingSource && !exporting;
  const hookLength = hook.trim().length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-veru-paper/5 bg-veru-card/30 px-4 py-3">
        <button type="button" onClick={onClose} className="button-ghost px-3 py-2 text-xs">
          <IconArrowLeft size={13} />
          Volver
        </button>
        <span className="chip border-veru-ember/25 bg-veru-ember/10 text-veru-blush">
          <IconWand size={11} />
          Editor Virocut
        </span>
        <span className="text-[11px] leading-relaxed text-veru-paper/40">
          Encuadre, capas y subtítulos en el navegador
        </span>
      </div>

      <div className="grid flex-1 gap-5 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-3">
          <div className="relative mx-auto w-full max-w-[330px] overflow-hidden rounded-2xl border border-veru-paper/10 bg-black shadow-2xl">
            <canvas
              ref={canvasRef}
              width={PREVIEW_WIDTH}
              height={PREVIEW_HEIGHT}
              onPointerDown={handleCanvasPoint}
              className="block w-full cursor-crosshair"
              aria-label="Vista previa del clip"
            />
            {loadingSource && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 text-center">
                <IconLoader size={24} className="animate-spin text-veru-blush" />
                <p className="px-6 text-[11px] text-veru-paper/60">
                  Cargando video original…
                </p>
              </div>
            )}
            {!loadingSource && sourceError && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/85 px-6 text-center">
                <IconFilm size={28} className="text-veru-paper/25" />
                <p className="text-[11px] leading-relaxed text-rose-200">
                  {sourceError}
                </p>
              </div>
            )}
          </div>

          <video
            ref={videoRef}
            src={sourceUrl || undefined}
            preload="auto"
            playsInline
            onLoadedMetadata={handleLoaded}
            onEnded={() => {
              setPlaying(false);
              setTime(clipDuration);
            }}
            className="pointer-events-none absolute h-px w-px opacity-0"
          />

          <div className="flex items-center gap-2 rounded-2xl border border-veru-paper/10 bg-black/25 px-3 py-2">
            <button
              type="button"
              onClick={() => void togglePlay()}
              disabled={!ready}
              className="button-primary h-8 w-8 shrink-0 justify-center rounded-full p-0"
              aria-label={playing ? "Pausar" : "Reproducir"}
            >
              {playing ? (
                <span className="flex gap-[3px]">
                  <span className="h-3 w-[3px] rounded-sm bg-current" />
                  <span className="h-3 w-[3px] rounded-sm bg-current" />
                </span>
              ) : (
                <IconPlay size={13} />
              )}
            </button>
            <input
              type="range"
              min={0}
              max={clipDuration}
              step={0.01}
              value={Math.min(time, clipDuration)}
              onChange={(event) => handleSeek(Number(event.target.value))}
              disabled={!ready}
              className="min-w-0 flex-1 accent-veru-ember"
              aria-label="Posición del clip"
            />
            <span className="shrink-0 text-[10px] tabular-nums text-veru-paper/45">
              {formatTime(time)} / {formatTime(clipDuration)}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void handleExport()}
              disabled={!canRender}
              className="button-primary px-4 py-2.5 text-xs"
            >
              {exporting ? (
                <IconLoader size={13} className="animate-spin" />
              ) : (
                <IconScissors size={13} />
              )}
              {exporting
                ? `Renderizando ${Math.round(progress * 100)}%`
                : "Renderizar MP4"}
            </button>
            {resultUrl && (
              <a
                href={resultUrl}
                download={downloadName(clip.idx, `${clip.title ?? "clip"}-virocut`, "mp4")}
                className="button-ghost px-3 py-2.5 text-xs"
              >
                <IconDownload size={13} />
                Descargar
              </a>
            )}
            {resultBlob && (
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving}
                className="button-primary px-4 py-2.5 text-xs"
              >
                {saving ? (
                  <IconLoader size={13} className="animate-spin" />
                ) : (
                  <IconCheck size={13} />
                )}
                {saving
                  ? `Guardando ${saveProgress}%`
                  : "Guardar en Clipwise"}
              </button>
            )}
            <button type="button" onClick={resetLook} className="button-ghost px-3 py-2.5 text-xs">
              <IconRefresh size={13} />
              Restablecer
            </button>
          </div>

          {exporting && (
            <div className="h-1.5 overflow-hidden rounded-full bg-veru-paper/10">
              <div
                className="h-full rounded-full bg-veru-ember transition-[width]"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          )}

          {exportError && (
            <p className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-[11px] leading-relaxed text-rose-200">
              {exportError}
            </p>
          )}

          {savedMessage && (
            <p className="flex items-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-200">
              <IconCheck size={13} />
              {savedMessage}
            </p>
          )}

          {resultUrl && (
            <div className="rounded-2xl border border-veru-paper/10 bg-black/40 p-2">
              <video
                key={resultUrl}
                src={resultUrl}
                controls
                playsInline
                className="max-h-72 w-full rounded-xl bg-black object-contain"
              />
              <p className="px-2 pt-2 text-[10px] text-veru-paper/35">
                Render del navegador · 1080×1920 · H.264 + AAC
              </p>
            </div>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          <section className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-3.5">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-veru-paper/45">
                Plantilla
              </h4>
              <span className="text-[10px] text-veru-paper/30">9:16</span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {LAYOUTS.map((item) => {
                const active = template === item.value;
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setTemplate(item.value)}
                    aria-pressed={active}
                    className={`rounded-lg border px-2 py-1.5 text-left text-[10px] font-medium transition ${
                      active
                        ? "border-veru-ember/45 bg-veru-ember/15 text-veru-paper"
                        : "border-veru-paper/10 bg-black/20 text-veru-paper/55 hover:border-veru-paper/25 hover:text-veru-paper/85"
                    }`}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {(["blur", "black"] as const).map((item) => {
                const active = background === item;
                return (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setBackground(item)}
                    aria-pressed={active}
                    className={`rounded-lg border px-2 py-1.5 text-[10px] font-medium transition ${
                      active
                        ? "border-veru-ember/45 bg-veru-ember/15 text-veru-paper"
                        : "border-veru-paper/10 bg-black/20 text-veru-paper/55 hover:border-veru-paper/25 hover:text-veru-paper/85"
                    }`}
                  >
                    {item === "blur" ? "Fondo desenfocado" : "Fondo negro"}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-3.5">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-veru-paper/45">
                Subtítulos
              </h4>
              <button
                type="button"
                onClick={() => setCaptionsEnabled((value) => !value)}
                aria-pressed={captionsEnabled}
                className={`rounded-full border px-2 py-0.5 text-[9px] font-semibold transition ${
                  captionsEnabled
                    ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
                    : "border-veru-paper/15 bg-black/20 text-veru-paper/40"
                }`}
              >
                {captionsEnabled ? "Activos" : "Ocultos"}
              </button>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              {CAPTION_STYLES.map((item) => {
                const active = captionStyle === item.value;
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setCaptionStyle(item.value)}
                    aria-pressed={active}
                    className={`rounded-lg border px-1.5 py-1.5 text-[10px] font-medium transition ${
                      active
                        ? "border-veru-ember/45 bg-veru-ember/15 text-veru-paper"
                        : "border-veru-paper/10 bg-black/20 text-veru-paper/55 hover:border-veru-paper/25 hover:text-veru-paper/85"
                    }`}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-veru-paper/30">
              {words.length
                ? `${words.length} palabras sincronizadas · grupos de 3`
                : "Este clip no tiene palabras sincronizadas. El render saldrá sin subtítulos."}
            </p>
          </section>

          <section className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-3.5">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-veru-paper/45">
                Gancho
              </h4>
              <span className="text-[9px] tabular-nums text-veru-paper/30">
                {hookLength}/160
              </span>
            </div>
            <textarea
              value={hook}
              maxLength={160}
              rows={2}
              onChange={(event) => setHook(event.target.value)}
              placeholder="Frase que abre el clip"
              className="field mt-2 px-3 py-2 text-xs"
            />
            <div className="mt-2 grid grid-cols-4 gap-1.5">
              {HOOK_STYLES.map((item) => {
                const active = hookStyle === item.value;
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setHookStyle(item.value)}
                    aria-pressed={active}
                    className={`rounded-lg border px-1 py-1.5 text-[10px] font-medium transition ${
                      active
                        ? "border-veru-ember/45 bg-veru-ember/15 text-veru-paper"
                        : "border-veru-paper/10 bg-black/20 text-veru-paper/55 hover:border-veru-paper/25 hover:text-veru-paper/85"
                    }`}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-3.5">
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-veru-paper/45">
              Encuadre
            </h4>
            <p className="mt-1 text-[10px] leading-relaxed text-veru-paper/30">
              Toca la vista previa para mover el foco del recorte.
            </p>
            <label className="mt-2 block">
              <span className="label-xs">Horizontal · {Math.round(focusX * 100)}%</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={focusX}
                onChange={(event) => setFocusX(Number(event.target.value))}
                className="mt-1 w-full accent-veru-ember"
              />
            </label>
            <label className="mt-2 block">
              <span className="label-xs">Vertical · {Math.round(focusY * 100)}%</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={focusY}
                onChange={(event) => setFocusY(Number(event.target.value))}
                className="mt-1 w-full accent-veru-ember"
              />
            </label>
          </section>

          <section className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-3.5">
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-veru-paper/45">
              Marca de agua
            </h4>
            <input
              type="text"
              value={watermark}
              maxLength={80}
              onChange={(event) => setWatermark(event.target.value)}
              placeholder="Tu marca"
              className="field mt-2 px-3 py-2 text-xs"
            />
            <p className="mt-1.5 text-[10px] leading-relaxed text-veru-paper/30">
              Se dibuja arriba a la derecha. Déjala vacía para ocultarla.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
