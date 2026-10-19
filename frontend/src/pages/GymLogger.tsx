import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, CloudOff, GripVertical, List, Pencil } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  type Exercise,
  fetchLastPerformance,
  gymKeys,
  type LastPerformance,
  SYNC_SCOPE,
  type SetBody,
  type SetType,
  type Template,
  type TemplateSet,
  useExercises,
  useHistory,
  type ServerWorkout,
  useActiveServerWorkout,
  useTemplates,
  pullServerSets,
  useWorkout,
} from "../api/gym";
import { type ChatResponse, sendVoice } from "../api/coach";
import { DraftCard } from "../components/DraftCard";
import { Card, PageHeader } from "../components/Layout";
import { Markdown } from "../components/Markdown";
import { VoiceRecorder } from "../components/VoiceRecorder";
import { errorText } from "./AiCoach";
import { RestTimer, PRESETS, restPreset, setRestPreset, startRest } from "../components/RestTimer";
import { ExercisePicker } from "../components/gym/ExercisePicker";
import { AddSetButton, SetLabel, TableHeader, cellInput, selectAll } from "../components/gym/SetTable";
import { PrBadges } from "../components/gym/PersonalRecords";
import { TemplateEditor } from "../components/gym/TemplateEditor";
import { WorkoutDetail } from "../components/gym/WorkoutDetail";
import { WorkoutEditor } from "../components/gym/WorkoutEditor";
import { Button, Pager, Segmented, Sheet, parseDecimal } from "../components/ui";
import { type ActiveWorkout, type LocalExercise, type LocalSet, saveActiveWorkout, useActiveWorkout } from "../lib/activeWorkout";
import { formatDay, formatNumber, formatTime } from "../lib/format";
import { moveItem, useDragReorder } from "../lib/useDragReorder";
import { uuid } from "../lib/uuid";

/** Sync helpers: every call is an idempotent PUT/DELETE queued in order and persisted while offline. */
function useGymSync() {
  const putWorkout = useMutation<unknown, Error, { id: string; body: Record<string, unknown> }>({ mutationKey: ["gym", "workout"], scope: SYNC_SCOPE });
  const putSet = useMutation<unknown, Error, { workoutId: string; setId: string; body: SetBody }>({ mutationKey: ["gym", "set"], scope: SYNC_SCOPE });
  const deleteSet = useMutation<unknown, Error, { setId: string }>({ mutationKey: ["gym", "delete-set"], scope: SYNC_SCOPE });
  const discard = useMutation<unknown, Error, { id: string }>({ mutationKey: ["gym", "discard"], scope: SYNC_SCOPE });
  return { putWorkout: putWorkout.mutate, putSet: putSet.mutate, deleteSet: deleteSet.mutate, discard: discard.mutate };
}

const setBody = (exercise: LocalExercise, exerciseOrder: number, set: LocalSet, setOrder: number): SetBody => ({
  exercise_id: exercise.exercise_id,
  exercise_order: exerciseOrder,
  set_order: setOrder,
  set_type: set.set_type,
  weight_kg: parseDecimal(set.weight),
  reps: set.reps ? Math.round(parseDecimal(set.reps) ?? 0) : null,
  completed: true,
  completed_at: set.completed_at,
});

/** Planned sets from the last session of the exercise (ghost values), or one empty set. */
function plannedSets(last: LastPerformance | null, count?: number): LocalSet[] {
  const source = last?.sets.length ? last.sets : [{ set_type: "normal" as const, weight_kg: null, reps: null }];
  const n = count ?? source.length;
  return Array.from({ length: n }, (_, i) => {
    const s = source[Math.min(i, source.length - 1)];
    return {
      id: uuid(),
      set_type: s.set_type,
      weight: s.weight_kg !== null ? formatNumber(s.weight_kg, s.weight_kg % 1 ? 1 : 0) : "",
      reps: s.reps !== null ? String(s.reps) : "",
      completed: false,
      completed_at: null,
    };
  });
}

/** Sets of a template exercise; anything the template leaves blank falls back to the last session (ghost values). */
function templateSets(sets: TemplateSet[], last: LastPerformance | null): LocalSet[] {
  const ghost = plannedSets(last, sets.length);
  return sets.map((s, i) => ({
    ...ghost[i],
    set_type: s.set_type,
    weight: s.weight_kg !== null ? formatNumber(s.weight_kg, s.weight_kg % 1 ? 1 : 0) : ghost[i].weight,
    reps: s.reps !== null ? String(s.reps) : ghost[i].reps,
  }));
}

const HISTORY_PAGE_SIZE = 8;

// The charts (recharts) load only when the Grafy tab is opened
const GymStats = lazy(() => import("../components/gym/GymStats").then((m) => ({ default: m.GymStats })));
const VIEWS = [
  ["log", "Trénink"],
  ["stats", "Grafy"],
] as const;

export function GymLogger() {
  const workout = useActiveWorkout();
  return (
    <>
      {workout ? <ActiveWorkoutView workout={workout} /> : <StartView />}
      <RestTimer />
    </>
  );
}

function StartView() {
  const templates = useTemplates();
  const history = useHistory();
  const queryClient = useQueryClient();
  const { putWorkout, discard } = useGymSync();
  const exercisesQuery = useExercises();
  const active = useActiveServerWorkout();
  const [starting, setStarting] = useState(false);
  const [editing, setEditing] = useState<Template | "new" | null>(null);
  // By id: the summary is read from the history, so it reflects edits (and a just-logged past workout)
  const [viewing, setViewing] = useState<string | null>(null);
  const [loggingPast, setLoggingPast] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [historyPage, setHistoryPage] = useState(0);
  const [params, setParams] = useSearchParams();
  const view = params.get("v") === "stats" ? "stats" : "log";

  const discardOpen = (id: string) => {
    discard({ id });
    queryClient.setQueryData(["workouts", "active"], null);
    setConfirmDiscard(false);
  };

  /** A workout still open on the server (started on another device or before a reinstall): continue it here. */
  const resume = (server: ServerWorkout) => {
    const byOrder = new Map<number, LocalExercise>();
    for (const s of [...server.sets].sort((a, b) => a.exercise_order - b.exercise_order || a.set_order - b.set_order)) {
      const known = exercisesQuery.data?.find((e) => e.id === s.exercise_id);
      const exercise = byOrder.get(s.exercise_order) ?? {
        exercise_id: s.exercise_id,
        name: known?.name ?? `#${s.exercise_id}`,
        muscle_group: known?.muscle_group ?? "",
        sets: [],
        last: null,
      };
      exercise.sets.push({
        id: s.id,
        set_type: s.set_type,
        weight: s.weight_kg !== null ? formatNumber(s.weight_kg, s.weight_kg % 1 ? 1 : 0) : "",
        reps: s.reps !== null ? String(s.reps) : "",
        completed: s.completed,
        completed_at: s.completed_at,
      });
      byOrder.set(s.exercise_order, exercise);
    }
    saveActiveWorkout({ id: server.id, name: server.name, started_at: server.started_at, exercises: [...byOrder.values()] });
  };

  const start = async (name: string, template?: Template) => {
    setStarting(true);
    const exercises: LocalExercise[] = [];
    for (const item of template?.exercises ?? []) {
      const last = await fetchLastPerformance(queryClient, item.exercise_id).catch(() => null);
      const known = queryClient.getQueryData<Exercise[]>(gymKeys.exercises)?.find((e) => e.id === item.exercise_id);
      exercises.push({
        exercise_id: item.exercise_id,
        name: item.name,
        muscle_group: known?.muscle_group ?? "",
        sets: templateSets(item.sets, last),
        last,
      });
    }
    const workout: ActiveWorkout = { id: uuid(), name, started_at: new Date().toISOString(), exercises };
    saveActiveWorkout(workout);
    putWorkout({ id: workout.id, body: { name, started_at: workout.started_at } });
    setStarting(false);
  };

  if (editing) {
    return <TemplateEditor template={editing === "new" ? null : editing} exercises={exercisesQuery.data ?? []} onClose={() => setEditing(null)} />;
  }
  if (loggingPast) {
    return (
      <WorkoutEditor
        workout={null}
        exercises={exercisesQuery.data ?? []}
        onClose={() => setLoggingPast(false)}
        onSaved={(id) => (setLoggingPast(false), setViewing(id))}
      />
    );
  }
  const workouts = history.data ?? [];
  const viewed = viewing ? workouts.find((w) => w.id === viewing) : undefined;
  if (viewed) return <WorkoutDetail summary={viewed} onBack={() => setViewing(null)} />;
  if (viewing && history.isFetching) return <p className="animate-pulse px-1 pt-6 text-sm text-zinc-500">Načítám…</p>;

  const pages = Math.ceil(workouts.length / HISTORY_PAGE_SIZE);
  const shownPage = Math.min(historyPage, Math.max(pages - 1, 0));

  return (
    <>
      <PageHeader
        title="Gym"
        action={
          <Link to="/gym/exercises" className="flex items-center gap-1.5 rounded-full p-2 text-sm text-zinc-400 active:bg-zinc-800">
            <List size={18} /> Cviky
          </Link>
        }
      />
      <div className="space-y-3">
        <Segmented options={VIEWS} value={view} onChange={(v) => setParams(v === "stats" ? { v } : {}, { replace: true })} />
        {view === "stats" ? (
          <Suspense fallback={<p className="text-zinc-500">Načítám…</p>}>
            <GymStats />
          </Suspense>
        ) : (
          <>
            {active.data && (
              <Card className="border-emerald-700">
                <h2 className="font-semibold">Rozdělaný trénink</h2>
                <p className="mb-3 text-sm text-zinc-400">
                  {active.data.name} · od {formatDay(active.data.started_at)} {formatTime(active.data.started_at)} · {active.data.sets.length} sérií
                </p>
                <div className="grid grid-cols-[1fr_auto] gap-2">
                  <Button onClick={() => resume(active.data!)}>Pokračovat</Button>
                  <Button variant="danger" onClick={() => setConfirmDiscard(true)}>
                    Zahodit
                  </Button>
                </div>
              </Card>
            )}

            <Card>
              <h2 className="mb-2 font-semibold">Začít trénink</h2>
              <div className="space-y-1.5">
                {templates.data?.map((t) => (
                  <div key={t.id} className="flex items-stretch gap-1 rounded-xl bg-zinc-800/70">
                    <button disabled={starting} onClick={() => start(t.name, t)} className="flex min-w-0 flex-1 items-center gap-3 rounded-xl px-3 py-2 text-left active:bg-zinc-700">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2">
                          <span className="truncate font-medium">{t.name}</span>
                          <span className="shrink-0 text-xs text-zinc-500">
                            {t.exercises.length} cviků · {t.exercises.reduce((n, e) => n + e.sets.length, 0)} sérií
                          </span>
                        </div>
                        <div className="truncate text-xs text-zinc-400">{t.exercises.map((e) => e.name).join(", ")}</div>
                      </div>
                      <ChevronRight size={18} className="shrink-0 text-zinc-500" />
                    </button>
                    <button
                      aria-label={`Upravit šablonu ${t.name}`}
                      onClick={() => setEditing(t)}
                      className="flex w-11 shrink-0 items-center justify-center rounded-xl text-zinc-400 active:bg-zinc-700"
                    >
                      <Pencil size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Button variant="ghost" disabled={starting} onClick={() => start("Trénink")}>
                  Prázdný trénink
                </Button>
                <Button variant="ghost" className="px-2 whitespace-nowrap" onClick={() => setEditing("new")}>
                  + Nová šablona
                </Button>
              </div>
            </Card>

            <Card>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-semibold">Historie</h2>
                <Pager page={shownPage} pages={pages} onChange={setHistoryPage} />
              </div>
              <ul className="divide-y divide-zinc-800">
                {workouts.slice(shownPage * HISTORY_PAGE_SIZE, (shownPage + 1) * HISTORY_PAGE_SIZE).map((w) => (
                  <li key={w.id}>
                    <button onClick={() => setViewing(w.id)} className="flex w-full items-center gap-2 py-2.5 text-left text-sm active:bg-zinc-800/50">
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">{w.name}</div>
                        <div className="text-xs text-zinc-400">
                          {formatDay(w.started_at)} · {w.set_count} sérií
                          {w.duration_min !== null && ` · ${w.duration_min} min${w.ended_by === "user" ? "" : " (odhad)"}`}
                        </div>
                        <PrBadges prs={w.prs} />
                      </div>
                      <div className="shrink-0 tabular-nums text-zinc-300">{formatNumber(w.total_volume_kg)} kg</div>
                      <ChevronRight size={16} className="shrink-0 text-zinc-600" />
                    </button>
                  </li>
                ))}
              </ul>
              {history.isSuccess && workouts.length === 0 && <p className="py-4 text-sm text-zinc-500">Zatím žádný trénink.</p>}
              <Button variant="ghost" className="mt-2 w-full" onClick={() => setLoggingPast(true)}>
                + Zapsat starší trénink
              </Button>
            </Card>
          </>
        )}
      </div>

      {confirmDiscard && active.data && (
        <DiscardSheet
          setCount={active.data.sets.length}
          onCancel={() => setConfirmDiscard(false)}
          onConfirm={() => discardOpen(active.data!.id)}
        />
      )}
    </>
  );
}

/** Confirmation before an unfinished workout (and every set already saved for it) is deleted. */
function DiscardSheet({ setCount, onCancel, onConfirm }: { setCount: number; onCancel: () => void; onConfirm: () => void }) {
  return (
    <Sheet title="Zahodit trénink?" onClose={onCancel}>
      <p className="mb-4 text-sm text-zinc-400">
        Trénink se smaže, včetně {setCount} už uložených sérií. Nepůjde vrátit.
      </p>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Zpět
        </Button>
        <Button variant="danger" onClick={onConfirm}>
          Zahodit
        </Button>
      </div>
    </Sheet>
  );
}

function ActiveWorkoutView({ workout }: { workout: ActiveWorkout }) {
  const queryClient = useQueryClient();
  const sync = useGymSync();
  const pending = useIsMutating({ mutationKey: ["gym"] });
  const server = useWorkout(workout.id);
  const [picking, setPicking] = useState(false);
  const [confirmFinish, setConfirmFinish] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [voice, setVoice] = useState<{ busy: boolean; response?: ChatResponse; error?: string } | null>(null);
  const elapsed = useElapsed(workout.started_at);

  const dictate = async (audio: Blob) => {
    setVoice({ busy: true });
    try {
      const response = await sendVoice(audio, { workoutId: workout.id, model: "fast" });
      if (response.saved_sets.length) await pullServerSets(queryClient, workout.id);
      setVoice({ busy: false, response });
    } catch (error) {
      setVoice({ busy: false, error: errorText(error) });
    }
  };

  // The server may have closed it (2 h idle auto-finish) or another device may have finished it
  useEffect(() => {
    if (server.data?.ended_at) saveActiveWorkout(null);
  }, [server.data?.ended_at]);

  const update = (exercises: LocalExercise[]) => saveActiveWorkout({ ...workout, exercises });

  const syncSet = (exerciseIndex: number, setIndex: number, exercises = workout.exercises) => {
    const exercise = exercises[exerciseIndex];
    const set = exercise.sets[setIndex];
    if (!set.completed) return;
    sync.putSet({ workoutId: workout.id, setId: set.id, body: setBody(exercise, exerciseIndex + 1, set, setIndex + 1) });
  };

  const changeSet = (exerciseIndex: number, setIndex: number, patch: Partial<LocalSet>, syncNow = false) => {
    const exercises = workout.exercises.map((e, i) =>
      i !== exerciseIndex ? e : { ...e, sets: e.sets.map((s, j) => (j === setIndex ? { ...s, ...patch } : s)) },
    );
    update(exercises);
    if (syncNow) syncSet(exerciseIndex, setIndex, exercises);
  };

  const toggleComplete = (exerciseIndex: number, setIndex: number) => {
    const set = workout.exercises[exerciseIndex].sets[setIndex];
    if (set.completed) {
      changeSet(exerciseIndex, setIndex, { completed: false, completed_at: null });
      sync.deleteSet({ setId: set.id });
    } else {
      changeSet(exerciseIndex, setIndex, { completed: true, completed_at: new Date().toISOString() }, true);
      startRest();
    }
  };

  const addSet = (exerciseIndex: number) => {
    const exercise = workout.exercises[exerciseIndex];
    const previous = exercise.sets.at(-1);
    const set: LocalSet = {
      id: uuid(),
      set_type: "normal",
      weight: previous?.weight ?? "",
      reps: previous?.reps ?? "",
      completed: false,
      completed_at: null,
    };
    update(workout.exercises.map((e, i) => (i === exerciseIndex ? { ...e, sets: [...e.sets, set] } : e)));
  };

  const removeSet = (exerciseIndex: number, setIndex: number) => {
    const set = workout.exercises[exerciseIndex].sets[setIndex];
    if (set.completed) sync.deleteSet({ setId: set.id });
    update(workout.exercises.map((e, i) => (i === exerciseIndex ? { ...e, sets: e.sets.filter((_, j) => j !== setIndex) } : e)));
  };

  const addExercise = async (exercise: Exercise) => {
    setPicking(false);
    const last = await fetchLastPerformance(queryClient, exercise.id).catch(() => null);
    update([
      ...workout.exercises,
      { exercise_id: exercise.id, name: exercise.name, muscle_group: exercise.muscle_group, sets: plannedSets(last), last },
    ]);
  };

  const moveExercise = (from: number, to: number) => {
    const exercises = moveItem(workout.exercises, from, to);
    update(exercises);
    // Completed sets carry their exercise_order: re-send those whose exercise changed position
    for (let i = Math.min(from, to); i <= Math.max(from, to); i++) exercises[i].sets.forEach((_, s) => syncSet(i, s, exercises));
  };
  const reorder = useDragReorder(moveExercise);

  const finish = () => {
    // Every completed set once more before the finish (idempotent PUTs, same queue): repairs any set whose
    // earlier write was dropped, because the local copy is gone after this
    workout.exercises.forEach((exercise, e) => exercise.sets.forEach((_, s) => syncSet(e, s)));
    sync.putWorkout({ id: workout.id, body: { ended_at: new Date().toISOString() } });
    saveActiveWorkout(null);
    setConfirmFinish(false);
  };

  const discard = () => {
    sync.discard({ id: workout.id });
    queryClient.setQueryData(["workouts", "active"], null);
    saveActiveWorkout(null);
  };

  const done = workout.exercises.reduce((n, e) => n + e.sets.filter((s) => s.completed).length, 0);

  return (
    <>
      <header className="sticky top-0 z-20 -mx-4 mb-3 border-b border-zinc-800 bg-zinc-950/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold">{workout.name}</h1>
            <p className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="tabular-nums">{elapsed}</span> · {done} sérií
              {pending > 0 && (
                <span className="inline-flex items-center gap-1 text-amber-300">
                  <CloudOff size={12} /> čeká {pending}
                </span>
              )}
            </p>
          </div>
          <Button onClick={() => setConfirmFinish(true)}>Dokončit</Button>
        </div>
      </header>

      <div className="space-y-2">
        {workout.exercises.map((exercise, exerciseIndex) => (
          <div key={`${exercise.exercise_id}-${exerciseIndex}`} {...reorder.itemProps(exerciseIndex)} className="rounded-(--radius-card) data-dragging:bg-zinc-950 data-dragging:shadow-2xl">
            <Card className="px-2 py-1.5">
              <div className="flex items-center gap-1">
                <button type="button" aria-label="Přetáhnout cvik" {...reorder.handleProps(exerciseIndex)} className="flex size-9 shrink-0 items-center justify-center rounded-lg text-zinc-500 select-none active:bg-zinc-700">
                  <GripVertical size={16} />
                </button>
                <h2 className="min-w-0 flex-1 truncate font-semibold">{exercise.name}</h2>
                <span className="shrink-0 pr-2 text-xs tabular-nums text-zinc-500">
                  {exercise.sets.filter((x) => x.completed).length}/{exercise.sets.length}
                </span>
              </div>
              <TableHeader columns={["Série", "Minule", "kg", "Opak.", ""]} className={ACTIVE_COLS} />
              <div className="space-y-1">
                {exercise.sets.map((set, setIndex) => (
                  <SetRow
                    key={set.id}
                    index={setIndex}
                    set={set}
                    types={exercise.sets.map((x) => x.set_type)}
                    ghost={exercise.last?.sets[setIndex]}
                    onChange={(patch) => changeSet(exerciseIndex, setIndex, patch)}
                    onCommit={(patch) => changeSet(exerciseIndex, setIndex, patch ?? {}, true)}
                    onToggle={() => toggleComplete(exerciseIndex, setIndex)}
                    onRemove={() => removeSet(exerciseIndex, setIndex)}
                  />
                ))}
              </div>
              <AddSetButton onClick={() => addSet(exerciseIndex)} />
            </Card>
          </div>
        ))}

        <Button variant="ghost" className="w-full" onClick={() => setPicking(true)}>
          + Přidat cvik
        </Button>
        <RestPresetPicker />
        <Button variant="danger" className="w-full" onClick={() => setConfirmDiscard(true)}>
          Zahodit trénink
        </Button>
      </div>

      <div className="fixed right-4 bottom-[calc(env(safe-area-inset-bottom)+9.5rem)] z-20 md:bottom-24">
        <VoiceRecorder onRecorded={dictate} disabled={voice?.busy} className="size-14 bg-emerald-600 text-on-accent shadow-lg" />
      </div>
      {voice && (
        <Sheet title="Diktování" onClose={() => setVoice(null)}>
          {voice.busy && <p className="animate-pulse text-zinc-400">Zpracovávám nahrávku…</p>}
          {voice.error && <p className="text-amber-300">{voice.error}</p>}
          {voice.response && (
            <>
              <Markdown text={voice.response.reply} />
              {voice.response.drafts.map((d, i) => (
                <DraftCard key={i} draft={d} onSaved={(id) => void pullServerSets(queryClient, id)} />
              ))}
            </>
          )}
        </Sheet>
      )}
      {confirmDiscard && <DiscardSheet setCount={done} onCancel={() => setConfirmDiscard(false)} onConfirm={discard} />}
      {picking && <ExercisePicker onPick={addExercise} onClose={() => setPicking(false)} />}
      {confirmFinish && (
        <Sheet title="Dokončit trénink?" onClose={() => setConfirmFinish(false)}>
          <p className="mb-4 text-sm text-zinc-400">
            Uloží se {done} odcvičených sérií. Neodškrtnuté série se zahodí.
            {pending > 0 && " Některé změny ještě čekají na připojení, odešlou se samy."}
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" onClick={() => setConfirmFinish(false)}>
              Zpět
            </Button>
            <Button onClick={finish}>Dokončit</Button>
          </div>
          <Button variant="danger" className="mt-2 w-full" onClick={() => (setConfirmFinish(false), setConfirmDiscard(true))}>
            Zahodit trénink
          </Button>
        </Sheet>
      )}
    </>
  );
}

const ACTIVE_COLS = "grid-cols-[2rem_minmax(0,1fr)_4.25rem_3.5rem_2.25rem]";

function SetRow({
  index,
  set,
  types,
  ghost,
  onChange,
  onCommit,
  onToggle,
  onRemove,
}: {
  index: number;
  set: LocalSet;
  types: SetType[];
  ghost?: LastPerformance["sets"][number];
  onChange: (patch: Partial<LocalSet>) => void;
  onCommit: (patch?: Partial<LocalSet>) => void;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const ghostWeight = ghost?.weight_kg != null ? formatNumber(ghost.weight_kg, ghost.weight_kg % 1 ? 1 : 0) : null;
  return (
    <div className={`grid items-center gap-1.5 rounded-lg px-1 py-0.5 ${ACTIVE_COLS} ${set.completed ? "bg-emerald-500/15" : ""}`}>
      <SetLabel types={types} index={index} onType={(set_type) => onCommit({ set_type })} onRemove={onRemove} />
      {ghost ? (
        <button
          type="button"
          aria-label="Použít hodnoty z minula"
          onClick={() => onCommit({ weight: ghostWeight ?? "", reps: ghost.reps !== null ? String(ghost.reps) : "" })}
          className="h-9 truncate rounded-lg text-center text-sm tabular-nums text-zinc-500 active:bg-zinc-800"
        >
          {ghostWeight ?? "–"} × {ghost.reps ?? "–"}
        </button>
      ) : (
        <span className="text-center text-sm text-zinc-700">–</span>
      )}
      <input
        aria-label={`kg, série ${index + 1}`}
        inputMode="decimal"
        placeholder="kg"
        value={set.weight}
        onChange={(e) => onChange({ weight: e.target.value.replace(/[^\d.,]/g, "") })}
        onBlur={() => onCommit()}
        onFocus={selectAll}
        className={cellInput(set.completed)}
      />
      <input
        aria-label={`opakování, série ${index + 1}`}
        inputMode="numeric"
        placeholder="opak."
        value={set.reps}
        onChange={(e) => onChange({ reps: e.target.value.replace(/\D/g, "") })}
        onBlur={() => onCommit()}
        onFocus={selectAll}
        className={cellInput(set.completed)}
      />
      <button
        aria-label={set.completed ? "Zrušit odškrtnutí" : "Série hotová"}
        onClick={onToggle}
        className={`flex size-9 items-center justify-center rounded-lg ${set.completed ? "bg-emerald-500 text-on-accent" : "bg-zinc-800 text-zinc-400 active:bg-zinc-700"}`}
      >
        <Check size={18} strokeWidth={3} />
      </button>
    </div>
  );
}

function RestPresetPicker() {
  const [preset, setPreset] = useState(restPreset());
  return (
    <div className="flex items-center justify-between gap-2 px-1 text-sm text-zinc-400">
      Pauza
      <Segmented
        options={PRESETS.map((s) => [s, `${s / 60 >= 1 && s % 60 === 0 ? `${s / 60} min` : `${s} s`}`] as const)}
        value={preset}
        onChange={(s) => (setPreset(s), setRestPreset(s))}
      />
    </div>
  );
}

function useElapsed(startedAt: string): string {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min · od ${formatTime(startedAt)}`;
}
