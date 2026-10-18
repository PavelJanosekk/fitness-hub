import { ChevronLeft, ChevronRight, Flame, PartyPopper, Pencil, Plus } from "lucide-react";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { HabitRow, Ring, useHabitDays, useToggleHabit } from "../components/habits/parts";
import { Card, PageHeader } from "../components/Layout";
import { Button, Segmented } from "../components/ui";
import { addDays, formatDayMonth, isoDate } from "../lib/format";
import {
  type HabitDays,
  isActive,
  pct,
  plural,
  ROUTINE_WEEK_PCT,
  routineDay,
  routineWeekPct,
  routineWeekStreak,
  WEEKDAYS_LONG,
  WEEKDAYS_SHORT,
  weekDays,
  weekStart,
  weekdayIndex,
} from "../lib/habits";

// The month view carries the charts (recharts), the editor is rarely opened: both load on demand
const MonthView = lazy(() => import("../components/habits/MonthView").then((m) => ({ default: m.MonthView })));
const HabitEditList = lazy(() => import("../components/habits/HabitEditList").then((m) => ({ default: m.HabitEditList })));
const HabitSheet = lazy(() => import("../components/habits/HabitSheet").then((m) => ({ default: m.HabitSheet })));

const VIEWS = [
  ["day", "Den"],
  ["month", "Měsíc"],
] as const;

export function Habits() {
  const [params, setParams] = useSearchParams();
  const today = isoDate();
  const view = params.get("v") === "month" ? "month" : "day";
  const day = params.get("d") && params.get("d")! <= today ? params.get("d")! : today;
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const { board, habits, active } = useHabitDays();

  const open = (next: { v?: "day" | "month"; d?: string }) => {
    const v = next.v ?? view;
    const d = next.d ?? day;
    setParams({ ...(v === "month" ? { v } : {}), ...(d !== today ? { d } : {}) }, { replace: true });
  };

  return (
    <>
      <PageHeader
        title={editing ? "Upravit rutiny" : "Rutina"}
        action={
          editing ? (
            <button onClick={() => setEditing(false)} className="px-1 py-2 font-semibold text-emerald-400">
              Hotovo
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <button onClick={() => setEditing(true)} aria-label="Upravit rutiny" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
                <Pencil size={20} />
              </button>
              <button onClick={() => setAdding(true)} aria-label="Přidat rutinu" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
                <Plus size={22} />
              </button>
            </div>
          )
        }
      />

      {board.isPending ? (
        <p className="text-zinc-500">Načítám…</p>
      ) : board.isError && !board.data ? (
        <Card>
          <p className="text-zinc-400">Rutinu se nepodařilo načíst. Zkus to znovu, až bude spojení.</p>
        </Card>
      ) : editing ? (
        <Suspense fallback={<p className="text-zinc-500">Načítám…</p>}>
          <HabitEditList habits={habits} />
        </Suspense>
      ) : active.length === 0 ? (
        <Card className="space-y-3 text-center">
          <p className="text-zinc-400">Zatím tu nemáš žádné rutiny.</p>
          <Button onClick={() => setAdding(true)}>Přidat první rutinu</Button>
        </Card>
      ) : (
        <div className="space-y-3">
          <Segmented options={VIEWS} value={view} onChange={(v) => open({ v })} />
          {view === "day" ? (
            <DayView habits={habits} day={day} today={today} onDay={(d) => open({ d })} />
          ) : (
            <Suspense fallback={<p className="text-zinc-500">Načítám…</p>}>
              <MonthView habits={habits} today={today} onOpenDay={(d) => open({ v: "day", d })} />
            </Suspense>
          )}
        </div>
      )}

      {adding && (
        <Suspense fallback={null}>
          <HabitSheet onClose={() => setAdding(false)} />
        </Suspense>
      )}
    </>
  );
}

function DayView({ habits, day, today, onDay }: { habits: HabitDays[]; day: string; today: string; onDay: (day: string) => void }) {
  const toggle = useToggleHabit();
  const shown = habits.filter((h) => isActive(h, day) || (h.archived_at === null && day >= weekStart(h.start_date) && h.frequency === "weekly"));
  const daily = shown.filter((h) => h.frequency === "daily" && !h.is_bonus);
  const bonus = shown.filter((h) => h.frequency === "daily" && h.is_bonus);
  const weekly = shown.filter((h) => h.frequency === "weekly");
  const swipe = useRef<{ x: number; y: number } | null>(null);

  const go = (offset: number) => {
    const next = addDays(day, offset);
    if (next <= today) onDay(next);
  };

  return (
    <div
      className="space-y-3"
      onTouchStart={(e) => (swipe.current = { x: e.touches[0].clientX, y: e.touches[0].clientY })}
      onTouchEnd={(e) => {
        const start = swipe.current;
        swipe.current = null;
        if (!start) return;
        const dx = e.changedTouches[0].clientX - start.x;
        const dy = e.changedTouches[0].clientY - start.y;
        if (Math.abs(dx) > 70 && Math.abs(dy) < 40) go(dx < 0 ? 1 : -1);
      }}
    >
      <div className="flex items-center justify-between">
        <button onClick={() => go(-1)} aria-label="Předchozí den" className="rounded-full p-2.5 text-zinc-400 active:bg-zinc-800">
          <ChevronLeft size={20} />
        </button>
        <button onClick={() => onDay(today)} className="flex flex-col items-center">
          <span className="font-semibold">{day === today ? "Dnes" : capitalize(WEEKDAYS_LONG[weekdayIndex(day)])}</span>
          <span className="text-xs text-zinc-500">
            {WEEKDAYS_LONG[weekdayIndex(day)]} {formatDayMonth(day)}
          </span>
        </button>
        <button
          onClick={() => go(1)}
          disabled={day >= today}
          aria-label="Další den"
          className="rounded-full p-2.5 text-zinc-400 active:bg-zinc-800 disabled:opacity-30"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      <WeekStrip habits={habits} day={day} today={today} onDay={onDay} />
      <DayHero habits={habits} day={day} today={today} />

      {daily.length > 0 && (
        <Section title="Denní" count={`${daily.filter((h) => h.doneSet.has(day)).length} / ${daily.length}`}>
          {daily.map((h) => (
            <HabitRow key={h.id} h={h} day={day} onToggle={() => toggle(h, day)} />
          ))}
        </Section>
      )}
      {bonus.length > 0 && (
        <Section title="Bonus" count="nepočítá se do maxima">
          {bonus.map((h) => (
            <HabitRow key={h.id} h={h} day={day} onToggle={() => toggle(h, day)} />
          ))}
        </Section>
      )}
      {weekly.length > 0 && <WeeklySection habits={weekly} day={day} onToggle={(h) => toggle(h, day)} />}
    </div>
  );
}

function WeekStrip({ habits, day, today, onDay }: { habits: HabitDays[]; day: string; today: string; onDay: (day: string) => void }) {
  return (
    <div className="grid grid-cols-7 gap-1">
      {weekDays(weekStart(day)).map((d) => {
        const r = routineDay(habits, d);
        const value = pct(r.done, r.scheduled) ?? 0;
        const selected = d === day;
        return (
          <button
            key={d}
            onClick={() => onDay(d)}
            disabled={d > today}
            aria-pressed={selected}
            aria-label={`${WEEKDAYS_LONG[weekdayIndex(d)]} ${formatDayMonth(d)}, ${r.done} z ${r.scheduled}`}
            className={`flex flex-col items-center gap-1.5 rounded-2xl border py-2 disabled:opacity-35 ${
              selected ? "border-emerald-700 bg-emerald-950/60" : "border-transparent"
            }`}
          >
            <span className="text-[11px] text-zinc-400 capitalize">{WEEKDAYS_SHORT[weekdayIndex(d)]}</span>
            <Ring value={d > today ? 0 : value} size={34} stroke={4}>
              <span className={`text-xs font-semibold tabular-nums ${d === today ? "text-emerald-300" : ""}`}>{Number(d.slice(8))}</span>
            </Ring>
          </button>
        );
      })}
    </div>
  );
}

function DayHero({ habits, day, today }: { habits: HabitDays[]; day: string; today: string }) {
  const r = routineDay(habits, day);
  const value = pct(r.done, r.scheduled) ?? 0;
  const left = r.scheduled - r.done;
  const perfect = r.scheduled > 0 && left === 0;
  const weekValue = routineWeekPct(habits, weekStart(day), day < today ? day : today);
  const streak = routineWeekStreak(habits, day < today ? day : today);
  const celebrate = useCelebration(perfect && day === today);

  return (
    <Card className="flex items-center gap-4">
      <Ring value={value} size={96} stroke={8}>
        <span className="text-2xl font-bold tracking-tight tabular-nums">{value} %</span>
        <span className="text-xs text-zinc-400 tabular-nums">
          {r.done} / {r.scheduled}
        </span>
      </Ring>
      <div className="min-w-0 flex-1 space-y-2">
        <div className={`flex items-center gap-1.5 text-[17px] font-semibold ${celebrate ? "animate-bounce text-emerald-300" : ""}`}>
          {perfect && <PartyPopper size={18} className="text-emerald-400" />}
          {perfect ? "Perfektní den" : left === 1 ? "Zbývá 1 úkol" : left < 5 ? `Zbývají ${left} úkoly` : `Zbývá ${left} úkolů`}
        </div>
        <div className="text-[13px] text-zinc-400">
          Body {r.points} z {r.maxPoints}
          {r.bonus > 0 && <span className="text-amber-300"> · bonus +{r.bonus}</span>}
        </div>
        <div className="h-px bg-zinc-800" />
        <div className="flex items-center gap-1.5 text-[13px] text-zinc-300">
          <Flame size={16} className={streak ? "text-amber-400" : "text-zinc-500"} />
          Týdenní série{" "}
          <strong className="text-zinc-100">
            {streak} {plural(streak, "týden", "týdny", "týdnů")}
          </strong>
        </div>
        <div className="text-xs text-zinc-500">
          Tento týden {weekValue === null ? "–" : `${Math.round(weekValue)} %`} · počítá se od {ROUTINE_WEEK_PCT} %
        </div>
      </div>
    </Card>
  );
}

function WeeklySection({ habits, day, onToggle }: { habits: HabitDays[]; day: string; onToggle: (h: HabitDays) => void }) {
  const monday = weekStart(day);
  const met = habits.filter((h) => weekDays(monday).filter((d) => h.doneSet.has(d)).length >= h.weekly_target).length;
  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between px-0.5 pt-1">
        <h2 className="font-semibold">Tento týden</h2>
        <span className="text-[13px] text-zinc-400 tabular-nums">
          {met} / {habits.length} · {formatDayMonth(monday)}–{formatDayMonth(addDays(monday, 6))}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-300" style={{ width: `${(met / habits.length) * 100}%` }} />
      </div>
      <div className="ui-card divide-y divide-zinc-800 overflow-hidden">
        {habits.map((h) => (
          <HabitRow key={h.id} h={h} day={day} onToggle={() => onToggle(h)} />
        ))}
      </div>
    </section>
  );
}

function Section({ title, count, children }: { title: string; count: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between px-0.5 pt-1">
        <h2 className="font-semibold">{title}</h2>
        <span className="text-[13px] text-zinc-400 tabular-nums">{count}</span>
      </div>
      <div className="ui-card divide-y divide-zinc-800 overflow-hidden">{children}</div>
    </section>
  );
}

/** True for a moment after `active` turns on (a perfect day reached by a tick, not on every visit). */
function useCelebration(active: boolean) {
  const [on, setOn] = useState(false);
  const previous = useRef(active);
  useEffect(() => {
    if (active && !previous.current) {
      setOn(true);
      const timer = setTimeout(() => setOn(false), 2400);
      previous.current = active;
      return () => clearTimeout(timer);
    }
    previous.current = active;
  }, [active]);
  return on;
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

