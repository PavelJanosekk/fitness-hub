import { ArrowDown, PartyPopper, Trophy } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";
import { useBoss, useCharacter } from "../../api/rpg";
import { useChartColors } from "../charts/palette";
import { Button } from "../ui";

const KEY = "fitness-hub-rpg-seen";
type Seen = { level: number; bossDefeated: boolean };
type Event = { kind: "up" | "down"; level: number; title: string } | { kind: "boss"; name: string };

function readSeen(): Seen | null {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "null");
  } catch {
    return null;
  }
}
function writeSeen(seen: Seen) {
  try {
    localStorage.setItem(KEY, JSON.stringify(seen));
  } catch {
    // private mode: the animation just shows again next time
  }
}

/** Shows a level-up / level-down / boss-defeated moment once per change (per device). Mounted in the layout. */
export function LevelWatcher() {
  const { data: c } = useCharacter();
  const { data: boss } = useBoss();
  const [event, setEvent] = useState<Event | null>(null);

  useEffect(() => {
    if (!c || boss === undefined) return;
    const defeated = boss?.status === "defeated";
    const seen = readSeen();
    writeSeen({ level: c.level, bossDefeated: defeated });
    if (!seen) return; // first visit: remember, don't celebrate the whole history
    if (defeated && !seen.bossDefeated && boss) setEvent({ kind: "boss", name: boss.name });
    else if (c.level !== seen.level) setEvent({ kind: c.level > seen.level ? "up" : "down", level: c.level, title: c.title });
  }, [c, boss]);

  if (!event) return null;
  return <Moment event={event} onClose={() => setEvent(null)} />;
}

function Moment({ event, onClose }: { event: Event; onClose: () => void }) {
  const { series } = useChartColors();
  const happy = event.kind !== "down";
  return createPortal(
    <div className="ui-scrim fixed inset-0 z-50 flex items-center justify-center p-6" onClick={onClose}>
      <style>{`@keyframes rpg-fall { from { transform: translateY(-10vh) rotate(0); opacity: 1 } to { transform: translateY(105vh) rotate(540deg); opacity: .9 } }
@keyframes rpg-pop { from { transform: scale(.6); opacity: 0 } to { transform: scale(1); opacity: 1 } }`}</style>
      {happy &&
        Array.from({ length: 36 }, (_, i) => (
          <span
            key={i}
            className="pointer-events-none absolute top-0 h-3 w-2 rounded-sm"
            style={{
              left: `${(i * 37) % 100}%`,
              background: series[i % series.length],
              animation: `rpg-fall ${2.2 + (i % 5) * 0.35}s ${(i % 7) * 0.12}s ease-in forwards`,
            }}
          />
        ))}
      <div
        role="dialog"
        aria-label={event.kind === "boss" ? "Boss poražen" : event.kind === "up" ? "Nový level" : "Pokles levelu"}
        className="ui-card relative w-full max-w-sm space-y-3 bg-zinc-900 p-6 text-center"
        style={{ animation: "rpg-pop .35s ease-out" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-center">
          {event.kind === "boss" ? (
            <Trophy size={48} className="text-amber-300" />
          ) : event.kind === "up" ? (
            <PartyPopper size={48} className="text-emerald-400" />
          ) : (
            <ArrowDown size={48} className="text-red-400" />
          )}
        </div>
        {event.kind === "boss" ? (
          <>
            <h2 className="text-2xl font-bold">Boss poražen!</h2>
            <p className="text-zinc-300">{event.name} je za tebou. Trofej najdeš u Hrdiny.</p>
          </>
        ) : (
          <>
            <h2 className="text-2xl font-bold">{event.kind === "up" ? `Level ${event.level}!` : `Pokles na level ${event.level}`}</h2>
            <p className="text-zinc-300">{event.kind === "up" ? event.title : "Tresty ti vzaly XP. Důvody najdeš v historii XP."}</p>
          </>
        )}
        <div className="grid grid-cols-2 gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Zavřít
          </Button>
          <Link to="/hero/character" onClick={onClose} className="ui-btn flex min-h-11 items-center justify-center rounded-xl bg-emerald-500 px-4 font-medium text-on-accent">
            Hrdina
          </Link>
        </div>
      </div>
    </div>,
    document.body,
  );
}
