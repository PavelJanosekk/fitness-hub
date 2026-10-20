import { Plus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { type BucketAutoRule, type BucketBoard, type BucketInput, type BucketItem, type Category, type Season, useSaveBucketItem } from "../../api/bucket";
import { useExercises } from "../../api/gym";
import { CATEGORIES, countryName, RARITY, SEASONS } from "../../lib/bucket";
import { formatNumber } from "../../lib/format";
import { Button, Chips, DecimalInput, parseDecimal, Segmented } from "../ui";

const COSTS = [
  [0, "–"],
  [1, "€"],
  [2, "€€"],
  [3, "€€€"],
] as const;

const AUTO = [
  { rule: null, label: "Ne, jen ručně" },
  { rule: "marathon", label: "Uběhnutý maraton", hint: "běh ≥ 42 km" },
  { rule: "exercise", label: "Zapsaný cvik v gymu", hint: "první série" },
  { rule: "hike", label: "Túra s převýšením", hint: "Strava" },
  { rule: "continents", label: "Počet kontinentů", hint: "mapa světa" },
] as const;

const input =
  "mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

export function saveError(error: Error): string {
  if (error instanceof ApiError) return `Chyba ${error.status}: ${error.message}`;
  return navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, bucket list jde upravit jen s připojením.";
}

/** Create (`item` undefined) or edit an item: name, category, rarity, details, tags, countries, auto rule. */
export function ItemForm({
  item,
  board,
  initialCategory,
  onDone,
}: {
  item?: BucketItem;
  board: BucketBoard;
  initialCategory?: Category | null;
  onDone: (item: BucketItem) => void;
}) {
  const save = useSaveBucketItem();
  const [title, setTitle] = useState(item?.title ?? "");
  const [category, setCategory] = useState<Category | null>(item?.category ?? initialCategory ?? null);
  const [rarity, setRarity] = useState<number>(item?.rarity ?? 1);
  const [note, setNote] = useState(item?.note ?? "");
  const [link, setLink] = useState(item?.link ?? "");
  const [travel, setTravel] = useState(item?.travel_time ?? "");
  const [season, setSeason] = useState<Season | null>(item?.season ?? null);
  const [cost, setCost] = useState<number>(item?.cost ?? 0);
  const [countries, setCountries] = useState<string[]>(item?.country_codes ?? []);
  const [rule, setRule] = useState<BucketAutoRule | null>(item?.auto_rule ?? null);
  const [exerciseId, setExerciseId] = useState<number | null>(item?.auto_exercise_id ?? null);
  const [threshold, setThreshold] = useState(item?.auto_threshold != null ? String(item.auto_threshold) : "");
  const [steps, setSteps] = useState<string[]>([]);
  const [step, setStep] = useState("");
  const valid = title.trim() !== "" && category !== null && (rule !== "exercise" || exerciseId !== null);

  const submit = () => {
    if (!valid) return;
    const body: BucketInput = {
      title: title.trim(),
      category: category!,
      rarity,
      note: note.trim() || null,
      link: link.trim() || null,
      travel_time: travel.trim() || null,
      season,
      cost: cost || null,
      country_codes: countries,
      auto_rule: rule,
      auto_exercise_id: rule === "exercise" ? exerciseId : null,
      auto_threshold: rule === "hike" || rule === "continents" ? parseDecimal(threshold) : null,
      ...(item ? {} : { steps: [...steps, ...(step.trim() ? [step.trim()] : [])] }),
    };
    save.mutate({ id: item?.id, ...body }, { onSuccess: onDone });
  };

  return (
    <form onSubmit={(e) => (e.preventDefault(), submit())} className="space-y-5">
      <label className="block text-sm text-zinc-400">
        Co chceš zažít
        <input autoFocus={!item} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="např. Seskok padákem" className={input} />
      </label>

      <div>
        <p className="mb-1.5 text-sm text-zinc-400">Kategorie</p>
        <Chips label="Kategorie" options={CATEGORIES.map((c) => [c.key, c.label] as const)} value={category} onChange={setCategory} wrap />
      </div>

      <div>
        <p className="mb-1.5 text-sm text-zinc-400">Obtížnost</p>
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Obtížnost">
          {board.rarities.map((r) => {
            const style = RARITY[r.level as 1 | 2 | 3 | 4];
            const selected = rarity === r.level;
            return (
              <button
                key={r.level}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setRarity(r.level)}
                className={`min-h-12 rounded-xl border-2 px-3 py-1.5 text-left ${selected ? `${style.ring} ${style.soft}` : "border-zinc-800"}`}
              >
                <span className={`block text-sm font-semibold ${style.text}`}>{r.name}</span>
                <span className="text-xs text-zinc-400">+{formatNumber(r.xp)} XP</span>
              </button>
            );
          })}
        </div>
      </div>

      <label className="block text-sm text-zinc-400">
        Poznámka
        <textarea value={note} maxLength={2000} rows={2} onChange={(e) => setNote(e.target.value)} className={`${input} py-2`} />
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm text-zinc-400">
          Cesta z domova
          <input value={travel} maxLength={40} onChange={(e) => setTravel(e.target.value)} placeholder="např. 3 h 15 min" className={input} />
        </label>
        <label className="block text-sm text-zinc-400">
          Odkaz
          <input value={link} type="url" inputMode="url" onChange={(e) => setLink(e.target.value)} placeholder="https://…" className={input} />
        </label>
      </div>

      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-zinc-400">Sezóna</span>
        <Chips label="Sezóna" options={SEASONS} value={season} onChange={setSeason} allLabel="Kdykoli" wrap />
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-zinc-400">Cena</span>
        <Segmented options={COSTS} value={cost} onChange={setCost} />
      </div>

      <CountryPicker board={board} value={countries} onChange={setCountries} />

      <div>
        <p className="mb-1.5 text-sm text-zinc-400">Splnit automaticky z dat aplikace</p>
        <div className="ui-card divide-y divide-zinc-800 overflow-hidden" role="radiogroup" aria-label="Automatické splnění">
          {AUTO.map((a) => {
            const selected = rule === a.rule;
            return (
              <button
                key={a.rule ?? "manual"}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setRule(a.rule)}
                className="flex min-h-12 w-full items-center gap-3 px-3 py-2 text-left active:bg-zinc-800/60"
              >
                <span className={`flex size-5 shrink-0 items-center justify-center rounded-full border-2 ${selected ? "border-emerald-500" : "border-zinc-600"}`}>
                  {selected && <span className="size-2.5 rounded-full bg-emerald-500" />}
                </span>
                <span className="flex-1 text-sm">{a.label}</span>
                {"hint" in a && <span className="text-xs text-zinc-500">{a.hint}</span>}
              </button>
            );
          })}
        </div>
        {rule === "exercise" && <ExerciseSelect value={exerciseId} onChange={setExerciseId} />}
        {(rule === "hike" || rule === "continents") && (
          <label className="mt-2 flex items-center gap-2 text-sm text-zinc-400">
            Alespoň
            <DecimalInput ariaLabel="Hranice" value={threshold} onChange={setThreshold} placeholder={rule === "hike" ? "1000" : "7"} className="max-w-32" />
            {rule === "hike" ? "m převýšení" : "kontinentů"}
          </label>
        )}
        <p className="mt-2 text-xs text-zinc-500">Když to data ukážou, položka se splní sama a aplikace ti to oznámí.</p>
      </div>

      {!item && (
        <div>
          <p className="mb-1.5 text-sm text-zinc-400">Kroky (volitelné, každý +{board.step_xp} XP)</p>
          {steps.map((s, i) => (
            <div key={i} className="mb-1.5 flex items-center gap-2 text-sm">
              <span className="flex-1 rounded-lg bg-zinc-800 px-3 py-2">{s}</span>
              <button type="button" aria-label={`Odebrat krok ${s}`} onClick={() => setSteps(steps.filter((_, j) => j !== i))} className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
                <X size={16} />
              </button>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <input
              value={step}
              maxLength={120}
              onChange={(e) => setStep(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && step.trim()) {
                  e.preventDefault();
                  setSteps([...steps, step.trim()]);
                  setStep("");
                }
              }}
              placeholder="např. A1"
              className={`${input} mt-0`}
            />
            <button
              type="button"
              aria-label="Přidat krok"
              disabled={!step.trim()}
              onClick={() => (setSteps([...steps, step.trim()]), setStep(""))}
              className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-zinc-800 text-zinc-200 active:bg-zinc-700 disabled:opacity-40"
            >
              <Plus size={18} />
            </button>
          </div>
        </div>
      )}

      {save.isError && <p className="text-sm text-red-300">{saveError(save.error)}</p>}
      <Button type="submit" disabled={!valid || save.isPending} className="w-full">
        {save.isPending ? "Ukládám…" : item ? "Uložit změny" : "Přidat na bucket list"}
      </Button>
    </form>
  );
}

function ExerciseSelect({ value, onChange }: { value: number | null; onChange: (id: number | null) => void }) {
  const { data: exercises = [] } = useExercises();
  return (
    <label className="mt-2 block text-sm text-zinc-400">
      Cvik
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} className={input}>
        <option value="">Vyber cvik…</option>
        {[...exercises]
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
      </select>
    </label>
  );
}

/** Countries of the item (for the world map): chips of the chosen ones + a search over every known country. */
export function CountryPicker({ board, value, onChange }: { board: BucketBoard; value: string[]; onChange: (codes: string[]) => void }) {
  const [query, setQuery] = useState("");
  const all = useMemo(
    () => Object.keys(board.country_continents).map((code) => ({ code, name: countryName(code) })).sort((a, b) => a.name.localeCompare(b.name, "cs")),
    [board.country_continents],
  );
  const normalize = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const hits = query.trim() ? all.filter((c) => !value.includes(c.code) && normalize(c.name).includes(normalize(query.trim()))).slice(0, 6) : [];
  return (
    <div>
      <p className="mb-1.5 text-sm text-zinc-400">Země (pro mapu světa)</p>
      {value.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {value.map((code) => (
            <button key={code} type="button" onClick={() => onChange(value.filter((c) => c !== code))} className="flex min-h-9 items-center gap-1 rounded-full bg-zinc-800 px-3 text-sm active:bg-zinc-700">
              {countryName(code)} <X size={14} className="text-zinc-400" />
            </button>
          ))}
        </div>
      )}
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Hledat zemi…" aria-label="Hledat zemi" className={`${input} mt-0`} />
      {hits.length > 0 && (
        <div className="ui-card mt-1.5 divide-y divide-zinc-800 overflow-hidden">
          {hits.map((c) => (
            <button
              key={c.code}
              type="button"
              onClick={() => (onChange([...value, c.code]), setQuery(""))}
              className="flex min-h-11 w-full items-center justify-between px-3 text-left text-sm active:bg-zinc-800/60"
            >
              {c.name}
              <span className="text-xs text-zinc-500">{board.continent_names[board.country_continents[c.code]]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
