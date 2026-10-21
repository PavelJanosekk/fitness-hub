import { Check, ExternalLink, MapPin, Pause, Pencil, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { type SideQuest, type SideQuestBoard, useDeleteSideQuest, useSaveSideQuest } from "../../api/sideQuests";
import { fullDate } from "../../lib/bucket";
import { addDays, formatNumber } from "../../lib/format";
import { DURATION, mapLink, QUEST_CATEGORY, travelLabel } from "../../lib/sideQuests";
import { Stars } from "../bucket/ItemSheet";
import { Button, Sheet } from "../ui";
import { input, QuestForm, saveError } from "./QuestForm";

const SKILL_NAMES: Record<string, string> = { mind: "Mysl", nutrition: "Výživa", adventure: "Dobrodružství" };

/** One side quest: details, start / pause, complete (date, ★, memory), edit, delete. */
export function QuestSheet({ quest, board, completing = false, onClose }: { quest: SideQuest; board: SideQuestBoard; completing?: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<"view" | "complete" | "edit">(completing ? "complete" : "view");
  const save = useSaveSideQuest();
  const remove = useDeleteSideQuest();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const style = DURATION[quest.duration];
  const category = QUEST_CATEGORY[quest.category];
  const skill = board.categories.find((c) => c.key === quest.category)?.skill;
  const Icon = category.icon;

  if (mode === "edit") {
    return (
      <Sheet title="Upravit side quest" onClose={onClose}>
        <QuestForm quest={quest} onDone={() => setMode("view")} />
      </Sheet>
    );
  }

  const travel = travelLabel(quest);
  return (
    <Sheet title={quest.title} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className={`rounded-full bg-zinc-800 px-2.5 py-1 font-semibold ${style.text}`}>{style.name}</span>
          <span className="flex items-center gap-1 rounded-full bg-zinc-800 px-2.5 py-1 text-zinc-300">
            <Icon size={13} /> {category.label}
          </span>
          <span className="rounded-full bg-zinc-800 px-2.5 py-1 text-zinc-300">
            {quest.done && !quest.xp ? "bez XP" : `+${formatNumber(quest.xp)} XP`}
            {skill && SKILL_NAMES[skill] ? ` · ${SKILL_NAMES[skill]}` : ""}
          </span>
          {quest.active && !quest.done && <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-emerald-300">Rozjeto</span>}
        </div>

        {quest.note && <p className="text-[15px] whitespace-pre-line text-zinc-200">{quest.note}</p>}
        {travel && (
          <p className="flex items-center gap-1.5 text-sm text-zinc-300">
            <MapPin size={15} className="text-zinc-500" /> Z domova autem {travel}
          </p>
        )}
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {quest.link && (
            <a href={quest.link} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm text-emerald-400">
              <ExternalLink size={15} /> Odkaz
            </a>
          )}
          {quest.category === "trip" && (
            <a href={mapLink(quest.title)} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm text-emerald-400">
              <MapPin size={15} /> Na mapě
            </a>
          )}
        </div>

        {quest.done && <DoneBlock quest={quest} onEdit={() => setMode("complete")} />}

        {mode === "complete" ? (
          <CompleteForm quest={quest} today={board.today} onDone={() => setMode("view")} />
        ) : (
          !quest.done && (
            <div className="grid grid-cols-2 gap-2">
              <Button className="col-span-2 flex items-center justify-center gap-2" onClick={() => setMode("complete")}>
                <Check size={18} /> Splněno!
              </Button>
              <Button variant="ghost" className="col-span-2 flex items-center justify-center gap-2" disabled={save.isPending} onClick={() => save.mutate({ id: quest.id, active: !quest.active })}>
                {quest.active ? <Pause size={17} /> : <Play size={17} />} {quest.active ? "Odložit" : "Rozjet"}
              </Button>
            </div>
          )
        )}

        {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
        {remove.isError && <p className="text-sm text-red-300">{saveError(remove.error)}</p>}

        <div className="flex gap-2 border-t border-zinc-800 pt-3">
          <Button variant="ghost" className="flex flex-1 items-center justify-center gap-2" onClick={() => setMode("edit")}>
            <Pencil size={16} /> Upravit
          </Button>
          {confirmDelete ? (
            <Button variant="danger" className="flex-1" disabled={remove.isPending} onClick={() => remove.mutate(quest.id, { onSuccess: onClose })}>
              Opravdu smazat
            </Button>
          ) : (
            <Button variant="danger" aria-label="Smazat side quest" className="flex items-center justify-center" onClick={() => setConfirmDelete(true)}>
              <Trash2 size={17} />
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}

function DoneBlock({ quest, onEdit }: { quest: SideQuest; onEdit: () => void }) {
  const save = useSaveSideQuest();
  return (
    <div className="space-y-2 rounded-2xl border border-emerald-800/60 bg-emerald-950/30 p-3">
      <p className="flex items-center gap-2 font-medium text-emerald-300">
        <Check size={17} /> {quest.done_on ? `Splněno ${fullDate(quest.done_on)}` : "Splněno ještě před aplikací"}
      </p>
      {quest.rating ? <Stars value={quest.rating} /> : null}
      {quest.memory && <p className="text-sm whitespace-pre-line text-zinc-200">{quest.memory}</p>}
      <div className="flex flex-wrap gap-2 pt-1">
        <button onClick={onEdit} className="min-h-9 rounded-full bg-zinc-800 px-3 text-sm active:bg-zinc-700">
          {quest.memory || quest.rating ? "Upravit vzpomínku" : "Přidat vzpomínku"}
        </button>
        <button
          onClick={() => save.mutate({ id: quest.id, done_on: null, done_before_app: false })}
          disabled={save.isPending}
          className="min-h-9 rounded-full px-3 text-sm text-zinc-400 active:bg-zinc-800"
        >
          Zrušit splnění
        </button>
      </div>
    </div>
  );
}

function CompleteForm({ quest, today, onDone }: { quest: SideQuest; today: string; onDone: () => void }) {
  const save = useSaveSideQuest();
  const [day, setDay] = useState(quest.done_on ?? today);
  const [rating, setRating] = useState(quest.rating ?? 0);
  const [memory, setMemory] = useState(quest.memory ?? "");
  const before = quest.done_before_app;
  return (
    <form
      className="space-y-3 rounded-2xl border border-zinc-800 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ id: quest.id, memory: memory.trim() || null, rating: rating || null, ...(before ? {} : { done_on: day }) }, { onSuccess: onDone });
      }}
    >
      {!before && (
        <label className="block text-sm text-zinc-400">
          Kdy
          <input type="date" value={day} max={today} onChange={(e) => setDay(e.target.value)} className={input} required />
        </label>
      )}
      <div>
        <p className="mb-1 text-sm text-zinc-400">Jaké to bylo</p>
        <Stars value={rating} onChange={setRating} />
      </div>
      <label className="block text-sm text-zinc-400">
        Vzpomínka
        <textarea value={memory} maxLength={2000} rows={3} onChange={(e) => setMemory(e.target.value)} placeholder="Co se povedlo, co příště jinak…" className={`${input} py-2`} />
      </label>
      {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
      <div className="grid grid-cols-[auto_1fr] gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Zpět
        </Button>
        <Button type="submit" disabled={save.isPending || !day}>
          {save.isPending ? "Ukládám…" : quest.done ? "Uložit" : `Splněno · +${formatNumber(quest.xp)} XP`}
        </Button>
      </div>
      {!quest.done && day < addDays(quest.created_at.slice(0, 10), -7) && (
        <p className="text-xs text-zinc-500">Splnění víc než týden před přidáním na seznam se počítá bez XP.</p>
      )}
    </form>
  );
}
