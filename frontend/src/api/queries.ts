import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, isoDate } from "../lib/format";
import { uuid } from "../lib/uuid";
import { api } from "./client";
import type { DayIntake, EnergyDay, MetricDay, StepsBreakdown, WeekStats } from "./types";

export const keys = {
  metrics: (days: number) => ["metrics", days] as const,
  weekly: (weeks: number) => ["metrics", "weekly", weeks] as const,
  steps: (date: string) => ["metrics", "steps", date] as const,
  intake: (date: string) => ["nutrition", "day", date] as const,
  energy: (start: string, end: string) => ["metrics", "energy", "v3", start, end] as const,
};

export function useMetrics(days: number) {
  const end = isoDate();
  return useQuery({
    queryKey: keys.metrics(days),
    queryFn: () => api<MetricDay[]>(`/api/metrics?start_date=${addDays(end, -(days - 1))}&end_date=${end}`),
  });
}

/** Estimated expenditure per day (base + steps + training) for [start, end]. */
export const useEnergy = (start: string, end: string) =>
  useQuery({
    queryKey: keys.energy(start, end),
    queryFn: () => api<EnergyDay[]>(`/api/metrics/energy?start_date=${start}&end_date=${end}`),
  });

export const useWeekly = (weeks: number) =>
  useQuery({ queryKey: keys.weekly(weeks), queryFn: () => api<WeekStats[]>(`/api/metrics/weekly?weeks=${weeks}`) });

export const useStepsBreakdown = (date: string, enabled: boolean) =>
  useQuery({
    queryKey: keys.steps(date),
    queryFn: () => api<StepsBreakdown>(`/api/metrics/steps-breakdown?date=${date}`),
    enabled,
  });

export const useDayIntake = (date: string) =>
  useQuery({ queryKey: keys.intake(date), queryFn: () => api<DayIntake>(`/api/nutrition/day?date=${date}`) });

export function useSaveWeight() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["metrics", "upsert"],
    mutationFn: (weight_kg: number) => api("/api/metrics", { method: "POST", body: { date: isoDate(), weight_kg } }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["metrics"] }),
  });
}

/** Morning resting HR, entered by hand (E41): feeds the weekly base proposal. */
export function useSaveRestingHr() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["metrics", "resting-hr"],
    mutationFn: (resting_hr: number) => api("/api/metrics", { method: "POST", body: { date: isoDate(), resting_hr } }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
      queryClient.invalidateQueries({ queryKey: ["nutrition", "targets"] });
    },
  });
}

export function useQuickAddKcal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["nutrition", "quick-add"],
    // The id is generated once per entry, so a retry after a dropped connection can't log it twice
    mutationFn: ({ id, kcal, protein_g }: { id: string; kcal: number; protein_g?: number }) =>
      api("/api/nutrition/quick-add", { method: "POST", body: { id, date: isoDate(), kcal, protein_g } }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["nutrition"] });
      queryClient.invalidateQueries({ queryKey: ["metrics"] });
    },
  });
}

export const newEntryId = uuid;
