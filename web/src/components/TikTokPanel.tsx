import { useCallback, useEffect, useRef, useState } from "react";

import { createTikTokGrab, listTikTokGrabs, publishTikTokGrab } from "../lib/api";
import type { TikTokGrab } from "../lib/types";
import { IconAlert, IconLoader, IconSparkles } from "./icons";

const STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  processing: "Procesando",
  publishing: "Publicando",
  ready: "Listo",
  failed: "Falló",
};

const STAGE_LABEL: Record<string, string> = {
  downloading: "Descargando de TikTok",
  cleaning: "Quitando marca de agua",
  publishing: "Subiendo a YouTube",
};

export function TikTokPanel() {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [autoPublish, setAutoPublish] = useState(false);
  const [grabs, setGrabs] = useState<TikTokGrab[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listTikTokGrabs();
      setGrabs(data.grabs);
      setError(null);
    } catch {
      // Silencio: el panel se refresca en el siguiente tick.
    }
  }, []);

  useEffect(() => {
    void refresh();
    pollRef.current = window.setInterval(() => {
      void refresh();
    }, 3000);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [refresh]);

  const active = grabs.some(
    (grab) => grab.status === "queued" || grab.status === "processing" || grab.status === "publishing",
  );

  const submit = async () => {
    const trimmed = url.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await createTikTokGrab({ url: trimmed, title, auto_publish: autoPublish });
      setUrl("");
      setTitle("");
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo crear el grab.");
    } finally {
      setBusy(false);
    }
  };

  const publishNow = async (grabId: string) => {
    try {
      await publishTikTokGrab(grabId);
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo publicar.");
    }
  };

  return (
    <section className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <div className="rounded-2xl border border-veru-paper/5 bg-ink/60 p-5 shadow-xl shadow-black/20">
        <div className="mb-4 flex items-center gap-2">
          <IconSparkles className="h-5 w-5 text-veru-ember" />
          <h2 className="text-lg font-semibold tracking-tight">Robar de TikTok</h2>
        </div>
        <p className="mb-4 text-sm text-veru-paper/50">
          Pega la URL del video de TikTok. Lo descargamos sin marca de agua y,
          si quieres, lo publicamos directo a YouTube en automático.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://www.tiktok.com/@usuario/video/123..."
            className="field flex-1"
          />
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Título para YouTube (opcional)"
            className="field w-full sm:w-72"
          />
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !url.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-veru-ember px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-veru-ember/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? <IconLoader className="h-4 w-4 animate-spin" /> : null}
            {busy ? "Procesando..." : "Descargar"}
          </button>
        </div>
        <label className="mt-3 inline-flex cursor-pointer items-center gap-2 text-sm text-veru-paper/70">
          <input
            type="checkbox"
            checked={autoPublish}
            onChange={(event) => setAutoPublish(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300 accent-veru-ember"
          />
          Publicar en YouTube automáticamente al terminar
        </label>
        {error ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-rose-300">
            <IconAlert className="h-4 w-4" /> {error}
          </p>
        ) : null}
      </div>

      <div className="space-y-3">
        {grabs.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-veru-paper/10 bg-ink/40 p-8 text-center text-sm text-veru-paper/35">
            Todavía no has robado ningún video. Pega una URL arriba.
          </p>
        ) : null}
        {grabs.map((grab) => (
          <article
            key={grab.id}
            className="rounded-2xl border border-veru-paper/5 bg-ink/60 p-4 shadow-lg shadow-black/10"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-veru-paper/90">
                  {grab.title || grab.url}
                </p>
                <p className="text-xs text-veru-paper/35">
                  {grab.author ? `@${grab.author} · ` : ""}
                  {grab.clean ? "Sin marca de agua" : "Marca tratada con delogo"}
                </p>
              </div>
              <span
                className={`chip text-xs ${
                  grab.status === "ready"
                    ? "text-emerald-300"
                    : grab.status === "failed"
                      ? "text-rose-300"
                      : "text-amber-700"
                }`}
              >
                {STATUS_LABEL[grab.status] ?? grab.status}
                {grab.stage && STAGE_LABEL[grab.stage]
                  ? ` · ${STAGE_LABEL[grab.stage]}`
                  : ""}
              </span>
            </div>
            {grab.status !== "ready" && grab.status !== "failed" ? (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-veru-paper/5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-veru-ember to-veru-blush transition-all"
                  style={{ width: `${Math.max(4, grab.progress)}%` }}
                />
              </div>
            ) : null}
            {grab.error ? (
              <p className="mt-2 flex items-center gap-2 text-xs text-rose-300">
                <IconAlert className="h-3.5 w-3.5" /> {grab.error}
              </p>
            ) : null}
            {grab.status === "ready" ? (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {grab.youtube_url ? (
                  <a
                    href={grab.youtube_url}
                    target="_blank"
                    rel="noreferrer"
                    className="chip text-emerald-300"
                  >
                    Ver en YouTube
                  </a>
                ) : (
                  <button
                    type="button"
                    onClick={() => void publishNow(grab.id)}
                    className="chip cursor-pointer text-veru-ember hover:text-veru-blush"
                  >
                    Publicar en YouTube
                  </button>
                )}
                <a
                  href={`/api/tiktok/grabs/${grab.id}/video.mp4`}
                  className="chip cursor-pointer text-veru-blush hover:text-veru-blush"
                >
                  Descargar MP4 limpio
                </a>
              </div>
            ) : null}
          </article>
        ))}
        {active ? (
          <p className="text-center text-xs text-veru-paper/25">
            El panel se actualiza solo cada 3 segundos.
          </p>
        ) : null}
      </div>
    </section>
  );
}
