import type { Activity, PlanWeek } from "../api/running";
import { isoDate } from "./format";

export type WeekRow = {
  key: string;
  date: string | null;
  plan: string | null;
  run: Activity | null;
  /** done: run exists; todo: still ahead; missed: planned but not run; info: plan detail without a day */
  status: "done" | "todo" | "missed" | "info";
};

const NO_QUALITY = /^(nic|—|–|-)$/i;
const km = (run: Activity) => run.distance_meters / 1000;
const mid = (low: number, high: number | null) => (low + (high ?? low)) / 2;

/**
 * The runs of a plan week as one list. With a day-by-day schedule, planned runs are paired with actual runs by date.
 * Without one, the list is the actual runs plus what the weekly table says is still to come (long run, quality,
 * the rest as easy km).
 */
export function buildWeekRows(week: PlanWeek, today: string): WeekRow[] {
  const dateOf = (run: Activity) => isoDate(new Date(run.start_time));
  const open = (date: string | null) => ((date ?? week.week_end) < today ? "missed" : "todo");
  const rows: WeekRow[] = [];
  const free = [...week.runs];
  const take = (pick: (run: Activity) => boolean) => {
    const index = free.findIndex(pick);
    return index < 0 ? null : free.splice(index, 1)[0];
  };

  if (week.days.length) {
    for (const day of week.days.filter((d) => !d.is_rest)) {
      const run = take((r) => dateOf(r) === day.planned_date);
      rows.push({
        key: `day-${day.planned_date}`,
        date: day.planned_date,
        plan: day.text,
        run,
        status: run ? "done" : open(day.planned_date),
      });
    }
  } else {
    const lrMin = week.long_run_km_min;
    if (week.long_run_text && lrMin !== null) {
      const longest = free.reduce<Activity | null>((best, r) => (!best || km(r) > km(best) ? r : best), null);
      const run = longest && km(longest) >= lrMin * 0.8 ? take((r) => r === longest) : null;
      rows.push({
        key: "long-run",
        date: run ? dateOf(run) : null,
        plan: `Long run ${week.long_run_text} km`,
        run,
        status: run ? "done" : open(null),
      });
    }
  }

  for (const run of free) {
    rows.push({ key: `run-${run.id}`, date: dateOf(run), plan: null, run, status: "done" });
  }

  if (!week.days.length) {
    if (week.quality && !NO_QUALITY.test(week.quality)) {
      rows.push({ key: "quality", date: null, plan: `Kvalita: ${week.quality}`, run: null, status: "info" });
    }
    if (week.km_min !== null && week.long_run_km_min !== null && week.week_end >= today) {
      const rest = Math.round(mid(week.km_min, week.km_max) - mid(week.long_run_km_min, week.long_run_km_max));
      if (rest > 0) rows.push({ key: "easy", date: null, plan: `Další easy běhy, zbytek objemu ~${rest} km`, run: null, status: "info" });
    }
  }

  return rows.sort((a, b) => (a.date && b.date ? a.date.localeCompare(b.date) : a.date ? -1 : b.date ? 1 : 0));
}
