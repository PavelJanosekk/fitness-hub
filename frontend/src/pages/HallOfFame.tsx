import { ChevronLeft, Repeat, Sparkles } from "lucide-react";
import { Link } from "react-router";
import { type BucketItem, useBucketBoard } from "../api/bucket";
import { useHabitBoard } from "../api/habits";
import type { HabitEntry } from "../lib/habits";
import { Stars } from "../components/bucket/ItemSheet";
import { Card } from "../components/Layout";
import { CATEGORY, fullDate, RARITY } from "../lib/bucket";
import { formatNumber } from "../lib/format";

type Moment = { habitId: number; habit: string; date: string } & HabitEntry;

/**
 * Síň slávy (E36): completed bucket-list items as a timeline by year with their memories; older ones at the end.
 * Routine entries rated 4–5 stars (E37) join the timeline.
 */
export function HallOfFame() {
  const { data, isPending } = useBucketBoard();
  const habits = useHabitBoard();
  if (!data) return <p className="text-zinc-500">{isPending ? "Načítám…" : "Síň slávy se nepodařilo načíst."}</p>;
  const dated = data.items.filter((i) => i.done && i.completed_on).sort((a, b) => b.completed_on!.localeCompare(a.completed_on!));
  const before = data.items.filter((i) => i.source === "before").sort((a, b) => b.rarity - a.rarity || a.title.localeCompare(b.title, "cs"));
  const moments: Moment[] = (habits.data?.habits ?? []).flatMap((h) =>
    Object.entries(h.entries ?? {})
      .filter(([, e]) => (e.rating ?? 0) >= 4)
      .map(([date, e]) => ({ ...e, habitId: h.id, habit: h.title, date })),
  );
  const years = [...new Set([...dated.map((i) => i.completed_on!.slice(0, 4)), ...moments.map((m) => m.date.slice(0, 4))])].sort().reverse();

  return (
    <div className="space-y-3">
      <Link to="/hero/bucket" className="flex items-center gap-1 py-2 pr-2 text-sm text-zinc-400">
        <ChevronLeft size={18} /> Bucket list
      </Link>
      {!dated.length && !moments.length && (
        <Card>
          <p className="text-zinc-400">Až něco z bucket listu splníš, objeví se to tady i se vzpomínkou.</p>
        </Card>
      )}
      {years.map((year) => {
        const items = dated.filter((i) => i.completed_on!.startsWith(year));
        const xp = items.reduce((sum, i) => sum + i.xp + i.goal_xp, 0);
        const yearMoments = moments.filter((m) => m.date.startsWith(year));
        // Bucket items and ★ 4–5 routine entries (E37) in one timeline, newest first
        const timeline = [
          ...items.map((i) => ({ date: i.completed_on!, node: <Entry key={`b${i.id}`} item={i} /> })),
          ...yearMoments.map((m) => ({ date: m.date, node: <MomentEntry key={`h${m.habitId}:${m.date}`} moment={m} /> })),
        ].sort((a, b) => b.date.localeCompare(a.date));
        return (
          <section key={year} className="space-y-2">
            <h2 className="flex items-baseline justify-between px-0.5 pt-1">
              <span className="text-xl font-bold">{year}</span>
              <span className="text-[13px] text-zinc-400">
                {items.length + yearMoments.length}
                {xp > 0 && ` · +${formatNumber(xp)} XP`}
              </span>
            </h2>
            <ol className="relative space-y-2 border-l-2 border-zinc-800 pl-4">{timeline.map((t) => t.node)}</ol>
          </section>
        );
      })}
      {before.length > 0 && (
        <section className="space-y-2">
          <h2 className="px-0.5 pt-2 font-semibold">Splněno ještě před aplikací</h2>
          <div className="flex flex-wrap gap-1.5">
            {before.map((i) => (
              <Link key={i.id} to={`/hero/bucket?i=${i.id}`} className={`rounded-full px-2.5 py-1 text-xs ${RARITY[i.rarity].soft} ${RARITY[i.rarity].text}`}>
                {i.title}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function MomentEntry({ moment }: { moment: Moment }) {
  return (
    <li className="relative">
      <span className="absolute top-4 -left-[23px] size-3 rounded-full bg-amber-300 ring-4 ring-zinc-950" aria-hidden />
      <Link to="/hero" className="ui-card block space-y-1.5 border-l-4! border-amber-300/60 p-3">
        <div className="flex items-center justify-between gap-2 text-xs text-zinc-400">
          <span className="flex items-center gap-1">
            <Repeat size={13} /> {fullDate(moment.date)}
          </span>
          <span className="text-amber-300">Z rutiny</span>
        </div>
        <div className="font-semibold">{moment.ability ?? moment.habit}</div>
        {moment.rating ? <Stars value={moment.rating} /> : null}
        {moment.note && <p className="text-sm whitespace-pre-line text-zinc-300">{moment.note}</p>}
        {moment.ability && <p className="text-xs text-zinc-500">{moment.habit}</p>}
      </Link>
    </li>
  );
}

function Entry({ item }: { item: BucketItem }) {
  const style = RARITY[item.rarity];
  const Icon = CATEGORY[item.category].icon;
  return (
    <li className="relative">
      <span className={`absolute top-4 -left-[23px] size-3 rounded-full ring-4 ring-zinc-950 ${style.bar}`} aria-hidden />
      <Link to={`/hero/bucket?i=${item.id}`} className={`ui-card block space-y-1.5 border-l-4! p-3 ${style.ring}`}>
        <div className="flex items-center justify-between gap-2 text-xs text-zinc-400">
          <span className="flex items-center gap-1">
            <Icon size={13} /> {fullDate(item.completed_on!)}
          </span>
          <span className={style.text}>
            {style.name}
            {item.xp > 0 && ` · +${formatNumber(item.xp + item.goal_xp)} XP`}
          </span>
        </div>
        <div className="font-semibold">{item.title}</div>
        {item.rating ? <Stars value={item.rating} /> : null}
        {item.memory && <p className="text-sm whitespace-pre-line text-zinc-300">{item.memory}</p>}
        {item.source === "auto" && (
          <p className="text-xs text-zinc-500">
            <Sparkles size={12} className="mr-1 inline align-[-1px]" />
            {item.auto_label}
          </p>
        )}
      </Link>
    </li>
  );
}
