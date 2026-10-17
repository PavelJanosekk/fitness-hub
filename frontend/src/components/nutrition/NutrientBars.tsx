import { ChevronDown } from "lucide-react";
import { useState } from "react";
import type { NutrientTotal } from "../../api/nutrition";
import { formatNumber } from "../../lib/format";

const MACROS = ["protein_g", "carbs_g", "fat_g", "fiber_g"] as const;
const SHORT: Record<string, string> = { protein_g: "Bílkoviny", carbs_g: "Sacharidy", fat_g: "Tuky", fiber_g: "Vláknina" };
// Below this share of the day's kcal a total says "incomplete data", not "too little" (Amendment C1)
const MIN_COVERAGE = 0.7;

function Bar({ percent, tone = "bg-emerald-500" }: { percent: number | null; tone?: string }) {
  const width = Math.min(100, Math.max(0, percent ?? 0));
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

const digits = (unit: string) => (unit === "g" || unit === "kcal" ? 0 : 1);

/** Today's kcal against the target plus the four macros. */
export function MacroSummary({ nutrients, trainingDay }: { nutrients: NutrientTotal[]; trainingDay: boolean }) {
  const byKey = Object.fromEntries(nutrients.map((n) => [n.key, n]));
  const kcal = byKey.kcal;
  const over = (kcal?.percent ?? 0) > 105;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <p>
          <span className="text-3xl font-semibold tabular-nums">{formatNumber(kcal?.amount ?? 0)}</span>
          <span className="text-zinc-400"> / {formatNumber(kcal?.target)} kcal</span>
        </p>
        {trainingDay && <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">tréninkový den</span>}
      </div>
      <Bar percent={kcal?.percent ?? null} tone={over ? "bg-amber-400" : "bg-emerald-500"} />
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        {MACROS.map((key) => {
          const n = byKey[key];
          if (!n) return null;
          return (
            <div key={key}>
              <p className="text-xs text-zinc-400">{SHORT[key]}</p>
              <p className="tabular-nums">
                {formatNumber(n.amount)} <span className="text-zinc-500">/ {formatNumber(n.target)} g</span>
              </p>
              <Bar percent={n.percent} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Vitamins and minerals: % of target, dimmed when too little of the day's food knows the value. */
export function MicroGrid({ nutrients }: { nutrients: NutrientTotal[] }) {
  const [open, setOpen] = useState(false);
  const micros = nutrients.filter((n) => !["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"].includes(n.key));
  const incomplete = micros.filter((n) => (n.coverage ?? 0) < MIN_COVERAGE).length;
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between py-1 text-left">
        <span className="font-semibold">Vitamíny a minerály</span>
        <span className="flex items-center gap-1 text-xs text-zinc-500">
          {incomplete > 0 && `${incomplete}× neúplná data`}
          <ChevronDown size={16} className={open ? "rotate-180" : ""} />
        </span>
      </button>
      {open && (
        <ul className="mt-2 grid gap-x-4 gap-y-2.5 sm:grid-cols-2">
          {micros.map((n) => {
            const partial = (n.coverage ?? 0) < MIN_COVERAGE;
            return (
              <li key={n.key} className={partial ? "opacity-50" : ""}>
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-300">{n.label}</span>
                  <span className="tabular-nums text-zinc-400">
                    {n.amount === null ? "?" : `${formatNumber(n.amount, digits(n.unit))} ${n.unit}`}
                    {n.percent !== null && ` · ${formatNumber(n.percent)} %`}
                  </span>
                </div>
                <Bar percent={n.percent} tone={partial ? "bg-zinc-500" : "bg-sky-500"} />
                {partial && n.coverage !== null && (
                  <p className="text-[11px] text-zinc-500">známo jen u {formatNumber(n.coverage * 100)} % kalorií</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
