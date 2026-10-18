import { Check, Lock, Medal } from "lucide-react";
import { useBadges, useQuests } from "../../api/rpg";
import { formatDayMonth, formatNumber } from "../../lib/format";
import { Card } from "../Layout";

/** This week's quests: progress, reward, done day. */
export function QuestsCard() {
  const { data } = useQuests();
  if (!data || data.quests.length === 0) return null;
  const done = data.quests.filter((q) => q.done_on).length;
  return (
    <Card className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Výpravy tohoto týdne</h2>
        <span className="text-[13px] text-zinc-400 tabular-nums">
          {done} / {data.quests.length} · obnoví se v pondělí
        </span>
      </div>
      {data.quests.map((q) => {
        const share = Math.min(1, q.progress / q.target);
        return (
          <div key={q.key} className="space-y-1">
            <div className="flex items-center gap-2 text-sm">
              <span
                className={`flex size-5 shrink-0 items-center justify-center rounded-full border-2 ${q.done_on ? "border-emerald-500 bg-emerald-500 text-on-accent" : "border-zinc-600"}`}
              >
                {q.done_on && <Check size={12} strokeWidth={3.4} />}
              </span>
              <span className={`min-w-0 flex-1 ${q.done_on ? "text-zinc-400" : ""}`}>{q.title}</span>
              <span className="shrink-0 text-xs font-semibold text-emerald-300 tabular-nums">+{q.xp} XP</span>
            </div>
            <div className="flex items-center gap-2 pl-7">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800">
                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${share * 100}%` }} />
              </div>
              <span className="w-24 shrink-0 text-right text-xs text-zinc-400 tabular-nums">
                {q.done_on ? `hotovo ${formatDayMonth(q.done_on)}` : `${formatNumber(q.progress, q.unit === "km" ? 1 : 0)} / ${formatNumber(q.target, q.unit === "km" ? 1 : 0)} ${q.unit}`}
              </span>
            </div>
          </div>
        );
      })}
      <p className={`text-xs ${data.all_done ? "text-emerald-300" : "text-zinc-500"}`}>
        {data.all_done ? `Všechny výpravy splněny: +${data.all_bonus_xp} XP` : `Splň všechny a dostaneš bonus +${data.all_bonus_xp} XP. Nesplněné zůstanou v historii.`}
      </p>
    </Card>
  );
}

/** Badges: unlocked ones with their day, locked ones greyed with progress. */
export function BadgesCard() {
  const { data } = useBadges();
  if (!data) return null;
  const unlocked = data.filter((b) => b.unlocked_on).length;
  return (
    <Card className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Odznaky</h2>
        <span className="text-[13px] text-zinc-400 tabular-nums">
          {unlocked} / {data.length}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {data.map((b) => (
          <div
            key={b.key}
            title={b.description}
            className={`flex flex-col items-center gap-1.5 rounded-2xl border p-2 text-center ${b.unlocked_on ? "border-amber-500/40 bg-amber-500/5" : "border-zinc-800 opacity-60"}`}
          >
            <span
              className={`flex size-11 items-center justify-center rounded-full border-2 ${b.unlocked_on ? "border-amber-400 text-amber-300" : "border-zinc-700 text-zinc-500"}`}
            >
              {b.unlocked_on ? <Medal size={20} /> : <Lock size={18} />}
            </span>
            <span className="text-xs leading-tight font-medium">{b.title}</span>
            <span className="text-[10px] leading-tight text-zinc-500">{b.unlocked_on ? formatDayMonth(b.unlocked_on) : (b.progress ?? b.description)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
