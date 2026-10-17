import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type PlanWeek = {
  week_start: string;
  week_end: string;
  block: string | null;
  km_text: string | null;
  km_min: number | null;
  km_max: number | null;
  long_run_text: string | null;
  long_run_km_min: number | null;
  long_run_km_max: number | null;
  quality: string | null;
  notes: string | null;
  actual_km: number;
  actual_runs: number;
  longest_run_km: number | null;
};

export type Activity = {
  id: number;
  start_time: string;
  activity_type: string;
  distance_meters: number;
  duration_seconds: number;
  avg_hr: number | null;
  notes: string | null;
  description: string | null;
  pace_sec_per_km: number | null;
  rpe: number | null;
  heat: boolean;
  gap_sec_per_km: number | null;
  ef_gap: number | null;
  decoupling_pct: number | null;
  pct_above_easy: number | null;
  z4_minutes: number | null;
};

export type KbStatus = {
  repo: string | null;
  lthr: number | null;
  max_hr: number | null;
  kb_updated: string | null;
  last_synced_at: string | null;
  last_sync_error: string | null;
  sync_warnings: string[];
  documents: { path: string; characters: number }[];
  races: { name: string; date: string; distance_km: number | null; is_goal_race: boolean; goal: string | null }[];
  plan_weeks: number;
};

export const useRunWeeks = () => useQuery({ queryKey: ["running", "weeks"], queryFn: () => api<PlanWeek[]>("/api/running/weeks") });
export const useActivities = () =>
  useQuery({ queryKey: ["running", "activities"], queryFn: () => api<Activity[]>("/api/running/activities?limit=40") });
export const useKb = () => useQuery({ queryKey: ["coach", "kb"], queryFn: () => api<KbStatus>("/api/coach/kb") });

/** HR zones as % of LTHR, rounded exactly like the backend and the knowledge base (02_physiology_zones.md). */
export function zones(lthr: number) {
  const r = (pct: number) => Math.round(pct * lthr);
  return [
    { zone: "Z1", label: "Recovery", range: `≤${r(0.8) - 1}` },
    { zone: "Z2", label: "Easy", range: `${r(0.8)}–${r(0.89)}` },
    { zone: "Z3", label: "Steady / MP", range: `${r(0.89) + 1}–${r(0.94)}` },
    { zone: "Z4", label: "Threshold", range: `${r(0.94) + 1}–${lthr}` },
    { zone: "Z5", label: "Nad prahem", range: `≥${lthr + 1}` },
  ];
}
