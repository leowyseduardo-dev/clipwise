import { useEffect, useState } from "react";
import { getJson, sendJson } from "../lib/api";
import type { Job } from "../lib/types";
export function ArchiveList({
  open,
  revision,
}: {
  open: (id: string) => void;
  revision: Job[];
}) {
  const [rows, setRows] = useState<Job[]>([]),
    [active, setActive] = useState(false),
    [err, setErr] = useState("");
  useEffect(() => {
    if (active)
      getJson<{ jobs: Job[] }>("/api/jobs?archived=true")
        .then((r) => setRows(r.jobs))
        .catch((e) => setErr(e.message));
  }, [active, revision]);
  return (
    <div className="mb-3">
      <button className="button-ghost" onClick={() => setActive(!active)}>
        {active ? "Cerrar archivo" : "Ver archivados"}
      </button>
      {active && (
        <div className="studio-box">
          {rows.length
            ? rows.map((r) => (
                <button
                  className="button-ghost"
                  key={r.id}
                  onClick={() => open(r.id)}
                >
                  {r.title}
                </button>
              ))
            : "Sin proyectos archivados."}
          {err}
        </div>
      )}
    </div>
  );
}
type Usage = {
  storage_bytes: number;
  ready: number;
  media_seconds: number;
  processing_seconds: number | null;
  analysis_modes: string[];
  meter: {
    model: string;
    calls: number;
    cached: number;
    prompt: number;
    completion: number;
  }[];
  api_usd_estimate: number | null;
  render_usd_estimate: number | null;
  storage_usd_month_estimate: number | null;
};
export function ProjectTools({
  job,
  changed,
  open,
}: {
  job: Job;
  changed: () => Promise<void>;
  open: (id: string) => void;
}) {
  const [name, setName] = useState(job.title),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [usage, setUsage] = useState<Usage | null>(null);
  const url = "/api/studio/jobs/" + job.id;
  const [social, setSocial] = useState<
    { clip: string; views: number; likes: number | null }[] | null
  >(null);
  async function act(kind: string) {
    setBusy(true);
    setError("");
    try {
      if (kind === "social")
        setSocial(
          (
            await sendJson<{
              videos: { clip: string; views: number; likes: number | null }[];
            }>(url + "/youtube-stats", "POST")
          ).videos,
        );
      else if (kind === "usage") setUsage(await getJson<Usage>(url + "/usage"));
      else if (kind === "copy") {
        const j = await sendJson<Job>(url + "/duplicate", "POST");
        await changed();
        open(j.id);
      } else {
        await sendJson(
          url,
          "PATCH",
          kind === "name" ? { title: name } : { archived: !job.archived },
        );
        await changed();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operación fallida.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="studio-box mb-4">
      <summary>Administrar proyecto</summary>
      <div className="studio-actions">
        <input
          className="field"
          aria-label="Nombre del proyecto"
          value={name}
          maxLength={150}
          onChange={(e) => setName(e.target.value)}
        />
        {[
          ["name", "Renombrar"],
          ["copy", "Duplicar proyecto"],
          ["archive", job.archived ? "Restaurar" : "Archivar"],
          ["usage", "Ver uso real"],
        ].map(([k, v]) => (
          <button
            key={k}
            className="button-ghost"
            disabled={busy || (!name.trim() && k === "name")}
            onClick={() => act(k)}
          >
            {v}
          </button>
        ))}
      </div>
      <button
        className="button-ghost"
        disabled={busy}
        onClick={() => act("social")}
      >
        Consultar YouTube conectado
      </button>
      {social && (
        <div>
          {social.length ? (
            social.map((s) => (
              <p key={s.clip}>
                {job.clips?.find((c) => c.id === s.clip)?.title} · {s.views}{" "}
                vistas · {s.likes ?? "—"} Me gusta
              </p>
            ))
          ) : (
            <p>
              No hay publicaciones medibles de este proyecto en la cuenta
              conectada.
            </p>
          )}
        </div>
      )}
      {usage && (
        <div>
          {usage.meter
            .filter((m) => m.calls || m.cached)
            .map((m) => (
              <p key={m.model}>
                {m.model} · {m.calls} llamadas · {m.cached} en caché ·{" "}
                {m.prompt + m.completion} tokens reportados
              </p>
            ))}
          {(
            [
              ["IA", usage.api_usd_estimate],
              ["Render", usage.render_usd_estimate],
              ["Almacenamiento mensual", usage.storage_usd_month_estimate],
            ] as const
          ).map(
            ([k, v]) =>
              v != null && (
                <small key={k}>
                  {k} · estimación USD {v.toFixed(4)}{" "}
                </small>
              ),
          )}
        </div>
      )}
      {usage && (
        <p>
          {usage.ready} clips listos · {usage.media_seconds} s de video generado
          · {(usage.storage_bytes / 1048576).toFixed(1)} MB en disco
          {usage.processing_seconds != null &&
            " · " + usage.processing_seconds + " s de procesamiento"}{" "}
          · {usage.analysis_modes.join(" + ")}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
