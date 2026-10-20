import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Skill } from "../../api/rpg";
import { formatNumber } from "../../lib/format";
import { useChartKit } from "../charts/DashboardCharts";
import { Card } from "../Layout";

/** Fixed palette slot per skill (Síla shares Tělo's blue, Výživa / Domov / Disciplína / Mysl match the habit areas). */
const SLOT: Record<string, number> = { strength: 0, nutrition: 1, home: 2, discipline: 3, mind: 4, endurance: 6 };

export function SkillsCard({ skills }: { skills: Skill[] }) {
  const { series, ink, tooltip } = useChartKit();
  const data = skills.map((s) => ({ name: s.name, level: s.level }));
  return (
    <Card className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Vlastnosti</h2>
        <span className="text-xs text-zinc-500">level vlastnosti</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={data} outerRadius="72%" margin={{ top: 4, right: 24, bottom: 4, left: 24 }}>
          <PolarGrid stroke={ink.grid} />
          <PolarAngleAxis dataKey="name" tick={{ fill: ink.secondary, fontSize: 12 }} />
          <PolarRadiusAxis tick={false} axisLine={false} domain={[0, "dataMax"]} />
          <Tooltip {...tooltip} formatter={(v) => [`level ${v}`, "Dovednost"]} />
          <Radar dataKey="level" stroke={series[2]} strokeWidth={2} fill={series[2]} fillOpacity={0.25} isAnimationActive={false} />
        </RadarChart>
      </ResponsiveContainer>
      <div className="space-y-2.5">
        {skills.map((s) => {
          const progress = Math.max(0, Math.min(1, (s.xp - s.level_start_xp) / (s.next_level_xp - s.level_start_xp)));
          return (
            <div key={s.key} className={s.rusting ? "opacity-70" : ""}>
              <div className="flex items-center gap-2 text-sm">
                <span className="size-2 shrink-0 rounded-full" style={{ background: series[SLOT[s.key] ?? 0] }} />
                <span className="font-semibold">{s.name}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-zinc-500">{s.source}</span>
                {s.rusting && (
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${s.losing ? "bg-red-500/15 text-red-300" : "bg-amber-500/15 text-amber-300"}`}>
                    {s.losing ? "ztrácí XP" : "rezaví"} · {s.idle_days} dní
                  </span>
                )}
                <span className="shrink-0 font-semibold tabular-nums">Lv {s.level}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                <div className={`h-full rounded-full ${s.rusting ? "bg-zinc-500" : "bg-emerald-500"}`} style={{ width: `${progress * 100}%` }} />
              </div>
              <div className="mt-0.5 text-right text-[11px] text-zinc-500 tabular-nums">
                {formatNumber(s.xp)} / {formatNumber(s.next_level_xp)} XP
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-zinc-500">Dovednost bez XP 14 dní rezaví, od 21 dní ztrácí každý týden 10 % XP (ubere i celkový level).</p>
    </Card>
  );
}
