import {
  ALL_FORMATS,
  BlobSource,
  BufferTarget,
  Conversion,
  Input,
  Mp4OutputFormat,
  Output,
  Quality,
} from "mediabunny";

export type Cue = { start: number; end: number; text: string };

export type RenderOptions = {
  start: number;
  end: number;
  cues: Cue[];
  width?: number;
  height?: number;
  onProgress?: (value: number) => void;
};

function drawCaption(
  ctx: OffscreenCanvasRenderingContext2D,
  text: string,
  width: number,
  height: number,
) {
  const fontSize = Math.round(height * 0.052);
  ctx.font = `800 ${fontSize}px Inter, Arial, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.lineJoin = "round";

  const maxWidth = width * 0.86;
  const words = text.toUpperCase().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (ctx.measureText(candidate).width > maxWidth && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);

  const lineHeight = fontSize * 1.12;
  const bottom = height * 0.88;
  const startY = bottom - (lines.length - 1) * lineHeight;
  lines.forEach((line, index) => {
    const y = startY + index * lineHeight;
    ctx.lineWidth = Math.max(6, fontSize * 0.16);
    ctx.strokeStyle = "rgba(0,0,0,0.92)";
    ctx.strokeText(line, width / 2, y);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(line, width / 2, y);
  });
}

export async function probeDuration(file: File): Promise<number> {
  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
  return input.computeDuration();
}

export async function renderClip(file: File, options: RenderOptions): Promise<Blob> {
  const width = options.width ?? 1080;
  const height = options.height ?? 1920;

  const input = new Input({ formats: ALL_FORMATS, source: new BlobSource(file) });
  const output = new Output({
    format: new Mp4OutputFormat(),
    target: new BufferTarget(),
  });

  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D no disponible en este navegador.");

  const conversion = await Conversion.init({
    input,
    output,
    trim: { start: options.start, end: options.end },
    video: {
      width,
      height,
      fit: "cover",
      processedWidth: width,
      processedHeight: height,
      quality: new Quality("high"),
      process: (sample) => {
        const absolute = sample.timestamp;
        const relative = absolute >= options.start ? absolute - options.start : absolute;
        ctx.clearRect(0, 0, width, height);
        sample.drawWithFit(ctx, { fit: "cover" });
        const cue = options.cues.find((c) => relative >= c.start && relative < c.end);
        if (cue) drawCaption(ctx, cue.text, width, height);
        return canvas;
      },
    },
    audio: { quality: new Quality("high") },
  });

  if (!conversion.isValid) {
    throw new Error("Este archivo no se puede convertir en el navegador.");
  }
  conversion.onProgress = (value) => options.onProgress?.(value);
  await conversion.execute();

  const buffer = output.target.buffer;
  if (!buffer) throw new Error("El render no produjo ningún archivo.");
  return new Blob([buffer], { type: "video/mp4" });
}
