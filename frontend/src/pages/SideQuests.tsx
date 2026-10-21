import { Check, Dices, Play, Plus, Search, Swords } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { type QuestCategory, type QuestDuration, type SideQuest, type SideQuestBoard, useSideQuestBoard } from "../api/sideQuests";
import { Card } from "../components/Layout";
import { QuestForm } from "../components/sideQuests/QuestForm";
import { QuestSheet } from "../components/sideQuests/QuestSheet";
import { Chips, Segmented, Sheet } from "../components/ui";
import { fullDate } from "../lib/bucket";
import { addDays, formatNumber } from "../lib/format";
import { DURATION, DURATION_KEYS, QUEST_CATEGORIES, QUEST_CATEGORY, sortQuests, travelLabel } from "../lib/sideQuests";

const STATUSES = [
  ["open", "Čeká"],
  ["done", "Splněno"],
  ["all", "Vše"],
] as const;
type Status = (typeof STATUSES)[number][0];

const DURATION_OPTIONS = DURATION_KEYS.map((key) => [key, DURATION[key].name] as const);
const CATEGORY_OPTIONS = QUEST_CATEGORIES.map((c) => [c.key, c.label] as const);

/** "26. 10." */
const shortDate = (iso: string) => `${Number(iso.slice(8, 10))}. ${Number(iso.slice(5, 7))}.`;

const normalize = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** Side quests (E45): the weekly "1 side quest", started ones, the list by category with filters, add / edit. */
export function SideQuests() {
  const board = useSideQuestBoard();
  const [params, setParams] = useSearchParams();
  const category = (QUEST_CATEGORIES.find((c) => c.key === params.get("c"))?.key ?? null) as QuestCategory | null;
  const status = (STATUSES.find(([key]) => key === params.get("s"))?.[0] ?? "open") as Status;
  const [duration, setDuration] = useState<QuestDuration | null>(null);
  const [query, setQuery] = useState("");
  const [opened, setOpened] = useState<{ id: number; complete: boolean } | null>(null);
  const [adding, setAdding] = useState(false);

  // ?i=<id> opens a quest
  const linked = Number(params.get("i")) || null;
  useEffect(() => {
    if (!linked) return;
    setOpened({ id: linked, complete: false });
    const next = new URLSearchParams(params);
    next.delete("i");
    setParams(next, { replace: true });
  }, [linked, params, setParams]);

  const setFilter = (next: { c?: QuestCategory | null; s?: Status }) => {
    const c = next.c !== undefined ? next.c : category;
    const s = next.s ?? status;
    setParams({ ...(c ? { c } : {}), ...(s !== "open" ? { s } : {}) }, { replace: true });
  };

  const data = board.data;
  const shown = useMemo(() => {
    if (!data) return [];
    const q = normalize(query.trim());
    return sortQuests(
      data.items.filter(
        (i) =>
          (status === "all" || (status === "done") === i.done) &&
          (!category || i.category === category) &&
          (!duration || i.duration === duration) &&
          (!q || normalize(i.title).includes(q) || normalize(i.note ?? "").includes(q)),
      ),
    );
  }, [data, status, category, duration, query]);

  if (board.isPending) return <p className="text-zinc-500">Načítám…</p>;
  if (!data) {
    return (
      <Card>
        <p className="text-zinc-400">Side questy se nepodařilo načíst. Zkus to znovu, až bude spojení.</p>
      </Card>
    );
  }
  const quest = opened ? data.items.find((i) => i.id === opened.id) : undefined;
  const active = data.items.filter((i) => i.active && !i.done);
  const grouped = !category && !query.trim();
  const open = (id: number, complete = false) => setOpened({ id, complete });
  const roll = () => {
    const pool = shown.filter((i) => !i.done);
    if (pool.length) open(pool[Math.floor(Math.random() * pool.length)].id);
  };

  return (
    <div className="space-y-3">
      <WeekCard board={data} />
      {status === "open" && active.length > 0 && (
        <section className="space-y-2">
          <h2 className="flex items-center gap-2 px-0.5 font-semibold">
            <Play size={16} className="text-emerald-400" /> Rozjeté
          </h2>
          <QuestList items={active} onOpen={open} />
        </section>
      )}

      <div className="flex items-center justify-between gap-2 pt-1">
        <Segmented options={STATUSES} value={status} onChange={(s) => setFilter({ s })} />
        <div className="flex gap-2">
          <button onClick={roll} aria-label="Kostka: náhodný quest z výběru" className="flex size-10 items-center justify-center rounded-full bg-zinc-800 text-emerald-400 active:bg-zinc-700">
            <Dices size={19} />
          </button>
          <button onClick={() => setAdding(true)} aria-label="Přidat side quest" className="flex min-h-10 items-center gap-1 rounded-full bg-emerald-500 px-3.5 text-sm font-medium text-on-accent active:bg-emerald-400">
            <Plus size={18} /> Přidat
          </button>
        </div>
      </div>
      <label className="flex min-h-11 items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950 px-3 focus-within:border-emerald-500">
        <Search size={17} className="text-zinc-500" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat side quest" aria-label="Hledat" className="w-full bg-transparent text-base outline-none" />
      </label>
      <Chips label="Kategorie" options={CATEGORY_OPTIONS} value={category} onChange={(c) => setFilter({ c })} allLabel="Vše" />
      <Chips label="Délka" options={DURATION_OPTIONS} value={duration} onChange={setDuration} allLabel="Jakkoli dlouhé" />

      {shown.length === 0 ? (
        <Card className="text-center">
          <p className="text-zinc-400">{status === "done" ? "Tady zatím nic splněného není." : "Nic tu není. Přidej si quest na volnou chvíli."}</p>
        </Card>
      ) : grouped ? (
        QUEST_CATEGORIES.map((c) => {
          const items = shown.filter((i) => i.category === c.key && !(i.active && !i.done));
          if (!items.length) return null;
          return (
            <section key={c.key} className="space-y-2">
              <h2 className="flex items-center gap-2 px-0.5 pt-1 font-semibold">
                <c.icon size={17} className="text-zinc-400" /> {c.label}
                <span className="ml-auto text-[13px] font-normal text-zinc-400 tabular-nums">{items.length}</span>
              </h2>
              <QuestList items={items} onOpen={open} />
            </section>
          );
        })
      ) : (
        <QuestList items={shown} onOpen={open} />
      )}

      {quest && <QuestSheet key={quest.id} quest={quest} board={data} completing={opened?.complete} onClose={() => setOpened(null)} />}
      {adding && (
        <Sheet title="Nový side quest" onClose={() => setAdding(false)}>
          <QuestForm initialCategory={category} onDone={() => setAdding(false)} />
        </Sheet>
      )}
    </div>
  );
}

function WeekCard({ board }: { board: SideQuestBoard }) {
  const { week } = board;
  const done = week.active && week.done > 0;
  const total = board.items.length;
  const finished = board.items.filter((i) => i.done).length;
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-3">
        <span className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${done ? "bg-emerald-500 text-on-accent" : "bg-zinc-800 text-zinc-300"}`}>
          {done ? <Check size={22} strokeWidth={3} /> : <Swords size={21} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold">Side quest týdne</div>
          <div className="truncate text-[13px] text-zinc-400">
            {done
              ? `Splněno: ${week.titles.join(", ")}`
              : week.active
                ? `Dokonči jakýkoli side quest · +${formatNumber(week.xp)} XP`
                : `Od pondělí ${shortDate(addDays(week.week_start, 7))} · +${formatNumber(week.xp)} XP každý týden`}
          </div>
        </div>
      </div>
      <div className="flex justify-between text-[13px] text-zinc-400">
        <span>
          <strong className="text-zinc-100 tabular-nums">{finished}</strong> / {total} splněno
        </span>
        <span>
          <strong className="text-zinc-100">{formatNumber(board.xp_total)} XP</strong> ze side questů
        </span>
      </div>
    </Card>
  );
}

function QuestList({ items, onOpen }: { items: SideQuest[]; onOpen: (id: number, complete?: boolean) => void }) {
  return (
    <div className="ui-card divide-y divide-zinc-800 overflow-hidden">
      {items.map((i) => (
        <QuestRow key={i.id} quest={i} onOpen={(complete) => onOpen(i.id, complete)} />
      ))}
    </div>
  );
}

function QuestRow({ quest, onOpen }: { quest: SideQuest; onOpen: (complete: boolean) => void }) {
  const style = DURATION[quest.duration];
  const meta = [
    quest.done ? null : `+${formatNumber(quest.xp)} XP`,
    quest.category === "trip" ? travelLabel(quest) : QUEST_CATEGORY[quest.category].label,
    quest.active && !quest.done ? "rozjeto" : null,
    quest.done_before_app ? "před aplikací" : quest.done_on ? fullDate(quest.done_on) : null,
  ].filter(Boolean);
  return (
    <div className="flex min-h-14 items-stretch">
      <button onClick={() => onOpen(false)} className="flex min-w-0 flex-1 items-center gap-3 py-2 pr-1 pl-3 text-left active:bg-zinc-800/60">
        <span className={`w-1 self-stretch rounded-full ${style.bar} ${quest.done ? "opacity-40" : ""}`} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className={`block truncate text-[15px] ${quest.done ? "text-zinc-400" : ""}`}>{quest.title}</span>
          <span className="block truncate text-xs text-zinc-500">
            <span className={style.text}>{style.name}</span>
            {meta.length > 0 && ` · ${meta.join(" · ")}`}
          </span>
        </span>
      </button>
      <button
        onClick={() => onOpen(!quest.done)}
        aria-label={quest.done ? `${quest.title}: splněno` : `Splnit ${quest.title}`}
        className="flex w-14 shrink-0 items-center justify-center active:bg-zinc-800/60"
      >
        <span className={`flex size-8 items-center justify-center rounded-full border-2 ${quest.done ? "border-emerald-500 bg-emerald-500 text-on-accent" : `${style.ring} opacity-70`}`}>
          {quest.done && <Check size={17} strokeWidth={3} />}
        </span>
      </button>
    </div>
  );
}
