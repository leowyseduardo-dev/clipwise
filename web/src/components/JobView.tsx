import { useEffect, useMemo, useState } from "react";

import type { Clip, Job, PublishPlatform } from "../lib/types";
import { CATEGORY_INFO, CATEGORY_ORDER, categoryInfo } from "../lib/categories";
import { formatDate, formatLanguage, formatScore, formatTime } from "../lib/format";
import { STAGES, stageStatus } from "../lib/stages";
import { ClipCard } from "./ClipCard";
import {
  IconAlert,
  IconCheck,
  IconDownload,
  IconFilm,
  IconLoader,
  IconRefresh,
  IconTrash,
  IconX,
} from "./icons";

const JOB_STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  processing: "Procesando",
  ready: "Listo",
  failed: "Error",
  cancelled: "Cancelado",
};

interface JobViewProps {
  job: Job;
  onCancel: () => void;
  onRetryJob: () => void;
  onDelete: () => void;
  onOpenClip: (clip: Clip, platform?: PublishPlatform) => void;
  onRetryClip: (clip: Clip) => void;
  retryingClipId: string | null;
  retryingJob: boolean;
}

export function JobView({
  job,
  onCancel,
  onRetryJob,
  onDelete,
  onOpenClip,
  onRetryClip,
  retryingClipId,
  retryingJob,
}: JobViewProps) {
  const clips = job.clips ?? [];
  const [categoryFilter, setCategoryFilter] = useState("all");
  const readyClips = clips.filter((clip) => clip.status === "ready");
  const active = job.status === "queued" || job.status === "processing";
  const failed = job.status === "failed" || job.status === "cancelled";
  const averageScore = readyClips.length
    ? readyClips.reduce((sum, clip) => sum + (clip.score ?? 0), 0) / readyClips.length
    : null;
  const availableCategories = useMemo(
    () =>
      CATEGORY_ORDER.filter((category) =>
        clips.some((clip) => categoryInfo(clip.category)?.id === category),
      ),
    [clips],
  );
  const visibleClips = useMemo(
    () =>
      categoryFilter === "all"
        ? clips
        : clips.filter((clip) => categoryInfo(clip.category)?.id === categoryFilter),
    [categoryFilter, clips],
  );

  useEffect(() => {
    if (
      categoryFilter !== "all" &&
      !availableCategories.some((category) => category === categoryFilter)
    ) {
      setCategoryFilter("all");
    }
  }, [availableCategories, categoryFilter]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-veru-paper/35">
              Trabajo activo
            </p>
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                job.status === "ready"
                  ? "border-emerald-400/25 bg-emerald-500/10 text-emerald-300"
                  : failed
                    ? "border-rose-400/25 bg-rose-500/10 text-rose-300"
                    : "border-veru-ember/25 bg-veru-ember/10 text-veru-ember"
              }`}
            >
              {active && <IconLoader size={10} className="animate-spin" />}
              {JOB_STATUS_LABEL[job.status] ?? job.status}
            </span>
          </div>
          <h2 className="mt-1.5 truncate text-2xl font-semibold tracking-tight text-veru-paper">
            {job.title}
          </h2>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-veru-paper/50">
            <span className="chip">
              {({ youtube: "YouTube", kick: "Kick", twitch: "Twitch", upload: "Archivo subido" })[job.source_type]}
            </span>
            {job.streamer ? (
              <span className="chip border-veru-ember/25 bg-veru-ember/10 text-veru-blush">
                {job.streamer}
              </span>
            ) : null}
            {job.game ? <span className="chip">{job.game}</span> : null}
            {job.long_mode ? (
              <span className="chip border-veru-blush/25 bg-veru-blush/10 text-veru-blush">
                Stream largo
              </span>
            ) : null}
            {job.duration ? <span className="chip">{formatTime(job.duration)}</span> : null}
            {job.language ? (
              <span className="chip">{formatLanguage(job.language)}</span>
            ) : null}
            {job.has_music ? <span className="chip">Con música</span> : null}
            {readyClips.length > 0 && (
              <span className="chip">
                {readyClips.length} clips · media {formatScore(averageScore)}
              </span>
            )}
            <span className="text-veru-paper/25">{formatDate(job.created_at)}</span>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {readyClips.length > 0 && (
            <a
              href={`/api/jobs/${job.id}/download.zip`}
              className="button-primary py-2.5 text-xs"
            >
              <IconDownload size={15} />
              Descargar todo
            </a>
          )}
          {failed && clips.length === 0 && (
            <button
              type="button"
              onClick={onRetryJob}
              disabled={retryingJob}
              className="button-ghost"
            >
              <IconRefresh size={14} className={retryingJob ? "animate-spin" : ""} />
              {retryingJob ? "Reintentando…" : "Reintentar"}
            </button>
          )}
          {active && (
            <button type="button" onClick={onCancel} className="button-ghost">
              <IconX size={14} />
              Cancelar
            </button>
          )}
          <DeleteJobButton onDelete={onDelete} />
        </div>
      </div>

      {job.status !== "ready" && (
        <div
          className={`panel p-5 ${
            failed ? "border-rose-400/20 bg-rose-950/10" : ""
          }`}
        >
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm font-medium text-veru-paper/80">
              {failed
                ? job.status === "cancelled"
                  ? "Procesamiento cancelado"
                  : "El procesamiento se detuvo"
                : "Analizando y editando tu video"}
            </p>
            <span className="text-[11px] tabular-nums text-veru-paper/35">
              {Math.round(job.progress)}%
            </span>
          </div>

          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-veru-paper/10">
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${
                failed
                  ? "bg-rose-400/70"
                  : "bg-veru-ember"
              }`}
              style={{ width: `${Math.max(2, Math.min(100, job.progress))}%` }}
            />
          </div>

          {failed && job.error && (
            <p className="mt-3 flex items-start gap-2 rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-xs leading-relaxed text-rose-200">
              <IconAlert size={14} className="mt-0.5 shrink-0" />
              <span className="break-words">{job.error}</span>
            </p>
          )}

          {failed && readyClips.length > 0 && (
            <p className="mt-3 text-[11px] leading-relaxed text-emerald-200/80">
              El trabajo se detuvo, pero {readyClips.length === 1 ? "el clip ya renderizado sigue disponible" : "los clips ya renderizados siguen disponibles"}. Usa «Descargar todo» o abre cada clip.
            </p>
          )}

          {failed && clips.length === 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <a href="#trabajos" className="button-ghost">
                <IconFilm size={14} />
                Ver trabajos anteriores
              </a>
              <span className="text-[11px] leading-relaxed text-veru-paper/35">
                Los clips de otros trabajos siguen disponibles aunque este haya fallado.
              </span>
            </div>
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StageList job={job} />
          </div>

          {!failed && clips.length === 0 && (
            <p className="mt-4 text-[11px] leading-relaxed text-veru-paper/35">
              La transcripción y el análisis pueden tardar varios minutos según
              la duración del video. La primera ejecución descarga el modelo de
              voz de Whisper.
            </p>
          )}

          {job.long_mode && !failed && (
            <p className="mt-3 text-[11px] leading-relaxed text-veru-blush/75">
              Fuente larga: el audio se transcribe una vez y cada clip se
              descarga por separado justo antes de renderizarse.
            </p>
          )}
        </div>
      )}

      {clips.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold tracking-tight text-veru-paper/80">
              Clips generados{" "}
              <span className="font-normal text-veru-paper/35">
                ({readyClips.length}/{clips.length} listos)
              </span>
            </h3>
            {readyClips.length > 0 && (
              <span className="hidden text-[11px] text-veru-paper/35 sm:block">
                Pulsa un clip para previsualizar, editar subtítulos o descargar.
              </span>
            )}
          </div>

          {availableCategories.length > 1 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setCategoryFilter("all")}
                aria-pressed={categoryFilter === "all"}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide transition ${
                  categoryFilter === "all"
                    ? "border-veru-ember/40 bg-veru-ember/15 text-veru-blush"
                    : "border-veru-paper/10 bg-veru-paper/[0.03] text-veru-paper/50 hover:border-veru-paper/20 hover:text-veru-paper/80"
                }`}
              >
                Todos
                <span className="tabular-nums opacity-70">{clips.length}</span>
              </button>
              {availableCategories.map((category) => {
                const info = CATEGORY_INFO[category];
                const count = clips.filter(
                  (clip) => categoryInfo(clip.category)?.id === category,
                ).length;
                return (
                  <button
                    key={category}
                    type="button"
                    onClick={() => setCategoryFilter(category)}
                    aria-pressed={categoryFilter === category}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide transition ${
                      categoryFilter === category
                        ? info.className
                        : "border-veru-paper/10 bg-veru-paper/[0.03] text-veru-paper/50 hover:border-veru-paper/20 hover:text-veru-paper/80"
                    }`}
                  >
                    {info.label}
                    <span className="tabular-nums opacity-70">{count}</span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visibleClips.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                onOpen={(platform) => onOpenClip(clip, platform)}
                onRetry={() => onRetryClip(clip)}
                retrying={retryingClipId === clip.id}
              />
            ))}
          </div>
          {visibleClips.length === 0 && (
            <div className="panel px-6 py-8 text-center text-sm text-veru-paper/50">
              No hay clips en esta categoría.
            </div>
          )}
        </div>
      )}

      {job.status === "ready" && clips.length === 0 && (
        <div className="panel flex flex-col items-center gap-2 px-6 py-10 text-center">
          <IconFilm size={22} className="text-veru-paper/35" />
          <p className="text-sm text-veru-paper/70">No se generaron clips.</p>
          <p className="max-w-md text-xs leading-relaxed text-veru-paper/35">
            El video puede no contener voz o ser demasiado corto. Prueba con un
            archivo más largo o desactiva el recorte de silencios.
          </p>
        </div>
      )}
    </div>
  );
}

function StageList({ job }: { job: Job }) {
  const { activeIndex, completed } = stageStatus(job.stage, job.status);
  const stopped = job.status === "failed" || job.status === "cancelled";

  return (
    <>
      {STAGES.map((stage, index) => {
        const done = completed || index < activeIndex;
        const current = !completed && index === activeIndex;
        const broke = current && stopped;
        return (
          <div key={stage.key} className="flex items-start gap-2.5">
            <span
              className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold ${
                broke
                  ? "border-rose-400/40 bg-rose-500/15 text-rose-300"
                  : done
                    ? "border-emerald-400/30 bg-emerald-500/15 text-emerald-300"
                    : current
                      ? "border-veru-ember/40 bg-veru-ember/15 text-veru-blush"
                      : "border-veru-paper/10 bg-veru-paper/5 text-veru-paper/35"
              }`}
            >
              {broke ? (
                <IconAlert size={12} />
              ) : done ? (
                <IconCheck size={12} />
              ) : current ? (
                <IconLoader size={12} className="animate-spin" />
              ) : (
                index + 1
              )}
            </span>
            <div className="min-w-0">
              <p
                className={`text-xs font-medium ${
                  done || current ? "text-veru-paper/80" : "text-veru-paper/35"
                }`}
              >
                {stage.label}
              </p>
              <p className="truncate text-[10px] leading-relaxed text-veru-paper/35">
                {stage.detail}
              </p>
            </div>
          </div>
        );
      })}
    </>
  );
}

function DeleteJobButton({ onDelete }: { onDelete: () => void }) {
  return (
    <button
      type="button"
      onClick={() => {
        if (window.confirm("¿Eliminar este trabajo y todos sus clips renderizados?")) {
          onDelete();
        }
      }}
      className="button-ghost px-2.5"
      aria-label="Eliminar trabajo"
      title="Eliminar trabajo"
    >
      <IconTrash size={15} />
    </button>
  );
}
