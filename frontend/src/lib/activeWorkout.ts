import { useSyncExternalStore } from "react";
import type { LastPerformance, SetRole, SetType } from "../api/gym";

/** The workout in progress, kept on the phone so nothing is lost without signal (docs/SPEC.md §8). */
export type LocalSet = {
  id: string;
  set_type: SetType;
  weight: string; // as typed (Czech decimal comma allowed)
  reps: string;
  completed: boolean;
  completed_at: string | null;
  progress?: boolean; // the target changed it or pushes it (E33, E35)
  // The plan (E35): the target the set was pre-filled with and its role; kept when the values are edited
  planned_weight?: number | null;
  planned_reps?: number | null;
  role?: SetRole | null;
  rir?: number | null; // confirmed by the user (0-3, 3 = 3+); null = not confirmed
};
export type LocalExercise = {
  exercise_id: number;
  name: string;
  muscle_group: string;
  sets: LocalSet[];
  last: LastPerformance | null;
  unusual?: boolean; // pain, interruption, fatigue: kept out of the progression (E35)
};
export type ActiveWorkout = { id: string; name: string; started_at: string; exercises: LocalExercise[] };

const KEY = "fitness-hub-active-workout";
const listeners = new Set<() => void>();
let cache: { raw: string | null; value: ActiveWorkout | null } = { raw: null, value: null };

function read(): ActiveWorkout | null {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(KEY);
  } catch {
    return cache.value;
  }
  if (raw !== cache.raw) cache = { raw, value: raw ? (JSON.parse(raw) as ActiveWorkout) : null };
  return cache.value;
}

export function saveActiveWorkout(workout: ActiveWorkout | null) {
  try {
    if (workout) localStorage.setItem(KEY, JSON.stringify(workout));
    else localStorage.removeItem(KEY);
  } catch {
    cache = { raw: null, value: workout }; // storage blocked: keep it in memory at least
  }
  listeners.forEach((listener) => listener());
}

/** Change the stored workout as it is now, not a render's copy that an await may have outdated. */
export function patchActiveWorkout(change: (workout: ActiveWorkout) => ActiveWorkout) {
  const workout = read();
  if (workout) saveActiveWorkout(change(workout));
}

/** An edited exercise keeps its new name and muscle group in the workout in progress too. */
export function updateActiveExercise(exercise: { id: number; name: string; muscle_group: string }) {
  const workout = read();
  if (!workout?.exercises.some((e) => e.exercise_id === exercise.id)) return;
  saveActiveWorkout({
    ...workout,
    exercises: workout.exercises.map((e) => (e.exercise_id === exercise.id ? { ...e, name: exercise.name, muscle_group: exercise.muscle_group } : e)),
  });
}

export function useActiveWorkout(): ActiveWorkout | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      const onStorage = (e: StorageEvent) => e.key === KEY && listener();
      window.addEventListener("storage", onStorage);
      return () => {
        listeners.delete(listener);
        window.removeEventListener("storage", onStorage);
      };
    },
    read,
    () => null,
  );
}

/** Add sets the server has but the phone doesn't (e.g. saved by the AI coach) to the local workout. */
export function mergeServerSets(
  server: {
    id: string;
    sets: { id: string; exercise_id: number; set_type: SetType; weight_kg: number | null; reps: number | null; completed: boolean; completed_at: string | null; rpe?: number | null }[];
  },
  names: Map<number, { name: string; muscle_group: string }>,
) {
  const local = read();
  if (!local || local.id !== server.id) return;
  const known = new Set(local.exercises.flatMap((e) => e.sets.map((s) => s.id)));
  const exercises = local.exercises.map((e) => ({ ...e, sets: [...e.sets] }));
  for (const s of server.sets) {
    if (known.has(s.id) || !s.completed) continue;
    const set: LocalSet = {
      id: s.id,
      set_type: s.set_type,
      weight: s.weight_kg !== null ? String(s.weight_kg).replace(".", ",") : "",
      reps: s.reps !== null ? String(s.reps) : "",
      completed: true,
      completed_at: s.completed_at,
      // An RPE the coach saved survives the logger re-sending the set (it stores RIR as 10 - RIR)
      rir: s.rpe == null ? null : Math.min(3, Math.max(0, Math.round(10 - s.rpe))),
    };
    const target = exercises.find((e) => e.exercise_id === s.exercise_id);
    if (target) target.sets.push(set);
    else {
      const info = names.get(s.exercise_id);
      exercises.push({ exercise_id: s.exercise_id, name: info?.name ?? `#${s.exercise_id}`, muscle_group: info?.muscle_group ?? "", sets: [set], last: null });
    }
  }
  saveActiveWorkout({ ...local, exercises });
}
