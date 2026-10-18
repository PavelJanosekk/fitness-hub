import { Check, ChevronDown, Search, TriangleAlert, Trophy } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type ProgressionSession, type StatsDay, type StatsExercise, type StatsWeek, useGymStats, useProgression } from "../../api/gym";
import { addDays, formatDay, formatDayMonth, formatNumber, isoDate } from "../../lib/format";
import { CalendarHeatmap, mondayOf as monday } from "../charts/CalendarHeatmap";
import { Legend, useChartKit } from "../charts/DashboardCharts";
import { MUSCLE_GROUPS } from "../charts/palette";
import { Card } from "../Layout";
import { Segmented, Sheet } from "../ui";

const DAY_MS = 86_400_000;
const groupColor = (series: readonly string[], key: string) => series[MUSCLE_GROUPS.findIndex(([k]) => k === key)];
const groupLabel = (key: string) => MUSCLE_GROUPS.find(([k]) => k === key)?.[1] ?? key;
const plural = (n: number, one: string, few: string, many: string) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
const kg = (value: number | null | undefined, digits = 1) => (value === null || value === undefined ? "–" : `${formatNumber(value, value % 1 ? digits : 0)} kg`);

/** Gym → Grafy (E23): consistency, progression of one exercise, volume per muscle group, balance. */
export function GymStats() {
  const stats = useGymStats();
  if (stats.isPending) return <p className="text-zinc-500">Načítám…</p>;
  if (!stats.data) return <Card><p className="text-zinc-400">Grafy se nepodařilo načíst. Zkus to znovu, až bude spojení.</p></Card>;
  const { days, weeks, exercises } = stats.data;
  return (
    <div className="space-y-3">
      <Tiles days={days} weeks={weeks} />
      <ActivityHeatmap days={days} />
      {exercises.length > 0 && <ProgressionCard exercises={exercises} />}
      <MuscleSection weeks={weeks} />
    </div>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="p-3!">
      <div className="text-xs text-zinc-400">{label}</div>
      <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-zinc-500">{hint}</div>}
    </Card>
  );
}

function Tiles({ days, weeks }: { days: StatsDay[]; weeks: StatsWeek[] }) {
  const today = isoDate();
  const yearAgo = addDays(today, -364);
  const workouts = days.filter((d) => d.date >= yearAgo).reduce((n, d) => n + d.workouts, 0);
  // Weeks in a row with a workout; the current week only counts once it has one (it is still open)
  const trained = new Set(days.map((d) => monday(d.date)));
  let week = monday(today);
  if (!trained.has(week)) week = addDays(week, -7);
  let streak = 0;
  while (trained.has(week)) (streak++, (week = addDays(week, -7)));
  const closed = weeks.slice(-13, -1);
  const perWeek = closed.length ? closed.reduce((n, w) => n + w.workouts, 0) / closed.length : null;
  return (
    <div className="grid grid-cols-3 gap-2">
      <Tile label="Tréninky" value={String(workouts)} hint="za 12 měsíců" />
      <Tile label="Týdnů v řadě" value={String(streak)} hint="s tréninkem" />
      <Tile label="Za týden" value={perWeek === null ? "–" : formatNumber(perWeek, 1)} hint="Ø 12 týdnů" />
    </div>
  );
}

function ActivityHeatmap({ days }: { days: StatsDay[] }) {
  const byDate = new Map(days.map((d) => [d.date, d]));
  const detail = (day: string) => {
    const info = byDate.get(day);
    if (!info) return `${formatDay(day)} · bez tréninku`;
    return `${formatDay(day)} · ${info.workouts > 1 ? `${info.workouts} tréninky · ` : ""}${info.sets} sérií · ${formatNumber(info.volume_kg)} kg`;
  };
  return <CalendarHeatmap values={new Map(days.map((d) => [d.date, d.sets]))} detail={detail} moreLabel="víc sérií" />;
}

const RANGES = [
  ["3m", "3M"],
  ["6m", "6M"],
  ["1y", "1R"],
  ["all", "Vše"],
] as const;
type Range = (typeof RANGES)[number][0];
const RANGE_DAYS: Record<Range, number | null> = { "3m": 91, "6m": 182, "1y": 365, all: null };
const EXERCISE_KEY = "fitness-hub-stats-exercise";

function storedExercise(): number | null {
  try {
    const value = Number(localStorage.getItem(EXERCISE_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function ProgressionCard({ exercises }: { exercises: StatsExercise[] }) {
  const [exerciseId, setExerciseId] = useState(() => {
    const stored = storedExercise();
    return exercises.some((e) => e.exercise_id === stored) ? stored! : exercises[0].exercise_id;
  });
  const [range, setRange] = useState<Range>("6m");
  const [picking, setPicking] = useState(false);
  const progression = useProgression(exerciseId);
  const exercise = exercises.find((e) => e.exercise_id === exerciseId);

  const pick = (id: number) => {
    setExerciseId(id);
    setPicking(false);
    try {
      localStorage.setItem(EXERCISE_KEY, String(id));
    } catch {
      // per-device convenience only
    }
  };

  const limit = RANGE_DAYS[range];
  const since = limit ? addDays(isoDate(), -limit) : "";
  const sessions = (progression.data?.sessions ?? []).filter((s) => s.date >= since);
  const weighted = progression.data?.weighted ?? true;

  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Progres cviku</h2>
        <Segmented options={RANGES} value={range} onChange={setRange} />
      </div>
      <button onClick={() => setPicking(true)} className="flex min-h-11 w-full items-center gap-2 rounded-xl bg-zinc-800 px-3 text-left active:bg-zinc-700">
        <span className="min-w-0 flex-1 truncate font-medium">{exercise?.name ?? "Vyber cvik"}</span>
        <span className="shrink-0 text-xs text-zinc-400">{exercise && `${exercise.sessions}×`}</span>
        <ChevronDown size={18} className="shrink-0 text-zinc-400" />
      </button>
      {progression.isPending ? (
        <p className="py-16 text-center text-sm text-zinc-500">Načítám…</p>
      ) : sessions.length === 0 ? (
        <p className="py-16 text-center text-sm text-zinc-500">V tomhle období žádný trénink tohoto cviku.</p>
      ) : (
        <>
          <ProgressionChart sessions={sessions} weighted={weighted} />
          <ProgressionSummary sessions={sessions} weighted={weighted} />
        </>
      )}
      {picking && <StatsExercisePicker exercises={exercises} onPick={pick} onClose={() => setPicking(false)} />}
    </Card>
  );
}

type Point = ProgressionSession & { ts: number };

function ProgressionChart({ sessions, weighted }: { sessions: ProgressionSession[]; weighted: boolean }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const data: Point[] = sessions.map((s) => ({ ...s, ts: new Date(`${s.date}T12:00:00`).getTime() }));
  const lines = weighted
    ? ([
        ["e1rm", "Odhad 1RM", series[0], "e1rm"],
        ["max_weight", "Nejtěžší série", series[1], "weight"],
      ] as const)
    : ([["max_reps", "Nejvíc opakování", series[0], "reps"]] as const);
  const span = data.length > 1 ? data[data.length - 1].ts - data[0].ts : DAY_MS;
  return (
    <>
      <Legend
        items={[
          ...lines.map(([, label, color]) => ({ label, color, kind: "line" as const })),
          { label: "Rekord", color: ink.secondary, kind: "dot" as const },
        ]}
      />
      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={["dataMin - 43200000", "dataMax + 43200000"]}
            tickFormatter={(ts: number) => {
              const iso = isoDate(new Date(ts));
              return span > 300 * DAY_MS ? `${Number(iso.slice(5, 7))}/${iso.slice(2, 4)}` : formatDayMonth(iso);
            }}
            minTickGap={28}
            {...axis}
          />
          <YAxis
            domain={[(min: number) => Math.max(0, Math.floor(min * 0.95)), (max: number) => Math.ceil(max * 1.03)]}
            allowDecimals={false}
            tickFormatter={(v) => formatNumber(v)}
            width={44}
            {...axis}
          />
          <Tooltip
            {...tooltip}
            labelFormatter={(_, payload) => {
              const p = payload?.[0]?.payload as Point | undefined;
              return p ? `${formatDay(p.date)} · ${p.sets} ${plural(p.sets, "série", "série", "sérií")}` : "";
            }}
            formatter={(v, name, item) => {
              const p = item.payload as Point;
              if (name === "e1rm") return [`${kg(Number(v))} (${p.e1rm_set})`, "Odhad 1RM"];
              if (name === "max_weight") return [`${kg(Number(v))} × ${p.max_weight_reps}`, "Nejtěžší série"];
              return [`${v}`, "Opakování"];
            }}
          />
          {lines.map(([key, , color, prKind]) => (
            <Line
              key={key}
              dataKey={key}
              stroke={color}
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
              dot={(props: { cx?: number; cy?: number; payload?: Point; index?: number }) => {
                const { cx, cy, payload, index } = props;
                if (cx === undefined || cy === undefined || payload?.[key] === null) return <g key={index} />;
                const record = payload?.pr.includes(prKind);
                return record ? (
                  <circle key={index} cx={cx} cy={cy} r={5} fill={color} stroke={surface} strokeWidth={2} />
                ) : (
                  <circle key={index} cx={cx} cy={cy} r={2.5} fill={color} />
                );
              }}
              activeDot={{ r: 6, fill: color, stroke: surface, strokeWidth: 2 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

function ProgressionSummary({ sessions, weighted }: { sessions: ProgressionSession[]; weighted: boolean }) {
  const records = sessions.filter((s) => s.pr.length > 0).length;
  const measure = (s: ProgressionSession) => (weighted ? s.e1rm : s.max_reps);
  const known = sessions.filter((s) => measure(s) !== null);
  const best = known.reduce<ProgressionSession | null>((b, s) => (!b || measure(s)! > measure(b)! ? s : b), null);
  const change = known.length > 1 ? measure(known[known.length - 1])! - measure(known[0])! : null;
  const unit = weighted ? " kg" : " opak.";
  return (
    <div className="grid grid-cols-3 gap-2 text-center">
      <div className="rounded-xl bg-zinc-800/60 px-2 py-2">
        <div className="text-[11px] text-zinc-400">{weighted ? "Nejlepší 1RM" : "Nejvíc opak."}</div>
        <div className="font-semibold tabular-nums">{best ? `${formatNumber(measure(best), 1)}${unit}` : "–"}</div>
        <div className="truncate text-[11px] text-zinc-500">{best && (weighted ? `${best.e1rm_set} · ${formatDayMonth(best.date)}` : formatDayMonth(best.date))}</div>
      </div>
      <div className="rounded-xl bg-zinc-800/60 px-2 py-2">
        <div className="text-[11px] text-zinc-400">Změna</div>
        <div className="font-semibold tabular-nums">{change === null ? "–" : `${change > 0 ? "+" : ""}${formatNumber(change, 1)}${unit}`}</div>
        <div className="text-[11px] text-zinc-500">za období</div>
      </div>
      <div className="rounded-xl bg-zinc-800/60 px-2 py-2">
        <div className="text-[11px] text-zinc-400">Rekordy</div>
        <div className="flex items-center justify-center gap-1 font-semibold tabular-nums">
          <Trophy size={14} className="text-amber-300" /> {records}
        </div>
        <div className="text-[11px] text-zinc-500">
          {sessions.length} {plural(sessions.length, "trénink", "tréninky", "tréninků")}
        </div>
      </div>
    </div>
  );
}

function StatsExercisePicker({ exercises, onPick, onClose }: { exercises: StatsExercise[]; onPick: (id: number) => void; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLocaleLowerCase("cs");
  const shown = exercises.filter((e) => e.name.toLocaleLowerCase("cs").includes(needle));
  return (
    <Sheet title="Vyber cvik" onClose={onClose} tall>
      <label className="mb-2 flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3">
        <Search size={18} className="text-zinc-500" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 w-full bg-transparent outline-none" />
      </label>
      <ul className="divide-y divide-zinc-800">
        {shown.map((e) => (
          <li key={e.exercise_id}>
            <button onClick={() => onPick(e.exercise_id)} className="flex w-full items-center gap-2 py-2.5 text-left active:bg-zinc-800/50">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{e.name}</span>
                <span className="text-xs text-zinc-400">
                  {groupLabel(e.muscle_group)} · naposledy {formatDayMonth(e.last_date)}
                </span>
              </span>
              <span className="shrink-0 text-sm tabular-nums text-zinc-400">{e.sessions}×</span>
            </button>
          </li>
        ))}
      </ul>
      {shown.length === 0 && <p className="py-4 text-sm text-zinc-500">Nic nenalezeno.</p>}
    </Sheet>
  );
}

const PERIODS = [
  [4, "4 týdny"],
  [12, "12 týdnů"],
  [26, "26 týdnů"],
] as const;

/** Weekly volume, distribution and antagonist balance share one period control. */
function MuscleSection({ weeks }: { weeks: StatsWeek[] }) {
  const [period, setPeriod] = useState<(typeof PERIODS)[number][0]>(12);
  const shown = weeks.slice(-period);
  return (
    <>
      <div className="flex items-center justify-between gap-2 pt-2">
        <h2 className="text-lg font-semibold">Partie</h2>
        <Segmented options={PERIODS} value={period} onChange={setPeriod} />
      </div>
      <WeeklyVolumeCard weeks={shown} />
      <DistributionCard weeks={shown} />
      <BalanceCard weeks={shown} />
    </>
  );
}

const METRICS = [
  ["sets", "Série"],
  ["volume_kg", "Objem"],
] as const;

function WeeklyVolumeCard({ weeks }: { weeks: StatsWeek[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const [metric, setMetric] = useState<(typeof METRICS)[number][0]>("sets");
  const rows = weeks.map((w) => ({ week: w.week_start, ...w[metric] }));
  const present = MUSCLE_GROUPS.filter(([key]) => weeks.some((w) => w[metric][key]));
  const format = (v: number) => (metric === "sets" ? `${v} sérií` : `${formatNumber(v)} kg`);
  return (
    <Card>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="font-semibold">Objem po týdnech</h2>
        <Segmented options={METRICS} value={metric} onChange={setMetric} />
      </div>
      <Legend items={present.map(([key, label]) => ({ label, color: groupColor(series, key) }))} />
      <ResponsiveContainer width="100%" height={210}>
        <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="week" tickFormatter={formatDayMonth} minTickGap={16} {...axis} />
          <YAxis
            allowDecimals={false}
            tickFormatter={(v: number) => (metric === "sets" ? String(v) : v >= 1000 ? `${formatNumber(v / 1000)} t` : formatNumber(v))}
            width={44}
            {...axis}
          />
          <Tooltip {...tooltip} labelFormatter={(d) => `Týden od ${formatDayMonth(String(d))}`} formatter={(v, name) => [format(Number(v)), groupLabel(String(name))]} />
          {present.map(([key], i) => (
            <Bar
              key={key}
              dataKey={key}
              stackId="volume"
              fill={groupColor(series, key)}
              stroke={surface}
              strokeWidth={1}
              radius={i === present.length - 1 ? [4, 4, 0, 0] : undefined}
              maxBarSize={28}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

function DistributionCard({ weeks }: { weeks: StatsWeek[] }) {
  const { series, surface, tooltip } = useChartKit();
  const totals = MUSCLE_GROUPS.map(([key, label]) => ({ key, label, sets: weeks.reduce((n, w) => n + (w.sets[key] ?? 0), 0) }));
  const all = totals.reduce((n, t) => n + t.sets, 0);
  const data = totals.filter((t) => t.sets > 0);
  return (
    <Card>
      <h2 className="mb-2 font-semibold">Rozložení partií</h2>
      {all === 0 ? (
        <p className="py-6 text-sm text-zinc-500">V tomhle období žádné pracovní série.</p>
      ) : (
        <div className="grid grid-cols-[140px_1fr] items-center gap-3">
          <div className="relative h-[140px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="sets" nameKey="label" innerRadius="62%" outerRadius="100%" stroke={surface} strokeWidth={2} startAngle={90} endAngle={-270} isAnimationActive={false}>
                  {data.map((d) => (
                    <Cell key={d.key} fill={groupColor(series, d.key)} />
                  ))}
                </Pie>
                <Tooltip {...tooltip} formatter={(v, name) => [`${v} sérií · ${Math.round((Number(v) / all) * 100)} %`, String(name)]} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-bold tabular-nums">{all}</span>
              <span className="text-[11px] text-zinc-400">sérií</span>
            </div>
          </div>
          <ul className="space-y-1 text-sm">
            {totals.map((t) => (
              <li key={t.key} className={`flex items-center gap-2 ${t.sets ? "" : "text-zinc-500"}`}>
                <span className="size-2.5 shrink-0 rounded-sm" style={{ background: groupColor(series, t.key) }} />
                <span className="min-w-0 flex-1 truncate">{t.label}</span>
                <span className="tabular-nums text-zinc-400">{t.sets}</span>
                <span className="w-10 text-right font-medium tabular-nums">{Math.round((t.sets / all) * 100)} %</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

// Same order as the backend's MUSCLES: index i faces i + 4 on the radar
const MUSCLES = [
  ["chest", "Hrudník"],
  ["front_delts", "Přední ramena"],
  ["biceps", "Biceps"],
  ["quads", "Kvadricepsy"],
  ["back", "Záda"],
  ["rear_delts", "Zadní ramena"],
  ["triceps", "Triceps"],
  ["hamstrings", "Hamstringy"],
] as const;
const BALANCED = 1.5; // a pair is "vyrovnaný" while the bigger side has at most 1.5× the sets of the smaller

function BalanceCard({ weeks }: { weeks: StatsWeek[] }) {
  const { series, ink, tooltip } = useChartKit();
  const sets = useMemo(
    () => Object.fromEntries(MUSCLES.map(([key]) => [key, weeks.reduce((n, w) => n + (w.muscles[key] ?? 0), 0)])) as Record<string, number>,
    [weeks],
  );
  const classified = Object.values(sets).reduce((a, b) => a + b, 0);
  const unclassified = weeks.reduce((n, w) => n + w.unclassified_sets, 0);
  const data = MUSCLES.map(([key, label]) => ({ key, label, sets: sets[key] }));
  const pairs = MUSCLES.slice(0, 4).map((a, i) => [a, MUSCLES[i + 4]] as const);
  return (
    <Card className="space-y-2">
      <h2 className="font-semibold">Vyváženost antagonistů</h2>
      {classified === 0 ? (
        <p className="py-6 text-sm text-zinc-500">V tomhle období žádné série do protichůdných svalů.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={data} outerRadius="72%" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <PolarGrid stroke={ink.grid} />
              <PolarAngleAxis dataKey="label" tick={{ fill: ink.secondary, fontSize: 11 }} />
              <Radar dataKey="sets" stroke={series[0]} strokeWidth={2} fill={series[0]} fillOpacity={0.25} dot={{ r: 3, fill: series[0] }} isAnimationActive={false} />
              <Tooltip {...tooltip} formatter={(v) => [`${v} sérií`, "Pracovní série"]} />
            </RadarChart>
          </ResponsiveContainer>
          <ul className="space-y-2">
            {pairs.map(([[aKey, aLabel], [bKey, bLabel]]) => {
              const a = sets[aKey];
              const b = sets[bKey];
              const share = a + b ? a / (a + b) : 0.5;
              const ratio = Math.max(a, b) / Math.max(1, Math.min(a, b));
              const balanced = a + b > 0 && Math.min(a, b) > 0 && ratio <= BALANCED;
              // A pair can be "balanced" at 3 : 3 sets in half a year: say that it is barely trained
              const sparse = a + b > 0 && a + b < weeks.length;
              return (
                <li key={aKey} className="text-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <span>
                      {aLabel} <span className="font-semibold tabular-nums">{a}</span>
                    </span>
                    <span>
                      <span className="font-semibold tabular-nums">{b}</span> {bLabel}
                    </span>
                  </div>
                  <div className="my-1 flex h-2 overflow-hidden rounded-full bg-zinc-800">
                    {a + b > 0 && (
                      <>
                        <div className="h-full" style={{ width: `${share * 100}%`, background: series[0] }} />
                        <div className="h-full w-0.5 shrink-0 bg-zinc-950" />
                        <div className="h-full flex-1" style={{ background: ink.muted }} />
                      </>
                    )}
                  </div>
                  <div className={`flex items-center gap-1 text-xs ${balanced && !sparse ? "text-zinc-400" : "text-amber-300"}`}>
                    {balanced && !sparse ? <Check size={13} /> : <TriangleAlert size={13} />}
                    {a + b === 0
                      ? "netrénováno"
                      : sparse
                        ? `skoro netrénováno (${a + b} ${plural(a + b, "série", "série", "sérií")} za ${weeks.length} ${plural(weeks.length, "týden", "týdny", "týdnů")})`
                      : balanced
                        ? `vyrovnané (${formatNumber(ratio, 1)} : 1)`
                        : a && b
                          ? `převažuje ${(a > b ? aLabel : bLabel).toLowerCase()}, ${formatNumber(ratio, 1)}× víc sérií`
                          : `trénuješ jen ${(a > b ? aLabel : bLabel).toLowerCase()}`}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="text-[11px] text-zinc-500">
            Svaly se odvozují z názvu cviku. {unclassified > 0 && `${unclassified} ${plural(unclassified, "série", "série", "sérií")} (boky ramen, lýtka, shrugy…) do žádného páru nepatří. `}Core se nepočítá.
          </p>
        </>
      )}
    </Card>
  );
}
