import { Target } from "lucide-react";
import { type DayTarget, type TargetMode, useDecideProposal, useTargets } from "../../api/nutrition";
import { formatNumber, isoDate } from "../../lib/format";
import { Button } from "../ui";

const MODE_LABELS: Record<TargetMode, string> = { cut: "hubnutí", maintenance: "udržování", off: "bez cíle" };

/** The day's kcal target with its parts (E41); on today also tomorrow, which is higher before a long run. */
export function DayTargetCard({ date }: { date: string }) {
  const targets = useTargets(date);
  const decide = useDecideProposal();
  const data = targets.data;
  if (!data) return null;
  const proposal = date === isoDate() ? data.proposal : null;

  return (
    <div className="mb-4 border-b border-zinc-800 pb-3">
      <p className="mb-1.5 flex items-center gap-1.5 text-sm text-zinc-400">
        <Target size={16} /> Cíl · {MODE_LABELS[data.today.mode]}
      </p>
      <TargetLine target={data.today} label={date === isoDate() ? "Dnes" : null} />
      {date === isoDate() && <TargetLine target={data.tomorrow} label="Zítra" muted />}
      {proposal && (
        <div className="mt-3 rounded-xl bg-amber-500/10 p-3 text-sm">
          <p className="font-medium text-amber-200">
            Návrh: základ {formatNumber(proposal.current_base)} → {formatNumber(proposal.new_base)} kcal
          </p>
          <p className="mt-0.5 text-zinc-300">{proposal.reason}</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button variant="ghost" disabled={decide.isPending} onClick={() => decide.mutate(false)}>
              Nechat
            </Button>
            <Button disabled={decide.isPending} onClick={() => decide.mutate(true)}>
              Potvrdit
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function TargetLine({ target, label, muted = false }: { target: DayTarget; label: string | null; muted?: boolean }) {
  if (target.kcal === null) {
    return (
      <p className={`text-sm ${muted ? "text-zinc-500" : "text-zinc-300"}`}>
        {label && `${label}: `}
        {target.mode === "off" ? "bez cíle, jen zápis" : "chybí základ v Cílech"}
      </p>
    );
  }
  const parts = [`${formatNumber(target.base_kcal ?? 0)} základ`, ...target.parts.map((p) => `${formatNumber(p.kcal)} ${p.label}`)];
  return (
    <p className={`text-sm tabular-nums ${muted ? "text-zinc-500" : "text-zinc-300"}`}>
      {label && <span className="text-zinc-500">{label}: </span>}
      {parts.join(" + ")} = <span className={muted ? "" : "font-semibold text-zinc-100"}>{formatNumber(target.kcal)} kcal</span>
      {target.carbs_g !== null && ` · sacharidy ${formatNumber(target.carbs_g)} g`}
      {target.parts.length > 0 && target.weight_used_kg === null && " · chybí váha"}
    </p>
  );
}
