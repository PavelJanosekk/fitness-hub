import { Circle, CircleCheck, ExternalLink } from "lucide-react";
import { type Activity, type PlanWeek, stravaUrl } from "../../api/running";
import { formatDay, formatNumber, formatPace } from "../../lib/format";
import { buildWeekRows, type WeekRow } from "../../lib/weekRows";

/** Runs of one plan week: done ones checked and greyed out, open ones as the plan lists them. */
export function WeekRunList({
  week,
  today,
  onOpenRun,
}: {
  week: PlanWeek;
  today: string;
  onOpenRun: (id: number) => void;
}) {
  const rows = buildWeekRows(week, today);
  if (!rows.length) return <p className="py-2 text-sm text-zinc-500">V tomto týdnu zatím není žádný běh.</p>;
  return (
    <ul className="divide-y divide-zinc-800/70">
      {rows.map((row) => (
        <RunItem key={row.key} row={row} onOpenRun={onOpenRun} />
      ))}
    </ul>
  );
}

function RunItem({ row, onOpenRun }: { row: WeekRow; onOpenRun: (id: number) => void }) {
  const { run, plan, date, status } = row;
  const done = status === "done";
  const title = plan ?? run?.notes ?? "Běh";
  const link = run ? stravaUrl(run) : null;
  const open = run ? () => onOpenRun(run.id) : undefined;
  return (
    <li
      className={`flex gap-3 py-2.5 ${done ? "text-zinc-500" : "text-zinc-100"} ${open ? "cursor-pointer active:bg-zinc-800/40" : ""}`}
      onClick={open}
      onKeyDown={open && ((e) => (e.key === "Enter" || e.key === " ") && open())}
      role={open ? "button" : undefined}
      tabIndex={open ? 0 : undefined}
    >
      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center" aria-hidden>
        {done ? (
          <CircleCheck size={20} className="text-emerald-500" />
        ) : status === "info" ? (
          <span className="size-1.5 rounded-full bg-zinc-600" />
        ) : (
          <Circle size={20} className={status === "missed" ? "text-amber-600/70" : "text-zinc-500"} />
        )}
      </span>
      <div className="min-w-0 flex-1 text-sm">
        <div className="flex items-baseline justify-between gap-2">
          <span className={`min-w-0 ${done ? "" : "font-medium"}`}>
            {date && <span className={done ? "" : "text-zinc-400"}>{formatDay(date)} · </span>}
            {title}
          </span>
          {status === "missed" && <span className="shrink-0 text-xs text-amber-500/80">vynecháno</span>}
        </div>
        {run && <RunStats run={run} />}
        {run && plan && run.notes && <div className="mt-0.5 text-xs">{run.notes}</div>}
        {run?.description && <div className="mt-0.5 line-clamp-2 text-xs">{run.description}</div>}
      </div>
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          aria-label="Otevřít na Stravě"
          className="-my-1 -mr-1 flex size-11 shrink-0 items-center justify-center rounded-lg text-zinc-500 active:bg-zinc-800"
        >
          <ExternalLink size={16} />
        </a>
      )}
    </li>
  );
}

function RunStats({ run }: { run: Activity }) {
  return (
    <div className="mt-0.5 flex flex-wrap gap-x-3 tabular-nums">
      <span>{formatNumber(run.distance_meters / 1000, 2)} km</span>
      <span>{formatPace(run.pace_sec_per_km)}/km</span>
      {run.avg_hr && <span>{run.avg_hr} bpm</span>}
      {run.rpe !== null && <span>RPE {run.rpe}</span>}
    </div>
  );
}
