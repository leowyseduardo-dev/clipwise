import { useEffect, useState } from "react";

import { regenerateClipDescription, saveSubtitles } from "../lib/api";
import { categoryInfo } from "../lib/categories";
import {
  downloadName,
  formatScore,
  formatTime,
  sameText,
  scoreTone,
} from "../lib/format";
import type {
  Clip,
  LayoutOption,
  PublishPlatform,
  ScoreBreakdown,
  SubtitleCue,
  SubtitleStyleOption,
} from "../lib/types";
import { PublishingPanel } from "./PublishingPanel";
import { ClipWorkbench } from "./ClipWorkbench";
import { ScoreRing } from "./ScoreRing";
import {
  IconAlert,
  IconCheck,
  IconCopy,
  IconDownload,
  IconFilm,
  IconLoader,
  IconPlay,
  IconRefresh,
  IconTikTok,
  IconWand,
  IconX,
  IconYouTube,
} from "./icons";

interface DraftCue {
  start: number;
  end: number;
  text: string;
}

interface ClipModalProps {
  clip: Clip;
  initialPlatform?: PublishPlatform;
  onClose: () => void;
  onUpdated: (clip: Clip, message?: string) => void;
  onError: (message: string) => void;
  onRetry: () => void;
  retrying: boolean;
  subtitleStyles?: SubtitleStyleOption[];
  layouts?: LayoutOption[];
}

const LEGACY_BREAKDOWN: { key: keyof ScoreBreakdown; label: string }[] = [
  { key: "hook", label: "Gancho" },
  { key: "clarity", label: "Claridad" },
  { key: "interest", label: "Interés" },
  { key: "pacing", label: "Ritmo" },
  { key: "retention", label: "Retención" },
];

const ADVANCED_BREAKDOWN: { key: keyof ScoreBreakdown; label: string }[] = [
  { key: "intensity", label: "Intensidad" },
  { key: "surprise", label: "Sorpresa" },
  { key: "humor", label: "Humor" },
  { key: "originality", label: "Originalidad" },
  { key: "importance", label: "Importancia" },
  { key: "conversation", label: "Conversación" },
  { key: "entertainment", label: "Entretenimiento" },
  { key: "hook", label: "Gancho" },
  { key: "retention", label: "Retención" },
  { key: "context", label: "Contexto" },
];

function cuesToDrafts(cues: SubtitleCue[]): DraftCue[] {
  return cues
    .filter((cue) => typeof cue.text === "string" && cue.text.trim().length > 0)
    .map((cue) => ({ start: cue.start, end: cue.end, text: cue.text }));
}

export function ClipModal({
  clip,
  initialPlatform,
  onClose,
  onUpdated,
  onError,
  onRetry,
  retrying,
  subtitleStyles,
  layouts,
}: ClipModalProps) {
  const [showEditor, setShowEditor] = useState(false);
  const [drafts, setDrafts] = useState<DraftCue[]>(() =>
    cuesToDrafts(clip.subtitles.cues ?? []),
  );
  const [saving, setSaving] = useState(false);
  const [copiedDescription, setCopiedDescription] = useState(false);
  const [descriptionTab, setDescriptionTab] = useState<PublishPlatform>(
    initialPlatform ?? "youtube",
  );
  const [regenerating, setRegenerating] = useState(false);

  const tone = scoreTone(clip.score);
  const category = categoryInfo(clip.category);
  const advancedScore = clip.score_breakdown.intensity !== undefined;
  const breakdown = advancedScore ? ADVANCED_BREAKDOWN : LEGACY_BREAKDOWN;
  const processing = clip.status === "queued" || clip.status === "rendering";
  const cues = clip.subtitles.cues ?? [];
  const noSpeech = cues.length === 0;
  const descriptionText =
    descriptionTab === "youtube"
      ? clip.description || clip.caption || ""
      : clip.caption || clip.description || "";

  useEffect(() => {
    setDrafts(cuesToDrafts(clip.subtitles.cues ?? []));
  }, [clip.updated_at]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  async function copyDescription() {
    if (!descriptionText) return;
    try {
      await navigator.clipboard.writeText(descriptionText);
      setCopiedDescription(true);
      window.setTimeout(() => setCopiedDescription(false), 1800);
    } catch {
      onError("El navegador bloqueó el acceso al portapapeles.");
    }
  }

  async function handleRegenerateDescription() {
    setRegenerating(true);
    try {
      const updated = await regenerateClipDescription(clip.id);
      onUpdated(updated, "Título y textos revisados con el contenido del clip.");
      setCopiedDescription(false);
    } catch (error) {
      onError(
        error instanceof Error
          ? error.message
          : "No se pudo regenerar la descripción.",
      );
    } finally {
      setRegenerating(false);
    }
  }

  async function handleSave() {
    const cleaned = drafts
      .map((cue) => ({
        start: Math.max(0, cue.start),
        end: Math.max(0, cue.end),
        text: cue.text.trim(),
      }))
      .filter((cue) => cue.text.length > 0);

    if (!cleaned.length) {
      onError("Añade al menos una línea de subtítulo antes de guardar.");
      return;
    }

    setSaving(true);
    try {
      const updated = await saveSubtitles(clip.id, cleaned);
      onUpdated(updated);
      setShowEditor(false);
    } catch (error) {
      onError(
        error instanceof Error
          ? error.message
          : "No se pudieron guardar los subtítulos.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/75 backdrop-blur-md sm:items-center sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Clip ${clip.idx + 1}: ${clip.title ?? ""}`}
        className="relative flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-t-3xl border border-veru-paper/10 bg-veru-bg shadow-2xl sm:rounded-3xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-veru-paper/5 bg-veru-card/40 px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="chip shrink-0 border-veru-ember/25 bg-veru-ember/10 text-veru-blush">
              Clip {String(clip.idx + 1).padStart(2, "0")}
            </span>
            <span className="chip shrink-0">{formatTime(clip.duration)}</span>
            <span className={`chip shrink-0 ${tone.border} ${tone.bg} ${tone.text}`}>
              {formatScore(clip.score)}/100 · {tone.label}
            </span>
            {category && (
              <span className={`chip shrink-0 ${category.className}`}>
                {category.label}
              </span>
            )}
            {processing && (
              <span className="chip shrink-0 border-veru-ember/25 bg-veru-ember/10 text-veru-blush">
                <IconLoader size={11} className="animate-spin" />
                Regenerando
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl p-2 text-veru-paper/50 transition hover:bg-veru-paper/10 hover:text-veru-paper"
            aria-label="Cerrar"
            autoFocus
          >
            <IconX size={18} />
          </button>
        </div>

        <div className="grid flex-1 overflow-y-auto lg:grid-cols-[minmax(0,370px)_minmax(0,1fr)]">
          <div className="border-b border-veru-paper/5 bg-black/30 p-4 lg:border-b-0 lg:border-r">
            <div className="overflow-hidden rounded-2xl border border-veru-paper/10 bg-black">
              {clip.video_url ? (
                <video
                  key={clip.video_url}
                  src={clip.video_url}
                  poster={clip.thumb_url ?? undefined}
                  controls
                  playsInline
                  className="max-h-[56vh] w-full bg-black object-contain"
                />
              ) : (
                <div className="flex aspect-[9/16] max-h-[56vh] w-full flex-col items-center justify-center gap-3 bg-[radial-gradient(circle_at_50%_25%,rgba(160,76,245,0.22),transparent_65%)] text-center">
                  <IconFilm size={30} className="text-veru-paper/25" />
                  <p className="px-6 text-xs leading-relaxed text-veru-paper/35">
                    {clip.status === "failed"
                      ? "Este clip no tiene render disponible. Reintenta la edición."
                      : "El video estará disponible cuando termine el render."}
                  </p>
                  {clip.status === "failed" && (
                    <button
                      type="button"
                      onClick={onRetry}
                      disabled={retrying}
                      className="button-ghost"
                    >
                      <IconRefresh
                        size={14}
                        className={retrying ? "animate-spin" : ""}
                      />
                      Reintentar render
                    </button>
                  )}
                </div>
              )}
            </div>

            <div className="mt-3 flex flex-col gap-2">
              {clip.video_url ? (
                <a
                  href={clip.video_url}
                  download={downloadName(clip.idx, clip.title, "mp4")}
                  className="button-primary py-2.5 text-xs"
                >
                  <IconDownload size={15} />
                  Descargar MP4 (1080×1920)
                </a>
              ) : (
                <span className="button-primary cursor-not-allowed py-2.5 text-xs opacity-40">
                  <IconDownload size={15} />
                  Descargar MP4
                </span>
              )}
              {!noSpeech && (
                <a
                  href={`/api/clips/${clip.id}/subtitles.srt`}
                  download={downloadName(clip.idx, clip.title, "srt")}
                  className="button-ghost justify-center"
                >
                  <IconDownload size={13} />
                  Descargar subtítulos (.srt)
                </a>
              )}
            </div>

            {clip.status === "failed" && clip.error && (
              <p className="mt-3 flex items-start gap-2 rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-[11px] leading-relaxed text-rose-200">
                <IconAlert size={13} className="mt-0.5 shrink-0" />
                <span className="break-words">{clip.error}</span>
              </p>
            )}

            {processing && (
              <p className="mt-3 flex items-center gap-2 text-[11px] text-veru-blush/80">
                <IconLoader size={12} className="animate-spin" />
                Aplicando subtítulos y re-renderizando el clip…
              </p>
            )}
          </div>

          <div className="space-y-5 p-5">
            <div>
              <h3 className="text-lg font-semibold leading-snug tracking-tight text-veru-paper">
                {clip.title || `Clip ${clip.idx + 1}`}
              </h3>
              {clip.hook && !sameText(clip.hook, clip.title) && (
                <p className="mt-1.5 text-sm leading-relaxed text-veru-paper/70">
                  {clip.hook}
                </p>
              )}
              {clip.reason && (
                <p className="mt-2 text-[11px] leading-relaxed text-veru-paper/35">
                  {clip.reason}
                </p>
              )}
              {clip.tags.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {clip.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-veru-paper/10 bg-veru-paper/5 px-2 py-0.5 text-[10px] text-veru-paper/50"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {clip.overlay?.context && (
                <div className="mt-3 rounded-2xl border border-veru-ember/15 bg-veru-ember/[0.06] px-3.5 py-2.5">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-veru-blush/70">
                    Contexto en pantalla
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-veru-paper">
                      {clip.overlay.context}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[10px] leading-relaxed text-veru-paper/35">
                    Se muestra durante los primeros{" "}
                    {clip.overlay?.context_seconds
                      ? Math.round(clip.overlay.context_seconds)
                      : 5}{" "}
                    segundos del clip.
                  </p>
                </div>
              )}
            </div>

            <ClipWorkbench key={clip.id} clip={clip} busy={regenerating} onUpdated={onUpdated} onError={onError} styles={subtitleStyles} layouts={layouts} />

            {Boolean(clip.overlay?.voices?.length) && <details className="studio-box"><summary>Intervenciones por voz estimada</summary>{clip.overlay!.voices!.map((turn,index)=><p key={index}>Voz {turn.voice} · {formatTime(Math.max(turn.start,clip.start))}–{formatTime(Math.min(turn.end,clip.end))}</p>)}</details>}
            <PublishingPanel
              clip={clip}
              initialPlatform={initialPlatform}
              onError={onError}
            />

            <div className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-4">
              <div className="flex items-center gap-4">
                <ScoreRing score={clip.score} size={78} stroke={6} />
                <div>
                  <p className="text-[10px] font-medium uppercase tracking-[0.2em] text-veru-paper/35">
                    Puntuación editorial
                  </p>
                  <p className={`mt-0.5 text-sm font-semibold ${tone.text}`}>
                    {tone.label}
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-veru-paper/35">
                    {advancedScore
                      ? "Intensidad, sorpresa, humor, contexto y retención."
                      : "Gancho, claridad, interés, ritmo y retención."}
                  </p>
                </div>
              </div>
              <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
                {breakdown.map((item) => {
                  const value = Math.max(
                    0,
                    Math.min(100, Number(clip.score_breakdown[item.key] ?? 0)),
                  );
                  return (
                    <div key={item.key}>
                      <div className="mb-1 flex items-center justify-between text-[10px] text-veru-paper/35">
                        <span>{item.label}</span>
                        <span className="tabular-nums">{Math.round(value)}</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-veru-paper/10">
                        <div
                          className="h-full rounded-full bg-veru-ember"
                          style={{ width: `${value}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-veru-paper/50">
                    Texto de publicación
                  </h4>
                  <p className="mt-1 text-[10px] leading-relaxed text-veru-paper/35">
                    Explica el conflicto, la cita y lo que destaca. Distinto por
                    plataforma.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRegenerateDescription()}
                  disabled={regenerating}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-veru-paper/50 transition hover:bg-veru-paper/5 hover:text-veru-paper/90 disabled:opacity-40"
                >
                  {regenerating ? (
                    <IconLoader size={12} className="animate-spin" />
                  ) : (
                    <IconRefresh size={12} />
                  )}
                  {regenerating ? "Revisando…" : "Revisar título y textos"}
                </button>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-1 rounded-xl border border-veru-paper/10 bg-black/20 p-1">
                {(["youtube", "tiktok"] as PublishPlatform[]).map((id) => {
                  const TabIcon = id === "youtube" ? IconYouTube : IconTikTok;
                  const active = descriptionTab === id;
                  const activeClass =
                    id === "youtube"
                      ? "border-rose-400/40 bg-rose-500/15 text-rose-100"
                      : "border-veru-ember/40 bg-veru-ember/15 text-veru-paper";
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => {
                        setDescriptionTab(id);
                        setCopiedDescription(false);
                      }}
                      aria-pressed={active}
                      className={`inline-flex items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-[10px] font-semibold transition ${
                        active
                          ? activeClass
                          : "border-transparent text-veru-paper/50 hover:bg-veru-paper/5 hover:text-veru-paper/80"
                      }`}
                    >
                      <TabIcon size={12} />
                      {id === "youtube" ? "YouTube" : "TikTok"}
                    </button>
                  );
                })}
              </div>

              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="text-[10px] text-veru-paper/35">
                  {descriptionTab === "youtube"
                    ? "Descripción larga con contexto y hashtags"
                    : "Caption corto con contexto y hashtags"}
                </span>
                <button
                  type="button"
                  onClick={() => void copyDescription()}
                  disabled={!descriptionText}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-veru-paper/50 transition hover:bg-veru-paper/5 hover:text-veru-paper/90 disabled:opacity-40"
                >
                  {copiedDescription ? (
                    <IconCheck size={11} />
                  ) : (
                    <IconCopy size={11} />
                  )}
                  {copiedDescription ? "Copiado" : "Copiar"}
                </button>
              </div>

              <p className="mt-2 whitespace-pre-wrap rounded-xl border border-veru-paper/10 bg-black/25 px-3.5 py-3 text-xs leading-relaxed text-veru-paper/70">
                {descriptionText ||
                  "La descripción se generará al analizar el clip."}
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-veru-paper/50">
                  Subtítulos
                </h4>
                {!noSpeech && clip.status !== "queued" && clip.status !== "rendering" && (
                  <button
                    type="button"
                    onClick={() => setShowEditor((value) => !value)}
                    className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] text-veru-paper/70 transition hover:bg-veru-paper/5 hover:text-veru-paper"
                  >
                    <IconWand size={12} />
                    {showEditor ? "Ocultar editor" : "Editar texto"}
                  </button>
                )}
              </div>

              {noSpeech ? (
                <p className="mt-2 rounded-2xl border border-veru-paper/10 bg-black/25 px-4 py-3 text-xs leading-relaxed text-veru-paper/35">
                  No se detectó voz en este fragmento, así que el clip se genera
                  sin subtítulos. Puedes descargarlo igualmente.
                </p>
              ) : showEditor ? (
                <div className="mt-2 space-y-2">
                  <div className="max-h-64 space-y-2 overflow-y-auto rounded-2xl border border-veru-paper/10 bg-black/25 p-3">
                    {drafts.map((cue, index) => (
                      <div key={index} className="flex items-start gap-2">
                        <span className="w-10 shrink-0 pt-2 text-right text-[10px] tabular-nums text-veru-paper/35">
                          {formatTime(cue.start)}
                        </span>
                        <input
                          type="text"
                          value={cue.text}
                          maxLength={300}
                          onChange={(event) => {
                            const value = event.target.value;
                            setDrafts((previous) =>
                              previous.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, text: value } : item,
                              ),
                            );
                          }}
                          className="field px-3 py-2 text-xs"
                        />
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[10px] leading-relaxed text-veru-paper/35">
                      El video se re-renderiza al guardar. El texto conserva los
                      tiempos de cada línea.
                    </p>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setDrafts(cuesToDrafts(cues));
                          setShowEditor(false);
                        }}
                        className="button-ghost"
                      >
                        Cancelar
                      </button>
                      <button
                        type="button"
                        onClick={handleSave}
                        disabled={saving}
                        className="button-primary px-4 py-2 text-xs"
                      >
                        {saving ? (
                          <IconLoader size={13} className="animate-spin" />
                        ) : (
                          <IconCheck size={13} />
                        )}
                        {saving ? "Guardando…" : "Guardar y regenerar"}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-2 rounded-2xl border border-veru-paper/10 bg-black/25 px-4 py-3">
                  {cues.slice(0, 4).map((cue, index) => (
                    <p
                      key={index}
                      className="line-clamp-2 text-xs leading-relaxed text-veru-paper/70"
                    >
                      {cue.text}
                    </p>
                  ))}
                  {cues.length > 4 && (
                    <p className="mt-1 text-[10px] text-veru-paper/35">
                      +{cues.length - 4} líneas más · {cues.length} en total
                    </p>
                  )}
                  {cues.length <= 4 && (
                    <p className="mt-1 text-[10px] text-veru-paper/35">
                      {cues.length} {cues.length === 1 ? "línea" : "líneas"} ·
                      sincronizadas palabra a palabra
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-veru-paper/5 pt-3 text-[10px] text-veru-paper/35">
              <span className="inline-flex items-center gap-1">
                <IconPlay size={10} />
                9:16 · 1080×1920
              </span>
              <span className="text-veru-paper/20">·</span>
              <span>H.264 + AAC</span>
              <span className="text-veru-paper/20">·</span>
              <span>Subtítulos incrustados</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
