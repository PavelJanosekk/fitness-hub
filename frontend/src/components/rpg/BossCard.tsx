import { Skull, Trophy } from "lucide-react";
import { useBoss } from "../../api/rpg";
import { formatDayMonth, formatNumber } from "../../lib/format";
import { Card } from "../Layout";

const duration = (seconds: number) => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};

/** The marathon boss: HP = planned km still to run; runs hit it, skipped planned runs heal it. */
export function BossCard() {
  const { data: boss } = useBoss();
  if (!boss) return null;
  const share = boss.max_hp ? boss.hp / boss.max_hp : 0;
  const [y, m, d] = boss.race_date.split("-").map(Number);

  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-red-500/15 text-red-300">
          {boss.status === "defeated" ? <Trophy size={22} className="text-amber-300" /> : <Skull size={22} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-xs text-zinc-400">Boss</div>
          <h2 className="truncate font-semibold">{boss.name}</h2>
        </div>
        <div className="shrink-0 text-right text-xs text-zinc-400">
          {d}. {m}. {y}
          <div className="text-sm font-semibold text-zinc-100">
            {boss.status === "active" ? `za ${boss.days_left} dní` : boss.status === "defeated" ? "poražen" : "uprchl"}
          </div>
        </div>
      </div>

      {boss.status === "defeated" ? (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          Trofej: {formatNumber(boss.result_km, 2)} km za {boss.result_seconds ? duration(boss.result_seconds) : "–"}
        </p>
      ) : (
        <div className="space-y-1">
          <div className="h-3.5 overflow-hidden rounded-full bg-zinc-800">
            <div className="h-full rounded-full bg-red-500 transition-[width] duration-500" style={{ width: `${share * 100}%` }} />
          </div>
          <div className="flex justify-between text-xs text-zinc-400 tabular-nums">
            <span>
              {formatNumber(boss.hp)} / {formatNumber(boss.max_hp)} HP
            </span>
            <span>
              zásahy {formatNumber(boss.damage_km)} km · léčení {formatNumber(boss.heal_km)} km
            </span>
          </div>
          {boss.status === "missed" && <p className="text-sm text-red-300">Den závodu proběhl bez maratonu: boss uprchl.</p>}
        </div>
      )}

      {boss.events.length > 0 && (
        <div className="space-y-1">
          {boss.events.slice(0, 6).map((e, i) => (
            <div key={i} className="flex items-start gap-2 text-[13px]">
              <span className="w-12 shrink-0 text-zinc-500 tabular-nums">{formatDayMonth(e.date)}</span>
              <span className="min-w-0 flex-1 text-zinc-300">{e.text}</span>
              <span className={`shrink-0 tabular-nums ${e.kind === "hit" ? "text-emerald-300" : "text-red-300"}`}>
                {e.kind === "hit" ? "−" : "+"}
                {formatNumber(e.km, 1)} HP
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-zinc-500">HP = naplánované km do závodu. Každý km ho zraní, vynechaný plánovaný běh ho léčí. Porazíš ho jen maratonem.</p>
    </Card>
  );
}
