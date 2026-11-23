import { useState, type ReactNode } from "react";
import { AISettingsCard } from "./AISettingsCard";

import type { Health, OptionsResponse } from "../lib/types";
import {
  IconCheck,
  IconFilm,
  IconScissors,
  IconSparkles,
  IconTikTok,
  IconWand,
  IconYouTube,
} from "./icons";

const PIPELINE = [
  { n: "01", title: "Transcribe", body: "Whisper local, palabra a palabra." },
  { n: "02", title: "Analiza", body: "Escenas, audio, risas y tensión." },
  { n: "03", title: "Puntúa", body: "Momentos de 1 a 100 con contexto." },
  { n: "04", title: "Reencuadra", body: "9:16, cámaras y juego en su sitio." },
  { n: "05", title: "Subtitula", body: "Estilo, rótulo y sincronía fina." },
  { n: "06", title: "Publica", body: "YouTube y TikTok desde el clip." },
];

export function AIPanel({
  health,
  options,
  onGoCreate,
}: {
  health: Health | null;
  options: OptionsResponse | null;
  onGoCreate: () => void;
}) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const llm = configured ?? health?.llm === "enabled";
  const styleCount = options?.subtitle_styles.length ?? 9;
  const layoutCount = options?.layouts?.length ?? 13;
  const model = health?.whisper_model ?? "Whisper";

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-[36px] border border-veru-paper/[0.08] bg-veru-card/60 p-7 sm:p-11">
        <div className="pointer-events-none absolute -left-24 -top-32 h-80 w-80 rounded-full bg-veru-ember/25 blur-[110px]" />
        <div className="pointer-events-none absolute -bottom-40 right-0 h-96 w-96 rounded-full bg-veru-ember/10 blur-[120px]" />
        <div className="relative max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-veru-ember/30 bg-veru-ember/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-veru-blush">
            <IconSparkles size={12} />
            Motor IA
          </span>
          <h1 className="mt-5 text-4xl font-bold leading-[0.98] tracking-tighter sm:text-5xl">
            Toda la cadena de un clip,{" "}
            <span className="accent-italic">en una sola mesa.</span>
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-veru-paper/55">
            Clipwise escucha el directo, encuentra lo que merece cortarse,
            reencuadra a vertical y quema los subtítulos. Todo corre en tu
            máquina; el LLM solo entra si tú lo conectas.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="chip border-veru-ember/25 bg-veru-ember/10 text-veru-blush">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Procesado local
            </span>
            <span className="chip">{model}</span>
            <span className="chip">
              {llm ? "LLM conectado" : "Puntuación heurística"}
            </span>
            <span className="chip">{styleCount} estilos de subtítulo</span>
          </div>
          <button type="button" onClick={onGoCreate} className="button-primary mt-7">
            <IconSparkles size={16} />
            Crear un clip
          </button>
        </div>
      </section>

      <AISettingsCard onChanged={setConfigured} />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <CapabilityCard
          icon={<IconWand size={18} />}
          kicker="Transcripción"
          title="Cada palabra, con su tiempo"
          body={`${model} convierte la voz en subtítulos sincronizados. Detecta el idioma o fíjalo en español, inglés, portugués y más.`}
          points={["Whisper local", "Timestamps por palabra", "Sin subir el audio"]}
        />
        <CapabilityCard
          icon={<IconScissors size={18} />}
          kicker="Momentos virales"
          title="La IA decide qué cortar"
          body={
            llm
              ? "El LLM lee la transcripción y puntúa gancho, tensión, humor y retención. Tú solo eliges cuántos clips quieres."
              : "El motor puntúa gancho, claridad, intensidad, sorpresa y retención sin salir de tu equipo. Conecta un LLM para afinar la selección."
          }
          points={["Score de 1 a 100", "Categorías y contexto", "5–15 clips por video"]}
        />
        <CapabilityCard
          icon={<IconFilm size={18} />}
          kicker="Reencuadre"
          title="Cámaras y juego, en vertical"
          body="Detección de facecam con OpenCV, plantillas para una, dos, tres o cuatro cámaras y cajas manuales cuando quieres mandar tú."
          points={[`${layoutCount} plantillas`, "Seguimiento de cara", "Editor manual 9:16"]}
        />
        <CapabilityCard
          icon={<IconSparkles size={18} />}
          kicker="Subtítulos"
          title="Estilos que se leen en el feed"
          body="Impacto, minimalista, caja, píldora, neón y amarillo. Elige la voz visual del clip y añade un rótulo que enganche al inicio."
          points={[`${styleCount} estilos`, "Rótulo editable", "ASS incrustado en el MP4"]}
        />
        <CapabilityCard
          icon={<IconWand size={18} />}
          kicker="Montaje"
          title="Silencios fuera, ritmo dentro"
          body="Recorta pausas largas sin cortar la voz, activa el zoom dinámico y deja el contexto del creador en pantalla durante los primeros segundos."
          points={["Corte de silencios", "Zoom y reencuadre", "Contexto con rótulo"]}
        />
        <CapabilityCard
          icon={<IconYouTube size={18} />}
          kicker="Publicación"
          title="Del render al feed"
          body="Descarga el MP4 1080×1920, el SRT y los textos, o publica directo en YouTube y TikTok con las cuentas que conectes."
          points={["YouTube + TikTok", "Textos por plataforma", "Sin marca de agua"]}
          extra={
            <div className="flex items-center gap-2 text-veru-paper/35">
              <IconYouTube size={14} />
              <IconTikTok size={14} />
            </div>
          }
        />
      </section>

      <section className="panel p-6 sm:p-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow">La cadena</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              Del enlace al clip, sin saltos.
            </h2>
          </div>
          <span className="chip">
            <IconCheck size={11} />
            Un solo trabajo
          </span>
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {PIPELINE.map((step) => (
            <div
              key={step.n}
              className="group rounded-2xl border border-veru-paper/[0.08] bg-black/20 p-4 transition hover:border-veru-ember/40 hover:bg-veru-ember/[0.04]"
            >
              <span className="font-mono text-[10px] tracking-widest text-veru-ember">
                {step.n}
              </span>
              <p className="mt-2 font-display text-sm font-semibold tracking-tight text-veru-paper">
                {step.title}
              </p>
              <p className="mt-1 text-[11px] leading-relaxed text-veru-paper/40">
                {step.body}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function CapabilityCard({
  icon,
  kicker,
  title,
  body,
  points,
  extra,
}: {
  icon: ReactNode;
  kicker: string;
  title: string;
  body: string;
  points: string[];
  extra?: ReactNode;
}) {
  return (
    <article className="group relative overflow-hidden rounded-3xl border border-veru-paper/[0.08] bg-veru-card/70 p-5 transition duration-300 hover:border-veru-ember/40">
      <div className="pointer-events-none absolute -right-12 -top-12 h-28 w-28 rounded-full bg-veru-ember/0 blur-2xl transition duration-500 group-hover:bg-veru-ember/15" />
      <div className="relative flex items-start justify-between gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-veru-ember/25 bg-veru-ember/10 text-veru-blush">
          {icon}
        </span>
        <span className="text-[9px] font-semibold uppercase tracking-[0.2em] text-veru-paper/30">
          {kicker}
        </span>
      </div>
      <h3 className="relative mt-4 font-display text-lg font-semibold leading-snug tracking-tight">
        {title}
      </h3>
      <p className="relative mt-2 text-xs leading-relaxed text-veru-paper/45">{body}</p>
      <ul className="relative mt-4 space-y-1.5">
        {points.map((point) => (
          <li key={point} className="flex items-center gap-2 text-[11px] text-veru-paper/60">
            <IconCheck size={12} className="shrink-0 text-veru-ember" />
            {point}
          </li>
        ))}
      </ul>
      {extra ? <div className="relative mt-4">{extra}</div> : null}
    </article>
  );
}
