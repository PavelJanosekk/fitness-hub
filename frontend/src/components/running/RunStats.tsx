import { Check, TriangleAlert } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type RunStat, useRunStats } from "../../api/running";
import { addDays, formatDay, formatDayMonth, formatNumber, formatPace, isoDate } from "../../lib/format";
import { CalendarHeatmap, mondayOf } from "../charts/CalendarHeatmap";
import { Legend, useChartKit } from "../charts/DashboardCharts";
import { Card } from "../Layout";
import { Segmented } from "../ui";

const DAY_MS = 86_400_000;
const ts = (iso: string) => new Date(`${iso}T12:00:00`).getTime();
const plural = (n: number, one: string, few: string, many: string) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
const km = (value: number, digits = 1) => `${formatNumber(value, digits)} km`;

/** Easy runs for the efficiency trend: stream metrics, no heat, mostly Z1-Z2, at least 30 minutes. */
const EASY_MAX_ABOVE = 25;
const EASY_MIN_S = 30 * 60;
const isEasy = (r: RunStat) => !r.heat && r.pct_above_easy !== null && r.pct_above_easy <= EASY_MAX_ABOVE && r.moving_s >= EASY_MIN_S;

/** Běh → Grafy (E24): consistency, aerobic progress, intensity distribution and load. */
export function RunStats() {
  const stats = useRunStats();
  if (stats.isPending) return <p className="text-zinc-500">Načítám…</p>;
  if (!stats.data) return <Card><p className="text-zinc-400">Grafy se nepodařilo načíst. Zkus to znovu, až bude spojení.</p></Card>;
  const { runs } = stats.data;
  if (!runs.length) return <Card><p className="text-zinc-400">Běhy se objeví po propojení Stravy (Nastavení).</p></Card>;
  return (
    <div className="space-y-3">
      <Tiles runs={runs} />
      <RunHeatmap runs={runs} />
      <CumulativeCard runs={runs} />
      <PerformanceSection runs={runs} />
      <LoadSection runs={runs} />
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

function Tiles({ runs }: { runs: RunStat[] }) {
  const today = isoDate();
  const year = today.slice(0, 4);
  const yearKm = sum(runs.filter((r) => r.date.startsWith(year)).map((r) => r.distance_km));
  const yearAgo = addDays(today, -364);
  const count = runs.filter((r) => r.date >= yearAgo).length;
  // Weeks in a row with a run; the current week only counts once it has one
  const weeks = new Set(runs.map((r) => mondayOf(r.date)));
  let week = mondayOf(today);
  if (!weeks.has(week)) week = addDays(week, -7);
  let streak = 0;
  while (weeks.has(week)) (streak++, (week = addDays(week, -7)));
  return (
    <div className="grid grid-cols-3 gap-2">
      <Tile label={`Rok ${year}`} value={formatNumber(yearKm)} hint="km" />
      <Tile label="Běhy" value={String(count)} hint="za 12 měsíců" />
      <Tile label="Týdnů v řadě" value={String(streak)} hint="s během" />
    </div>
  );
}

function RunHeatmap({ runs }: { runs: RunStat[] }) {
  const byDay = new Map<string, RunStat[]>();
  for (const r of runs) byDay.set(r.date, [...(byDay.get(r.date) ?? []), r]);
  const values = new Map([...byDay].map(([d, rs]) => [d, sum(rs.map((r) => r.distance_km))]));
  const detail = (day: string) => {
    const rs = byDay.get(day);
    if (!rs) return `${formatDay(day)} · bez běhu`;
    const total = sum(rs.map((r) => r.distance_km));
    const pace = sum(rs.map((r) => r.moving_s)) / total;
    return `${formatDay(day)} · ${km(total)}${rs.length > 1 ? ` (${rs.length} běhy)` : ""} · ${formatPace(pace)}/km`;
  };
  return <CalendarHeatmap values={values} detail={detail} moreLabel="víc km" />;
}

/** Kilometres since 1 January, this year against last year (grey reference). */
function CumulativeCard({ runs }: { runs: RunStat[] }) {
  const { series, ink, axis, tooltip } = useChartKit();
  const today = isoDate();
  const year = Number(today.slice(0, 4));
  const dayOfYear = (iso: string) => Math.round((ts(iso) - ts(`${iso.slice(0, 4)}-01-01`)) / DAY_MS) + 1;
  const todayIndex = dayOfYear(today);
  const daily = (y: number) => {
    const perDay = new Array<number>(367).fill(0);
    for (const r of runs) if (r.date.startsWith(String(y))) perDay[dayOfYear(r.date)] += r.distance_km;
    return perDay;
  };
  const current = daily(year);
  const last = daily(year - 1);
  const data: { day: number; current: number | null; last: number }[] = [];
  let a = 0;
  let b = 0;
  for (let d = 1; d <= 366; d++) {
    a += current[d];
    b += last[d];
    data.push({ day: d, current: d <= todayIndex ? Math.round(a * 10) / 10 : null, last: Math.round(b * 10) / 10 });
  }
  const now = data[todayIndex - 1];
  const diff = (now.current ?? 0) - now.last;
  const monthStarts = Array.from({ length: 12 }, (_, m) => dayOfYear(`${year}-${String(m + 1).padStart(2, "0")}-01`));
  const monthLabel = (day: number) => ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"][monthStarts.indexOf(day)] ?? "";
  const dateOf = (day: number) => formatDayMonth(addDays(`${year}-01-01`, day - 1));
  return (
    <Card>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="font-semibold">Kilometry od 1. ledna</h2>
        {now.last > 0 && (
          <span className={`text-xs ${diff >= 0 ? "text-zinc-300" : "text-amber-300"}`}>
            {diff >= 0 ? "+" : "−"}
            {km(Math.abs(diff), 0)} proti loňsku
          </span>
        )}
      </div>
      <Legend
        items={[
          { label: String(year), color: series[2], kind: "line" },
          { label: String(year - 1), color: ink.muted, kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="day" type="number" domain={[1, 366]} ticks={monthStarts.filter((_, i) => i % 2 === 0)} tickFormatter={monthLabel} {...axis} />
          <YAxis tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => `k ${dateOf(Number(d))}`}
            formatter={(v, name) => [km(Number(v)), name === "current" ? String(year) : String(year - 1)]}
          />
          <Line dataKey="last" stroke={ink.muted} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey="current" stroke={series[2]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}

const RANGES = [
  ["6m", "6M"],
  ["1y", "1R"],
  ["all", "Vše"],
] as const;
type Range = (typeof RANGES)[number][0];
const RANGE_DAYS: Record<Range, number | null> = { "6m": 182, "1y": 365, all: null };

function PerformanceSection({ runs }: { runs: RunStat[] }) {
  const [range, setRange] = useState<Range>("1y");
  const limit = RANGE_DAYS[range];
  const since = limit ? addDays(isoDate(), -limit) : "";
  const shown = runs.filter((r) => r.date >= since);
  return (
    <>
      <div className="flex items-center justify-between gap-2 pt-2">
        <h2 className="text-lg font-semibold">Výkonnost</h2>
        <Segmented options={RANGES} value={range} onChange={setRange} />
      </div>
      <EfficiencyCard runs={shown} />
      <PaceHrCard runs={shown} />
      <VdotCard runs={shown} />
    </>
  );
}

const ROLLING_DAYS = 30;
const EF_MODES = [
  ["ef", "EF"],
  ["pace", "Tempo na easy tepu"],
] as const;

/** Efficiency factor (GAP metres per minute per heartbeat) of easy runs, with a 30-day rolling mean. */
function EfficiencyCard({ runs }: { runs: RunStat[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const [mode, setMode] = useState<(typeof EF_MODES)[number][0]>("ef");
  const value = (r: RunStat) => (mode === "ef" ? r.ef_gap : r.gap_at_easy_band_s_per_km);
  const easy = runs.filter((r) => isEasy(r) && value(r) !== null);
  const data = easy.map((r) => {
    const window = easy.filter((o) => o.date <= r.date && o.date > addDays(r.date, -ROLLING_DAYS)).map((o) => value(o)!);
    return { ...r, t: ts(r.date), v: value(r)!, avg: sum(window) / window.length };
  });
  const first = data[0]?.avg;
  const last = data.at(-1)?.avg;
  const better = first !== undefined && last !== undefined && (mode === "ef" ? last > first : last < first);
  const format = (v: number) => (mode === "ef" ? formatNumber(v, 2) : `${formatPace(v)}/km`);
  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Aerobní efektivita</h2>
        <Segmented options={EF_MODES} value={mode} onChange={setMode} />
      </div>
      {data.length < 2 ? (
        <p className="py-10 text-center text-sm text-zinc-500">V tomhle období málo klidných běhů s tepem.</p>
      ) : (
        <>
          <Legend
            items={[
              { label: "Klidný běh", color: series[0], kind: "dot" },
              { label: `Průměr ${ROLLING_DAYS} dní`, color: series[0], kind: "line" },
            ]}
          />
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid vertical={false} stroke={ink.grid} />
              <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => shortMonth(t)} minTickGap={28} {...axis} />
              <YAxis
                reversed={mode === "pace"}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => (mode === "ef" ? formatNumber(v, 2) : formatPace(v))}
                width={44}
                {...axis}
              />
              <Tooltip
                {...tooltip}
                labelFormatter={(_, p) => {
                  const r = p?.[0]?.payload as (RunStat & { avg: number }) | undefined;
                  return r ? `${formatDay(r.date)} · ${km(r.distance_km)}` : "";
                }}
                formatter={(v, name) => [format(Number(v)), name === "v" ? "Běh" : `Průměr ${ROLLING_DAYS} dní`]}
              />
              <Line dataKey="v" stroke={series[0]} strokeOpacity={0} dot={{ r: 3, fill: series[0], fillOpacity: 0.5, stroke: surface, strokeWidth: 1 }} activeDot={{ r: 5, fill: series[0], stroke: surface, strokeWidth: 2 }} isAnimationActive={false} />
              <Line dataKey="avg" stroke={series[0]} strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="text-xs text-zinc-400">
            {first !== undefined && last !== undefined && (
              <span className={better ? "text-zinc-200" : "text-amber-300"}>
                {format(first)} → {format(last)}
                {better ? " · zlepšení" : " · bez zlepšení"}.{" "}
              </span>
            )}
            {mode === "ef" ? "Metry za minutu na jeden úder (z GAP, kopce vyrovnané), vyšší je lepší." : "Tempo (GAP) v easy pásmu tepu, rychlejší je lepší."} Jen klidné běhy od 30 min bez
            horka ({data.length} {plural(data.length, "běh", "běhy", "běhů")}).
          </p>
        </>
      )}
    </Card>
  );
}

const shortMonth = (t: number) => {
  const iso = isoDate(new Date(t));
  return `${Number(iso.slice(5, 7))}/${iso.slice(2, 4)}`;
};

const AGE_BINS = [
  [365, "starší"],
  [180, "6–12 měs."],
  [90, "3–6 měs."],
  [0, "poslední 3 měs."],
] as const;
const AGE_OPACITY = [0.2, 0.4, 0.65, 1];

/** Pace (GAP) against steady HR per run; colour gets stronger for newer runs, so progress moves the cloud. */
function PaceHrCard({ runs }: { runs: RunStat[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const today = isoDate();
  const points = runs.filter((r) => !r.heat && r.hr_avg_steady !== null && r.gap_s_per_km !== null);
  const bin = (r: RunStat) => {
    const age = (ts(today) - ts(r.date)) / DAY_MS;
    return AGE_BINS.findIndex(([days], i) => age >= days || i === AGE_BINS.length - 1);
  };
  const groups = AGE_BINS.map((_, i) => points.filter((r) => bin(r) === i));
  const color = series[0];
  return (
    <Card className="space-y-2">
      <h2 className="font-semibold">Tempo vs. tep</h2>
      {points.length < 3 ? (
        <p className="py-10 text-center text-sm text-zinc-500">V tomhle období málo běhů s tepem.</p>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
            {AGE_BINS.map(([, label], i) =>
              groups[i].length ? (
                <span key={label} className="inline-flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: color, opacity: AGE_OPACITY[i] }} />
                  {label}
                </span>
              ) : null,
            )}
          </div>
          <ResponsiveContainer width="100%" height={230}>
            <ScatterChart margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={ink.grid} />
              <XAxis dataKey="hr_avg_steady" type="number" domain={["dataMin - 3", "dataMax + 3"]} tickFormatter={(v: number) => formatNumber(v)} name="Tep" unit=" bpm" {...axis} />
              <YAxis dataKey="gap_s_per_km" type="number" reversed domain={["dataMin - 10", "dataMax + 10"]} tickFormatter={(v: number) => formatPace(v)} width={44} {...axis} />
              <Tooltip
                {...tooltip}
                cursor={false}
                content={({ payload }) => {
                  const r = payload?.[0]?.payload as RunStat | undefined;
                  if (!r) return null;
                  return (
                    <div style={tooltip.contentStyle} className="px-3 py-2 text-xs">
                      <div style={tooltip.labelStyle}>
                        {formatDay(r.date)} · {km(r.distance_km)}
                      </div>
                      <div>
                        GAP {formatPace(r.gap_s_per_km)}/km · {formatNumber(r.hr_avg_steady)} bpm
                      </div>
                    </div>
                  );
                }}
              />
              {groups.map((group, i) => (
                <Scatter key={i} data={group} fill={color} fillOpacity={AGE_OPACITY[i]} stroke={surface} strokeWidth={1} isAnimationActive={false} />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-xs text-zinc-500">Každá tečka je běh: tep po prvních 10 minutách proti tempu GAP. Když se fyzička zlepšuje, nové tečky se posouvají doleva nahoru (rychleji na nižším tepu). Bez běhů v horku.</p>
        </>
      )}
    </Card>
  );
}

/** Best VDOT per month: the fastest effort of the month is the closest an everyday run gets to a race. */
function VdotCard({ runs }: { runs: RunStat[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const byMonth = new Map<string, RunStat>();
  for (const r of runs) {
    if (r.vdot === null) continue;
    const month = r.date.slice(0, 7);
    const best = byMonth.get(month);
    if (!best || r.vdot > best.vdot!) byMonth.set(month, r);
  }
  const data = [...byMonth].sort(([a], [b]) => a.localeCompare(b)).map(([month, r]) => ({ month, ...r }));
  const peak = data.reduce<(typeof data)[number] | null>((b, d) => (!b || d.vdot! > b.vdot! ? d : b), null);
  return (
    <Card className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-semibold">Odhad VDOT</h2>
        {peak && <span className="text-xs text-zinc-400">max {formatNumber(peak.vdot, 1)} ({formatDayMonth(peak.date)})</span>}
      </div>
      {data.length < 2 ? (
        <p className="py-10 text-center text-sm text-zinc-500">Málo dat.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid vertical={false} stroke={ink.grid} />
              <XAxis dataKey="month" tickFormatter={(m: string) => `${Number(m.slice(5))}/${m.slice(2, 4)}`} minTickGap={20} {...axis} />
              <YAxis domain={[(min: number) => Math.floor(min - 1), (max: number) => Math.ceil(max + 1)]} allowDecimals={false} width={44} {...axis} />
              <Tooltip
                {...tooltip}
                labelFormatter={(_, p) => {
                  const r = p?.[0]?.payload as RunStat | undefined;
                  return r ? `${formatDay(r.date)} · ${km(r.distance_km)} za ${formatPace(r.pace_s_per_km)}/km` : "";
                }}
                formatter={(v) => [formatNumber(Number(v), 1), "VDOT"]}
              />
              <Line dataKey="vdot" stroke={series[4]} strokeWidth={2} dot={{ r: 3, fill: series[4], stroke: surface, strokeWidth: 1 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <p className="text-xs text-zinc-500">Podle Danielse z nejrychlejšího běhu měsíce (vzdálenost a čas, ne tep). Měsíce bez závodu nebo tempového běhu ho podhodnocují.</p>
        </>
      )}
    </Card>
  );
}

const PERIODS = [
  [12, "12 týdnů"],
  [26, "26 týdnů"],
] as const;

type Week = { week: string; km: number; runs: number; longest: number; zones: [number, number, number] | null };

function weeksOf(runs: RunStat[], count: number): Week[] {
  const current = mondayOf(isoDate());
  return Array.from({ length: count }, (_, i) => {
    const week = addDays(current, -7 * (count - 1 - i));
    const end = addDays(week, 7);
    const rs = runs.filter((r) => r.date >= week && r.date < end);
    const z = rs.map((r) => r.zone_seconds).filter((z): z is Record<string, number> => z !== null);
    const easy = sum(z.map((s) => (s.z1 ?? 0) + (s.z2 ?? 0)));
    const grey = sum(z.map((s) => s.z3 ?? 0));
    const hard = sum(z.map((s) => (s.z4 ?? 0) + (s.z5 ?? 0)));
    const total = easy + grey + hard;
    return {
      week,
      km: Math.round(sum(rs.map((r) => r.distance_km)) * 10) / 10,
      runs: rs.length,
      longest: Math.max(0, ...rs.map((r) => r.distance_km)),
      zones: total ? [(100 * easy) / total, (100 * grey) / total, (100 * hard) / total] : null,
    };
  });
}

function LoadSection({ runs }: { runs: RunStat[] }) {
  const [period, setPeriod] = useState<(typeof PERIODS)[number][0]>(12);
  const weeks = weeksOf(runs, period);
  return (
    <>
      <div className="flex items-center justify-between gap-2 pt-2">
        <h2 className="text-lg font-semibold">Zátěž</h2>
        <Segmented options={PERIODS} value={period} onChange={setPeriod} />
      </div>
      <ZonesCard weeks={weeks} />
      <AcwrCard runs={runs} weeks={period} />
      <LongRunCard weeks={weeks} />
    </>
  );
}

const ZONE_GROUPS = [
  ["easy", "Z1–Z2 lehce"],
  ["grey", "Z3 šedá zóna"],
  ["hard", "Z4–Z5 tvrdě"],
] as const;

/** Share of running time per intensity each week (100 % stacked), against the 80/20 rule. */
function ZonesCard({ weeks }: { weeks: Week[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const colors = [series[2], series[3], series[1]];
  const rows = weeks.map((w) => ({ week: w.week, easy: w.zones?.[0] ?? null, grey: w.zones?.[1] ?? null, hard: w.zones?.[2] ?? null }));
  const known = weeks.filter((w) => w.zones);
  const all = known.length ? [0, 1, 2].map((i) => sum(known.map((w) => w.zones![i])) / known.length) : null;
  return (
    <Card className="space-y-2">
      <h2 className="font-semibold">Čas v zónách</h2>
      {!all ? (
        <p className="py-10 text-center text-sm text-zinc-500">V tomhle období žádné běhy s tepovými daty.</p>
      ) : (
        <>
          <Legend items={ZONE_GROUPS.map(([, label], i) => ({ label, color: colors[i] }))} />
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
              <CartesianGrid vertical={false} stroke={ink.grid} />
              <XAxis dataKey="week" tickFormatter={formatDayMonth} minTickGap={16} {...axis} />
              <YAxis domain={[0, 100]} ticks={[0, 20, 50, 80, 100]} tickFormatter={(v) => `${v} %`} width={44} {...axis} />
              <Tooltip
                {...tooltip}
                labelFormatter={(d) => `Týden od ${formatDayMonth(String(d))}`}
                formatter={(v, name) => [`${Math.round(Number(v))} %`, ZONE_GROUPS.find(([k]) => k === name)?.[1] ?? String(name)]}
              />
              <ReferenceLine y={80} stroke={ink.secondary} strokeDasharray="4 3" />
              {ZONE_GROUPS.map(([key], i) => (
                <Bar key={key} dataKey={key} stackId="zones" fill={colors[i]} stroke={surface} strokeWidth={1} maxBarSize={28} isAnimationActive={false} />
              ))}
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-zinc-400">
            Za období <span className="font-medium text-zinc-200">{Math.round(all[0])} % lehce</span> · {Math.round(all[1])} % Z3 · {Math.round(all[2])} % Z4–Z5. Čárkovaná čára je 80 % z
            pravidla 80/20. Jen běhy se streamem tepu ({known.length} z {weeks.filter((w) => w.runs).length} týdnů).
          </p>
        </>
      )}
    </Card>
  );
}

const ACWR_LOW = 0.8;
const ACWR_HIGH = 1.3;
const ACWR_RISK = 1.5;

/** Acute (7 days) vs chronic (28 days / 4) running km per day; the corridor 0.8-1.3 is the safe range. */
function AcwrCard({ runs, weeks }: { runs: RunStat[]; weeks: number }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const today = isoDate();
  const perDay = new Map<string, number>();
  for (const r of runs) perDay.set(r.date, (perDay.get(r.date) ?? 0) + r.distance_km);
  const window = (end: string, days: number) => {
    let total = 0;
    for (let i = 0; i < days; i++) total += perDay.get(addDays(end, -i)) ?? 0;
    return total;
  };
  const data = Array.from({ length: weeks * 7 }, (_, i) => {
    const day = addDays(today, -(weeks * 7 - 1 - i));
    const acute = window(day, 7);
    const chronic = window(day, 28) / 4;
    return { day, t: ts(day), acute, chronic, ratio: chronic > 0 ? Math.round((acute / chronic) * 100) / 100 : null };
  });
  const latest = data.at(-1)!;
  const status =
    latest.ratio === null
      ? null
      : latest.ratio > ACWR_RISK
        ? { text: "riziko: objem roste moc rychle", warn: true }
        : latest.ratio > ACWR_HIGH
          ? { text: "nad bezpečným pásmem", warn: true }
          : latest.ratio < ACWR_LOW
            ? { text: "pod pásmem: odlehčení / ztráta formy", warn: false }
            : { text: "v bezpečném pásmu", warn: false };
  const top = Math.max(2, Math.ceil(Math.max(...data.map((d) => d.ratio ?? 0)) * 2) / 2);
  return (
    <Card className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-semibold">Akutní / chronická zátěž</h2>
        {latest.ratio !== null && <span className="text-xl font-bold tabular-nums">{formatNumber(latest.ratio, 2)}</span>}
      </div>
      {status && (
        <p className={`flex items-center gap-1 text-xs ${status.warn ? "text-amber-300" : "text-zinc-400"}`}>
          {status.warn ? <TriangleAlert size={13} /> : <Check size={13} />} Dnes {status.text} ({km(latest.acute)} za 7 dní, Ø {km(latest.chronic)} týdně za 4 týdny)
        </p>
      )}
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => formatDayMonth(isoDate(new Date(t)))} minTickGap={28} {...axis} />
          <YAxis domain={[0, top]} ticks={[0, 0.5, ACWR_LOW, ACWR_HIGH, ACWR_RISK, ...(top > 2 ? [top] : [2])]} tickFormatter={(v: number) => formatNumber(v, 1)} width={44} {...axis} />
          <ReferenceArea y1={ACWR_LOW} y2={ACWR_HIGH} fill={series[2]} fillOpacity={0.12} stroke="none" />
          <ReferenceLine y={ACWR_RISK} stroke={series[1]} strokeDasharray="4 3" />
          <Tooltip
            {...tooltip}
            labelFormatter={(_, p) => {
              const d = p?.[0]?.payload as (typeof data)[number] | undefined;
              return d ? `${formatDay(d.day)} · 7 dní ${km(d.acute)}, Ø ${km(d.chronic)}/týden` : "";
            }}
            formatter={(v) => [formatNumber(Number(v), 2), "Poměr"]}
          />
          <Line dataKey="ratio" stroke={series[0]} strokeWidth={2} dot={false} activeDot={{ r: 5, fill: series[0], stroke: surface, strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="text-xs text-zinc-500">Kilometry za posledních 7 dní děleno průměrným týdnem za posledních 28 dní. Zelené pásmo 0,8–1,3 je bezpečné, nad čárkovanou 1,5 rychle roste riziko zranění.</p>
    </Card>
  );
}

const LONG_SHARE_MAX = 0.5;

/** Weekly km (bars) and the week's longest run (line); flags weeks where the long run carries over half the week. */
function LongRunCard({ weeks }: { weeks: Week[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const data = weeks.map((w) => ({ ...w, longest: w.runs ? Math.round(w.longest * 10) / 10 : null }));
  const heavy = weeks.filter((w) => w.km > 0 && w.longest / w.km > LONG_SHARE_MAX && w.runs >= 3);
  return (
    <Card className="space-y-2">
      <h2 className="font-semibold">Long run vs. týdenní objem</h2>
      <Legend
        items={[
          { label: "Týden (km)", color: series[2] },
          { label: "Nejdelší běh", color: series[0], kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="week" tickFormatter={formatDayMonth} minTickGap={16} {...axis} />
          <YAxis tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => `Týden od ${formatDayMonth(String(d))}`}
            formatter={(v, name, item) => {
              const w = item.payload as Week;
              return name === "km"
                ? [`${km(Number(v))} · ${w.runs} ${plural(w.runs, "běh", "běhy", "běhů")}`, "Týden"]
                : [`${km(Number(v))} · ${Math.round((w.longest / w.km) * 100)} % týdne`, "Nejdelší běh"];
            }}
          />
          <Bar dataKey="km" fill={series[2]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          <Line dataKey="longest" stroke={series[0]} strokeWidth={2} dot={{ r: 3, fill: series[0], stroke: surface, strokeWidth: 1 }} connectNulls={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className={`flex items-center gap-1 text-xs ${heavy.length ? "text-amber-300" : "text-zinc-400"}`}>
        {heavy.length ? <TriangleAlert size={13} /> : <Check size={13} />}
        {heavy.length
          ? `${heavy.length} ${plural(heavy.length, "týden", "týdny", "týdnů")} se 3+ běhy, kde long run tvořil přes polovinu objemu (${heavy.map((w) => formatDayMonth(w.week)).join(", ")}).`
          : "Long run nikde netvořil přes polovinu týdne (u týdnů se 3+ běhy)."}
      </p>
    </Card>
  );
}
