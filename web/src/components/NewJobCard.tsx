import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";

import { createJob } from "../lib/api";
import { fileExtension, formatBytes } from "../lib/format";
import type { Job, LayoutOption, SubtitleStyleOption } from "../lib/types";
import {
  IconCheck,
  IconChevronDown,
  IconLink,
  IconMusic,
  IconSparkles,
  IconUpload,
  IconX,
} from "./icons";

const VIDEO_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"];
const MUSIC_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"];

const LANGUAGES: { id: string; name: string }[] = [
  { id: "auto", name: "Detección automática" },
  { id: "es", name: "Español" },
  { id: "en", name: "Inglés" },
  { id: "pt", name: "Portugués" },
  { id: "fr", name: "Francés" },
  { id: "it", name: "Italiano" },
  { id: "de", name: "Alemán" },
];

const DEFAULT_LAYOUTS: LayoutOption[] = [
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
];

const STYLE_PREVIEW: Record<string, string> = {
  shorts: "text-[13px] font-black uppercase tracking-tight",
  impact: "text-[13px] font-black uppercase italic tracking-tight",
  bold: "text-[13px] font-extrabold tracking-tight",
  clean: "text-[12px] font-medium",
  pill: "rounded-full bg-veru-paper px-2 py-0.5 text-[9px] font-bold text-veru-ink",
  box: "rounded bg-veru-ink px-1.5 py-0.5 text-[9px] font-bold text-veru-paper ring-1 ring-veru-paper/25",
  yellow: "text-[13px] font-black text-yellow-300",
  neon: "text-[13px] font-black text-veru-blush",
  minimal: "text-[11px] font-normal",
};

interface NewJobCardProps {
  styles: SubtitleStyleOption[];
  defaultStyle: string;
  minClips: number;
  maxClips: number;
  maxUploadMb: number;
  maxSourceMinutes: number;
  layouts?: LayoutOption[];
  longSourceMinutes?: number;
  contextOverlayDefault?: boolean;
  engineReady: boolean;
  onCreated: (job: Job) => void;
  onError: (message: string) => void;
}

export function NewJobCard({
  styles,
  defaultStyle,
  minClips,
  maxClips,
  maxUploadMb,
  maxSourceMinutes,
  layouts,
  longSourceMinutes,
  contextOverlayDefault = true,
  engineReady,
  onCreated,
  onError,
}: NewJobCardProps) {
  const [tab, setTab] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [extraFiles,setExtraFiles] = useState<File[]>([]);
  const [useDNA,setUseDNA] = useState(false);
  const [aspect,setAspect] = useState("9:16");
  const [musicFile, setMusicFile] = useState<File | null>(null);
  const [style, setStyle] = useState(defaultStyle || styles[0]?.id || "shorts");
  const [clips, setClips] = useState("auto");
  const [language, setLanguage] = useState("auto");
  const [streamer, setStreamer] = useState("");
  const [game, setGame] = useState("");
  const [layout, setLayout] = useState("auto");
  const [cardText, setCardText] = useState("");
  const [cardStyle, setCardStyle] = useState("impact");
  const [cardPosition, setCardPosition] = useState("top");
  const [cardSeconds, setCardSeconds] = useState(4);
  const [contextOverlay, setContextOverlay] = useState(contextOverlayDefault);
  const [removeSilences, setRemoveSilences] = useState(true);
  const [dynamicZoom, setDynamicZoom] = useState(true);
  const [rights, setRights] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const videoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setStyle(defaultStyle || styles[0]?.id || "shorts");
  }, [defaultStyle, styles]);

  useEffect(() => {
    setContextOverlay(contextOverlayDefault);
  }, [contextOverlayDefault]);

  const clipChoices = [5, 8, 10, 12, 15].filter(
    (value) => value >= minClips && value <= maxClips,
  );
  if (!clipChoices.length) clipChoices.push(maxClips);

  const selectedStyle = styles.find((item) => item.id === style);
  const layoutChoices = layouts?.length ? layouts : DEFAULT_LAYOUTS;
  const selectedLayout = layoutChoices.find((item) => item.id === layout);
  const sourceLimitLabel =
    maxSourceMinutes <= 0
      ? longSourceMinutes
        ? `sin límite · audio-first desde ${longSourceMinutes} min`
        : "sin límite de duración"
      : longSourceMinutes && longSourceMinutes < maxSourceMinutes
        ? `${maxSourceMinutes} min · audio-first desde ${longSourceMinutes} min`
        : `${maxSourceMinutes} min`;

  function pickVideos(files: File[]) {
    if (!files.length) return;
    for (const file of files) {
    if (!VIDEO_EXTENSIONS.includes(fileExtension(file.name))) {
      setLocalError("Formato no compatible. Usa MP4, MOV, MKV, WEBM, M4V o AVI.");
      return;
    }
    if (file.size > maxUploadMb * 1024 * 1024) {
      setLocalError(`El video supera el límite de ${maxUploadMb} MB.`);
      return;
    }
    }
    setLocalError(null);
    setVideoFile(files[0]);setExtraFiles(files.slice(1));
  }

  function pickMusic(file: File | null) {
    if (!file) return;
    if (!MUSIC_EXTENSIONS.includes(fileExtension(file.name))) {
      setLocalError("Formato de música no compatible. Usa MP3, WAV, M4A, AAC, OGG o FLAC.");
      return;
    }
    setLocalError(null);
    setMusicFile(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    pickVideos(Array.from(event.dataTransfer.files));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setLocalError(null);

    if (tab === "url" && !url.trim()) {
      setLocalError("Pega un enlace de YouTube, Kick o Twitch o cambia a «Subir archivo».");
      return;
    }
    if (tab === "url" && !rights) {
      setLocalError("Confirma que tienes derechos sobre el video antes de continuar.");
      return;
    }
    if (tab === "upload" && !videoFile) {
      setLocalError("Selecciona un archivo de video.");
      return;
    }

    const form = new FormData();
    form.append("source_type", tab);
    if (tab === "url") {
      form.append("url", url.trim());
      form.append("rights_accepted", rights ? "true" : "false");
    } else if (videoFile) {
      form.append("video", videoFile);
    }
    if (streamer.trim()) form.append("streamer_name", streamer.trim());
    if (game.trim()) form.append("game_name", game.trim());
    form.append(
      "options",
      JSON.stringify({
        aspect, use_creator_profile:useDNA,
        max_clips: clips === "auto" ? null : Number(clips),
        subtitle_style: style,
        remove_silences: removeSilences,
        dynamic_zoom: dynamicZoom,
        language: language === "auto" ? null : language,
        layout,
        context_overlay: contextOverlay,
        title_card: cardText.trim(),
        title_card_style: cardStyle,
        title_card_position: cardPosition,
        title_card_seconds: cardSeconds,
      }),
    );
    if (musicFile) form.append("music", musicFile);

    setSubmitting(true);
    setUploadPct(tab === "upload" ? 0 : null);
    try {
      const sources = tab==="url" ? [...new Set(url.split(/\r?\n/).map(s=>s.trim()).filter(Boolean))] : [videoFile!,...extraFiles];
      for (let index=0;index<sources.length;index++) {
        const entry=sources[index];
        if(typeof entry==="string") form.set("url",entry); else form.set("video",entry);
        const job=await createJob(form,(percent)=>setUploadPct(percent));
        onCreated(job);
        const remaining=sources.slice(index+1);
        if(tab==="url") setUrl(remaining.join("\n"));
        else {setVideoFile((remaining[0] as File)||null);setExtraFiles(remaining.slice(1) as File[]);}
      }
      setUrl("");
      setVideoFile(null);
      setMusicFile(null);
      setStreamer("");
      setGame("");
      setLayout("auto");
      setRights(false);
      if (videoInput.current) videoInput.current.value = "";
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "No se pudo crear el trabajo.",
      );
    } finally {
      setSubmitting(false);
      setUploadPct(null);
    }
  }

  const submitLabel = submitting
    ? uploadPct !== null && uploadPct < 100
      ? `Subiendo ${uploadPct}%`
      : "Preparando análisis…"
    : "Generar clips";

  return (
    <form onSubmit={handleSubmit} className="panel overflow-hidden">
      <div className="studio-actions px-5 pt-4"><label>Formato de salida<select className="field" value={aspect} onChange={e=>setAspect(e.target.value)}>{["9:16","1:1","16:9"].map(v=><option key={v}>{v}</option>)}</select></label>
      <label className="text-xs"><input type="checkbox" checked={useDNA} onChange={e=>setUseDNA(e.target.checked)}/> Usar mi Creator DNA</label></div>
      <div className="relative border-b border-veru-paper/[0.06] px-5 py-5 sm:px-6">
        <div className="pointer-events-none absolute -right-16 -top-20 h-44 w-44 rounded-full bg-veru-ember/20 blur-[60px]" />
        <div className="relative flex items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Crear clips</p>
            <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight">
              Pega el enlace o sube tu video
            </h2>
          </div>
          <span className="chip border-veru-ember/30 bg-veru-ember/10 text-veru-blush">
            <IconSparkles size={11} />
            IA
          </span>
        </div>

        <p className="mt-4 text-xs text-veru-paper/50">
          Pega un enlace de YouTube, Kick o Twitch y Clipwise descarga el video,
          encuentra los mejores momentos y los edita con subtítulos. También
          puedes subir un archivo.
        </p>
      </div>

      <div className="space-y-4 p-5 sm:p-6">
        <div className="grid grid-cols-2 gap-1 rounded-2xl border border-slate-200 bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => {
              setTab("url");
              setLocalError(null);
            }}
            aria-pressed={tab === "url"}
            className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition ${
              tab === "url"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <IconLink size={14} />
            Pegar enlace
          </button>
          <button
            type="button"
            onClick={() => {
              setTab("upload");
              setLocalError(null);
            }}
            aria-pressed={tab === "upload"}
            className={`inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition ${
              tab === "upload"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <IconUpload size={14} />
            Subir archivo
          </button>
        </div>

        {tab === "url" ? (
          <div className="space-y-3">
            <div className="relative">
              <IconLink
                size={17}
                className="pointer-events-none absolute left-3.5 top-3 text-veru-paper/25"
              />
              <textarea
                rows={2}
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="Pega el enlace de YouTube, Kick o Twitch"
                aria-label="Enlace del video"
                className="field pl-10"
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-medium">
              {["YouTube", "Kick", "Twitch"].map((platform) => (
                <span
                  key={platform}
                  className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-slate-500"
                >
                  {platform}
                </span>
              ))}
              <span className="ml-auto text-slate-400">VOD, clips y estrenos</span>
            </div>
            <p className="text-[11px] leading-relaxed text-veru-paper/55">
              Clipwise descarga el video y genera los cortes automáticamente.
              Para capturar un canal en directo, abre Directos.
            </p>
            <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-[11px] leading-relaxed text-slate-500">
              <input
                type="checkbox"
                checked={rights}
                onChange={(event) => setRights(event.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 accent-[#2563eb]"
              />
              <span>
                Confirmo que soy titular de este video o tengo permiso para
                procesarlo. Clipwise no elude DRM ni restricciones de acceso.
              </span>
            </label>
            <p className="text-[10px] leading-relaxed text-veru-paper/30">
              En videos largos se prioriza la pista de audio para analizar y luego
              se descargan los tramos elegidos. El ahorro depende de los formatos
              disponibles en la plataforma.
            </p>
          </div>
        ) : (
          <div>
            <input
              ref={videoInput}
              type="file"
              accept={VIDEO_EXTENSIONS.join(",")}
              className="hidden"
              multiple
              onChange={(event) => pickVideos(Array.from(event.target.files || []))}
            />
            <div
              role="button"
              tabIndex={0}
              onClick={() => videoInput.current?.click()}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  videoInput.current?.click();
                }
              }}
              onDragOver={(event) => {
                event.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              className={`flex min-h-[9.5rem] cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-6 text-center transition ${
                dragActive
                  ? "border-blue-500 bg-blue-50"
                  : "border-slate-300 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/60"
              }`}
            >
              {videoFile ? (
                <>
                  <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-100 text-blue-600">
                    <IconCheck size={20} />
                  </span>
                  <p className="max-w-full truncate text-sm font-medium text-slate-800">
                    {videoFile.name}{extraFiles.length>0 ? " + "+extraFiles.length+" archivos" : ""}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {formatBytes(videoFile.size)} · pulsa para cambiar
                  </p>
                  <button
                    type="button"
                    className="text-[10px] text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-slate-800"
                    onClick={(event) => {
                      event.stopPropagation();
                      setVideoFile(null);setExtraFiles([]);
                      if (videoInput.current) videoInput.current.value = "";
                    }}
                  >
                    Quitar archivo
                  </button>
                </>
              ) : (
                <>
                  <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-blue-600 shadow-sm ring-1 ring-slate-200">
                    <IconUpload size={20} />
                  </span>
                  <p className="text-sm font-medium text-slate-700">
                    Arrastra el video aquí o pulsa para elegirlo
                  </p>
                  <p className="text-[10px] leading-relaxed text-slate-400">
                    MP4, MOV, MKV, WEBM, M4V o AVI · máx. {maxUploadMb} MB ·{" "}
                    {sourceLimitLabel}
                  </p>
                </>
              )}
            </div>
          </div>
        )}

        <details className="group rounded-2xl border border-slate-200 bg-slate-50">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-medium text-slate-600">
            <span className="flex items-center gap-2">
              <IconSparkles size={14} className="text-veru-ember" />
              Ajustes avanzados (opcional) — por defecto Clipwise decide todo
            </span>
            <IconChevronDown size={14} className="text-slate-400 transition group-open:rotate-180" />
          </summary>
          <div className="space-y-4 border-t border-slate-200 px-4 py-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="label-xs">Creador / canal</span>
            <input
              type="text"
              value={streamer}
              onChange={(event) => setStreamer(event.target.value)}
              placeholder="Ej. Dr Donut"
              maxLength={40}
              className="field py-2.5"
            />
          </label>
          <label className="block">
            <span className="label-xs">Juego</span>
            <input
              type="text"
              value={game}
              onChange={(event) => setGame(event.target.value)}
              placeholder="Ej. Roblox"
              maxLength={60}
              className="field py-2.5"
            />
          </label>
        </div>

        <label className="block">
          <span className="label-xs">Composición</span>
          <select
            value={layout}
            onChange={(event) => setLayout(event.target.value)}
            className="field appearance-none py-2.5"
          >
            {layoutChoices.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          {selectedLayout && (
            <span className="mt-1.5 block text-[10px] leading-snug text-veru-paper/35">
              {selectedLayout.description}
            </span>
          )}
        </label>

        <div>
          <div className="flex items-center justify-between gap-3">
            <span className="label-xs mb-0">Estilo de subtítulos</span>
            {selectedStyle && (
              <span className="text-[10px] font-medium text-veru-ember">
                {selectedStyle.name}
              </span>
            )}
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {styles.map((item) => {
              const active = item.id === style;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setStyle(item.id)}
                  aria-pressed={active}
                  className={`caption-chip ${
                    active
                      ? "border-blue-500 bg-blue-50"
                      : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <span
                    className={`leading-none ${
                      STYLE_PREVIEW[item.id] ?? "text-[12px] font-bold"
                    }`}
                  >
                    Aa
                  </span>
                  <span
                    className={`text-[9px] font-medium uppercase tracking-[0.1em] ${
                      active ? "text-blue-700" : "text-slate-500"
                    }`}
                  >
                    {item.name}
                  </span>
                </button>
              );
            })}
          </div>
          {selectedStyle && (
            <p className="mt-2 text-[10px] leading-relaxed text-veru-paper/35">
              {selectedStyle.description}
            </p>
          )}
        </div>
          </div>
        </details>

        <details className="group rounded-2xl border border-slate-200 bg-slate-50">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-medium text-slate-600">
            <span className="flex items-center gap-2">
              <IconSparkles size={14} className="text-veru-ember" />
              Rótulo y ajustes avanzados
            </span>
            <IconChevronDown
              size={14}
              className="text-slate-400 transition group-open:rotate-180"
            />
          </summary>

          <div className="space-y-4 border-t border-slate-200 px-4 py-4">
            <div>
              <p className="text-[11px] font-semibold text-slate-700">
                Rótulo · título al inicio
              </p>
              <label className="mt-2 block">
                <span className="label-xs">Texto · {cardText.length}/120</span>
                <input
                  value={cardText}
                  maxLength={120}
                  placeholder="Se quema en los primeros segundos de cada clip"
                  onChange={(event) => setCardText(event.target.value)}
                  className="field py-2.5"
                />
              </label>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <label className="block">
                  <span className="label-xs">Estilo</span>
                  <select
                    value={cardStyle}
                    onChange={(event) => setCardStyle(event.target.value)}
                    className="field appearance-none px-3 py-2 text-xs"
                  >
                    <option value="impact">Impacto</option>
                    <option value="clean">Limpio</option>
                    <option value="box">Caja</option>
                  </select>
                </label>
                <label className="block">
                  <span className="label-xs">Posición</span>
                  <select
                    value={cardPosition}
                    onChange={(event) => setCardPosition(event.target.value)}
                    className="field appearance-none px-3 py-2 text-xs"
                  >
                    <option value="top">Arriba</option>
                    <option value="center">Centro</option>
                    <option value="bottom">Abajo</option>
                  </select>
                </label>
                <label className="block">
                  <span className="label-xs">Segundos</span>
                  <input
                    type="number"
                    min={0.5}
                    max={15}
                    step={0.5}
                    value={cardSeconds}
                    onChange={(event) =>
                      setCardSeconds(Number(event.target.value) || 4)
                    }
                    className="field px-3 py-2 text-xs"
                  />
                </label>
              </div>
            </div>

            <div className="divider" />

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="label-xs">Número de clips</span>
                <select
                  value={clips}
                  onChange={(event) => setClips(event.target.value)}
                  className="field appearance-none py-2.5"
                >
                  <option value="auto">Automático (5–15)</option>
                  {clipChoices.map((value) => (
                    <option key={value} value={String(value)}>
                      {value} clips
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label-xs">Idioma del audio</span>
                <select
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  className="field appearance-none py-2.5"
                >
                  {LANGUAGES.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <ToggleRow
                label="Contexto al inicio"
                hint="Frase breve del momento, sin etiquetas de canal ni juego."
                checked={contextOverlay}
                onChange={setContextOverlay}
              />
              <ToggleRow
                label="Recortar silencios"
                hint="Fuera pausas largas."
                checked={removeSilences}
                onChange={setRemoveSilences}
              />
              <ToggleRow
                label="Zoom dinámico"
                hint="Reencuadre con movimiento."
                checked={dynamicZoom}
                onChange={setDynamicZoom}
              />
            </div>

            <div>
              <input
                type="file"
                accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*"
                onChange={(event) => pickMusic(event.target.files?.[0] ?? null)}
                className="block w-full text-[11px] text-veru-paper/40 file:mr-3 file:rounded-full file:border-0 file:bg-veru-paper/[0.08] file:px-3 file:py-1.5 file:text-[11px] file:font-medium file:text-veru-paper/70 hover:file:bg-veru-paper/15"
              />
              {musicFile && (
                <div className="mt-2 flex items-center justify-between gap-3 text-[10px] text-veru-paper/40">
                  <span className="truncate">
                    {musicFile.name} · {formatBytes(musicFile.size)}
                  </span>
                  <button
                    type="button"
                    onClick={() => setMusicFile(null)}
                    className="inline-flex items-center gap-1 text-veru-paper/40 hover:text-veru-paper/80"
                  >
                    <IconX size={11} />
                    Quitar
                  </button>
                </div>
              )}
              <p className="mt-1.5 flex items-center gap-1.5 text-[10px] text-veru-paper/30">
                <IconMusic size={11} />
                Música de fondo opcional, mezclada por debajo de la voz.
              </p>
            </div>
          </div>
        </details>

        {localError && (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
            {localError}
          </p>
        )}

        {!engineReady && (
          <p className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
            FFmpeg no está disponible. Revisa la configuración del motor antes
            de procesar videos.
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !engineReady}
          className="button-primary w-full py-3.5 text-sm"
        >
          <IconSparkles size={17} />
          {submitLabel}
        </button>

        {submitting && uploadPct !== null && (
          <div className="h-1.5 overflow-hidden rounded-full bg-veru-paper/10">
            <div
              className="h-full rounded-full bg-veru-ember transition-[width]"
              style={{ width: `${Math.max(3, uploadPct)}%` }}
            />
          </div>
        )}

        <p className="text-center text-[10px] leading-relaxed text-veru-paper/30">
          Procesado en Clipwise con Whisper + FFmpeg · Sin marca de agua forzada ·
          Clips verticales 1080×1920
        </p>
      </div>
    </form>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 rounded-2xl border border-veru-paper/[0.08] bg-veru-paper/[0.02] px-3.5 py-3">
      <span className="min-w-0">
        <span className="block text-[11px] font-medium text-veru-paper/70">
          {label}
        </span>
        <span className="mt-0.5 block text-[9px] text-veru-paper/30">{hint}</span>
      </span>
      <span className="relative shrink-0">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          className="peer sr-only"
        />
        <span className="toggle-track block peer-checked:border-veru-ember peer-checked:bg-veru-ember/30" />
        <span className="toggle-knob peer-checked:left-[18px] peer-checked:bg-veru-ember" />
      </span>
    </label>
  );
}
