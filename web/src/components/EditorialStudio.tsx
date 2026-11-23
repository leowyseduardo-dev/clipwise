import { useCallback, useEffect, useState } from "react";
import { getJson, sendJson } from "../lib/api";
import type { Clip, Job } from "../lib/types";

type Strategy = {
  broll: { start: number; end: number; quote: string }[];
  next_video: string;
  topics: string[];
};
type Hook = { kind: string; text: string };
type Review = {
  strength: string;
  tip: string;
  confidence: number | null;
  hooks: Hook[];
};
type Battle = {
  versions: { mode: string; clip: Clip }[];
  favorite: string | null;
};
type WeekItem = {
  clip_id: string;
  day: string;
  platform: string;
  title: string;
  strength?: string;
  tip?: string;
  job_id?: string;
  description?: string;
  tags?: string[];
};
type Profile = {
  examples: number;
  style: string | null;
  categories: Record<string, number>;
  duration: number | null;
  topics: Record<string, number>;
};
const modes: Record<string, string> = {
  original: "Original",
  dynamic: "Dinámico",
  clean: "Minimalista",
  opening: "Otro gancho",
};
const platforms = [
  "YouTube Shorts",
  "TikTok",
  "Instagram Reels",
  "Facebook Reels",
];
const message = (e: unknown) =>
  e instanceof Error ? e.message : "No se pudo completar la operación.";
const localDate = () => {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
};

export function HookPicker({
  clip,
  choose,
}: {
  clip: Clip;
  choose: (text: string) => void;
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let alive = true;
    setPending(true);
    setError("");
    const path = `/api/studio/clips/${clip.id}`;
    (offset
      ? sendJson<Review>(`${path}/hooks?offset=${offset}`, "POST")
      : getJson<Review>(path + "/editorial")
    )
      .then((r) => {
        if (alive) setReview(r);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      })
      .finally(() => {
        if (alive) setPending(false);
      });
    return () => {
      alive = false;
    };
  }, [clip.id, clip.updated_at, offset]);
  return (
    <section className="studio-box">
      <h4>Gancho de apertura</h4>
      {review && (
        <>
          <p>
            {review.strength} {review.tip}
          </p>
          {review.confidence != null && (
            <small>Confianza de la categoría · {review.confidence}/100</small>
          )}
          {review.hooks.map((h) => (
            <button
              type="button"
              className="hook-row"
              key={h.text}
              onClick={() => choose(h.text)}
            >
              <small>{h.kind}</small>
              {h.text}
            </button>
          ))}
          {!review.hooks.length && (
            <p>Este clip carece de texto para sugerir un gancho.</p>
          )}
        </>
      )}
      <button
        className="button-ghost"
        type="button"
        disabled={pending}
        onClick={() => setOffset((n) => n + 1)}
      >
        {pending ? "Leyendo…" : "Generar otras aperturas"}
      </button>
      <button
        type="button"
        className="button-ghost"
        onClick={() =>
          getJson<Strategy>(`/api/studio/clips/${clip.id}/strategy`)
            .then(setStrategy)
            .catch((e) => setError(message(e)))
        }
      >
        Ideas y B-roll
      </button>
      {strategy && (
        <div>
          <p>{strategy.next_video}</p>
          {strategy.broll.length > 0 ? (
            <>
              <small>
                Fragmentos relacionados del video original para revisar como
                B-roll
              </small>
              {strategy.broll.map((b) => (
                <p key={b.start}>
                  {Math.floor(b.start / 60)}:
                  {String(Math.floor(b.start) % 60).padStart(2, "0")} ·{" "}
                  {b.quote}
                </p>
              ))}
            </>
          ) : (
            <small>
              Sin fragmentos externos al corte con coincidencia temática
              suficiente.
            </small>
          )}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

export function ClipBattle({ clip }: { clip: Clip }) {
  const [battle, setBattle] = useState<Battle | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const url = `/api/studio/clips/${clip.id}/battle`;
  const refresh = useCallback(() => getJson<Battle>(url), [url]);
  const rendering = battle?.versions.some((v) =>
    ["queued", "rendering"].includes(v.clip.status),
  );
  useEffect(() => {
    let alive = true;
    const read = () =>
      refresh()
        .then((b) => {
          if (alive) setBattle(b);
        })
        .catch((e) => {
          if (alive) setError(message(e));
        });
    void read();
    const t = rendering ? window.setInterval(read, 2200) : undefined;
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [refresh, rendering]);
  async function act(path: string, method: string, payload?: unknown) {
    setPending(true);
    setError("");
    try {
      setBattle(await sendJson<Battle>(path, method, payload));
      window.dispatchEvent(new Event("studio-clips"));
      window.dispatchEvent(new Event("studio-calendar"));
    } catch (e) {
      setError(message(e));
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="studio-box">
      <h4>Clip Battle</h4>
      <p>
        Compara las ediciones del mismo momento. Tu favorita alimenta Creator
        DNA.
      </p>
      <div className="studio-grid">
        {battle?.versions.map((v) => (
          <article className="battle-card" key={v.clip.id}>
            <strong>{modes[v.mode]}</strong>
            {v.clip.video_url ? (
              <video
                controls
                playsInline
                preload="none"
                poster={v.clip.thumb_url || undefined}
                src={v.clip.video_url}
              />
            ) : (
              <small>{v.clip.error || "Render en cola"}</small>
            )}
            {v.clip.status === "ready" && (
              <button
                className="button-ghost"
                disabled={pending}
                aria-pressed={battle.favorite === v.clip.id}
                onClick={() =>
                  act(`/api/studio/clips/${v.clip.id}/favorite`, "PUT")
                }
              >
                {battle.favorite === v.clip.id
                  ? "★ Favorita"
                  : "Elegir favorita"}
              </button>
            )}
          </article>
        ))}
      </div>
      <div className="studio-actions">
        {["dynamic", "clean", "opening"]
          .filter((m) => !battle?.versions.some((v) => v.mode === m))
          .map((mode) => (
            <button
              type="button"
              key={mode}
              disabled={pending || !battle}
              className="button-ghost"
              onClick={() => act(url, "POST", { mode })}
            >
              Crear · {modes[mode]}
            </button>
          ))}
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

export function WeekPlanner({ job }: { job: Job }) {
  const [items, setItems] = useState<WeekItem[]>([]);
  const [start, setStart] = useState(localDate);
  const [platform, setPlatform] = useState(platforms[0]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const path = `/api/studio/jobs/${job.id}/week`;
  async function action(save: boolean) {
    setBusy(true);
    setNotice("");
    try {
      if (save) {
        await sendJson(path, "PUT", { items });
        setNotice("Calendario guardado.");
        setItems([]);
        window.dispatchEvent(new Event("studio-calendar"));
      } else {
        const next = await getJson<WeekItem[]>(
          path + "?" + new URLSearchParams({ start, platform }),
        );
        setItems(next);
        if (!next.length) setNotice("Se necesita un clip renderizado.");
      }
    } catch (e) {
      setNotice(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="studio-box">
      <h3>Una semana de contenido</h3>
      <div className="studio-actions">
        <label>
          Primer día
          <input
            className="field"
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          Destino
          <select
            className="field"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            {platforms.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={busy || !start}
          className="button-ghost"
          onClick={() => action(false)}
        >
          Proponer calendario
        </button>
      </div>
      {items.map((item) => (
        <article key={item.clip_id} className="studio-line">
          <div>
            <strong>{item.title}</strong>
            <p>
              {item.strength} {item.tip}
            </p>
            <details>
              <summary>Texto y etiquetas</summary>
              <p>{item.description}</p>
              <small>{item.tags?.map((t) => "#" + t).join(" ")}</small>
            </details>
          </div>
          <input
            className="field"
            type="date"
            aria-label="Fecha del clip"
            value={item.day}
            onChange={(e) =>
              setItems((rows) =>
                rows.map((i) =>
                  i === item ? { ...i, day: e.target.value } : i,
                ),
              )
            }
          />
          <button
            type="button"
            className="button-ghost"
            onClick={() => setItems((rows) => rows.filter((i) => i !== item))}
          >
            Quitar
          </button>
        </article>
      ))}
      {items.length > 0 && (
        <button
          type="button"
          className="button-primary"
          disabled={busy || items.some((i) => !i.day)}
          onClick={() => action(true)}
        >
          Aprobar {items.length} publicaciones
        </button>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}

export function StudioOverview({ open }: { open: (id: string) => void }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [events, setEvents] = useState<WeekItem[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const refresh = () =>
      Promise.all([
        getJson<Profile>("/api/studio/dna"),
        getJson<WeekItem[]>("/api/studio/calendar"),
      ])
        .then(([d, c]) => {
          if (alive) {
            setProfile(d);
            setEvents(c);
          }
        })
        .catch((e) => {
          if (alive) setError(message(e));
        });
    void refresh();
    window.addEventListener("studio-calendar", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      alive = false;
      window.removeEventListener("studio-calendar", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, []);
  async function clear() {
    if (
      !window.confirm("¿Borrar tus preferencias y las estadísticas importadas de tus proyectos? Los videos seguirán disponibles.")
    )
      return;
    try {
      setProfile(await sendJson("/api/studio/dna", "DELETE"));
    } catch (e) {
      setError(message(e));
    }
  }
  return (
    <div className="studio-overview">
      <section className="studio-box">
        <h3>Creator DNA</h3>
        {profile?.examples ? (
          <>
            <p>
              {profile.examples} elecciones · {profile.duration} s de duración
              típica · estilo {profile.style}
            </p>
            <small>{Object.keys(profile.topics).join(" · ")}</small>
          </>
        ) : (
          <p>
            Elige una versión favorita en Clip Battle para personalizar tus
            próximos cortes.
          </p>
        )}
        {profile && (
          <button className="button-ghost" onClick={clear}>
            Borrar mis preferencias y estadísticas importadas
          </button>
        )}
      </section>
      <section className="studio-box">
        <h3>Calendario editorial</h3>
        {!events.length && (
          <p>Los clips que apruebes en un proyecto aparecerán aquí.</p>
        )}
        {events.map((i) => (
          <div key={i.clip_id} className="studio-line">
            <button
              className="text-left"
              onClick={() => i.job_id && open(i.job_id)}
            >
              <small>
                {i.day} · {i.platform}
              </small>
              {i.title}
            </button>
            <button
              className="button-ghost"
              onClick={async () => {
                try {
                  await sendJson("/api/studio/calendar/" + i.clip_id, "DELETE");
                  setEvents((v) => v.filter((t) => t.clip_id !== i.clip_id));
                } catch (e) {
                  setError(message(e));
                }
              }}
            >
              Quitar
            </button>
          </div>
        ))}
      </section>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
