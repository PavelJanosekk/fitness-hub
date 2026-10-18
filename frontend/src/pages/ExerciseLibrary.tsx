import { ArrowLeft, ChevronRight, Plus, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { type Exercise, useExercises } from "../api/gym";
import { ExerciseSheet } from "../components/gym/ExerciseSheet";
import { EQUIPMENT_LABELS, GROUP_LABELS, useExerciseFilter } from "../components/gym/exercises";
import { PageHeader } from "../components/Layout";
import { Chips } from "../components/ui";

/** All exercises: search, filter by muscle group, create new ones and edit name / group / equipment. */
export function ExerciseLibrary() {
  const exercises = useExercises();
  const { query, setQuery, group, setGroup, groups, filtered } = useExerciseFilter(exercises.data);
  const [editing, setEditing] = useState<Exercise | "new" | null>(null);

  return (
    <>
      <PageHeader title="Cviky" />
      <div className="mb-3 flex items-center gap-2">
        <Link to="/gym" aria-label="Zpět" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
          <ArrowLeft size={20} />
        </Link>
        <label className="flex flex-1 items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3 focus-within:border-emerald-500">
          <Search size={18} className="text-zinc-500" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 flex-1 bg-transparent outline-none" />
        </label>
        <button onClick={() => setEditing("new")} aria-label="Nový cvik" className="flex size-11 items-center justify-center rounded-xl bg-emerald-500 text-on-accent">
          <Plus size={20} />
        </button>
      </div>
      <div className="mb-3">
        <Chips label="Partie" options={groups.map((g) => [g, GROUP_LABELS[g]] as const)} value={group} onChange={setGroup} allLabel="Vše" />
      </div>
      <ul className="space-y-1">
        {filtered.map((exercise) => (
          <li key={exercise.id}>
            <button onClick={() => setEditing(exercise)} className="flex w-full items-center gap-2 rounded-xl bg-zinc-900/60 px-3 py-2.5 text-left active:bg-zinc-800">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{exercise.name}</span>
                <span className="text-xs text-zinc-500">
                  {GROUP_LABELS[exercise.muscle_group] ?? exercise.muscle_group}
                  {exercise.equipment && ` · ${EQUIPMENT_LABELS[exercise.equipment] ?? exercise.equipment}`}
                </span>
              </span>
              <ChevronRight size={16} className="shrink-0 text-zinc-600" />
            </button>
          </li>
        ))}
      </ul>
      {exercises.isSuccess && filtered.length === 0 && (
        <div className="py-6 text-center text-sm text-zinc-500">
          Žádný cvik nenalezen.
          {query.trim() && (
            <button onClick={() => setEditing("new")} className="mx-auto mt-2 flex min-h-11 items-center gap-1.5 rounded-xl px-3 text-emerald-400 active:bg-zinc-800">
              <Plus size={16} /> Vytvořit cvik „{query.trim()}“
            </button>
          )}
        </div>
      )}
      {editing !== null && (
        <ExerciseSheet
          exercise={editing === "new" ? null : editing}
          initialName={query.trim()}
          initialGroup={group}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
