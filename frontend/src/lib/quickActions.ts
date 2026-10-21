import type { MealType, QuickAction, QuickActionColor } from "../api/nutrition";

/** Time windows of quick actions (E42), in minutes of the local day: [start, end), end may be 1440 (midnight). */

export const DAY_MINUTES = 1440;

export const minuteOfDay = (date = new Date()) => date.getHours() * 60 + date.getMinutes();

export const inWindow = (action: Pick<QuickAction, "start_minute" | "end_minute">, minute: number) =>
  action.start_minute <= minute && minute < action.end_minute;

/** Minutes to the window (around midnight too): 0 inside, else the nearer of "starts in" and "ended ago". */
export function windowDistance(action: Pick<QuickAction, "start_minute" | "end_minute">, minute: number): number {
  if (inWindow(action, minute)) return 0;
  const startsIn = (action.start_minute - minute + DAY_MINUTES) % DAY_MINUTES;
  const endedAgo = (minute - action.end_minute + 1 + DAY_MINUTES) % DAY_MINUTES;
  return Math.min(startsIn, endedAgo);
}

/** All actions, the most relevant now first; ties keep the saved order. */
export const byRelevance = (actions: QuickAction[], minute: number) =>
  [...actions].sort((a, b) => windowDistance(a, minute) - windowDistance(b, minute) || a.position - b.position);

/** The action whose window starts next (for "Teď nic, další …"). */
export function nextUp(actions: QuickAction[], minute: number): QuickAction | null {
  const startsIn = (a: QuickAction) => (a.start_minute - minute + DAY_MINUTES) % DAY_MINUTES;
  return [...actions].filter((a) => !inWindow(a, minute)).sort((a, b) => startsIn(a) - startsIn(b))[0] ?? null;
}

/** 300 → "5:00", 1440 → "24:00". */
export const formatMinute = (minute: number) => `${Math.floor(minute / 60)}:${String(minute % 60).padStart(2, "0")}`;

/** For <input type="time">: "05:00"; midnight as an end is "00:00". */
export const timeValue = (minute: number) =>
  `${String(Math.floor(minute / 60) % 24).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;

export function parseTime(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

/** The window a new action gets for its meal (the user can change it). */
export const MEAL_WINDOWS: Record<MealType, [number, number]> = {
  breakfast: [5 * 60, 10 * 60],
  morning_snack: [9 * 60, 12 * 60],
  lunch: [11 * 60, 14 * 60],
  afternoon_snack: [14 * 60, 18 * 60],
  dinner: [17 * 60, 21 * 60],
  second_dinner: [20 * 60, DAY_MINUTES],
  fueling: [0, DAY_MINUTES],
  other: [0, DAY_MINUTES],
};

export const COLORS: readonly QuickActionColor[] = ["amber", "emerald", "sky", "violet", "red"];

export const EMOJIS = ["🥣", "🥛", "🍳", "🥞", "🥪", "🥗", "🍗", "🍚", "🍝", "🐟", "🥩", "🧀", "🍌", "🍎", "🥜", "🍫", "🥤", "☕", "🍵", "🍽️"];
