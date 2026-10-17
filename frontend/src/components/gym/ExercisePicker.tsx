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

const normalize = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export function ExercisePicker({ onPick, onClose }: { onPick: (exercise: Exercise) => void; onClose: () => void }) {
  const exercises = useExercises();
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const groups = Object.keys(GROUP_LABELS).filter((g) => exercises.data?.some((e) => e.muscle_group === g));
  const filtered = useMemo(() => {
    const needle = normalize(query.trim());
    return (exercises.data ?? []).filter((e) => (group === null || e.muscle_group === group) && normalize(e.name).includes(needle));
  }, [exercises.data, query, group]);
  return (
    <Sheet title="Přidat cvik" onClose={onClose} tall>
      <div className="sticky top-0 z-10 -mx-4 -mt-1 bg-zinc-900 px-4 pb-2">
        <label className="mb-2 flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3">
          <Search size={18} className="text-zinc-500" />
          <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 w-full bg-transparent outline-none" />
        </label>
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group" aria-label="Partie">
          {[null, ...groups].map((g) => (
            <button
              key={g ?? "all"}
              aria-pressed={group === g}
              onClick={() => setGroup(g)}
              className={`min-h-9 shrink-0 rounded-full px-3 text-sm ${group === g ? "bg-emerald-500 font-medium text-zinc-950" : "bg-zinc-800 text-zinc-300 active:bg-zinc-700"}`}
            >
              {g === null ? "Vše" : GROUP_LABELS[g]}
            </button>
          ))}
        </div>
      </div>
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
      {exercises.isSuccess && filtered.length === 0 && <p className="py-6 text-center text-sm text-zinc-500">Žádný cvik nenalezen.</p>}
    </Sheet>
  );
}
