import { Pause, Zap } from "lucide-react";
import { Link } from "react-router";
import type { Character } from "../../api/rpg";
import { useCharacter } from "../../api/rpg";
import { formatNumber } from "../../lib/format";
import { Card } from "../Layout";

export const signed = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatNumber(Math.abs(value))}`;

export function LevelBadge({ level, size = 56 }: { level: number; size?: number }) {
  return (
    <span
      className="flex shrink-0 flex-col items-center justify-center rounded-2xl border-2 border-emerald-500 bg-emerald-950/70"
      style={{ width: size, height: size }}
    >
      <span className="text-[9px] tracking-widest text-emerald-300 uppercase">level</span>
      <span className="text-2xl leading-6 font-extrabold tabular-nums">{level}</span>
    </span>
  );
}

/** XP bar inside the current level; a negative total sits at the start of level 1. */
export function XpBar({ c }: { c: Character }) {
  const span = c.next_level_xp - c.level_start_xp;
  const progress = Math.max(0, Math.min(1, (c.xp_total - c.level_start_xp) / span));
  return (
    <div className="space-y-1">
      <div className="h-2.5 overflow-hidden rounded-full bg-zinc-800">
        <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-500" style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="flex justify-between text-xs text-zinc-400 tabular-nums">
        <span>
          {formatNumber(c.xp_total)} / {formatNumber(c.next_level_xp)} XP
        </span>
        <span className={c.today_xp > 0 ? "text-emerald-300" : c.today_xp < 0 ? "text-red-300" : ""}>{signed(c.today_xp)} XP dnes</span>
      </div>
    </div>
  );
}

/** Přehled: level, title and XP bar; opens the Hrdina page. */
export function CharacterCard() {
  const { data: c } = useCharacter();
  if (!c) return null;
  return (
    <Link to="/hero" className="block">
      <Card className="space-y-3">
        <div className="flex items-center gap-3">
          <LevelBadge level={c.level} size={52} />
          <div className="min-w-0 flex-1">
            <div className="text-[17px] font-bold">{c.title}</div>
            <div className="truncate text-xs text-zinc-400">
              {c.next_title ? `další titul na levelu ${c.next_title.level}: ${c.next_title.title}` : "nejvyšší titul"}
            </div>
          </div>
          {c.tired || c.cursed.length ? (
            <span className="rounded-full bg-red-500/15 px-2 py-1 text-xs font-semibold text-red-300">
              {c.tired ? "unavený" : `prokletí ${c.cursed.length}`}
            </span>
          ) : c.paused ? (
            <span className="flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-1 text-xs text-zinc-300">
              <Pause size={12} /> pauza
            </span>
          ) : (
            c.multiplier > 1 && (
              <span className="flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-1 text-xs font-semibold text-amber-300">
                <Zap size={12} /> ×{formatNumber(c.multiplier, 1)}
              </span>
            )
          )}
        </div>
        <XpBar c={c} />
      </Card>
    </Link>
  );
}
