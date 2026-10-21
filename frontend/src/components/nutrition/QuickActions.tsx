import { ArrowLeft, Check, CheckCircle2, ChevronRight, Loader2, Pencil, Plus, Trash2, Undo2, X, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  type MealType,
  type QuickAction,
  type QuickActionColor,
  MEAL_TYPES,
  mealTypeLabel,
  mealTypeNow,
  useDaySummary,
  useDeleteQuickAction,
  useLogQuickAction,
  useQuickActions,
  useSaveQuickAction,
  useUndoItems,
} from "../../api/nutrition";
import { formatNumber } from "../../lib/format";
import {
  COLORS,
  DAY_MINUTES,
  EMOJIS,
  MEAL_WINDOWS,
  byRelevance,
  formatMinute,
  inWindow,
  minuteOfDay,
  nextUp,
  parseTime,
  timeValue,
} from "../../lib/quickActions";
import { uuid } from "../../lib/uuid";
import { Button, DecimalInput, Sheet, parseDecimal } from "../ui";
import { FoodSearch } from "./AddFoodSheet";

type View = null | "all" | { edit: QuickAction | null };
type Toast = { title: string; detail: string; itemIds: string[]; actionId: string } | { error: string };

/** The minute of the local day, ticking, so the offered actions follow the clock while the page stays open. */
function useMinute(): number {
  const [minute, setMinute] = useState(() => minuteOfDay());
  useEffect(() => {
    const timer = window.setInterval(() => setMinute(minuteOfDay()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return minute;
}

function partOfDay(minute: number): string {
  const hour = minute / 60;
  if (hour < 5) return "v noci";
  if (hour < 9) return "ráno";
  if (hour < 12) return "dopoledne";
  if (hour < 14) return "v poledne";
  if (hour < 18) return "odpoledne";
  if (hour < 22) return "večer";
  return "v noci";
}

const itemsText = (action: Pick<QuickAction, "items">) => action.items.map((i) => `${formatNumber(i.amount_g)} g ${i.food_name}`).join(" · ");
const windowText = (action: Pick<QuickAction, "start_minute" | "end_minute">) =>
  `${formatMinute(action.start_minute)}–${formatMinute(action.end_minute)}`;

/**
 * One-tap meals on Jídlo (E42): the actions whose time window contains now as tinted cards, "Vše" for every
 * action by relevance, and an editor. A tap logs into the open day at once and offers Zpět; an action whose
 * items are in the open day is done there and folds away after its check animation.
 */
export function QuickActions({ date }: { date: string }) {
  const actions = useQuickActions();
  const summary = useDaySummary(date);
  const minute = useMinute();
  const [view, setView] = useState<View>(null);
  const { log, pendingId, doneId, leavingId, justLogged, settle, toast, undo, closeToast } = useLogWithUndo(date);
  // Done today = its items are in the open day (they carry the action's id), so Zpět or deleting them brings it back
  const inDay = useMemo(() => {
    const ids = new Set<string>();
    for (const meal of summary.data?.meals ?? []) for (const item of meal.items) if (item.quick_action_id) ids.add(item.quick_action_id);
    return ids;
  }, [summary.data]);
  useEffect(() => settle(inDay), [inDay, settle]);
  const logged = new Set([...inDay, ...justLogged]);

  const all = actions.data ?? [];
  const inWindowNow = byRelevance(all, minute).filter((a) => inWindow(a, minute));
  const current = inWindowNow.filter((a) => !logged.has(a.id) || [pendingId, doneId, leavingId].includes(a.id));
  const allDone = inWindowNow.length > 0 && current.length === 0;
  const next = current.length ? null : nextUp(all.filter((a) => !logged.has(a.id)), minute);
  const nextPosition = all.reduce((max, a) => Math.max(max, a.position + 1), 0);
  const state = (action: QuickAction) => (pendingId === action.id ? "pending" : doneId === action.id ? "done" : "idle");

  if (!actions.data) return null;
  return (
    <section aria-label="Rychlé přidání">
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-200">
          <Zap size={15} className="text-amber-400" fill="currentColor" />
          Rychlé přidání
          {all.length > 0 && <span className="font-normal text-zinc-500">· {partOfDay(minute)}</span>}
        </h2>
        {all.length > 0 && (
          <button onClick={() => setView("all")} className="-mr-1 flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-emerald-400 active:bg-zinc-800">
            Vše <span className="text-xs text-zinc-500 tabular-nums">{all.length}</span>
            <ChevronRight size={16} />
          </button>
        )}
      </div>

      {all.length === 0 ? (
        <button onClick={() => setView({ edit: null })} className="qa-card qa-amber qa-empty">
          <span className="qa-emoji">⚡</span>
          <span className="min-w-0 flex-1">
            <span className="block font-semibold text-zinc-50">Vytvoř si rychlou akci</span>
            <span className="block text-xs text-zinc-400">Jídlo, které jíš často, pak zapíšeš jedním klepnutím.</span>
          </span>
          <span className="qa-plus">
            <Plus size={18} />
          </span>
        </button>
      ) : current.length > 0 ? (
        <div>
          {current.map((action) => (
            <div key={action.id} className={`qa-fold ${leavingId === action.id ? "qa-leaving" : ""}`}>
              <div className="min-h-0">
                <ActionCard action={action} state={state(action)} onLog={() => log(action)} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <button onClick={() => setView("all")} className="flex w-full items-center gap-2 rounded-2xl border border-dashed border-zinc-700 px-3 py-2.5 text-left text-sm text-zinc-400 active:bg-zinc-800">
          <span className="min-w-0 flex-1">
            {allDone ? (
              <span className="flex items-center gap-1.5 text-zinc-200">
                <Check size={16} strokeWidth={3} className="text-emerald-400" /> Na teď máš zapsáno
              </span>
            ) : (
              <span className="block text-zinc-300">Teď nic</span>
            )}
            {next && (
              <span className="block truncate text-xs text-zinc-500">
                Další: {next.emoji} {next.name} od {formatMinute(next.start_minute)}
              </span>
            )}
          </span>
          <ChevronRight size={16} className="text-zinc-500" />
        </button>
      )}

      {view === "all" && (
        <AllActionsSheet
          actions={all}
          minute={minute}
          logged={logged}
          pendingId={pendingId}
          onLog={(action) => (log(action), setView(null))}
          onEdit={(action) => setView({ edit: action })}
          onClose={() => setView(null)}
        />
      )}
      {view && view !== "all" && (
        <ActionEditor action={view.edit} nextPosition={nextPosition} onClose={() => setView(all.length ? "all" : null)} />
      )}
      {toast && <UndoToast toast={toast} onUndo={undo} onClose={closeToast} />}
    </section>
  );
}

/** Logging with a short-lived toast; Zpět deletes exactly the items this tap created. */
function useLogWithUndo(date: string) {
  const logAction = useLogQuickAction();
  const undoItems = useUndoItems();
  const [toast, setToast] = useState<Toast | null>(null);
  const [doneId, setDoneId] = useState<string | null>(null);
  const [leavingId, setLeavingId] = useState<string | null>(null);
  // Logged in this visit and not yet in the refetched summary: keeps a done card from popping back for a moment
  const [justLogged, setJustLogged] = useState<{ date: string; ids: string[] }>({ date, ids: [] });
  const justLoggedIds = justLogged.date === date ? justLogged.ids : [];

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  // The check shows for a moment, then the card folds away (qa-leaving) and is gone
  useEffect(() => {
    if (!doneId) return;
    const timer = window.setTimeout(() => (setLeavingId(doneId), setDoneId(null)), 1100);
    return () => window.clearTimeout(timer);
  }, [doneId]);
  useEffect(() => {
    if (!leavingId) return;
    const timer = window.setTimeout(() => setLeavingId(null), 450);
    return () => window.clearTimeout(timer);
  }, [leavingId]);

  const log = (action: QuickAction) => {
    const itemIds = action.items.map(() => uuid());
    logAction.mutate(
      { action, date, itemIds },
      {
        onSuccess: () => {
          setDoneId(action.id);
          setJustLogged((prev) => ({ date, ids: [...(prev.date === date ? prev.ids : []), action.id] }));
          setToast({
            title: `${action.emoji} ${action.name}`,
            detail: `Přidáno do: ${mealTypeLabel(action.meal_type)} · ${formatNumber(action.kcal)} kcal · ${formatNumber(action.protein_g)} g B`,
            itemIds,
            actionId: action.id,
          });
        },
        onError: () => setToast({ error: `${action.name} se nepodařilo přidat.` }),
      },
    );
  };
  const undo = () => {
    if (toast && "itemIds" in toast) {
      undoItems.mutate(toast.itemIds);
      setJustLogged((prev) => ({ ...prev, ids: prev.ids.filter((id) => id !== toast.actionId) }));
    }
    setToast(null);
    setDoneId(null);
    setLeavingId(null);
  };
  const pendingId = logAction.isPending ? (logAction.variables?.action.id ?? null) : null;
  // Once the day's summary has an action's items, it is the source of truth
  const settle = useCallback(
    (inDay: Set<string>) =>
      setJustLogged((prev) => (prev.ids.some((id) => inDay.has(id)) ? { ...prev, ids: prev.ids.filter((id) => !inDay.has(id)) } : prev)),
    [],
  );
  return { log, pendingId, doneId, leavingId, justLogged: justLoggedIds, settle, toast, undo, closeToast: () => setToast(null) };
}

type CardState = "idle" | "pending" | "done";

/** The big tinted card; without `onLog` it is the editor's live preview. */
function ActionCard({
  action,
  state = "idle",
  onLog,
}: {
  action: Pick<QuickAction, "name" | "emoji" | "color" | "meal_type" | "items" | "kcal" | "protein_g">;
  state?: CardState;
  onLog?: () => void;
}) {
  const body = (
    <>
      <span className="qa-emoji" aria-hidden>
        {action.emoji}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold text-zinc-50">{action.name || "Bez názvu"}</span>
        <span className="block truncate text-xs text-zinc-400">
          <span className="qa-ink font-medium">{mealTypeLabel(action.meal_type)}</span>
          {action.items.length > 0 && ` · ${itemsText(action)}`}
        </span>
      </span>
      <span className="shrink-0 text-right tabular-nums leading-tight">
        <span className="block font-semibold text-zinc-50">
          {formatNumber(action.kcal)} <span className="text-xs font-normal text-zinc-400">kcal</span>
        </span>
        <span className="block text-xs text-zinc-400">{formatNumber(action.protein_g)} g B</span>
      </span>
      <span className="qa-plus" aria-hidden>
        {state === "pending" ? <Loader2 size={18} className="animate-spin" /> : state === "done" ? <Check size={18} strokeWidth={3} /> : <Plus size={18} strokeWidth={2.5} />}
      </span>
    </>
  );
  const className = `qa-card qa-${action.color} ${state === "done" ? "qa-done" : ""}`;
  if (!onLog) return <div className={className}>{body}</div>;
  return (
    <button onClick={onLog} disabled={state === "pending"} aria-label={`Přidat ${action.name}`} className={className}>
      {body}
    </button>
  );
}

function AllActionsSheet({
  actions,
  minute,
  logged,
  pendingId,
  onLog,
  onEdit,
  onClose,
}: {
  actions: QuickAction[];
  minute: number;
  logged: Set<string>;
  pendingId: string | null;
  onLog: (action: QuickAction) => void;
  onEdit: (action: QuickAction | null) => void;
  onClose: () => void;
}) {
  return (
    <Sheet title="Rychlé akce" onClose={onClose}>
      <p className="-mt-1 mb-3 text-xs text-zinc-500">Nahoře to, co se hodí teď, dál podle toho, jak blízko je jejich čas.</p>
      <ul className="space-y-2">
        {byRelevance(actions, minute).map((action) => {
          const now = inWindow(action, minute);
          return (
            <li key={action.id} className={`qa-row qa-${action.color} ${now ? "qa-row-now" : ""}`}>
              <span className="qa-emoji qa-emoji-sm" aria-hidden>
                {action.emoji}
              </span>
              <button onClick={() => onEdit(action)} className="min-w-0 flex-1 text-left">
                <span className="flex items-center gap-1.5">
                  <span className="truncate font-medium text-zinc-100">{action.name}</span>
                  {logged.has(action.id) ? (
                    <span className="qa-badge qa-badge-done">
                      <Check size={11} strokeWidth={3} /> Zapsáno
                    </span>
                  ) : (
                    now && <span className="qa-badge">Teď</span>
                  )}
                </span>
                <span className="line-clamp-2 text-xs text-zinc-500">
                  {mealTypeLabel(action.meal_type)} · {windowText(action)} · {formatNumber(action.kcal)} kcal
                </span>
              </button>
              <button onClick={() => onEdit(action)} aria-label={`Upravit ${action.name}`} className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
                <Pencil size={16} />
              </button>
              <button onClick={() => onLog(action)} disabled={pendingId === action.id} aria-label={`Přidat ${action.name}`} className="qa-plus qa-plus-sm">
                {pendingId === action.id ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} strokeWidth={2.5} />}
              </button>
            </li>
          );
        })}
      </ul>
      <Button variant="ghost" onClick={() => onEdit(null)} className="mt-4 flex w-full items-center justify-center gap-1.5">
        <Plus size={18} /> Nová rychlá akce
      </Button>
    </Sheet>
  );
}

const COLOR_LABELS: Record<QuickActionColor, string> = { amber: "Oranžová", emerald: "Zelená", sky: "Modrá", violet: "Fialová", red: "Červená" };

type EditItem = { food_id: number; food_name: string; kcalPerG: number; proteinPerG: number; grams: string };

const gramsText = (grams: number) => String(grams).replace(".", ",");

function ActionEditor({ action, nextPosition, onClose }: { action: QuickAction | null; nextPosition: number; onClose: () => void }) {
  const save = useSaveQuickAction();
  const remove = useDeleteQuickAction();
  const initialMeal = action?.meal_type ?? mealTypeNow();
  const [name, setName] = useState(action?.name ?? "");
  const [emoji, setEmoji] = useState(action?.emoji ?? "🥣");
  const [color, setColor] = useState<QuickActionColor>(action?.color ?? "amber");
  const [mealType, setMealType] = useState<MealType>(initialMeal);
  const [start, setStart] = useState(timeValue(action?.start_minute ?? MEAL_WINDOWS[initialMeal][0]));
  const [end, setEnd] = useState(timeValue(action?.end_minute ?? MEAL_WINDOWS[initialMeal][1]));
  const [windowTouched, setWindowTouched] = useState(action !== null);
  const [items, setItems] = useState<EditItem[]>(
    () =>
      action?.items.map((i) => ({
        food_id: i.food_id,
        food_name: i.food_name,
        kcalPerG: i.kcal / i.amount_g,
        proteinPerG: i.protein_g / i.amount_g,
        grams: gramsText(i.amount_g),
      })) ?? [],
  );
  const [picking, setPicking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const startMinute = parseTime(start);
  const parsedEnd = parseTime(end);
  const endMinute = parsedEnd === 0 ? DAY_MINUTES : parsedEnd; // "00:00" as an end is midnight
  const amounts = items.map((i) => parseDecimal(i.grams) ?? 0);
  const kcal = items.reduce((sum, i, n) => sum + i.kcalPerG * amounts[n], 0);
  const protein = items.reduce((sum, i, n) => sum + i.proteinPerG * amounts[n], 0);
  const windowOk = startMinute !== null && endMinute !== null && startMinute < endMinute;
  const valid = name.trim() !== "" && items.length > 0 && amounts.every((g) => g > 0 && g <= 5000) && windowOk;

  const pickMeal = (meal: MealType) => {
    setMealType(meal);
    if (!windowTouched) {
      setStart(timeValue(MEAL_WINDOWS[meal][0]));
      setEnd(timeValue(MEAL_WINDOWS[meal][1]));
    }
  };

  const submit = () => {
    if (!valid) return;
    save.mutate(
      {
        id: action?.id ?? uuid(),
        name: name.trim(),
        emoji,
        color,
        meal_type: mealType,
        start_minute: startMinute!,
        end_minute: endMinute!,
        position: action?.position ?? nextPosition,
        items: items.map((i, n) => ({ food_id: i.food_id, amount_g: amounts[n] })),
      },
      { onSuccess: onClose },
    );
  };

  const title = action ? "Upravit rychlou akci" : "Nová rychlá akce";
  if (picking) {
    return (
      <Sheet title="Přidat potravinu" onClose={() => setPicking(false)} tall>
        <button onClick={() => setPicking(false)} className="-mt-1 mb-3 flex items-center gap-1 text-sm text-zinc-400">
          <ArrowLeft size={16} /> {title}
        </button>
        <FoodSearch
          onPick={(food) => {
            setItems((list) => [
              ...list,
              { food_id: food.id, food_name: food.name, kcalPerG: food.kcal / 100, proteinPerG: food.protein_g / 100, grams: "100" },
            ]);
            if (!name.trim() && items.length === 0) setName(food.name);
            setPicking(false);
          }}
        />
      </Sheet>
    );
  }

  const label = "mb-1.5 block text-xs font-medium uppercase tracking-wide text-zinc-500";
  return (
    <Sheet title={title} onClose={onClose}>
      <div className="space-y-4">
        <ActionCard
          action={{
            name: name.trim(),
            emoji,
            color,
            meal_type: mealType,
            kcal,
            protein_g: protein,
            items: items.map((i, n) => ({ food_id: i.food_id, food_name: i.food_name, amount_g: amounts[n], kcal: 0, protein_g: 0 })),
          }}
        />

        <div>
          <label className={label} htmlFor="qa-name">
            Název
          </label>
          <input
            id="qa-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            placeholder="Třeba Vločky s proteinem"
            className="min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 outline-none placeholder:text-zinc-600 focus:border-emerald-500"
          />
        </div>

        <div>
          <span className={label}>Ikona a barva</span>
          <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {EMOJIS.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => setEmoji(e)}
                aria-pressed={emoji === e}
                className={`qa-${color} qa-pick flex size-10 shrink-0 items-center justify-center rounded-xl text-xl`}
              >
                {e}
              </button>
            ))}
          </div>
          <div className="mt-2 flex gap-2.5" role="group" aria-label="Barva">
            {COLORS.map((c) => (
              <button key={c} type="button" onClick={() => setColor(c)} aria-pressed={color === c} aria-label={COLOR_LABELS[c]} className={`qa-${c} qa-swatch`} />
            ))}
          </div>
        </div>

        <div>
          <span className={label}>Jídlo</span>
          <div className="flex flex-wrap gap-1.5">
            {MEAL_TYPES.filter(([key]) => key !== "fueling").map(([key, text]) => (
              <button
                key={key}
                type="button"
                onClick={() => pickMeal(key)}
                aria-pressed={mealType === key}
                className={`min-h-9 rounded-full px-3 text-sm ${mealType === key ? "bg-emerald-500 font-medium text-on-accent" : "bg-zinc-800 text-zinc-300 active:bg-zinc-700"}`}
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className={label}>Nabízet</span>
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-400">od</span>
            <input
              type="time"
              aria-label="Od"
              value={start}
              onChange={(e) => (setStart(e.target.value), setWindowTouched(true))}
              className="min-h-11 flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-3 tabular-nums outline-none focus:border-emerald-500"
            />
            <span className="text-sm text-zinc-400">do</span>
            <input
              type="time"
              aria-label="Do"
              value={end}
              onChange={(e) => (setEnd(e.target.value), setWindowTouched(true))}
              className="min-h-11 flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-3 tabular-nums outline-none focus:border-emerald-500"
            />
          </div>
          {!windowOk && <p className="mt-1 text-xs text-red-300">Začátek musí být před koncem (konec 0:00 = půlnoc).</p>}
        </div>

        <div>
          <span className={label}>Potraviny</span>
          <ul className="space-y-1.5">
            {items.map((item, n) => (
              <li key={`${item.food_id}-${n}`} className="flex items-center gap-2 rounded-xl bg-zinc-800/60 py-1.5 pr-1.5 pl-3">
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 text-sm leading-snug text-zinc-200">{item.food_name}</span>
                  <span className="text-xs tabular-nums text-zinc-500">
                    {formatNumber(item.kcalPerG * amounts[n])} kcal · {formatNumber(item.proteinPerG * amounts[n], 1)} g B
                  </span>
                </span>
                <div className="w-20">
                  <DecimalInput
                    ariaLabel={`Gramy ${item.food_name}`}
                    value={item.grams}
                    onChange={(grams) => setItems((list) => list.map((x, m) => (m === n ? { ...x, grams } : x)))}
                    className="!min-h-9 text-right !text-base"
                  />
                </div>
                <span className="text-sm text-zinc-500">g</span>
                <button
                  type="button"
                  onClick={() => setItems((list) => list.filter((_, m) => m !== n))}
                  aria-label={`Odebrat ${item.food_name}`}
                  className="rounded-full p-1.5 text-zinc-500 active:bg-zinc-700"
                >
                  <X size={16} />
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => setPicking(true)}
            disabled={items.length >= 15}
            className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-zinc-700 py-2.5 text-sm text-emerald-400 active:bg-zinc-800"
          >
            <Plus size={16} /> Přidat potravinu
          </button>
        </div>

        {save.isError && <p className="text-sm text-red-300">Uložení se nepovedlo, zkus to znovu.</p>}
        <div className="flex gap-2">
          {action && (
            <Button
              variant="danger"
              onClick={() => (confirmDelete ? remove.mutate(action.id, { onSuccess: onClose }) : setConfirmDelete(true))}
              disabled={remove.isPending}
              className="flex items-center gap-1.5"
            >
              <Trash2 size={16} /> {confirmDelete ? "Opravdu?" : "Smazat"}
            </Button>
          )}
          <Button onClick={submit} disabled={!valid || save.isPending} className="flex-1">
            {save.isPending ? "Ukládám…" : "Uložit"}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}

function UndoToast({ toast, onUndo, onClose }: { toast: Toast; onUndo: () => void; onClose: () => void }) {
  return createPortal(
    <div className="qa-toast-wrap pointer-events-none fixed inset-x-0 z-50 flex justify-center px-4">
      <div role="status" className="qa-toast pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-2xl border border-zinc-700 bg-zinc-900 py-2 pr-2 pl-4">
        {"error" in toast ? (
          <>
            <X size={20} className="shrink-0 text-red-400" />
            <span className="flex-1 text-sm text-zinc-200">{toast.error}</span>
            <button onClick={onClose} aria-label="Zavřít" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
              <X size={16} />
            </button>
          </>
        ) : (
          <>
            <CheckCircle2 size={20} className="shrink-0 text-emerald-400" />
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate text-sm font-medium text-zinc-100">{toast.title}</span>
              <span className="block truncate text-xs text-zinc-400">{toast.detail}</span>
            </span>
            <button onClick={onUndo} className="flex min-h-10 items-center gap-1 rounded-xl px-3 text-sm font-semibold text-emerald-400 active:bg-zinc-800">
              <Undo2 size={16} /> Zpět
            </button>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
