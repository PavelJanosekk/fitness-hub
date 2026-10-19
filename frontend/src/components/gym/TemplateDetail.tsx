import { ChevronLeft, Pencil } from "lucide-react";
import { useState } from "react";
import { type Exercise, type Template, useDeleteTemplate } from "../../api/gym";
import { formatNumber } from "../../lib/format";
import { Card } from "../Layout";
import { Button, Sheet } from "../ui";
import { GROUP_LABELS } from "./exercises";
import { SET_TYPES } from "./SetTable";

/** A template's exercises and planned sets; from here it is started, edited or deleted. */
export function TemplateDetail({
  template,
  exercises,
  starting,
  onBack,
  onStart,
  onEdit,
}: {
  template: Template;
  exercises: Exercise[];
  starting: boolean;
  onBack: () => void;
  onStart: () => void;
  onEdit: () => void;
}) {
  const remove = useDeleteTemplate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const setCount = template.exercises.reduce((n, e) => n + e.sets.length, 0);

  return (
    <>
      <header className="sticky top-0 z-20 -mx-4 mb-3 border-b border-zinc-800 bg-zinc-950/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center gap-2">
          <button aria-label="Zpět na šablony" onClick={onBack} className="-ml-2 flex size-11 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800">
            <ChevronLeft size={24} />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold">{template.name}</h1>
            <p className="text-xs text-zinc-400">
              {template.exercises.length} cviků · {setCount} sérií
            </p>
          </div>
          <button aria-label="Upravit šablonu" onClick={onEdit} className="flex size-11 shrink-0 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800">
            <Pencil size={18} />
          </button>
        </div>
      </header>

      <div className="space-y-3">
        <Button className="w-full" disabled={starting} onClick={onStart}>
          Začít trénink
        </Button>

        {template.exercises.map((item, index) => {
          const group = exercises.find((e) => e.id === item.exercise_id)?.muscle_group ?? "";
          return (
            <Card key={`${item.exercise_id}-${index}`} className="p-3">
              <div className="mb-2 flex items-baseline justify-between gap-2 px-1">
                <h2 className="font-semibold">{item.name}</h2>
                <span className="text-xs text-zinc-500">{GROUP_LABELS[group] ?? ""}</span>
              </div>
              <ol className="divide-y divide-zinc-800/70 text-sm">
                {item.sets.map((set, i) => (
                  <li key={i} className="flex items-baseline justify-between px-1 py-1.5">
                    <span className="text-zinc-500">
                      Série {i + 1}
                      {set.set_type !== "normal" && ` · ${SET_TYPES[set.set_type].label.toLowerCase()}`}
                    </span>
                    <span className="tabular-nums">
                      {set.weight_kg !== null ? `${formatNumber(set.weight_kg, set.weight_kg % 1 ? 1 : 0)} kg` : "– kg"} × {set.reps ?? "–"}
                    </span>
                  </li>
                ))}
              </ol>
            </Card>
          );
        })}
        {template.exercises.some((e) => e.sets.some((s) => s.weight_kg === null || s.reps === null)) && (
          <p className="px-1 text-xs text-zinc-500">Prázdné hodnoty se při startu doplní z minulého tréninku.</p>
        )}

        <Button variant="ghost" className="w-full" onClick={onEdit}>
          Upravit šablonu
        </Button>
        <Button variant="danger" className="w-full" onClick={() => setConfirmDelete(true)}>
          Smazat šablonu
        </Button>
      </div>

      {confirmDelete && (
        <Sheet title="Smazat šablonu?" onClose={() => setConfirmDelete(false)}>
          <p className="mb-4 text-sm text-zinc-400">Šablona „{template.name}“ se smaže. Odcvičené tréninky v historii zůstanou.</p>
          {remove.isError && <p className="mb-3 text-sm text-amber-300">Smazání se nepovedlo, zkus to znovu.</p>}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Zpět
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(template.id, { onSuccess: onBack })}>
              Smazat
            </Button>
          </div>
        </Sheet>
      )}
    </>
  );
}
