import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, CloudOff, Minus, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  type Exercise,
  fetchLastPerformance,
  gymKeys,
  type LastPerformance,
  SYNC_SCOPE,
  type SetBody,
  type Template,
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
import { Button, Segmented, Sheet, parseDecimal } from "../components/ui";
import { type ActiveWorkout, type LocalExercise, type LocalSet, saveActiveWorkout, useActiveWorkout } from "../lib/activeWorkout";
import { formatDay, formatNumber, formatTime } from "../lib/format";
import { uuid } from "../lib/uuid";

const GROUP_LABELS: Record<string, string> = {
  chest: "Hrudník",
  back: "Záda",
  legs: "Nohy",
  shoulders: "Ramena",
  arms: "Paže",
  core: "Core",
  full_body: "Celé tělo",
  cardio: "Kardio",
};

/** Sync helpers: every call is an idempotent PUT/DELETE queued in order and persisted while offline. */
function useGymSync() {
  const putWorkout = useMutation<unknown, Error, { id: string; body: Record<string, unknown> }>({ mutationKey: ["gym", "workout"], scope: SYNC_SCOPE });
  const putSet = useMutation<unknown, Error, { workoutId: string; setId: string; body: SetBody }>({ mutationKey: ["gym", "set"], scope: SYNC_SCOPE });
  const deleteSet = useMutation<unknown, Error, { setId: string }>({ mutationKey: ["gym", "delete-set"], scope: SYNC_SCOPE });
  return { putWorkout: putWorkout.mutate, putSet: putSet.mutate, deleteSet: deleteSet.mutate };
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
  const { putWorkout } = useGymSync();
  const exercisesQuery = useExercises();
  const active = useActiveServerWorkout();
  const [starting, setStarting] = useState(false);

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
        sets: plannedSets(last, item.set_count),
        last,
      });
    }
    const workout: ActiveWorkout = { id: uuid(), name, started_at: new Date().toISOString(), exercises };
    saveActiveWorkout(workout);
    putWorkout({ id: workout.id, body: { name, started_at: workout.started_at } });
    setStarting(false);
  };

  return (
    <>
      <PageHeader title="Gym" />
      <div className="space-y-3">
        {active.data && (
          <Card className="border-emerald-700">
            <h2 className="font-semibold">Rozdělaný trénink</h2>
            <p className="mb-3 text-sm text-zinc-400">
              {active.data.name} · od {formatDay(active.data.started_at)} {formatTime(active.data.started_at)} · {active.data.sets.length} sérií
            </p>
            <Button className="w-full" onClick={() => resume(active.data!)}>
              Pokračovat
            </Button>
          </Card>
        )}

        <Card>
          <h2 className="mb-3 font-semibold">Začít trénink</h2>
          <div className="space-y-2">
            {templates.data?.map((t) => (
              <button
                key={t.name}
                disabled={starting}
                onClick={() => start(t.name, t)}
                className="flex w-full items-center gap-3 rounded-xl bg-zinc-800/70 p-3 text-left active:bg-zinc-700"
              >
                <div className="flex-1">
                  <div className="font-medium">{t.name}</div>
                  <div className="text-xs text-zinc-400">
                    {t.exercises.length} cviků · naposledy {formatDay(t.last_started_at)}
                  </div>
                </div>
                <ChevronRight size={18} className="text-zinc-500" />
              </button>
            ))}
          </div>
          <Button variant="ghost" className="mt-3 w-full" disabled={starting} onClick={() => start("Trénink")}>
            Prázdný trénink
          </Button>
        </Card>

        <Card>
          <h2 className="mb-2 font-semibold">Historie</h2>
          <ul className="divide-y divide-zinc-800">
            {history.data?.map((w) => (
              <li key={w.id} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <div className="font-medium">{w.name}</div>
                  <div className="text-xs text-zinc-400">
                    {formatDay(w.started_at)} · {w.set_count} sérií
                    {w.duration_min !== null && ` · ${w.duration_min} min${w.ended_by === "user" ? "" : " (odhad)"}`}
                  </div>
                </div>
                <div className="tabular-nums text-zinc-300">{formatNumber(w.total_volume_kg)} kg</div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

function ActiveWorkoutView({ workout }: { workout: ActiveWorkout }) {
  const queryClient = useQueryClient();
  const sync = useGymSync();
  const pending = useIsMutating({ mutationKey: ["gym"] });
  const server = useWorkout(workout.id);
  const [picking, setPicking] = useState(false);
  const [confirmFinish, setConfirmFinish] = useState(false);
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

  const finish = () => {
    sync.putWorkout({ id: workout.id, body: { ended_at: new Date().toISOString() } });
    saveActiveWorkout(null);
    setConfirmFinish(false);
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

      <div className="space-y-3">
        {workout.exercises.map((exercise, exerciseIndex) => (
          <Card key={`${exercise.exercise_id}-${exerciseIndex}`} className="p-3">
            <div className="mb-2 flex items-baseline justify-between gap-2 px-1">
              <h2 className="font-semibold">{exercise.name}</h2>
              <span className="text-xs text-zinc-500">{GROUP_LABELS[exercise.muscle_group] ?? ""}</span>
            </div>
            <div className="space-y-2">
              {exercise.sets.map((set, setIndex) => (
                <SetRow
                  key={set.id}
                  index={setIndex}
                  set={set}
                  ghost={exercise.last?.sets[setIndex]}
                  onChange={(patch) => changeSet(exerciseIndex, setIndex, patch)}
                  onCommit={() => syncSet(exerciseIndex, setIndex)}
                  onToggle={() => toggleComplete(exerciseIndex, setIndex)}
                  onRemove={() => removeSet(exerciseIndex, setIndex)}
                />
              ))}
            </div>
            <button onClick={() => addSet(exerciseIndex)} className="mt-2 w-full rounded-xl py-2.5 text-sm text-emerald-400 active:bg-zinc-800">
              + Přidat sérii
            </button>
          </Card>
        ))}

        <Button variant="ghost" className="w-full" onClick={() => setPicking(true)}>
          + Přidat cvik
        </Button>
        <RestPresetPicker />
      </div>

      <div className="fixed right-4 bottom-[calc(env(safe-area-inset-bottom)+9.5rem)] z-20 md:bottom-24">
        <VoiceRecorder onRecorded={dictate} disabled={voice?.busy} className="size-14 bg-emerald-600 text-zinc-950 shadow-lg" />
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
          <Button variant="danger" className="mt-2 w-full" onClick={() => (saveActiveWorkout(null), setConfirmFinish(false))}>
            Zahodit jen v telefonu
          </Button>
        </Sheet>
      )}
    </>
  );
}

function SetRow({
  index,
  set,
  ghost,
  onChange,
  onCommit,
  onToggle,
  onRemove,
}: {
  index: number;
  set: LocalSet;
  ghost?: LastPerformance["sets"][number];
  onChange: (patch: Partial<LocalSet>) => void;
  onCommit: () => void;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const step = (field: "weight" | "reps", delta: number) => {
    const current = parseDecimal(set[field]) ?? 0;
    const next = Math.max(0, Math.round((current + delta) * 10) / 10);
    onChange({ [field]: formatNumber(next, next % 1 ? 1 : 0) });
  };
  return (
    <div className={`rounded-xl p-2 ${set.completed ? "bg-emerald-500/10" : "bg-zinc-800/50"}`}>
      <div className="mb-1.5 flex items-center justify-between px-1 text-xs text-zinc-400">
        <span>
          Série {index + 1}
          {set.set_type !== "normal" && ` · ${{ warmup: "zahřívací", drop: "drop", failure: "do selhání" }[set.set_type]}`}
        </span>
        <span className="flex items-center gap-2">
          {ghost && (
            <span>
              minule {ghost.weight_kg !== null ? formatNumber(ghost.weight_kg, 1) : "–"} × {ghost.reps ?? "–"}
            </span>
          )}
          <button aria-label="Smazat sérii" onClick={onRemove} className="p-1 text-zinc-500 active:text-red-300">
            <Trash2 size={14} />
          </button>
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Stepper label="kg" value={set.weight} onChange={(v) => onChange({ weight: v })} onStep={(d) => step("weight", d * 2.5)} onBlur={onCommit} />
        <Stepper label="opak." value={set.reps} onChange={(v) => onChange({ reps: v })} onStep={(d) => step("reps", d)} onBlur={onCommit} numeric />
        <button
          aria-label={set.completed ? "Zrušit odškrtnutí" : "Série hotová"}
          onClick={onToggle}
          className={`flex size-12 shrink-0 items-center justify-center rounded-xl ${set.completed ? "bg-emerald-500 text-zinc-950" : "bg-zinc-700 text-zinc-300 active:bg-zinc-600"}`}
        >
          <Check size={24} strokeWidth={3} />
        </button>
      </div>
    </div>
  );
}

function Stepper({
  label,
  value,
  onChange,
  onStep,
  onBlur,
  numeric = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onStep: (direction: 1 | -1) => void;
  onBlur: () => void;
  numeric?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center rounded-xl bg-zinc-950">
      <button aria-label={`Méně ${label}`} onClick={() => (onStep(-1), onBlur())} className="flex h-12 w-10 shrink-0 items-center justify-center text-zinc-400 active:text-white">
        <Minus size={18} />
      </button>
      <input
        aria-label={label}
        inputMode={numeric ? "numeric" : "decimal"}
        value={value}
        onChange={(e) => onChange(e.target.value.replace(numeric ? /\D/g : /[^\d.,]/g, ""))}
        onBlur={onBlur}
        placeholder={label}
        className="h-12 w-full min-w-0 bg-transparent text-center text-lg font-semibold tabular-nums outline-none placeholder:text-sm placeholder:font-normal placeholder:text-zinc-600"
      />
      <button aria-label={`Více ${label}`} onClick={() => (onStep(1), onBlur())} className="flex h-12 w-10 shrink-0 items-center justify-center text-zinc-400 active:text-white">
        <Plus size={18} />
      </button>
    </div>
  );
}

function ExercisePicker({ onPick, onClose }: { onPick: (exercise: Exercise) => void; onClose: () => void }) {
  const exercises = useExercises();
  const [query, setQuery] = useState("");
  const normalize = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const filtered = useMemo(
    () => (exercises.data ?? []).filter((e) => normalize(e.name).includes(normalize(query.trim()))),
    [exercises.data, query],
  );
  return (
    <Sheet title="Přidat cvik" onClose={onClose}>
      <label className="mb-3 flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3">
        <Search size={18} className="text-zinc-500" />
        <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 w-full bg-transparent outline-none" />
      </label>
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
    </Sheet>
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
