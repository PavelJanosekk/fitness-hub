import type { MealItem } from "../../api/types";
import { SOURCE_LABELS, useDaySummary, useFood, useNutrients } from "../../api/nutrition";
import { formatNumber } from "../../lib/format";
import { Sheet } from "../ui";

const ITEM_MACROS = ["kcal", "protein_g", "carbs_g", "fat_g"] as const;

const digits = (value: number, unit: string) => (unit === "kcal" || value >= 100 || value === 0 ? 0 : value >= 1 ? 1 : 2);

type Row = { key: string; label: string; unit: string; amount: number | null; estimated: boolean; percent: number | null };

function Rows({ rows }: { rows: Row[] }) {
  return (
    <ul className="space-y-1.5">
      {rows.map((row) => (
        <li key={row.key}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-zinc-300">{row.label}</span>
            <span className="whitespace-nowrap tabular-nums text-zinc-200">
              {row.amount === null ? (
                <span className="text-zinc-500">neznámé</span>
              ) : (
                <>
                  {row.estimated && <span className="text-zinc-500">≈ </span>}
                  {formatNumber(row.amount, digits(row.amount, row.unit))} {row.unit}
                  {row.percent !== null && <span className="text-zinc-500"> · {formatNumber(row.percent)} %</span>}
                </>
              )}
            </span>
          </div>
          {row.percent !== null && (
            <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-zinc-800">
              <div className="h-full rounded-full bg-sky-500" style={{ width: `${Math.min(100, row.percent)}%` }} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Everything one eaten item brings: kcal and macros as logged, the rest scaled from its food (≈ = from USDA references). */
export function ItemNutrientsSheet({ item, date, onClose }: { item: MealItem; date: string; onClose: () => void }) {
  const food = useFood(item.food_id ?? null);
  const nutrients = useNutrients();
  // The same targets as the day view: the user's own, else the EU reference
  const targets = Object.fromEntries((useDaySummary(date).data?.nutrients ?? []).map((n) => [n.key, n.target]));
  const grams = item.amount_g ?? null;
  const own: Record<string, number | null | undefined> = { ...(food.data?.micronutrients ?? {}) };
  if (food.data) for (const key of ["sugar_g", "saturated_fat_g", "fiber_g", "salt_g"] as const) own[key] = food.data[key];
  const borrowed = food.data?.borrowed ?? {};

  const row = (key: string, label: string, unit: string, reference: number | null): Row => {
    let amount: number | null;
    let estimated = false;
    if ((ITEM_MACROS as readonly string[]).includes(key)) {
      amount = item[key as (typeof ITEM_MACROS)[number]] ?? null;
    } else if (grams === null) {
      amount = null;
    } else if (own[key] !== null && own[key] !== undefined) {
      amount = (own[key] as number) * (grams / 100);
    } else if (borrowed[key] !== undefined) {
      amount = borrowed[key] * (grams / 100);
      estimated = true;
    } else {
      amount = null;
    }
    const percent = amount !== null && reference ? (amount / reference) * 100 : null;
    return { key, label, unit, amount, estimated, percent };
  };

  const all = (nutrients.data ?? []).map((n) => row(n.key, n.label, n.unit, targets[n.key] ?? n.reference));
  const macros = all.filter((r) => !nutrients.data?.find((n) => n.key === r.key)?.micro);
  const micros = all.filter((r) => nutrients.data?.find((n) => n.key === r.key)?.micro && r.amount !== null);
  const unknownMicros = all.filter((r) => nutrients.data?.find((n) => n.key === r.key)?.micro && r.amount === null).length;

  return (
    <Sheet title={item.food_name ?? item.label} onClose={onClose} tall>
      <p className="mb-3 text-sm text-zinc-400">
        {grams !== null ? `${formatNumber(grams)} g` : "Rychlý zápis"}
        {item.food_source && ` · ${SOURCE_LABELS[item.food_source] ?? item.food_source}`}
        {" · % z denního cíle"}
      </p>
      {item.food_id && !food.data ? (
        <p className="text-zinc-500">Načítám…</p>
      ) : (
        <div className="space-y-5">
          <Rows rows={macros} />
          {item.food_id && (
            <div>
              <h3 className="mb-2 font-semibold">Vitamíny a minerály</h3>
              {micros.length > 0 ? <Rows rows={micros} /> : <p className="text-sm text-zinc-500">U této potraviny zatím neznámé.</p>}
              {unknownMicros > 0 && micros.length > 0 && <p className="mt-2 text-xs text-zinc-500">{unknownMicros} dalších hodnot neznámých.</p>}
              {micros.some((r) => r.estimated) && <p className="mt-1 text-xs text-zinc-500">≈ odhad z USDA podle surovin potraviny</p>}
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}
