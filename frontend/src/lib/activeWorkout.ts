import { useSyncExternalStore } from "react";
import type { LastPerformance, SetType } from "../api/gym";

/** The workout in progress, kept on the phone so nothing is lost without signal (docs/SPEC.md §8). */
export type LocalSet = {
  id: string;
  set_type: SetType;
  weight: string; // as typed (Czech decimal comma allowed)
  reps: string;
  completed: boolean;
  completed_at: string | null;
};
export type LocalExercise = {
  exercise_id: number;
  name: string;
  muscle_group: string;
  sets: LocalSet[];
  last: LastPerformance | null;
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
