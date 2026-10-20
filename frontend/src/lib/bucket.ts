import { Brain, Globe, HeartPulse, type LucideIcon, Medal, Mountain, Sparkles, UtensilsCrossed, Zap } from "lucide-react";
import type { BucketItem, Category, Season } from "../api/bucket";

export const CATEGORIES: { key: Category; label: string; icon: LucideIcon }[] = [
  { key: "travel", label: "Cestování", icon: Globe },
  { key: "expedition", label: "Výpravy", icon: Mountain },
  { key: "experience", label: "Zážitky", icon: Sparkles },
  { key: "adrenaline", label: "Adrenalin", icon: Zap },
  { key: "sport", label: "Sport & pohyb", icon: Medal },
  { key: "skill", label: "Dovednosti", icon: Brain },
  { key: "food", label: "Jídlo & pití", icon: UtensilsCrossed },
  { key: "wellbeing", label: "Tělo & mysl", icon: HeartPulse },
];
export const CATEGORY = Object.fromEntries(CATEGORIES.map((c) => [c.key, c])) as Record<Category, (typeof CATEGORIES)[number]>;

/** Loot-style rarity (E36). Literal class names, so Tailwind (and the theme remaps) pick them up. */
export const RARITY = {
  1: { name: "Běžná", text: "text-zinc-300", bar: "bg-zinc-500", ring: "border-zinc-500", soft: "bg-zinc-500/15" },
  2: { name: "Vzácná", text: "text-sky-300", bar: "bg-sky-500", ring: "border-sky-500", soft: "bg-sky-500/15" },
  3: { name: "Epická", text: "text-violet-300", bar: "bg-violet-500", ring: "border-violet-500", soft: "bg-violet-500/15" },
  4: { name: "Legendární", text: "text-amber-300", bar: "bg-amber-400", ring: "border-amber-400", soft: "bg-amber-400/15" },
} as const;

export const SEASONS: readonly (readonly [Season, string])[] = [
  ["summer", "Léto"],
  ["winter", "Zima"],
];
export const SEASON_LABEL: Record<Season, string> = { summer: "léto", winter: "zima" };
export const costLabel = (cost: number | null) => (cost ? "€".repeat(cost) : null);

const regionNames = (() => {
  try {
    return new Intl.DisplayNames(["cs"], { type: "region" });
  } catch {
    return null;
  }
})();
/** Czech country name; codes Intl doesn't know (it throws on some) fall back to the code itself. */
export function countryName(code: string): string {
  try {
    return regionNames?.of(code) ?? code;
  } catch {
    return code;
  }
}

/** "za 5 dní" / "dnes" / "před 3 dny" for a planned date. */
export function countdown(day: string, today: string): string {
  const days = Math.round((Date.parse(`${day}T12:00:00`) - Date.parse(`${today}T12:00:00`)) / 86_400_000);
  if (days === 0) return "dnes";
  if (days === 1) return "zítra";
  if (days > 0) return `za ${days} ${days < 5 ? "dny" : "dní"}`;
  return `před ${-days} ${-days === 1 ? "dnem" : "dny"}`;
}

export const stepsDone = (item: BucketItem) => item.steps.filter((s) => s.done_on).length;

/** Open items: planned first (soonest), then starred goals, then rarer first. Done items: newest first. */
export function sortItems(items: BucketItem[], year: number): BucketItem[] {
  const open = items.filter((i) => !i.done);
  const done = items.filter((i) => i.done);
  open.sort(
    (a, b) =>
      (a.planned_for ?? "9999").localeCompare(b.planned_for ?? "9999") ||
      Number(b.year_goal === year) - Number(a.year_goal === year) ||
      b.rarity - a.rarity ||
      a.title.localeCompare(b.title, "cs"),
  );
  done.sort((a, b) => (b.completed_on ?? "").localeCompare(a.completed_on ?? "") || a.title.localeCompare(b.title, "cs"));
  return [...open, ...done];
}

/** "20. 10. 2026" */
export const fullDate = (iso: string) => `${Number(iso.slice(8, 10))}. ${Number(iso.slice(5, 7))}. ${iso.slice(0, 4)}`;
