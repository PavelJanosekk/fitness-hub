import { useState } from "react";
import { type Profile, useProfile, useSaveProfile } from "../../api/nutrition";
import { Button, DecimalInput, Sheet, parseDecimal } from "../ui";

const FIELDS: readonly (readonly [keyof Profile, string])[] = [
  ["kcal_target", "Základ (kcal)"],
  ["maintenance_offset_kcal", "Udržování: + kcal"],
  ["protein_target_g", "Bílkoviny (g)"],
  ["fat_target_g", "Tuky (g)"],
  ["fiber_target_g", "Vláknina (g)"],
  ["height_cm", "Výška (cm)"],
  ["birth_year", "Rok narození"],
];

const toText = (value: number | null) => (value === null ? "" : String(value).replace(".", ","));

/** The base and fixed macros of the daily target (E41); runs add to the base, carbs are the rest. */
export function TargetsSheet({ onClose }: { onClose: () => void }) {
  const profile = useProfile();
  return (
    <Sheet title="Cíle výživy" onClose={onClose}>
      {profile.data ? <TargetsForm profile={profile.data} onDone={onClose} /> : <p className="text-zinc-500">Načítám…</p>}
    </Sheet>
  );
}

function TargetsForm({ profile, onDone }: { profile: Profile; onDone: () => void }) {
  const save = useSaveProfile();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map(([key]) => [key, toText(profile[key] as number | null)])),
  );
  const [sex, setSex] = useState(profile.sex);

  const submit = () => {
    const numbers = Object.fromEntries(FIELDS.map(([key]) => [key, parseDecimal(values[key] ?? "")]));
    save.mutate({ ...(numbers as unknown as Profile), sex }, { onSuccess: onDone });
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-400">
        Denní cíl = základ + běhy (0,75 × váha × km, threshold a LR 1,0 × váha × km; LR napůl den předem). Sacharidy jsou zbytek po
        bílkovinách a tucích. V režimu udržování se k základu přičte navýšení (prázdné = 500).
      </p>
      <div className="grid grid-cols-2 gap-3">
        {FIELDS.map(([key, label]) => (
          <label key={key} className="text-sm text-zinc-400">
            {label}
            <DecimalInput ariaLabel={label} value={values[key] ?? ""} onChange={(v) => setValues({ ...values, [key]: v })} className="mt-1" />
          </label>
        ))}
        <label className="text-sm text-zinc-400">
          Pohlaví
          <select
            value={sex ?? ""}
            onChange={(e) => setSex((e.target.value || null) as Profile["sex"])}
            className="mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-zinc-100"
          >
            <option value="">–</option>
            <option value="male">muž</option>
            <option value="female">žena</option>
          </select>
        </label>
      </div>
      <Button onClick={submit} disabled={save.isPending} className="w-full">
        {save.isError ? "Zkusit znovu" : "Uložit cíle"}
      </Button>
    </div>
  );
}
