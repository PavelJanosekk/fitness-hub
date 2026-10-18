import { useMemo, useState } from "react";
import type { Exercise } from "../../api/gym";

export const GROUP_LABELS: Record<string, string> = {
  chest: "Hrudník",
  back: "Záda",
  legs: "Nohy",
  shoulders: "Ramena",
  arms: "Paže",
  core: "Core",
  full_body: "Celé tělo",
  cardio: "Kardio",
};

export const EQUIPMENT_LABELS: Record<string, string> = {
  barbell: "Velká činka",
  dumbbell: "Jednoručky",
  machine: "Stroj",
  plate_loaded: "Stroj na kotouče",
  cable: "Kladka",
  bodyweight: "Vlastní váha",
  band: "Guma",
};

const normalize = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** Search (diacritics-insensitive) and muscle-group filter shared by the picker and the exercise list. */
export function useExerciseFilter(exercises: Exercise[] | undefined) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const groups = Object.keys(GROUP_LABELS).filter((g) => exercises?.some((e) => e.muscle_group === g));
  const filtered = useMemo(() => {
    const needle = normalize(query.trim());
    return (exercises ?? []).filter((e) => (group === null || e.muscle_group === group) && normalize(e.name).includes(needle));
  }, [exercises, query, group]);
  return { query, setQuery, group, setGroup, groups, filtered };
}
