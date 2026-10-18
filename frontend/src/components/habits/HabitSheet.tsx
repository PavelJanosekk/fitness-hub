import { Minus, Plus } from "lucide-react";
import { useState } from "react";
import { ApiError } from "../../api/client";
import { type HabitInput, useSaveHabit } from "../../api/habits";
import { AUTO_RULES, type AutoRule, type Frequency, type HabitDays, type Skill, SKILLS } from "../../lib/habits";
import { Button, Chips, DecimalInput, parseDecimal, Segmented, Sheet } from "../ui";

const FREQUENCIES = [
  ["daily", "Denně"],
  ["weekly", "Týdně"],
] as const;
const POINTS = [
  [1, "1"],
  [2, "2"],
  [3, "3"],
] as const;

function saveError(error: Error): string {
  if (error instanceof ApiError) return `Chyba ${error.status}: ${error.message}`;
  return navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, rutiny jde upravit jen s připojením.";
}

/** Create (`habit` undefined) or edit a habit: name, daily/weekly (× per week), area, points, bonus, auto rule. */
export function HabitSheet({ habit, onClose }: { habit?: HabitDays; onClose: () => void }) {
  const save = useSaveHabit();
  const [title, setTitle] = useState(habit?.title ?? "");
  const [frequency, setFrequency] = useState<Frequency>(habit?.frequency ?? "daily");
  const [target, setTarget] = useState(habit?.weekly_target ?? 1);
  const [skill, setSkill] = useState<Skill | null>(habit?.skill ?? null);
  const [points, setPoints] = useState(habit?.points ?? 1);
  const [bonus, setBonus] = useState(habit?.is_bonus ?? false);
  const [rule, setRule] = useState<AutoRule | null>(habit?.auto_rule ?? null);
  const [threshold, setThreshold] = useState(habit?.auto_threshold != null ? String(habit.auto_threshold).replace(".", ",") : "");
  const ruleMeta = AUTO_RULES.find((a) => a.rule === rule);
  const valid = title.trim() !== "";

  const submit = () => {
    if (!valid) return;
    const body: HabitInput = {
      title: title.trim(),
      frequency,
      weekly_target: frequency === "weekly" ? target : 1,
      skill,
      points,
      is_bonus: frequency === "daily" && bonus,
      auto_rule: rule,
      auto_threshold: ruleMeta?.unit ? parseDecimal(threshold) : null,
    };
    save.mutate({ id: habit?.id, ...body }, { onSuccess: onClose });
  };

  return (
    <Sheet title={habit ? "Upravit rutinu" : "Nová rutina"} onClose={onClose}>
      <form onSubmit={(e) => (e.preventDefault(), submit())} className="space-y-5">
        <label className="block text-sm text-zinc-400">
          Název
          <input
            autoFocus={!habit}
            value={title}
            maxLength={80}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="např. Ustlat postel"
            className="mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500"
          />
        </label>

        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-zinc-400">Opakování</span>
          <Segmented options={FREQUENCIES} value={frequency} onChange={setFrequency} />
        </div>

        {frequency === "weekly" && (
          <div className="flex items-center justify-between gap-3">
            <span>
              <span className="block text-[15px]">Kolikrát za týden</span>
              <span className="text-xs text-zinc-500">týden je splněný při {target} {target === 1 ? "dni" : "dnech"}</span>
            </span>
            <span className="flex items-center rounded-xl bg-zinc-800 p-0.5">
              <button type="button" aria-label="Méně" disabled={target <= 1} onClick={() => setTarget(target - 1)} className="flex size-10 items-center justify-center rounded-lg active:bg-zinc-700 disabled:opacity-30">
                <Minus size={18} />
              </button>
              <span className="min-w-8 text-center font-semibold tabular-nums">{target}×</span>
              <button type="button" aria-label="Více" disabled={target >= 7} onClick={() => setTarget(target + 1)} className="flex size-10 items-center justify-center rounded-lg active:bg-zinc-700 disabled:opacity-30">
                <Plus size={18} />
              </button>
            </span>
          </div>
        )}

        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Oblast</p>
          <Chips label="Oblast" options={SKILLS} value={skill} onChange={setSkill} allLabel="Žádná" wrap />
        </div>

        <div className="flex items-center justify-between gap-3">
          <span className="text-[15px]">Body za splnění</span>
          <Segmented options={POINTS} value={points} onChange={setPoints} />
        </div>

        {frequency === "daily" && (
          <button type="button" role="switch" aria-checked={bonus} onClick={() => setBonus(!bonus)} className="flex w-full items-center justify-between gap-3 text-left">
            <span>
              <span className="block text-[15px]">Bonus</span>
              <span className="text-xs text-zinc-500">přidá body, ale nezvedá maximum dne ani procenta</span>
            </span>
            <span className={`flex h-7 w-12 shrink-0 items-center rounded-full p-0.5 transition-colors ${bonus ? "bg-emerald-500" : "bg-zinc-700"}`}>
              <span className={`size-6 rounded-full bg-zinc-50 shadow transition-transform ${bonus ? "translate-x-5" : ""}`} />
            </span>
          </button>
        )}

        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Splnit automaticky z dat aplikace</p>
          <div className="ui-card divide-y divide-zinc-800 overflow-hidden" role="radiogroup" aria-label="Automatické splnění">
            {[{ rule: null, label: "Ne, jen ručně" } as const, ...AUTO_RULES].map((a) => {
              const selected = rule === a.rule;
              return (
                <button
                  key={a.rule ?? "manual"}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setRule(a.rule)}
                  className="flex min-h-12 w-full items-center gap-3 px-3 py-2 text-left active:bg-zinc-800/60"
                >
                  <span className={`flex size-5 shrink-0 items-center justify-center rounded-full border-2 ${selected ? "border-emerald-500" : "border-zinc-600"}`}>
                    {selected && <span className="size-2.5 rounded-full bg-emerald-500" />}
                  </span>
                  <span className="flex-1 text-sm">{a.label}</span>
                  {"hint" in a && a.hint && <span className="text-xs text-zinc-500">{a.hint}</span>}
                </button>
              );
            })}
          </div>
          {ruleMeta?.unit && (
            <label className="mt-2 flex items-center gap-2 text-sm text-zinc-400">
              Alespoň
              <DecimalInput
                ariaLabel="Hranice"
                value={threshold}
                onChange={setThreshold}
                placeholder={ruleMeta.fallback ? String(ruleMeta.fallback) : "cíl"}
                className="max-w-32"
              />
              {ruleMeta.unit}
            </label>
          )}
          <p className="mt-2 text-xs text-zinc-500">I automatickou rutinu jde odškrtnout ručně, třeba když jsi cvičil bez hodinek.</p>
        </div>

        {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
        <Button type="submit" disabled={!valid || save.isPending} className="w-full">
          {save.isPending ? "Ukládám…" : habit ? "Uložit změny" : "Přidat rutinu"}
        </Button>
      </form>
    </Sheet>
  );
}
