export type MetricDay = {
  date: string;
  weight_kg: number | null;
  weight_7d_avg: number | null;
  calories_in: number | null;
  calories_in_7d_avg: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  calories_out: number | null;
  steps: number | null;
  sleep_hours: number | null;
  notes: string | null;
};

export type WeekStats = {
  week_start: string;
  run_km: number;
  runs: number;
  gym_workouts: number;
  gym_sets: Record<string, number>;
};

export type StepsBreakdown = {
  date: string;
  steps: number | null;
  steps_method: "manual" | "buckets" | "max_daily" | "single_source" | null;
  sleep_hours: number | null;
  source_totals: Record<string, number>;
  buckets: { start: string; merged: number; per_source: Record<string, number> }[];
};

export type MealItem = {
  id: string;
  label: string;
  /** Food items: nutrients are computed from the food (amount_g); quick-add items carry manual values */
  food_id?: number | null;
  food_name?: string | null;
  food_source?: string | null;
  amount_g?: number | null;
  kcal: number;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
};
export type Meal = { id: string; logged_date: string; meal_type: string; notes: string | null; items: MealItem[] };
export type DayIntake = {
  date: string;
  meals: Meal[];
  totals: { kcal: number; protein_g: number | null; carbs_g: number | null; fat_g: number | null };
};

export type EnergyItem = {
  source: "gym" | "strava" | "activity";
  activity_type: string;
  name: string | null;
  minutes: number;
  distance_km: number | null;
  /** device: the watch's calories via Strava; estimate: MET or running cost × weight */
  method: "device" | "estimate";
  kcal: number | null;
};
/** Estimated expenditure of a day; null parts are unknown and named in `missing` */
export type EnergyDay = {
  date: string;
  weight_kg: number | null;
  bmr_kcal: number | null;
  base_kcal: number | null;
  steps: number | null;
  steps_counted: number | null;
  steps_kcal: number | null;
  exercise_kcal: number | null;
  /** steps + training: the headline number */
  active_kcal: number | null;
  /** base + active, informational; null without a profile */
  total_kcal: number | null;
  missing: ("weight" | "profile" | "steps")[];
  items: EnergyItem[];
};
