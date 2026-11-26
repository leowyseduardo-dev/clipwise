import { useCallback, useEffect, useState } from "react";
import { StudioOverview, WeekPlanner } from "./components/EditorialStudio";
import { ProjectTools, ArchiveList } from "./components/ProjectTools";

import {
  cancelJob,
  deleteJob,
  getHealth,
  getJob,
  getOptions,
  listJobs,
  retryClip,
  retryJob,
} from "./lib/api";
import type {
  Clip,
  Health,
  Job,
  OptionsResponse,
  PublishPlatform,
} from "./lib/types";
import { Header, type AppView } from "./components/Header";
import { AIPanel } from "./components/AIPanel";
import { NewJobCard } from "./components/NewJobCard";
import { LivePanel } from "./components/LivePanel";
import { JobView } from "./components/JobView";
import { JobsList } from "./components/JobsList";
import { ClipModal } from "./components/ClipModal";
import { Toast, type ToastKind, type ToastState } from "./components/Toast";
import {
  IconAlert,
  IconLoader,
} from "./components/icons";

const FALLBACK_OPTIONS: OptionsResponse = {
  subtitle_styles: [
    { id: "shorts", name: "Shorts", description: "Una palabra a la vez, mayúsculas y borde grueso." },
    { id: "impact", name: "Impacto", description: "Impact en mayúsculas, palabra activa en amarillo." },
    { id: "bold", name: "Bold", description: "Grande, grueso y con palabra resaltada." },
    { id: "clean", name: "Limpio", description: "Elegante y fácil de leer." },
    { id: "pill", name: "Píldora", description: "La palabra que suena va dentro de una píldora blanca." },
    { id: "box", name: "Caja", description: "Texto sobre una caja oscura, siempre legible." },
    { id: "yellow", name: "Amarillo", description: "El amarillo clásico de los virales, con borde negro." },
    { id: "neon", name: "Neón", description: "Contraste alto con acento cian." },
    { id: "minimal", name: "Minimal", description: "Discreto, para no tapar la imagen." },
  ],
  default_style: "shorts",
  min_clips: 5,
  max_clips: 15,
  layouts: [
    { id: "auto", name: "Automático", description: "Elige la plantilla según las cámaras y el juego." },
    { id: "vertical", name: "Vertical", description: "Recorte vertical clásico con seguimiento de cara." },
    { id: "cam_juego", name: "Cámara + juego", description: "Cámara arriba y partida abajo." },
    { id: "dos_cams_juego", name: "2 cams + juego", description: "Dos cámaras arriba y la partida debajo." },
    { id: "tres_cams_juego", name: "3 cams + juego", description: "Tres cámaras arriba y la partida debajo." },
    { id: "dividido", name: "Dividido", description: "Dos cámaras apiladas, como una llamada." },
    { id: "trio", name: "Trío", description: "Tres cámaras apiladas." },
    { id: "cuarteto", name: "Cuarteto", description: "Cuatro cámaras en cuadrícula." },
    { id: "trio_juego", name: "Trío con juego", description: "Partida arriba y tres cámaras abajo." },
    { id: "spotlight", name: "Spotlight", description: "Lo importante en grande y la escena completa debajo." },
    { id: "centrado", name: "Centrado", description: "El video entero sobre un fondo difuminado." },
    { id: "horizontal", name: "Horizontal", description: "El video completo con bandas arriba y abajo." },
  ],
  title_card_styles: [
    { id: "impact", name: "Impacto" },
    { id: "clean", name: "Limpio" },
    { id: "box", name: "Caja" },
  ],
  title_card_positions: [
    { id: "top", name: "Arriba" },
    { id: "center", name: "Centro" },
    { id: "bottom", name: "Abajo" },
  ],
  context_overlay: true,
  long_source_minutes: 720,
};

function readJobParam(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("job");
}

function syncJobParam(jobId: string | null) {
  const url = new URL(window.location.href);
  if (jobId) url.searchParams.set("job", jobId);
  else url.searchParams.delete("job");
  window.history.replaceState({}, "", url.toString());
}

function focusJobSection() {
  window.setTimeout(() => {
    document
      .getElementById("trabajo")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 120);
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [view, setView] = useState<AppView>("clips");
  const [options, setOptions] = useState<OptionsResponse | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<string | null>(() => readJobParam());
  const [job, setJob] = useState<Job | null>(null);
  const [loadingJob, setLoadingJob] = useState(false);
  const [activeClipId, setActiveClipId] = useState<string | null>(null);
  const [activePublishPlatform, setActivePublishPlatform] =
    useState<PublishPlatform | undefined>(undefined);
  const [retryingClipId, setRetryingClipId] = useState<string | null>(null);
  const [retryingJob, setRetryingJob] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const notify = useCallback((message: string, kind: ToastKind = "error") => {
    setToast({ id: Date.now(), message, kind });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    let alive = true;
    const loadHealth = () => {
      getHealth()
        .then((data) => {
          if (!alive) return;
          setHealth(data);
          setHealthError(false);
        })
        .catch(() => {
          if (alive) setHealthError(true);
        });
    };
    loadHealth();
    getOptions()
      .then((data) => {
        if (alive) setOptions(data);
      })
      .catch(() => undefined);
    const timer = window.setInterval(loadHealth, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const refreshJobs = useCallback(async (): Promise<Job[]> => {
    try {
      const data = await listJobs();
      setJobs(data);
      return data;
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    if (jobId) return;
    if (!jobs.length) return;
    const running = jobs.find(
      (item) => item.status === "processing" || item.status === "queued",
    );
    if (running) setJobId(running.id);
  }, [jobs, jobId]);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setLoadingJob(false);
      syncJobParam(null);
      return;
    }
    let cancelled = false;
    setLoadingJob(true);
    syncJobParam(jobId);
    getJob(jobId)
      .then((data) => {
        if (!cancelled) setJob(data);
      })
      .catch((error) => {
        if (cancelled) return;
        notify(
          error instanceof Error ? error.message : "No se pudo cargar el trabajo.",
        );
        setJob(null);
        setJobId(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingJob(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, notify]);

  const pollActive = Boolean(
    job &&
      job.id === jobId &&
      (job.status === "queued" ||
        job.status === "processing" ||
        (job.clips ?? []).some(
          (clip) => clip.status === "queued" || clip.status === "rendering",
        )),
  );

  useEffect(() => {
    if (!jobId || !pollActive) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const data = await getJob(jobId);
        if (cancelled) return;
        setJob(data);
        if (
          data.status === "ready" ||
          data.status === "failed" ||
          data.status === "cancelled"
        ) {
          void refreshJobs();
        }
      } catch {
        // Keep the last known state; the next tick retries.
      }
    }, 1600);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [jobId, pollActive, refreshJobs]);

  const applyClip = useCallback((updated: Clip) => {
    setJob((previous) => {
      if (!previous) return previous;
      const clips = previous.clips ?? [];
      if (!clips.some((clip) => clip.id === updated.id)) return previous;
      return {
        ...previous,
        clips: clips.map((clip) => (clip.id === updated.id ? updated : clip)),
      };
    });
  }, []);

  useEffect(() => {
    let alive=true;
    const refresh=()=>{if(jobId)getJob(jobId).then(j=>{if(alive)setJob(j);}).catch(()=>undefined);};
    window.addEventListener("studio-clips",refresh);
    return ()=>{alive=false;window.removeEventListener("studio-clips",refresh);};
  },[jobId]);

  function handleCreated(created: Job) {
    setJob(created);
    setJobId(created.id);
    setActiveClipId(null);
    setActivePublishPlatform(undefined);
    notify("Trabajo creado. Analizando el video…", "success");
    void refreshJobs();
    focusJobSection();
  }

  function handleSelect(id: string) {
    setActiveClipId(null);
    setActivePublishPlatform(undefined);
    if (id === jobId) {
      void getJob(id)
        .then(setJob)
        .catch(() => undefined);
      focusJobSection();
      return;
    }
    setJobId(id);
    focusJobSection();
  }

  async function handleCancel() {
    if (!job) return;
    try {
      const updated = await cancelJob(job.id);
      setJob(updated);
      notify("Procesamiento cancelado.", "info");
      void refreshJobs();
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "No se pudo cancelar el trabajo.",
      );
    }
  }

  async function handleRetryJob() {
    if (!job || retryingJob) return;
    setRetryingJob(true);
    try {
      const updated = await retryJob(job.id);
      setJob(updated);
      notify("Trabajo reencolado. Reintentando la descarga…", "info");
      void refreshJobs();
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "No se pudo reintentar el trabajo.",
      );
    } finally {
      setRetryingJob(false);
    }
  }

  async function handleDelete() {
    if (!job) return;
    try {
      await deleteJob(job.id);
      setActiveClipId(null);
      setActivePublishPlatform(undefined);
      setJob(null);
      setJobId(null);
      syncJobParam(null);
      notify("Trabajo eliminado.", "info");
      void refreshJobs();
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "No se pudo eliminar el trabajo.",
      );
    }
  }

  async function handleRetryClip(clip: Clip) {
    setRetryingClipId(clip.id);
    try {
      const updated = await retryClip(clip.id);
      applyClip(updated);
      notify("Clip en cola para re-renderizar.", "info");
      void refreshJobs();
    } catch (error) {
      notify(
        error instanceof Error
          ? error.message
          : "No se pudo reintentar la edición del clip.",
      );
    } finally {
      setRetryingClipId(null);
    }
  }

  function handleClipUpdated(updated: Clip, message?: string) {
    applyClip(updated);
    notify(message ?? "Subtítulos guardados. Regenerando el clip…", "success");
    void refreshJobs();
  }

  const engineReady = health ? health.ffmpeg.available : !healthError;
  const opts = options ?? FALLBACK_OPTIONS;
  const maxUploadMb = health?.max_upload_mb ?? 16384;
  const maxSourceMinutes = health?.max_source_minutes ?? 720;
  const longSourceMinutes =
    health?.long_source_minutes ?? opts.long_source_minutes ?? 720;
  const activeClip =
    job && job.id === jobId
      ? (job.clips ?? []).find((clip) => clip.id === activeClipId) ?? null
      : null;

  return (
    <div className="relative z-10 min-h-screen">
      <Header
        health={health}
        healthError={healthError}
        view={view}
        onViewChange={setView}
      />

      {view === "ai" ? (
        <main className="mx-auto w-full max-w-[1240px] px-4 pb-24 pt-8 sm:px-6 lg:px-8">
          <AIPanel
            health={health}
            options={options}
            onGoCreate={() => {
              setView("clips");
              window.setTimeout(() => {
                document
                  .getElementById("crear")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }, 80);
            }}
          />
        </main>
      ) : view === "live" ? (
        <main className="mx-auto w-full max-w-[1240px] px-4 pb-24 pt-8 sm:px-6 lg:px-8">
          <LivePanel />
        </main>
      ) : (
        <main className="mx-auto w-full max-w-[1240px] px-4 pb-16 pt-8 sm:px-6 lg:px-8">
          {health && !health.ffmpeg.available && (
            <div className="mb-6 flex items-start gap-3 rounded-3xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900">
              <IconAlert size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <div>
                <p className="font-semibold">FFmpeg no está disponible</p>
                <p className="mt-0.5 text-amber-800/80">
                  Revisa <code className="font-mono">FFMPEG_BIN</code> y{" "}
                  <code className="font-mono">FFPROBE_BIN</code> en la
                  configuración del motor. Sin FFmpeg no se pueden renderizar
                  clips.
                </p>
              </div>
            </div>
          )}

          <section className="studio-home">
            <div className="studio-intro"><h1>Estudio de clips</h1><p>Importa un video, revisa los mejores cortes y prepara tu calendario de publicación.</p><StudioOverview open={handleSelect}/></div>
            <div id="crear" className="scroll-mt-24">
              <NewJobCard
                styles={opts.subtitle_styles}
                defaultStyle={opts.default_style}
                minClips={opts.min_clips}
                maxClips={opts.max_clips}
                maxUploadMb={maxUploadMb}
                maxSourceMinutes={maxSourceMinutes}
                layouts={opts.layouts}
                longSourceMinutes={longSourceMinutes}
                contextOverlayDefault={opts.context_overlay !== false}
                engineReady={engineReady}
                onCreated={handleCreated}
                onError={(message) => notify(message, "error")}
              />
              <p className="mt-3 px-1 text-center text-[10px] leading-relaxed text-veru-paper/30">
                La primera transcripción descarga el modelo de voz de Whisper.
                En videos largos, el análisis puede tardar varios minutos.
              </p>
            </div>
          </section>

          {jobId && (!job || job.id !== jobId) && loadingJob && (
            <section id="trabajo" className="mt-14 scroll-mt-24">
              <div className="panel flex items-center gap-3 px-5 py-5">
                <IconLoader size={18} className="animate-spin text-veru-ember" />
                <p className="text-sm text-veru-paper/70">Cargando trabajo…</p>
              </div>
            </section>
          )}

          {job && job.id === jobId && (
            <section id="trabajo" className="mt-14 scroll-mt-24">
              <ProjectTools key={job.id} job={job} changed={async()=>{setJob(await getJob(job.id));await refreshJobs();}} open={handleSelect}/>
              <JobView
                job={job}
                onCancel={() => void handleCancel()}
                onRetryJob={() => void handleRetryJob()}
                onDelete={() => void handleDelete()}
                onOpenClip={(clip, platform) => {
                  setActivePublishPlatform(platform);
                  setActiveClipId(clip.id);
                }}
                onRetryClip={(clip) => void handleRetryClip(clip)}
                retryingClipId={retryingClipId}
                retryingJob={retryingJob}
              />
              {job.clips?.some(c=>c.status==="ready") && <WeekPlanner key={job.id} job={job}/>}
            </section>
          )}

          <section id="trabajos" className="mt-16 scroll-mt-24">
            <ArchiveList open={handleSelect} revision={jobs}/>
            <JobsList
              jobs={jobs}
              activeJobId={jobId}
              onSelect={handleSelect}
            />
          </section>

          <footer className="mt-20 border-t border-veru-paper/[0.06] pt-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div className="max-w-sm">
                <p className="font-display text-lg font-bold tracking-tighter">
                  Clipwise<span className="text-veru-ember">.</span>
                </p>
                <p className="mt-2 text-[11px] leading-relaxed text-veru-paper/35">
                  FFmpeg · Whisper · PySceneDetect · OpenCV. Procesado en
                  Clipwise. Si activas un LLM, solo se envían fragmentos de la
                  transcripción para puntuar los momentos.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] uppercase tracking-[0.14em] text-veru-paper/30">
                <a href="/docs" className="transition hover:text-veru-paper/70">
                  API
                </a>
                <span className="text-veru-paper/15">·</span>
                <span>9:16 · 1:1 · 16:9</span>
                <span className="text-veru-paper/15">·</span>
                <span>H.264 + AAC</span>
              </div>
            </div>
            
          </footer>
        </main>
      )}

      {activeClip && (
        <ClipModal
          key={activeClip.id}
          clip={activeClip}
          initialPlatform={activePublishPlatform}
          subtitleStyles={opts.subtitle_styles}
          layouts={opts.layouts}
          onClose={() => {
            setActiveClipId(null);
            setActivePublishPlatform(undefined);
          }}
          onUpdated={handleClipUpdated}
          onError={(message) => notify(message, "error")}
          onRetry={() => void handleRetryClip(activeClip)}
          retrying={retryingClipId === activeClip.id}
        />
      )}

      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
