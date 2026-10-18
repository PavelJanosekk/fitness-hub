/**
 * Habit tracker derivations (E20). Mirrors backend/app/services/habits.py so the UI can show a tick instantly and
 * offline; keep the rules of both in sync:
 * - a habit counts from its start_date and stops counting on the day it is archived;
 * - a daily streak ends today if today is done, else yesterday (an unticked today does not break it);
 * - a weekly habit is met in an ISO week with at least weekly_target done days, its streak counts met weeks;
 * - the routine of a day = active non-bonus daily habits; bonus habits only add points;
 * - a routine week counts toward the routine streak at >= ROUTINE_WEEK_PCT % of its scheduled daily ticks;
 * - skipped days (a pause, or the one forgiven missed day per month, E22) count for nothing: they neither break nor
 *   extend a streak and are left out of rates and the week %; a fully paused week is skipped the same way.
 */
import { addDays, isoDate } from "./format";

export type Frequency = "daily" | "weekly";
export type Skill = "body" | "nutrition" | "home" | "discipline" | "mind";
export type AutoRule = "gym_workout" | "activity" | "gym_or_activity" | "steps" | "sleep" | "weight_logged" | "protein";

export type Habit = {
  id: number;
  title: string;
  frequency: Frequency;
  weekly_target: number;
  skill: Skill | null;
  points: number;
  is_bonus: boolean;
  auto_rule: AutoRule | null;
  auto_threshold: number | null;
  position: number;
  start_date: string;
  archived_at: string | null;
  done: string[]; // ticked by hand
  auto: Record<string, string>; // completed by the auto rule: day -> what did it
};
// paused / forgiven: optional, older persisted boards don't have them
export type HabitBoard = { today: string; start: string; habits: Habit[]; paused?: string[]; forgiven?: string[] };

export const ROUTINE_WEEK_PCT = 60;

/** Skill order = chart palette slot, so each area keeps its color in every theme. */
export const SKILLS: readonly (readonly [Skill, string])[] = [
  ["body", "Tělo"],
  ["nutrition", "Výživa"],
  ["home", "Domov"],
  ["discipline", "Disciplína"],
  ["mind", "Mysl"],
];
export const skillIndex = (skill: Skill | null) => SKILLS.findIndex(([key]) => key === skill);
export const skillLabel = (skill: Skill | null) => SKILLS.find(([key]) => key === skill)?.[1] ?? null;

export const AUTO_RULES: readonly { rule: AutoRule; label: string; hint?: string; unit?: string; fallback?: number }[] = [
  { rule: "gym_workout", label: "Trénink v Gymu" },
  { rule: "activity", label: "Aktivita ze Stravy", hint: "běh, kolo, plavání…" },
  { rule: "gym_or_activity", label: "Gym nebo Strava" },
  { rule: "steps", label: "Kroky", unit: "kroků", fallback: 10_000 },
  { rule: "sleep", label: "Spánek", unit: "h", fallback: 7 },
  { rule: "weight_logged", label: "Zapsaná váha" },
  { rule: "protein", label: "Bílkoviny", unit: "g", hint: "prázdné = denní cíl z Jídla" },
];

export const WEEKDAYS_SHORT = ["po", "út", "st", "čt", "pá", "so", "ne"] as const;
export const WEEKDAYS_LONG = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"] as const;

export function plural(n: number, one: string, few: string, many: string): string {
  return n === 1 ? one : n >= 2 && n <= 4 ? few : many;
}

/** 0 = Monday … 6 = Sunday */
export const weekdayIndex = (iso: string) => (new Date(`${iso}T12:00:00`).getDay() + 6) % 7;
export const weekStart = (iso: string) => addDays(iso, -weekdayIndex(iso));
export const weekDays = (monday: string) => Array.from({ length: 7 }, (_, i) => addDays(monday, i));

/** `skip` = paused + forgiven days, shared by all habits of one board. */
export type HabitDays = Habit & { manual: Set<string>; doneSet: Set<string>; archivedOn: string | null; skip: Set<string> };

export function withDays(habit: Habit, skip: Set<string> = new Set()): HabitDays {
  const manual = new Set(habit.done);
  return {
    ...habit,
    manual,
    doneSet: new Set([...manual, ...Object.keys(habit.auto)]),
    archivedOn: habit.archived_at ? isoDate(new Date(habit.archived_at)) : null,
    skip,
  };
}

const weekSkipped = (skip: Set<string>, monday: string) => weekDays(monday).every((d) => skip.has(d));

export const isActive = (h: HabitDays, day: string) => day >= h.start_date && (h.archivedOn === null || day < h.archivedOn);
export const weekCount = (done: Set<string>, monday: string) => weekDays(monday).filter((d) => done.has(d)).length;
export const isRoutine = (h: HabitDays) => h.frequency === "daily" && !h.is_bonus;

export function currentStreak(h: HabitDays, on: string): number {
  let streak = 0;
  if (h.frequency === "weekly") {
    let week = weekStart(on);
    if (weekCount(h.doneSet, week) < h.weekly_target) week = addDays(week, -7);
    for (; week >= weekStart(h.start_date); week = addDays(week, -7)) {
      if (weekCount(h.doneSet, week) >= h.weekly_target) streak += 1;
      else if (!weekSkipped(h.skip, week)) break;
    }
    return streak;
  }
  for (let day = h.doneSet.has(on) ? on : addDays(on, -1); day >= h.start_date; day = addDays(day, -1)) {
    if (h.doneSet.has(day)) streak += 1;
    else if (!h.skip.has(day)) break;
  }
  return streak;
}

export function bestStreak(h: HabitDays, on: string): number {
  let best = 0;
  let run = 0;
  if (h.frequency === "weekly") {
    for (let week = weekStart(h.start_date); week <= weekStart(on); week = addDays(week, 7)) {
      if (weekCount(h.doneSet, week) >= h.weekly_target) run += 1;
      else if (!weekSkipped(h.skip, week)) run = 0;
      best = Math.max(best, run);
    }
    return best;
  }
  for (let day = h.start_date; day <= on; day = addDays(day, 1)) {
    if (h.doneSet.has(day)) run += 1;
    else if (!h.skip.has(day)) run = 0;
    best = Math.max(best, run);
  }
  return best;
}

/** [done, scheduled] days (daily) or met/elapsed weeks (weekly; the current week only once met); skipped days only count when done. */
export function completion(h: HabitDays, start: string, end: string): [number, number] {
  let done = 0;
  let scheduled = 0;
  if (h.frequency === "weekly") {
    const current = weekStart(end);
    for (let week = weekStart(start > h.start_date ? start : h.start_date); week <= end; week = addDays(week, 7)) {
      if (!isActive(h, week > h.start_date ? week : h.start_date)) continue;
      const met = weekCount(h.doneSet, week) >= h.weekly_target;
      if (met || (week < current && !weekSkipped(h.skip, week))) {
        scheduled += 1;
        done += met ? 1 : 0;
      }
    }
    return [done, scheduled];
  }
  for (let day = start; day <= end; day = addDays(day, 1)) {
    if (!isActive(h, day) || (h.skip.has(day) && !h.doneSet.has(day))) continue;
    scheduled += 1;
    done += h.doneSet.has(day) ? 1 : 0;
  }
  return [done, scheduled];
}

export type RoutineDay = { done: number; scheduled: number; points: number; maxPoints: number; bonus: number };

/** The day's routine: non-bonus daily habits (done / scheduled) and the sheet's points (bonus on top of the max). */
export function routineDay(habits: HabitDays[], day: string): RoutineDay {
  const result: RoutineDay = { done: 0, scheduled: 0, points: 0, maxPoints: 0, bonus: 0 };
  for (const h of habits) {
    if (h.frequency !== "daily" || !isActive(h, day)) continue;
    const done = h.doneSet.has(day);
    if (h.is_bonus) {
      if (done) result.bonus += h.points;
      continue;
    }
    result.scheduled += 1;
    result.maxPoints += h.points;
    if (done) {
      result.done += 1;
      result.points += h.points;
    }
  }
  return result;
}

export const pct = (done: number, scheduled: number) => (scheduled ? Math.round((done / scheduled) * 100) : null);

/** Percent of the routine done in one ISO week, counting days up to `on`; null when nothing was scheduled. */
export function routineWeekPct(habits: HabitDays[], monday: string, on: string): number | null {
  const skip = habits[0]?.skip ?? new Set<string>();
  let done = 0;
  let scheduled = 0;
  for (const day of weekDays(monday)) {
    if (day > on) break;
    if (skip.has(day)) continue;
    const r = routineDay(habits, day);
    done += r.done;
    scheduled += r.scheduled;
  }
  return scheduled ? (done / scheduled) * 100 : null;
}

export function routineWeekStreak(habits: HabitDays[], on: string): number {
  if (!habits.length) return 0;
  const first = weekStart(habits.reduce((min, h) => (h.start_date < min ? h.start_date : min), on));
  let week = weekStart(on);
  const current = routineWeekPct(habits, week, on);
  if (current === null || current < ROUTINE_WEEK_PCT) week = addDays(week, -7);
  let streak = 0;
  for (; week >= first; week = addDays(week, -7)) {
    const p = routineWeekPct(habits, week, on);
    if (p === null) continue;
    if (p < ROUTINE_WEEK_PCT) break;
    streak += 1;
  }
  return streak;
}
