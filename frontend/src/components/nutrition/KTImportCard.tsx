import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Utensils } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { addDays, formatDay, isoDate } from "../../lib/format";
import { errorText } from "../../pages/AiCoach";
import { Card } from "../Layout";
import { Button } from "../ui";

type KTImport = {
  configured: boolean;
  running: boolean;
  status: "idle" | "running" | "done" | "error";
  range_from: string | null;
  range_to: string | null;
  next_day: string | null;
  days_done: number;
  days_skipped: number;
  items_imported: number;
  foods_created: number;
  weights_filled: number;
  warnings: string[];
  last_error: string | null;
};

const URL = "/api/nutrition/import/kaloricke-tabulky";
const dayCount = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000) + 1;

/** One-time import of the KalorickéTabulky diary (throttled background job; the same range resumes). */
export function KTImportCard() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["kt-import"],
    queryFn: () => api<KTImport>(URL),
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });
  const [from, setFrom] = useState(() => addDays(isoDate(), -1));
  const start = useMutation({
    mutationFn: (date_from: string) => api<KTImport>(URL, { method: "POST", body: { date_from } }),
    onSuccess: (data) => queryClient.setQueryData(["kt-import"], data),
  });
  const s = status.data;
  // New meals and foods appear in the Jídlo tab as the import progresses and when it ends
  const progress = `${s?.status}:${s?.days_done}`;
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ["nutrition"] });
    queryClient.invalidateQueries({ queryKey: ["metrics"] });
  }, [progress, queryClient]);

  return (
    <Card>
      <h2 className="mb-2 flex items-center gap-2 font-semibold">
        <Utensils size={18} /> Import z KalorickýchTabulek
      </h2>
      {!s ? (
        <p className="text-sm text-zinc-500">Načítám…</p>
      ) : !s.configured ? (
        <p className="text-sm text-zinc-400">Chybí KALORICKETABULKY_EMAIL / _PASSWORD v .env na serveru.</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-zinc-400">
            Stáhne deník a váhu po dnech (1 požadavek za 2 s). Jídla zapsaná v aplikaci nechá a KT jídla přidá k nim (co máš v obou, bude dvakrát). Opakovaný import
            stejného období pokračuje tam, kde skončil.
          </p>
          {s.range_from && s.range_to && s.status !== "idle" && (
            <div className="mb-3 rounded-xl bg-zinc-950 p-3 text-sm">
              <p>
                {formatDay(s.range_from)} – {formatDay(s.range_to)}: {s.days_done} / {dayCount(s.range_from, s.range_to)} dní
                {s.running && " · běží…"}
                {s.status === "done" && " · hotovo"}
              </p>
              <p className="text-zinc-400">
                {s.items_imported} položek, {s.foods_created} nových potravin, {s.weights_filled} vážení
                {s.days_skipped > 0 && `, ${s.days_skipped} dní přeskočeno`}
              </p>
              {s.status === "error" && <p className="text-red-300">Chyba: {s.last_error}</p>}
              {s.warnings.length > 0 && (
                <details className="mt-1 text-xs text-zinc-500">
                  <summary>{s.warnings.length} upozornění</summary>
                  <ul className="mt-1 space-y-0.5">
                    {s.warnings.slice(-30).map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
          <div className="flex items-end gap-2">
            <label className="flex-1 text-sm text-zinc-400">
              Od
              <input
                type="date"
                value={s.status === "error" && s.range_from ? s.range_from : from}
                max={addDays(isoDate(), -1)}
                onChange={(e) => setFrom(e.target.value)}
                className="mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-zinc-100"
              />
            </label>
            <Button onClick={() => start.mutate(s.status === "error" && s.range_from ? s.range_from : from)} disabled={s.running || start.isPending}>
              {s.status === "error" ? "Pokračovat" : "Importovat"}
            </Button>
          </div>
          {start.isError && <p className="mt-2 text-sm text-red-300">{errorText(start.error)}</p>}
        </>
      )}
    </Card>
  );
}
