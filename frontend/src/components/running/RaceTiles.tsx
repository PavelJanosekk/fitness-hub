import { Flag, Plus } from "lucide-react";
import { useState } from "react";
import { ApiError } from "../../api/client";
import { type Race, useAddRace, useDeleteRace } from "../../api/running";
import { formatDay, formatNumber, isoDate } from "../../lib/format";
import { Card } from "../Layout";
import { Button, Chips, DecimalInput, parseDecimal, Sheet } from "../ui";

const daysUntil = (iso: string) => Math.round((new Date(`${iso}T12:00:00`).getTime() - new Date(`${isoDate()}T12:00:00`).getTime()) / 86_400_000);
const DISTANCES = [
  ["5", "5 km"],
  ["10", "10 km"],
  ["21.0975", "Půlmaraton"],
  ["42.195", "Maraton"],
] as const;
const input = "mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

const errorText = (error: Error) =>
  error instanceof ApiError ? `Chyba ${error.status}: ${error.message}` : navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, závody jde upravit jen s připojením.";

/** Countdown tiles of upcoming races; a tap opens the race (with removal), the last tile adds one. */
export function RaceTiles({ races }: { races: Race[] }) {
  const [open, setOpen] = useState<Race | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        {races.map((race) => (
          <button key={race.id} type="button" onClick={() => setOpen(race)} className="text-left">
            <Card className={`h-full active:opacity-80 ${race.is_goal_race ? "border-emerald-700" : ""}`}>
              <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                <Flag size={14} /> {formatDay(race.date)}
              </div>
              <div className="mt-1 text-3xl font-semibold tabular-nums">{daysUntil(race.date)}</div>
              <div className="text-xs text-zinc-400">dní · {race.name}</div>
            </Card>
          </button>
        ))}
        <button
          type="button"
          onClick={() => setAdding(true)}
          className={`flex min-h-11 items-center justify-center gap-1.5 rounded-[var(--radius-card)] border border-dashed border-zinc-700 text-sm text-zinc-400 active:bg-zinc-800/40 ${races.length % 2 ? "" : "col-span-2 py-3"}`}
        >
          <Plus size={16} /> Přidat závod
        </button>
      </div>
      {open && <RaceSheet race={open} onClose={() => setOpen(null)} />}
      {adding && <AddRaceSheet onClose={() => setAdding(false)} />}
    </>
  );
}

function RaceSheet({ race, onClose }: { race: Race; onClose: () => void }) {
  const remove = useDeleteRace();
  return (
    <Sheet title={race.name} onClose={onClose}>
      <dl className="mb-4 space-y-1 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-zinc-400">Datum</dt>
          <dd>{formatDay(race.date)}</dd>
        </div>
        {race.distance_km !== null && (
          <div className="flex justify-between gap-3">
            <dt className="text-zinc-400">Vzdálenost</dt>
            <dd className="tabular-nums">{formatNumber(race.distance_km, race.distance_km % 1 ? 1 : 0)} km</dd>
          </div>
        )}
        {race.is_goal_race && <p className="text-emerald-400">Hlavní závod (boss v Hrdinovi)</p>}
        {race.goal && <p className="text-zinc-300">{race.goal}</p>}
      </dl>
      <p className="mb-3 text-xs text-zinc-500">
        {race.source === "kb"
          ? "Závod je ze znalostní báze. Po odebrání zůstane skrytý i po další synchronizaci."
          : "Závod jsi přidal v aplikaci."}
      </p>
      {remove.isError && <p className="mb-3 text-sm text-red-300">{errorText(remove.error)}</p>}
      <Button variant="danger" className="w-full" disabled={remove.isPending} onClick={() => remove.mutate(race.id, { onSuccess: onClose })}>
        {remove.isPending ? "Odebírám…" : "Odebrat závod"}
      </Button>
    </Sheet>
  );
}

function AddRaceSheet({ onClose }: { onClose: () => void }) {
  const add = useAddRace();
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [preset, setPreset] = useState<string | null>(null);
  const [km, setKm] = useState("");
  const [goal, setGoal] = useState(false);
  const distance = preset !== null ? Number(preset) : parseDecimal(km);
  const valid = name.trim() !== "" && date !== "" && (distance === null || distance > 0);

  const submit = () => {
    if (!valid) return;
    add.mutate({ name: name.trim(), date, distance_km: distance, is_goal_race: goal }, { onSuccess: onClose });
  };

  return (
    <Sheet title="Nový závod" onClose={onClose}>
      <form onSubmit={(e) => (e.preventDefault(), submit())} className="space-y-4">
        <label className="block text-sm text-zinc-400">
          Název
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="např. Běchovice–Praha" className={input} />
        </label>
        <label className="block text-sm text-zinc-400">
          Datum
          <input type="date" value={date} min={isoDate()} onChange={(e) => setDate(e.target.value)} className={input} />
        </label>
        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Vzdálenost</p>
          <Chips label="Vzdálenost" options={DISTANCES} value={preset} onChange={setPreset} allLabel="Jiná" wrap />
          {preset === null && <DecimalInput value={km} onChange={setKm} placeholder="km (nepovinné)" ariaLabel="Vzdálenost v km" className="mt-2" />}
        </div>
        <label className="flex min-h-11 items-center gap-3 text-sm">
          <input type="checkbox" checked={goal} onChange={(e) => setGoal(e.target.checked)} className="size-5 accent-emerald-500" />
          Hlavní závod (boss v Hrdinovi)
        </label>
        {add.isError && <p className="text-sm text-red-300">{errorText(add.error)}</p>}
        <Button type="submit" disabled={!valid || add.isPending} className="w-full">
          {add.isPending ? "Ukládám…" : "Přidat závod"}
        </Button>
      </form>
    </Sheet>
  );
}
