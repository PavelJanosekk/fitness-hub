import { ArrowLeft, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/client";
import { type Food, type FoodInput, SOURCE_LABELS, useDeleteFood, useFood, useFoods, useSaveFood } from "../api/nutrition";
import { PageHeader } from "../components/Layout";
import { SourceBadge } from "../components/nutrition/MealDraftCard";
import { Button, DecimalInput, Segmented, Sheet, parseDecimal } from "../components/ui";
import { formatNumber } from "../lib/format";

const SOURCES = [
  ["", "Vše"],
  ["custom", "Vlastní"],
  ["kaloricke_tabulky", "KT"],
  ["openfoodfacts", "OFF"],
  ["usda", "USDA"],
] as const;

const VALUE_FIELDS = [
  ["kcal", "kcal"],
  ["protein_g", "Bílkoviny g"],
  ["carbs_g", "Sacharidy g"],
  ["fat_g", "Tuky g"],
  ["sugar_g", "z toho cukry g"],
  ["saturated_fat_g", "Nasycené MK g"],
  ["fiber_g", "Vláknina g"],
  ["salt_g", "Sůl g"],
] as const;
const REQUIRED = new Set(["kcal", "protein_g", "carbs_g", "fat_g"]);

function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

/** The local food database: everything the resolver can match, editable (a fix applies to all logged meals). */
export function FoodDatabase() {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<string>("");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const foods = useFoods(useDebounced(query), source);

  return (
    <>
      <PageHeader title="Potraviny" />
      <div className="mb-3 flex items-center gap-2">
        <Link to="/nutrition" aria-label="Zpět" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
          <ArrowLeft size={20} />
        </Link>
        <label className="flex flex-1 items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-3 focus-within:border-emerald-500">
          <Search size={18} className="text-zinc-500" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat" className="min-h-11 flex-1 bg-transparent outline-none" />
        </label>
        <button onClick={() => setEditing("new")} aria-label="Nová potravina" className="flex size-11 items-center justify-center rounded-xl bg-emerald-500 text-zinc-950">
          <Plus size={20} />
        </button>
      </div>
      <div className="mb-3 overflow-x-auto">
        <Segmented options={SOURCES} value={source} onChange={setSource} />
      </div>
      <ul className="space-y-1">
        {foods.data?.map((food) => (
          <li key={food.id}>
            <button onClick={() => setEditing(food.id)} className="flex w-full items-center gap-2 rounded-xl bg-zinc-900/60 px-3 py-2.5 text-left active:bg-zinc-800">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{food.name}</span>
                <span className="text-xs text-zinc-500">
                  {formatNumber(food.kcal)} kcal · B {formatNumber(food.protein_g, 1)} · S {formatNumber(food.carbs_g, 1)} · T {formatNumber(food.fat_g, 1)}
                  {food.use_count > 0 && ` · snědeno ${food.use_count}×`}
                </span>
              </span>
              <SourceBadge source={food.source} />
            </button>
          </li>
        ))}
      </ul>
      {foods.data?.length === 0 && <p className="text-sm text-zinc-500">Nic nenalezeno.</p>}
      {editing !== null && <FoodSheet id={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function FoodSheet({ id, onClose }: { id: number | null; onClose: () => void }) {
  const food = useFood(id);
  if (id !== null && !food.data) return null;
  return (
    <Sheet title={food.data?.name ?? "Nová potravina"} onClose={onClose}>
      <FoodForm food={food.data ?? null} onDone={onClose} />
    </Sheet>
  );
}

const toText = (value: number | null | undefined) => (value === null || value === undefined ? "" : String(value).replace(".", ","));

function FoodForm({ food, onDone }: { food: Food | null; onDone: () => void }) {
  const save = useSaveFood();
  const remove = useDeleteFood();
  const [name, setName] = useState(food?.name_cs ?? food?.name ?? "");
  const [brand, setBrand] = useState(food?.brand ?? "");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(VALUE_FIELDS.map(([key]) => [key, toText(food?.[key])])),
  );
  const parsed = Object.fromEntries(VALUE_FIELDS.map(([key]) => [key, parseDecimal(values[key] ?? "")]));
  const valid = name.trim() !== "" && [...REQUIRED].every((key) => parsed[key] !== null);

  const submit = () => {
    const body: FoodInput & { id?: number } = { id: food?.id, name_cs: name.trim(), brand: brand.trim() || null, ...parsed };
    save.mutate(body, { onSuccess: onDone });
  };
  const deleteError = remove.error instanceof ApiError && remove.error.status === 409 ? "Potravina je v zapsaných jídlech, nejde smazat." : null;

  return (
    <div className="space-y-3">
      {food && (
        <p className="text-xs text-zinc-500">
          {SOURCE_LABELS[food.source]}
          {food.name_en && food.name_en !== name && ` · ${food.name_en}`}
          {food.ean && ` · EAN ${food.ean}`}
        </p>
      )}
      <label className="block text-sm text-zinc-400">
        Název (česky)
        <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-zinc-100 outline-none focus:border-emerald-500" />
      </label>
      <label className="block text-sm text-zinc-400">
        Značka
        <input value={brand} onChange={(e) => setBrand(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-zinc-100 outline-none focus:border-emerald-500" />
      </label>
      <p className="text-sm text-zinc-400">Hodnoty na 100 g (prázdné = neznámé)</p>
      <div className="grid grid-cols-2 gap-3">
        {VALUE_FIELDS.map(([key, label]) => (
          <label key={key} className="text-xs text-zinc-400">
            {label}
            {REQUIRED.has(key) && " *"}
            <DecimalInput ariaLabel={label} value={values[key] ?? ""} onChange={(v) => setValues({ ...values, [key]: v })} className="mt-1" />
          </label>
        ))}
      </div>
      {food && Object.keys(food.micronutrients).length > 0 && (
        <p className="text-xs text-zinc-500">Mikroživiny: {Object.keys(food.micronutrients).length} známých hodnot</p>
      )}
      {food && food.portions.length > 0 && (
        <p className="text-xs text-zinc-500">Porce: {food.portions.map((p) => `${p.label} ${formatNumber(p.grams)} g`).join(" · ")}</p>
      )}
      {food && food.use_count > 0 && <p className="text-xs text-amber-300">Úprava se projeví ve všech {food.use_count} zapsaných jídlech.</p>}
      <Button onClick={submit} disabled={!valid || save.isPending} className="w-full">
        {save.isError ? "Zkusit znovu" : food ? "Uložit změny" : "Vytvořit potravinu"}
      </Button>
      {food && food.use_count === 0 && (
        <Button variant="danger" onClick={() => remove.mutate(food.id, { onSuccess: onDone })} className="w-full">
          Smazat potravinu
        </Button>
      )}
      {deleteError && <p className="text-sm text-red-300">{deleteError}</p>}
    </div>
  );
}
