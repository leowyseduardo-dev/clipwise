import type { Clip, PublishPlatform } from "../lib/types";
import { categoryInfo } from "../lib/categories";
import {
  downloadName,
  formatScore,
  formatTime,
  sameText,
  scoreTone,
} from "../lib/format";
import { ScoreRing } from "./ScoreRing";
import {
  IconAlert,
  IconDownload,
  IconFilm,
  IconLoader,
  IconPlay,
  IconRefresh,
  IconTikTok,
  IconWand,
  IconYouTube,
} from "./icons";

const CLIP_STATUS: Record<string, { label: string; className: string }> = {
  queued: {
    label: "En cola",
    className: "border-veru-paper/15 bg-black/60 text-veru-paper/70",
  },
  rendering: {
    label: "Editando…",
    className: "border-veru-ember/30 bg-black/70 text-veru-blush",
  },
  ready: {
    label: "Listo",
    className: "border-emerald-400/30 bg-emerald-950/70 text-emerald-200",
  },
  failed: {
    label: "Error",
    className: "border-rose-400/30 bg-rose-950/70 text-rose-200",
  },
};

export function ClipCard({
  clip,
  onOpen,
  onRetry,
  retrying,
}: {
  clip: Clip;
  onOpen: (platform?: PublishPlatform) => void;
  onRetry: () => void;
  retrying: boolean;
}) {
  const tone = scoreTone(clip.score);
  const category = categoryInfo(clip.category);
  const status = CLIP_STATUS[clip.status] ?? CLIP_STATUS.queued;
  const processing = clip.status === "queued" || clip.status === "rendering";
  const canOpen = Boolean(clip.video_url);

  return (
    <article className="group flex flex-col overflow-hidden rounded-3xl border border-veru-paper/10 bg-veru-paper/[0.03] transition hover:border-veru-paper/20 hover:bg-veru-paper/[0.05]">
      <button
        type="button"
        onClick={() => onOpen()}
        disabled={!canOpen}
        className={`relative block aspect-[9/16] w-full overflow-hidden bg-black text-left ${
          canOpen ? "cursor-pointer" : "cursor-default"
        }`}
        aria-label={`Abrir ${clip.title ?? "clip"}`}
      >
        {clip.thumb_url ? (
          <img
            src={clip.thumb_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-[radial-gradient(circle_at_50%_20%,rgba(160,76,245,0.16),transparent_60%)]">
            <IconFilm size={26} className="text-veru-paper/25" />
            <span className="px-4 text-center text-[11px] leading-relaxed text-veru-paper/35">
              {clip.status === "failed"
                ? "Render no disponible"
                : "Preparando vista previa…"}
            </span>
          </div>
        )}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/85 via-black/5 to-black/35" />

        <div className="absolute left-3 top-3">
          <ScoreRing score={clip.score} size={52} stroke={4} />
        </div>

        <span
          className={`absolute right-3 top-3 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide backdrop-blur ${status.className}`}
        >
          {processing && <IconLoader size={10} className="animate-spin" />}
          {status.label}
        </span>

        <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-veru-paper/60">
              Clip {String(clip.idx + 1).padStart(2, "0")}
            </p>
            <p className={`text-[11px] font-medium ${tone.text}`}>
              {formatScore(clip.score)} · {tone.label}
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-veru-paper/15 bg-black/55 px-2 py-0.5 text-[10px] font-medium tabular-nums text-veru-paper/85 backdrop-blur">
            {formatTime(clip.duration)}
          </span>
        </div>

        {canOpen && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition duration-300 group-hover:opacity-100">
            <span className="flex h-12 w-12 items-center justify-center rounded-full border border-veru-paper/25 bg-black/50 text-veru-paper shadow-2xl backdrop-blur">
              <IconPlay size={20} fill="currentColor" strokeWidth={0} className="translate-x-[1px]" />
            </span>
          </span>
        )}
      </button>

      <div className="flex flex-1 flex-col gap-2 p-4">
        {category && (
          <span
            className={`inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] ${category.className}`}
          >
            {category.label}
          </span>
        )}
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-veru-paper/90">
          {clip.title || `Clip ${clip.idx + 1}`}
        </h3>
        {clip.overlay?.context && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="line-clamp-1 text-[10px] font-medium uppercase tracking-wide text-veru-paper/70">
              {clip.overlay.context}
            </span>
          </div>
        )}
        {clip.hook && !sameText(clip.hook, clip.title) && (
          <p className="line-clamp-2 text-[11px] leading-relaxed text-veru-paper/50">
            {clip.hook}
          </p>
        )}

        {clip.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {clip.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-veru-paper/10 bg-veru-paper/5 px-2 py-0.5 text-[10px] text-veru-paper/50"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {clip.status === "failed" && clip.error && (
          <div className="mt-1 rounded-xl border border-rose-400/20 bg-rose-500/10 px-2.5 py-2 text-[10px] leading-relaxed text-rose-200">
            <span className="flex items-start gap-1.5">
              <IconAlert size={12} className="mt-0.5 shrink-0" />
              <span className="line-clamp-3 break-words">{clip.error}</span>
            </span>
          </div>
        )}

        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <button
            type="button"
            onClick={() => onOpen()}
            disabled={!canOpen}
            className="button-ghost flex-1 justify-center"
          >
            <IconWand size={13} />
            Ver y editar
          </button>

          {clip.status === "failed" ? (
            <button
              type="button"
              onClick={onRetry}
              disabled={retrying}
              className="button-ghost px-2.5"
              aria-label="Reintentar render"
              title="Reintentar render"
            >
              <IconRefresh size={14} className={retrying ? "animate-spin" : ""} />
            </button>
          ) : clip.video_url ? (
            <a
              href={clip.video_url}
              download={downloadName(clip.idx, clip.title, "mp4")}
              className="button-ghost px-2.5"
              aria-label="Descargar clip"
              title="Descargar clip"
            >
              <IconDownload size={14} />
            </a>
          ) : null}
        </div>

        {canOpen && (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onOpen("youtube")}
              className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-rose-400/25 bg-rose-500/10 px-2 py-1.5 text-[10px] font-semibold text-rose-100 transition hover:border-rose-300/40 hover:bg-rose-500/20"
              aria-label="Publicar en YouTube"
              title="Publicar en YouTube"
            >
              <IconYouTube size={12} />
              YouTube
            </button>
            <button
              type="button"
              onClick={() => onOpen("tiktok")}
              className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-veru-blush/25 bg-veru-blush/10 px-2 py-1.5 text-[10px] font-semibold text-veru-paper transition hover:border-veru-blush/40 hover:bg-veru-blush/20"
              aria-label="Publicar en TikTok"
              title="Publicar en TikTok"
            >
              <IconTikTok size={12} />
              TikTok
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
