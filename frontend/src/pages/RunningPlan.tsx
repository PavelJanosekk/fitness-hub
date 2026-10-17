import { Flag, Thermometer } from "lucide-react";
import { type Activity, type PlanWeek, useActivities, useKb, useRunWeeks, zones } from "../api/running";
import { Card, PageHeader } from "../components/Layout";
import { formatDay, formatNumber, formatPace, isoDate } from "../lib/format";

const RUN_TYPES = new Set(["Run", "TrailRun", "VirtualRun"]);
const daysUntil = (iso: string) => Math.round((new Date(`${iso}T12:00:00`).getTime() - new Date(`${isoDate()}T12:00:00`).getTime()) / 86_400_000);

export function RunningPlan() {
  const kb = useKb();
  const weeks = useRunWeeks();
  const activities = useActivities();
  const today = isoDate();
  const current = weeks.data?.find((w) => w.week_start <= today && today <= w.week_end);
  const upcoming = (kb.data?.races ?? []).filter((r) => r.date >= today);
  const runs = (activities.data ?? []).filter((a) => RUN_TYPES.has(a.activity_type));

  return (
    <>
      <PageHeader title="Běh" />
      <div className="space-y-3">
        {upcoming.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            {upcoming.map((race) => (
              <Card key={race.name} className={race.is_goal_race ? "border-emerald-700" : ""}>
                <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <Flag size={14} /> {formatDay(race.date)}
                </div>
                <div className="mt-1 text-3xl font-semibold tabular-nums">{daysUntil(race.date)}</div>
                <div className="text-xs text-zinc-400">dní · {race.name}</div>
              </Card>
            ))}
          </div>
        )}

        {current && (
          <Card>
            <div className="mb-1 text-xs text-zinc-500">{current.block}</div>
            <h2 className="mb-3 font-semibold">
              Tento týden · {formatDay(current.week_start)} – {formatDay(current.week_end)}
            </h2>
            <WeekProgress week={current} />
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-zinc-400">Long run</dt>
              <dd>
                {current.long_run_text ?? "–"}
                {current.longest_run_km !== null && <span className="text-zinc-400"> · nejdelší {formatNumber(current.longest_run_km, 1)} km</span>}
              </dd>
              <dt className="text-zinc-400">Kvalita</dt>
              <dd>{current.quality ?? "–"}</dd>
              {current.notes && (
                <>
                  <dt className="text-zinc-400">Pozn.</dt>
                  <dd>{current.notes}</dd>
                </>
              )}
            </dl>
          </Card>
        )}

        <Card>
          <h2 className="mb-2 font-semibold">Plán po týdnech</h2>
          {weeks.data?.length ? (
            <ul className="divide-y divide-zinc-800">
              {weeks.data.map((week) => (
                <li key={week.week_start} className={`py-3 ${week === current ? "rounded-lg bg-zinc-800/40 px-2" : ""}`}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium">
                      {formatDay(week.week_start)} – {formatDay(week.week_end)}
                    </span>
                    <span className="text-xs text-zinc-400">LR {week.long_run_text ?? "–"}</span>
                  </div>
                  <WeekProgress week={week} compact />
                  {week.quality && <div className="mt-1 truncate text-xs text-zinc-500">{week.quality}</div>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="py-4 text-sm text-zinc-500">Plán se načte ze znalostní báze (Nastavení → synchronizovat).</p>
          )}
        </Card>

        {kb.data?.lthr && (
          <Card>
            <h2 className="mb-2 font-semibold">Zóny (LTHR {kb.data.lthr})</h2>
            <table className="w-full text-sm">
              <tbody>
                {zones(kb.data.lthr).map((z) => (
                  <tr key={z.zone} className="border-t border-zinc-800 first:border-0">
                    <td className="py-1.5 font-medium">{z.zone}</td>
                    <td className="py-1.5 text-zinc-400">{z.label}</td>
                    <td className="py-1.5 text-right tabular-nums">{z.range} bpm</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        <Card>
          <h2 className="mb-2 font-semibold">Poslední běhy</h2>
          {runs.length ? (
            <ul className="divide-y divide-zinc-800">
              {runs.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </ul>
          ) : (
            <p className="py-4 text-sm text-zinc-500">Běhy se objeví po propojení Stravy (Nastavení).</p>
          )}
        </Card>
      </div>
    </>
  );
}

function WeekProgress({ week, compact = false }: { week: PlanWeek; compact?: boolean }) {
  const target = week.km_max ?? week.km_min;
  const pct = target ? Math.min(100, (week.actual_km / target) * 100) : 0;
  const reached = week.km_min !== null && week.actual_km >= week.km_min;
  return (
    <div>
      <div className={`flex justify-between ${compact ? "text-xs" : "text-sm"}`}>
        <span className="tabular-nums">
          {formatNumber(week.actual_km, 1)} km{" "}
          <span className="text-zinc-400">
            z {week.km_text ?? "–"} · {week.actual_runs} {week.actual_runs === 1 ? "běh" : "běhů"}
          </span>
        </span>
        {reached && <span className="text-emerald-400">splněno</span>}
      </div>
      {target ? (
        <div className={`mt-1 overflow-hidden rounded-full bg-zinc-800 ${compact ? "h-1.5" : "h-2.5"}`}>
          <div className={`h-full rounded-full ${reached ? "bg-emerald-500" : "bg-sky-500"}`} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function RunRow({ run }: { run: Activity }) {
  const km = run.distance_meters / 1000;
  return (
    <li className="py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-medium">{run.notes ?? run.activity_type}</span>
        <span className="shrink-0 text-xs text-zinc-400">{formatDay(run.start_time)}</span>
      </div>
      <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-sm tabular-nums text-zinc-300">
        <span>{formatNumber(km, 2)} km</span>
        <span>{formatPace(run.pace_sec_per_km)}/km</span>
        {run.gap_sec_per_km && <span className="text-zinc-400">GAP {formatPace(run.gap_sec_per_km)}</span>}
        {run.avg_hr && <span>{run.avg_hr} bpm</span>}
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
        {run.heat && (
          <Chip>
            <Thermometer size={12} /> horko
          </Chip>
        )}
        {run.ef_gap !== null && <Chip>EF {formatNumber(run.ef_gap, 2)}</Chip>}
        {run.decoupling_pct !== null && <Chip>decoupling {formatNumber(run.decoupling_pct, 1)} %</Chip>}
        {run.pct_above_easy !== null && <Chip>nad easy {formatNumber(run.pct_above_easy)} %</Chip>}
        {run.z4_minutes ? <Chip>Z4 {formatNumber(run.z4_minutes)} min</Chip> : null}
        {run.rpe !== null && <Chip>RPE {run.rpe}</Chip>}
      </div>
    </li>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-1.5 py-0.5 text-zinc-300">{children}</span>;
}
