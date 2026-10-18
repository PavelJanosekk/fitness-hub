import { ChevronDown, Flame } from "lucide-react";
import { useState } from "react";
import { useEnergy } from "../../api/queries";
import type { EnergyDay, EnergyItem } from "../../api/types";
import { formatNumber, isoDate } from "../../lib/format";

const ACTIVITY_LABELS: Record<string, string> = {
  Run: "Běh",
  TrailRun: "Trailový běh",
  VirtualRun: "Běh na pásu",
  Walk: "Chůze",
  Hike: "Turistika",
  Ride: "Kolo",
  VirtualRide: "Kolo na trenažéru",
  MountainBikeRide: "Horské kolo",
  GravelRide: "Gravel",
  EBikeRide: "Elektrokolo",
  Swim: "Plavání",
  WeightTraining: "Posilování",
  Workout: "Trénink",
  Yoga: "Jóga",
};

export const activityLabel = (type: string) => ACTIVITY_LABELS[type] ?? type;

function itemLabel(item: EnergyItem) {
  if (item.source === "gym") return item.name ?? "Posilovna";
  const distance = item.distance_km ? ` ${formatNumber(item.distance_km, 1)} km` : "";
  return `${activityLabel(item.activity_type)}${distance}`;
}

/** The day's estimated expenditure under the intake summary: a number only, nothing is subtracted. */
export function EnergySummary({ date, onOpenTargets }: { date: string; onOpenTargets: () => void }) {
  const energy = useEnergy(date, date);
  const [open, setOpen] = useState(false);
  const day = energy.data?.[0];
  if (!day) return null;

  if (day.total_kcal === null) {
    return (
      <div className="mt-4 border-t border-zinc-800 pt-3 text-sm text-zinc-400">
        <p className="flex items-center gap-1.5">
          <Flame size={16} className="text-zinc-500" /> Výdej energie
          {day.exercise_kcal ? <span className="tabular-nums"> · trénink {formatNumber(day.exercise_kcal)} kcal</span> : null}
        </p>
        <button onClick={onOpenTargets} className="mt-1 text-left text-xs text-emerald-400">
          {day.missing.includes("weight") ? "Pro odhad výdeje zapiš váhu na Přehledu." : "Pro odhad výdeje doplň v cílech pohlaví, rok narození a výšku ›"}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-left">
        <span className="flex items-center gap-1.5 text-zinc-400">
          <Flame size={16} /> Výdej
        </span>
        <span className="flex items-center gap-1 tabular-nums">
          <span className="font-semibold text-zinc-100">≈ {formatNumber(day.total_kcal)} kcal</span>
          <ChevronDown size={16} className={`text-zinc-500 ${open ? "rotate-180" : ""}`} />
        </span>
      </button>
      <p className="mt-0.5 text-right text-xs tabular-nums text-zinc-500">
        základ {formatNumber(day.base_kcal)} · kroky {day.steps_kcal === null ? "?" : formatNumber(day.steps_kcal)} · trénink{" "}
        {formatNumber(day.exercise_kcal)}
      </p>
      {open && <EnergyDetail day={day} />}
    </div>
  );
}

function EnergyDetail({ day }: { day: EnergyDay }) {
  const isToday = day.date === isoDate();
  const rows: [string, string, number | null][] = [
    ["Základ", `klidový metabolismus ${formatNumber(day.bmr_kcal)} kcal + trávení a běžný pohyb (×1,15)`, day.base_kcal],
    [
      "Kroky",
      day.steps === null
        ? "chybí data z mobilu i hodinek"
        : day.steps_counted !== day.steps
          ? `${formatNumber(day.steps_counted)} z ${formatNumber(day.steps)} (kroky při běhu počítá trénink)`
          : `${formatNumber(day.steps)} kroků`,
      day.steps_kcal,
    ],
    ...day.items.map(
      (item): [string, string, number | null] => [
        itemLabel(item),
        `${formatNumber(item.minutes)} min · ${item.method === "device" ? "z hodinek (Strava)" : "odhad"}`,
        item.kcal,
      ],
    ),
  ];
  return (
    <div className="mt-2 space-y-1.5 text-sm">
      {rows.map(([label, detail, kcal], i) => (
        <div key={i} className="flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <span className="text-zinc-200">{label}</span> <span className="text-xs text-zinc-500">{detail}</span>
          </div>
          <span className="shrink-0 tabular-nums text-zinc-300">{kcal === null ? "?" : `${formatNumber(kcal)} kcal`}</span>
        </div>
      ))}
      <p className="pt-1 text-[11px] text-zinc-500">
        Přibližný odhad z váhy {formatNumber(day.weight_kg, 1)} kg.{isToday && " Dnes: základ za celý den, kroky a trénink zatím."}
      </p>
    </div>
  );
}
