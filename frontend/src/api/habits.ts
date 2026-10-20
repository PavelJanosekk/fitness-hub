import { type Mutation, type QueryClient, useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { AbilityBrief, AutoRule, Frequency, Habit, HabitBoard, HabitEntry, LogMode, Skill } from "../lib/habits";
import { type Ability, type AbilityDetail, abilityKey } from "../lib/abilities";
import { api } from "./client";
import { retryServerWrite, serverRetryDelay } from "./gym";

export const habitKeys = {
  board: ["habits", "board", "v2"] as const, // v2: log_mode, entries, abilities (E37)
  abilities: ["habits", "abilities", "v1"] as const,
  ability: (id: number) => ["habits", "ability", id, "v1"] as const,
};

/**
 * One habit, one day: the idempotent PUT behind every tick (queued offline, replayed in order). Entry fields that are
 * left out keep what the server has (a bare tick never wipes a note); null clears them. `ability` is a name, so a
 * dovednost typed in offline is created once on replay.
 */
export type HabitDayWrite = {
  habitId: number;
  date: string;
  done: boolean;
  note?: string | null;
  rating?: number | null;
  ability?: string | null;
};
const DAY_KEY = ["habits", "day"] as const;
const HABIT_SCOPE = { id: "habit-sync" };
const ENTRY_FIELDS = ["note", "rating", "ability"] as const;

export const isHabitWrite = (mutation: Mutation<unknown, Error, unknown, unknown>) => mutation.options.mutationKey?.[0] === "habits";

function applyEntry(habit: Habit, write: HabitDayWrite, abilities: AbilityBrief[]): Habit["entries"] {
  const entries = { ...(habit.entries ?? {}) };
  if (!write.done) {
    delete entries[write.date];
    return entries;
  }
  if (!ENTRY_FIELDS.some((field) => field in write)) return entries;
  const entry: HabitEntry = entries[write.date] ? { ...entries[write.date] } : { note: null, rating: null, ability_id: null, ability: null };
  if ("note" in write) entry.note = write.note?.trim() || null;
  if ("rating" in write) entry.rating = write.rating || null;
  if ("ability" in write) {
    const name = write.ability?.trim();
    const known = name ? abilities.find((a) => abilityKey(a.name) === abilityKey(name)) : undefined;
    entry.ability = known?.name ?? name ?? null;
    entry.ability_id = known && known.id > 0 ? known.id : null;
  }
  if (entry.note || entry.rating || entry.ability) entries[write.date] = entry;
  else delete entries[write.date];
  return entries;
}

export function applyDay(board: HabitBoard, write: HabitDayWrite): HabitBoard {
  const { habitId, date, done } = write;
  let abilities = board.abilities ?? [];
  const name = write.ability?.trim();
  if (done && name && !abilities.some((a) => abilityKey(a.name) === abilityKey(name))) {
    abilities = [{ id: -abilities.length - 1, name, icon: null }, ...abilities]; // until the server has it
  }
  return {
    ...board,
    abilities,
    habits: board.habits.map((h) =>
      h.id !== habitId
        ? h
        : {
            ...h,
            done: done ? [...new Set([...h.done, date])].sort() : h.done.filter((d) => d !== date),
            entries: applyEntry(h, write, abilities),
          },
    ),
  };
}

/** Registered before the persisted cache is restored, so ticks queued offline still run after a reload. */
export function registerHabitMutations(queryClient: QueryClient) {
  queryClient.setMutationDefaults(DAY_KEY, {
    mutationFn: ({ habitId, date, ...body }: HabitDayWrite) => api(`/api/habits/${habitId}/days/${date}`, { method: "PUT", body }),
    scope: HABIT_SCOPE,
    retry: retryServerWrite,
    retryDelay: serverRetryDelay,
    // Confirmed ticks go into the cache right away, so nothing flickers between "no longer pending" and the refetch
    onSuccess: (_data, write: HabitDayWrite) =>
      queryClient.setQueryData<HabitBoard>(habitKeys.board, (board) => board && applyDay(board, write)),
    // Refetch (auto rules, other devices) only after the last queued tick, or a refetch would hide the later ones
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey: DAY_KEY }) <= 1) {
        queryClient.invalidateQueries({ queryKey: ["habits"] });
        queryClient.invalidateQueries({ queryKey: ["rpg"] });
      }
    },
  });
}

/**
 * The board with every tick still waiting for the server applied on top, so a tick shows instantly and survives a
 * reload or a refetch while offline.
 */
export function useHabitBoard() {
  const query = useQuery({ queryKey: habitKeys.board, queryFn: () => api<HabitBoard>("/api/habits/board") });
  const pending = useMutationState({
    filters: { mutationKey: DAY_KEY, status: "pending" },
    select: (m) => m.state.variables as HabitDayWrite,
  });
  const data = useMemo(() => (query.data ? pending.reduce(applyDay, query.data) : undefined), [query.data, pending]);
  return { ...query, data };
}

export function useSetHabitDay() {
  const mutation = useMutation<unknown, Error, HabitDayWrite>({ mutationKey: DAY_KEY, scope: HABIT_SCOPE });
  return mutation.mutate;
}

export type HabitInput = {
  title: string;
  frequency: Frequency;
  weekly_target: number;
  skill: Skill | null;
  points: number;
  is_bonus: boolean;
  auto_rule: AutoRule | null;
  auto_threshold: number | null;
  log_mode: LogMode;
};

/** Create or edit a habit, or archive / restore it. Needs the server (it assigns the id), so it fails at once. */
export function useSaveHabit() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: ({ id, ...body }: Partial<HabitInput> & { id?: number; archived?: boolean }) =>
      id ? api<Habit>(`/api/habits/${id}`, { method: "PATCH", body }) : api<Habit>("/api/habits", { method: "POST", body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["habits"] });
      queryClient.invalidateQueries({ queryKey: ["rpg"] });
    },
  });
}

export function useDeleteHabit() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: (id: number) => api(`/api/habits/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["habits"] }),
  });
}

export function useAbilities() {
  return useQuery({ queryKey: habitKeys.abilities, queryFn: () => api<Ability[]>("/api/habits/abilities") });
}

export function useAbility(id: number | null) {
  return useQuery({
    queryKey: habitKeys.ability(id ?? 0),
    queryFn: () => api<AbilityDetail>(`/api/habits/abilities/${id}`),
    enabled: id != null && id > 0,
  });
}

/** Rename / icon, merge into another, delete. Online only; every habit query refetches after. */
export function useEditAbility() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: (
      edit:
        | { id: number; kind: "update"; name?: string; icon?: string | null }
        | { id: number; kind: "merge"; intoId: number }
        | { id: number; kind: "delete" },
    ) => {
      if (edit.kind === "merge") return api(`/api/habits/abilities/${edit.id}/merge`, { method: "POST", body: { into_id: edit.intoId } });
      if (edit.kind === "delete") return api(`/api/habits/abilities/${edit.id}`, { method: "DELETE" });
      const { id, kind: _kind, ...body } = edit;
      return api(`/api/habits/abilities/${id}`, { method: "PATCH", body });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["habits"] });
      queryClient.invalidateQueries({ queryKey: ["rpg"] });
    },
  });
}

export function useReorderHabits() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: (ids: number[]) => api("/api/habits/order", { method: "PUT", body: { ids } }),
    onMutate: (ids) =>
      queryClient.setQueryData<HabitBoard>(habitKeys.board, (board) =>
        board && { ...board, habits: ids.map((id, position) => ({ ...board.habits.find((h) => h.id === id)!, position })) },
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["habits"] }),
  });
}
