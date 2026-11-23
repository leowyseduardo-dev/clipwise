export interface StageInfo {
  key: string;
  label: string;
  detail: string;
  matches: string[];
}

export const STAGES: StageInfo[] = [
  {
    key: "prepare",
    label: "Preparación",
    detail: "Descarga, validación y normalización del video",
    matches: ["queued", "preparing", "downloading", "extracting_audio"],
  },
  {
    key: "transcribe",
    label: "Transcripción",
    detail: "Voz a texto con timestamps por palabra",
    matches: ["transcribing"],
  },
  {
    key: "analyze",
    label: "Análisis IA",
    detail: "Momentos virales, ganchos y puntuación",
    matches: [
      "analyzing_audio",
      "detecting_scenes",
      "analyzing_visual",
      "analyzing_moments",
      "creating_clips",
    ],
  },
  {
    key: "render",
    label: "Edición",
    detail: "Tramo del clip, reencuadre, subtítulos, silencios y render",
    matches: ["downloading_clip", "rendering"],
  },
];

export function stageStatus(
  stage: string,
  status: string,
): { activeIndex: number; completed: boolean } {
  if (status === "ready") return { activeIndex: STAGES.length, completed: true };
  if (status === "failed" || status === "cancelled") {
    const failedIndex = STAGES.findIndex((item) => item.matches.includes(stage));
    return { activeIndex: failedIndex >= 0 ? failedIndex : 0, completed: false };
  }
  const index = STAGES.findIndex((item) => item.matches.includes(stage));
  return { activeIndex: index >= 0 ? index : 0, completed: false };
}

export function stageLabel(stage: string): string {
  const found = STAGES.find((item) => item.matches.includes(stage));
  return found ? found.label : "Procesando";
}
