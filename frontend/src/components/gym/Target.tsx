import { TrendingUp } from "lucide-react";
import type { LastPerformance, ProgressionTarget, SetType } from "../../api/gym";
import { formatDay } from "../../lib/format";
import { Button, Sheet } from "../ui";

/** Progression targets in the active workout (E33): the line under an exercise and the sheet explaining it. */

const kg = (weight: number) => weight.toLocaleString("cs-CZ", { maximumFractionDigits: 2 });
const plural = (n: number, one: string, few: string, many: string) => `${n} ${n === 1 ? one : n < 5 ? few : many}`;

/** Working sets grouped by weight: "40 kg × 6, 6, 6", "100 kg × 2 · 80 kg × 6, 5", "8, 6 opak." without a load. */
export function setsSummary(sets: { set_type: SetType; weight_kg: number | null; reps: number | null }[]): string {
  const groups: { weight: number; reps: string[] }[] = [];
  for (const s of sets) {
    if (s.set_type !== "normal" && s.set_type !== "failure") continue;
    const weight = s.weight_kg ?? 0;
    const group = groups.at(-1);
    if (group?.weight === weight) group.reps.push(String(s.reps ?? "–"));
    else groups.push({ weight, reps: [String(s.reps ?? "–")] });
  }
  return groups.map((g) => (g.weight ? `${kg(g.weight)} kg × ${g.reps.join(", ")}` : `${g.reps.join(", ")} opak.`)).join(" · ");
}

const STEPS: Record<ProgressionTarget["kind"], (t: ProgressionTarget) => string> = {
  sets: () => "+1 série",
  reps: () => "+1 opakování",
  weight: (t) => `+${kg(t.weight_step)} kg`,
  lighter: () => "lehčí váha",
  deload: () => "odlehčení",
  comeback: () => "po pauze",
};
const easing = (t: ProgressionTarget) => t.kind === "deload" || t.kind === "comeback" || t.kind === "lighter";
// No lighter weight was possible, so the target keeps progressing despite the stall
const stuck = (t: ProgressionTarget) => t.stalled_sessions >= 3 && t.kind !== "deload";

export function TargetLine({ target, onOpen }: { target: ProgressionTarget; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className="mb-1 flex w-full min-w-0 items-center gap-1.5 rounded-lg px-2 py-1 text-left text-xs active:bg-zinc-800">
      <TrendingUp size={14} className="shrink-0 text-emerald-400" />
      <span className="shrink-0 text-zinc-500">Cíl</span>
      <span className="min-w-0 truncate font-medium tabular-nums text-zinc-200">{setsSummary(target.sets)}</span>
      <span className={`ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-medium ${easing(target) ? "bg-amber-500/15 text-amber-300" : "bg-emerald-500/15 text-emerald-300"}`}>
        {STEPS[target.kind](target)}
      </span>
      {stuck(target) && <span className="size-1.5 shrink-0 rounded-full bg-amber-400" aria-label="Bez zlepšení" />}
    </button>
  );
}

function reason(t: ProgressionTarget): string {
  const loaded = t.weight_kg > 0;
  switch (t.kind) {
    case "sets":
      return `Další série se stejnou vahou a opakováními jako ta poslední. Objem roste, i když opakování zatím ne. Až budeš mít ${plural(t.sets_max, "sérii", "série", "sérií")}, přijdou na řadu opakování.`;
    case "reps":
      return "Přidej 1 opakování v nejslabší sérii, ostatní série drž. Když ho nedáš, nevadí: cíl zůstane stejný a zkusíš to příště.";
    case "weight":
      return `Všechny série dosáhly horní hranice ${t.rep_max} opakování. Přidej ${kg(t.weight_step)} kg a začni znovu od ${t.rep_min} opakování.`;
    case "lighter":
      return `Žádná série nedosáhla ${t.rep_min} opakování, takže váha je na rozsah ${t.rep_min}–${t.rep_max} moc těžká. O krok lehčí váha, opakování jsou odhadnutá ze stejného maxima (1RM).`;
    case "deload":
      return `${plural(t.stalled_sessions, "trénink", "tréninky", "tréninků")} po sobě bez zlepšení na téhle váze. Uber asi 10 % a vybuduj to znovu nahoru, obvykle pak překonáš i původní maximum.`;
    case "comeback":
      return `Od minula uběhlo ${plural(t.days_since, "den", "dny", "dní")}. Začni ${loaded ? "asi o 10 % lehčeji" : "asi s 10 % méně opakováními"}, síla se rychle vrátí.`;
  }
}

export function TargetSheet({
  name,
  target,
  last,
  onEdit,
  onClose,
}: {
  name: string;
  target: ProgressionTarget;
  last: LastPerformance;
  onEdit?: () => void;
  onClose: () => void;
}) {
  return (
    <Sheet title={name} onClose={onClose}>
      <div className="space-y-4 text-sm">
        <div className="rounded-xl bg-zinc-800/70 p-3">
          <p className="text-xs text-zinc-500">{last.workout_started_at ? `Minule (${formatDay(last.workout_started_at)})` : "Minule"}</p>
          <p className="tabular-nums text-zinc-300">{setsSummary(last.sets)}</p>
          <p className="mt-2 text-xs text-zinc-500">Cíl · {STEPS[target.kind](target)}</p>
          <p className="text-lg font-semibold tabular-nums text-emerald-300">{setsSummary(target.sets)}</p>
          <p className="mt-2 text-zinc-300">{reason(target)}</p>
          {stuck(target) && (
            <p className="mt-2 text-amber-300">
              {plural(target.stalled_sessions, "trénink", "tréninky", "tréninků")} bez zlepšení, ale o krok lehčí váha by byla moc velký skok. Zkus menší krok váhy nebo na čas jiný cvik.
            </p>
          )}
        </div>
        <div>
          <h3 className="mb-1 font-semibold">Jak se cíl počítá</h3>
          <p className="mb-1 text-zinc-400">Z minulého tréninku, vždy jen jeden krok:</p>
          <ol className="list-decimal space-y-0.5 pl-5 text-zinc-300">
            <li>Po pauze nad 3 týdny nebo po 3 trénincích bez zlepšení asi o 10 % lehčeji.</li>
            <li>Když žádná série nedá {target.rep_min} opakování, o krok lehčí váha.</li>
            <li>
              Když všechny série dají {target.rep_max}, +{kg(target.weight_step)} kg a znovu od {target.rep_min}.
            </li>
            <li>Dokud nemáš {plural(target.sets_max, "sérii", "série", "sérií")}, přidá se série.</li>
            <li>Jinak +1 opakování v nejslabší sérii.</li>
          </ol>
          <p className="mt-1 text-xs text-zinc-500">Zahřívací série, drop sety a série s jinou vahou zůstávají jako minule.</p>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 p-3">
          <p className="text-zinc-400">
            Rozsah {target.rep_min}–{target.rep_max} opak. · krok {kg(target.weight_step)} kg · max {plural(target.sets_max, "série", "série", "sérií")}
          </p>
          {onEdit && (
            <Button variant="ghost" className="shrink-0 px-3" onClick={onEdit}>
              Upravit
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}

