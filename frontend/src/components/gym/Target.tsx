import { AlertTriangle, TrendingUp } from "lucide-react";
import type { LastPerformance, ProgressionTarget, SetRole, SetType, TargetReason, TargetSet } from "../../api/gym";
import type { LocalSet } from "../../lib/activeWorkout";
import { formatDay } from "../../lib/format";
import { Button, Sheet, parseDecimal } from "../ui";

/** Progression targets in the active workout (E35): the line under an exercise, its sheet, and the per-set details. */

export const kgText = (weight: number | null | undefined) =>
  weight === null || weight === undefined ? "" : weight.toLocaleString("cs-CZ", { maximumFractionDigits: 2 });
const plural = (n: number, one: string, few: string, many: string) => `${n} ${n === 1 ? one : n < 5 ? few : many}`;

/** E33's targets, still kept in a workout on the phone, have no blocks: those are ignored. */
export const asTarget = (target: unknown): ProgressionTarget | null =>
  target && Array.isArray((target as ProgressionTarget).blocks) ? (target as ProgressionTarget) : null;

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
  return groups.map((g) => (g.weight ? `${kgText(g.weight)} kg × ${g.reps.join(", ")}` : `${g.reps.join(", ")} opak.`)).join(" · ");
}

const REASONS: Record<TargetReason, string> = {
  plus_rep: "+1 opakování",
  weight_up: "Zvýšení váhy",
  return_up: "Návrat na vyšší váhu",
  add_set: "+1 série",
  hold: "Udržet cíl",
  check_drop: "Prověřit propad",
  lower: "Snížit váhu",
  comeback: "Po pauze",
  no_data: "Málo dat",
};
const reasonLabel = (role: SetRole, reason: TargetReason) => (role === "backoff" && reason === "plus_rep" ? "Back-off progres" : REASONS[reason]);
const CAUTION = new Set<TargetReason>(["hold", "check_drop", "lower", "comeback", "no_data"]);
const ROLE_LABELS: Record<SetRole, string> = { straight: "", top: "Top-set", backoff: "Back-off" };
const flagged = (t: ProgressionTarget) => t.warnings.some((w) => w === "stall" || w === "decline" || w === "big_jump");

export function TargetLine({ target, onOpen }: { target: ProgressionTarget; onOpen: () => void }) {
  const labels = [...new Set(target.blocks.map((b) => reasonLabel(b.role, b.reason)))];
  const caution = target.blocks.some((b) => CAUTION.has(b.reason));
  return (
    <button type="button" onClick={onOpen} className="mb-1 flex w-full min-w-0 items-center gap-1.5 rounded-lg px-2 py-1 text-left text-xs active:bg-zinc-800">
      <TrendingUp size={14} className="shrink-0 text-emerald-400" />
      <span className="shrink-0 text-zinc-500">Cíl</span>
      <span className="min-w-0 truncate font-medium tabular-nums text-zinc-200">{setsSummary(target.sets)}</span>
      <span className={`ml-auto max-w-[45%] shrink-0 truncate rounded-full px-1.5 py-0.5 text-[11px] font-medium ${caution ? "bg-amber-500/15 text-amber-300" : "bg-emerald-500/15 text-emerald-300"}`}>
        {labels.join(" · ")}
      </span>
      {flagged(target) && <AlertTriangle size={13} className="shrink-0 text-amber-400" aria-label="Upozornění k cíli" />}
    </button>
  );
}

/** Why this block got its step, in a sentence (the pushed set is numbered within its block). */
function explain(t: ProgressionTarget, role: SetRole, reason: TargetReason): string {
  const pushed = t.sets.filter((s) => s.role === role).findIndex((s) => s.priority) + 1;
  const which = role === "backoff" ? `${pushed}. back-off sérii` : `${pushed}. sérii`;
  const lo = t.rep_min;
  switch (reason) {
    case "plus_rep":
      return `Přidej 1 opakování v ${which} (je označená), ostatní série drž.`;
    case "weight_up":
      return `První série dala horní hranici ${t.rep_max}, prostřední aspoň ${lo} a poslední aspoň ${lo - 1}. Přidej ${kgText(t.weight_step)} kg. Opakování jsou odhad podle tvého poklesu mezi sériemi, rozhodne skutečný výkon.`;
    case "return_up":
      return "Podmínky pro vyšší váhu jsou splněné a tuhle váhu už jsi zvedal, takže cíl bere tvoje opakování z té doby.";
    case "add_set":
      return `U cviku máš zapnuté přidávání sérií (do ${t.sets_max}), takže nejdřív série navíc a pak opakování.`;
    case "hold":
      return t.warnings.includes("last_not_comparable")
        ? "Minulý trénink byl neobvyklý nebo s jinou vahou než v plánu, takže se do progrese nepočítá. Cíl je minulý plán."
        : "Minule cíl nevyšel o opakování. Zopakuj ho, nic se neposouvá.";
    case "check_drop":
      return `Některá série minule výrazně zaostala (pod ${lo} opakování a aspoň o 2 pod cílem). Plán zůstává, váha se nemění. Může za tím být únava, kratší pauza, jiný průběh tréninku nebo chyba v zápisu.`;
    case "lower":
      return "Výrazný propad se opakoval dvakrát po sobě, takže váha jde o krok dolů. Až se opakování vrátí, půjde zase nahoru.";
    case "comeback":
      return `Od minula uběhlo ${plural(t.days_since, "den", "dny", "dní")}. Začni asi o 10 % lehčeji (bez zátěže s méně opakováními), síla se rychle vrátí.`;
    case "no_data":
      return "Na tenhle cvik je málo srovnatelných tréninků (nebo se změnila strategie), takže cíl jen zopakuje poslední hodnoty.";
  }
}

const WARNINGS: Partial<Record<ProgressionTarget["warnings"][number], (t: ProgressionTarget) => string>> = {
  stall: (t) =>
    `${plural(t.stalled_sessions, "trénink", "tréninky", "tréninků")} na téhle váze bez lepšího součtu opakování. Progres se možná zpomaluje, nic se ale nemění samo.`,
  decline: () => "Součet opakování klesá 3 tréninky po sobě. Zvaž lehčí trénink, návrh je níž.",
  big_jump: (t) =>
    `Krok ${kgText(t.weight_step)} kg je na tuhle váhu velký skok a odhad první série vychází pod rozsah. Zvaž menší krok v nastavení cviku.`,
};

export function TargetSheet({
  name,
  target,
  last,
  unusual,
  canApply,
  onApply,
  onUnusual,
  onEdit,
  onClose,
}: {
  name: string;
  target: ProgressionTarget;
  last: LastPerformance;
  unusual: boolean;
  canApply: boolean; // some sets aren't ticked yet
  onApply: (sets: TargetSet[]) => void;
  onUnusual: (unusual: boolean) => void;
  onEdit?: () => void;
  onClose: () => void;
}) {
  const suggestion = target.suggestion;
  const effort = target.target_rir === 0 ? "do selhání" : `${target.target_rir} opak. v záloze`;
  return (
    <Sheet title={name} onClose={onClose}>
      <div className="space-y-4 text-sm">
        <div className="rounded-xl bg-zinc-800/70 p-3">
          <p className="text-xs text-zinc-500">{last.workout_started_at ? `Minule (${formatDay(last.workout_started_at)})` : "Minule"}</p>
          <p className="tabular-nums text-zinc-300">{setsSummary(last.sets)}</p>
          <p className="mt-2 text-xs text-zinc-500">Cíl · každá série {effort}</p>
          <p className="text-lg font-semibold tabular-nums text-emerald-300">{setsSummary(target.sets)}</p>
          {target.blocks.map((b) => (
            <p key={b.role} className="mt-2 text-zinc-300">
              <span className="font-medium">
                {ROLE_LABELS[b.role] && `${ROLE_LABELS[b.role]}: `}
                {reasonLabel(b.role, b.reason)}.
              </span>{" "}
              {explain(target, b.role, b.reason)}
            </p>
          ))}
          {target.fatigue_from && <p className="mt-2 text-zinc-400">Tehdy jsi před tímhle cvikem dělal {target.fatigue_from} na stejnou partii, mohla to být únava.</p>}
          {target.warnings.map((w) => {
            const text = WARNINGS[w]?.(target);
            return (
              text && (
                <p key={w} className="mt-2 flex gap-1.5 text-amber-300">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {text}
                </p>
              )
            );
          })}
        </div>

        {suggestion && (
          <div className="rounded-xl border border-zinc-800 p-3">
            <p className="font-medium">{suggestion.kind === "deload" ? "Lehčí trénink jen pro dnešek" : "Lehčí varianta jen pro dnešek"}</p>
            <p className="tabular-nums text-zinc-300">{setsSummary(suggestion.sets)}</p>
            <p className="mt-1 text-xs text-zinc-500">Plán se tím nemění, příště se cíl vrátí.</p>
            <Button variant="ghost" className="mt-2 w-full" disabled={!canApply} onClick={() => onApply(suggestion.sets)}>
              Použít dnes
            </Button>
          </div>
        )}

        <label className="flex items-start gap-3 rounded-xl border border-zinc-800 p-3">
          <input type="checkbox" checked={unusual} onChange={(e) => onUnusual(e.target.checked)} className="mt-1 size-4 shrink-0 accent-emerald-500" />
          <span>
            Neobvyklý průběh dnes
            <span className="block text-xs text-zinc-500">Bolest, přerušení, mimořádná únava. Dnešek se u cviku nebude počítat do progrese.</span>
          </span>
        </label>

        <div>
          <h3 className="mb-1 font-semibold">Jak se cíl počítá</h3>
          <ol className="list-decimal space-y-0.5 pl-5 text-zinc-300">
            <li>
              Váha nahoru, když první série dá {target.rep_max}, prostřední aspoň {target.rep_min} a poslední aspoň {target.rep_min - 1}.
            </li>
            <li>Jinak +1 opakování: v první sérii, dokud nedá {target.rep_max}, pak v první slabší další sérii.</li>
            <li>Nesplněný cíl se opakuje. Výrazný propad se jen označí, váha jde dolů až po druhém propadu za sebou.</li>
            <li>Po pauze nad 3 týdny asi o 10 % lehčeji. Stagnace a pokles jen upozorní.</li>
            <li>{target.sets_max ? `Série se přidávají do ${target.sets_max}.` : "Počet sérií se nemění."}</li>
          </ol>
          <p className="mt-1 text-xs text-zinc-500">Neobvyklé tréninky a ruční změny váhy se do progrese nepočítají, pokud změnu nepotvrdíš i pro příště.</p>
        </div>

        <div className="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 p-3">
          <p className="text-zinc-400">
            {target.strategy === "top_backoff" ? "Top-set + back-off" : "Stejné série"} · {target.rep_min}–{target.rep_max} opak. · krok {kgText(target.weight_step)} kg · RIR{" "}
            {target.target_rir}
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

const RIR_VALUES = [0, 1, 2, 3] as const;

/**
 * Under a ticked set: its target when the set differs from it, and the RIR (reps in reserve). The picker shows for the
 * set just ticked; nothing selected means not confirmed, and the exercise's target RIR is only a grey hint.
 */
export function SetMeta({ set, picker, targetRir, onRir }: { set: LocalSet; picker: boolean; targetRir: number; onRir: (rir: number | null) => void }) {
  const hasPlan = set.planned_weight != null || set.planned_reps != null;
  const reps = set.reps ? Math.round(parseDecimal(set.reps) ?? 0) : null;
  const differs = hasPlan && ((set.planned_weight ?? null) !== parseDecimal(set.weight) || (set.planned_reps ?? null) !== reps);
  if (!differs && !picker && set.rir == null) return null;
  return (
    <div className="flex min-h-6 items-center justify-between gap-2 pr-1 pl-9 text-[11px] text-zinc-500">
      <span className="tabular-nums">{differs && `cíl ${set.planned_weight ? `${kgText(set.planned_weight)} kg × ` : ""}${set.planned_reps ?? "–"}`}</span>
      {picker ? (
        <span className="flex items-center gap-1">
          RIR
          {RIR_VALUES.map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={set.rir === v}
              aria-label={`RIR ${v === 3 ? "3 a víc" : v}`}
              onClick={() => onRir(set.rir === v ? null : v)}
              className={`h-6 min-w-7 rounded-md px-1.5 text-xs font-medium ${set.rir === v ? "bg-emerald-500 text-on-accent" : "bg-zinc-800 text-zinc-300 active:bg-zinc-700"}`}
            >
              {v === 3 ? "3+" : v}
            </button>
          ))}
          {set.rir == null && <span className="pl-0.5 text-zinc-600">cíl {targetRir}</span>}
        </span>
      ) : (
        set.rir != null && <span>RIR {set.rir === 3 ? "3+" : set.rir}</span>
      )}
    </div>
  );
}
