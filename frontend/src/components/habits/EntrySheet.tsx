import { Plus, Sparkles, X } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { useSetHabitDay } from "../../api/habits";
import { abilityKey, matchAbilities } from "../../lib/abilities";
import { formatDay } from "../../lib/format";
import { entryOf, hasContent, type HabitDays, logModeOf, weekDays, weekStart } from "../../lib/habits";
import { Stars } from "../bucket/ItemSheet";
import { Button, Sheet } from "../ui";
import { entryTarget, setEntryTarget, subscribeEntry } from "./entryStore";
import { useHabitDays } from "./parts";

/**
 * The entry sheet of a note / review habit (E37): opened by a tap on the row, the tick is saved only on Uložit (J3).
 * One host lives in the Layout, so the Přehled card and the Rutina page open the same sheet.
 */
const input = "mt-1 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

export function EntrySheetHost() {
  const current = useSyncExternalStore(subscribeEntry, entryTarget);
  const { habits, board } = useHabitDays();
  const habit = current && habits.find((h) => h.id === current.habitId);
  if (!current || !habit) return null;
  return (
    <EntrySheet
      key={`${current.habitId}:${current.day}`}
      h={habit}
      day={current.day}
      abilities={board.data?.abilities ?? []}
      onClose={() => setEntryTarget(null)}
    />
  );
}

function EntrySheet({ h, day, abilities, onClose }: { h: HabitDays; day: string; abilities: { name: string }[]; onClose: () => void }) {
  const setDay = useSetHabitDay();
  const review = logModeOf(h) === "review";
  const ticked = h.manual.has(day);
  const entry = entryOf(h, day);
  const [note, setNote] = useState(entry?.note ?? "");
  const [rating, setRating] = useState(entry?.rating ?? 0);
  const [ability, setAbility] = useState(entry?.ability ?? "");
  const [typing, setTyping] = useState(false);
  const [confirmUntick, setConfirmUntick] = useState(false);

  const typed = ability.trim();
  const known = typed ? abilities.find((a) => abilityKey(a.name) === abilityKey(typed)) : undefined;
  const suggestions = matchAbilities(abilities, typed).filter((a) => a !== known);
  const isNew = typed !== "" && !known;

  const save = () => {
    setDay({ habitId: h.id, date: day, done: true, note: note.trim() || null, ability: known?.name ?? (typed || null), ...(review ? { rating: rating || null } : {}) });
    onClose();
  };
  const untick = () => {
    if (hasContent(entry) && !confirmUntick) return setConfirmUntick(true);
    // A weekly habit done once a week unticks its whole week, like a tap on a plain row
    const days = h.frequency === "weekly" && h.weekly_target === 1 ? weekDays(weekStart(day)).filter((d) => h.manual.has(d)) : [day];
    days.forEach((d) => setDay({ habitId: h.id, date: d, done: false }));
    onClose();
  };

  return (
    <Sheet title={h.title} onClose={onClose}>
      <form onSubmit={(e) => (e.preventDefault(), save())} className="space-y-4">
        <p className="-mt-2 text-sm text-zinc-500">{formatDay(day)}{ticked ? " · splněno" : ""}</p>
        {review && (
          <div>
            <p className="mb-1 text-sm text-zinc-400">Jaké to bylo</p>
            <Stars value={rating} onChange={setRating} />
          </div>
        )}
        <label className="block text-sm text-zinc-400">
          {review ? "Poznámka" : "Co jsi dělal / vyzkoušel?"}
          <textarea
            value={note}
            maxLength={2000}
            rows={3}
            onChange={(e) => setNote(e.target.value)}
            placeholder={review ? "Co se povedlo, co příště jinak…" : "např. bouldering v Lezci, první cesta 5a"}
            className={`${input} py-2`}
          />
        </label>

        <div>
          <p className="text-sm text-zinc-400">
            Dovednost <span className="text-zinc-600">(nepovinné)</span>
          </p>
          <div className="relative">
            <input
              value={ability}
              maxLength={60}
              onChange={(e) => (setAbility(e.target.value), setTyping(true))}
              onFocus={() => setTyping(true)}
              placeholder="vyber nebo napiš novou, např. Lezení"
              aria-label="Dovednost"
              className={`${input} min-h-11 pr-10`}
            />
            {ability && (
              <button type="button" aria-label="Smazat dovednost" onClick={() => setAbility("")} className="absolute right-1 top-1 flex size-10 items-center justify-center text-zinc-500">
                <X size={18} />
              </button>
            )}
          </div>
          {(typing || !typed) && (suggestions.length > 0 || isNew) && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {isNew && (
                <span className="flex min-h-9 items-center gap-1 rounded-full border border-emerald-700 px-3 text-sm text-emerald-300">
                  <Plus size={14} /> Nová: {typed}
                </span>
              )}
              {suggestions.map((a) => (
                <button
                  key={a.name}
                  type="button"
                  onClick={() => (setAbility(a.name), setTyping(false))}
                  className="min-h-9 rounded-full bg-zinc-800 px-3 text-sm text-zinc-200 active:bg-zinc-700"
                >
                  {a.name}
                </button>
              ))}
            </div>
          )}
          {isNew && (
            <p className="mt-1.5 flex items-center gap-1 text-xs text-emerald-400">
              <Sparkles size={12} /> Nová dovednost pro hrdinu · +25 XP do Mysli
            </p>
          )}
        </div>

        <Button type="submit" className="w-full">
          {ticked ? "Uložit" : "Uložit a splnit"}
        </Button>
        {ticked && (
          <Button type="button" variant="danger" onClick={untick} className="w-full">
            {confirmUntick ? "Opravdu? Smaže se i poznámka" : "Zrušit splnění"}
          </Button>
        )}
      </form>
    </Sheet>
  );
}
