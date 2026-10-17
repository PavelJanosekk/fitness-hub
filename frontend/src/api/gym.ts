import { type QueryClient, useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type Exercise = { id: number; name: string; muscle_group: string; equipment: string | null };
export type SetType = "normal" | "warmup" | "drop" | "failure";
export type LastPerformance = {
  exercise_id: number;
  workout_id: string | null;
  workout_started_at: string | null;
  sets: { set_order: number; set_type: SetType; weight_kg: number | null; reps: number | null }[];
};
export type Template = {
  name: string;
  last_workout_id: string;
  last_started_at: string;
  exercises: { exercise_id: number; name: string; set_count: number }[];
};
export type WorkoutSummary = {
  id: string;
  name: string;
  started_at: string;
  ended_at: string | null;
  ended_by: string | null;
  source: string;
  duration_min: number | null;
  set_count: number;
  total_volume_kg: number;
};
export type ServerSet = {
  id: string;
  exercise_id: number;
  exercise_order: number;
  set_order: number;
  set_type: SetType;
  weight_kg: number | null;
  reps: number | null;
  completed: boolean;
  completed_at: string | null;
};
export type ServerWorkout = Omit<WorkoutSummary, "duration_min" | "set_count" | "total_volume_kg"> & {
  notes: string | null;
  sets: ServerSet[];
};

export type SetBody = Omit<ServerSet, "id">;

export const gymKeys = {
  exercises: ["exercises"] as const,
  templates: ["workouts", "templates"] as const,
  history: ["workouts", "history"] as const,
  workout: (id: string) => ["workouts", id] as const,
  last: (exerciseId: number) => ["exercises", exerciseId, "last"] as const,
};

export const useExercises = () =>
  useQuery({ queryKey: gymKeys.exercises, queryFn: () => api<Exercise[]>("/api/exercises"), staleTime: 10 * 60_000 });
export const useTemplates = () =>
  useQuery({ queryKey: gymKeys.templates, queryFn: () => api<Template[]>("/api/workouts/templates") });
export const useHistory = () =>
  useQuery({ queryKey: gymKeys.history, queryFn: () => api<WorkoutSummary[]>("/api/workouts?limit=30") });
export const useActiveServerWorkout = () =>
  useQuery({ queryKey: ["workouts", "active"], queryFn: () => api<ServerWorkout | null>("/api/workouts/active") });
export const useWorkout = (id: string | null) =>
  useQuery({ queryKey: gymKeys.workout(id ?? ""), queryFn: () => api<ServerWorkout>(`/api/workouts/${id}`), enabled: !!id });

export const fetchLastPerformance = (queryClient: QueryClient, exerciseId: number) =>
  queryClient.fetchQuery({
    queryKey: gymKeys.last(exerciseId),
    queryFn: () => api<LastPerformance>(`/api/exercises/${exerciseId}/last-performance`),
    staleTime: 5 * 60_000,
  });

/**
 * Workout writes go through persisted, paused-when-offline mutations. Their functions are registered here
 * (not inline) so mutations restored from localStorage after a reload can still run; one shared scope keeps
 * them in order (the workout is created before its sets).
 */
export const SYNC_SCOPE = { id: "gym-sync" };

export function registerGymMutations(queryClient: QueryClient) {
  queryClient.setMutationDefaults(["gym", "workout"], {
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api(`/api/workouts/${id}`, { method: "PUT", body }),
    scope: SYNC_SCOPE,
    retry: 5,
    // Here, not at the call site: the workout screen is gone by the time a finish request settles
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
  queryClient.setMutationDefaults(["gym", "set"], {
    mutationFn: ({ workoutId, setId, body }: { workoutId: string; setId: string; body: SetBody }) =>
      api(`/api/workouts/${workoutId}/sets/${setId}`, { method: "PUT", body }),
    scope: SYNC_SCOPE,
    retry: 5,
  });
  queryClient.setMutationDefaults(["gym", "delete-set"], {
    mutationFn: ({ setId }: { setId: string }) => api(`/api/workouts/sets/${setId}`, { method: "DELETE" }),
    scope: SYNC_SCOPE,
    retry: 5,
  });
}

/** After the AI coach saved sets into the open workout, pull them into the phone's local copy. */
export async function pullServerSets(queryClient: QueryClient, workoutId: string) {
  const { mergeServerSets } = await import("../lib/activeWorkout");
  const [server, exercises] = await Promise.all([
    api<ServerWorkout>(`/api/workouts/${workoutId}`),
    queryClient.fetchQuery({ queryKey: gymKeys.exercises, queryFn: () => api<Exercise[]>("/api/exercises"), staleTime: 10 * 60_000 }),
  ]);
  mergeServerSets(server, new Map(exercises.map((e) => [e.id, { name: e.name, muscle_group: e.muscle_group }])));
}
