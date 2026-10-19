import { ChevronLeft, GripVertical, Trash2, X } from "lucide-react";
import { useState } from "react";
import { type Exercise, type ServerSet, type ServerWorkout, type SetType, useSaveWorkout } from "../../api/gym";
import { formatNumber, isoDate } from "../../lib/format";
import { moveItem, useDragReorder } from "../../lib/useDragReorder";
import { uuid } from "../../lib/uuid";
import { Card } from "../Layout";
import { Button, parseDecimal } from "../ui";
import { ExercisePicker } from "./ExercisePicker";
import { GROUP_LABELS } from "./exercises";
import { AddSetButton, SetLabel, TableHeader, cellInput, selectAll } from "./SetTable";

/** A set being edited; `saved` holds the server row (fields the editor doesn't show are sent back unchanged). */
type DraftSet = { id: string; set_type: SetType; weight: string; reps: string; saved?: ServerSet };
type DraftExercise = { key: string; exercise_id: number; name: string; muscle_group: string; sets: DraftSet[] };

const fmt = (value: number | null) => (value === null ? "" : formatNumber(value, value % 1 ? 1 : 0));
const localTime = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const EDITOR_COLS = "grid-cols-[2rem_minmax(0,1fr)_minmax(0,1fr)_2.25rem]";
const DEFAULT_DURATION_MIN = 60;
const field = "mt-1 h-11 w-full min-w-0 rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

/** Exercises of a server workout in their order; only completed sets (what the history shows). */
function draftExercises(workout: ServerWorkout, exercises: Exercise[]): DraftExercise[] {
  const byOrder = new Map<number, DraftExercise>();
  for (const s of [...workout.sets].sort((a, b) => a.exercise_order - b.exercise_order || a.set_order - b.set_order)) {
    if (!s.completed) continue;
    const known = exercises.find((e) => e.id === s.exercise_id);
    const item = byOrder.get(s.exercise_order) ?? {
      key: uuid(),
      exercise_id: s.exercise_id,
      name: known?.name ?? `#${s.exercise_id}`,
      muscle_group: known?.muscle_group ?? "",
      sets: [],
    };
    item.sets.push({ id: s.id, set_type: s.set_type, weight: fmt(s.weight_kg), reps: s.reps === null ? "" : String(s.reps), saved: s });
    byOrder.set(s.exercise_order, item);
  }
  return [...byOrder.values()];
}

/**
 * Edit a finished workout (name, date and time, duration, exercises and sets) or log a past one (`workout` = null).
 * Saves everything in one request; a set with neither kg nor reps is dropped.
 */
export function WorkoutEditor({
  workout,
  exercises,
  onClose,
  onSaved,
}: {
  workout: ServerWorkout | null;
  exercises: Exercise[];
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const save = useSaveWorkout();
  const [name, setName] = useState(workout?.name ?? "Trénink");
  const [date, setDate] = useState(workout ? isoDate(new Date(workout.started_at)) : isoDate());
  const [time, setTime] = useState(workout ? localTime(workout.started_at) : "17:00");
  const [initialTiming] = useState(() => ({
    date: workout ? isoDate(new Date(workout.started_at)) : "",
    time: workout ? localTime(workout.started_at) : "",
    duration: String(workout?.ended_at ? Math.max(1, Math.round((Date.parse(workout.ended_at) - Date.parse(workout.started_at)) / 60_000)) : DEFAULT_DURATION_MIN),
  }));
  const [duration, setDuration] = useState(initialTiming.duration);
  const [notes, setNotes] = useState(workout?.notes ?? "");
  const [items, setItems] = useState<DraftExercise[]>(() => (workout ? draftExercises(workout, exercises) : []));
  const [picking, setPicking] = useState(false);

  const patchExercise = (index: number, patch: (e: DraftExercise) => DraftExercise) => setItems((prev) => prev.map((e, i) => (i === index ? patch(e) : e)));
  const patchSet = (index: number, setIndex: number, patch: Partial<DraftSet>) =>
    patchExercise(index, (e) => ({ ...e, sets: e.sets.map((s, j) => (j === setIndex ? { ...s, ...patch } : s)) }));
  const removeSet = (index: number, setIndex: number) => patchExercise(index, (e) => ({ ...e, sets: e.sets.filter((_, j) => j !== setIndex) }));
  const reorder = useDragReorder((from, to) => setItems((prev) => moveItem(prev, from, to)));

  const startedAt = new Date(`${date}T${time || "00:00"}`);
  const minutes = Math.round(parseDecimal(duration) ?? 0);
  const filled = (s: DraftSet) => s.weight.trim() !== "" || s.reps.trim() !== "";
  const valid = name.trim() !== "" && !Number.isNaN(startedAt.getTime()) && minutes > 0;

  const submit = () => {
    // Untouched timing goes back as it was: the rounded minutes would otherwise turn an estimated end into "set by the user"
    const timingKept = workout?.ended_at && date === initialTiming.date && time === initialTiming.time && duration === initialTiming.duration;
    const started = timingKept ? workout.started_at : startedAt.toISOString();
    const ended = timingKept ? workout.ended_at! : new Date(startedAt.getTime() + minutes * 60_000).toISOString();
    // Moving the workout to another day moves the completion times of its sets with it
    const shift = workout ? Date.parse(started) - Date.parse(workout.started_at) : 0;
    const kept = items.map((e) => ({ ...e, sets: e.sets.filter(filled) })).filter((e) => e.sets.length > 0);
    save.mutate(
      {
        id: workout?.id ?? uuid(),
        name: name.trim(),
        started_at: started,
        ended_at: ended,
        notes: notes.trim() || null,
        sets: kept.flatMap((e, exerciseIndex) =>
          e.sets.map((s, setIndex) => ({
            rpe: s.saved?.rpe ?? null,
            duration_s: s.saved?.duration_s ?? null,
            distance_m: s.saved?.distance_m ?? null,
            notes: s.saved?.notes ?? null,
            id: s.id,
            exercise_id: e.exercise_id,
            exercise_order: exerciseIndex + 1,
            set_order: setIndex + 1,
            set_type: s.set_type,
            weight_kg: parseDecimal(s.weight),
            reps: s.reps ? Number(s.reps) : null,
            completed: true,
            completed_at: s.saved?.completed_at ? new Date(Date.parse(s.saved.completed_at) + shift).toISOString() : started,
          })),
        ),
      },
      { onSuccess: (saved) => onSaved(saved.id) },
    );
  };

  return (
    <>
      <header className="sticky top-0 z-20 -mx-4 mb-3 border-b border-zinc-800 bg-zinc-950/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1">
            <button aria-label="Zpět bez uložení" onClick={onClose} className="-ml-2 flex size-11 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800">
              <ChevronLeft size={24} />
            </button>
            <h1 className="truncate text-xl font-semibold">{workout ? "Upravit trénink" : "Zapsat starší trénink"}</h1>
          </div>
          <Button disabled={!valid || save.isPending} onClick={submit}>
            Uložit
          </Button>
        </div>
      </header>

      <div className="space-y-2">
        {save.isError && <p className="px-1 text-sm text-amber-300">Uložení se nepovedlo, zkus to znovu.</p>}
        <Card className="space-y-2">
          <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-2">
            <label className="block text-sm text-zinc-400">
              Název
              <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={field} />
            </label>
            <label className="block text-sm text-zinc-400">
              Délka (min)
              <input inputMode="numeric" value={duration} onFocus={selectAll} onChange={(e) => setDuration(e.target.value.replace(/\D/g, ""))} className={field} />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm text-zinc-400">
              Datum
              <input type="date" value={date} max={isoDate()} onChange={(e) => setDate(e.target.value)} className={field} />
            </label>
            <label className="block text-sm text-zinc-400">
              Začátek
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={field} />
            </label>
          </div>
          <label className="block text-sm text-zinc-400">
            Poznámka
            <input value={notes} onChange={(e) => setNotes(e.target.value)} className={field} />
          </label>
        </Card>

        {items.map((item, index) => (
          <div key={item.key} {...reorder.itemProps(index)} className="rounded-(--radius-card) data-dragging:bg-zinc-950 data-dragging:shadow-2xl">
            <Card className="px-2 py-1.5">
              <div className="flex items-center gap-1">
                <button type="button" aria-label="Přetáhnout cvik" {...reorder.handleProps(index)} className="flex size-9 shrink-0 items-center justify-center rounded-lg text-zinc-500 select-none active:bg-zinc-700">
                  <GripVertical size={16} />
                </button>
                <h2 className="min-w-0 flex-1 truncate font-semibold">{item.name}</h2>
                <span className="shrink-0 text-xs text-zinc-500">{GROUP_LABELS[item.muscle_group] ?? ""}</span>
                <button
                  type="button"
                  aria-label="Odebrat cvik"
                  onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}
                  className="flex size-9 shrink-0 items-center justify-center rounded-lg text-zinc-500 active:bg-zinc-700 active:text-red-300"
                >
                  <Trash2 size={15} />
                </button>
              </div>
              <TableHeader columns={["Série", "kg", "Opak.", ""]} className={EDITOR_COLS} />
              <div className="space-y-1">
                {item.sets.map((set, setIndex) => (
                  <div key={set.id} className={`grid items-center gap-1.5 px-1 ${EDITOR_COLS}`}>
                    <SetLabel
                      types={item.sets.map((x) => x.set_type)}
                      index={setIndex}
                      onType={(set_type) => patchSet(index, setIndex, { set_type })}
                      onRemove={() => removeSet(index, setIndex)}
                    />
                    <input
                      aria-label={`kg, série ${setIndex + 1}`}
                      inputMode="decimal"
                      placeholder="kg"
                      value={set.weight}
                      onChange={(e) => patchSet(index, setIndex, { weight: e.target.value.replace(/[^\d.,]/g, "") })}
                      onFocus={selectAll}
                      className={cellInput()}
                    />
                    <input
                      aria-label={`opakování, série ${setIndex + 1}`}
                      inputMode="numeric"
                      placeholder="opak."
                      value={set.reps}
                      onChange={(e) => patchSet(index, setIndex, { reps: e.target.value.replace(/\D/g, "") })}
                      onFocus={selectAll}
                      className={cellInput()}
                    />
                    <button
                      type="button"
                      aria-label="Odebrat sérii"
                      onClick={() => removeSet(index, setIndex)}
                      className="flex size-9 items-center justify-center rounded-lg text-zinc-500 active:bg-zinc-700"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <AddSetButton
                onClick={() =>
                  patchExercise(index, (e) => {
                    const last = e.sets.at(-1);
                    return { ...e, sets: [...e.sets, { id: uuid(), set_type: "normal", weight: last?.weight ?? "", reps: last?.reps ?? "" }] };
                  })
                }
              />
            </Card>
          </div>
        ))}
        {items.length === 0 && <p className="px-1 py-2 text-sm text-zinc-500">Zatím žádný cvik.</p>}

        <Button variant="ghost" className="w-full" onClick={() => setPicking(true)}>
          + Přidat cvik
        </Button>
      </div>

      {picking && (
        <ExercisePicker
          onClose={() => setPicking(false)}
          onPick={(exercise) => {
            setPicking(false);
            setItems((prev) => [
              ...prev,
              {
                key: uuid(),
                exercise_id: exercise.id,
                name: exercise.name,
                muscle_group: exercise.muscle_group,
                sets: [{ id: uuid(), set_type: "normal", weight: "", reps: "" }],
              },
            ]);
          }}
        />
      )}
    </>
  );
}
