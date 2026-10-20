/** Dovednosti (E37). Mirrors backend/app/services/abilities.py: one dovednost per key, levels by entry count. */

/** The name without case, diacritics and extra spaces: "Lezení" and " lezeni " are one dovednost. */
export const abilityKey = (name: string) =>
  name.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("cs").split(/\s+/).filter(Boolean).join(" ");

/** Dovednosti matching what was typed: names starting with it first, then names containing it. */
export function matchAbilities<T extends { name: string }>(abilities: T[], query: string, limit = 6): T[] {
  const q = abilityKey(query);
  if (!q) return abilities.slice(0, limit);
  const keyed = abilities.map((a) => [abilityKey(a.name), a] as const);
  const starts = keyed.filter(([key]) => key.startsWith(q) || key.split(" ").some((word) => word.startsWith(q)));
  const contains = keyed.filter(([key]) => key.includes(q) && !starts.some(([s]) => s === key));
  return [...starts, ...contains].slice(0, limit).map(([, a]) => a);
}

export type Ability = {
  id: number;
  name: string;
  icon: string | null;
  count: number;
  first_on: string | null;
  last_on: string | null;
  level: number;
  level_name: string;
  next_level_at: number | null;
  last_note: string | null;
};
export type AbilityEntry = { date: string; habit_id: number; habit_title: string; note: string | null; rating: number | null };
export type AbilityDetail = Ability & { entries: AbilityEntry[] };
