import { useMemo, useState } from "react";
import type { Exercise } from "../../api/gym";

export const GROUP_LABELS: Record<string, string> = {
  chest: "Hrudník",
  back: "Záda",
  legs: "Nohy",
  shoulders: "Ramena",
  biceps: "Biceps",
  triceps: "Triceps",
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

/** Progression defaults per equipment as in backend `services/overload.py` (E33): [rep min, rep max, weight step kg]. */
const PROGRESSION_DEFAULTS: Record<string, [number, number, number]> = {
  barbell: [6, 10, 2.5],
  dumbbell: [6, 10, 2.5],
  bodyweight: [6, 10, 2.5],
  machine: [8, 12, 5],
  cable: [8, 12, 5],
  plate_loaded: [8, 12, 5],
};
export const progressionDefaults = (equipment: string | null) => {
  const [repMin, repMax, step] = (equipment && PROGRESSION_DEFAULTS[equipment]) || [8, 12, 2.5];
  return { rep_min: repMin, rep_max: repMax, weight_step: step, sets_max: 3 };
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
