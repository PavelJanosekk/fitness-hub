import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import type { MetricDay } from "../../api/types";
import { addDays, formatDayMonth, formatNumber, isoDate } from "../../lib/format";
import { Card } from "../Layout";
import { Segmented } from "../ui";
import { mondayOf } from "./CalendarHeatmap";
import { useChartKit } from "./DashboardCharts";

const VIEWS = [
  ["week", "Týden"],
  ["month", "Měsíc"],
  ["year", "Rok"],
] as const;
type View = (typeof VIEWS)[number][0];
const AGGS = [
  ["avg", "Ø za den"],
  ["total", "Celkem"],
] as const;
type Agg = (typeof AGGS)[number][0];
const WEEKDAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];
const MONTHS = ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"];
const monthName = new Intl.DateTimeFormat("cs-CZ", { month: "long", year: "numeric" });

/** Daily steps since 1 January of last year; under "metrics" so a new sync refreshes it. */
function useStepsHistory() {
  const today = isoDate();
  const start = `${Number(today.slice(0, 4)) - 1}-01-01`;
  return useQuery({
    queryKey: ["metrics", "steps-history", start],
    queryFn: () => api<MetricDay[]>(`/api/metrics?start_date=${start}&end_date=${today}`),
    select: (days) => new Map(days.filter((d) => d.steps !== null).map((d) => [d.date, d.steps!])),
  });
}

const shiftMonth = (iso: string, months: number) => {
  const [y, m] = iso.split("-").map(Number);
  const index = y * 12 + m - 1 + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}-01`;
};
const daysOf = (start: string, end: string) => {
  const out: string[] = [];
  for (let d = start; d <= end; d = addDays(d, 1)) out.push(d);
  return out;
};

type Bucket = { label: string; title: string; value: number | null; days: number; total: number };

function bucket(label: string, title: string, days: string[], steps: Map<string, number>, agg: Agg): Bucket {
  const known = days.map((d) => steps.get(d)).filter((v): v is number => v !== undefined);
  const total = known.reduce((a, b) => a + b, 0);
  return { label, title, days: known.length, total, value: known.length ? (agg === "total" ? total : Math.round(total / known.length)) : null };
}

/** Steps per day of a week, per week of a month, or per month of a year; average per day or the total. */
export function StepsCard() {
  const history = useStepsHistory();
  const { series, ink, axis, tooltip } = useChartKit();
  const [view, setView] = useState<View>("week");
  const [agg, setAgg] = useState<Agg>("avg");
  const [offset, setOffset] = useState(0);
  const steps = history.data ?? new Map<string, number>();
  const today = isoDate();
  const first = [...steps.keys()].sort()[0] ?? today;

  let buckets: Bucket[] = [];
  let period = "";
  let periodDays: string[] = [];
  let earliest = 0; // the lowest offset that still has data
  if (view === "week") {
    const start = addDays(mondayOf(today), 7 * offset);
    periodDays = daysOf(start, addDays(start, 6));
    buckets = periodDays.map((d, i) => bucket(WEEKDAYS[i], `${WEEKDAYS[i]} ${formatDayMonth(d)}`, [d], steps, "total"));
    period = `${formatDayMonth(start)} – ${formatDayMonth(addDays(start, 6))}`;
    earliest = -Math.floor((new Date(`${mondayOf(today)}T12:00:00`).getTime() - new Date(`${mondayOf(first)}T12:00:00`).getTime()) / (7 * 86_400_000));
  } else if (view === "month") {
    const start = shiftMonth(`${today.slice(0, 7)}-01`, offset);
    const end = addDays(shiftMonth(start, 1), -1);
    periodDays = daysOf(start, end);
    for (let w = mondayOf(start); w <= end; w = addDays(w, 7)) {
      const days = daysOf(w < start ? start : w, addDays(w, 6) > end ? end : addDays(w, 6));
      const label = `${Number(days[0].slice(8))}.–${Number(days.at(-1)!.slice(8))}.`;
      buckets.push(bucket(label, `${formatDayMonth(days[0])} – ${formatDayMonth(days.at(-1)!)}`, days, steps, agg));
    }
    period = monthName.format(new Date(`${start}T12:00:00`));
    earliest = (Number(first.slice(0, 4)) - Number(today.slice(0, 4))) * 12 + Number(first.slice(5, 7)) - Number(today.slice(5, 7));
  } else {
    const year = Number(today.slice(0, 4)) + offset;
    periodDays = daysOf(`${year}-01-01`, `${year}-12-31`);
    buckets = MONTHS.map((m, i) => {
      const start = `${year}-${String(i + 1).padStart(2, "0")}-01`;
      return bucket(m, monthName.format(new Date(`${start}T12:00:00`)), daysOf(start, addDays(shiftMonth(start, 1), -1)), steps, agg);
    });
    period = String(year);
    earliest = Number(first.slice(0, 4)) - Number(today.slice(0, 4));
  }
  const summary = bucket("", "", periodDays, steps, "total");
  const average = summary.days ? Math.round(summary.total / summary.days) : null;
  const showsAvg = view !== "week" && agg === "avg";
  const reference = view === "week" ? average : showsAvg ? average : null;
  const changeView = (v: View) => (setView(v), setOffset(0));

  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Kroky</h2>
        <Segmented options={VIEWS} value={view} onChange={changeView} />
      </div>
      <div className="flex items-center justify-between gap-2">
        <button onClick={() => setOffset(offset - 1)} disabled={offset <= Math.min(0, earliest)} aria-label="Předchozí" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800 disabled:opacity-30">
          <ChevronLeft size={20} />
        </button>
        <div className="text-center">
          <div className="font-semibold capitalize">{period}</div>
          <div className="text-xs text-zinc-400 tabular-nums">
            {summary.days ? `${formatNumber(summary.total)} celkem · Ø ${formatNumber(average)} za den` : "bez dat"}
          </div>
        </div>
        <button onClick={() => setOffset(offset + 1)} disabled={offset >= 0} aria-label="Další" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800 disabled:opacity-30">
          <ChevronRight size={20} />
        </button>
      </div>
      {history.isPending ? (
        <p className="py-16 text-center text-sm text-zinc-500">Načítám…</p>
      ) : (
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={buckets} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
            <CartesianGrid vertical={false} stroke={ink.grid} />
            <XAxis dataKey="label" interval={0} {...axis} />
            <YAxis tickFormatter={(v: number) => (v >= 1000 ? `${formatNumber(v / 1000, v % 1000 ? 1 : 0)} k` : String(v))} width={40} {...axis} />
            <Tooltip
              {...tooltip}
              labelFormatter={(_, p) => (p?.[0]?.payload as Bucket | undefined)?.title ?? ""}
              formatter={(v, _, item) => {
                const b = item.payload as Bucket;
                if (view === "week") return [formatNumber(Number(v)), "Kroky"];
                return [`${formatNumber(Number(v))}${agg === "avg" ? " za den" : ""} · ${b.days} ${b.days === 1 ? "den" : b.days < 5 ? "dny" : "dní"} s daty`, agg === "avg" ? "Průměr" : "Celkem"];
              }}
            />
            {reference !== null && <ReferenceLine y={reference} stroke={ink.secondary} strokeDasharray="4 3" />}
            <Bar dataKey="value" fill={series[3]} radius={[4, 4, 0, 0]} maxBarSize={32} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      )}
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-zinc-500">{reference !== null ? "čárkovaně průměr za den" : ""}</span>
        {view !== "week" && <Segmented options={AGGS} value={agg} onChange={setAgg} />}
      </div>
    </Card>
  );
}
