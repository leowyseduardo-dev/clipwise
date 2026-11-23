import { useCallback, useEffect, useRef, useState } from "react";

import {
  clipLiveSession,
  createLiveSession,
  deleteLiveSession,
  listLiveSessions,
  resumeLiveSession,
  stopLiveSession,
} from "../lib/api";
import type { LiveSession } from "../lib/types";
import {
  IconAlert,
  IconDownload,
  IconLoader,
  IconPlay,
  IconScissors,
  IconSparkles,
  IconTrash,
} from "./icons";

const CLIP_LENGTHS = [15, 30, 60];

const PLATFORM_LABEL: Record<string, string> = {
  kick: "Kick",
  youtube: "YouTube",
  twitch: "Twitch",
};

const PLATFORM_CLASS: Record<string, string> = {
  kick: "border-lime-400/30 bg-lime-400/10 text-lime-300",
  youtube: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  twitch: "border-veru-ember/30 bg-veru-ember/10 text-veru-ember",
};

const STATUS_LABEL: Record<string, string> = {
  connecting: "Conectando",
  recording: "Grabando en vivo",
  stopped: "Detenida",
  offline: "Sin directo",
  error: "Error",
};

const STATUS_DOT: Record<string, string> = {
  connecting: "animate-pulse bg-amber-400",
  recording: "animate-pulse bg-emerald-400",
  stopped: "bg-veru-paper/35",
  offline: "bg-veru-paper/35",
  error: "bg-rose-400",
};

function clock(total: number): string {
  const safe = Math.max(0, Math.round(total));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function when(value: string | null): string {
  if (!value) return "";
  const time = value.slice(11, 19);
  return time || value;
}

export function LivePanel() {
  const [url, setUrl] = useState("");
  const [sessions, setSessions] = useState<LiveSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [clipBusy, setClipBusy] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listLiveSessions();
      setSessions(data);
    } catch {
      // Silencio: el panel se refresca en el siguiente tick.
    }
  }, []);

  useEffect(() => {
    void refresh();
    pollRef.current = window.setInterval(() => {
      void refresh();
    }, 4000);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [refresh]);

  const submit = async () => {
    const trimmed = url.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    setError(null);
    try {
      await createLiveSession(trimmed);
      setUrl("");
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo abrir la emisión.");
    } finally {
      setCreating(false);
    }
  };

  const runAction = async (key: string, action: () => Promise<unknown>, fallback: string) => {
    if (actionBusy) return;
    setActionBusy(key);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : fallback);
    } finally {
      setActionBusy(null);
    }
  };

  const grab = async (session: LiveSession, seconds: number) => {
    const key = `${session.id}:${seconds}`;
    if (clipBusy) return;
    setClipBusy(key);
    setError(null);
    try {
      await clipLiveSession(session.id, seconds);
      await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "No se pudo cortar el clip.");
    } finally {
      setClipBusy(null);
    }
  };

  return (
    <section className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <div className="rounded-2xl border border-veru-paper/5 bg-ink/60 p-5 shadow-xl shadow-black/20">
        <div className="mb-4 flex items-center gap-2">
          <IconSparkles className="h-5 w-5 text-veru-ember" />
          <h2 className="text-lg font-semibold tracking-tight">Clips en vivo</h2>
        </div>
        <p className="mb-4 text-sm text-veru-paper/50">
          Pega el enlace de una emisión de Kick, YouTube o Twitch. Clipwise graba
          un búfer rodante de 6 minutos; pides un clip y sale en segundos, con lo
          que acaba de pasar.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void submit();
            }}
            placeholder="https://www.twitch.tv/canal  ·  https://kick.com/canal  ·  https://youtube.com/watch?v=..."
            className="field flex-1"
          />
          <button
            type="button"
            onClick={() => void submit()}
            disabled={creating || !url.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-veru-ember px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-veru-ember/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {creating ? (
              <IconLoader className="h-4 w-4 animate-spin" />
            ) : (
              <IconPlay className="h-4 w-4" />
            )}
            {creating ? "Conectando..." : "Vigilar en vivo"}
          </button>
        </div>
        {error ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-rose-300">
            <IconAlert className="h-4 w-4" /> {error}
          </p>
        ) : null}
        <p className="mt-3 text-xs text-veru-paper/25">
          Kick, YouTube y Twitch. Hasta 3 emisiones a la vez; cada una guarda 6
          minutos de metraje.
        </p>
      </div>

      <div className="space-y-3">
        {sessions.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-veru-paper/10 bg-ink/40 p-8 text-center text-sm text-veru-paper/35">
            Todavía no vigilas ninguna emisión. Pega una URL arriba.
          </p>
        ) : null}
        {sessions.map((session) => {
          const bufferMax = Math.max(1, session.buffer_minutes * 60);
          const fill = Math.min(100, (session.buffer_seconds / bufferMax) * 100);
          const live = session.status === "recording";
          const canResume =
            session.status === "stopped" ||
            session.status === "offline" ||
            session.status === "error";
          return (
            <article
              key={session.id}
              className="rounded-2xl border border-veru-paper/5 bg-ink/60 p-4 shadow-lg shadow-black/10"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-veru-paper/90">
                    {session.title || session.url}
                  </p>
                  <p className="truncate text-xs text-veru-paper/35">
                    {session.author ? `${session.author} · ` : ""}
                    {session.url}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`chip border text-[11px] ${
                      PLATFORM_CLASS[session.platform] ?? "border-veru-paper/10 text-veru-paper/70"
                    }`}
                  >
                    {PLATFORM_LABEL[session.platform] ?? session.platform}
                  </span>
                  <span className="chip text-xs">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        STATUS_DOT[session.status] ?? "bg-veru-paper/35"
                      }`}
                    />
                    {STATUS_LABEL[session.status] ?? session.status}
                  </span>
                </div>
              </div>

              <div className="mt-3 flex items-center gap-3">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-veru-paper/5">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-veru-ember to-veru-blush transition-all"
                    style={{ width: `${Math.max(2, fill)}%` }}
                  />
                </div>
                <span className="shrink-0 text-xs tabular-nums text-veru-paper/35">
                  {clock(session.buffer_seconds)} / {clock(bufferMax)}
                </span>
              </div>

              {session.error ? (
                <p className="mt-2 flex items-center gap-2 text-xs text-rose-300">
                  <IconAlert className="h-3.5 w-3.5" /> {session.error}
                </p>
              ) : null}

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {CLIP_LENGTHS.map((seconds) => {
                  const key = `${session.id}:${seconds}`;
                  const busy = clipBusy === key;
                  const ready = live && session.buffer_seconds >= seconds;
                  return (
                    <button
                      key={seconds}
                      type="button"
                      onClick={() => void grab(session, seconds)}
                      disabled={!ready || clipBusy !== null}
                      className={`chip inline-flex cursor-pointer items-center gap-1.5 ${
                        ready
                          ? "text-veru-blush hover:text-veru-blush"
                          : "cursor-not-allowed text-veru-paper/25"
                      } disabled:cursor-not-allowed`}
                    >
                      {busy ? (
                        <IconLoader className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <IconScissors className="h-3.5 w-3.5" />
                      )}
                      Clip {seconds}s
                    </button>
                  );
                })}

                <span className="mx-1 h-4 w-px bg-veru-paper/10" />

                {live ? (
                  <button
                    type="button"
                    onClick={() =>
                      void runAction(
                        `${session.id}:stop`,
                        () => stopLiveSession(session.id),
                        "No se pudo detener.",
                      )
                    }
                    disabled={actionBusy !== null}
                    className="chip cursor-pointer text-amber-700 hover:text-amber-800"
                  >
                    Detener
                  </button>
                ) : null}

                {canResume ? (
                  <button
                    type="button"
                    onClick={() =>
                      void runAction(
                        `${session.id}:resume`,
                        () => resumeLiveSession(session.id),
                        "No se pudo reanudar.",
                      )
                    }
                    disabled={actionBusy !== null}
                    className="chip cursor-pointer text-emerald-300 hover:text-emerald-200"
                  >
                    Reanudar
                  </button>
                ) : null}

                <button
                  type="button"
                  onClick={() => {
                    if (!window.confirm("¿Borrar esta emisión y todos sus clips?")) return;
                    void runAction(
                      `${session.id}:delete`,
                      () => deleteLiveSession(session.id),
                      "No se pudo borrar.",
                    );
                  }}
                  disabled={actionBusy !== null}
                  className="chip cursor-pointer text-rose-300 hover:text-rose-200"
                >
                  <IconTrash className="h-3.5 w-3.5" /> Borrar
                </button>
              </div>

              {live && session.buffer_seconds < 8 ? (
                <p className="mt-2 text-xs text-veru-paper/25">
                  Llenando el búfer… los clips se activan en unos segundos.
                </p>
              ) : null}

              {session.clips.length > 0 ? (
                <ul className="mt-4 space-y-2 border-t border-veru-paper/5 pt-3">
                  {session.clips.map((clip) => (
                    <li
                      key={clip.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-black/20 px-3 py-2"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium text-veru-paper/80">
                          {clip.title}
                        </p>
                        <p className="text-[11px] text-veru-paper/35">
                          {when(clip.created_at)} · {clip.seconds}s
                          {clip.author ? ` · ${clip.author}` : ""}
                        </p>
                      </div>
                      <a
                        href={`/api/live/clips/${clip.id}/video.mp4`}
                        className="chip inline-flex cursor-pointer items-center gap-1.5 text-veru-blush hover:text-veru-blush"
                      >
                        <IconDownload className="h-3.5 w-3.5" /> Descargar
                      </a>
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          );
        })}
        {sessions.some((session) => session.status === "recording") ? (
          <p className="text-center text-xs text-veru-paper/25">
            El panel se actualiza solo cada 4 segundos.
          </p>
        ) : null}
      </div>
    </section>
  );
}
