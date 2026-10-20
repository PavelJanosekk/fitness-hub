import { ChevronRight, Sparkles } from "lucide-react";
import { Link } from "react-router";
import { useAbilities } from "../../api/habits";
import { plural } from "../../lib/habits";
import { Card } from "../Layout";

/** Postava: the hero's Dovednosti (E37), the last few as chips, link to the full list. */
export function AbilitiesCard() {
  const { data } = useAbilities();
  const used = (data ?? []).filter((a) => a.count > 0);
  return (
    <Link to="/hero/character/abilities" className="block">
      <Card className="space-y-2.5 active:bg-zinc-800/60">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Dovednosti</h2>
          <span className="flex items-center gap-1 text-xs text-zinc-400">
            {used.length} {plural(used.length, "dovednost", "dovednosti", "dovedností")}
            <ChevronRight size={14} />
          </span>
        </div>
        {used.length ? (
          <div className="flex flex-wrap gap-1.5">
            {used.slice(0, 5).map((a) => (
              <span key={a.id} className="rounded-full bg-zinc-800 px-2.5 py-1 text-[13px] text-zinc-200">
                {a.icon ? `${a.icon} ` : ""}
                {a.name}
                {a.count > 1 && <span className="ml-1 text-zinc-500">×{a.count}</span>}
              </span>
            ))}
          </div>
        ) : (
          <p className="flex items-center gap-1.5 text-sm text-zinc-400">
            <Sparkles size={14} className="text-emerald-400" />
            Zatím žádné. Přibývají z rutiny, když u návyku s poznámkou zapíšeš dovednost.
          </p>
        )}
      </Card>
    </Link>
  );
}
