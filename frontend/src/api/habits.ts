import { type Mutation, type QueryClient, useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { AutoRule, Frequency, Habit, HabitBoard, Skill } from "../lib/habits";
import { api } from "./client";
import { retryServerWrite, serverRetryDelay } from "./gym";

export const habitKeys = {
  board: ["habits", "board", "v1"] as const,
};

/** One habit, one day: the idempotent PUT behind every tick (queued offline, replayed in order). */
export type HabitDayWrite = { habitId: number; date: string; done: boolean };
const DAY_KEY = ["habits", "day"] as const;
const HABIT_SCOPE = { id: "habit-sync" };

export const isHabitWrite = (mutation: Mutation<unknown, Error, unknown, unknown>) => mutation.options.mutationKey?.[0] === "habits";

export function applyDay(board: HabitBoard, { habitId, date, done }: HabitDayWrite): HabitBoard {
  return {
    ...board,
    habits: board.habits.map((h) =>
      h.id !== habitId ? h : { ...h, done: done ? [...new Set([...h.done, date])].sort() : h.done.filter((d) => d !== date) },
    ),
  };
}

/** Registered before the persisted cache is restored, so ticks queued offline still run after a reload. */
export function registerHabitMutations(queryClient: QueryClient) {
  queryClient.setMutationDefaults(DAY_KEY, {
    mutationFn: ({ habitId, date, done }: HabitDayWrite) => api(`/api/habits/${habitId}/days/${date}`, { method: "PUT", body: { done } }),
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
