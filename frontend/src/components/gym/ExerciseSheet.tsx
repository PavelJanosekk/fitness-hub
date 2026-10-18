import { useState } from "react";
import { ApiError } from "../../api/client";
import { type Exercise, useSaveExercise } from "../../api/gym";
import { Button, Chips, Sheet } from "../ui";
import { EQUIPMENT_LABELS, GROUP_LABELS } from "./exercises";

function saveError(error: Error): string {
  if (error instanceof ApiError) return error.status === 409 ? "Cvik s tímto názvem už existuje." : `Chyba ${error.status}: ${error.message}`;
  return navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, cviky jde upravit jen s připojením.";
}

/** Create (`exercise` null) or edit an exercise: name, muscle group, equipment. A rename shows everywhere, history included. */
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
  const valid = name.trim() !== "" && group !== null;
  // Keep an equipment value the list doesn't know (older data) selectable
  const equipmentOptions = Object.entries(EQUIPMENT_LABELS).concat(equipment && !EQUIPMENT_LABELS[equipment] ? [[equipment, equipment]] : []);

  const submit = () => {
    if (!valid || group === null) return;
    save.mutate(
      { id: exercise?.id, name: name.trim(), muscle_group: group, equipment },
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
        {exercise && <p className="text-xs text-zinc-500">Změna se projeví v celé historii, šablonách i rozdělaném tréninku.</p>}
        {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
        <Button type="submit" disabled={!valid || save.isPending} className="w-full">
          {save.isPending ? "Ukládám…" : exercise ? "Uložit změny" : "Vytvořit cvik"}
        </Button>
      </form>
    </Sheet>
  );
}
