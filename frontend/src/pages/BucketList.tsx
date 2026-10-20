import { CalendarClock, Check, Dices, Map as MapIcon, Plus, Search, Sparkles, Star, Trophy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { type BucketBoard, type BucketItem, type Category, useBucketBoard } from "../api/bucket";
import { DiceSheet } from "../components/bucket/DiceSheet";
import { ItemForm } from "../components/bucket/ItemForm";
import { ItemSheet } from "../components/bucket/ItemSheet";
import { Card } from "../components/Layout";
import { Chips, Segmented, Sheet } from "../components/ui";
import { CATEGORIES, costLabel, countdown, RARITY, SEASON_LABEL, sortItems, stepsDone } from "../lib/bucket";
import { formatNumber } from "../lib/format";

const STATUSES = [
  ["open", "Čeká"],
  ["done", "Splněno"],
  ["all", "Vše"],
] as const;
type Status = (typeof STATUSES)[number][0];

const TAGS = [
  ["summer", "Léto"],
  ["winter", "Zima"],
  ["cheap", "Levné"],
  ["goal", "Letošní cíle"],
  ["auto", "Splní se samo"],
] as const;
type Tag = (typeof TAGS)[number][0];

const TOOL = "ui-card flex min-h-16 flex-col items-center justify-center gap-1 text-[13px] font-medium active:bg-zinc-800/60";

const normalize = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export function BucketList() {
  const board = useBucketBoard();
  const [params, setParams] = useSearchParams();
  const category = (CATEGORIES.find((c) => c.key === params.get("c"))?.key ?? null) as Category | null;
  const status = (STATUSES.find(([key]) => key === params.get("s"))?.[0] ?? "open") as Status;
  const [tag, setTag] = useState<Tag | null>(null);
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<{ id: number; mode: "view" | "complete" | "plan" } | null>(null);
  const [adding, setAdding] = useState(false);
  const [dice, setDice] = useState(false);

  // ?i=<id> opens an item (the completion moment links here to add a memory)
  const linked = Number(params.get("i")) || null;
  useEffect(() => {
    if (!linked) return;
    setOpenId({ id: linked, mode: "view" });
    const next = new URLSearchParams(params);
    next.delete("i");
    setParams(next, { replace: true });
  }, [linked, params, setParams]);

  const setFilter = (next: { c?: Category | null; s?: Status }) => {
    const c = next.c !== undefined ? next.c : category;
    const s = next.s ?? status;
    setParams({ ...(c ? { c } : {}), ...(s !== "open" ? { s } : {}) }, { replace: true });
  };

  const data = board.data;
  const year = data ? Number(data.today.slice(0, 4)) : new Date().getFullYear();
  const shown = useMemo(() => {
    if (!data) return [];
    const q = normalize(query.trim());
    return sortItems(
      data.items.filter(
        (i) =>
          (status === "all" || (status === "done") === i.done) &&
          (!category || i.category === category) &&
          (!q || normalize(i.title).includes(q) || normalize(i.note ?? "").includes(q)) &&
          (!tag ||
            (tag === "summer" && i.season === "summer") ||
            (tag === "winter" && i.season === "winter") ||
            (tag === "cheap" && i.cost === 1) ||
            (tag === "goal" && i.year_goal === year) ||
            (tag === "auto" && i.auto_rule !== null)),
      ),
      year,
    );
  }, [data, status, category, query, tag, year]);

  if (board.isPending) return <p className="text-zinc-500">Načítám…</p>;
  if (!data) {
    return (
      <Card>
        <p className="text-zinc-400">Bucket list se nepodařilo načíst. Zkus to znovu, až bude spojení.</p>
      </Card>
    );
  }
  const opened = openId ? data.items.find((i) => i.id === openId.id) : undefined;
  const grouped = !category && !query.trim();

  return (
    <div className="space-y-3">
      <Summary board={data} />
      <Planned board={data} onOpen={(id) => setOpenId({ id, mode: "view" })} />
      <div className="grid grid-cols-3 gap-2">
        <button onClick={() => setDice(true)} className={TOOL}>
          <Dices size={20} className="text-emerald-400" /> Kostka osudu
        </button>
        <Link to="/hero/bucket/map" className={TOOL}>
          <MapIcon size={20} className="text-emerald-400" /> Mapa
        </Link>
        <Link to="/hero/bucket/fame" className={TOOL}>
          <Trophy size={20} className="text-emerald-400" /> Síň slávy
        </Link>
      </div>
      <CategoryGrid board={data} value={category} onChange={(c) => setFilter({ c })} />

      <div className="flex items-center justify-between gap-2 pt-1">
        <Segmented options={STATUSES} value={status} onChange={(s) => setFilter({ s })} />
        <button onClick={() => setAdding(true)} aria-label="Přidat položku" className="flex min-h-10 items-center gap-1 rounded-full bg-emerald-500 px-3.5 text-sm font-medium text-on-accent active:bg-emerald-400">
          <Plus size={18} /> Přidat
        </button>
      </div>
      <label className="flex min-h-11 items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950 px-3 focus-within:border-emerald-500">
        <Search size={17} className="text-zinc-500" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat v bucket listu" aria-label="Hledat" className="w-full bg-transparent text-base outline-none" />
      </label>
      <Chips label="Štítky" options={TAGS} value={tag} onChange={setTag} allLabel="Vše" />

      {shown.length === 0 ? (
        <Card className="space-y-3 text-center">
          <p className="text-zinc-400">{status === "done" ? "Tady zatím nic splněného není." : "Nic tu není. Přidej si něco, co chceš zažít."}</p>
        </Card>
      ) : grouped ? (
        CATEGORIES.map((c) => {
          const items = shown.filter((i) => i.category === c.key);
          if (!items.length) return null;
          return (
            <section key={c.key} className="space-y-2">
              <h2 className="flex items-center gap-2 px-0.5 pt-1 font-semibold">
                <c.icon size={17} className="text-zinc-400" /> {c.label}
                <span className="ml-auto text-[13px] font-normal text-zinc-400 tabular-nums">{items.length}</span>
              </h2>
              <ItemList items={items} board={data} onOpen={(id, complete) => setOpenId({ id, mode: complete ? "complete" : "view" })} />
            </section>
          );
        })
      ) : (
        <ItemList items={shown} board={data} onOpen={(id, complete) => setOpenId({ id, mode: complete ? "complete" : "view" })} />
      )}

      {opened && (
        <ItemSheet key={opened.id} item={opened} board={data} initialMode={openId?.mode} onClose={() => setOpenId(null)} />
      )}
      {dice && (
        <DiceSheet
          board={data}
          onClose={() => setDice(false)}
          onPick={(item, plan) => {
            setDice(false);
            setOpenId({ id: item.id, mode: plan ? "plan" : "view" });
          }}
        />
      )}
      {adding && (
        <Sheet title="Nová položka" onClose={() => setAdding(false)}>
          <ItemForm board={data} initialCategory={category} onDone={() => setAdding(false)} />
        </Sheet>
      )}
    </div>
  );
}

function Summary({ board }: { board: BucketBoard }) {
  const total = board.items.length;
  const done = board.items.filter((i) => i.done).length;
  const value = total ? Math.round((done / total) * 100) : 0;
  const yq = board.year_quest;
  const visited = board.countries.length;
  const continents = Object.keys(board.continents).length;
  return (
    <Card className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-3xl font-bold tracking-tight tabular-nums">
            {done} <span className="text-lg font-medium text-zinc-400">/ {total}</span>
          </div>
          <div className="text-[13px] text-zinc-400">splněno · {value} %</div>
        </div>
        <div className="text-right text-[13px] text-zinc-400">
          <div>
            <strong className="text-zinc-100">{formatNumber(board.xp_total)} XP</strong> z bucket listu
          </div>
          <div>
            {visited} {visited === 1 ? "země" : visited < 5 ? "země" : "zemí"} · {continents} / 7 kontinentů
          </div>
        </div>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-zinc-800" aria-hidden>
        {([4, 3, 2, 1] as const).map((r) => {
          const n = board.items.filter((i) => i.done && i.rarity === r).length;
          return n ? <div key={r} className={RARITY[r].bar} style={{ width: `${(n / total) * 100}%` }} /> : null;
        })}
      </div>
      <YearGoals board={board} />
      <div className="flex items-center gap-2 text-[13px] text-zinc-300">
        <Sparkles size={15} className={yq.reached_on ? "text-amber-300" : "text-zinc-500"} />
        Rok dobrodružství {yq.year}:{" "}
        <strong className="tabular-nums">
          {Math.min(yq.done, yq.target)} / {yq.target}
        </strong>
        <span className="text-zinc-500">{yq.reached_on ? "splněno" : `+${formatNumber(yq.xp)} XP`}</span>
      </div>
    </Card>
  );
}

function YearGoals({ board }: { board: BucketBoard }) {
  const year = Number(board.today.slice(0, 4));
  const goals = board.items.filter((i) => i.year_goal === year);
  if (!goals.length) {
    return <p className="text-xs text-zinc-500">Tip: označ si ★ 3–5 věcí jako letošní cíle, splněný cíl dá +{Math.round(board.year_goal_share * 100)} % XP navíc.</p>;
  }
  const done = goals.filter((i) => i.done).length;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-[13px] text-zinc-300">
        <Star size={15} className="text-amber-300" fill="currentColor" /> Letošní cíle:{" "}
        <strong className="tabular-nums">
          {done} / {goals.length}
        </strong>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {goals.map((g) => (
          <span key={g.id} className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs ${g.done ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-800 text-zinc-300"}`}>
            {g.done && <Check size={12} strokeWidth={3} />} {g.title}
          </span>
        ))}
      </div>
    </div>
  );
}

function Planned({ board, onOpen }: { board: BucketBoard; onOpen: (id: number) => void }) {
  const planned = board.items.filter((i) => !i.done && i.planned_for).sort((a, b) => a.planned_for!.localeCompare(b.planned_for!));
  if (!planned.length) return null;
  return (
    <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {planned.map((i) => (
        <button key={i.id} onClick={() => onOpen(i.id)} className={`ui-card min-w-44 shrink-0 border-l-4! p-3 text-left ${RARITY[i.rarity].ring}`}>
          <span className="flex items-center gap-1 text-xs text-zinc-400">
            <CalendarClock size={13} /> {countdown(i.planned_for!, board.today)}
          </span>
          <span className="block truncate font-semibold">{i.title}</span>
        </button>
      ))}
    </div>
  );
}

function CategoryGrid({ board, value, onChange }: { board: BucketBoard; value: Category | null; onChange: (c: Category | null) => void }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {CATEGORIES.map((c) => {
        const items = board.items.filter((i) => i.category === c.key);
        const done = items.filter((i) => i.done).length;
        const selected = value === c.key;
        return (
          <button
            key={c.key}
            aria-pressed={selected}
            onClick={() => onChange(selected ? null : c.key)}
            className={`flex flex-col items-center gap-1 rounded-2xl border px-1 py-2 ${selected ? "border-emerald-600 bg-emerald-950/50" : "border-zinc-800"}`}
          >
            <c.icon size={20} className={selected ? "text-emerald-300" : "text-zinc-300"} />
            <span className="w-full truncate text-center text-[11px] text-zinc-300">{c.label.split(" ")[0]}</span>
            <span className="h-1 w-10 overflow-hidden rounded-full bg-zinc-800">
              <span className="block h-full rounded-full bg-emerald-500" style={{ width: `${items.length ? (done / items.length) * 100 : 0}%` }} />
            </span>
            <span className="text-[11px] text-zinc-500 tabular-nums">
              {done}/{items.length}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function ItemList({ items, board, onOpen }: { items: BucketItem[]; board: BucketBoard; onOpen: (id: number, complete: boolean) => void }) {
  const year = Number(board.today.slice(0, 4));
  return (
    <div className="ui-card divide-y divide-zinc-800 overflow-hidden">
      {items.map((i) => (
        <ItemRow key={i.id} item={i} year={year} today={board.today} onOpen={(complete) => onOpen(i.id, complete)} />
      ))}
    </div>
  );
}

function ItemRow({ item, year, today, onOpen }: { item: BucketItem; year: number; today: string; onOpen: (complete: boolean) => void }) {
  const style = RARITY[item.rarity];
  const meta = [
    item.done ? null : `+${formatNumber(item.xp)} XP`,
    item.planned_for && !item.done ? countdown(item.planned_for, today) : null,
    item.travel_time,
    costLabel(item.cost),
    item.season ? SEASON_LABEL[item.season] : null,
    item.steps.length ? `${stepsDone(item)}/${item.steps.length} kroků` : null,
    !item.done && item.auto_progress ? item.auto_progress : null,
    item.source === "auto" ? `samo: ${item.auto_label}` : null,
    item.source === "before" ? "před aplikací" : null,
  ].filter(Boolean);
  return (
    <div className="flex min-h-14 items-stretch">
      <button onClick={() => onOpen(false)} className="flex min-w-0 flex-1 items-center gap-3 py-2 pr-1 pl-3 text-left active:bg-zinc-800/60">
        <span className={`w-1 self-stretch rounded-full ${style.bar} ${item.done ? "opacity-40" : ""}`} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className={`flex items-center gap-1.5 text-[15px] ${item.done ? "text-zinc-400" : ""}`}>
            <span className="truncate">{item.title}</span>
            {item.year_goal === year && <Star size={14} className="shrink-0 text-amber-300" fill="currentColor" aria-label="Letošní cíl" />}
            {item.auto_rule && !item.done && <Sparkles size={13} className="shrink-0 text-zinc-500" aria-label="Splní se samo" />}
          </span>
          <span className="block truncate text-xs text-zinc-500">
            <span className={style.text}>{style.name}</span>
            {meta.length > 0 && ` · ${meta.join(" · ")}`}
          </span>
        </span>
      </button>
      <button
        onClick={() => onOpen(!item.done)}
        aria-label={item.done ? `${item.title}: splněno` : `Splnit ${item.title}`}
        className="flex w-14 shrink-0 items-center justify-center active:bg-zinc-800/60"
      >
        <span
          className={`flex size-8 items-center justify-center rounded-full border-2 ${item.done ? "border-emerald-500 bg-emerald-500 text-on-accent" : `${style.ring} opacity-70`}`}
        >
          {item.done && <Check size={17} strokeWidth={3} />}
        </span>
      </button>
    </div>
  );
}

