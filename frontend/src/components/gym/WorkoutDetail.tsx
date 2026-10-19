import { ChevronLeft, Pencil } from "lucide-react";
import { useState } from "react";
import { useDeleteWorkout, useExercises, useWorkout, type WorkoutSummary } from "../../api/gym";
import { formatDay, formatNumber, formatTime } from "../../lib/format";
import { Card } from "../Layout";
import { Button, Sheet } from "../ui";
import { GROUP_LABELS } from "./exercises";
import { PrBadge } from "./PersonalRecords";
import { WorkoutEditor } from "./WorkoutEditor";

const SET_TYPE_LABEL = { normal: "", warmup: "zahřívací", drop: "drop", failure: "do selhání" } as const;

/** A finished workout laid out like the active workout screen; "Upravit" opens the editor. */
export function WorkoutDetail({ summary, onBack }: { summary: WorkoutSummary; onBack: () => void }) {
  const workout = useWorkout(summary.id);
  const exercises = useExercises();
  const remove = useDeleteWorkout();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(false);

  const byExercise = new Map(exercises.data?.map((e) => [e.id, e]));
  const groups = new Map<number, { exerciseId: number; sets: NonNullable<typeof workout.data>["sets"] }>();
  for (const set of workout.data?.sets ?? []) {
    if (!set.completed) continue;
    const group = groups.get(set.exercise_order) ?? { exerciseId: set.exercise_id, sets: [] };
    group.sets.push(set);
    groups.set(set.exercise_order, group);
  }
  const prByExercise = new Map(summary.prs.map((pr) => [pr.exercise_id, pr]));

  if (editing && workout.data) {
    return <WorkoutEditor workout={workout.data} exercises={exercises.data ?? []} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} />;
  }

  return (
    <>
      <header className="sticky top-0 z-20 -mx-4 mb-3 border-b border-zinc-800 bg-zinc-950/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center gap-2">
          <button aria-label="Zpět na historii" onClick={onBack} className="-ml-2 flex size-11 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800">
            <ChevronLeft size={24} />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold">{summary.name}</h1>
            <p className="text-xs text-zinc-400">
              {formatDay(summary.started_at)} {formatTime(summary.started_at)} · {summary.set_count} sérií · {formatNumber(summary.total_volume_kg)} kg
              {summary.duration_min !== null && ` · ${summary.duration_min} min${summary.ended_by === "user" ? "" : " (odhad)"}`}
            </p>
          </div>
          {/* An unfinished workout is edited live on the workout screen, not here */}
          {summary.ended_at && (
            <button
              aria-label="Upravit trénink"
              disabled={!workout.data || !exercises.data}
              onClick={() => setEditing(true)}
              className="flex size-11 shrink-0 items-center justify-center rounded-full text-zinc-300 active:bg-zinc-800 disabled:text-zinc-700"
            >
              <Pencil size={18} />
            </button>
          )}
        </div>
      </header>

      <div className="space-y-3">
        {summary.prs.length > 0 && (
          <Card className="space-y-1.5">
            <h2 className="font-semibold">Rekordy</h2>
            <div className="flex flex-col items-start gap-1.5">
              {summary.prs.map((pr) => (
                <PrBadge key={pr.exercise_id} pr={pr} detail />
              ))}
            </div>
          </Card>
        )}

        {workout.isPending && <p className="animate-pulse px-1 text-sm text-zinc-500">Načítám…</p>}
        {workout.isError && <p className="px-1 text-sm text-amber-300">Trénink se nepodařilo načíst.</p>}
        {[...groups.entries()]
          .sort(([a], [b]) => a - b)
          .map(([order, { exerciseId, sets }]) => {
            const exercise = byExercise.get(exerciseId);
            const pr = prByExercise.get(exerciseId);
            return (
              <Card key={order} className="p-3">
                <div className="mb-2 flex items-baseline justify-between gap-2 px-1">
                  <h2 className="font-semibold">{exercise?.name ?? `#${exerciseId}`}</h2>
                  <span className="text-xs text-zinc-500">{GROUP_LABELS[exercise?.muscle_group ?? ""] ?? ""}</span>
                </div>
                {pr && (
                  <div className="mb-2 px-1">
                    <PrBadge pr={pr} detail />
                  </div>
                )}
                <ol className="divide-y divide-zinc-800/70 text-sm">
                  {sets.map((set, i) => (
                    <li key={set.id} className="flex items-baseline justify-between px-1 py-1.5">
                      <span className="text-zinc-500">
                        Série {i + 1}
                        {SET_TYPE_LABEL[set.set_type] && ` · ${SET_TYPE_LABEL[set.set_type]}`}
                      </span>
                      <span className="tabular-nums">
                        {set.weight_kg !== null ? formatNumber(set.weight_kg, 1) : "–"} kg × {set.reps ?? "–"}
                      </span>
                    </li>
                  ))}
                </ol>
              </Card>
            );
          })}
        {workout.data && groups.size === 0 && <p className="px-1 text-sm text-zinc-500">Tento trénink nemá žádné odcvičené série.</p>}

        {summary.ended_at && (
          <Button variant="ghost" className="w-full" disabled={!workout.data || !exercises.data} onClick={() => setEditing(true)}>
            Upravit trénink
          </Button>
        )}
        <Button variant="danger" className="w-full" onClick={() => setConfirmDelete(true)}>
          Smazat trénink
        </Button>
      </div>

      {confirmDelete && (
        <Sheet title="Smazat trénink?" onClose={() => setConfirmDelete(false)}>
          <p className="mb-4 text-sm text-zinc-400">Trénink i všechny jeho série se smažou natrvalo.</p>
          {remove.isError && <p className="mb-3 text-sm text-amber-300">Smazání se nepovedlo, zkus to znovu.</p>}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Zpět
            </Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(summary.id, { onSuccess: onBack })}>
              Smazat
            </Button>
          </div>
        </Sheet>
      )}
    </>
  );
}
