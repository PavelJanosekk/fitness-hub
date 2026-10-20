import { Sparkles, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";
import { type BucketItem, useBucketBoard } from "../../api/bucket";
import { CATEGORY, fullDate, RARITY } from "../../lib/bucket";
import { formatNumber } from "../../lib/format";
import { useChartColors } from "../charts/palette";
import { Button } from "../ui";

const KEY = "fitness-hub-bucket-seen";

function readSeen(): number[] | null {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "null");
  } catch {
    return null;
  }
}
function writeSeen(ids: number[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    // private mode: the moment just shows again next time
  }
}

/**
 * Announces every newly completed bucket-list item once per device: by hand, by the coach or by an auto rule
 * (a marathon, a gym skill, a hike, the 7th continent), so nothing completes silently (E36). Mounted in the layout.
 */
export function BucketWatcher() {
  const { data } = useBucketBoard();
  const [queue, setQueue] = useState<BucketItem[]>([]);

  useEffect(() => {
    if (!data) return;
    const done = data.items.filter((i) => i.done);
    const seen = readSeen();
    writeSeen(done.map((i) => i.id));
    if (!seen) return; // first visit: remember, don't celebrate the whole list
    const fresh = done.filter((i) => !seen.includes(i.id) && i.source !== "before").sort((a, b) => b.rarity - a.rarity);
    if (fresh.length) setQueue((q) => [...q, ...fresh.filter((i) => !q.some((x) => x.id === i.id))]);
  }, [data]);

  if (!queue.length) return null;
  return <Moment item={queue[0]} onClose={() => setQueue((q) => q.slice(1))} />;
}

function Moment({ item, onClose }: { item: BucketItem; onClose: () => void }) {
  const { series } = useChartColors();
  const style = RARITY[item.rarity];
  const category = CATEGORY[item.category];
  const Icon = category.icon;
  const pieces = 12 + item.rarity * 12;
  return createPortal(
    <div className="ui-scrim fixed inset-0 z-50 flex items-center justify-center p-6" onClick={onClose}>
      <style>{`@keyframes bucket-fall { from { transform: translateY(-10vh) rotate(0); opacity: 1 } to { transform: translateY(105vh) rotate(540deg); opacity: .9 } }
@keyframes bucket-pop { from { transform: scale(.6); opacity: 0 } to { transform: scale(1); opacity: 1 } }`}</style>
      {Array.from({ length: pieces }, (_, i) => (
        <span
          key={i}
          className="pointer-events-none absolute top-0 h-3 w-2 rounded-sm"
          style={{
            left: `${(i * 37) % 100}%`,
            background: series[i % series.length],
            animation: `bucket-fall ${2.2 + (i % 5) * 0.35}s ${(i % 7) * 0.12}s ease-in forwards`,
          }}
        />
      ))}
      <div
        role="dialog"
        aria-label={`Splněno: ${item.title}`}
        className={`ui-card relative w-full max-w-sm space-y-3 border-2! bg-zinc-900 p-6 text-center ${style.ring}`}
        style={{ animation: "bucket-pop .35s ease-out" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-center">
          <span className={`flex size-16 items-center justify-center rounded-full ${style.soft}`}>
            <Icon size={32} className={style.text} />
          </span>
        </div>
        <p className={`text-xs font-semibold tracking-widest uppercase ${style.text}`}>
          {style.name} · {category.label}
        </p>
        <h2 className="text-2xl font-bold">{item.title}</h2>
        <p className="text-zinc-300">Splněno z bucket listu!</p>
        {item.xp > 0 && (
          <p className="text-3xl font-bold text-emerald-300 tabular-nums">+{formatNumber(item.xp + item.goal_xp)} XP</p>
        )}
        {item.goal_xp > 0 && (
          <p className="flex items-center justify-center gap-1.5 text-sm text-amber-300">
            <Star size={15} fill="currentColor" /> Letošní cíl: +{formatNumber(item.goal_xp)} XP navíc
          </p>
        )}
        {item.source === "auto" && (
          <p className="text-sm text-zinc-400">
            <Sparkles size={15} className="mr-1 inline align-[-2px]" />
            Splněno samo z dat: {item.auto_label}
            {item.completed_on && ` · ${fullDate(item.completed_on)}`}
          </p>
        )}
        <div className="grid grid-cols-2 gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Super
          </Button>
          <Link
            to={`/hero/bucket?i=${item.id}`}
            onClick={onClose}
            className="ui-btn flex min-h-11 items-center justify-center rounded-xl bg-emerald-500 px-4 font-medium text-on-accent"
          >
            {item.memory ? "Otevřít" : "Vzpomínka"}
          </Link>
        </div>
      </div>
    </div>,
    document.body,
  );
}
