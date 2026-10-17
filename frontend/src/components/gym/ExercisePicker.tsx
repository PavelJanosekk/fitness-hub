import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { type Exercise, useExercises } from "../../api/gym";
import { Sheet } from "../ui";

export const GROUP_LABELS: Record<string, string> = {
  chest: "Hrudník",
  back: "Záda",
  legs: "Nohy",
  shoulders: "Ramena",
  arms: "Paže",
  core: "Core",
  full_body: "Celé tělo",
  cardio: "Kardio",
};

export function ExercisePicker({ onPick, onClose }: { onPick: (exercise: Exercise) => void; onClose: () => void }) {
  const exercises = useExercises();
  const [query, setQuery] = useState("");
  const normalize = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const filtered = useMemo(
    () => (exercises.data ?? []).filter((e) => normalize(e.name).includes(normalize(query.trim()))),
    [exercises.data, query],
  );
  return (
    <Sheet title="Přidat cvik" onClose={onClose}>
      <label className="mb-3 flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3">
        <Search size={18} className="text-zinc-500" />
        <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 w-full bg-transparent outline-none" />
      </label>
      <ul className="divide-y divide-zinc-800">
        {filtered.map((e) => (
          <li key={e.id}>
            <button onClick={() => onPick(e)} className="flex w-full items-center justify-between py-3 text-left active:bg-zinc-800">
              <span>{e.name}</span>
              <span className="text-xs text-zinc-500">{GROUP_LABELS[e.muscle_group] ?? e.muscle_group}</span>
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
