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
import { MUSCLE_GROUPS, useChartColors } from "./palette";

/** The current theme's chart colors plus the axis and tooltip props every chart shares. */
function useChartKit() {
  const colors = useChartColors();
  const { ink } = colors;
  return {
    series: colors.series,
    ink,
    surface: colors.surface,
    axis: { tick: { fill: ink.muted, fontSize: 11 }, tickLine: false, axisLine: false } as const,
    tooltip: {
      contentStyle: { background: colors.tooltip, border: `1px solid ${ink.grid}`, borderRadius: 12, color: ink.primary },
      labelStyle: { color: ink.secondary },
      cursor: { stroke: ink.muted, strokeWidth: 1, fill: colors.cursor },
    },
  };
}
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
  const { series, ink, surface, axis, tooltip } = useChartKit();
  return (
    <>
      <Legend
        items={[
          { label: "Ranní váha", color: series[0], kind: "dot" },
          { label: "7denní průměr", color: series[0], kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis domain={["dataMin - 1", "dataMax + 1"]} tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => shortDate(String(d))}
            formatter={(v, name) => [`${formatNumber(Number(v), 1)} kg`, name === "weight_kg" ? "Váha" : "7denní průměr"]}
          />
          <Line
            dataKey="weight_kg"
            stroke={series[0]}
            strokeOpacity={0}
            dot={{ r: 4, fill: series[0], fillOpacity: 0.55, stroke: surface, strokeWidth: 2 }}
            activeDot={{ r: 6, fill: series[0], stroke: surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
          <Line dataKey="weight_7d_avg" stroke={series[0]} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}

/** Daily intake (bars) and its 7-day average over logged days (line). */
export function KcalChart({ data }: { data: MetricDay[] }) {
  const { series, ink, axis, tooltip } = useChartKit();
  return (
    <>
      <Legend
        items={[
          { label: "Příjem (kcal)", color: series[1] },
          { label: "7denní průměr", color: ink.secondary, kind: "line" },
        ]}
      />
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => shortDate(String(d))}
            formatter={(v, name) => [`${formatNumber(Number(v))} kcal`, name === "calories_in" ? "Příjem" : "7denní průměr"]}
          />
          <Bar dataKey="calories_in" fill={series[1]} radius={[4, 4, 0, 0]} maxBarSize={14} isAnimationActive={false} />
          <Line
            dataKey="calories_in_7d_avg"
            stroke={ink.secondary}
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
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const rows = weeks.map((w) => ({ week: w.week_start, ...w.gym_sets }));
  const present = MUSCLE_GROUPS.filter(([key]) => weeks.some((w) => w.gym_sets[key]));
  return (
    <>
      <Legend items={present.map(([key, label]) => ({ label, color: series[MUSCLE_GROUPS.findIndex(([k]) => k === key)] }))} />
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
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
              fill={series[MUSCLE_GROUPS.findIndex(([k]) => k === key)]}
              stroke={surface}
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
  const { series, ink, axis, tooltip } = useChartKit();
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={weeks} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
        <CartesianGrid vertical={false} stroke={ink.grid} />
        <XAxis dataKey="week_start" tickFormatter={shortDate} minTickGap={16} {...axis} />
        <YAxis width={44} {...axis} />
        <Tooltip
          {...tooltip}
          labelFormatter={(d) => `Týden od ${shortDate(String(d))}`}
          formatter={(v) => [`${formatNumber(Number(v), 1)} km`, "Běh"]}
        />
        <Bar dataKey="run_km" fill={series[2]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export type RunVolumeWeek = { week_start: string; run_km: number; runs: number; plan_km: number | null };

/** Weekly running volume (bars) against the plan's upper km bound (dots) where the plan has one. */
export function RunVolumeChart({ weeks }: { weeks: RunVolumeWeek[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const hasPlan = weeks.some((w) => w.plan_km !== null);
  return (
    <>
      <Legend
        items={[
          { label: "Odběhnuto (km)", color: series[2] },
          ...(hasPlan ? [{ label: "Plán (horní hranice)", color: ink.secondary, kind: "dot" as const }] : []),
        ]}
      />
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={weeks} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
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
          <Bar dataKey="run_km" fill={series[2]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          <Line
            dataKey="plan_km"
            stroke={ink.secondary}
            strokeOpacity={0}
            dot={{ r: 4, fill: ink.secondary, stroke: surface, strokeWidth: 2 }}
            activeDot={{ r: 5, fill: ink.secondary, stroke: surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}
