import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, CloudOff, GripVertical, List, Trash2, X } from "lucide-react";
import { Fragment, lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  type Exercise,
  fetchLastPerformance,
  gymKeys,
  type LastPerformance,
  SYNC_SCOPE,
  type SetBody,
  type SetType,
  type TargetSet,
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
import { ExerciseSheet } from "../components/gym/ExerciseSheet";
import { AddSetButton, SetLabel, TableHeader, cellInput, selectAll } from "../components/gym/SetTable";
import { PrBadges } from "../components/gym/PersonalRecords";
import { SetMeta, TargetLine, TargetSheet, asTarget, kgText } from "../components/gym/Target";
import { TemplateDetail } from "../components/gym/TemplateDetail";
import { TemplateEditor } from "../components/gym/TemplateEditor";
import { WorkoutDetail } from "../components/gym/WorkoutDetail";
import { WorkoutEditor } from "../components/gym/WorkoutEditor";
import { Button, Pager, Segmented, Sheet, parseDecimal } from "../components/ui";
import {
  type ActiveWorkout,
  type LocalExercise,
  type LocalSet,
  patchActiveWorkout,
  saveActiveWorkout,
  useActiveWorkout,
} from "../lib/activeWorkout";
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
  // E35: the plan the set was pre-filled with, the confirmed RIR as RPE (3+ -> 7) and the unusual flag
  planned_weight_kg: set.planned_weight ?? null,
  planned_reps: set.planned_reps ?? null,
  role: set.role ?? null,
  rpe: set.rir != null ? 10 - set.rir : null,
  unusual: !!exercise.unusual,
});

/** RIR-based RPE back to the RIR the user picked (0-3, 3 = 3+). */
const rirFromRpe = (rpe: number | null | undefined) => (rpe == null ? null : Math.min(3, Math.max(0, Math.round(10 - rpe))));
const isWorking = (type: SetType) => type === "normal" || type === "failure";
const repsText = (reps: number | null) => (reps !== null ? String(reps) : "");

/** Planned sets: the progression target with its plan (E35), else the last session (ghost values), else one empty set. */
function plannedSets(last: LastPerformance | null): LocalSet[] {
  const target = asTarget(last?.target);
  if (target?.sets.length) {
    return target.sets.map((s) => ({
      id: uuid(),
      set_type: s.set_type,
      weight: kgText(s.weight_kg),
      reps: repsText(s.reps),
      completed: false,
      completed_at: null,
      progress: s.changed || s.priority,
      planned_weight: s.weight_kg,
      planned_reps: s.reps,
      role: s.role,
    }));
  }
  const source = last?.sets.length ? last.sets : [{ set_type: "normal" as const, weight_kg: null, reps: null }];
  return source.map((s) => ({ id: uuid(), set_type: s.set_type, weight: kgText(s.weight_kg), reps: repsText(s.reps), completed: false, completed_at: null }));
}

/** The template decides how many working sets an exercise has (E35): extra ones copy the last, surplus ones go. */
function withWorkingSets(sets: LocalSet[], count: number): LocalSet[] {
  const working = sets.filter((s) => isWorking(s.set_type));
  if (!count || working.length === count) return sets;
  if (working.length > count) {
    const surplus = new Set(working.slice(count).map((s) => s.id));
    return sets.filter((s) => !surplus.has(s.id));
  }
  const last = working.at(-1);
  if (!last) return sets;
  const at = sets.indexOf(last) + 1;
  const extra = Array.from({ length: count - working.length }, () => ({ ...last, id: uuid(), progress: false }));
  return [...sets.slice(0, at), ...extra, ...sets.slice(at)];
}

/**
 * Sets of a template exercise. With a target, the template only gives the number of working sets: every template
 * holds a snapshot of an old session (E33, E35). Without one, the template's values are the plan and anything it
 * leaves blank falls back to the last session (ghost values).
 */
function templateSets(sets: TemplateSet[], last: LastPerformance | null): LocalSet[] {
  if (asTarget(last?.target)) return withWorkingSets(plannedSets(last), sets.filter((s) => isWorking(s.set_type)).length);
  const ghost = plannedSets(last);
  return sets.map((s, i) => {
    const fallback = ghost[Math.min(i, ghost.length - 1)];
    const weight = s.weight_kg !== null ? kgText(s.weight_kg) : fallback.weight;
    const reps = s.reps !== null ? String(s.reps) : fallback.reps;
    const planned = isWorking(s.set_type) && (weight !== "" || reps !== "");
    return {
      id: uuid(),
      set_type: s.set_type,
      weight,
      reps,
      completed: false,
      completed_at: null,
      ...(planned && { planned_weight: parseDecimal(weight), planned_reps: reps ? Number(reps) : null, role: "straight" as const }),
    };
  });
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
  // By id, so the detail shows the template as saved (and closes once it's deleted)
  const [openTemplate, setOpenTemplate] = useState<string | null>(null);
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
        planned_weight: s.planned_weight_kg ?? null,
        planned_reps: s.planned_reps ?? null,
        role: s.role ?? null,
        rir: rirFromRpe(s.rpe),
      });
      exercise.unusual ||= !!s.unusual;
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
    setOpenTemplate(null);
  };

  if (editing) {
    return <TemplateEditor template={editing === "new" ? null : editing} exercises={exercisesQuery.data ?? []} onClose={() => setEditing(null)} />;
  }
  const opened = openTemplate ? templates.data?.find((t) => t.id === openTemplate) : undefined;
  if (opened) {
    return (
      <TemplateDetail
        template={opened}
        exercises={exercisesQuery.data ?? []}
        starting={starting}
        onBack={() => setOpenTemplate(null)}
        onStart={() => start(opened.name, opened)}
        onEdit={() => setEditing(opened)}
      />
    );
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
                  <button key={t.id} onClick={() => setOpenTemplate(t.id)} className="flex w-full min-w-0 items-center gap-3 rounded-xl bg-zinc-800/70 px-3 py-2 text-left active:bg-zinc-700">
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
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null);
  const [explaining, setExplaining] = useState<number | null>(null);
  const [editingExercise, setEditingExercise] = useState<Exercise | null>(null);
  const [offer, setOffer] = useState<WeightOffer | null>(null);
  const exercisesQuery = useExercises();
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

  // A weight changed by hand (E35): offer to copy it to the following unticked sets of the same block. It stays a change
  // for today; only "I příště" makes it the plan
  const commitSet = (exerciseIndex: number, setIndex: number, patch?: Partial<LocalSet>, weightBefore?: string) => {
    changeSet(exerciseIndex, setIndex, patch ?? {}, true);
    if (weightBefore === undefined) return;
    const sets = workout.exercises[exerciseIndex].sets;
    const edited = { ...sets[setIndex], ...patch };
    const before = parseDecimal(weightBefore);
    const after = parseDecimal(edited.weight);
    if (after === null || before === after) return;
    const targets = sets.flatMap((s, i) =>
      i > setIndex && !s.completed && (s.role ?? null) === (edited.role ?? null) && parseDecimal(s.weight) === before ? [i] : [],
    );
    const offPlan = edited.planned_weight != null && edited.planned_weight !== after;
    if (targets.length || offPlan) setOffer({ exerciseIndex, setIndex, weight: edited.weight, targets, previous: targets.map((i) => sets[i].weight), applied: false });
    else setOffer(null);
  };

  const copyWeight = (o: WeightOffer, weights: string[]) =>
    update(
      workout.exercises.map((e, i) =>
        i !== o.exerciseIndex ? e : { ...e, sets: e.sets.map((s, j) => (o.targets.includes(j) ? { ...s, weight: weights[o.targets.indexOf(j)] } : s)) },
      ),
    );

  // The new weight becomes the plan of its block, so the next target builds on it
  const keepForNextTime = (o: WeightOffer) => {
    const role = workout.exercises[o.exerciseIndex].sets[o.setIndex].role ?? null;
    const weight = parseDecimal(o.weight);
    const exercises = workout.exercises.map((e, i) =>
      i !== o.exerciseIndex ? e : { ...e, sets: e.sets.map((s) => ((s.role ?? null) === role && s.planned_weight != null ? { ...s, planned_weight: weight } : s)) },
    );
    update(exercises);
    exercises[o.exerciseIndex].sets.forEach((_, s) => syncSet(o.exerciseIndex, s, exercises));
    setOffer(null);
  };

  const markUnusual = (exerciseIndex: number, unusual: boolean) => {
    const exercises = workout.exercises.map((e, i) => (i === exerciseIndex ? { ...e, unusual } : e));
    update(exercises);
    exercises[exerciseIndex].sets.forEach((_, s) => syncSet(exerciseIndex, s, exercises));
  };

  // Today only: the unticked sets take the easier values, their plan stays, so the next target goes back up
  const applySuggestion = (exerciseIndex: number, suggested: TargetSet[]) => {
    update(
      workout.exercises.map((e, i) =>
        i !== exerciseIndex
          ? e
          : {
              ...e,
              sets: e.sets.flatMap((s, j) => {
                const v = suggested[j];
                if (s.completed) return [s];
                return v ? [{ ...s, weight: kgText(v.weight_kg), reps: v.reps !== null ? String(v.reps) : s.reps }] : [];
              }),
            },
      ),
    );
    setExplaining(null);
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

  // New progression settings change the target: refresh it, and re-plan the sets while none of them is checked
  const retarget = async (exerciseId: number) => {
    const last = await fetchLastPerformance(queryClient, exerciseId).catch(() => null);
    if (!last) return;
    patchActiveWorkout((w) => ({
      ...w,
      exercises: w.exercises.map((e) =>
        e.exercise_id !== exerciseId ? e : { ...e, last, sets: e.sets.some((s) => s.completed) ? e.sets : plannedSets(last) },
      ),
    }));
  };

  const moveExercise = (from: number, to: number) => {
    const exercises = moveItem(workout.exercises, from, to);
    update(exercises);
    // Completed sets carry their exercise_order: re-send those whose exercise changed position
    for (let i = Math.min(from, to); i <= Math.max(from, to); i++) exercises[i].sets.forEach((_, s) => syncSet(i, s, exercises));
  };
  const reorder = useDragReorder(moveExercise);

  const removeExercise = (index: number) => {
    setConfirmRemove(null);
    workout.exercises[index].sets.forEach((set) => set.completed && sync.deleteSet({ setId: set.id }));
    const exercises = workout.exercises.filter((_, i) => i !== index);
    update(exercises);
    // The exercises below moved up one position: re-send their completed sets with the new exercise_order
    for (let i = index; i < exercises.length; i++) exercises[i].sets.forEach((_, s) => syncSet(i, s, exercises));
  };
  // Without a completed set nothing is lost, so no confirmation
  const askRemoveExercise = (index: number) =>
    workout.exercises[index].sets.some((s) => s.completed) ? setConfirmRemove(index) : removeExercise(index);

  // `confirmRest`: the unticked sets that have reps are ticked now and saved too; the rest are dropped either way
  const finish = (confirmRest = false) => {
    const now = new Date().toISOString();
    const exercises = confirmRest
      ? workout.exercises.map((e) => ({ ...e, sets: e.sets.map((s) => (!s.completed && hasReps(s) ? { ...s, completed: true, completed_at: now } : s)) }))
      : workout.exercises;
    // Every completed set once more before the finish (idempotent PUTs, same queue): repairs any set whose
    // earlier write was dropped, because the local copy is gone after this
    exercises.forEach((exercise, e) => exercise.sets.forEach((_, s) => syncSet(e, s, exercises)));
    sync.putWorkout({ id: workout.id, body: { ended_at: now } });
    saveActiveWorkout(null);
    setConfirmFinish(false);
  };

  const discard = () => {
    sync.discard({ id: workout.id });
    queryClient.setQueryData(["workouts", "active"], null);
    saveActiveWorkout(null);
  };

  const done = workout.exercises.reduce((n, e) => n + e.sets.filter((s) => s.completed).length, 0);
  const unticked = workout.exercises.flatMap((e) => e.sets.filter((s) => !s.completed));
  const confirmable = unticked.filter(hasReps).length;
  // The RIR picker shows under the set ticked last
  const latestDone = workout.exercises
    .flatMap((e) => e.sets)
    .filter((s) => s.completed && s.completed_at)
    .reduce<LocalSet | null>((latest, s) => (!latest || s.completed_at! > latest.completed_at! ? s : latest), null)?.id;
  const explained = explaining !== null ? workout.exercises[explaining] : undefined;
  const explainedTarget = asTarget(explained?.last?.target);
  // Editing the settings needs the exercise from the server list (it is not there while offline)
  const explainedExercise = explained && exercisesQuery.data?.find((e) => e.id === explained.exercise_id);

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
        {workout.exercises.map((exercise, exerciseIndex) => {
          const target = asTarget(exercise.last?.target);
          return (
          <div key={`${exercise.exercise_id}-${exerciseIndex}`} {...reorder.itemProps(exerciseIndex)} className="rounded-(--radius-card) data-dragging:bg-zinc-950 data-dragging:shadow-2xl">
            <Card className="px-2 py-1.5">
              <div className="flex items-center gap-1">
                <button type="button" aria-label="Přetáhnout cvik" {...reorder.handleProps(exerciseIndex)} className="flex size-9 shrink-0 items-center justify-center rounded-lg text-zinc-500 select-none active:bg-zinc-700">
                  <GripVertical size={16} />
                </button>
                <h2 className="min-w-0 flex-1 truncate font-semibold">{exercise.name}</h2>
                <span className="shrink-0 text-xs tabular-nums text-zinc-500">
                  {exercise.sets.filter((x) => x.completed).length}/{exercise.sets.length}
                </span>
                <button
                  type="button"
                  aria-label={`Odebrat cvik ${exercise.name}`}
                  onClick={() => askRemoveExercise(exerciseIndex)}
                  className="flex size-9 shrink-0 items-center justify-center rounded-lg text-zinc-500 active:bg-zinc-700 active:text-red-300"
                >
                  <Trash2 size={15} />
                </button>
              </div>
              {target && <TargetLine target={target} onOpen={() => setExplaining(exerciseIndex)} />}
              <TableHeader columns={["Série", "Minule", "kg", "Opak.", ""]} className={ACTIVE_COLS} />
              <div className="space-y-1">
                {exercise.sets.map((set, setIndex) => (
                  <Fragment key={set.id}>
                    <SetRow
                      index={setIndex}
                      set={set}
                      types={exercise.sets.map((x) => x.set_type)}
                      ghost={exercise.last?.sets[setIndex]}
                      onChange={(patch) => changeSet(exerciseIndex, setIndex, patch)}
                      onCommit={(patch, weightBefore) => commitSet(exerciseIndex, setIndex, patch, weightBefore)}
                      onToggle={() => toggleComplete(exerciseIndex, setIndex)}
                      onRemove={() => removeSet(exerciseIndex, setIndex)}
                    />
                    {set.completed && (
                      <SetMeta
                        set={set}
                        picker={set.id === latestDone}
                        targetRir={target?.target_rir ?? 1}
                        onRir={(rir) => changeSet(exerciseIndex, setIndex, { rir }, true)}
                      />
                    )}
                    {offer?.exerciseIndex === exerciseIndex && offer.setIndex === setIndex && (
                      <WeightOfferBar
                        offer={offer}
                        canKeep={set.planned_weight != null}
                        onApply={() => (copyWeight(offer, offer.targets.map(() => offer.weight)), setOffer({ ...offer, applied: true }))}
                        onUndo={() => (copyWeight(offer, offer.previous), setOffer(null))}
                        onKeep={() => keepForNextTime(offer)}
                        onClose={() => setOffer(null)}
                      />
                    )}
                  </Fragment>
                ))}
              </div>
              <AddSetButton onClick={() => addSet(exerciseIndex)} />
            </Card>
          </div>
          );
        })}

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
      {confirmRemove !== null && workout.exercises[confirmRemove] && (
        <Sheet title="Odebrat cvik?" onClose={() => setConfirmRemove(null)}>
          <p className="mb-4 text-sm text-zinc-400">
            {workout.exercises[confirmRemove].name} se z tréninku odebere, včetně{" "}
            {((n) => (n === 1 ? "1 odškrtnuté série" : `${n} odškrtnutých sérií`))(workout.exercises[confirmRemove].sets.filter((s) => s.completed).length)}.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" onClick={() => setConfirmRemove(null)}>
              Zpět
            </Button>
            <Button variant="danger" onClick={() => removeExercise(confirmRemove)}>
              Odebrat
            </Button>
          </div>
        </Sheet>
      )}
      {explaining !== null && explained?.last && explainedTarget && (
        <TargetSheet
          name={explained.name}
          target={explainedTarget}
          last={explained.last}
          unusual={!!explained.unusual}
          canApply={explained.sets.some((s) => !s.completed)}
          onApply={(sets) => applySuggestion(explaining, sets)}
          onUnusual={(unusual) => markUnusual(explaining, unusual)}
          onEdit={explainedExercise && (() => (setExplaining(null), setEditingExercise(explainedExercise)))}
          onClose={() => setExplaining(null)}
        />
      )}
      {editingExercise && (
        <ExerciseSheet exercise={editingExercise} onClose={() => setEditingExercise(null)} onSaved={(saved) => void retarget(saved.id)} />
      )}
      {confirmDiscard && <DiscardSheet setCount={done} onCancel={() => setConfirmDiscard(false)} onConfirm={discard} />}
      {picking && <ExercisePicker onPick={addExercise} onClose={() => setPicking(false)} />}
      {confirmFinish && (
        <Sheet title="Dokončit trénink?" onClose={() => setConfirmFinish(false)}>
          {unticked.length === 0 ? (
            <>
              <p className="mb-4 text-sm text-zinc-400">
                Uloží se {setsText(done)}.{pending > 0 && " Některé změny ještě čekají na připojení, odešlou se samy."}
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Button variant="ghost" onClick={() => setConfirmFinish(false)}>
                  Zpět
                </Button>
                <Button onClick={() => finish()}>Dokončit</Button>
              </div>
            </>
          ) : (
            <>
              <p className="mb-4 text-sm text-zinc-400">
                Odškrtnuto {done} z {done + unticked.length} sérií. Co s těmi zbylými?
                {confirmable < unticked.length &&
                  ` ${unticked.length - confirmable === 1 ? "1 série nemá" : `${unticked.length - confirmable} sérií nemá`} vyplněná opakování, ta se zahodí vždy.`}
                {pending > 0 && " Některé změny ještě čekají na připojení, odešlou se samy."}
              </p>
              {confirmable > 0 && (
                <Button className="w-full" onClick={() => finish(true)}>
                  Potvrdit {setsText(confirmable)} a dokončit
                </Button>
              )}
              <Button variant={confirmable > 0 ? "ghost" : "primary"} className="mt-2 w-full" onClick={() => finish()}>
                {done > 0 ? `Uložit jen ${setsText(done)}` : "Dokončit bez sérií"}
              </Button>
              <Button variant="ghost" className="mt-2 w-full" onClick={() => setConfirmFinish(false)}>
                Zpět k tréninku
              </Button>
            </>
          )}
          <Button variant="danger" className="mt-2 w-full" onClick={() => (setConfirmFinish(false), setConfirmDiscard(true))}>
            Zahodit trénink
          </Button>
        </Sheet>
      )}
    </>
  );
}

/** A set that can be ticked without the user's input: it has a rep count. */
const hasReps = (s: LocalSet) => (parseDecimal(s.reps) ?? 0) > 0;

const setsText = (n: number) => (n === 1 ? "1 sérii" : n >= 2 && n <= 4 ? `${n} série` : `${n} sérií`);

const ACTIVE_COLS = "grid-cols-[2rem_minmax(0,1fr)_4.25rem_3.5rem_2.25rem]";

/** A weight changed by hand during the workout and the following unticked sets of its block it can be copied to. */
type WeightOffer = { exerciseIndex: number; setIndex: number; weight: string; targets: number[]; previous: string[]; applied: boolean };

const OFFER_BUTTON = "shrink-0 rounded-md bg-zinc-700 px-2 py-1 font-medium text-zinc-100 active:bg-zinc-600";

function WeightOfferBar({
  offer,
  canKeep,
  onApply,
  onUndo,
  onKeep,
  onClose,
}: {
  offer: WeightOffer;
  canKeep: boolean;
  onApply: () => void;
  onUndo: () => void;
  onKeep: () => void;
  onClose: () => void;
}) {
  const sets = offer.targets.map((i) => i + 1).join(", ");
  const series = offer.targets.length > 1 ? "sérií" : "série";
  return (
    <div className="ml-9 flex items-center gap-1.5 rounded-lg bg-zinc-800/70 py-1 pr-1 pl-2 text-xs text-zinc-300">
      <span className="min-w-0 flex-1">
        {offer.applied ? `Propsáno do ${series} ${sets}.` : offer.targets.length ? `Propsat ${offer.weight} kg do ${series} ${sets}?` : `${offer.weight} kg mimo plán.`}
      </span>
      {!offer.applied && offer.targets.length > 0 && (
        <button type="button" onClick={onApply} className={OFFER_BUTTON}>
          Propsat
        </button>
      )}
      {offer.applied && (
        <button type="button" onClick={onUndo} className={OFFER_BUTTON}>
          Vrátit
        </button>
      )}
      {canKeep && (
        <button type="button" onClick={onKeep} className={OFFER_BUTTON}>
          I příště
        </button>
      )}
      <button type="button" aria-label="Zavřít" onClick={onClose} className="flex size-7 shrink-0 items-center justify-center rounded-md text-zinc-500 active:bg-zinc-700">
        <X size={14} />
      </button>
    </div>
  );
}
// The set the progression target pushes (E33); a ring too, since Zen's accent text is close to its ink
const PROGRESS_CELL = "text-emerald-300 ring-1 ring-emerald-500/60";

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
  onCommit: (patch?: Partial<LocalSet>, weightBefore?: string) => void;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const ghostWeight = ghost?.weight_kg != null ? formatNumber(ghost.weight_kg, ghost.weight_kg % 1 ? 1 : 0) : null;
  const weightAtFocus = useRef(set.weight); // to tell a changed weight on blur (E35)
  return (
    <div className={`grid items-center gap-1.5 rounded-lg px-1 py-0.5 ${ACTIVE_COLS} ${set.completed ? "bg-emerald-500/15" : ""}`}>
      <SetLabel types={types} index={index} onType={(set_type) => onCommit({ set_type })} onRemove={onRemove} />
      {ghost ? (
        <button
          type="button"
          aria-label="Použít hodnoty z minula"
          onClick={() => onCommit({ weight: ghostWeight ?? "", reps: ghost.reps !== null ? String(ghost.reps) : "" }, set.weight)}
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
        onBlur={() => onCommit(undefined, weightAtFocus.current)}
        onFocus={(e) => ((weightAtFocus.current = set.weight), selectAll(e))}
        className={`${cellInput(set.completed)} ${set.progress && !set.completed ? PROGRESS_CELL : ""}`}
      />
      <input
        aria-label={`opakování, série ${index + 1}`}
        inputMode="numeric"
        placeholder="opak."
        value={set.reps}
        onChange={(e) => onChange({ reps: e.target.value.replace(/\D/g, "") })}
        onBlur={() => onCommit()}
        onFocus={selectAll}
        className={`${cellInput(set.completed)} ${set.progress && !set.completed ? PROGRESS_CELL : ""}`}
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
