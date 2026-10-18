import { useEffect, useRef, useState } from "react";
import { addDays, isoDate } from "../../lib/format";
import { Card } from "../Layout";

const WEEKS = 53;
/** Sequential single-hue scale (accent), the same steps as the Rutina calendar. */
const HEAT = ["bg-zinc-800", "bg-emerald-500/30", "bg-emerald-500/55", "bg-emerald-500/80", "bg-emerald-500"];
export const mondayOf = (iso: string) => addDays(iso, -((new Date(`${iso}T12:00:00`).getDay() + 6) % 7));

/**
 * GitHub-style year grid (53 weeks × 7 days, newest week on the right). Levels split the active days at their own
 * quartiles, so the scale follows the athlete instead of a fixed number; tapping a day shows `detail(day)`.
 */
export function CalendarHeatmap({
  values,
  detail,
  moreLabel,
}: {
  values: Map<string, number>;
  detail: (day: string) => string;
  moreLabel: string;
}) {
  const today = isoDate();
  const start = addDays(mondayOf(today), -7 * (WEEKS - 1));
  const scroller = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth;
  }, []);

  const active = [...values].filter(([d, v]) => d >= start && v > 0).map(([, v]) => v).sort((a, b) => a - b);
  const quantile = (q: number) => active[Math.min(active.length - 1, Math.floor(q * active.length))] ?? 0;
  const cuts = [quantile(0.25), quantile(0.5), quantile(0.75)];
  const level = (v: number) => (v <= 0 ? 0 : 1 + cuts.filter((c) => v > c).length);
  const columns = Array.from({ length: WEEKS }, (_, w) => Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)));
  const monthFormat = new Intl.DateTimeFormat("cs-CZ", { month: "short" });

  return (
    <Card className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Aktivita</h2>
        <span className="text-xs text-zinc-500">posledních 12 měsíců</span>
      </div>
      <div className="flex gap-1.5">
        <div className="grid shrink-0 grid-rows-[14px_repeat(7,12px)] gap-[3px] text-[10px] leading-3 text-zinc-500">
          <span />
          {["Po", "", "St", "", "Pá", "", "Ne"].map((d, i) => (
            <span key={i}>{d}</span>
          ))}
        </div>
        <div ref={scroller} className="min-w-0 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <div className="flex w-max gap-[3px]">
            {columns.map((column, w) => {
              const first = column.find((d) => d.slice(8) === "01");
              return (
                <div key={w} className="grid grid-rows-[14px_repeat(7,12px)] gap-[3px]">
                  <span className="w-3 overflow-visible text-[10px] leading-3 whitespace-nowrap text-zinc-500">
                    {first ? monthFormat.format(new Date(`${first}T12:00:00`)) : ""}
                  </span>
                  {column.map((d) =>
                    d > today ? (
                      <span key={d} />
                    ) : (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setSelected(d === selected ? null : d)}
                        aria-label={detail(d)}
                        className={`size-3 rounded-[3px] ${HEAT[level(values.get(d) ?? 0)]} ${d === selected ? "ring-2 ring-zinc-100" : ""}`}
                      />
                    ),
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px] text-zinc-500">
        <span className="min-w-0 truncate text-xs text-zinc-300">{selected ? detail(selected) : "Ťukni na den"}</span>
        <span className="flex shrink-0 items-center gap-1">
          méně
          {HEAT.map((c) => (
            <span key={c} className={`size-2.5 rounded-[2px] ${c}`} />
          ))}
          {moreLabel}
        </span>
      </div>
    </Card>
  );
}
