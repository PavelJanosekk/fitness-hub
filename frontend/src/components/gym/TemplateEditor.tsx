import { ChevronLeft, GripVertical, Trash2, X } from "lucide-react";
import { useState } from "react";
import { type Exercise, type SetType, type Template, useDeleteTemplate, useSaveTemplate } from "../../api/gym";
import { formatNumber } from "../../lib/format";
import { moveItem, useDragReorder } from "../../lib/useDragReorder";
import { uuid } from "../../lib/uuid";
import { Card } from "../Layout";
import { Button, Sheet, parseDecimal } from "../ui";
import { ExercisePicker, GROUP_LABELS } from "./ExercisePicker";
import { AddSetButton, SetLabel, TableHeader, cellInput, selectAll } from "./SetTable";

type DraftSet = { set_type: SetType; weight: string; reps: string };
type DraftExercise = { exercise_id: number; name: string; muscle_group: string; sets: DraftSet[] };

const fmt = (value: number | null) => (value === null ? "" : formatNumber(value, value % 1 ? 1 : 0));
const EDITOR_COLS = "grid-cols-[2rem_minmax(0,1fr)_minmax(0,1fr)_2.25rem]";

/** Create or edit a template: name, exercises (order, add, remove) and the planned sets with kg × reps. */
export function TemplateEditor({ template, exercises, onClose }: { template: Template | null; exercises: Exercise[]; onClose: () => void }) {
  const save = useSaveTemplate();
  const remove = useDeleteTemplate();
  const [name, setName] = useState(template?.name ?? "");
  const [items, setItems] = useState<DraftExercise[]>(() =>
    (template?.exercises ?? []).map((e) => ({
      exercise_id: e.exercise_id,
      name: e.name,
      muscle_group: exercises.find((x) => x.id === e.exercise_id)?.muscle_group ?? "",
      sets: e.sets.map((s) => ({ set_type: s.set_type, weight: fmt(s.weight_kg), reps: s.reps === null ? "" : String(s.reps) })),
    })),
  );
  const [picking, setPicking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const patchExercise = (index: number, patch: (e: DraftExercise) => DraftExercise) => setItems((prev) => prev.map((e, i) => (i === index ? patch(e) : e)));
  const patchSet = (index: number, setIndex: number, patch: Partial<DraftSet>) =>
    patchExercise(index, (e) => ({ ...e, sets: e.sets.map((s, j) => (j === setIndex ? { ...s, ...patch } : s)) }));
  const reorder = useDragReorder((from, to) => setItems((prev) => moveItem(prev, from, to)));

  const canSave = name.trim() !== "" && items.length > 0 && items.every((e) => e.sets.length > 0) && !save.isPending;
  const submit = () =>
    save.mutate(
      {
        id: template?.id ?? uuid(),
        name: name.trim(),
        exercises: items.map((e) => ({
          exercise_id: e.exercise_id,
          sets: e.sets.map((s) => ({ set_type: s.set_type, weight_kg: parseDecimal(s.weight), reps: s.reps ? Number(s.reps) : null })),
        })),
      },
      { onSuccess: onClose },
    );

  return (
    <>
      <header className="sticky top-0 z-20 -mx-4 mb-3 border-b border-zinc-800 bg-zinc-950/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1">
            <button aria-label="Zpět bez uložení" onClick={onClose} className="-ml-2 flex size-11 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800">
              <ChevronLeft size={24} />
            </button>
            <h1 className="truncate text-xl font-semibold">{template ? "Upravit šablonu" : "Nová šablona"}</h1>
          </div>
          <Button disabled={!canSave} onClick={submit}>
            Uložit
          </Button>
        </div>
      </header>

      <div className="space-y-2">
        {save.isError && <p className="px-1 text-sm text-amber-300">Uložení se nepovedlo, zkus to znovu.</p>}
        <input
          aria-label="Název šablony"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Název (např. Chest tri)"
          maxLength={80}
          className="h-10 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base outline-none focus:border-emerald-500"
        />

        {items.map((item, index) => (
          <div key={`${item.exercise_id}-${index}`} {...reorder.itemProps(index)} className="rounded-(--radius-card) data-dragging:bg-zinc-950 data-dragging:shadow-2xl">
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
                  <div key={setIndex} className={`grid items-center gap-1.5 px-1 ${EDITOR_COLS}`}>
                    <SetLabel
                      types={item.sets.map((x) => x.set_type)}
                      index={setIndex}
                      canRemove={item.sets.length > 1}
                      onType={(set_type) => patchSet(index, setIndex, { set_type })}
                      onRemove={() => patchExercise(index, (e) => ({ ...e, sets: e.sets.filter((_, j) => j !== setIndex) }))}
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
                      disabled={item.sets.length === 1}
                      onClick={() => patchExercise(index, (e) => ({ ...e, sets: e.sets.filter((_, j) => j !== setIndex) }))}
                      className="flex size-9 items-center justify-center rounded-lg text-zinc-500 active:bg-zinc-700 disabled:text-zinc-800"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <AddSetButton onClick={() => patchExercise(index, (e) => ({ ...e, sets: [...e.sets, { ...(e.sets.at(-1) ?? { weight: "", reps: "" }), set_type: "normal" }] }))} />
            </Card>
          </div>
        ))}

        <Button variant="ghost" className="w-full" onClick={() => setPicking(true)}>
          + Přidat cvik
        </Button>
        {template && (
          <Button variant="danger" className="w-full" onClick={() => setConfirmDelete(true)}>
            Smazat šablonu
          </Button>
        )}
      </div>

      {picking && (
        <ExercisePicker
          onClose={() => setPicking(false)}
          onPick={(exercise) => {
            setPicking(false);
            setItems((prev) => [
              ...prev,
              { exercise_id: exercise.id, name: exercise.name, muscle_group: exercise.muscle_group, sets: [{ set_type: "normal", weight: "", reps: "" }] },
            ]);
          }}
        />
      )}
      {confirmDelete && template && (
        <Sheet title="Smazat šablonu?" onClose={() => setConfirmDelete(false)}>
          <p className="mb-4 text-sm text-zinc-400">Šablona „{template.name}“ se smaže. Odcvičené tréninky v historii zůstanou.</p>
          {remove.isError && <p className="mb-3 text-sm text-amber-300">Smazání se nepovedlo, zkus to znovu.</p>}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Zpět
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(template.id, { onSuccess: onClose })}>
              Smazat
            </Button>
          </div>
        </Sheet>
      )}
    </>
  );
}
