import { ChevronDown, ExternalLink, Flag, Thermometer } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useWeekly } from "../api/queries";
import { type Activity, type PlanWeek, stravaUrl, useActivities, useKb, useRunWeeks, zones } from "../api/running";
import { RunVolumeChart } from "../components/charts/DashboardCharts";
import { Card, PageHeader } from "../components/Layout";
import { WeekRunList } from "../components/running/WeekRunList";
import { Pager, Segmented } from "../components/ui";
import { formatDay, formatDayMonth, formatNumber, formatPace, isoDate } from "../lib/format";

const RUN_TYPES = new Set(["Run", "TrailRun", "VirtualRun"]);
const WEEKS_PER_PAGE = 4;
const RUNS_PER_PAGE = 5;
const daysUntil = (iso: string) => Math.round((new Date(`${iso}T12:00:00`).getTime() - new Date(`${isoDate()}T12:00:00`).getTime()) / 86_400_000);
const stravaLabel = "Otevřít na Stravě";
// The charts load only when the Grafy tab is opened
const RunStats = lazy(() => import("../components/running/RunStats").then((m) => ({ default: m.RunStats })));
const VIEWS = [
  ["plan", "Plán"],
  ["stats", "Grafy"],
] as const;

export function RunningPlan() {
  const [params, setParams] = useSearchParams();
  const view = params.get("v") === "stats" ? "stats" : "plan";
  return (
    <>
      <PageHeader title="Běh" />
      <div className="space-y-3">
        <Segmented options={VIEWS} value={view} onChange={(v) => setParams(v === "stats" ? { v } : {}, { replace: true })} />
        {view === "stats" ? (
          <Suspense fallback={<p className="text-zinc-500">Načítám…</p>}>
            <RunStats />
          </Suspense>
        ) : (
          <PlanView />
        )}
      </div>
    </>
  );
}

function PlanView() {
  const kb = useKb();
  const weeks = useRunWeeks();
  const activities = useActivities();
  const weekly = useWeekly(10);
  const today = isoDate();
  const current = weeks.data?.find((w) => w.week_start <= today && today <= w.week_end);
  const upcoming = (kb.data?.races ?? []).filter((r) => r.date >= today);
  const runs = (activities.data ?? []).filter((a) => RUN_TYPES.has(a.activity_type));
  const planKm = new Map((weeks.data ?? []).map((w) => [w.week_start, w.km_max ?? w.km_min]));
  const volume = (weekly.data ?? []).map((w) => ({ ...w, plan_km: planKm.get(w.week_start) ?? null }));

  const [runPage, setRunPage] = useState(0);
  const navigate = useNavigate();
  const openRun = (id: number) => navigate(`/run/${id}`);

  return (
    <>
      <Card>
        <h2 className="mb-2 font-semibold">Objem za 10 týdnů</h2>
        {volume.some((w) => w.runs) ? <RunVolumeChart weeks={volume} /> : <p className="py-4 text-sm text-zinc-500">Běhy se objeví po propojení Stravy (Nastavení).</p>}
      </Card>

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
          {current.notes && <p className="mt-3 text-sm text-zinc-400">{current.notes}</p>}
          <div className="mt-2 border-t border-zinc-800 pt-1">
            <WeekRunList week={current} today={today} onOpenRun={openRun} />
          </div>
        </Card>
      )}

      <PlanWeeks
        weeks={(weeks.data ?? []).filter((w) => w !== current)}
        today={today}
        onOpenRun={openRun}
      />

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
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold">Poslední běhy</h2>
          <Pager page={runPage} pages={Math.ceil(runs.length / RUNS_PER_PAGE)} onChange={setRunPage} />
        </div>
        {runs.length ? (
          <ul className="divide-y divide-zinc-800">
            {runs.slice(runPage * RUNS_PER_PAGE, (runPage + 1) * RUNS_PER_PAGE).map((run) => (
              <RunRow key={run.id} run={run} onOpen={() => openRun(run.id)} />
            ))}
          </ul>
        ) : (
          <p className="py-4 text-sm text-zinc-500">Běhy se objeví po propojení Stravy (Nastavení).</p>
        )}
      </Card>
    </>
  );
}

/** Weeks as expandable tiles, a few per page; opens on the page with the next upcoming week. */
function PlanWeeks({
  weeks,
  today,
  onOpenRun,
}: {
  weeks: PlanWeek[];
  today: string;
  onOpenRun: (id: number) => void;
}) {
  const firstAhead = weeks.findIndex((w) => w.week_start > today);
  const [page, setPage] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const pages = Math.ceil(weeks.length / WEEKS_PER_PAGE);
  const shown = Math.min(page ?? Math.floor(Math.max(firstAhead, 0) / WEEKS_PER_PAGE), Math.max(pages - 1, 0));
  const toggle = (weekStart: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(weekStart)) next.add(weekStart);
      return next;
    });

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Plán po týdnech</h2>
        <Pager page={shown} pages={pages} onChange={setPage} />
      </div>
      {weeks.length ? (
        <ul className="space-y-2">
          {weeks.slice(shown * WEEKS_PER_PAGE, (shown + 1) * WEEKS_PER_PAGE).map((week) => {
            const isOpen = expanded.has(week.week_start);
            const kmLabel = week.km_text ? (/^~?\d/.test(week.km_text) ? `${week.km_text.replace(/\s*\(.*\)/, "")} km` : week.km_text) : null;
            return (
              <li key={week.week_start} className="rounded-xl border border-zinc-800 bg-zinc-950/40">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => toggle(week.week_start)}
                  className="flex min-h-11 w-full items-start gap-2 p-3 text-left"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="font-medium tabular-nums">
                        {formatDayMonth(week.week_start)} – {formatDayMonth(week.week_end)}
                      </span>
                      {kmLabel && <span className="shrink-0 text-xs text-zinc-400">{kmLabel}</span>}
                    </span>
                    {week.notes && <span className={`mt-0.5 block text-xs text-zinc-500 ${isOpen ? "" : "line-clamp-2"}`}>{week.notes}</span>}
                  </span>
                  <ChevronDown size={18} className={`mt-0.5 shrink-0 text-zinc-500 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                </button>
                {isOpen && (
                  <div className="border-t border-zinc-800 px-3 pb-1">
                    <WeekRunList week={week} today={today} onOpenRun={onOpenRun} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="py-4 text-sm text-zinc-500">Plán se načte ze znalostní báze (Nastavení → synchronizovat).</p>
      )}
    </Card>
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

function RunRow({ run, onOpen }: { run: Activity; onOpen: () => void }) {
  const km = run.distance_meters / 1000;
  const link = stravaUrl(run);
  return (
    <li
      className="-mx-2 cursor-pointer rounded-lg px-2 py-3 active:bg-zinc-800/40"
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}
      role="button"
      tabIndex={0}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-medium">{run.notes ?? run.activity_type}</span>
        <span className="flex shrink-0 items-center gap-1 text-xs text-zinc-400">
          {formatDay(run.start_time)}
          {link && (
            <a href={link} target="_blank" rel="noreferrer" aria-label={stravaLabel} onClick={(e) => e.stopPropagation()} className="-my-3 -mr-2 flex size-11 items-center justify-center rounded-lg active:bg-zinc-800">
              <ExternalLink size={14} />
            </a>
          )}
        </span>
      </div>
      <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-sm tabular-nums text-zinc-300">
        <span>{formatNumber(km, 2)} km</span>
        <span>{formatPace(run.pace_sec_per_km)}/km</span>
        {run.gap_sec_per_km && <span className="text-zinc-400">GAP {formatPace(run.gap_sec_per_km)}</span>}
        {run.avg_hr && <span>{run.avg_hr} bpm</span>}
      </div>
      {run.description && <p className="mt-1 line-clamp-2 text-xs text-zinc-500">{run.description}</p>}
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
