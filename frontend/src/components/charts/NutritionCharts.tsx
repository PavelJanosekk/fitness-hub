import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useProfile } from "../../api/nutrition";
import type { MetricDay } from "../../api/types";
import { formatDayMonth, formatNumber } from "../../lib/format";
import { Card } from "../Layout";
import { KcalChart, Legend, useChartKit } from "./DashboardCharts";

const MACROS = [
  ["protein_kcal", "Bílkoviny", 4, "protein_g"],
  ["carbs_kcal", "Sacharidy", 4, "carbs_g"],
  ["fat_kcal", "Tuky", 9, "fat_g"],
] as const;

const mean = (values: (number | null)[]) => {
  const known = values.filter((v): v is number => v !== null);
  return known.length ? known.reduce((a, b) => a + b, 0) / known.length : null;
};

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="p-3!">
      <div className="text-xs text-zinc-400">{label}</div>
      <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-zinc-500">{hint}</div>}
    </Card>
  );
}

/** Přehled → Strava: averages, intake, macro split and protein against the target. */
export function NutritionCharts({ days }: { days: MetricDay[] }) {
  const profile = useProfile().data;
  const logged = days.filter((d) => d.calories_in !== null);
  const kcal = mean(logged.map((d) => d.calories_in));
  const protein = mean(logged.map((d) => d.protein_g));
  const target = profile?.kcal_target ?? null;
  if (!logged.length) return <Card><p className="py-6 text-center text-sm text-zinc-500">V tomhle období žádný zapsaný příjem.</p></Card>;
  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        <Tile label="Ø příjem" value={formatNumber(kcal)} hint={target ? `kcal · cíl ${formatNumber(target)}` : "kcal za den"} />
        <Tile label="Ø bílkoviny" value={protein === null ? "–" : `${formatNumber(protein)} g`} hint={profile?.protein_target_g ? `cíl ${formatNumber(profile.protein_target_g)} g` : "za den"} />
        <Tile label="Zapsáno" value={`${logged.length}`} hint={`z ${days.length} dní`} />
      </div>
      <Card>
        <h2 className="mb-3 font-semibold">Příjem energie</h2>
        <KcalChart data={days} />
      </Card>
      <MacroCard days={days} />
      <ProteinCard days={days} target={profile?.protein_target_g ?? null} />
    </>
  );
}

/** Energy from protein / carbs / fat per day (4 / 4 / 9 kcal per g), stacked. */
function MacroCard({ days }: { days: MetricDay[] }) {
  const { series, ink, surface, axis, tooltip } = useChartKit();
  const colors = [series[0], series[3], series[1]];
  const rows = days.map((d) => ({
    date: d.date,
    ...Object.fromEntries(MACROS.map(([key, , factor, field]) => [key, d[field] === null ? null : Math.round(d[field]! * factor)])),
  }));
  const totals = MACROS.map(([, , factor, field]) => days.reduce((n, d) => n + (d[field] ?? 0) * factor, 0));
  const all = totals.reduce((a, b) => a + b, 0);
  return (
    <Card>
      <h2 className="mb-2 font-semibold">Makroživiny</h2>
      <Legend items={MACROS.map(([, label], i) => ({ label: all ? `${label} ${Math.round((100 * totals[i]) / all)} %` : label, color: colors[i] }))} />
      <ResponsiveContainer width="100%" height={190}>
        <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="date" tickFormatter={formatDayMonth} minTickGap={24} {...axis} />
          <YAxis tickFormatter={(v) => formatNumber(v)} width={54} {...axis} />
          <Tooltip
            {...tooltip}
            labelFormatter={(d) => formatDayMonth(String(d))}
            formatter={(v, name) => {
              const macro = MACROS.find(([k]) => k === name)!;
              return [`${formatNumber(Number(v))} kcal · ${formatNumber(Number(v) / macro[2])} g`, macro[1]];
            }}
          />
          {MACROS.map(([key], i) => (
            <Bar
              key={key}
              dataKey={key}
              stackId="macros"
              fill={colors[i]}
              stroke={surface}
              strokeWidth={1}
              radius={i === MACROS.length - 1 ? [4, 4, 0, 0] : undefined}
              maxBarSize={14}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 text-xs text-zinc-500">Podíly za období počítané z energie (bílkoviny a sacharidy 4 kcal/g, tuky 9 kcal/g).</p>
    </Card>
  );
}

function ProteinCard({ days, target }: { days: MetricDay[]; target: number | null }) {
  const { series, ink, axis, tooltip } = useChartKit();
  const logged = days.filter((d) => d.protein_g !== null);
  const hit = target ? logged.filter((d) => d.protein_g! >= target).length : null;
  return (
    <Card>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="font-semibold">Bílkoviny za den</h2>
        {hit !== null && (
          <span className="text-xs text-zinc-400">
            cíl splněn {hit} z {logged.length} dní
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={days} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={ink.grid} />
          <XAxis dataKey="date" tickFormatter={formatDayMonth} minTickGap={24} {...axis} />
          <YAxis tickFormatter={(v) => formatNumber(v)} width={44} {...axis} />
          <Tooltip {...tooltip} labelFormatter={(d) => formatDayMonth(String(d))} formatter={(v) => [`${formatNumber(Number(v))} g`, "Bílkoviny"]} />
          {target && <ReferenceLine y={target} stroke={ink.secondary} strokeDasharray="4 3" />}
          <Bar dataKey="protein_g" fill={series[0]} radius={[4, 4, 0, 0]} maxBarSize={14} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      {target && <p className="mt-1 text-xs text-zinc-500">Čárkovaně cíl {formatNumber(target)} g (Jídlo → Cíle).</p>}
    </Card>
  );
}
