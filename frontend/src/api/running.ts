import { useQuery } from "@tanstack/react-query";
import { addDays, isoDate } from "../lib/format";
import { api } from "./client";

export type PlanDay = {
  planned_date: string;
  text: string;
  is_rest: boolean;
  km_min: number | null;
  km_max: number | null;
};

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
  days: PlanDay[];
  runs: Activity[];
};

export type Activity = {
  id: number;
  external_id: string | null;
  start_time: string;
  activity_type: string;
  distance_meters: number;
  duration_seconds: number;
  elapsed_seconds?: number | null;
  elevation_gain_m?: number | null;
  avg_cadence?: number | null;
  avg_hr: number | null;
  max_hr?: number | null;
  calories?: number | null;
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

// "v2": the persisted query cache on phones still holds the old shape without `days`/`runs`
export const useRunWeeks = () =>
  useQuery({
    queryKey: ["running", "weeks", "v2"],
    queryFn: () => api<PlanWeek[]>(`/api/running/weeks?end_date=${addDays(isoDate(), 400)}`),
  });
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

/** Link to the activity on strava.com (external ids look like "strava:1234567890"). */
export const stravaUrl = (activity: Pick<Activity, "external_id">) =>
  activity.external_id?.startsWith("strava:") ? `https://www.strava.com/activities/${activity.external_id.slice(7)}` : null;

export type RunStat = {
  id: number;
  date: string;
  distance_km: number;
  moving_s: number;
  avg_hr: number | null;
  heat: boolean;
  vdot: number | null;
  pace_s_per_km: number | null;
  gap_s_per_km: number | null;
  hr_avg_steady: number | null;
  ef_gap: number | null;
  gap_at_easy_band_s_per_km: number | null;
  pct_above_easy: number | null;
  zone_seconds: Record<string, number> | null;
};
export type RunStats = { lthr: number | null; runs: RunStat[] };

export const useRunStats = () =>
  useQuery({ queryKey: ["running", "stats", "v1"], queryFn: () => api<RunStats>("/api/running/stats") });

export type RunSplit = {
  km: number;
  moving_s: number;
  pace: number;
  gap: number | null;
  hr: number | null;
  elevation_m: number | null;
  cadence: number | null;
};
export type RunSeriesKey = "time_s" | "distance_km" | "pace" | "gap" | "hr" | "altitude" | "cadence" | "lat" | "lng";
export type RunDetail = {
  activity: Activity;
  /** "partial": fetched before altitude, cadence and the route were requested (Strava was unreachable) */
  streams: "full" | "partial" | "none";
  elevation_gain_m: number | null;
  lthr: number | null;
  zone_bounds: Record<string, string> | null;
  zone_seconds: Record<string, number> | null;
  hr_avg_steady: number | null;
  pace_first10_s_per_km: number | null;
  /** Equal-length columns; a key is missing when the run didn't record it */
  series: Partial<Record<RunSeriesKey, (number | null)[]>>;
  splits: RunSplit[];
  route: [number, number][];
};

export const useRunDetail = (id: number) =>
  useQuery({ queryKey: ["running", "activity", id, "v1"], queryFn: () => api<RunDetail>(`/api/running/activities/${id}`) });
