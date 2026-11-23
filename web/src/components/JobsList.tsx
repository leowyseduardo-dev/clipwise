import type { Job } from "../lib/types";
import { formatDate, formatTime } from "../lib/format";
import { IconFilm, IconLoader } from "./icons";

const STATUS_STYLE: Record<string, string> = {
  queued: "border-veru-paper/10 bg-veru-paper/5 text-veru-paper/50",
  processing: "border-veru-ember/25 bg-veru-ember/10 text-veru-ember",
  ready: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  cancelled: "border-amber-200 bg-amber-50 text-amber-700",
};

const STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  processing: "Procesando",
  ready: "Listo",
  failed: "Error",
  cancelled: "Cancelado",
};

export function JobsList({
  jobs,
  activeJobId,
  onSelect,
}: {
  jobs: Job[];
  activeJobId: string | null;
  onSelect: (jobId: string) => void;
}) {
  if (!jobs.length) return null;

  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-veru-paper/80">
            Trabajos recientes
          </h2>
          <p className="mt-0.5 text-[11px] text-veru-paper/35">
            Vuelve a cualquier análisis para descargar o editar sus clips.
          </p>
        </div>
        <span className="hidden text-[11px] text-veru-paper/35 sm:block">
          {jobs.length} {jobs.length === 1 ? "trabajo" : "trabajos"}
        </span>
      </div>

      <div className="grid gap-2">
        {jobs.map((job) => {
          const active = job.id === activeJobId;
          const processing = job.status === "queued" || job.status === "processing";
          const clips = job.clips_target ?? 0;
          return (
            <button
              key={job.id}
              type="button"
              onClick={() => onSelect(job.id)}
              className={`flex w-full items-center gap-3 rounded-2xl border px-3.5 py-3 text-left transition ${
                active
                  ? "border-veru-ember/35 bg-veru-ember/[0.08]"
                  : "border-veru-paper/10 bg-veru-paper/[0.025] hover:border-veru-paper/20 hover:bg-veru-paper/[0.05]"
              }`}
            >
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border ${
                  processing
                    ? "border-veru-ember/25 bg-veru-ember/10 text-veru-ember"
                    : "border-veru-paper/10 bg-veru-paper/5 text-veru-paper/50"
                }`}
              >
                {processing ? (
                  <IconLoader size={16} className="animate-spin" />
                ) : (
                  <IconFilm size={16} />
                )}
              </span>

              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium text-veru-paper/90">
                  {job.title || "Video sin título"}
                </span>
                <span className="mt-0.5 block truncate text-[10px] text-veru-paper/35">
                  {formatDate(job.created_at)} ·{" "}
                  {({ youtube: "YouTube", kick: "Kick", twitch: "Twitch", upload: "Archivo" })[job.source_type]} ·{" "}
                  {formatTime(job.duration)}
                  {clips > 0 ? ` · ${clips} clips` : ""}
                </span>
              </span>

              <span
                className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                  STATUS_STYLE[job.status] ?? STATUS_STYLE.queued
                }`}
              >
                {STATUS_LABEL[job.status] ?? job.status}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
