import { Check, Flame } from "lucide-react";
import { Link } from "react-router";
import { isoDate } from "../../lib/format";
import { isActive, plural, routineDay, routineWeekStreak, weekDays, weekStart } from "../../lib/habits";
import { Card } from "../Layout";
import { Ring, useHabitDays, useToggleHabit } from "./parts";

const MAX_ITEMS = 3;

/** Přehled card: today's routine ring and only what is left today, tickable in place. Hidden without habits. */
export function RoutineCard() {
  const { active } = useHabitDays();
  const toggle = useToggleHabit();
  const today = isoDate();
  const daily = active.filter((h) => h.frequency === "daily" && isActive(h, today));
  if (!daily.length) return null;

  const r = routineDay(active, today);
  const streak = routineWeekStreak(active, today);
  const monday = weekStart(today);
  const weekly = active.filter((h) => h.frequency === "weekly");
  const weeklyMet = weekly.filter((h) => weekDays(monday).filter((d) => h.doneSet.has(d)).length >= h.weekly_target).length;
  // Routine first, bonus last; ticked ones drop out
  const left = daily.filter((h) => !h.doneSet.has(today)).sort((a, b) => Number(a.is_bonus) - Number(b.is_bonus));
  const routineLeft = left.filter((h) => !h.is_bonus).length;

  return (
    <Card className="space-y-2.5">
      <div className="flex items-center gap-3">
        <Ring value={r.scheduled ? (r.done / r.scheduled) * 100 : 0} size={52} stroke={5}>
          <span className="text-[13px] font-bold tabular-nums">
            {r.done}/{r.scheduled}
          </span>
        </Ring>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{routineLeft === 0 ? "Dnešní rutina splněna" : "Dnešní rutina"}</h2>
          <p className="flex items-center gap-1 text-xs text-zinc-400">
            <Flame size={13} className={streak ? "text-amber-400" : "text-zinc-500"} />
            Série {streak} {plural(streak, "týden", "týdny", "týdnů")}
            {weekly.length > 0 && ` · týden ${weeklyMet}/${weekly.length} úkolů`}
          </p>
        </div>
        <Link to="/hero" className="shrink-0 px-1 py-2 text-[13px] text-zinc-400">
          Vše ›
        </Link>
      </div>
      {left.length > 0 && (
        <div className="space-y-1.5">
          {left.slice(0, MAX_ITEMS).map((h) => (
            <button
              key={h.id}
              type="button"
              onClick={() => toggle(h, today)}
              className="flex min-h-11 w-full items-center gap-2.5 rounded-xl bg-zinc-800/70 px-2.5 py-1.5 text-left active:bg-zinc-700"
            >
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-zinc-600">
                <Check size={13} strokeWidth={3.4} className="text-transparent" />
              </span>
              <span className="min-w-0 flex-1 truncate text-sm">{h.title}</span>
              {h.is_bonus && <span className="shrink-0 text-xs font-semibold text-amber-300">+{h.points} b</span>}
            </button>
          ))}
          {left.length > MAX_ITEMS && (
            <Link to="/hero" className="block px-1 text-xs text-zinc-500">
              a {left.length - MAX_ITEMS} další v Rutině
            </Link>
          )}
        </div>
      )}
    </Card>
  );
}
