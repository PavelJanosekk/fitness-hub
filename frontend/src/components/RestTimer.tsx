import { Minus, Plus, Timer, X } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

/** Floating rest countdown above the tab bar. Stored as an end time, so it survives re-renders and app switches. */
const KEY = "fitness-hub-rest";
const PRESET_KEY = "fitness-hub-rest-preset";
export const PRESETS = [60, 90, 120, 180] as const;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

type Rest = { endsAt: number; total: number } | null;
let cached: { raw: string | null; value: Rest } = { raw: null, value: null };
function readRest(): Rest {
  const raw = localStorage.getItem(KEY);
  if (raw !== cached.raw) cached = { raw, value: raw ? (JSON.parse(raw) as Rest) : null };
  return cached.value;
}

export const restPreset = () => Number(localStorage.getItem(PRESET_KEY)) || 120;
export const setRestPreset = (seconds: number) => localStorage.setItem(PRESET_KEY, String(seconds));

export function startRest(seconds = restPreset()) {
  localStorage.setItem(KEY, JSON.stringify({ endsAt: Date.now() + seconds * 1000, total: seconds }));
  notify();
}
function stopRest() {
  localStorage.removeItem(KEY);
  notify();
}
function adjustRest(delta: number) {
  const rest = readRest();
  if (!rest) return;
  localStorage.setItem(KEY, JSON.stringify({ endsAt: rest.endsAt + delta * 1000, total: Math.max(1, rest.total + delta) }));
  notify();
}

export function RestTimer() {
  const rest = useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), readRest);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!rest) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [rest]);
  if (!rest) return null;
  const left = Math.max(0, Math.round((rest.endsAt - now) / 1000));
  const done = left === 0;
  if (done && now - rest.endsAt > 15_000) {
    stopRest();
    return null;
  }
  return (
    <div className="fixed inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+4.5rem)] z-30 md:bottom-4 md:left-auto md:right-6 md:w-80">
      <div className={`overflow-hidden rounded-2xl border shadow-xl ${done ? "border-emerald-500 bg-emerald-950" : "border-zinc-700 bg-zinc-900"}`}>
        <div className="flex items-center gap-2 p-2">
          <Timer size={18} className={done ? "text-emerald-400" : "text-zinc-400"} />
          <span className="flex-1 text-xl font-semibold tabular-nums">
            {done ? "Pauza hotová" : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`}
          </span>
          <button aria-label="Ubrat 15 s" onClick={() => adjustRest(-15)} className="rounded-lg bg-zinc-800 p-2.5 active:bg-zinc-700">
            <Minus size={16} />
          </button>
          <button aria-label="Přidat 15 s" onClick={() => adjustRest(15)} className="rounded-lg bg-zinc-800 p-2.5 active:bg-zinc-700">
            <Plus size={16} />
          </button>
          <button aria-label="Ukončit pauzu" onClick={stopRest} className="rounded-lg bg-zinc-800 p-2.5 active:bg-zinc-700">
            <X size={16} />
          </button>
        </div>
        <div className="h-1 bg-zinc-800">
          <div className="h-full bg-emerald-500 transition-[width] duration-300" style={{ width: `${(left / rest.total) * 100}%` }} />
        </div>
      </div>
    </div>
  );
}
