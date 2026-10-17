import { ChevronDown, ChevronLeft, ChevronUp, Trash2, X } from "lucide-react";
import { useState } from "react";
import { type Exercise, type SetType, type Template, useDeleteTemplate, useSaveTemplate } from "../../api/gym";
import { formatNumber } from "../../lib/format";
import { uuid } from "../../lib/uuid";
import { Card } from "../Layout";
import { Button, DecimalInput, Sheet, parseDecimal } from "../ui";
import { ExercisePicker, GROUP_LABELS } from "./ExercisePicker";

type DraftSet = { set_type: SetType; weight: string; reps: string };
type DraftExercise = { exercise_id: number; name: string; muscle_group: string; sets: DraftSet[] };

const fmt = (value: number | null) => (value === null ? "" : formatNumber(value, value % 1 ? 1 : 0));
const SET_TYPE_LABEL = { normal: "", warmup: "zahřívací", drop: "drop", failure: "do selhání" } as const;

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
  const move = (index: number, delta: -1 | 1) =>
    setItems((prev) => {
      const next = [...prev];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      return next;
    });

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

      <div className="space-y-3">
        {save.isError && <p className="px-1 text-sm text-amber-300">Uložení se nepovedlo, zkus to znovu.</p>}
        <input
          aria-label="Název šablony"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Název (např. Chest tri)"
          maxLength={80}
          className="min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-lg outline-none focus:border-emerald-500"
        />

        {items.map((item, index) => (
          <Card key={`${item.exercise_id}-${index}`} className="p-3">
            <div className="mb-2 flex items-center justify-between gap-1 px-1">
              <div className="min-w-0">
                <h2 className="truncate font-semibold">{item.name}</h2>
                <span className="text-xs text-zinc-500">{GROUP_LABELS[item.muscle_group] ?? ""}</span>
              </div>
              <div className="flex shrink-0 text-zinc-400">
                <IconButton label="Posunout nahoru" disabled={index === 0} onClick={() => move(index, -1)}>
                  <ChevronUp size={18} />
                </IconButton>
                <IconButton label="Posunout dolů" disabled={index === items.length - 1} onClick={() => move(index, 1)}>
                  <ChevronDown size={18} />
                </IconButton>
                <IconButton label="Odebrat cvik" onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}>
                  <Trash2 size={16} />
                </IconButton>
              </div>
            </div>
            <div className="space-y-2">
              {item.sets.map((set, setIndex) => (
                <div key={setIndex} className="flex items-center gap-2 rounded-xl bg-zinc-800/50 p-2">
                  <span className="w-14 shrink-0 text-xs text-zinc-400">
                    Série {setIndex + 1}
                    {SET_TYPE_LABEL[set.set_type] && <span className="block text-[10px] text-zinc-500">{SET_TYPE_LABEL[set.set_type]}</span>}
                  </span>
                  <DecimalInput
                    ariaLabel={`kg, série ${setIndex + 1}`}
                    placeholder="kg"
                    value={set.weight}
                    onChange={(weight) => patchExercise(index, (e) => ({ ...e, sets: e.sets.map((s, j) => (j === setIndex ? { ...s, weight } : s)) }))}
                    className="text-center"
                  />
                  <input
                    aria-label={`opakování, série ${setIndex + 1}`}
                    inputMode="numeric"
                    placeholder="opak."
                    value={set.reps}
                    onChange={(e) => {
                      const reps = e.target.value.replace(/\D/g, "");
                      patchExercise(index, (x) => ({ ...x, sets: x.sets.map((s, j) => (j === setIndex ? { ...s, reps } : s)) }));
                    }}
                    className="min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-center text-lg tabular-nums outline-none focus:border-emerald-500"
                  />
                  <IconButton
                    label="Odebrat sérii"
                    disabled={item.sets.length === 1}
                    onClick={() => patchExercise(index, (e) => ({ ...e, sets: e.sets.filter((_, j) => j !== setIndex) }))}
                  >
                    <X size={16} />
                  </IconButton>
                </div>
              ))}
            </div>
            <button
              onClick={() => patchExercise(index, (e) => ({ ...e, sets: [...e.sets, { ...(e.sets.at(-1) ?? { weight: "", reps: "" }), set_type: "normal" }] }))}
              className="mt-2 w-full rounded-xl py-2.5 text-sm text-emerald-400 active:bg-zinc-800"
            >
              + Přidat sérii
            </button>
          </Card>
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

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="flex size-11 shrink-0 items-center justify-center rounded-lg text-zinc-400 active:bg-zinc-700 disabled:text-zinc-700"
    >
      {children}
    </button>
  );
}
