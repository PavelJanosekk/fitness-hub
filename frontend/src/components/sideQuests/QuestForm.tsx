import { useState } from "react";
import { ApiError } from "../../api/client";
import { type QuestCategory, type QuestDuration, type SideQuest, useSaveSideQuest, useSideQuestBoard } from "../../api/sideQuests";
import { formatNumber } from "../../lib/format";
import { DURATION, DURATION_KEYS, QUEST_CATEGORIES } from "../../lib/sideQuests";
import { Button } from "../ui";

export const input =
  "mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

export function saveError(error: Error): string {
  if (error instanceof ApiError) return `Chyba ${error.status}: ${error.message}`;
  return navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, side questy jdou upravit jen s připojením.";
}

const toInt = (value: string) => (value.trim() === "" ? null : Math.max(0, Math.round(Number(value))) || 0);

/** Create (`quest` undefined) or edit a side quest: name, category, duration, note, link, drive time for trips. */
export function QuestForm({ quest, initialCategory, onDone }: { quest?: SideQuest; initialCategory?: QuestCategory | null; onDone: (quest: SideQuest) => void }) {
  const save = useSaveSideQuest();
  const xp = useSideQuestBoard().data?.durations;
  const [title, setTitle] = useState(quest?.title ?? "");
  const [category, setCategory] = useState<QuestCategory | null>(quest?.category ?? initialCategory ?? null);
  const [duration, setDuration] = useState<QuestDuration>(quest?.duration ?? "day");
  const [note, setNote] = useState(quest?.note ?? "");
  const [link, setLink] = useState(quest?.link ?? "");
  const [minutes, setMinutes] = useState(quest?.travel_minutes != null ? String(quest.travel_minutes) : "");
  const [km, setKm] = useState(quest?.distance_km != null ? String(quest.distance_km) : "");
  const valid = title.trim() !== "" && category !== null;

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        const trip = category === "trip";
        save.mutate(
          {
            id: quest?.id,
            title: title.trim(),
            category,
            duration,
            note: note.trim() || null,
            link: link.trim() || null,
            travel_minutes: trip ? toInt(minutes) : null,
            distance_km: trip ? toInt(km) : null,
          },
          { onSuccess: onDone },
        );
      }}
    >
      <label className="block text-sm text-zinc-400">
        Co
        <input value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} placeholder="Např. Naučit se žonglovat" className={input} autoFocus={!quest} required />
      </label>

      <fieldset>
        <legend className="mb-1.5 text-sm text-zinc-400">Kategorie</legend>
        <div className="grid grid-cols-5 gap-1.5">
          {QUEST_CATEGORIES.map((c) => (
            <button
              key={c.key}
              type="button"
              aria-pressed={category === c.key}
              onClick={() => setCategory(c.key)}
              className={`flex min-w-0 flex-col items-center gap-1 rounded-xl border px-0.5 py-2 text-[10.5px] ${category === c.key ? "border-emerald-600 bg-emerald-950/50 text-emerald-200" : "border-zinc-800 text-zinc-300"}`}
            >
              <c.icon size={19} /> <span className="w-full truncate text-center">{c.label}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-1.5 text-sm text-zinc-400">Jak dlouho</legend>
        <div className="grid grid-cols-5 gap-1.5">
          {DURATION_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={duration === key}
              onClick={() => setDuration(key)}
              className={`flex flex-col items-center rounded-xl border px-1 py-2 text-[12px] ${duration === key ? `${DURATION[key].ring} bg-zinc-800` : "border-zinc-800"}`}
            >
              <span className={DURATION[key].text}>{DURATION[key].name}</span>
              <span className="text-[11px] text-zinc-500">+{formatNumber(xp?.find((d) => d.key === key)?.xp)} XP</span>
            </button>
          ))}
        </div>
      </fieldset>

      {category === "trip" && (
        <div className="grid grid-cols-2 gap-2">
          <label className="block text-sm text-zinc-400">
            Autem (min)
            <input inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value.replace(/\D/g, ""))} className={input} />
          </label>
          <label className="block text-sm text-zinc-400">
            Vzdálenost (km)
            <input inputMode="numeric" value={km} onChange={(e) => setKm(e.target.value.replace(/\D/g, ""))} className={input} />
          </label>
        </div>
      )}

      <label className="block text-sm text-zinc-400">
        Poznámka
        <textarea value={note} maxLength={2000} rows={2} onChange={(e) => setNote(e.target.value)} className={`${input} py-2`} />
      </label>
      <label className="block text-sm text-zinc-400">
        Odkaz
        <input type="url" value={link} maxLength={2000} onChange={(e) => setLink(e.target.value)} placeholder="https://" className={input} />
      </label>

      {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
      <Button type="submit" className="w-full" disabled={!valid || save.isPending}>
        {save.isPending ? "Ukládám…" : quest ? "Uložit" : "Přidat side quest"}
      </Button>
    </form>
  );
}
