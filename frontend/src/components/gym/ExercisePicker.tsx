import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { type Exercise, useExercises } from "../../api/gym";
import { Chips, Sheet } from "../ui";
import { ExerciseSheet } from "./ExerciseSheet";
import { GROUP_LABELS, useExerciseFilter } from "./exercises";

export function ExercisePicker({ onPick, onClose }: { onPick: (exercise: Exercise) => void; onClose: () => void }) {
  const exercises = useExercises();
  const { query, setQuery, group, setGroup, groups, filtered } = useExerciseFilter(exercises.data);
  // A new exercise replaces the list while it is being created; saving it picks it right away
  const [creating, setCreating] = useState(false);

  if (creating) return <ExerciseSheet exercise={null} initialName={query.trim()} initialGroup={group} onClose={() => setCreating(false)} onSaved={onPick} />;
  return (
    <Sheet title="Přidat cvik" onClose={onClose} tall>
      <div className="sticky top-0 z-10 -mx-4 -mt-1 bg-zinc-900 px-4 pb-2 backdrop-blur-xl">
        <label className="mb-2 flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3">
          <Search size={18} className="text-zinc-500" />
          <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 w-full bg-transparent outline-none" />
        </label>
        <Chips label="Partie" options={groups.map((g) => [g, GROUP_LABELS[g]] as const)} value={group} onChange={setGroup} allLabel="Vše" />
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
      {exercises.isSuccess && filtered.length === 0 && <p className="pt-6 pb-2 text-center text-sm text-zinc-500">Žádný cvik nenalezen.</p>}
      {exercises.isSuccess && (
        <button type="button" onClick={() => setCreating(true)} className="mt-2 flex min-h-11 w-full items-center justify-center gap-1.5 rounded-xl text-sm text-emerald-400 active:bg-zinc-800">
          <Plus size={16} /> {query.trim() ? `Vytvořit cvik „${query.trim()}“` : "Nový cvik"}
        </button>
      )}
    </Sheet>
  );
}
