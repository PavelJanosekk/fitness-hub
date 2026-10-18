import { Check, CloudOff, Footprints, Moon, Settings } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { newEntryId, useDayIntake, useEnergy, useMetrics, useQuickAddKcal, useSaveWeight, useStepsBreakdown, useWeekly } from "../api/queries";
import { EnergyChart, KcalChart, WeeklyGymChart, WeeklyRunChart, WeightChart } from "../components/charts/DashboardCharts";
import { RoutineCard } from "../components/habits/RoutineCard";
import { CharacterCard } from "../components/rpg/CharacterCard";
import { Card, PageHeader } from "../components/Layout";
import { Button, DecimalInput, parseDecimal, Segmented, Sheet } from "../components/ui";
import { addDays, formatNumber, isoDate } from "../lib/format";

const RANGES = [
  [30, "30 dní"],
  [90, "90 dní"],
] as const;

const SOURCE_LABELS: Record<string, string> = {
  apple_health: "iPhone",
  samsung_health: "Hodinky",
  manual: "Ručně",
};
const METHOD_LABELS: Record<string, string> = {
  buckets: "po 15 min vyšší z obou zdrojů, sečteno",
  max_daily: "vyšší z denních součtů",
  single_source: "jediný zdroj",
  manual: "zadáno ručně",
};

export function Dashboard() {
  const [range, setRange] = useState<30 | 90>(30);
  const [showSteps, setShowSteps] = useState(false);
  const metrics = useMetrics(range);
  const weekly = useWeekly(12);
  const energy = useEnergy(addDays(isoDate(), -(range - 1)), isoDate());
  const days = metrics.data ?? [];
  const todayMetric = days.at(-1);
  const lastWeight = [...days].reverse().find((d) => d.weight_7d_avg !== null);

  return (
    <>
      <PageHeader
        title="Přehled"
        action={
          <Link to="/settings" aria-label="Nastavení" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800 md:hidden">
            <Settings size={22} />
          </Link>
        }
      />

      <div className="space-y-3">
        <CharacterCard />
        <RoutineCard />
        <TodayCard weight7d={lastWeight?.weight_7d_avg ?? null} />

        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => setShowSteps(true)} className="text-left">
            <StatTile icon={<Footprints size={16} />} label="Kroky dnes" value={formatNumber(todayMetric?.steps)} hint="detail ›" />
          </button>
          <StatTile icon={<Moon size={16} />} label="Spánek" value={todayMetric?.sleep_hours ? `${formatNumber(todayMetric.sleep_hours, 1)} h` : "–"} />
        </div>

        <Card>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="font-semibold">Váha</h2>
            <Segmented options={RANGES} value={range} onChange={setRange} />
          </div>
          {days.some((d) => d.weight_kg !== null) ? <WeightChart data={days} /> : <Empty text="Zatím žádná váha. Zapiš ji nahoře." />}
        </Card>

        <Card>
          <h2 className="mb-3 font-semibold">Příjem energie</h2>
          {days.some((d) => d.calories_in !== null) ? <KcalChart data={days} /> : <Empty text="Zatím žádný zapsaný příjem." />}
        </Card>

        <Card>
          <h2 className="mb-3 font-semibold">Aktivně spálené kalorie (odhad)</h2>
          {energy.data?.some((d) => d.active_kcal !== null) ? (
            <EnergyChart data={energy.data} />
          ) : (
            <Empty text={energy.data ? "Pro odhad zapiš váhu nahoře." : "Načítám…"} />
          )}
        </Card>

        <Card>
          <h2 className="mb-3 font-semibold">Gym: pracovní série za týden</h2>
          {weekly.data?.some((w) => w.gym_workouts) ? <WeeklyGymChart weeks={weekly.data} /> : <Empty text="Za posledních 12 týdnů žádný trénink." />}
        </Card>

        <Card>
          <h2 className="mb-3 font-semibold">Běh: km za týden</h2>
          {weekly.data?.some((w) => w.runs) ? <WeeklyRunChart weeks={weekly.data} /> : <Empty text="Běhy se objeví po propojení Stravy." />}
        </Card>
      </div>

      {showSteps && <StepsSheet onClose={() => setShowSteps(false)} />}
    </>
  );
}

function TodayCard({ weight7d }: { weight7d: number | null }) {
  const [weight, setWeight] = useState("");
  const [kcal, setKcal] = useState("");
  const [protein, setProtein] = useState("");
  const saveWeight = useSaveWeight();
  const quickAdd = useQuickAddKcal();
  const intake = useDayIntake(isoDate());
  const totals = intake.data?.totals;

  const submitWeight = () => {
    const value = parseDecimal(weight);
    if (value) saveWeight.mutate(value, { onSuccess: () => setWeight("") });
  };
  const submitKcal = () => {
    const value = parseDecimal(kcal);
    if (!value) return;
    quickAdd.mutate(
      { id: newEntryId(), kcal: value, protein_g: parseDecimal(protein) ?? undefined },
      { onSuccess: () => (setKcal(""), setProtein("")) },
    );
  };

  return (
    <Card>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-sm text-zinc-400">
            Dnešní váha (kg){weight7d !== null && <span className="text-zinc-500"> · průměr {formatNumber(weight7d, 1)}</span>}
          </label>
          <div className="flex gap-2">
            <DecimalInput ariaLabel="Váha v kg" placeholder="84,6" value={weight} onChange={setWeight} />
            <Button onClick={submitWeight} disabled={!parseDecimal(weight)}>
              Uložit
            </Button>
          </div>
          <Status mutation={saveWeight} />
        </div>
        <div>
          <label className="mb-1.5 block text-sm text-zinc-400">
            Rychlý zápis jídla
            {totals && <span className="text-zinc-500"> · dnes {formatNumber(totals.kcal)} kcal{totals.protein_g !== null && `, ${formatNumber(totals.protein_g)} g B`}</span>}
          </label>
          <div className="flex gap-2">
            <DecimalInput ariaLabel="Kalorie" placeholder="kcal" value={kcal} onChange={setKcal} />
            <DecimalInput ariaLabel="Bílkoviny v gramech" placeholder="B g" value={protein} onChange={setProtein} className="max-w-20" />
            <Button onClick={submitKcal} disabled={!parseDecimal(kcal)}>
              Přidat
            </Button>
          </div>
          <Status mutation={quickAdd} />
        </div>
      </div>
    </Card>
  );
}

function Status({ mutation }: { mutation: { isPaused: boolean; isSuccess: boolean; isError: boolean } }) {
  if (mutation.isPaused)
    return (
      <p className="mt-1.5 flex items-center gap-1 text-xs text-amber-300">
        <CloudOff size={14} /> Offline, uloží se po připojení
      </p>
    );
  if (mutation.isError) return <p className="mt-1.5 text-xs text-red-300">Nepovedlo se uložit</p>;
  if (mutation.isSuccess)
    return (
      <p className="mt-1.5 flex items-center gap-1 text-xs text-emerald-400">
        <Check size={14} /> Uloženo
      </p>
    );
  return null;
}

function StatTile({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: string; hint?: string }) {
  return (
    <Card className="h-full">
      <div className="flex items-center gap-1.5 text-sm text-zinc-400">
        {icon} {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-zinc-500">{hint}</div>}
    </Card>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-zinc-500">{text}</p>;
}

function StepsSheet({ onClose }: { onClose: () => void }) {
  const breakdown = useStepsBreakdown(isoDate(), true);
  const data = breakdown.data;
  return (
    <Sheet title="Kroky dnes" onClose={onClose}>
      {!data || data.steps === null ? (
        <p className="text-zinc-400">Zatím žádná data z iPhonu ani z hodinek.</p>
      ) : (
        <div className="space-y-3">
          <div className="text-4xl font-semibold tabular-nums">{formatNumber(data.steps)}</div>
          <p className="text-sm text-zinc-400">Výpočet: {METHOD_LABELS[data.steps_method ?? ""] ?? "–"}</p>
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(data.source_totals).map(([source, total]) => (
                <tr key={source} className="border-t border-zinc-800">
                  <td className="py-2 text-zinc-400">{SOURCE_LABELS[source] ?? source}</td>
                  <td className="py-2 text-right tabular-nums">{formatNumber(total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Sheet>
  );
}
