import { Trophy } from "lucide-react";
import type { PersonalRecord } from "../../api/gym";
import { formatNumber } from "../../lib/format";

/** "Bench Press (Barbell)" -> "Bench Press": the equipment suffix is noise in a badge. */
export const shortName = (name: string) => name.replace(/\s*\(.*\)\s*$/, "");

export function recordText(pr: PersonalRecord): string {
  if (pr.kind === "weight") return `${formatNumber(pr.value, 1)} kg × ${pr.reps}`;
  if (pr.kind === "e1rm") return `odhad 1RM ${formatNumber(pr.value, 1)} kg`;
  return `${pr.value} opakování`;
}

const KIND_LABEL: Record<PersonalRecord["kind"], string> = { weight: "PR", e1rm: "1RM PR", reps: "PR" };

export function PrBadge({ pr, detail = false }: { pr: PersonalRecord; detail?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-1.5 py-0.5 text-xs font-medium text-amber-300">
      <Trophy size={12} />
      {shortName(pr.name)} {KIND_LABEL[pr.kind]}
      {detail && <span className="font-normal text-amber-300/70">· {recordText(pr)}</span>}
    </span>
  );
}

/** Up to `max` badges and a "+N" for the rest. */
export function PrBadges({ prs, max = 2 }: { prs: PersonalRecord[]; max?: number }) {
  if (!prs.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {prs.slice(0, max).map((pr) => (
        <PrBadge key={pr.exercise_id} pr={pr} />
      ))}
      {prs.length > max && <span className="rounded-md bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400">+{prs.length - max}</span>}
    </div>
  );
}
