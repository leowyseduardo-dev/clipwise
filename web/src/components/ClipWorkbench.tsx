import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import {
  clipFrameUrl,
  saveClipCopy,
  saveClipEdit,
} from "../lib/api";
import { ClipBattle, HookPicker } from "./EditorialStudio";
import { PresetControls, ExportControls, type ExportLook } from "./ExportControls";
import { formatTime } from "../lib/format";
import type {
  CameraBox,
  Clip,
  LayoutOption,
  SubtitleStyleOption,
  TitleCardPosition,
  TitleCardStyle,
} from "../lib/types";
import {
  IconCheck,
  IconCopy,
  IconDownload,
  IconFilm,
  IconLoader,
  IconRefresh,
  IconSparkles,
  IconWand,
  IconX,
} from "./icons";

const DEFAULT_STYLES: SubtitleStyleOption[] = [
  { id: "shorts", name: "Shorts", description: "Una palabra a la vez, mayúsculas y borde grueso." },
  { id: "impact", name: "Impacto", description: "Impact en mayúsculas, palabra activa en amarillo." },
  { id: "bold", name: "Bold", description: "Grande, grueso y con palabra resaltada." },
  { id: "clean", name: "Limpio", description: "Elegante y fácil de leer." },
  { id: "pill", name: "Píldora", description: "La palabra que suena va dentro de una píldora blanca." },
  { id: "box", name: "Caja", description: "Texto sobre una caja oscura, siempre legible." },
  { id: "yellow", name: "Amarillo", description: "El amarillo clásico de los virales, con borde negro." },
  { id: "neon", name: "Neón", description: "Contraste alto con acento cian." },
  { id: "minimal", name: "Minimal", description: "Discreto, para no tapar la imagen." },
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

const TEMPLATE_GROUPS: { label: string; ids: string[] }[] = [
  { label: "Solo cámaras", ids: ["vertical", "dividido", "trio", "cuarteto", "spotlight"] },
  { label: "Con juego", ids: ["cam_juego", "dos_cams_juego", "tres_cams_juego", "trio_juego"] },
  { label: "Otros", ids: ["auto", "centrado", "horizontal"] },
];

const STYLE_PREVIEW: Record<string, string> = {
  shorts: "text-[20px] font-black uppercase tracking-tight",
  impact: "text-[20px] font-black uppercase italic tracking-tighter",
  bold: "text-[20px] font-extrabold tracking-tight",
  clean: "text-[18px] font-medium",
  pill: "rounded-full bg-veru-paper px-2.5 py-1 text-[13px] font-bold text-veru-ink",
  box: "rounded bg-veru-ink px-2 py-1 text-[13px] font-bold text-veru-paper ring-1 ring-veru-paper/25",
  yellow: "text-[20px] font-black text-yellow-300",
  neon: "text-[20px] font-black text-veru-blush",
  minimal: "text-[16px] font-normal",
};

const CARD_STYLES: { id: TitleCardStyle; name: string; preview: string }[] = [
  { id: "impact", name: "Impacto", preview: "text-[16px] font-black uppercase italic tracking-tighter" },
  { id: "clean", name: "Limpio", preview: "text-[15px] font-medium" },
  { id: "box", name: "Caja", preview: "rounded bg-veru-ink px-2 py-0.5 text-[12px] font-bold ring-1 ring-veru-paper/25" },
];

const CARD_POSITIONS: { id: TitleCardPosition; name: string }[] = [
  { id: "top", name: "Arriba" },
  { id: "center", name: "Centro" },
  { id: "bottom", name: "Abajo" },
];

type StudioTab = "plantilla" | "subtitulos" | "rotulo" | "camaras" | "texto" | "battle";

const TABS: { id: StudioTab; label: string; icon: typeof IconFilm }[] = [
  { id: "plantilla", label: "Plantilla", icon: IconFilm },
  { id: "subtitulos", label: "Subtítulos", icon: IconSparkles },
  { id: "rotulo", label: "Rótulo", icon: IconWand },
  { id: "camaras", label: "Cámaras", icon: IconFilm },
  { id: "battle", label: "Clip Battle", icon: IconFilm },
  { id: "texto", label: "Texto", icon: IconCopy },
];

function clampBox(box: CameraBox): CameraBox {
  const w = Math.min(Math.max(box.w, 0.05), 1);
  const h = Math.min(Math.max(box.h, 0.05), 1);
  return {
    x: Math.min(Math.max(box.x, 0), 1 - w),
    y: Math.min(Math.max(box.y, 0), 1 - h),
    w,
    h,
  };
}

export function ClipWorkbench({
  clip,
  busy,
  onUpdated,
  onError,
  styles,
  layouts,
}: {
  clip: Clip;
  busy: boolean;
  onUpdated: (clip: Clip, message?: string) => void;
  onError: (message: string) => void;
  styles?: SubtitleStyleOption[];
  layouts?: LayoutOption[];
}) {
  const [tab, setTab] = useState<StudioTab>("plantilla");
  const [title, setTitle] = useState(clip.title || "");
  const [description, setDescription] = useState(clip.description || "");
  const [caption, setCaption] = useState(clip.caption || "");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [copied, setCopied] = useState("");

  const options = clip.overlay?.render_options;
  const [look, setLook] = useState<ExportLook>(() => ({platform:options?.platform||"universal",sound_accent:options?.sound_accent||false,logo_id:options?.logo_id||"",transition:options?.transition||"cut",aspect: options?.aspect || "9:16", caption_font: options?.caption_font || "", caption_color: options?.caption_color || "", accent_color: options?.accent_color || "", music_level: options?.music_level ?? null, saturation: options?.saturation ?? 1, brand_text: options?.brand_text || ""}));
  const storedLayout = options?.layout === "split" ? "cam_juego" : options?.layout;
  const [style, setStyle] = useState(clip.style || "shorts");
  const [layout, setLayout] = useState<string>(storedLayout || "auto");
  const [silences, setSilences] = useState(options?.remove_silences ?? true);
  const [zoom, setZoom] = useState(options?.dynamic_zoom ?? true);
  const [context, setContext] = useState(options?.context_overlay ?? true);
  const [cardText, setCardText] = useState(options?.title_card || "");
  const [cardSeconds, setCardSeconds] = useState<number>(options?.title_card_seconds ?? 4);
  const [cardPosition, setCardPosition] = useState<string>(options?.title_card_position || "top");
  const [cardStyle, setCardStyle] = useState<string>(options?.title_card_style || "impact");
  const [manualCams, setManualCams] = useState<CameraBox[]>(options?.manual_cams ?? []);

  const [frameTime, setFrameTime] = useState(0);
  const [frameAspect, setFrameAspect] = useState(16 / 9);
  const [frameError, setFrameError] = useState(false);
  const frameRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    index: number;
    mode: "move" | "resize";
    startX: number;
    startY: number;
    rect: DOMRect;
    box: CameraBox;
  } | null>(null);
  const [dragging, setDragging] = useState(false);

  const styleChoices = styles?.length ? styles : DEFAULT_STYLES;
  const layoutChoices = layouts?.length ? layouts : DEFAULT_LAYOUTS;
  const selectedStyle = styleChoices.find((item) => item.id === style);
  const selectedLayout = layoutChoices.find((item) => item.id === layout);
  const processing = clip.status === "queued" || clip.status === "rendering";

  useEffect(() => {
    if (!dirty) {
      setTitle(clip.title || "");
      setDescription(clip.description || "");
      setCaption(clip.caption || "");
    }
  }, [clip.title, clip.description, clip.caption, dirty]);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(""), 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = (event.clientX - drag.startX) / drag.rect.width;
      const dy = (event.clientY - drag.startY) / drag.rect.height;
      setManualCams((previous) =>
        previous.map((box, index) => {
          if (index !== drag.index) return box;
          if (drag.mode === "move") {
            return clampBox({
              ...box,
              x: drag.box.x + dx,
              y: drag.box.y + dy,
            });
          }
          return clampBox({
            ...box,
            w: drag.box.w + dx,
            h: drag.box.h + dy,
          });
        }),
      );
    };
    const onUp = () => {
      dragRef.current = null;
      setDragging(false);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [dragging]);

  async function copy(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
    } catch {
      onError("No se pudo copiar. Puedes seleccionar el texto manualmente.");
    }
  }

  async function save() {
    setSaving(true);
    try {
      const updated = await saveClipCopy(clip.id, {
        title: title.trim(),
        description,
        caption,
      });
      onUpdated(updated, "Título y textos guardados para publicar.");
      setDirty(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudo guardar.");
    } finally {
      setSaving(false);
    }
  }

  async function render() {
    setApplying(true);
    try {
      const updated = await saveClipEdit(clip.id, {
        ...look,
        subtitle_style: style,
        layout,
        remove_silences: silences,
        dynamic_zoom: zoom,
        context_overlay: context,
        title_card: cardText.trim(),
        title_card_seconds: cardSeconds,
        title_card_position: cardPosition,
        title_card_style: cardStyle,
        manual_cams: manualCams.map((box) => ({
          x: Number(box.x.toFixed(4)),
          y: Number(box.y.toFixed(4)),
          w: Number(box.w.toFixed(4)),
          h: Number(box.h.toFixed(4)),
        })),
      });
      onUpdated(
        updated,
        "Edición en cola. La vista previa se actualizará al terminar.",
      );
    } catch (error) {
      onError(error instanceof Error ? error.message : "No se pudo aplicar la edición.");
    } finally {
      setApplying(false);
    }
  }

  function startDrag(
    event: ReactPointerEvent<HTMLElement>,
    index: number,
    mode: "move" | "resize",
  ) {
    if (processing) return;
    const frame = frameRef.current;
    if (!frame) return;
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = {
      index,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      rect: frame.getBoundingClientRect(),
      box: manualCams[index],
    };
    setDragging(true);
  }

  function addCamera() {
    if (manualCams.length >= 4) return;
    const offset = manualCams.length * 0.04;
    setManualCams((previous) => [
      ...previous,
      clampBox({ x: 0.03 + offset, y: 0.04 + offset, w: 0.3, h: 0.34 }),
    ]);
  }

  function removeCamera(index: number) {
    setManualCams((previous) => previous.filter((_, item) => item !== index));
  }

  const canRender = !processing && !busy && !applying;

  return (
    <div className="overflow-hidden rounded-3xl border border-veru-ember/20 bg-veru-ember/[0.03]">
      <div className="border-b border-veru-paper/[0.06] px-4 py-3.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-veru-ember text-veru-ink">
              <IconWand size={13} />
            </span>
            <div>
              <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-veru-ember">
                Estudio
              </p>
              <p className="text-[11px] font-medium text-veru-paper/60">
                Editor de clip
              </p>
            </div>
          </div>
          {processing && (
            <span className="chip border-veru-ember/30 bg-veru-ember/10 text-veru-blush">
              <IconLoader size={10} className="animate-spin" />
              Renderizando
            </span>
          )}
        </div>

        <div className="mt-3 flex gap-3 rounded-2xl border border-veru-paper/[0.08] bg-black/25 p-2.5">
          <div className="relative aspect-[9/16] w-[64px] shrink-0 overflow-hidden rounded-xl border border-veru-paper/10 bg-black">
            {clip.thumb_url ? (
              <img
                src={clip.thumb_url}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="flex h-full w-full items-center justify-center text-veru-paper/20">
                <IconFilm size={16} />
              </span>
            )}
            <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-1 pb-1 pt-3 text-center">
              <span className="line-clamp-1 text-[6px] font-black uppercase leading-tight text-veru-paper">
                {cardText || "CLIP"}
              </span>
            </span>
          </div>
          <div className="min-w-0 flex-1 py-0.5">
            <p className="text-[9px] font-medium uppercase tracking-[0.16em] text-veru-paper/35">
              Clip {String(clip.idx + 1).padStart(2, "0")} ·{" "}
              {formatTime(clip.duration)}
            </p>
            <p className="mt-1 line-clamp-2 text-[12px] font-semibold leading-snug text-veru-paper/85">
              {clip.title || `Clip ${clip.idx + 1}`}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-full border border-veru-paper/10 bg-veru-paper/[0.04] px-2 py-0.5 text-[9px] text-veru-paper/50">
                {selectedLayout?.name ?? layout}
              </span>
              <span className="rounded-full border border-veru-paper/10 bg-veru-paper/[0.04] px-2 py-0.5 text-[9px] text-veru-paper/50">
                {selectedStyle?.name ?? style}
              </span>
              {manualCams.length > 0 && (
                <span className="rounded-full border border-veru-ember/30 bg-veru-ember/10 px-2 py-0.5 text-[9px] text-veru-blush">
                  {manualCams.length} cámara{manualCams.length === 1 ? "" : "s"}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => void render()}
            disabled={!canRender}
            className="button-primary shrink-0 self-center px-3.5 py-2.5 text-[11px]"
          >
            {applying ? (
              <IconLoader size={13} className="animate-spin" />
            ) : (
              <IconWand size={13} />
            )}
            {applying ? "Aplicando" : "Aplicar"}
          </button>
        </div>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-veru-paper/[0.06] px-3 py-2 no-scrollbar">
        {TABS.map((item) => {
          const active = tab === item.id;
          const TabIcon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              aria-pressed={active}
              className={`shrink-0 rounded-full px-3 py-1.5 text-[10px] font-semibold transition ${
                active
                  ? "bg-veru-paper text-veru-ink"
                  : "text-veru-paper/40 hover:bg-veru-paper/[0.05] hover:text-veru-paper/75"
              }`}
            >
              <span className="inline-flex items-center gap-1.5">
                <TabIcon size={11} />
                {item.label}
              </span>
            </button>
          );
        })}
      </div>

      <div className="p-4">
        <fieldset disabled={processing} className="disabled:opacity-50">
          {tab === "plantilla" && (
            <div className="space-y-4">
              <ExportControls value={look} onChange={setLook}/>
              <PresetControls settings={{...look,subtitle_style:style,layout,remove_silences:silences,dynamic_zoom:zoom,context_overlay:context,title_card_style:cardStyle,title_card_position:cardPosition,title_card_seconds:cardSeconds}} apply={preset=>{
                setLook(preset);setStyle(preset.subtitle_style);setLayout(preset.layout);setSilences(preset.remove_silences);setZoom(preset.dynamic_zoom);setContext(preset.context_overlay);
                setCardStyle(preset.title_card_style);setCardPosition(preset.title_card_position);setCardSeconds(preset.title_card_seconds);
              }}/>
              {TEMPLATE_GROUPS.map((group) => {
                const items = group.ids
                  .map((id) => layoutChoices.find((item) => item.id === id))
                  .filter((item): item is LayoutOption => Boolean(item));
                if (!items.length) return null;
                return (
                  <div key={group.label}>
                    <p className="mb-2 text-[9px] font-semibold uppercase tracking-[0.18em] text-veru-paper/35">
                      {group.label}
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      {items.map((item) => {
                        const active = layout === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => setLayout(item.id)}
                            aria-pressed={active}
                            className={`template-pill ${
                              active
                                ? "border-veru-ember/70 bg-veru-ember/[0.08]"
                                : "border-veru-paper/[0.08] bg-black/20 hover:border-veru-paper/20"
                            }`}
                          >
                            <span className="flex h-14 w-full items-center justify-center rounded-xl bg-black/35 p-1.5">
                              <LayoutGlyph id={item.id} />
                            </span>
                            <span
                              className={`truncate text-[10px] font-medium ${
                                active ? "text-veru-blush" : "text-veru-paper/60"
                              }`}
                            >
                              {item.name}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              {selectedLayout && (
                <p className="rounded-2xl border border-veru-paper/[0.06] bg-black/20 px-3 py-2 text-[10px] leading-relaxed text-veru-paper/40">
                  {selectedLayout.description}
                </p>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                <ToggleRow
                  label="Acortar silencios"
                  hint="Respeta la voz"
                  checked={silences}
                  onChange={setSilences}
                />
                <ToggleRow
                  label="Zoom dinámico"
                  hint="Reencuadre con movimiento"
                  checked={zoom}
                  onChange={setZoom}
                />
                <ToggleRow
                  label="Contexto al inicio"
                  hint="Frase breve del momento"
                  checked={context}
                  onChange={setContext}
                />
              </div>
            </div>
          )}

          {tab === "subtitulos" && (
            <div>
              <div className="grid grid-cols-3 gap-2">
                {styleChoices.map((item) => {
                  const active = style === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setStyle(item.id)}
                      aria-pressed={active}
                      className={`caption-chip ${
                        active
                          ? "border-veru-ember/70 bg-veru-ember/[0.08]"
                          : "border-veru-paper/[0.08] bg-black/20 hover:border-veru-paper/20"
                      }`}
                    >
                      <span
                        className={`leading-none ${
                          STYLE_PREVIEW[item.id] ?? "text-[16px] font-bold"
                        }`}
                      >
                        Aa
                      </span>
                      <span
                        className={`text-[9px] font-medium uppercase tracking-[0.1em] ${
                          active ? "text-veru-blush" : "text-veru-paper/35"
                        }`}
                      >
                        {item.name}
                      </span>
                    </button>
                  );
                })}
              </div>
              {selectedStyle && (
                <p className="mt-3 rounded-2xl border border-veru-paper/[0.06] bg-black/20 px-3 py-2 text-[10px] leading-relaxed text-veru-paper/40">
                  {selectedStyle.description}
                </p>
              )}
            </div>
          )}

          {tab === "battle" && <ClipBattle clip={clip}/>}
          {tab === "rotulo" && (
            <div className="space-y-3">
              <HookPicker clip={clip} choose={setCardText}/>
              <label className="block">
                <span className="label-xs">Texto · {cardText.length}/120</span>
                <input
                  value={cardText}
                  maxLength={120}
                  placeholder="El título que engancha al principio del clip"
                  onChange={(event) => setCardText(event.target.value)}
                  className="field py-2.5"
                />
              </label>
              <div>
                <span className="label-xs">Estilo</span>
                <div className="grid grid-cols-3 gap-2">
                  {CARD_STYLES.map((item) => {
                    const active = cardStyle === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setCardStyle(item.id)}
                        aria-pressed={active}
                        className={`caption-chip ${
                          active
                            ? "border-veru-ember/70 bg-veru-ember/[0.08]"
                            : "border-veru-paper/[0.08] bg-black/20 hover:border-veru-paper/20"
                        }`}
                      >
                        <span className={`leading-none ${item.preview}`}>Aa</span>
                        <span
                          className={`text-[9px] font-medium uppercase tracking-[0.1em] ${
                            active ? "text-veru-blush" : "text-veru-paper/35"
                          }`}
                        >
                          {item.name}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <span className="label-xs">Posición</span>
                <div className="grid grid-cols-3 gap-1 rounded-full border border-veru-paper/[0.08] bg-black/25 p-1">
                  {CARD_POSITIONS.map((item) => {
                    const active = cardPosition === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setCardPosition(item.id)}
                        aria-pressed={active}
                        className={`rounded-full px-2 py-1.5 text-[10px] font-semibold transition ${
                          active
                            ? "bg-veru-paper text-veru-ink"
                            : "text-veru-paper/40 hover:text-veru-paper/75"
                        }`}
                      >
                        {item.name}
                      </button>
                    );
                  })}
                </div>
              </div>
              <label className="block">
                <span className="label-xs">
                  Duración · {cardSeconds.toFixed(1)} s
                </span>
                <input
                  type="range"
                  min={0.5}
                  max={15}
                  step={0.5}
                  value={cardSeconds}
                  onChange={(event) => setCardSeconds(Number(event.target.value))}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-veru-paper/10 accent-[#a04cf5]"
                />
              </label>
              <div className="relative overflow-hidden rounded-2xl border border-veru-paper/[0.08] bg-black/40 p-4">
                <div className="pointer-events-none absolute inset-0 bg-radial-ember" />
                <p
                  className={`relative text-center ${
                    CARD_STYLES.find((item) => item.id === cardStyle)?.preview ??
                    ""
                  } ${cardPosition === "center" ? "py-4" : ""}`}
                >
                  {cardText.trim() || "TU RÓTULO AQUÍ"}
                </p>
              </div>
            </div>
          )}

          {tab === "camaras" && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[10px] leading-relaxed text-veru-paper/40">
                  Dibuja las cámaras sobre el fotograma. Se aplican al render.
                </p>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setManualCams([])}
                    className="button-soft px-2.5 py-1.5 text-[10px]"
                  >
                    <IconRefresh size={11} />
                    Auto
                  </button>
                  <button
                    type="button"
                    onClick={addCamera}
                    disabled={manualCams.length >= 4}
                    className="button-soft px-2.5 py-1.5 text-[10px] disabled:opacity-40"
                  >
                    + Cámara
                  </button>
                </div>
              </div>

              <div
                ref={frameRef}
                className="relative mx-auto w-full max-w-[520px] touch-none select-none overflow-hidden rounded-2xl border border-veru-paper/15 bg-black"
                style={{ aspectRatio: String(frameAspect) }}
              >
                {frameError ? (
                  <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-radial-ember px-4 text-center">
                    <IconFilm size={20} className="text-veru-paper/30" />
                    <p className="text-[10px] leading-relaxed text-veru-paper/40">
                      No se encontró el video original. Puedes guardar las cajas
                      y se aplicarán al renderizar.
                    </p>
                  </div>
                ) : (
                  <img
                    src={clipFrameUrl(clip.id, frameTime)}
                    alt="Fotograma del video original"
                    draggable={false}
                    onLoad={(event) => {
                      const image = event.currentTarget;
                      if (image.naturalWidth && image.naturalHeight) {
                        setFrameAspect(image.naturalWidth / image.naturalHeight);
                      }
                      setFrameError(false);
                    }}
                    onError={() => setFrameError(true)}
                    className="absolute inset-0 h-full w-full object-contain"
                  />
                )}

                {manualCams.map((box, index) => (
                  <div
                    key={index}
                    role="button"
                    tabIndex={0}
                    aria-label={`Cámara ${index + 1}`}
                    onPointerDown={(event) => startDrag(event, index, "move")}
                    className={`camera-box cursor-move rounded-sm ${
                      dragging ? "select-none" : ""
                    }`}
                    style={{
                      left: `${box.x * 100}%`,
                      top: `${box.y * 100}%`,
                      width: `${box.w * 100}%`,
                      height: `${box.h * 100}%`,
                    }}
                  >
                    <span className="pointer-events-none absolute left-1 top-1 rounded bg-veru-ember px-1 py-0.5 text-[8px] font-bold leading-none text-veru-ink">
                      CAM {index + 1}
                    </span>
                    <button
                      type="button"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation();
                        removeCamera(index);
                      }}
                      className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded bg-veru-ink/80 text-veru-paper/70 hover:text-veru-paper"
                      aria-label={`Quitar cámara ${index + 1}`}
                    >
                      <IconX size={9} />
                    </button>
                    <span
                      onPointerDown={(event) => startDrag(event, index, "resize")}
                      className="absolute -bottom-1 -right-1 h-3.5 w-3.5 cursor-nwse-resize rounded-sm border border-veru-ink bg-veru-ember"
                    />
                  </div>
                ))}

                {manualCams.length === 0 && (
                  <div className="pointer-events-none absolute inset-0 flex items-end justify-center pb-3">
                    <span className="rounded-full border border-veru-paper/15 bg-black/70 px-3 py-1 text-[9px] text-veru-paper/50 backdrop-blur">
                      Detección automática · añade cajas para mandar tú
                    </span>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <label className="flex flex-1 items-center gap-2 text-[10px] text-veru-paper/40">
                  <span className="shrink-0 font-mono text-[9px] tabular-nums">
                    {frameTime.toFixed(1)} s
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0.1, (clip.duration ?? 1) - 0.1)}
                    step={0.1}
                    value={frameTime}
                    onChange={(event) => setFrameTime(Number(event.target.value))}
                    className="h-1 w-full cursor-pointer appearance-none rounded-full bg-veru-paper/10 accent-[#a04cf5]"
                    aria-label="Fotograma del clip"
                  />
                  <span className="shrink-0 font-mono text-[9px] tabular-nums">
                    {formatTime(clip.duration)}
                  </span>
                </label>
                <span className="chip">{manualCams.length}/4</span>
              </div>
            </div>
          )}

          {tab === "texto" && (
            <div className="space-y-3">
              <p className="text-[10px] leading-relaxed text-veru-paper/40">
                Edita el texto que se enviará a YouTube y TikTok. No cambia el
                texto quemado en el video.
              </p>
              <label className="block">
                <span className="label-xs">Título · {title.length}/100</span>
                <input
                  aria-label="Título de publicación"
                  className="field py-2.5"
                  value={title}
                  maxLength={100}
                  onChange={(event) => {
                    setTitle(event.target.value);
                    setDirty(true);
                  }}
                />
              </label>
              <label className="block">
                <span className="label-xs">YouTube · descripción y hashtags</span>
                <textarea
                  aria-label="Texto de YouTube"
                  className="field"
                  rows={5}
                  maxLength={5000}
                  value={description}
                  onChange={(event) => {
                    setDescription(event.target.value);
                    setDirty(true);
                  }}
                />
              </label>
              <label className="block">
                <span className="label-xs">TikTok / Reels · caption y hashtags</span>
                <textarea
                  aria-label="Texto de TikTok y Reels"
                  className="field"
                  rows={4}
                  maxLength={2200}
                  value={caption}
                  onChange={(event) => {
                    setCaption(event.target.value);
                    setDirty(true);
                  }}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void save()}
                  disabled={!dirty || !title.trim() || saving}
                  className="button-primary px-4 py-2.5 text-[11px] disabled:opacity-40"
                >
                  {saving ? (
                    <IconLoader size={12} className="animate-spin" />
                  ) : (
                    <IconCheck size={12} />
                  )}
                  Guardar textos
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => void copy(title, "title")}
                >
                  <IconCopy size={12} />
                  {copied === "title" ? "Copiado" : "Copiar título"}
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => void copy(`${title}\n\n${caption}`, "pack")}
                >
                  <IconCopy size={12} />
                  {copied === "pack" ? "Copiado" : "Copiar paquete"}
                </button>
              </div>
              {dirty && (
                <p className="text-[10px] text-amber-700">
                  Cambios sin guardar. Guarda antes de publicar o descargar el
                  texto.
                </p>
              )}
              <a
                href={`/api/clips/${clip.id}/publication.txt`}
                download
                className="inline-flex items-center gap-1.5 text-[10px] text-veru-blush/70 hover:text-veru-paper"
              >
                <IconDownload size={11} />
                Descargar textos guardados (.txt)
              </a>
            </div>
          )}
        </fieldset>

        <div className="mt-3 flex items-center justify-between gap-2 border-t border-veru-paper/[0.06] pt-3">
          <p className="text-[9px] leading-relaxed text-veru-paper/25">
            Se genera una nueva versión. La vista anterior sigue disponible
            durante el render.
          </p>
          <button
            type="button"
            onClick={() => void render()}
            disabled={!canRender}
            className="button-primary shrink-0 px-4 py-2.5 text-[11px]"
          >
            {applying ? (
              <IconLoader size={12} className="animate-spin" />
            ) : (
              <IconWand size={12} />
            )}
            {applying ? "Aplicando…" : "Aplicar edición"}
          </button>
        </div>
      </div>
    </div>
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
    <label className="flex cursor-pointer items-center justify-between gap-3 rounded-2xl border border-veru-paper/[0.08] bg-black/20 px-3 py-2.5">
      <span className="min-w-0">
        <span className="block text-[10px] font-medium text-veru-paper/65">
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

function LayoutGlyph({ id }: { id: string }) {
  const ember = "bg-veru-ember/70";
  const soft = "bg-veru-paper/15";
  const base = "flex h-full w-9 flex-col gap-0.5 overflow-hidden rounded-[4px] bg-black/40 p-0.5";

  if (id === "auto") {
    return (
      <span className={base}>
        <span className={`h-2/3 rounded-[2px] ${ember}`} />
        <span className={`flex-1 rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "vertical") {
    return (
      <span className={base}>
        <span className={`h-full rounded-[2px] ${ember}`} />
      </span>
    );
  }
  if (id === "dividido") {
    return (
      <span className={base}>
        <span className={`h-1/2 rounded-[2px] ${ember}`} />
        <span className={`h-1/2 rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "trio") {
    return (
      <span className={base}>
        <span className={`h-1/3 rounded-[2px] ${ember}`} />
        <span className={`h-1/3 rounded-[2px] ${soft}`} />
        <span className={`h-1/3 rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "cuarteto") {
    return (
      <span className={`${base} flex-row flex-wrap`}>
        <span className={`h-[48%] w-[48%] rounded-[2px] ${ember}`} />
        <span className={`h-[48%] w-[48%] rounded-[2px] ${soft}`} />
        <span className={`h-[48%] w-[48%] rounded-[2px] ${soft}`} />
        <span className={`h-[48%] w-[48%] rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "cam_juego") {
    return (
      <span className={base}>
        <span className={`h-[42%] rounded-[2px] ${ember}`} />
        <span className={`h-[55%] rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "dos_cams_juego") {
    return (
      <span className={base}>
        <span className="flex h-[42%] gap-0.5">
          <span className={`w-1/2 rounded-[2px] ${ember}`} />
          <span className={`w-1/2 rounded-[2px] ${ember}`} />
        </span>
        <span className={`h-[55%] rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "tres_cams_juego") {
    return (
      <span className={base}>
        <span className="flex h-[42%] gap-0.5">
          <span className={`w-1/3 rounded-[2px] ${ember}`} />
          <span className={`w-1/3 rounded-[2px] ${ember}`} />
          <span className={`w-1/3 rounded-[2px] ${ember}`} />
        </span>
        <span className={`h-[55%] rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "trio_juego") {
    return (
      <span className={base}>
        <span className={`h-[55%] rounded-[2px] ${soft}`} />
        <span className="flex h-[42%] gap-0.5">
          <span className={`w-1/3 rounded-[2px] ${ember}`} />
          <span className={`w-1/3 rounded-[2px] ${ember}`} />
          <span className={`w-1/3 rounded-[2px] ${ember}`} />
        </span>
      </span>
    );
  }
  if (id === "spotlight") {
    return (
      <span className={base}>
        <span className={`h-[68%] rounded-[2px] ${ember}`} />
        <span className={`h-[29%] rounded-[2px] ${soft}`} />
      </span>
    );
  }
  if (id === "centrado") {
    return (
      <span className={`${base} justify-center`}>
        <span className={`h-[62%] rounded-[2px] ${ember}`} />
      </span>
    );
  }
  if (id === "horizontal") {
    return (
      <span className={`${base} justify-center`}>
        <span className={`h-[48%] rounded-[2px] ${ember}`} />
      </span>
    );
  }
  return (
    <span className={base}>
      <span className={`h-full rounded-[2px] ${soft}`} />
    </span>
  );
}
