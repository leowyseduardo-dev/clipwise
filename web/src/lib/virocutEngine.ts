import {
  ALL_FORMATS,
  AudioBufferSink,
  AudioBufferSource,
  BlobSource,
  BufferTarget,
  CanvasSource,
  Input,
  Mp4OutputFormat,
  Output,
  canEncodeAudio,
  canEncodeVideo,
} from "mediabunny";

export type Word = { start: number; end: number; text: string };
export type Cue = { start: number; end: number; text: string };

export type LayoutTemplate =
  | "vertical"
  | "dividido"
  | "cam_juego"
  | "dos_cams_juego"
  | "tres_cams_juego"
  | "trio"
  | "cuarteto"
  | "horizontal"
  | "spotlight"
  | "centrado";

export type CaptionStyle =
  | "default"
  | "minimal"
  | "caja"
  | "pildora"
  | "neon"
  | "amarillo";

export type OverlayStyle = "impact" | "bar" | "pill" | "clean";

export type RenderOptions = {
  start: number;
  end: number;
  template?: LayoutTemplate;
  focusX?: number;
  focusY?: number;
  cues?: Cue[];
  words?: Word[];
  captionStyle?: CaptionStyle;
  captionsEnabled?: boolean;
  hook?: string;
  hookStyle?: OverlayStyle;
  watermark?: string;
  width?: number;
  height?: number;
  fps?: number;
  bitrate?: number;
  onProgress?: (value: number) => void;
};

type Slot = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  kind: "main" | "cam" | "game";
};

type Template = {
  background: "blur" | "solid";
  slots: Slot[];
};

const TEMPLATES: Record<LayoutTemplate, Template> = {
  vertical: {
    background: "blur",
    slots: [{ id: "main", x: 0, y: 0, w: 1, h: 1, kind: "main" }],
  },
  dividido: {
    background: "blur",
    slots: [
      { id: "top", x: 0, y: 0, w: 1, h: 0.5, kind: "cam" },
      { id: "bottom", x: 0, y: 0.5, w: 1, h: 0.5, kind: "cam" },
    ],
  },
  cam_juego: {
    background: "blur",
    slots: [
      { id: "cam", x: 0, y: 0, w: 1, h: 0.43, kind: "cam" },
      { id: "game", x: 0, y: 0.43, w: 1, h: 0.57, kind: "game" },
    ],
  },
  dos_cams_juego: {
    background: "blur",
    slots: [
      { id: "cam_a", x: 0, y: 0, w: 0.5, h: 0.25, kind: "cam" },
      { id: "cam_b", x: 0.5, y: 0, w: 0.5, h: 0.25, kind: "cam" },
      { id: "game", x: 0, y: 0.25, w: 1, h: 0.75, kind: "game" },
    ],
  },
  tres_cams_juego: {
    background: "blur",
    slots: [
      { id: "cam", x: 0, y: 0, w: 1, h: 0.49, kind: "cam" },
      { id: "game", x: 0, y: 0.49, w: 1, h: 0.51, kind: "game" },
    ],
  },
  trio: {
    background: "blur",
    slots: [0, 1, 2].map((index) => ({
      id: `p${index + 1}`,
      x: 0,
      y: index / 3,
      w: 1,
      h: 1 / 3,
      kind: "cam" as const,
    })),
  },
  cuarteto: {
    background: "blur",
    slots: [
      { id: "p1", x: 0, y: 0, w: 1, h: 1 / 3, kind: "cam" },
      { id: "p2", x: 0, y: 1 / 3, w: 1, h: 1 / 3, kind: "cam" },
      { id: "p3", x: 0, y: 2 / 3, w: 0.5, h: 1 / 3, kind: "cam" },
      { id: "p4", x: 0.5, y: 2 / 3, w: 0.5, h: 1 / 3, kind: "cam" },
    ],
  },
  horizontal: {
    background: "blur",
    slots: [{ id: "main", x: 0, y: 0.34, w: 1, h: 0.32, kind: "main" }],
  },
  spotlight: {
    background: "blur",
    slots: [
      { id: "main", x: 0, y: 0, w: 1, h: 0.62, kind: "main" },
      { id: "detail", x: 0, y: 0.66, w: 1, h: 0.32, kind: "main" },
    ],
  },
  centrado: {
    background: "blur",
    slots: [{ id: "main", x: 0, y: 0.25, w: 1, h: 0.5, kind: "main" }],
  },
};

const CAPTION_STYLES: Record<
  CaptionStyle,
  {
    upper: boolean;
    weight: number;
    highlight: string;
    stroke: number;
    box?: boolean;
    pill?: string;
    family?: string;
  }
> = {
  default: {
    upper: true,
    weight: 800,
    highlight: "#FFD400",
    stroke: 0.12,
    family: 'Impact, "Arial Black", sans-serif',
  },
  minimal: {
    upper: false,
    weight: 600,
    highlight: "#FFFFFF",
    stroke: 0.07,
    family: '"Inter Tight", system-ui, sans-serif',
  },
  caja: {
    upper: false,
    weight: 700,
    highlight: "#FFD400",
    stroke: 0,
    box: true,
    family: '"Inter Tight", system-ui, sans-serif',
  },
  pildora: {
    upper: false,
    weight: 800,
    highlight: "#FFFFFF",
    stroke: 0.12,
    pill: "#8B5CF6",
    family: '"Inter Tight", system-ui, sans-serif',
  },
  neon: {
    upper: true,
    weight: 900,
    highlight: "#39FF88",
    stroke: 0.14,
    family: 'Impact, "Arial Black", sans-serif',
  },
  amarillo: {
    upper: true,
    weight: 900,
    highlight: "#FFFF00",
    stroke: 0.24,
    family: '"Arial Black", Impact, system-ui, sans-serif',
  },
};

const EMOJI_FONT =
  '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif';

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function once(target: EventTarget, event: string, timeoutMs = 15000): Promise<void> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      target.removeEventListener(event, onEvent);
      reject(new Error(`Timeout esperando ${event}.`));
    }, timeoutMs);
    const onEvent = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      target.removeEventListener(event, onEvent);
      resolve();
    };
    target.addEventListener(event, onEvent, { once: true });
  });
}

function seek(video: HTMLVideoElement, time: number): Promise<void> {
  const target = clamp(time, 0, Math.max(0, video.duration - 0.001));
  if (Math.abs(video.currentTime - target) < 0.001) return Promise.resolve();
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      video.removeEventListener("seeked", finish);
      resolve();
    };
    const timer = setTimeout(finish, 2500);
    video.addEventListener("seeked", finish, { once: true });
    video.currentTime = target;
  });
}

function splitGraphemes(text: string): string[] {
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter("es", { granularity: "grapheme" });
    return Array.from(segmenter.segment(text), (part) => part.segment);
  }
  return Array.from(text);
}

function measureRun(
  ctx: CanvasRenderingContext2D,
  text: string,
  textFont: string,
  emojiFont: string,
): number {
  let width = 0;
  for (const part of splitGraphemes(text)) {
    const emoji = /\p{Extended_Pictographic}/u.test(part);
    ctx.font = emoji ? emojiFont : textFont;
    width += ctx.measureText(part).width;
  }
  ctx.font = textFont;
  return width;
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  textFont: string,
  emojiFont: string,
): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split(/\n/)) {
    let current = "";
    for (const word of paragraph.split(/\s+/).filter(Boolean)) {
      const candidate = current ? `${current} ${word}` : word;
      if (current && measureRun(ctx, candidate, textFont, emojiFont) > maxWidth) {
        lines.push(current);
        current = word;
      } else {
        current = candidate;
      }
      const graphemes = splitGraphemes(current);
      while (
        measureRun(ctx, current, textFont, emojiFont) > maxWidth &&
        graphemes.length > 1
      ) {
        let cut = graphemes.length - 1;
        while (
          cut > 1 &&
          measureRun(ctx, graphemes.slice(0, cut).join(""), textFont, emojiFont) >
            maxWidth
        ) {
          cut -= 1;
        }
        lines.push(graphemes.slice(0, cut).join(""));
        graphemes.splice(0, cut);
        current = graphemes.join("");
      }
    }
    if (current) lines.push(current);
  }
  return lines.slice(0, 6);
}

function drawRun(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  textFont: string,
  emojiFont: string,
  fill: string,
  stroke?: { color: string; width: number },
): number {
  let cursor = x;
  for (const part of splitGraphemes(text)) {
    const emoji = /\p{Extended_Pictographic}/u.test(part);
    ctx.font = emoji ? emojiFont : textFont;
    const width = ctx.measureText(part).width;
    if (!emoji && stroke && stroke.width > 0) {
      ctx.lineWidth = stroke.width;
      ctx.strokeStyle = stroke.color;
      ctx.strokeText(part, cursor, y);
    }
    ctx.fillStyle = fill;
    ctx.fillText(part, cursor, y);
    cursor += width;
  }
  ctx.font = textFont;
  return cursor - x;
}

function cuesToWords(cues: Cue[]): Word[] {
  const words: Word[] = [];
  for (const cue of cues) {
    const parts = cue.text.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) continue;
    const weights = parts.map((part) => Math.max(1, splitGraphemes(part).length));
    const total = weights.reduce((sum, value) => sum + value, 0);
    let cursor = cue.start;
    parts.forEach((part, index) => {
      const duration = ((cue.end - cue.start) * weights[index]) / total;
      words.push({ start: cursor, end: cursor + duration, text: part });
      cursor += duration;
    });
  }
  return words.sort((a, b) => a.start - b.start);
}

type CaptionGroup = { start: number; end: number; words: Word[] };

function groupWords(words: Word[], maxWords = 3): CaptionGroup[] {
  const groups: CaptionGroup[] = [];
  let current: Word[] = [];
  const flush = () => {
    if (!current.length) return;
    groups.push({
      start: current[0].start,
      end: current[current.length - 1].end,
      words: current,
    });
    current = [];
  };
  for (const word of words) {
    const previous = current[current.length - 1];
    if (
      previous &&
      (current.length >= maxWords ||
        word.start - previous.end > 0.6 ||
        /[.!?¡¿…]$/.test(previous.text))
    ) {
      flush();
    }
    current.push(word);
  }
  flush();
  for (let index = 0; index < groups.length; index += 1) {
    const group = groups[index];
    const next = groups[index + 1];
    if (group.end - group.start < 0.9) {
      group.end = Math.min(next ? next.start : Number.POSITIVE_INFINITY, group.start + 0.9);
    }
    if (next && next.start - group.end < 0.4) group.end = next.start;
  }
  return groups;
}

function currentWordIndex(group: CaptionGroup, time: number): number {
  const adjusted = time + 0.15;
  let index = -1;
  group.words.forEach((word, wordIndex) => {
    if (adjusted >= word.start) index = wordIndex;
  });
  return index;
}

function drawCaptions(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  groups: CaptionGroup[],
  time: number,
  style: CaptionStyle,
): void {
  const group = groups.find((item) => time >= item.start && time < item.end);
  if (!group) return;
  const config = CAPTION_STYLES[style];
  const fontSize = Math.round((height * 3.8) / 100);
  const family = config.family ?? '"Inter Tight", system-ui, sans-serif';
  const textFont = `${config.weight} ${fontSize}px ${family}, ${EMOJI_FONT}`;
  const emojiFont = `${fontSize}px ${EMOJI_FONT}`;
  const baseline = height * 0.94 + fontSize * 0.35;
  const words = group.words.map((word) =>
    config.upper ? word.text.toUpperCase() : word.text,
  );
  const highlightIndex = currentWordIndex(group, time);

  ctx.save();
  ctx.font = textFont;
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.lineJoin = "round";

  const space = ctx.measureText(" ").width;
  const widths = words.map((word) => measureRun(ctx, word, textFont, emojiFont));
  let total = widths.reduce((sum, value) => sum + value, 0) + space * (words.length - 1);
  let scale = 1;
  let drawFont = textFont;
  let drawEmojiFont = emojiFont;
  if (total > width * 0.9) {
    scale = (width * 0.9) / total;
    drawFont = `${config.weight} ${Math.round(fontSize * scale)}px ${family}, ${EMOJI_FONT}`;
    drawEmojiFont = `${Math.round(fontSize * scale)}px ${EMOJI_FONT}`;
    ctx.font = drawFont;
    total = width * 0.9;
  }
  let cursor = (width - total) / 2;

  if (config.box) {
    const pad = fontSize * 0.3;
    ctx.fillStyle = "rgba(0,0,0,0.65)";
    ctx.fillRect(
      cursor - pad,
      baseline - fontSize * scale * 0.85 - pad / 2,
      total + pad * 2,
      fontSize * scale * 1.1 + pad,
    );
  }

  words.forEach((word, index) => {
    const wordWidth = (widths[index] ?? 0) * scale;
    if (config.pill && index === highlightIndex) {
      const size = fontSize * scale;
      const radius = size * 0.14;
      ctx.fillStyle = config.pill;
      ctx.beginPath();
      ctx.roundRect(
        cursor - radius,
        baseline - size * 0.82,
        wordWidth + radius * 2,
        size * 1.05,
        size * 0.22,
      );
      ctx.fill();
    }
    const stroke =
      config.stroke > 0
        ? {
            color: config.stroke >= 0.18 ? "#000000" : "rgba(0,0,0,0.9)",
            width: Math.max(3, fontSize * scale * config.stroke),
          }
        : undefined;
    drawRun(
      ctx,
      word,
      cursor,
      baseline,
      drawFont,
      drawEmojiFont,
      index === highlightIndex ? config.highlight : "#FFFFFF",
      stroke,
    );
    cursor += wordWidth + space * scale;
  });
  ctx.restore();
}

function drawHook(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  text: string,
  style: OverlayStyle,
): { top: number; bottom: number } {
  const fontSize = Math.round(
    (height * (style === "impact" ? 6.6 : style === "bar" ? 4.6 : 5.2)) / 100,
  );
  const family =
    style === "impact"
      ? 'Impact, "Arial Black", sans-serif'
      : '"Inter Tight", system-ui, sans-serif';
  const textFont = `${style === "impact" ? 900 : 800} ${fontSize}px ${family}, ${EMOJI_FONT}`;
  const emojiFont = `${fontSize}px ${EMOJI_FONT}`;
  const lines = wrapText(
    ctx,
    style === "impact" ? text.toUpperCase() : text,
    width * (style === "bar" ? 0.86 : 0.8),
    textFont,
    emojiFont,
  );
  const lineHeight = fontSize * 1.18;
  const padding = style === "pill" ? fontSize * 0.4 : style === "bar" ? fontSize * 0.32 : fontSize * 0.2;
  const top = height * 0.08;
  const maxWidth = Math.max(
    ...lines.map((line) => measureRun(ctx, line, textFont, emojiFont)),
  );

  ctx.save();
  ctx.font = textFont;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";

  if (style === "pill") {
    const boxWidth = maxWidth + padding * 2;
    const boxHeight = lines.length * lineHeight + padding * 2;
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.beginPath();
    ctx.roundRect((width - boxWidth) / 2, top - padding + fontSize * 0.08, boxWidth, boxHeight, fontSize * 0.45);
    ctx.fill();
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath();
    ctx.roundRect((width - boxWidth) / 2, top - padding, boxWidth, boxHeight, fontSize * 0.45);
    ctx.fill();
  } else if (style === "bar") {
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, top - padding, width, lines.length * lineHeight + padding * 2);
  }

  const isImpact = style === "impact";
  const clean = style === "clean" || isImpact;
  lines.forEach((line, index) => {
    const y = top + lineHeight * (index + 0.5);
    const x = (width - measureRun(ctx, line, textFont, emojiFont)) / 2;
    drawRun(
      ctx,
      line,
      x,
      y,
      textFont,
      emojiFont,
      clean ? "#FFFFFF" : "#000000",
      clean
        ? {
            color: "#000000",
            width: fontSize * (isImpact ? 0.22 : 0.14),
          }
        : undefined,
    );
  });
  ctx.restore();
  return {
    top: (top - padding) / height,
    bottom: (top + lines.length * lineHeight + padding) / height,
  };
}

function drawWatermark(
  ctx: CanvasRenderingContext2D,
  width: number,
  text: string,
): void {
  const fontSize = Math.round(width * 0.026);
  ctx.save();
  ctx.font = `700 ${fontSize}px "Inter Tight", system-ui, sans-serif`;
  ctx.textAlign = "right";
  ctx.textBaseline = "top";
  ctx.fillStyle = "rgba(255,255,255,0.75)";
  ctx.shadowColor = "rgba(0,0,0,0.45)";
  ctx.shadowBlur = fontSize * 0.4;
  ctx.fillText(text, width - width * 0.035, width * 0.035);
  ctx.restore();
}

function sourceRect(
  videoWidth: number,
  videoHeight: number,
  destWidth: number,
  destHeight: number,
  focusX: number,
  focusY: number,
): { sx: number; sy: number; sw: number; sh: number } {
  const destAspect = destWidth / destHeight;
  const videoAspect = videoWidth / videoHeight;
  if (videoAspect > destAspect) {
    const sw = videoHeight * destAspect;
    const sh = videoHeight;
    return {
      sx: clamp(focusX * videoWidth - sw / 2, 0, videoWidth - sw),
      sy: 0,
      sw,
      sh,
    };
  }
  const sw = videoWidth;
  const sh = videoWidth / destAspect;
  return {
    sx: 0,
    sy: clamp(focusY * videoHeight - sh / 2, 0, videoHeight - sh),
    sw,
    sh,
  };
}

function drawFrame(
  ctx: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  width: number,
  height: number,
  template: LayoutTemplate,
  focusX: number,
  focusY: number,
  groups: CaptionGroup[],
  captionStyle: CaptionStyle,
  captionsEnabled: boolean,
  hook: string,
  hookStyle: OverlayStyle,
  watermark: string,
  time: number,
): void {
  const config = TEMPLATES[template];
  const videoWidth = video.videoWidth;
  const videoHeight = video.videoHeight;

  ctx.clearRect(0, 0, width, height);
  if (config.background === "blur") {
    const cover = sourceRect(videoWidth, videoHeight, width, height, 0.5, 0.5);
    ctx.save();
    ctx.filter = "blur(28px)";
    ctx.drawImage(video, cover.sx, cover.sy, cover.sw, cover.sh, -40, -40, width + 80, height + 80);
    ctx.restore();
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fillRect(0, 0, width, height);
  } else {
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, width, height);
  }

  for (const slot of config.slots) {
    const dx = slot.x * width;
    const dy = slot.y * height;
    const dw = slot.w * width;
    const dh = slot.h * height;
    const isGame = slot.kind === "game";
    const crop = sourceRect(
      videoWidth,
      videoHeight,
      dw,
      dh,
      isGame ? 0.5 : focusX,
      isGame ? 0.5 : focusY,
    );
    ctx.drawImage(video, crop.sx, crop.sy, crop.sw, crop.sh, dx, dy, dw, dh);
  }

  if (hook.trim()) drawHook(ctx, width, height, hook.trim(), hookStyle);
  if (captionsEnabled && groups.length) {
    drawCaptions(ctx, width, height, groups, time, captionStyle);
  }
  if (watermark.trim()) drawWatermark(ctx, width, watermark.trim());
}

async function extractAudioBuffer(
  input: Input,
  start: number,
  end: number,
): Promise<AudioBuffer | null> {
  const track = await input.getPrimaryAudioTrack();
  if (!track || !(await track.canDecode())) return null;
  const sampleRate = track.sampleRate;
  const length = Math.max(1, Math.round((end - start) * sampleRate));
  const buffer = new AudioBuffer({
    length,
    numberOfChannels: 2,
    sampleRate,
  });
  const left = buffer.getChannelData(0);
  const right = buffer.getChannelData(1);
  const sink = new AudioBufferSink(track);
  let written = 0;
  for await (const { buffer: source, timestamp } of sink.buffers(start, end)) {
    let offset = Math.round((timestamp - start) * sampleRate);
    let sourceOffset = 0;
    if (offset < 0) {
      sourceOffset = -offset;
      offset = 0;
    }
    const count = Math.min(source.length - sourceOffset, length - offset);
    if (count <= 0) continue;
    left.set(source.getChannelData(0).subarray(sourceOffset, sourceOffset + count), offset);
    right.set(
      (source.numberOfChannels > 1 ? source.getChannelData(1) : source.getChannelData(0)).subarray(
        sourceOffset,
        sourceOffset + count,
      ),
      offset,
    );
    written += count;
  }
  if (written < length * 0.8) return null;
  return buffer;
}

async function chooseAudioCodec(): Promise<"aac" | "opus" | null> {
  try {
    if (await canEncodeAudio("aac")) return "aac";
  } catch {
    // AAC is not available on every browser.
  }
  try {
    if (await canEncodeAudio("opus")) return "opus";
  } catch {
    // No audio encoder available.
  }
  return null;
}

export async function renderClip(file: File, options: RenderOptions): Promise<Blob> {
  const width = options.width ?? 1080;
  const height = options.height ?? 1920;
  const fps = options.fps ?? 30;
  const bitrate = options.bitrate ?? 4_000_000;
  const template = options.template ?? "vertical";
  const captionStyle = options.captionStyle ?? "default";
  const hookStyle = options.hookStyle ?? "impact";
  const focusX = clamp(options.focusX ?? 0.5, 0, 1);
  const focusY = clamp(options.focusY ?? 0.42, 0, 1);

  if (!(await canEncodeVideo("avc", { width, height }))) {
    throw new Error("Este navegador no puede codificar H.264 a 1080x1920.");
  }

  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
  const sourceDuration = await input.computeDuration();
  const start = clamp(options.start, 0, Math.max(0, sourceDuration - 0.05));
  const end = clamp(options.end, start + 0.05, sourceDuration);
  const clipDuration = end - start;

  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.crossOrigin = "anonymous";
  const objectUrl = URL.createObjectURL(file);
  video.src = objectUrl;
  await once(video, "loadeddata", 20000);
  video.pause();

  const words = options.words?.length ? options.words : cuesToWords(options.cues ?? []);
  const groups = groupWords(words);
  const captionsEnabled = options.captionsEnabled ?? groups.length > 0;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D no disponible.");

  const target = new BufferTarget();
  const output = new Output({
    format: new Mp4OutputFormat({ fastStart: "in-memory" }),
    target,
  });
  const videoSource = new CanvasSource(canvas, {
    codec: "avc",
    bitrate,
    keyFrameInterval: 2,
    latencyMode: "quality",
  });
  output.addVideoTrack(videoSource, { frameRate: fps });

  const audioCodec = await chooseAudioCodec();
  let audioBuffer: AudioBuffer | null = null;
  let audioSource: AudioBufferSource | null = null;
  if (audioCodec) {
    try {
      audioBuffer = await extractAudioBuffer(input, start, end);
    } catch {
      audioBuffer = null;
    }
    if (audioBuffer) {
      audioSource = new AudioBufferSource({ codec: audioCodec, bitrate: 160_000 });
      output.addAudioTrack(audioSource);
    }
  }

  await output.start();
  const totalFrames = Math.max(1, Math.round(clipDuration * fps));
  try {
    for (let frame = 0; frame < totalFrames; frame += 1) {
      const time = start + frame / fps;
      await seek(video, time);
      drawFrame(
        ctx,
        video,
        width,
        height,
        template,
        focusX,
        focusY,
        groups,
        captionStyle,
        captionsEnabled,
        options.hook ?? "",
        hookStyle,
        options.watermark ?? "",
        frame / fps,
      );
      await videoSource.add(frame / fps, 1 / fps);
      options.onProgress?.(0.05 + (frame / totalFrames) * 0.9);
    }
    videoSource.close();
    if (audioSource && audioBuffer) {
      await audioSource.add(audioBuffer);
      audioSource.close();
    }
    await output.finalize();
    options.onProgress?.(1);
  } catch (error) {
    try {
      await output.cancel();
    } catch {
      // The output may already be closed.
    }
    throw error;
  } finally {
    video.pause();
    video.removeAttribute("src");
    video.load();
    URL.revokeObjectURL(objectUrl);
  }

  const buffer = target.buffer;
  if (!buffer) throw new Error("El render no produjo ningún archivo.");
  return new Blob([buffer], { type: "video/mp4" });
}

export async function probeVideo(file: File): Promise<{ duration: number; width: number; height: number }> {
  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
  const duration = await input.computeDuration();
  const track = await input.getPrimaryVideoTrack();
  const width = track ? await track.getDisplayWidth() : 0;
  const height = track ? await track.getDisplayHeight() : 0;
  return { duration, width, height };
}
