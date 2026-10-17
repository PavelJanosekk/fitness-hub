import { useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useState } from "react";
import { confirmDraft, type Draft } from "../api/coach";
import { formatNumber } from "../lib/format";
import { Button } from "./ui";

const REASONS: Record<Draft["reason"], string> = {
  exercise_uncertain: "Nejsem si jistý cvikem, vyber správný:",
  exercise_unknown: "Cvik jsem nenašel, vyber ho:",
  implausible_numbers: "Čísla se hodně liší od minula, zkontroluj je:",
};

/** A dictated set the coach didn't save on its own: one tap confirms it (docs/SPEC.md §3, hybrid save flow). */
export function DraftCard({ draft, onSaved }: { draft: Draft; onSaved?: (workoutId: string) => void }) {
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState<number | null>(draft.candidates.length === 1 || draft.reason === "implausible_numbers" ? draft.candidates[0]?.exercise_id ?? null : null);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  const save = async () => {
    if (choice === null) return;
    setState("saving");
    try {
      const saved = await confirmDraft({ exercise_id: choice, sets: draft.sets, workout_id: draft.workout_id });
      setState("saved");
      queryClient.invalidateQueries({ queryKey: ["workouts"] });
      onSaved?.(saved.workout_id);
    } catch {
      setState("error");
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
      <p className="mb-2 text-amber-200">
        „{draft.input_exercise_name}“ · {draft.sets.map((s) => `${formatNumber(s.weight_kg ?? 0, 1)}×${s.reps ?? "–"}`).join(", ")}
      </p>
      <p className="mb-2 text-zinc-400">{REASONS[draft.reason]}</p>
      {draft.reason === "implausible_numbers" && draft.last_session_weights.length > 0 && (
        <p className="mb-2 text-xs text-zinc-500">Minule: {draft.last_session_weights.map((w) => formatNumber(w, 1)).join(", ")} kg</p>
      )}
      <div className="mb-2 flex flex-wrap gap-2">
        {draft.candidates.map((c) => (
          <button
            key={c.exercise_id}
            onClick={() => setChoice(c.exercise_id)}
            className={`min-h-10 rounded-lg px-3 ${choice === c.exercise_id ? "bg-emerald-500 text-zinc-950" : "bg-zinc-800 text-zinc-200"}`}
          >
            {c.name}
          </button>
        ))}
      </div>
      {state === "saved" ? (
        <p className="flex items-center gap-1 text-emerald-400">
          <Check size={16} /> Uloženo
        </p>
      ) : (
        <Button onClick={save} disabled={choice === null || state === "saving"} className="w-full">
          {state === "error" ? "Zkusit znovu" : "Potvrdit a uložit"}
        </Button>
      )}
    </div>
  );
}
