import { CalendarClock, Dices } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { BucketBoard, BucketItem, Category } from "../../api/bucket";
import { CATEGORIES, CATEGORY, costLabel, RARITY, SEASON_LABEL } from "../../lib/bucket";
import { formatNumber } from "../../lib/format";
import { Button, Chips, Sheet } from "../ui";

const RARITIES = [
  ["1", "Běžná"],
  ["2", "Vzácná"],
  ["3", "Epická"],
  ["4", "Legendární"],
] as const;
const TAGS = [
  ["now", "Hodí se teď"],
  ["cheap", "Levné"],
  ["near", "Blízko"],
] as const;
type Tag = (typeof TAGS)[number][0];

/** Months that count as summer / winter for "Hodí se teď". */
const seasonNow = (today: string) => {
  const month = Number(today.slice(5, 7));
  return month >= 5 && month <= 9 ? "summer" : month === 12 || month <= 3 ? "winter" : null;
};
// Near = nothing abroad and not a travel item
const isNear = (item: BucketItem) => !item.country_codes.some((c) => c !== "CZ") && item.category !== "travel";

/** Kostka osudu: a random open item, filtered (category, rarity, fits now, cheap, near), for a free weekend. */
export function DiceSheet({ board, onClose, onPick }: { board: BucketBoard; onClose: () => void; onPick: (item: BucketItem, plan: boolean) => void }) {
  const [category, setCategory] = useState<Category | null>(null);
  const [rarity, setRarity] = useState<(typeof RARITIES)[number][0] | null>(null);
  const [tag, setTag] = useState<Tag | null>(null);
  const [shown, setShown] = useState<BucketItem | null>(null);
  const [rolling, setRolling] = useState(false);
  const timer = useRef<number | null>(null);
  useEffect(() => () => void (timer.current && clearInterval(timer.current)), []);

  const season = seasonNow(board.today);
  const pool = board.items.filter(
    (i) =>
      !i.done &&
      (!category || i.category === category) &&
      (!rarity || i.rarity === Number(rarity)) &&
      (!tag || (tag === "now" && (!i.season || i.season === season)) || (tag === "cheap" && (i.cost ?? 1) === 1) || (tag === "near" && isNear(i))),
  );

  const roll = () => {
    if (!pool.length) return;
    setRolling(true);
    let n = 0;
    timer.current = window.setInterval(() => {
      setShown(pool[Math.floor(Math.random() * pool.length)]);
      if (++n >= 12) {
        clearInterval(timer.current!);
        timer.current = null;
        setRolling(false);
      }
    }, 90);
  };

  const style = shown ? RARITY[shown.rarity] : null;
  return (
    <Sheet title="Kostka osudu" onClose={onClose}>
      <div className="space-y-4">
        <div className="space-y-2">
          <Chips label="Kategorie" options={CATEGORIES.map((c) => [c.key, c.label] as const)} value={category} onChange={setCategory} allLabel="Cokoli" />
          <Chips label="Obtížnost" options={RARITIES} value={rarity} onChange={setRarity} allLabel="Jakkoli těžké" />
          <Chips label="Štítky" options={TAGS} value={tag} onChange={setTag} allLabel="Bez omezení" />
        </div>

        <div className={`flex min-h-36 flex-col items-center justify-center gap-1.5 rounded-2xl border-2 p-4 text-center ${style ? style.ring : "border-dashed border-zinc-700"}`}>
          {shown && style ? (
            <>
              <span className={`text-xs font-semibold tracking-widest uppercase ${style.text}`}>
                {style.name} · {CATEGORY[shown.category].label}
              </span>
              <span className={`text-2xl font-bold ${rolling ? "opacity-60" : ""}`}>{shown.title}</span>
              {!rolling && (
                <span className="text-sm text-zinc-400">
                  {[`+${formatNumber(shown.xp)} XP`, shown.travel_time, costLabel(shown.cost), shown.season ? SEASON_LABEL[shown.season] : null].filter(Boolean).join(" · ")}
                </span>
              )}
            </>
          ) : (
            <span className="text-zinc-400">{pool.length ? `V osudí je ${pool.length} položek` : "Tomu filtru nic neodpovídá"}</span>
          )}
        </div>

        <Button className="flex w-full items-center justify-center gap-2" disabled={!pool.length || rolling} onClick={roll}>
          <Dices size={19} /> {shown ? "Hodit znovu" : "Hodit kostkou"}
        </Button>
        {shown && !rolling && (
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" onClick={() => onPick(shown, false)}>
              Otevřít
            </Button>
            <Button variant="ghost" className="flex items-center justify-center gap-2" onClick={() => onPick(shown, true)}>
              <CalendarClock size={17} /> Naplánovat
            </Button>
          </div>
        )}
      </div>
    </Sheet>
  );
}
