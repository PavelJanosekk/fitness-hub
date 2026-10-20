import { useState } from "react";
import { ApiError } from "../../api/client";
import { type Exercise, type ProgressionSettings, type ProgressionStrategy, useSaveExercise } from "../../api/gym";
import { Button, Chips, DecimalInput, Sheet, parseDecimal } from "../ui";
import { EQUIPMENT_LABELS, GROUP_LABELS, progressionDefaults } from "./exercises";

type SettingKey = "rep_min" | "rep_max" | "weight_step" | "sets_max";
const SETTINGS: { key: SettingKey; label: string; max: number; whole: boolean }[] = [
  { key: "rep_min", label: "Opak. od", max: 50, whole: true },
  { key: "rep_max", label: "Opak. do", max: 50, whole: true },
  { key: "weight_step", label: "Krok kg", max: 50, whole: false },
  { key: "sets_max", label: "Série do", max: 10, whole: true },
];
const STRATEGIES = [
  ["straight", "Stejné série"],
  ["top_backoff", "Top-set + back-off"],
] as const;
const RIR_OPTIONS = [
  ["0", "Do selhání"],
  ["1", "RIR 1"],
  ["2", "RIR 2"],
  ["3", "RIR 3+"],
] as const;
const shown = (value: number | null | undefined) => (value == null ? "" : String(value).replace(".", ","));

function saveError(error: Error): string {
  if (error instanceof ApiError) return error.status === 409 ? "Cvik s tímto názvem už existuje." : `Chyba ${error.status}: ${error.message}`;
  return navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, cviky jde upravit jen s připojením.";
}

/**
 * Create (`exercise` null) or edit an exercise: name, muscle group, equipment and the progression settings of its
 * targets (E33, E35; blank = the default). A rename shows everywhere, history included.
 */
export function ExerciseSheet({
  exercise,
  initialName = "",
  initialGroup = null,
  onClose,
  onSaved,
}: {
  exercise: Exercise | null;
  initialName?: string;
  initialGroup?: string | null;
  onClose: () => void;
  onSaved?: (exercise: Exercise) => void;
}) {
  const save = useSaveExercise();
  const [name, setName] = useState(exercise?.name ?? initialName);
  const [group, setGroup] = useState<string | null>(exercise?.muscle_group ?? initialGroup);
  const [equipment, setEquipment] = useState<string | null>(exercise?.equipment ?? null);
  const [settings, setSettings] = useState<Record<SettingKey, string>>({
    rep_min: shown(exercise?.rep_min),
    rep_max: shown(exercise?.rep_max),
    weight_step: shown(exercise?.weight_step),
    sets_max: shown(exercise?.sets_max),
  });
  // Null = the default (straight sets, 1 RIR), so changing the defaults later reaches every exercise left on them
  const [strategy, setStrategy] = useState<ProgressionStrategy | null>(exercise?.strategy ?? null);
  const [targetRir, setTargetRir] = useState<number | null>(exercise?.target_rir ?? null);
  const defaults = progressionDefaults(equipment);
  const parsed = Object.fromEntries(
    SETTINGS.map(({ key, whole }) => {
      const value = parseDecimal(settings[key]);
      return [key, value !== null && whole ? Math.round(value) : value];
    }),
  ) as Omit<ProgressionSettings, "strategy" | "target_rir">;
  const outOfRange = SETTINGS.some(({ key, max }) => {
    const value = parsed[key];
    return value !== null && (value <= 0 || value > max);
  });
  const settingsError = outOfRange
    ? "Hodnoty progrese musí být kladné (opakování do 50, krok do 50 kg, série do 10)."
    : parsed.rep_min !== null && parsed.rep_max !== null && parsed.rep_max < parsed.rep_min
      ? "Horní hranice opakování nesmí být pod spodní."
      : null;
  const valid = name.trim() !== "" && group !== null && settingsError === null;
  // Keep an equipment value the list doesn't know (older data) selectable
  const equipmentOptions = Object.entries(EQUIPMENT_LABELS).concat(equipment && !EQUIPMENT_LABELS[equipment] ? [[equipment, equipment]] : []);

  const submit = () => {
    if (!valid || group === null) return;
    save.mutate(
      { id: exercise?.id, name: name.trim(), muscle_group: group, equipment, ...parsed, strategy, target_rir: targetRir },
      {
        onSuccess: (saved) => {
          onSaved?.(saved);
          onClose();
        },
      },
    );
  };

  return (
    <Sheet title={exercise ? "Upravit cvik" : "Nový cvik"} onClose={onClose}>
      <form onSubmit={(e) => (e.preventDefault(), submit())} className="space-y-4">
        <label className="block text-sm text-zinc-400">
          Název
          <input
            autoFocus={!exercise}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="např. Incline Bench Press (Dumbbell)"
            className="mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500"
          />
        </label>
        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Partie</p>
          <Chips label="Partie" options={Object.entries(GROUP_LABELS)} value={group} onChange={(g) => g && setGroup(g)} wrap />
        </div>
        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Vybavení</p>
          <Chips label="Vybavení" options={equipmentOptions} value={equipment} onChange={setEquipment} allLabel="Nezadáno" wrap />
        </div>
        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Progrese</p>
          <div className="grid grid-cols-4 gap-2">
            {SETTINGS.map(({ key, label }) => (
              <label key={key} className="block min-w-0 text-xs text-zinc-500">
                {label}
                <DecimalInput
                  ariaLabel={label}
                  value={settings[key]}
                  placeholder={shown(defaults[key]) || "–"}
                  onChange={(value) => setSettings((s) => ({ ...s, [key]: value }))}
                  className="mt-1 px-2 text-center"
                />
              </label>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-zinc-500">
            Podle toho se počítá cíl na další trénink: opakování k horní hranici, pak váha o krok. Prázdné pole = výchozí hodnota pro vybavení.
            „Série do“ vyplň, jen když má appka přidávat série před opakováními; jinak se počet sérií nemění.
          </p>
          {settingsError && <p className="mt-1 text-sm text-red-300">{settingsError}</p>}
          <p className="mt-3 mb-1.5 text-xs text-zinc-500">Strategie</p>
          <Chips label="Strategie" options={STRATEGIES} value={strategy ?? "straight"} onChange={(v) => setStrategy(v === "straight" ? null : v)} wrap />
          <p className="mt-1 text-xs text-zinc-500">
            Top-set + back-off: první série má vlastní cíl, další série jsou lehčí a postupují samostatně.
          </p>
          <p className="mt-3 mb-1.5 text-xs text-zinc-500">Úsilí v každé sérii</p>
          <Chips
            label="Cílová rezerva opakování"
            options={RIR_OPTIONS}
            value={String(targetRir ?? 1) as (typeof RIR_OPTIONS)[number][0]}
            onChange={(v) => setTargetRir(v === null || v === "1" ? null : Number(v))}
            wrap
          />
        </div>
        {exercise && <p className="text-xs text-zinc-500">Změna se projeví v celé historii, šablonách i rozdělaném tréninku.</p>}
        {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
        <Button type="submit" disabled={!valid || save.isPending} className="w-full">
          {save.isPending ? "Ukládám…" : exercise ? "Uložit změny" : "Vytvořit cvik"}
        </Button>
      </form>
    </Sheet>
  );
}
