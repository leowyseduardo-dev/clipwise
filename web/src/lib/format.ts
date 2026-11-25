export function formatTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-ES", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return String(Math.round(score));
}

export function scoreTone(score: number | null | undefined): {
  label: string;
  text: string;
  stroke: string;
  bg: string;
  border: string;
} {
  if (score === null || score === undefined) {
    return {
      label: "Sin puntuar",
      text: "text-veru-paper/50",
      stroke: "#71717a",
      bg: "bg-veru-paper/35/10",
      border: "border-veru-paper/35/30",
    };
  }
  if (score >= 85) {
    return {
      label: "Excelente",
      text: "text-emerald-300",
      stroke: "#34d399",
      bg: "bg-emerald-500/10",
      border: "border-emerald-400/30",
    };
  }
  if (score >= 70) {
    return {
      label: "Bueno",
      text: "text-veru-blush",
      stroke: "#22d3ee",
      bg: "bg-cyan-500/10",
      border: "border-veru-blush/30",
    };
  }
  if (score >= 55) {
    return {
      label: "Correcto",
      text: "text-amber-300",
      stroke: "#fbbf24",
      bg: "bg-amber-500/10",
      border: "border-amber-400/30",
    };
  }
  return {
    label: "Mejorable",
    text: "text-rose-300",
    stroke: "#fb7185",
    bg: "bg-rose-500/10",
    border: "border-rose-400/30",
  };
}

const LANGUAGE_NAMES: Record<string, string> = {
  es: "Español",
  en: "Inglés",
  pt: "Portugués",
  fr: "Francés",
  it: "Italiano",
  de: "Alemán",
  nl: "Neerlandés",
  ca: "Catalán",
  gl: "Gallego",
  eu: "Euskera",
  ru: "Ruso",
  ja: "Japonés",
  ko: "Coreano",
  zh: "Chino",
  ar: "Árabe",
  hi: "Hindi",
  tr: "Turco",
  pl: "Polaco",
  sv: "Sueco",
  da: "Danés",
  no: "Noruego",
  fi: "Finés",
};

export function formatLanguage(code: string | null | undefined): string {
  if (!code) return "Idioma auto";
  return LANGUAGE_NAMES[code.toLowerCase()] ?? code.toUpperCase();
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  if (mb < 10) return `${mb.toFixed(1)} MB`;
  return `${mb.toFixed(0)} MB`;
}

export function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function sameText(
  left: string | null | undefined,
  right: string | null | undefined,
): boolean {
  const normalize = (value: string | null | undefined) =>
    (value ?? "")
      .toLocaleLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim();
  return normalize(left) === normalize(right);
}

export function downloadName(
  index: number,
  title: string | null | undefined,
  extension: string,
): string {
  const number = String(Math.max(0, index) + 1).padStart(2, "0");
  const slug = (title ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return `clip-${number}${slug ? `-${slug}` : ""}.${extension}`;
}
