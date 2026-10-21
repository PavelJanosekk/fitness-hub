import { Bike, Brain, Car, ChefHat, Compass, GraduationCap, Hammer, House, type LucideIcon, Users, Wrench } from "lucide-react";
import type { QuestCategory, QuestDuration, SideQuest } from "../api/sideQuests";

export const QUEST_CATEGORIES: { key: QuestCategory; label: string; icon: LucideIcon }[] = [
  { key: "learn", label: "Učení", icon: GraduationCap },
  { key: "skill", label: "Dovednosti", icon: Wrench },
  { key: "make", label: "Tvoření", icon: Hammer },
  { key: "food", label: "Jídlo", icon: ChefHat },
  { key: "move", label: "Pohyb", icon: Bike },
  { key: "explore", label: "Objevování", icon: Compass },
  { key: "people", label: "Lidé", icon: Users },
  { key: "self", label: "Sebepoznání", icon: Brain },
  { key: "home", label: "Domov", icon: House },
  { key: "trip", label: "Výlet", icon: Car },
];
export const QUEST_CATEGORY = Object.fromEntries(QUEST_CATEGORIES.map((c) => [c.key, c])) as Record<QuestCategory, (typeof QUEST_CATEGORIES)[number]>;

/** Durations (E45), longer = rarer colour. Literal class names, so Tailwind (and the theme remaps) pick them up. */
export const DURATION = {
  moment: { name: "Chvilka", text: "text-zinc-300", bar: "bg-zinc-500", ring: "border-zinc-500" },
  day: { name: "1 den", text: "text-sky-300", bar: "bg-sky-500", ring: "border-sky-500" },
  weekend: { name: "Víkend", text: "text-emerald-300", bar: "bg-emerald-500", ring: "border-emerald-500" },
  week: { name: "Týden", text: "text-violet-300", bar: "bg-violet-500", ring: "border-violet-500" },
  month: { name: "Měsíc+", text: "text-amber-300", bar: "bg-amber-400", ring: "border-amber-400" },
} as const satisfies Record<QuestDuration, unknown>;
export const DURATION_KEYS = Object.keys(DURATION) as QuestDuration[];

/** "25 min · 20 km", "1 h 40 min · 90 km" */
export function travelLabel(quest: Pick<SideQuest, "travel_minutes" | "distance_km">): string | null {
  const parts = [];
  const m = quest.travel_minutes;
  if (m != null) parts.push(m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`);
  if (quest.distance_km != null) parts.push(`${quest.distance_km} km`);
  return parts.length ? parts.join(" · ") : null;
}

/** Open: started first, then trips by drive time, then shorter first; done: newest first. */
export function sortQuests(items: SideQuest[]): SideQuest[] {
  const open = items.filter((i) => !i.done);
  const done = items.filter((i) => i.done);
  open.sort(
    (a, b) =>
      Number(b.active) - Number(a.active) ||
      (a.travel_minutes ?? -1) - (b.travel_minutes ?? -1) ||
      DURATION_KEYS.indexOf(a.duration) - DURATION_KEYS.indexOf(b.duration) ||
      a.title.localeCompare(b.title, "cs"),
  );
  done.sort((a, b) => (b.done_on ?? "").localeCompare(a.done_on ?? "") || a.title.localeCompare(b.title, "cs"));
  return [...open, ...done];
}

/** A map search for a trip (the seed has no links). */
export const mapLink = (title: string) => `https://mapy.cz/zakladni?q=${encodeURIComponent(title)}`;
