import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MetricDay, WeekStats } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { INK, MUSCLE_GROUPS, SERIES } from "./palette";

const SURFACE = "#111113";
const axis = { tick: { fill: INK.muted, fontSize: 11 }, tickLine: false, axisLine: false } as const;
const tooltip = {
  contentStyle: { background: "#18181b", border: `1px solid ${INK.grid}`, borderRadius: 12, color: INK.primary },
  labelStyle: { color: INK.secondary },
  cursor: { stroke: INK.muted, strokeWidth: 1, fill: "rgba(255,255,255,0.04)" },
} as const;
const shortDate = (iso: string) => `${Number(iso.slice(8, 10))}.${Number(iso.slice(5, 7))}.`;

export function Legend({ items }: { items: { label: string; color: string; kind?: "dot" | "line" | "bar" }[] }) {
  return (
    <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
      {items.map(({ label, color, kind = "bar" }) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <span
            className={kind === "line" ? "h-0.5 w-4 rounded" : kind === "dot" ? "size-2 rounded-full" : "size-2.5 rounded-sm"}
            style={{ background: color }}
          />
          {label}
        </span>
      ))}
    </div>
  );
}

/** Daily weight (dots) and its 7-day average (line): one measure, one axis. */
export function WeightChart({ data }: { data: MetricDay[] }) {
  return (
    <>
      <Legend
        items={[
          { label: "Ranní váha", color: SERIES[0], kind: "dot" },
          { label: "7denní průměr", color: SERIES[0], kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={INK.grid} />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis domain={["dataMin - 1", "dataMax + 1"]} tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => shortDate(String(d))}
            formatter={(v, name) => [`${formatNumber(Number(v), 1)} kg`, name === "weight_kg" ? "Váha" : "7denní průměr"]}
          />
          <Line
            dataKey="weight_kg"
            stroke={SERIES[0]}
            strokeOpacity={0}
            dot={{ r: 4, fill: SERIES[0], fillOpacity: 0.55, stroke: SURFACE, strokeWidth: 2 }}
            activeDot={{ r: 6, fill: SERIES[0], stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive={false}
          />
          <Line dataKey="weight_7d_avg" stroke={SERIES[0]} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}

/** Daily intake (bars) and its 7-day average over logged days (line). */
export function KcalChart({ data }: { data: MetricDay[] }) {
  return (
    <>
      <Legend
        items={[
          { label: "Příjem (kcal)", color: SERIES[1] },
          { label: "7denní průměr", color: INK.secondary, kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={INK.grid} />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => shortDate(String(d))}
            formatter={(v, name) => [`${formatNumber(Number(v))} kcal`, name === "calories_in" ? "Příjem" : "7denní průměr"]}
          />
          <Bar dataKey="calories_in" fill={SERIES[1]} radius={[4, 4, 0, 0]} maxBarSize={14} isAnimationActive={false} />
          <Line
            dataKey="calories_in_7d_avg"
            stroke={INK.secondary}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}

/** Working sets per muscle group per week, stacked in the fixed group order. */
export function WeeklyGymChart({ weeks }: { weeks: WeekStats[] }) {
  const rows = weeks.map((w) => ({ week: w.week_start, ...w.gym_sets }));
  const present = MUSCLE_GROUPS.filter(([key]) => weeks.some((w) => w.gym_sets[key]));
  return (
    <>
      <Legend items={present.map(([key, label]) => ({ label, color: SERIES[MUSCLE_GROUPS.findIndex(([k]) => k === key)] }))} />
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={INK.grid} />
          <XAxis dataKey="week" tickFormatter={shortDate} minTickGap={16} {...axis} />
          <YAxis allowDecimals={false} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => `Týden od ${shortDate(String(d))}`}
            formatter={(v, name) => [`${v} sérií`, MUSCLE_GROUPS.find(([k]) => k === name)?.[1] ?? String(name)]}
          />
          {present.map(([key]) => (
            <Bar
              key={key}
              dataKey={key}
              stackId="sets"
              fill={SERIES[MUSCLE_GROUPS.findIndex(([k]) => k === key)]}
              stroke={SURFACE}
              strokeWidth={1}
              maxBarSize={28}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </>
  );
}

export function WeeklyRunChart({ weeks }: { weeks: WeekStats[] }) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={weeks} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
        <CartesianGrid vertical={false} stroke={INK.grid} />
        <XAxis dataKey="week_start" tickFormatter={shortDate} minTickGap={16} {...axis} />
        <YAxis width={44} {...axis} />
        <Tooltip
          {...tooltip}
          labelFormatter={(d) => `Týden od ${shortDate(String(d))}`}
          formatter={(v) => [`${formatNumber(Number(v), 1)} km`, "Běh"]}
        />
        <Bar dataKey="run_km" fill={SERIES[2]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export type RunVolumeWeek = { week_start: string; run_km: number; runs: number; plan_km: number | null };

/** Weekly running volume (bars) against the plan's upper km bound (dots) where the plan has one. */
export function RunVolumeChart({ weeks }: { weeks: RunVolumeWeek[] }) {
  const hasPlan = weeks.some((w) => w.plan_km !== null);
  return (
    <>
      <Legend
        items={[
          { label: "Odběhnuto (km)", color: SERIES[2] },
          ...(hasPlan ? [{ label: "Plán (horní hranice)", color: INK.secondary, kind: "dot" as const }] : []),
        ]}
      />
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={weeks} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={INK.grid} />
          <XAxis dataKey="week_start" tickFormatter={shortDate} minTickGap={16} {...axis} />
          <YAxis width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => `Týden od ${shortDate(String(d))}`}
            formatter={(v, name, item) =>
              name === "run_km"
                ? [`${formatNumber(Number(v), 1)} km · ${item.payload.runs} běhů`, "Odběhnuto"]
                : [`${formatNumber(Number(v))} km`, "Plán"]
            }
          />
          <Bar dataKey="run_km" fill={SERIES[2]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          <Line
            dataKey="plan_km"
            stroke={INK.secondary}
            strokeOpacity={0}
            dot={{ r: 4, fill: INK.secondary, stroke: SURFACE, strokeWidth: 2 }}
            activeDot={{ r: 5, fill: INK.secondary, stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}
