import { CalendarClock, Check, ExternalLink, MapPin, Pencil, Plus, Sparkles, Star, Trash2, X } from "lucide-react";
import { useState } from "react";
import { type BucketBoard, type BucketItem, useDeleteBucketItem, useSaveBucketItem, useSaveStep } from "../../api/bucket";
import { CATEGORY, costLabel, countdown, countryName, fullDate, RARITY, SEASON_LABEL, stepsDone } from "../../lib/bucket";
import { addDays, formatNumber } from "../../lib/format";
import { Button, Sheet } from "../ui";
import { ItemForm, saveError } from "./ItemForm";

type Mode = "view" | "complete" | "edit" | "plan";

const input =
  "mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

/** One item: details, complete (date, ★, memory), plan, year goal, steps, edit, delete. */
export function ItemSheet({
  item,
  board,
  initialMode = "view",
  onClose,
  onCompleted,
}: {
  item: BucketItem;
  board: BucketBoard;
  initialMode?: Mode;
  onClose: () => void;
  onCompleted?: (item: BucketItem) => void;
}) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const save = useSaveBucketItem();
  const remove = useDeleteBucketItem();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const year = Number(board.today.slice(0, 4));
  const style = RARITY[item.rarity];
  const category = CATEGORY[item.category];
  const Icon = category.icon;
  const goal = item.year_goal === year;

  if (mode === "edit") {
    return (
      <Sheet title="Upravit položku" onClose={onClose}>
        <ItemForm item={item} board={board} onDone={() => setMode("view")} />
      </Sheet>
    );
  }

  return (
    <Sheet title={item.title} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className={`rounded-full px-2.5 py-1 font-semibold ${style.soft} ${style.text}`}>{style.name}</span>
          <span className="flex items-center gap-1 rounded-full bg-zinc-800 px-2.5 py-1 text-zinc-300">
            <Icon size={13} /> {category.label}
          </span>
          <span className="rounded-full bg-zinc-800 px-2.5 py-1 text-zinc-300">
            {item.done ? (item.xp ? `+${formatNumber(item.xp + item.goal_xp)} XP` : "bez XP") : `+${formatNumber(item.xp)} XP`}
          </span>
          {goal && (
            <span className="flex items-center gap-1 rounded-full bg-amber-400/15 px-2.5 py-1 text-amber-300">
              <Star size={13} fill="currentColor" /> Letošní cíl
            </span>
          )}
        </div>

        <Details item={item} board={board} />

        {item.done ? <DoneBlock item={item} onEdit={() => setMode("complete")} /> : null}

        {mode === "complete" ? (
          <CompleteForm
            item={item}
            today={board.today}
            onCancel={() => setMode("view")}
            onSaved={(saved) => {
              setMode("view");
              if (!item.done && saved.done) onCompleted?.(saved);
            }}
          />
        ) : mode === "plan" ? (
          <PlanForm item={item} today={board.today} onDone={() => setMode("view")} />
        ) : (
          !item.done && (
            <div className="grid grid-cols-2 gap-2">
              <Button className="col-span-2 flex items-center justify-center gap-2" onClick={() => setMode("complete")}>
                <Check size={18} /> Splněno!
              </Button>
              <Button variant="ghost" className="flex items-center justify-center gap-2" onClick={() => setMode("plan")}>
                <CalendarClock size={17} /> {item.planned_for ? "Přeplánovat" : "Naplánovat"}
              </Button>
              <Button
                variant="ghost"
                className={`flex items-center justify-center gap-2 ${goal ? "text-amber-300!" : ""}`}
                disabled={save.isPending}
                onClick={() => save.mutate({ id: item.id, year_goal: goal ? null : year })}
              >
                <Star size={17} fill={goal ? "currentColor" : "none"} /> {goal ? "Cíl letos" : "Cíl na letošek"}
              </Button>
            </div>
          )
        )}

        <Steps item={item} board={board} />

        {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
        {remove.isError && <p className="text-sm text-red-300">{saveError(remove.error)}</p>}

        <div className="flex gap-2 border-t border-zinc-800 pt-3">
          <Button variant="ghost" className="flex flex-1 items-center justify-center gap-2" onClick={() => setMode("edit")}>
            <Pencil size={16} /> Upravit
          </Button>
          {confirmDelete ? (
            <Button variant="danger" className="flex-1" disabled={remove.isPending} onClick={() => remove.mutate(item.id, { onSuccess: onClose })}>
              Opravdu smazat
            </Button>
          ) : (
            <Button variant="danger" aria-label="Smazat položku" className="flex items-center justify-center" onClick={() => setConfirmDelete(true)}>
              <Trash2 size={17} />
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}

function Details({ item, board }: { item: BucketItem; board: BucketBoard }) {
  const rows: [React.ReactNode, React.ReactNode][] = [];
  if (item.planned_for && !item.done) rows.push(["Naplánováno", `${fullDate(item.planned_for)} · ${countdown(item.planned_for, board.today)}`]);
  if (item.travel_time) rows.push(["Cesta z domova", item.travel_time]);
  if (item.season) rows.push(["Sezóna", SEASON_LABEL[item.season]]);
  if (item.cost) rows.push(["Cena", costLabel(item.cost)]);
  if (item.country_codes.length) rows.push(["Země", item.country_codes.map(countryName).join(", ")]);
  if (item.auto_rule) {
    const what = {
      marathon: "běh ≥ 42 km (≥ 40 km v den závodu)",
      exercise: `první série cviku ${item.auto_exercise_name ?? "?"}`,
      hike: `túra s převýšením ≥ ${item.auto_threshold ?? 1000} m`,
      continents: `${item.auto_threshold ?? 7} kontinentů na mapě`,
    }[item.auto_rule];
    rows.push(["Splní se samo", item.auto_progress ? `${what} · teď ${item.auto_progress}` : what]);
  }
  return (
    <div className="space-y-2">
      {item.note && <p className="text-[15px] whitespace-pre-line text-zinc-200">{item.note}</p>}
      {rows.length > 0 && (
        <dl className="ui-card divide-y divide-zinc-800 overflow-hidden text-sm">
          {rows.map(([label, value], i) => (
            <div key={i} className="flex justify-between gap-3 px-3 py-2">
              <dt className="shrink-0 text-zinc-400">{label}</dt>
              <dd className="text-right">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {item.link && (
        <a href={item.link} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm text-emerald-400">
          <ExternalLink size={15} /> Odkaz
        </a>
      )}
      {item.lat != null && item.lon != null && (
        <a
          href={`https://www.openstreetmap.org/?mlat=${item.lat}&mlon=${item.lon}#map=11/${item.lat}/${item.lon}`}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-sm text-emerald-400"
        >
          <MapPin size={15} /> Na mapě
        </a>
      )}
    </div>
  );
}

function DoneBlock({ item, onEdit }: { item: BucketItem; onEdit: () => void }) {
  const save = useSaveBucketItem();
  const when =
    item.source === "before"
      ? "Splněno ještě před aplikací"
      : item.source === "auto"
        ? `Splněno samo ${fullDate(item.completed_on!)}${item.auto_label ? ` · ${item.auto_label}` : ""}`
        : `Splněno ${fullDate(item.completed_on!)}`;
  return (
    <div className="space-y-2 rounded-2xl border border-emerald-800/60 bg-emerald-950/30 p-3">
      <p className="flex items-center gap-2 font-medium text-emerald-300">
        {item.source === "auto" ? <Sparkles size={17} /> : <Check size={17} />} {when}
      </p>
      {item.rating ? <Stars value={item.rating} /> : null}
      {item.memory && <p className="text-sm whitespace-pre-line text-zinc-200">{item.memory}</p>}
      <div className="flex flex-wrap gap-2 pt-1">
        <button onClick={onEdit} className="min-h-9 rounded-full bg-zinc-800 px-3 text-sm active:bg-zinc-700">
          {item.memory || item.rating ? "Upravit vzpomínku" : "Přidat vzpomínku"}
        </button>
        {item.source !== "auto" && (
          <button
            onClick={() => save.mutate({ id: item.id, done_on: null, done_before_app: false })}
            disabled={save.isPending}
            className="min-h-9 rounded-full px-3 text-sm text-zinc-400 active:bg-zinc-800"
          >
            Zrušit splnění
          </button>
        )}
      </div>
      {item.source === "auto" && <p className="text-xs text-zinc-500">Splnilo se z dat aplikace; vypneš to v úpravách (automatické splnění).</p>}
    </div>
  );
}

export function Stars({ value, onChange }: { value: number; onChange?: (value: number) => void }) {
  return (
    <div className="flex gap-1" role={onChange ? "radiogroup" : undefined} aria-label="Hodnocení">
      {[1, 2, 3, 4, 5].map((n) =>
        onChange ? (
          <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} z 5`} onClick={() => onChange(value === n ? 0 : n)} className="p-1">
            <Star size={26} className={n <= value ? "text-amber-300" : "text-zinc-600"} fill={n <= value ? "currentColor" : "none"} />
          </button>
        ) : (
          <Star key={n} size={16} className={n <= value ? "text-amber-300" : "text-zinc-700"} fill={n <= value ? "currentColor" : "none"} />
        ),
      )}
    </div>
  );
}

function CompleteForm({ item, today, onCancel, onSaved }: { item: BucketItem; today: string; onCancel: () => void; onSaved: (item: BucketItem) => void }) {
  const save = useSaveBucketItem();
  const before = item.source === "before";
  const [day, setDay] = useState(item.done_on ?? item.completed_on ?? today);
  const [rating, setRating] = useState(item.rating ?? 0);
  const [memory, setMemory] = useState(item.memory ?? "");
  const keepsDay = item.source === "auto" || before;
  return (
    <form
      className="space-y-3 rounded-2xl border border-zinc-800 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        const body = { memory: memory.trim() || null, rating: rating || null, ...(keepsDay ? {} : { done_on: day }) };
        save.mutate({ id: item.id, ...body }, { onSuccess: onSaved });
      }}
    >
      {!keepsDay && (
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
        <textarea value={memory} maxLength={2000} rows={3} onChange={(e) => setMemory(e.target.value)} placeholder="S kým, kde, co se povedlo…" className={`${input} py-2`} />
      </label>
      {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
      <div className="grid grid-cols-[auto_1fr] gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Zpět
        </Button>
        <Button type="submit" disabled={save.isPending || !day}>
          {save.isPending ? "Ukládám…" : item.done ? "Uložit" : `Splněno · +${formatNumber(item.xp)} XP`}
        </Button>
      </div>
      {!item.done && day < addDays(item.created_at.slice(0, 10), -7) && (
        <p className="text-xs text-zinc-500">Splnění víc než týden před přidáním na seznam se počítá bez XP.</p>
      )}
    </form>
  );
}

function PlanForm({ item, today, onDone }: { item: BucketItem; today: string; onDone: () => void }) {
  const save = useSaveBucketItem();
  const [day, setDay] = useState(item.planned_for ?? "");
  return (
    <form
      className="space-y-3 rounded-2xl border border-zinc-800 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ id: item.id, planned_for: day || null }, { onSuccess: onDone });
      }}
    >
      <label className="block text-sm text-zinc-400">
        Kdy to chceš zažít
        <input type="date" value={day} min={today} onChange={(e) => setDay(e.target.value)} className={input} />
      </label>
      {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
      <div className="grid grid-cols-2 gap-2">
        {item.planned_for ? (
          <Button type="button" variant="ghost" disabled={save.isPending} onClick={() => save.mutate({ id: item.id, planned_for: null }, { onSuccess: onDone })}>
            Zrušit plán
          </Button>
        ) : (
          <Button type="button" variant="ghost" onClick={onDone}>
            Zpět
          </Button>
        )}
        <Button type="submit" disabled={save.isPending || !day}>
          Naplánovat
        </Button>
      </div>
    </form>
  );
}

function Steps({ item, board }: { item: BucketItem; board: BucketBoard }) {
  const saveStep = useSaveStep();
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);
  if (!item.steps.length && !adding) {
    return item.done ? null : (
      <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 text-sm text-zinc-400">
        <Plus size={15} /> Rozdělit na kroky (+{board.step_xp} XP za krok)
      </button>
    );
  }
  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="font-semibold">Kroky</h3>
        <span className="text-xs text-zinc-400 tabular-nums">
          {stepsDone(item)} / {item.steps.length} · +{board.step_xp} XP za krok
        </span>
      </div>
      {item.steps.length > 0 && (
        <div className="ui-card divide-y divide-zinc-800 overflow-hidden">
          {item.steps.map((s) => (
            <div key={s.id} className="flex min-h-12 items-center gap-3 px-3">
              <button
                aria-label={s.done_on ? `Zrušit krok ${s.title}` : `Splnit krok ${s.title}`}
                disabled={saveStep.isPending}
                onClick={() => saveStep.mutate({ stepId: s.id, done_on: s.done_on ? null : board.today })}
                className={`flex size-7 shrink-0 items-center justify-center rounded-full border-2 ${s.done_on ? "border-emerald-500 bg-emerald-500 text-on-accent" : "border-zinc-600"}`}
              >
                {s.done_on && <Check size={15} strokeWidth={3} />}
              </button>
              <span className={`flex-1 text-sm ${s.done_on ? "text-zinc-400" : ""}`}>{s.title}</span>
              {s.done_on && <span className="text-xs text-zinc-500">{fullDate(s.done_on)}</span>}
              <button aria-label={`Smazat krok ${s.title}`} onClick={() => saveStep.mutate({ stepId: s.id, remove: true })} className="rounded-full p-1.5 text-zinc-500 active:bg-zinc-800">
                <X size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) saveStep.mutate({ itemId: item.id, title: title.trim() }, { onSuccess: () => setTitle("") });
        }}
      >
        <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="Nový krok" aria-label="Nový krok" className={`${input} mt-0`} />
        <button type="submit" aria-label="Přidat krok" disabled={!title.trim() || saveStep.isPending} className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-zinc-800 active:bg-zinc-700 disabled:opacity-40">
          <Plus size={18} />
        </button>
      </form>
      {saveStep.isError && <p className="text-sm text-red-300">{saveError(saveStep.error)}</p>}
    </section>
  );
}
