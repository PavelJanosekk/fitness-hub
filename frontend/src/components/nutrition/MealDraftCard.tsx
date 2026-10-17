import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import { type Candidate, type MealDraft, SOURCE_LABELS, kcalFor, mealTypeLabel, useConfirmDraft } from "../../api/nutrition";
import { formatNumber } from "../../lib/format";
import { uuid } from "../../lib/uuid";
import { Button, DecimalInput, parseDecimal } from "../ui";

export function SourceBadge({ source, grounded }: { source: string; grounded?: boolean }) {
  const label = source === "web_estimate" && grounded ? "Web" : (SOURCE_LABELS[source] ?? source);
  const tone = source === "web_estimate" ? "bg-amber-500/15 text-amber-300" : "bg-zinc-800 text-zinc-400";
  return <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${tone}`}>{label}</span>;
}

type Row = { candidate: Candidate | null; grams: string; open: boolean };

/** A dictated meal the assistant didn't save on its own: check the foods, fix grams, confirm with one tap (E4).
 * Confirming also teaches the app these phrases, so next time the same foods save directly. */
export function MealDraftCard({ draft }: { draft: MealDraft }) {
  const confirm = useConfirmDraft();
  // One id per card: a retried confirm can't log the meal twice
  const [mealId] = useState(uuid);
  const [rows, setRows] = useState<Row[]>(() =>
    draft.items.map((item) => ({ candidate: item.chosen, grams: String(item.amount_g).replace(".", ","), open: !item.chosen })),
  );
  const update = (index: number, patch: Partial<Row>) => setRows((all) => all.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const ready = rows.every((r) => r.candidate && (parseDecimal(r.grams) ?? 0) > 0);
  const total = rows.reduce((sum, r) => sum + (r.candidate ? (kcalFor(r.candidate.per_100g, parseDecimal(r.grams) ?? 0) ?? 0) : 0), 0);

  const save = () =>
    confirm.mutate({
      id: mealId,
      date: draft.date,
      meal_type: draft.meal_type,
      raw_input: draft.raw_input,
      items: draft.items.map((item, i) => ({
        input: item.input,
        candidate: rows[i].candidate as Candidate,
        amount_g: parseDecimal(rows[i].grams) as number,
      })),
    });

  return (
    <div className="mt-2 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
      <p className="mb-2 text-amber-200">
        {mealTypeLabel(draft.meal_type)} · zkontroluj potraviny a potvrď
      </p>
      <ul className="space-y-2">
        {draft.items.map((item, i) => {
          const row = rows[i];
          const grams = parseDecimal(row.grams) ?? 0;
          const kcal = row.candidate ? kcalFor(row.candidate.per_100g, grams) : null;
          return (
            <li key={i} className="rounded-lg bg-zinc-900/70 p-2">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-zinc-500">„{item.input.user_phrase}“</p>
                  {row.candidate ? (
                    <p className="flex items-center gap-1.5">
                      <span className="truncate">{row.candidate.name}</span>
                      <SourceBadge source={row.candidate.source} grounded={row.candidate.grounded} />
                    </p>
                  ) : (
                    <p className="text-amber-300">Potravinu jsem nenašel, vyber z nabídky</p>
                  )}
                  {item.confidence !== null && item.confidence < 0.6 && row.candidate && (
                    <p className="text-xs text-amber-400">nejistá shoda</p>
                  )}
                </div>
                <DecimalInput
                  ariaLabel="Gramy"
                  value={row.grams}
                  onChange={(grams) => update(i, { grams })}
                  className="!min-h-9 w-20 text-right !text-base"
                />
                <span className="mt-2 w-4 text-zinc-500">g</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-xs text-zinc-500">
                <span>{kcal !== null ? `${formatNumber(kcal)} kcal` : "–"}</span>
                {item.candidates.length > 1 && (
                  <button onClick={() => update(i, { open: !row.open })} className="flex items-center gap-0.5 text-zinc-400">
                    Změnit <ChevronDown size={14} className={row.open ? "rotate-180" : ""} />
                  </button>
                )}
              </div>
              {row.open && (
                <div className="mt-2 space-y-1">
                  {item.candidates.map((c) => (
                    <button
                      key={c.ref}
                      onClick={() => update(i, { candidate: c, open: false })}
                      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left ${row.candidate?.ref === c.ref ? "bg-emerald-500/15 text-emerald-200" : "bg-zinc-800/70 text-zinc-200"}`}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {c.name}
                        {c.brand && <span className="text-zinc-500"> · {c.brand}</span>}
                      </span>
                      <span className="shrink-0 text-xs text-zinc-500">{formatNumber(c.per_100g.kcal)} kcal/100 g</span>
                      <SourceBadge source={c.source} grounded={c.grounded} />
                    </button>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {confirm.isSuccess ? (
        <p className="mt-2 flex items-center gap-1 text-emerald-400">
          <Check size={16} /> Uloženo · {formatNumber(total)} kcal
        </p>
      ) : (
        <Button onClick={save} disabled={!ready || confirm.isPending} className="mt-2 w-full">
          {confirm.isError ? "Zkusit znovu" : `Potvrdit a uložit · ${formatNumber(total)} kcal`}
        </Button>
      )}
    </div>
  );
}
