import { Check, Flame, Zap } from "lucide-react";
import { useMemo } from "react";
import { useHabitBoard, useSetHabitDay } from "../../api/habits";
import { isoDate } from "../../lib/format";
import {
  AUTO_RULES,
  currentStreak,
  type HabitDays,
  plural,
  skillIndex,
  skillLabel,
  WEEKDAYS_SHORT,
  weekDays,
  weekStart,
  weekdayIndex,
  withDays,
} from "../../lib/habits";
import { useChartColors } from "../charts/palette";

/** All habits in their order with done-day sets; `active` = not archived. */
export function useHabitDays() {
  const board = useHabitBoard();
  const habits = useMemo(() => (board.data?.habits ?? []).map(withDays).sort((a, b) => a.position - b.position || a.id - b.id), [board.data]);
  return { board, habits, active: habits.filter((h) => h.archived_at === null) };
}

/**
 * Tick / untick a habit on a day. Days completed by an auto rule can't be unticked (the data says so).
 * Weekly habits: with a target of 1 a done week is unticked as a whole, otherwise the tap toggles the given day.
 */
export function useToggleHabit() {
  const setDay = useSetHabitDay();
  return (h: HabitDays, day: string) => {
    if (h.frequency === "weekly") {
      const days = weekDays(weekStart(day));
      const manual = days.filter((d) => h.manual.has(d));
      const met = days.filter((d) => h.doneSet.has(d)).length >= h.weekly_target;
      if (h.weekly_target === 1 && met) {
        manual.forEach((d) => setDay({ habitId: h.id, date: d, done: false }));
        return;
      }
      if (h.manual.has(day)) setDay({ habitId: h.id, date: day, done: false });
      else if (!h.auto[day]) setDay({ habitId: h.id, date: day, done: true });
      return;
    }
    if (h.manual.has(day)) setDay({ habitId: h.id, date: day, done: false });
    else if (!h.auto[day]) setDay({ habitId: h.id, date: day, done: true });
  };
}

/** Progress ring; colors come from the theme palette (track = tile, fill = accent). */
export function Ring({ value, size, stroke, children }: { value: number; size: number; stroke: number; children?: React.ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <span className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-zinc-800" />
        {value > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${(Math.min(value, 100) / 100) * c} ${c}`}
            className="stroke-emerald-500 transition-[stroke-dasharray] duration-300"
          />
        )}
      </svg>
      <span className="absolute inset-0 flex flex-col items-center justify-center">{children}</span>
    </span>
  );
}

export function SkillDot({ skill }: { skill: HabitDays["skill"] }) {
  const { series, ink } = useChartColors();
  const index = skillIndex(skill);
  return <span className="size-2 shrink-0 rounded-full" style={{ background: index >= 0 ? series[index] : ink.muted }} />;
}

export function StreakBadge({ value, unit, lit }: { value: number; unit: "day" | "week"; lit: boolean }) {
  if (value <= 0) return null;
  const label = unit === "day" ? plural(value, "den", "dny", "dní") : plural(value, "týden", "týdny", "týdnů");
  return (
    <span className={`flex shrink-0 items-center gap-1 text-[13px] tabular-nums ${lit ? "text-zinc-100" : "text-zinc-400"}`}>
      <Flame size={15} className={lit ? "text-amber-400" : "text-zinc-500"} />
      {value} {label}
    </span>
  );
}

const autoRuleLabel = (h: HabitDays) => AUTO_RULES.find((a) => a.rule === h.auto_rule)?.label ?? "";

/** One tap row of the day view: checkbox, title, area + what completed it, streak. */
export function HabitRow({ h, day, onToggle }: { h: HabitDays; day: string; onToggle: () => void }) {
  const weekly = h.frequency === "weekly";
  const monday = weekStart(day);
  const doneDays = weekly ? weekDays(monday).filter((d) => h.doneSet.has(d)) : [];
  const done = weekly ? doneDays.length >= h.weekly_target : h.doneSet.has(day);
  const autoOnly = !weekly && done && !h.manual.has(day);
  const autoText = weekly ? doneDays.map((d) => h.auto[d]).find(Boolean) : h.auto[day];
  const partial = weekly && h.weekly_target > 1 && !done ? doneDays.length : 0;

  let status: string;
  if (weekly) {
    const when = doneDays.length ? `hotovo ${doneDays.map((d) => WEEKDAYS_SHORT[weekdayIndex(d)]).join(", ")}` : "tento týden ještě ne";
    status = h.weekly_target > 1 ? `${doneDays.length}/${h.weekly_target}× · ${when}` : when;
  } else {
    status = autoText ?? (h.auto_rule ? `automaticky: ${autoRuleLabel(h)}` : "");
  }
  const streak = currentStreak(h, day < isoDate() ? day : isoDate());

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={done}
      aria-disabled={autoOnly}
      className="flex min-h-[60px] w-full items-center gap-3 px-3.5 py-2.5 text-left active:bg-zinc-800/60"
    >
      <span
        className={`flex size-[30px] shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
          done ? "border-emerald-500 bg-emerald-500 text-on-accent" : partial ? "border-emerald-700 text-zinc-200" : "border-zinc-600"
        }`}
      >
        {done ? autoOnly ? <Zap size={15} strokeWidth={2.6} /> : <Check size={16} strokeWidth={3.2} /> : partial ? <span className="text-[11px] font-semibold">{partial}</span> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className={`block text-[15px] font-medium ${done ? "text-zinc-400" : "text-zinc-100"}`}>{h.title}</span>
        <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-zinc-500">
          <SkillDot skill={h.skill} />
          {skillLabel(h.skill) && <span className="shrink-0">{skillLabel(h.skill)}</span>}
          {status && (
            <span className="flex min-w-0 items-center gap-1 truncate">
              {skillLabel(h.skill) && <span aria-hidden="true">·</span>}
              {autoText && <Zap size={11} className="shrink-0 text-emerald-400" />}
              <span className="truncate">{status}</span>
            </span>
          )}
        </span>
      </span>
      {h.is_bonus ? (
        <span className="shrink-0 rounded-full bg-zinc-800 px-2 py-0.5 text-xs font-semibold text-amber-300">+{h.points} b</span>
      ) : (
        <StreakBadge value={streak} unit={weekly ? "week" : "day"} lit={done} />
      )}
    </button>
  );
}
