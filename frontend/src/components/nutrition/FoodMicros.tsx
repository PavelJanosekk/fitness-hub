import { ChevronDown, Plus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { type Food, type MicroRef, useFoods, useNutrients } from "../../api/nutrition";
import { formatNumber } from "../../lib/format";
import { DecimalInput, parseDecimal } from "../ui";

const STATUS: Record<string, string> = {
  mapped: "doplněno automaticky",
  manual: "upraveno ručně",
  unmatched: "bez obdoby v USDA",
};

const digits = (value: number) => (value >= 100 || value === 0 ? 0 : value >= 1 ? 1 : 2);

/** Vitamins and minerals per 100 g: the food's own values and, marked ≈, those borrowed from its USDA references. */
export function NutrientValues({ food }: { food: Food }) {
  const nutrients = useNutrients();
  const [open, setOpen] = useState(false);
  const own = food.micronutrients;
  const borrowed = food.borrowed ?? {};
  const micros = (nutrients.data ?? []).filter((n) => n.micro && (n.key in own || n.key in borrowed));
  if (micros.length === 0) return <p className="text-xs text-zinc-500">Vitamíny a minerály: zatím neznámé.</p>;
  const total = (nutrients.data ?? []).filter((n) => n.micro).length;
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between py-1 text-left text-sm">
        <span className="text-zinc-300">
          Vitamíny a minerály na 100 g <span className="text-zinc-500">· {micros.length}/{total}</span>
        </span>
        <ChevronDown size={16} className={`text-zinc-500 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <>
          <ul className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            {micros.map((n) => {
              const value = own[n.key] ?? borrowed[n.key];
              const estimated = !(n.key in own);
              return (
                <li key={n.key} className="flex justify-between gap-2">
                  <span className="truncate text-zinc-400">{n.label}</span>
                  <span className={`whitespace-nowrap tabular-nums ${estimated ? "text-zinc-400" : "text-zinc-200"}`}>
                    {estimated && "≈ "}
                    {formatNumber(value, digits(value))} {n.unit}
                  </span>
                </li>
              );
            })}
          </ul>
          {Object.keys(borrowed).length > 0 && <p className="mt-1 text-xs text-zinc-500">≈ odhad z USDA podle surovin níže</p>}
        </>
      )}
    </div>
  );
}

function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

export type RefDraft = MicroRef & { gramsText: string };

export const toRefDrafts = (refs: MicroRef[]): RefDraft[] =>
  refs.map((r) => ({ ...r, gramsText: formatNumber(r.grams_per_g * 100, 1).replace(/,0$/, "") }));

/** The references to send; null while a gram field is not a valid number. */
export function refsBody(drafts: RefDraft[]): { ref_food_id: number; grams_per_g: number }[] | null {
  const out = [];
  for (const draft of drafts) {
    const grams = parseDecimal(draft.gramsText);
    if (grams === null || grams <= 0 || grams > 500) return null;
    out.push({ ref_food_id: draft.ref_food_id, grams_per_g: grams / 100 });
  }
  return out;
}

/** Which USDA foods (grams per 100 g of this food) the missing vitamins and minerals are estimated from. */
export function MicroRefsEditor({
  refs,
  onChange,
  status,
  isNew = false,
}: {
  refs: RefDraft[];
  onChange: (refs: RefDraft[]) => void;
  status: string | null;
  isNew?: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const results = useFoods(useDebounced(query), "usda");
  const hits = query.trim() ? (results.data ?? []).filter((f) => !refs.some((r) => r.ref_food_id === f.id)).slice(0, 6) : [];

  const update = (index: number, gramsText: string) => onChange(refs.map((r, i) => (i === index ? { ...r, gramsText } : r)));
  const add = (food: Food) => {
    onChange([...refs, { ref_food_id: food.id, name: food.name, grams_per_g: 1, gramsText: refs.length ? "50" : "100" }]);
    setQuery("");
    setAdding(false);
  };

  return (
    <div className="space-y-2">
      <p className="text-sm text-zinc-400">
        Suroviny pro odhad (g na 100 g){status && STATUS[status] && <span className="text-zinc-500"> · {STATUS[status]}</span>}
      </p>
      {refs.length === 0 && !adding && (
        <p className="text-xs text-zinc-500">
          {isNew ? "Můžeš nechat prázdné: po uložení se doplní automaticky." : "Žádné. Přidej surovinu z USDA, která potravině odpovídá."}
        </p>
      )}
      <ul className="space-y-1.5">
        {refs.map((ref, index) => (
          <li key={ref.ref_food_id} className="flex items-center gap-2">
            <span className="min-w-0 flex-1 text-sm leading-snug" title={ref.name}>
              {ref.name}
            </span>
            <div className="w-20 shrink-0">
              <DecimalInput ariaLabel={`Gramy: ${ref.name}`} value={ref.gramsText} onChange={(v) => update(index, v)} className="text-base" />
            </div>
            <button
              onClick={() => onChange(refs.filter((_, i) => i !== index))}
              aria-label={`Odebrat ${ref.name}`}
              className="flex size-11 shrink-0 items-center justify-center rounded-xl text-zinc-500 active:bg-zinc-800"
            >
              <X size={18} />
            </button>
          </li>
        ))}
      </ul>
      {adding ? (
        <div>
          <label className="flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3 focus-within:border-emerald-500">
            <Search size={16} className="text-zinc-500" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Hledat v USDA (anglicky)"
              className="min-h-11 flex-1 bg-transparent text-sm outline-none"
            />
          </label>
          <ul className="mt-1">
            {hits.map((food) => (
              <li key={food.id}>
                <button onClick={() => add(food)} className="w-full rounded-lg px-2 py-2 text-left text-sm active:bg-zinc-800">
                  {food.name}
                  <span className="text-xs text-zinc-500"> · {formatNumber(food.kcal)} kcal</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="flex min-h-11 items-center gap-1.5 text-sm text-emerald-300">
          <Plus size={16} /> Přidat surovinu
        </button>
      )}
    </div>
  );
}
