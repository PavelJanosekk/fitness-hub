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

/** The day's actively burned kcal (steps + training) under the intake summary: a number only, nothing is subtracted. */
export function EnergySummary({ date, onOpenTargets }: { date: string; onOpenTargets: () => void }) {
  const energy = useEnergy(date, date);
  const [open, setOpen] = useState(false);
  const day = energy.data?.[0];
  if (!day) return null;

  if (day.active_kcal === null) {
    return (
      <div className="mt-4 border-t border-zinc-800 pt-3 text-sm text-zinc-400">
        <p className="flex items-center gap-1.5">
          <Flame size={16} className="text-zinc-500" /> Aktivně spáleno
        </p>
        <p className="mt-1 text-xs text-zinc-500">Pro odhad zapiš váhu na Přehledu.</p>
      </div>
    );
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-left">
        <span className="flex items-center gap-1.5 text-zinc-400">
          <Flame size={16} /> Aktivně spáleno
        </span>
        <span className="flex items-center gap-1 tabular-nums">
          <span className="font-semibold text-zinc-100">≈ {formatNumber(day.active_kcal)} kcal</span>
          <ChevronDown size={16} className={`text-zinc-500 ${open ? "rotate-180" : ""}`} />
        </span>
      </button>
      <p className="mt-0.5 text-right text-xs tabular-nums text-zinc-500">
        kroky {day.steps_kcal === null ? "?" : formatNumber(day.steps_kcal)} · trénink {formatNumber(day.exercise_kcal)}
      </p>
      {open && <EnergyDetail day={day} onOpenTargets={onOpenTargets} />}
    </div>
  );
}

function EnergyDetail({ day, onOpenTargets }: { day: EnergyDay; onOpenTargets: () => void }) {
  const isToday = day.date === isoDate();
  const rows: [string, string, number | null][] = [
    [
      "Kroky",
      day.steps === null
        ? "chybí data z mobilu i hodinek"
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
      <div className="space-y-1 border-t border-zinc-800 pt-2 text-xs text-zinc-500">
        {day.bmr_kcal === null ? (
          <button onClick={onOpenTargets} className="text-left text-emerald-400">
            Bazální metabolismus: doplň v cílech pohlaví, rok narození a výšku ›
          </button>
        ) : (
          <>
            <p className="flex justify-between gap-3">
              <span>Bazální metabolismus (navíc, v čísle výše není)</span>
              <span className="tabular-nums">{formatNumber(day.bmr_kcal)} kcal</span>
            </p>
            <p className="flex justify-between gap-3">
              <span>Celkový výdej dne (bazál ×1,15 + aktivně)</span>
              <span className="tabular-nums">≈ {formatNumber(day.total_kcal)} kcal</span>
            </p>
          </>
        )}
        <p className="text-[11px]">
          Přibližný odhad z váhy {formatNumber(day.weight_kg, 1)} kg.{isToday && " Dnes: kroky a trénink zatím."}
        </p>
      </div>
    </div>
  );
}
