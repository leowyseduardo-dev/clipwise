import type { ClipCategory } from "./types";

export interface CategoryInfo {
  id: ClipCategory;
  label: string;
  short: string;
  className: string;
}

export const CATEGORY_ORDER: ClipCategory[] = [
  "angry",
  "funny",
  "crazy_reactions",
  "epic",
  "unexpected",
  "scary",
  "fails",
  "wins",
  "drama",
  "shocking",
];

export const CATEGORY_INFO: Record<ClipCategory, CategoryInfo> = {
  angry: {
    id: "angry",
    label: "ANGRY MOMENTS",
    short: "Enfado",
    className: "border-rose-400/30 bg-rose-500/10 text-rose-200",
  },
  funny: {
    id: "funny",
    label: "FUNNY MOMENTS",
    short: "Humor",
    className: "border-amber-300/30 bg-amber-400/10 text-amber-200",
  },
  crazy_reactions: {
    id: "crazy_reactions",
    label: "CRAZY REACTIONS",
    short: "Reacción",
    className: "border-veru-ember/30 bg-veru-ember/10 text-veru-blush",
  },
  epic: {
    id: "epic",
    label: "EPIC MOMENTS",
    short: "Épico",
    className: "border-veru-blush/30 bg-veru-blush/10 text-veru-blush",
  },
  unexpected: {
    id: "unexpected",
    label: "UNEXPECTED MOMENTS",
    short: "Inesperado",
    className: "border-veru-ember/30 bg-veru-ember/10 text-fuchsia-200",
  },
  scary: {
    id: "scary",
    label: "SCARY MOMENTS",
    short: "Miedo",
    className: "border-orange-400/30 bg-orange-500/10 text-orange-200",
  },
  fails: {
    id: "fails",
    label: "FAILS",
    short: "Fail",
    className: "border-amber-500/30 bg-amber-600/10 text-amber-200",
  },
  wins: {
    id: "wins",
    label: "WINS",
    short: "Victoria",
    className: "border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
  },
  drama: {
    id: "drama",
    label: "DRAMA",
    short: "Drama",
    className: "border-pink-400/30 bg-pink-500/10 text-pink-200",
  },
  shocking: {
    id: "shocking",
    label: "SHOCKING MOMENTS",
    short: "Shock",
    className: "border-red-400/30 bg-red-500/10 text-red-200",
  },
};

export function categoryInfo(value: string | null | undefined): CategoryInfo | null {
  if (!value) return null;
  return CATEGORY_INFO[value as ClipCategory] ?? null;
}
