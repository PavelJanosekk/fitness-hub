import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { type Food, MEAL_TYPES, type MealType, SOURCE_LABELS, kcalFor, mealTypeNow, useFood, useFoods, usePutItem } from "../../api/nutrition";
import { formatNumber } from "../../lib/format";
import { uuid } from "../../lib/uuid";
import { Button, DecimalInput, Sheet, parseDecimal } from "../ui";

/** Debounced value, so typing doesn't fire a search per keystroke. */
function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

/** Log a food by hand: search the local database (no AI), pick grams or a portion, choose the meal. */
export function AddFoodSheet({ date, mealType, onClose }: { date: string; mealType?: MealType; onClose: () => void }) {
  const [picked, setPicked] = useState<Food | null>(null);

  return (
    <Sheet title={picked ? picked.name : "Přidat potravinu"} onClose={onClose}>
      {picked ? (
        <PortionForm food={picked} date={date} initialMealType={mealType ?? mealTypeNow()} onBack={() => setPicked(null)} onDone={onClose} />
      ) : (
        <FoodSearch onPick={setPicked} />
      )}
    </Sheet>
  );
}

/** Search field + results from the local food database; empty query = the most eaten foods. */
export function FoodSearch({ onPick, autoFocus = true }: { onPick: (food: Food) => void; autoFocus?: boolean }) {
  const [query, setQuery] = useState("");
  const foods = useFoods(useDebounced(query));
  return (
    <>
      <label className="mb-3 flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3 focus-within:border-emerald-500">
        <Search size={18} className="text-zinc-500" />
        <input
          autoFocus={autoFocus}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Hledat (česky nebo anglicky)"
          className="min-h-11 flex-1 bg-transparent outline-none"
        />
      </label>
      {!query && <p className="mb-2 text-xs text-zinc-500">Nejčastěji jedené:</p>}
      <ul className="space-y-1">
        {foods.data?.map((food) => (
          <li key={food.id}>
            <button onClick={() => onPick(food)} className="flex w-full items-center gap-2 rounded-lg bg-zinc-800/60 px-3 py-2 text-left active:bg-zinc-800">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{food.name}</span>
                <span className="text-xs text-zinc-500">
                  {formatNumber(food.kcal)} kcal · B {formatNumber(food.protein_g, 1)} g / 100 g
                  {food.brand && ` · ${food.brand}`}
                </span>
              </span>
              <span className="text-[10px] uppercase text-zinc-500">{SOURCE_LABELS[food.source]}</span>
            </button>
          </li>
        ))}
      </ul>
      {foods.data?.length === 0 && (
        <p className="text-sm text-zinc-500">
          Nic nenalezeno. Potraviny z USDA mají české jméno, až když je jednou sníš: zkus anglicky, nebo jídlo nadiktuj asistentovi.
        </p>
      )}
    </>
  );
}

function PortionForm({
  food,
  date,
  initialMealType,
  onBack,
  onDone,
}: {
  food: Food;
  date: string;
  initialMealType: MealType;
  onBack: () => void;
  onDone: () => void;
}) {
  const detail = useFood(food.id);
  const putItem = usePutItem();
  const [grams, setGrams] = useState("100");
  const [mealType, setMealType] = useState<MealType>(initialMealType);
  const amount = parseDecimal(grams) ?? 0;
  const kcal = kcalFor(food, amount);

  const save = () =>
    putItem.mutate({ id: uuid(), food_id: food.id, amount_g: amount, meal_type: mealType, date }, { onSuccess: onDone });

  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-400">
        {formatNumber(food.kcal)} kcal · B {formatNumber(food.protein_g, 1)} · S {formatNumber(food.carbs_g, 1)} · T {formatNumber(food.fat_g, 1)} g na 100 g
      </p>
      {detail.data && detail.data.portions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {detail.data.portions.slice(0, 8).map((p) => (
            <button key={p.label} onClick={() => setGrams(String(p.grams).replace(".", ","))} className="rounded-lg bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-200 active:bg-zinc-700">
              {p.label} · {formatNumber(p.grams)} g
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <DecimalInput ariaLabel="Gramy" value={grams} onChange={setGrams} className="flex-1" />
        <span className="text-zinc-400">g · {formatNumber(kcal)} kcal</span>
      </div>
      <select
        value={mealType}
        onChange={(e) => setMealType(e.target.value as MealType)}
        aria-label="Jídlo"
        className="min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3"
      >
        {MEAL_TYPES.map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
      <div className="flex gap-2">
        <Button variant="ghost" onClick={onBack}>
          Zpět
        </Button>
        <Button onClick={save} disabled={amount <= 0 || putItem.isPending} className="flex-1">
          {putItem.isError ? "Zkusit znovu" : "Přidat"}
        </Button>
      </div>
    </div>
  );
}
