import { useIsMutating, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BookOpen, CheckCircle2, Dumbbell, RefreshCw, Webhook } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { useKb } from "../api/running";
import { Card, PageHeader } from "../components/Layout";
import { KTImportCard } from "../components/nutrition/KTImportCard";
import { Button } from "../components/ui";
import { formatDay, formatTime } from "../lib/format";
import { errorText } from "./AiCoach";

type IntegrationsStatus = {
  strava: { configured: boolean; connected: boolean; athlete_id: string | null; last_synced_at: string | null };
  webhooks_enabled: boolean;
  webhook_sources: Record<string, { last_received_at: string; last_day: string }>;
};
type ImportSummary = { workouts_created: number; workouts_skipped: number; sets_created: number; exercises_created: string[]; warnings: string[] };

const SOURCE_LABELS: Record<string, string> = { apple_health: "iPhone (Zkratky)", samsung_health: "Hodinky (Health Connect)" };
const when = (iso: string | null) => (iso ? `${formatDay(iso)} ${formatTime(iso)}` : "nikdy");

export function Settings() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["integrations"], queryFn: () => api<IntegrationsStatus>("/api/integrations/status") });
  const kb = useKb();
  const pending = useIsMutating();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (key: string, action: () => Promise<string>) => {
    setBusy(key);
    setMessage(null);
    try {
      setMessage(await action());
      queryClient.invalidateQueries();
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(null);
    }
  };

  const strava = status.data?.strava;
  return (
    <>
      <PageHeader title="Nastavení" />
      <div className="space-y-3">
        {message && <p className="rounded-xl bg-zinc-800 p-3 text-sm">{message}</p>}

        <Card>
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <RefreshCw size={18} /> Strava
          </h2>
          {!strava?.configured ? (
            <p className="text-sm text-zinc-400">Chybí STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET v .env na serveru.</p>
          ) : strava.connected ? (
            <>
              <p className="mb-3 text-sm text-zinc-400">Propojeno · poslední synchronizace {when(strava.last_synced_at)}</p>
              <Button
                className="w-full"
                disabled={busy !== null}
                onClick={() =>
                  run("strava", async () => {
                    const r = await api<{ created: number; updated: number; streams_fetched: number; streams_pending: number }>(
                      "/api/integrations/strava/sync",
                      { method: "POST" },
                    );
                    return `Strava: ${r.created} nových, ${r.updated} aktualizovaných, metriky ${r.streams_fetched} (zbývá ${r.streams_pending})`;
                  })
                }
              >
                {busy === "strava" ? "Synchronizuji…" : "Synchronizovat teď"}
              </Button>
            </>
          ) : (
            <a href="/api/integrations/strava/connect" className="block rounded-xl bg-[#fc4c02] py-3 text-center font-medium text-white">
              Propojit Stravu
            </a>
          )}
        </Card>

        <Card>
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <Webhook size={18} /> Zdroje kroků a spánku
          </h2>
          {!status.data?.webhooks_enabled && <p className="mb-2 text-sm text-amber-300">Webhooky jsou vypnuté (chybí WEBHOOK_TOKEN).</p>}
          <ul className="space-y-1.5 text-sm">
            {Object.entries(SOURCE_LABELS).map(([key, label]) => {
              const source = status.data?.webhook_sources[key];
              return (
                <li key={key} className="flex justify-between gap-2">
                  <span className="text-zinc-400">{label}</span>
                  <span>{source ? when(source.last_received_at) : "zatím nic"}</span>
                </li>
              );
            })}
          </ul>
        </Card>

        <Card>
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <BookOpen size={18} /> Znalostní báze (RunningCoach)
          </h2>
          {kb.data && (
            <div className="mb-3 space-y-1 text-sm text-zinc-400">
              <p>
                {kb.data.repo ?? "nenastaveno"} · {kb.data.documents.length} dokumentů · {kb.data.plan_weeks} týdnů plánu · LTHR {kb.data.lthr ?? "–"}
              </p>
              <p>Synchronizováno {when(kb.data.last_synced_at)}</p>
              {kb.data.last_sync_error && (
                <p className="flex items-center gap-1 text-red-300">
                  <AlertTriangle size={14} /> {kb.data.last_sync_error}
                </p>
              )}
              {kb.data.sync_warnings.map((w) => (
                <p key={w} className="flex items-center gap-1 text-amber-300">
                  <AlertTriangle size={14} /> {w}
                </p>
              ))}
            </div>
          )}
          <Button
            variant="ghost"
            className="w-full"
            disabled={busy !== null}
            onClick={() =>
              run("kb", async () => {
                const r = await api<{ downloaded: string[]; unchanged: number; weeks: number }>("/api/coach/kb/sync", { method: "POST" });
                return `Báze: ${r.downloaded.length} změněných dokumentů, ${r.unchanged} beze změny, ${r.weeks} týdnů plánu`;
              })
            }
          >
            {busy === "kb" ? "Synchronizuji…" : "Synchronizovat z GitHubu"}
          </Button>
        </Card>

        <Card>
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <Dumbbell size={18} /> Import ze Strongu
          </h2>
          <p className="mb-3 text-sm text-zinc-400">CSV export ze Strongu. Opakovaný import nic nezdvojí.</p>
          <label className={`block cursor-pointer rounded-xl bg-zinc-800 py-3 text-center font-medium active:bg-zinc-700 ${busy ? "opacity-50" : ""}`}>
            {busy === "strong" ? "Importuji…" : "Vybrat soubor"}
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              disabled={busy !== null}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                const form = new FormData();
                form.append("file", file);
                void run("strong", async () => {
                  const r = await api<ImportSummary>("/api/workouts/import-strong-csv", { method: "POST", form });
                  return `Strong: ${r.workouts_created} tréninků, ${r.sets_created} sérií (přeskočeno ${r.workouts_skipped}). ${r.warnings.join(" ")}`;
                });
              }}
            />
          </label>
        </Card>

        <KTImportCard />

        <Card>
          <h2 className="mb-1 flex items-center gap-2 font-semibold">
            <CheckCircle2 size={18} /> Aplikace
          </h2>
          <p className="text-sm text-zinc-400">
            {pending ? `${pending} změn čeká na odeslání (odešlou se po připojení).` : "Vše odesláno na server."}
          </p>
        </Card>
      </div>
    </>
  );
}
