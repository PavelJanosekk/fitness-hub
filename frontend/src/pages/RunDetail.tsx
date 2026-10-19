import { ChevronLeft, ExternalLink, Thermometer } from "lucide-react";
import { lazy, Suspense, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type RunDetail as Detail, type RunSeriesKey, stravaUrl, useRunDetail } from "../api/running";
import { useChartKit } from "../components/charts/DashboardCharts";
import { Card } from "../components/Layout";
import { formatDay, formatDuration, formatNumber, formatPace, formatTime } from "../lib/format";

// Leaflet only loads when a run with a route is opened
const RunMap = lazy(() => import("../components/running/RunMap").then((m) => ({ default: m.RunMap })));

const ZONES = [
  ["z1", "Z1", "Recovery"],
  ["z2", "Z2", "Easy"],
  ["z3", "Z3", "Steady / MP"],
  ["z4", "Z4", "Threshold"],
  ["z5", "Z5", "Nad prahem"],
] as const;

/** One run like on Strava: summary, route, pace / HR / elevation / cadence along the run, zones, km splits. */
export function RunDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const detail = useRunDetail(Number(id));
  const run = detail.data?.activity;
  const back = () => (window.history.state?.idx ? navigate(-1) : navigate("/run"));

  return (
    <>
      <header className="sticky top-0 z-20 -mx-4 mb-3 border-b border-zinc-800 bg-zinc-950/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center gap-2">
          <button aria-label="Zpět na běhy" onClick={back} className="-ml-2 flex size-11 shrink-0 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800">
            <ChevronLeft size={24} />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold">{run ? (run.notes ?? run.activity_type) : "Běh"}</h1>
            {run && (
              <p className="text-xs text-zinc-400">
                {formatDay(run.start_time)} {formatTime(run.start_time)}
              </p>
            )}
          </div>
          {run && stravaUrl(run) && (
            <a
              href={stravaUrl(run)!}
              target="_blank"
              rel="noreferrer"
              aria-label="Otevřít na Stravě"
              className="-mr-2 flex size-11 shrink-0 items-center justify-center rounded-full text-zinc-400 active:bg-zinc-800"
            >
              <ExternalLink size={18} />
            </a>
          )}
        </div>
      </header>
      {detail.isPending ? (
        <p className="text-zinc-500">Načítám…</p>
      ) : !detail.data ? (
        <Card>
          <p className="text-zinc-400">Běh se nepodařilo načíst. Zkus to znovu, až bude spojení.</p>
        </Card>
      ) : (
        <DetailBody detail={detail.data} />
      )}
    </>
  );
}

function DetailBody({ detail }: { detail: Detail }) {
  const { series } = detail;
  const [active, setActive] = useState<number | null>(null);
  const marker = active !== null && series.lat?.[active] != null && series.lng?.[active] != null ? ([series.lat[active], series.lng[active]] as [number, number]) : null;
  return (
    <div className="space-y-3">
      <Summary detail={detail} />
      {detail.streams === "partial" && (
        <p className="px-1 text-xs text-zinc-500">Výška, kadence a trasa se dotáhnou ze Stravy při příští synchronizaci.</p>
      )}
      {detail.route.length > 1 && (
        <Card className="p-2!">
          <Suspense fallback={<div className="h-64 rounded-xl bg-zinc-900" />}>
            <RunMap route={detail.route} marker={marker} />
          </Suspense>
        </Card>
      )}
      {series.time_s?.length ? <Charts detail={detail} active={active} onActive={setActive} /> : null}
      <Zones detail={detail} />
      <Splits detail={detail} />
      <Analysis detail={detail} />
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-400">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tracking-tight tabular-nums">
        {value}
        {unit && value !== "–" && <span className="ml-1 text-sm font-normal text-zinc-400">{unit}</span>}
      </div>
    </div>
  );
}

function Summary({ detail }: { detail: Detail }) {
  const run = detail.activity;
  const elapsed = run.elapsed_seconds && run.elapsed_seconds - run.duration_seconds >= 60 ? run.elapsed_seconds : null;
  return (
    <Card>
      <div className="grid grid-cols-3 gap-x-3 gap-y-4">
        <Stat label="Vzdálenost" value={formatNumber(run.distance_meters / 1000, 2)} unit="km" />
        <Stat label="Čas v pohybu" value={formatDuration(run.duration_seconds)} />
        <Stat label="Tempo" value={formatPace(run.pace_sec_per_km)} unit="/km" />
        <Stat label="Ø tep" value={formatNumber(run.avg_hr)} unit="bpm" />
        <Stat label="Převýšení" value={formatNumber(detail.elevation_gain_m)} unit="m" />
        <Stat label="Kadence" value={formatNumber(run.avg_cadence)} unit="spm" />
      </div>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-t border-zinc-800 pt-3 text-sm tabular-nums text-zinc-300">
        {run.gap_sec_per_km && <span>GAP {formatPace(run.gap_sec_per_km)}/km</span>}
        {run.max_hr && <span>Max tep {run.max_hr}</span>}
        {elapsed && <span>Celkem {formatDuration(elapsed)}</span>}
        {run.calories && <span>{formatNumber(run.calories)} kcal</span>}
        {run.rpe !== null && <span>RPE {run.rpe}</span>}
        {run.heat && (
          <span className="inline-flex items-center gap-1">
            <Thermometer size={14} /> horko
          </span>
        )}
      </div>
      {run.description && <p className="mt-3 whitespace-pre-line text-sm text-zinc-400">{run.description}</p>}
    </Card>
  );
}

const finite = (values: (number | null)[] | undefined) => (values ?? []).filter((v): v is number => v !== null && Number.isFinite(v));
/** Centered moving average of speed (pace is its inverse), so GPS jitter doesn't hide the pace changes. */
function smoothPace(paces: (number | null)[], radius: number): (number | null)[] {
  return paces.map((p, i) => {
    if (p === null) return null;
    let speed = 0;
    let count = 0;
    for (let j = Math.max(0, i - radius); j <= Math.min(paces.length - 1, i + radius); j++) {
      const v = paces[j];
      if (v) (speed += 1000 / v, count++);
    }
    return Math.round(1000 / (speed / count));
  });
}
/** Three ticks inside the domain at round steps (pace: 15 s, otherwise 5). */
function niceTicks([lo, hi]: [number, number], step: number): number[] {
  const mid = Math.round((lo + hi) / 2 / step) * step;
  return [Math.ceil(lo / step) * step, mid, Math.floor(hi / step) * step].filter((v, i, a) => a.indexOf(v) === i);
}
const mean = (values: number[]) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);
const quantile = (sorted: number[], q: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];

type ChartSpec = {
  key: RunSeriesKey;
  label: string;
  color: string;
  format: (v: number) => string;
  unit: string;
  average: number | null;
  /** Shown instead of the average when there is none (e.g. the elevation range) */
  idle?: string;
  domain: [number, number];
  reversed?: boolean;
  area?: boolean;
};

/** Small multiples on one distance axis (one measure per chart), sharing the cursor and a value readout. */
function Charts({ detail, active, onActive }: { detail: Detail; active: number | null; onActive: (i: number | null) => void }) {
  const { series: colors, ink, axis } = useChartKit();
  const { series } = detail;
  const run = detail.activity;
  const byDistance = (series.distance_km?.length ?? 0) > 0;
  const x = (byDistance ? series.distance_km : series.time_s?.map((t) => (t === null ? null : t / 60))) ?? [];
  const pace = useMemo(() => smoothPace(series.pace ?? [], 2), [series]);
  const rows = useMemo(
    () => x.map((value, i) => ({ x: value, pace: pace[i] ?? null, hr: series.hr?.[i] ?? null, altitude: series.altitude?.[i] ?? null, cadence: series.cadence?.[i] ?? null })),
    [series, x, pace],
  );

  const specs = useMemo(() => {
    const out: ChartSpec[] = [];
    const paces = finite(pace).sort((a, b) => a - b);
    if (paces.length) {
      // Clip stops and sprints so the usual pace range fills the chart; faster is up
      const lo = quantile(paces, 0.02);
      const hi = quantile(paces, 0.95);
      const pad = Math.max(10, (hi - lo) * 0.15);
      out.push({ key: "pace", label: "Tempo", color: colors[0], format: formatPace, unit: "/km", average: run.pace_sec_per_km, domain: [Math.floor(lo - pad), Math.ceil(hi + pad)], reversed: true });
    }
    const hrs = finite(series.hr).sort((a, b) => a - b);
    if (hrs.length) {
      // The first minutes' low HR would squash the rest of the run
      const domain: [number, number] = [Math.floor(quantile(hrs, 0.02) - 5), Math.ceil(hrs[hrs.length - 1] + 3)];
      out.push({ key: "hr", label: "Tep", color: colors[1], format: (v) => formatNumber(v), unit: "bpm", average: run.avg_hr, domain });
    }
    const alts = finite(series.altitude);
    if (alts.length) {
      const [lo, hi] = [Math.min(...alts), Math.max(...alts)];
      const pad = Math.max(5, (20 - (hi - lo)) / 2);
      out.push({ key: "altitude", label: "Výška", color: ink.muted, format: (v) => formatNumber(v), unit: "m n. m.", average: null, idle: `${formatNumber(lo)}–${formatNumber(hi)} m n. m.`, domain: [Math.floor(lo - pad), Math.ceil(hi + pad)], area: true });
    }
    const cadences = finite(series.cadence).sort((a, b) => a - b);
    if (cadences.length) {
      const [lo, hi] = [quantile(cadences, 0.03), quantile(cadences, 0.99)];
      out.push({ key: "cadence", label: "Kadence", color: colors[4], format: (v) => formatNumber(v), unit: "spm", average: run.avg_cadence ?? mean(cadences), domain: [Math.floor(lo - 5), Math.ceil(hi + 5)] });
    }
    return out;
  }, [series, pace, colors, ink, run]);

  const onMove = (state: { activeTooltipIndex?: number | string | null }) => {
    const index = state.activeTooltipIndex;
    onActive(index === null || index === undefined || index === "" ? null : Number(index));
  };
  const cursorAt = active !== null ? x[active] : null;
  const elapsed = active !== null ? series.time_s?.[active] : null;

  return (
    <Card className="space-y-1">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Průběh</h2>
        <span className="text-xs tabular-nums text-zinc-400">
          {cursorAt !== null && cursorAt !== undefined
            ? `${byDistance ? `${formatNumber(cursorAt, 2)} km · ` : ""}${formatDuration(elapsed)}`
            : "Táhni prstem po grafu"}
        </span>
      </div>
      {specs.map((spec, i) => {
        const value = active !== null ? rows[active]?.[spec.key as "pace" | "hr" | "altitude" | "cadence"] : null;
        const shown = value ?? (active === null ? spec.average : null);
        const last = i === specs.length - 1;
        return (
          <div key={spec.key}>
            <div className="flex items-baseline justify-between pt-2 text-xs">
              <span className="inline-flex items-center gap-1.5 text-zinc-400">
                <span className="h-0.5 w-3 rounded" style={{ background: spec.color }} />
                {spec.label}
                {active === null && spec.average !== null && <span className="text-zinc-500">· průměr</span>}
                {active === null && spec.idle && <span className="text-zinc-500">· rozsah</span>}
              </span>
              <span className="font-medium tabular-nums text-zinc-200">
                {shown !== null && shown !== undefined ? `${spec.format(shown)} ${spec.unit}` : active === null && spec.idle ? spec.idle : "–"}
              </span>
            </div>
            <ResponsiveContainer width="100%" height={last ? 112 : 92}>
              <ComposedChart
                data={rows}
                syncId="run-detail"
                margin={{ top: 8, right: 4, bottom: last ? 0 : 8, left: 0 }}
                onMouseMove={onMove}
                onMouseLeave={() => onActive(null)}
                onTouchMove={onMove}
                onTouchEnd={() => onActive(null)}
              >
                <XAxis
                  dataKey="x"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  hide={!last}
                  tickFormatter={(v) => (byDistance ? `${formatNumber(v, v < 10 ? 1 : 0)} km` : `${Math.round(v)} min`)}
                  minTickGap={24}
                  {...axis}
                />
                <YAxis
                  domain={spec.domain}
                  reversed={spec.reversed}
                  allowDataOverflow
                  ticks={niceTicks(spec.domain, spec.key === "pace" ? 15 : 5)}
                  interval={0}
                  width={38}
                  tickFormatter={(v) => spec.format(Number(v))}
                  {...axis}
                />
                <Tooltip content={() => null} cursor={{ stroke: ink.secondary, strokeWidth: 1 }} isAnimationActive={false} />
                {spec.area ? (
                  <Area dataKey={spec.key} type="monotone" stroke={spec.color} strokeWidth={1.5} fill={spec.color} fillOpacity={0.25} baseValue={spec.domain[0]} isAnimationActive={false} connectNulls />
                ) : (
                  <Line dataKey={spec.key} type="monotone" stroke={spec.color} strokeWidth={1.5} dot={false} activeDot={{ r: 4, stroke: ink.primary, strokeWidth: 0 }} isAnimationActive={false} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </Card>
  );
}

function Zones({ detail }: { detail: Detail }) {
  const { series } = useChartKit();
  const seconds = detail.zone_seconds;
  if (!seconds || !detail.zone_bounds) return null;
  const total = Object.values(seconds).reduce((a, b) => a + b, 0);
  if (!total) return null;
  // Same groups as Běh → Grafy: easy (Z1–Z2), grey zone (Z3), hard (Z4–Z5); lighter = the lower zone of a pair
  const color = { z1: series[2], z2: series[2], z3: series[3], z4: series[1], z5: series[1] } as const;
  const opacity = { z1: 0.55, z2: 1, z3: 1, z4: 0.7, z5: 1 } as const;
  const max = Math.max(...Object.values(seconds));
  return (
    <Card>
      <h2 className="mb-3 font-semibold">Čas v zónách <span className="text-sm font-normal text-zinc-500">(LTHR {detail.lthr})</span></h2>
      <ul className="space-y-2">
        {ZONES.map(([key, zone, label]) => {
          const s = seconds[key] ?? 0;
          return (
            <li key={key} className="grid grid-cols-[6.5rem_1fr_6rem] items-center gap-2 text-sm">
              <span className="whitespace-nowrap">
                <span className="font-medium">{zone}</span> <span className="text-xs text-zinc-500">{detail.zone_bounds![key]}</span>
              </span>
              <span className="h-3 overflow-hidden rounded-full bg-zinc-800" title={label}>
                <span className="block h-full rounded-full" style={{ width: `${(100 * s) / max}%`, background: color[key], opacity: opacity[key] }} />
              </span>
              <span className="whitespace-nowrap text-right tabular-nums">
                {formatDuration(s)} <span className="text-xs text-zinc-500">{Math.round((100 * s) / total)} %</span>
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Splits({ detail }: { detail: Detail }) {
  const { series } = useChartKit();
  const { splits } = detail;
  if (!splits.length) return null;
  const paces = splits.map((s) => s.pace);
  const [fast, slow] = [Math.min(...paces), Math.max(...paces)];
  const hasGap = splits.some((s) => s.gap !== null);
  const hasHr = splits.some((s) => s.hr !== null);
  const hasElevation = splits.some((s) => s.elevation_m !== null);
  let distance = 0;
  return (
    <Card>
      <h2 className="mb-2 font-semibold">Mezičasy</h2>
      <table className="w-full text-sm tabular-nums">
        <thead className="text-xs text-zinc-500">
          <tr>
            <th className="py-1 text-left font-normal">km</th>
            <th className="py-1 text-left font-normal">Tempo</th>
            {hasGap && <th className="py-1 text-right font-normal">GAP</th>}
            {hasHr && <th className="py-1 text-right font-normal">Tep</th>}
            {hasElevation && <th className="py-1 text-right font-normal">Výška</th>}
          </tr>
        </thead>
        <tbody>
          {splits.map((split, i) => {
            distance += split.km;
            // Bar length: faster = longer, so the quickest km fills the column
            const width = slow === fast ? 100 : 35 + (65 * (slow - split.pace)) / (slow - fast);
            return (
              <tr key={i} className="border-t border-zinc-800">
                <td className="py-1.5 pr-2 text-zinc-400">{split.km < 0.99 ? formatNumber(distance, 1) : Math.round(distance)}</td>
                <td className="w-1/2 py-1.5 pr-2">
                  <div className="flex items-center gap-2">
                    <span className="w-10 shrink-0">{formatPace(split.pace)}</span>
                    <span className="h-2 flex-1">
                      <span className="block h-full rounded-full" style={{ width: `${width}%`, background: series[0], opacity: split.km < 0.99 ? 0.5 : 1 }} />
                    </span>
                  </div>
                </td>
                {hasGap && <td className="py-1.5 text-right text-zinc-400">{formatPace(split.gap)}</td>}
                {hasHr && <td className="py-1.5 text-right">{formatNumber(split.hr)}</td>}
                {hasElevation && (
                  <td className="py-1.5 text-right text-zinc-400">
                    {split.elevation_m === null ? "–" : `${split.elevation_m > 0 ? "+" : ""}${split.elevation_m} m`}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function Analysis({ detail }: { detail: Detail }) {
  const run = detail.activity;
  const rows: [string, string][] = [];
  if (run.ef_gap !== null) rows.push(["Aerobní efektivita (EF, GAP)", formatNumber(run.ef_gap, 2)]);
  if (run.decoupling_pct !== null) rows.push(["Decoupling (tempo vs. tep)", `${formatNumber(run.decoupling_pct, 1)} %`]);
  if (detail.hr_avg_steady !== null) rows.push(["Ø tep po 10. minutě", formatNumber(detail.hr_avg_steady)]);
  if (detail.pace_first10_s_per_km !== null) rows.push(["Tempo prvních 10 minut", `${formatPace(detail.pace_first10_s_per_km)}/km`]);
  if (run.pct_above_easy !== null) rows.push(["Čas nad easy (Z3+)", `${formatNumber(run.pct_above_easy)} %`]);
  if (!rows.length) return null;
  return (
    <Card>
      <h2 className="mb-2 font-semibold">Analýza</h2>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-t border-zinc-800 first:border-0">
              <td className="py-1.5 text-zinc-400">{label}</td>
              <td className="py-1.5 text-right tabular-nums">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {run.decoupling_pct !== null && run.duration_seconds < 45 * 60 && (
        <p className="mt-2 text-xs text-zinc-500">Decoupling má smysl hlavně u souvislých běhů od ~50 minut.</p>
      )}
    </Card>
  );
}
