import { ChevronLeft, ChevronRight, Flame } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { addDays, formatDayMonth, formatNumber } from "../../lib/format";
import {
  completion,
  currentStreak,
  type HabitDays,
  isActive,
  pct,
  routineDay,
  WEEKDAYS_LONG,
  WEEKDAYS_SHORT,
  weekCount,
  weekStart,
  weekdayIndex,
} from "../../lib/habits";
import { Legend, useChartKit } from "../charts/DashboardCharts";
import { Card } from "../Layout";
import { SkillDot } from "./parts";

const monthFormat = new Intl.DateTimeFormat("cs-CZ", { month: "long", year: "numeric" });
const MATRIX_DAYS = 14;
const TREND_DAYS = 30;
const PATTERN_WEEKS = 8;

const monthStartOf = (iso: string) => `${iso.slice(0, 8)}01`;
function shiftMonth(start: string, months: number): string {
  const [year, month] = start.split("-").map(Number);
  const index = year * 12 + month - 1 + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}-01`;
}
const monthEndOf = (start: string) => addDays(shiftMonth(start, 1), -1);
const daysBetween = (start: string, end: string) => {
  const days: string[] = [];
  for (let d = start; d <= end; d = addDays(d, 1)) days.push(d);
  return days;
};
const shortDate = (iso: string) => formatDayMonth(iso);

/** Sequential single-hue scale (accent): more done = stronger, in every theme. */
function heat(value: number | null): string {
  if (value === null) return "bg-transparent text-zinc-600";
  if (value === 0) return "bg-zinc-800 text-zinc-300";
  if (value < 34) return "bg-emerald-500/25 text-zinc-100";
  if (value < 67) return "bg-emerald-500/50 text-zinc-50";
  if (value < 100) return "bg-emerald-500/75 text-zinc-50";
  return "bg-emerald-500 text-on-accent";
}

export function MonthView({ habits, today, onOpenDay }: { habits: HabitDays[]; today: string; onOpenDay: (day: string) => void }) {
  const [month, setMonth] = useState(monthStartOf(today));
  const monthEnd = monthEndOf(month);
  const end = monthEnd < today ? monthEnd : today;
  // Rates and patterns leave out today: it is still open
  const closed = end === today ? addDays(today, -1) : end;
  const firstStart = habits.reduce((min, h) => (h.start_date < min ? h.start_date : min), today);
  const daily = habits.filter((h) => h.frequency === "daily");
  const weekly = habits.filter((h) => h.frequency === "weekly");

  const monthDays = daysBetween(month, end);
  const dayPct = (d: string) => {
    const r = routineDay(habits, d);
    return pct(r.done, r.scheduled);
  };
  const closedPcts = monthDays.filter((d) => d <= closed).map(dayPct).filter((v): v is number => v !== null);
  const perfect = monthDays.map(dayPct).filter((v) => v === 100).length;
  const weeklyTotals = weekly.reduce(([done, all], h) => {
    const [d, s] = completion(h, month, end);
    return [done + d, all + s];
  }, [0, 0]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <button onClick={() => setMonth(shiftMonth(month, -1))} disabled={month <= monthStartOf(firstStart)} aria-label="Předchozí měsíc" className="rounded-full p-2.5 text-zinc-400 active:bg-zinc-800 disabled:opacity-30">
          <ChevronLeft size={20} />
        </button>
        <span className="font-semibold capitalize">{monthFormat.format(new Date(`${month}T12:00:00`))}</span>
        <button onClick={() => setMonth(shiftMonth(month, 1))} disabled={monthEnd >= today} aria-label="Další měsíc" className="rounded-full p-2.5 text-zinc-400 active:bg-zinc-800 disabled:opacity-30">
          <ChevronRight size={20} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Tile label="Průměr denních" value={closedPcts.length ? `${Math.round(closedPcts.reduce((a, b) => a + b, 0) / closedPcts.length)} %` : "–"} />
        <Tile label="Perfektní dny" value={String(perfect)} />
        <Tile label="Týdenní úkoly" value={weeklyTotals[1] ? `${pct(weeklyTotals[0], weeklyTotals[1])} %` : "–"} />
      </div>

      <Calendar habits={habits} month={month} today={today} onOpenDay={onOpenDay} />
      <Matrix habits={daily} end={end} today={today} onOpenDay={onOpenDay} />
      <TrendChart habits={habits} end={end} />
      <HabitRates habits={daily} end={closed} />
      <WeekdayPattern habits={habits} end={closed} />
      {weekly.length > 0 && <WeeklyHistory habits={weekly} end={end} />}
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-3!">
      <div className="text-xs text-zinc-400">{label}</div>
      <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums">{value}</div>
    </Card>
  );
}

function Calendar({ habits, month, today, onOpenDay }: { habits: HabitDays[]; month: string; today: string; onOpenDay: (d: string) => void }) {
  const days = daysBetween(month, monthEndOf(month));
  const blanks = weekdayIndex(month);
  return (
    <Card className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Kalendář</h2>
        <span className="text-xs text-zinc-500">ťukni na den</span>
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {WEEKDAYS_SHORT.map((w) => (
          <span key={w} className="text-center text-[11px] text-zinc-500 capitalize">
            {w}
          </span>
        ))}
        {Array.from({ length: blanks }, (_, i) => (
          <span key={`blank-${i}`} />
        ))}
        {days.map((d) => {
          const future = d > today;
          const r = routineDay(habits, d);
          const value = future ? null : pct(r.done, r.scheduled);
          return (
            <button
              key={d}
              disabled={future || r.scheduled === 0}
              onClick={() => onOpenDay(d)}
              aria-label={`${WEEKDAYS_LONG[weekdayIndex(d)]} ${formatDayMonth(d)}${value === null ? "" : `, ${value} %`}`}
              title={value === null ? undefined : `${formatDayMonth(d)} · ${r.done}/${r.scheduled}`}
              className={`flex aspect-square items-center justify-center rounded-[10px] text-[13px] font-semibold tabular-nums ${heat(value)} ${
                d === today ? "ring-2 ring-zinc-100 ring-inset" : ""
              }`}
            >
              {Number(d.slice(8))}
            </button>
          );
        })}
      </div>
      <div className="flex items-center justify-between text-[11px] text-zinc-500">
        <span className="flex items-center gap-1">
          0 %
          {[0, 20, 50, 80, 100].map((v) => (
            <span key={v} className={`size-3.5 rounded ${heat(v)}`} />
          ))}
          100 %
        </span>
        <span>rámeček = dnes</span>
      </div>
    </Card>
  );
}

function Matrix({ habits, end, today, onOpenDay }: { habits: HabitDays[]; end: string; today: string; onOpenDay: (d: string) => void }) {
  const days = daysBetween(addDays(end, -(MATRIX_DAYS - 1)), end);
  const rows = habits.filter((h) => days.some((d) => isActive(h, d)));
  const scroller = useRef<HTMLDivElement>(null);
  // On a narrow phone the newest days (today) stay in view; older ones are a swipe away
  useEffect(() => {
    if (scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth;
  }, [end]);
  if (!rows.length) return null;
  return (
    <Card className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Návyky × dny</h2>
        <span className="text-xs text-zinc-500">posledních {MATRIX_DAYS} dní</span>
      </div>
      <div ref={scroller} className="-mx-1 overflow-x-auto px-1">
        <table className="border-separate border-spacing-[2px]">
          <thead>
            <tr>
              <th />
              {days.map((d) => (
                <th key={d} className={`w-[14px] text-center text-[9px] font-normal ${d === today ? "text-zinc-100" : "text-zinc-500"}`}>
                  {WEEKDAYS_SHORT[weekdayIndex(d)].charAt(0).toUpperCase()}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.id}>
                <th scope="row" className="max-w-[88px] pr-1.5 text-left font-normal">
                  <span className="flex items-center gap-1.5 truncate text-xs text-zinc-300">
                    <SkillDot skill={h.skill} />
                    <span className="truncate">{h.title}</span>
                  </span>
                </th>
                {days.map((d) => {
                  const active = isActive(h, d);
                  const done = h.doneSet.has(d);
                  return (
                    <td key={d} className="p-0">
                      <button
                        disabled={!active}
                        onClick={() => onOpenDay(d)}
                        aria-label={`${h.title}, ${formatDayMonth(d)}: ${done ? "splněno" : "nesplněno"}`}
                        className={`block size-[14px] rounded-[4px] ${done ? "bg-emerald-500" : active ? "bg-zinc-800" : "bg-transparent"} ${
                          d === today ? "outline outline-1 outline-zinc-300" : ""
                        }`}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-zinc-500">zelená = splněno · tmavá = nesplněno · rámeček = dnes</p>
    </Card>
  );
}

function TrendChart({ habits, end }: { habits: HabitDays[]; end: string }) {
  const { series, ink, axis, tooltip } = useChartKit();
  const days = daysBetween(addDays(end, -(TREND_DAYS - 1)), end);
  const values = days.map((d) => {
    const r = routineDay(habits, d);
    return pct(r.done, r.scheduled);
  });
  const data = days.map((date, i) => {
    const window = values.slice(Math.max(0, i - 6), i + 1).filter((v): v is number => v !== null);
    return { date, pct: values[i], avg: window.length ? Math.round(window.reduce((a, b) => a + b, 0) / window.length) : null };
  });
  if (!values.some((v) => v !== null)) return null;
  return (
    <Card>
      <h2 className="mb-2 font-semibold">Plnění po dnech</h2>
      <Legend
        items={[
          { label: "Denní rutina (%)", color: series[2] },
          { label: "7denní průměr", color: ink.secondary, kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={170}>
        <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tickFormatter={(v) => `${v} %`} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => shortDate(String(d))}
            formatter={(v, name) => [`${formatNumber(Number(v))} %`, name === "pct" ? "Denní rutina" : "7denní průměr"]}
          />
          <Bar dataKey="pct" fill={series[2]} radius={[4, 4, 0, 0]} maxBarSize={12} isAnimationActive={false} />
          <Line dataKey="avg" stroke={ink.secondary} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </Card>
  );
}

function HabitRates({ habits, end }: { habits: HabitDays[]; end: string }) {
  const start = addDays(end, -(TREND_DAYS - 1));
  const rows = habits
    .map((h) => {
      const [done, scheduled] = completion(h, start, end);
      return { h, value: pct(done, scheduled) };
    })
    .filter((r): r is { h: HabitDays; value: number } => r.value !== null)
    .sort((a, b) => b.value - a.value);
  if (!rows.length) return null;
  // Bonus habits are optional by design, so they are never called out as the weak spot
  const weakest = rows.filter((r) => !r.h.is_bonus).at(-1);
  return (
    <Card className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Úspěšnost návyků</h2>
        <span className="text-xs text-zinc-500">{TREND_DAYS} dní bez dneška</span>
      </div>
      {rows.map(({ h, value }) => (
        <div key={h.id} className="grid grid-cols-[132px_minmax(0,1fr)_40px] items-center gap-2">
          <span className="flex min-w-0 items-center gap-1.5 text-[13px] text-zinc-300">
            <SkillDot skill={h.skill} />
            <span className="truncate">{h.title}</span>
          </span>
          <span className="h-2.5 overflow-hidden rounded-r bg-zinc-800">
            <span className="block h-full rounded-r bg-emerald-500" style={{ width: `${value}%` }} />
          </span>
          <span className="text-right text-[13px] tabular-nums">{value} %</span>
        </div>
      ))}
      {rows.length > 1 && weakest && weakest.value < 100 && (
        <p className="text-xs text-zinc-400">
          Nejvíc ti utíká <strong className="text-zinc-100">{weakest.h.title}</strong>.
        </p>
      )}
    </Card>
  );
}

function WeekdayPattern({ habits, end }: { habits: HabitDays[]; end: string }) {
  const sums = Array.from({ length: 7 }, () => [0, 0]);
  for (const d of daysBetween(addDays(end, -(PATTERN_WEEKS * 7 - 1)), end)) {
    const r = routineDay(habits, d);
    if (!r.scheduled) continue;
    sums[weekdayIndex(d)][0] += r.done / r.scheduled;
    sums[weekdayIndex(d)][1] += 1;
  }
  const values = sums.map(([total, count]) => (count ? Math.round((total / count) * 100) : null));
  const known = values.filter((v): v is number => v !== null);
  if (known.length < 2) return null;
  const weakest = values.indexOf(Math.min(...known));
  return (
    <Card className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Podle dne v týdnu</h2>
        <span className="text-xs text-zinc-500">průměr za {PATTERN_WEEKS} týdnů</span>
      </div>
      <div className="grid h-[124px] grid-cols-7 items-end gap-2.5 border-b border-zinc-700">
        {values.map((v, i) => (
          <div key={i} className="flex h-full flex-col items-center justify-end gap-1">
            <span className="text-[11px] text-zinc-300 tabular-nums">{v === null ? "–" : `${v} %`}</span>
            <span
              className={`w-full rounded-t ${i === weakest ? "bg-amber-400" : "bg-emerald-500/60"}`}
              style={{ height: `${((v ?? 0) / 100) * 96}px` }}
            />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-2.5">
        {WEEKDAYS_SHORT.map((w) => (
          <span key={w} className="text-center text-[11px] text-zinc-400 capitalize">
            {w}
          </span>
        ))}
      </div>
      <p className="text-xs text-zinc-400">
        Nejslabší den: <strong className="text-zinc-100">{WEEKDAYS_LONG[weakest]}</strong>
      </p>
    </Card>
  );
}

function WeeklyHistory({ habits, end }: { habits: HabitDays[]; end: string }) {
  const current = weekStart(end);
  const weeks = Array.from({ length: PATTERN_WEEKS }, (_, i) => addDays(current, -7 * (PATTERN_WEEKS - 1 - i)));
  return (
    <Card className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Týdenní úkoly</h2>
        <span className="text-xs text-zinc-500">posledních {PATTERN_WEEKS} týdnů</span>
      </div>
      {habits.map((h) => (
        <div key={h.id} className="flex items-center gap-2">
          <span className="flex min-w-0 flex-1 items-center gap-1.5 text-[13px] text-zinc-300">
            <SkillDot skill={h.skill} />
            <span className="truncate">{h.title}</span>
          </span>
          <span className="grid shrink-0 grid-cols-8 gap-1">
            {weeks.map((w) => {
              const active = w >= weekStart(h.start_date) && (h.archivedOn === null || w < h.archivedOn);
              const met = weekCount(h.doneSet, w) >= h.weekly_target;
              return (
                <span
                  key={w}
                  title={`Týden od ${formatDayMonth(w)}`}
                  className={`size-3.5 rounded-full border ${
                    met ? "border-emerald-500 bg-emerald-500" : !active ? "border-transparent" : w === current ? "border-zinc-400" : "border-zinc-700"
                  }`}
                />
              );
            })}
          </span>
          <span className="flex w-10 shrink-0 items-center justify-end gap-0.5 text-xs text-zinc-300 tabular-nums">
            <Flame size={13} className="text-amber-400" />
            {currentStreak(h, end)}
          </span>
        </div>
      ))}
      <p className="text-[11px] text-zinc-500">plný kroužek = splněno · poslední = tento týden · číslo = série týdnů</p>
    </Card>
  );
}
