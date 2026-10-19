import { type Mutation, type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updateActiveExercise } from "../lib/activeWorkout";
import { ApiError, api } from "./client";

export type Exercise = { id: number; name: string; muscle_group: string; equipment: string | null };
export type SetType = "normal" | "warmup" | "drop" | "failure";
export type LastPerformance = {
  exercise_id: number;
  workout_id: string | null;
  workout_started_at: string | null;
  sets: { set_order: number; set_type: SetType; weight_kg: number | null; reps: number | null }[];
};
export type TemplateSet = { set_type: SetType; weight_kg: number | null; reps: number | null };
export type TemplateExercise = { exercise_id: number; name: string; sets: TemplateSet[] };
export type Template = { id: string; name: string; position: number; exercises: TemplateExercise[] };
export type PersonalRecord = {
  exercise_id: number;
  name: string;
  kind: "weight" | "e1rm" | "reps";
  value: number;
  reps: number | null;
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
  prs: PersonalRecord[];
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
  // Not edited in the app (Strong imports, AI dictation), but kept when a finished workout is edited
  rpe?: number | null;
  duration_s?: number | null;
  distance_m?: number | null;
  notes?: string | null;
};
export type ServerWorkout = Omit<WorkoutSummary, "duration_min" | "set_count" | "total_volume_kg" | "prs"> & {
  notes: string | null;
  sets: ServerSet[];
};

export type SetBody = Omit<ServerSet, "id">;

export const gymKeys = {
  exercises: ["exercises"] as const,
  // "v2": the persisted cache on phones still holds the old template shape (derived from history)
  templates: ["workouts", "templates", "v2"] as const,
  history: ["workouts", "history", "v2"] as const, // v2: summaries gained `prs`; older persisted ones lack it
  workout: (id: string) => ["workouts", id] as const,
  last: (exerciseId: number) => ["exercises", exerciseId, "last"] as const,
  // Under "workouts" / "exercises", so finishing a workout or editing a set refreshes the charts too
  stats: ["workouts", "stats", "v1"] as const,
  progression: (exerciseId: number) => ["exercises", exerciseId, "progression", "v1"] as const,
};

export const useExercises = () =>
  useQuery({ queryKey: gymKeys.exercises, queryFn: () => api<Exercise[]>("/api/exercises"), staleTime: 10 * 60_000 });
export const useTemplates = () =>
  useQuery({ queryKey: gymKeys.templates, queryFn: () => api<Template[]>("/api/workouts/templates") });
export const useHistory = () =>
  useQuery({
    queryKey: gymKeys.history,
    queryFn: () => api<WorkoutSummary[]>("/api/workouts?limit=200"),
    select: (rows) => rows.map((w) => ({ ...w, prs: w.prs ?? [] })),
  });
export type StatsDay = { date: string; workouts: number; sets: number; volume_kg: number };
export type StatsWeek = {
  week_start: string;
  workouts: number;
  sets: Record<string, number>;
  volume_kg: Record<string, number>;
  muscles: Record<string, number>;
  unclassified_sets: number;
};
export type StatsExercise = { exercise_id: number; name: string; muscle_group: string; sessions: number; last_date: string };
export type GymStats = { days: StatsDay[]; weeks: StatsWeek[]; exercises: StatsExercise[] };
export type PrKind = PersonalRecord["kind"];
export type ProgressionSession = {
  workout_id: string;
  date: string;
  sets: number;
  volume_kg: number;
  max_weight: number | null;
  max_weight_reps: number | null;
  e1rm: number | null;
  e1rm_set: string | null;
  max_reps: number | null;
  pr: PrKind[];
};
export type ExerciseProgression = { exercise_id: number; name: string; weighted: boolean; sessions: ProgressionSession[] };

export const STATS_WEEKS = 26;
export const useGymStats = () =>
  useQuery({ queryKey: gymKeys.stats, queryFn: () => api<GymStats>(`/api/workouts/stats?weeks=${STATS_WEEKS}`) });
export const useProgression = (exerciseId: number | null) =>
  useQuery({
    queryKey: gymKeys.progression(exerciseId ?? 0),
    queryFn: () => api<ExerciseProgression>(`/api/exercises/${exerciseId}/progression`),
    enabled: exerciseId !== null,
  });

export type ExerciseInput = { name: string; muscle_group: string; equipment: string | null };

/** Create or edit an exercise. Needs the server (it assigns the id), so it fails at once instead of queueing. */
export function useSaveExercise() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: ({ id, ...body }: ExerciseInput & { id?: number }) =>
      id ? api<Exercise>(`/api/exercises/${id}`, { method: "PATCH", body }) : api<Exercise>("/api/exercises", { method: "POST", body }),
    onSuccess: (saved) => {
      queryClient.setQueryData<Exercise[]>(gymKeys.exercises, (list) =>
        [...(list ?? []).filter((e) => e.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)),
      );
      // Templates and history show exercise names from the server
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      updateActiveExercise(saved);
    },
  });
}

export function useSaveTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name, exercises }: { id: string; name: string; exercises: { exercise_id: number; sets: TemplateSet[] }[] }) =>
      api<Template>(`/api/workouts/templates/${id}`, { method: "PUT", body: { name, exercises } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: gymKeys.templates }),
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/workouts/templates/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: gymKeys.templates }),
  });
}

/** Deleting a finished workout from the history (not queued: needs the server, errors are shown). */
export function useDeleteWorkout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/workouts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

export type WorkoutEdit = {
  id: string;
  name: string;
  started_at: string;
  ended_at: string;
  notes: string | null;
  sets: (SetBody & { id: string })[];
};

/**
 * Editing a finished workout or logging a past one: one request with the whole set list (sets left out are deleted).
 * Not queued like the live workout: it needs the server, and errors are shown in the editor.
 */
export function useSaveWorkout() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: ({ id, ...body }: WorkoutEdit) =>
      api<ServerWorkout>(`/api/workouts/${id}`, { method: "PUT", body: { ...body, replace_sets: true } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(gymKeys.workout(saved.id), saved);
      // History, PRs, charts, ghost values, progression and the RPG ledger all derive from the sets
      for (const key of ["workouts", "exercises", "metrics", "rpg"]) queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
}

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

/**
 * The phone can be online while the server is not (a deploy, Tailscale off, `tailscale serve` answering 502), and
 * offlineFirst only pauses for the browser's own offline state. So a write keeps retrying for as long as the
 * server is unreachable. A rejected write (4xx) would fail again, and other 5xx get a few tries.
 */
export function retryServerWrite(failureCount: number, error: unknown): boolean {
  if (!(error instanceof ApiError)) return true; // fetch itself failed: no connection to the server
  if ([408, 429, 502, 503, 504].includes(error.status)) return true;
  return error.status >= 500 && failureCount < 5;
}

export const serverRetryDelay = (attempt: number) => Math.min(1000 * 2 ** attempt, 30_000);

export const isGymWrite = (mutation: Mutation<unknown, Error, unknown, unknown>) => mutation.options.mutationKey?.[0] === "gym";

/**
 * Called once the persisted cache is restored. Besides the paused writes (queued while offline), it resumes the
 * write that was in flight or retrying when the app closed: those are persisted too (see main.tsx), because
 * TanStack only keeps paused ones by default. Scoped writes still run one at a time, in order.
 */
export function resumePendingMutations(queryClient: QueryClient) {
  const pending = queryClient.getMutationCache().getAll().filter((m) => m.state.isPaused || m.state.status === "pending");
  return Promise.all(pending.map((m) => m.continue().catch(() => undefined)));
}

export function registerGymMutations(queryClient: QueryClient) {
  queryClient.setMutationDefaults(["gym", "workout"], {
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api(`/api/workouts/${id}`, { method: "PUT", body }),
    scope: SYNC_SCOPE,
    retry: retryServerWrite,
    retryDelay: serverRetryDelay,
    // Here, not at the call site: the workout screen is gone by the time a finish request settles
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
  // Discarding an unfinished workout: the delete is queued behind its earlier writes, so it can't be recreated by them
  queryClient.setMutationDefaults(["gym", "discard"], {
    mutationFn: ({ id }: { id: string }) => api(`/api/workouts/${id}`, { method: "DELETE" }),
    scope: SYNC_SCOPE,
    retry: retryServerWrite,
    retryDelay: serverRetryDelay,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
  queryClient.setMutationDefaults(["gym", "set"], {
    mutationFn: ({ workoutId, setId, body }: { workoutId: string; setId: string; body: SetBody }) =>
      api(`/api/workouts/${workoutId}/sets/${setId}`, { method: "PUT", body }),
    scope: SYNC_SCOPE,
    retry: retryServerWrite,
    retryDelay: serverRetryDelay,
  });
  queryClient.setMutationDefaults(["gym", "delete-set"], {
    mutationFn: ({ setId }: { setId: string }) => api(`/api/workouts/sets/${setId}`, { method: "DELETE" }),
    scope: SYNC_SCOPE,
    retry: retryServerWrite,
    retryDelay: serverRetryDelay,
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
