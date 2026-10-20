import { ChevronLeft, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/client";
import { useAbilities, useAbility, useEditAbility } from "../api/habits";
import { Stars } from "../components/bucket/ItemSheet";
import { Card } from "../components/Layout";
import { Button, Sheet } from "../components/ui";
import type { Ability } from "../lib/abilities";
import { formatDay } from "../lib/format";
import { plural } from "../lib/habits";

const input = "mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";

/** Dovednosti (E37): every dovednost the hero picked up through the routine, the most recently used first. */
export function Abilities() {
  const { data, isPending } = useAbilities();
  const [open, setOpen] = useState<number | null>(null);
  const abilities = data ?? [];

  return (
    <div className="space-y-3">
      <Link to="/hero/character" className="flex items-center gap-1 py-2 pr-2 text-sm text-zinc-400">
        <ChevronLeft size={18} /> Postava
      </Link>
      {!abilities.length && (
        <Card>
          <p className="text-zinc-400">
            {isPending ? "Načítám…" : "Dovednosti přibývají z rutiny: u návyku s poznámkou (třeba Vyzkoušet jednu novou věc) zapiš, co to bylo."}
          </p>
        </Card>
      )}
      <ul className="ui-card divide-y divide-zinc-800 overflow-hidden">
        {abilities.map((a) => (
          <li key={a.id}>
            <button type="button" onClick={() => setOpen(a.id)} className="flex min-h-[60px] w-full items-center gap-3 px-3.5 py-2.5 text-left active:bg-zinc-800/60">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-lg">{a.icon ?? <Sparkles size={18} className="text-emerald-400" />}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-medium">{a.name}</span>
                <span className="block truncate text-xs text-zinc-500">
                  {a.count ? `${a.level_name} · ${a.count}× · naposledy ${formatDay(a.last_on!)}` : "zatím bez zápisu"}
                </span>
                {a.last_note && <span className="block truncate text-xs text-zinc-400">{a.last_note}</span>}
              </span>
              <LevelPips ability={a} />
            </button>
          </li>
        ))}
      </ul>
      {open != null && <AbilitySheet id={open} others={abilities.filter((a) => a.id !== open)} onClose={() => setOpen(null)} />}
    </div>
  );
}

function LevelPips({ ability }: { ability: Ability }) {
  return (
    <span className="flex shrink-0 gap-0.5" aria-label={`úroveň ${ability.level} ze 4`}>
      {[1, 2, 3, 4].map((n) => (
        <span key={n} className={`h-3 w-1.5 rounded-full ${n <= ability.level && ability.count ? "bg-emerald-500" : "bg-zinc-700"}`} />
      ))}
    </span>
  );
}

function AbilitySheet({ id, others, onClose }: { id: number; others: Ability[]; onClose: () => void }) {
  const { data: a } = useAbility(id);
  const edit = useEditAbility();
  const [mode, setMode] = useState<"view" | "edit" | "merge">("view");
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  if (!a) return null;

  const error = edit.error instanceof ApiError ? edit.error.message : edit.error ? "Nepodařilo se uložit (offline?)" : null;
  const next = a.next_level_at ? `další úroveň za ${a.next_level_at - a.count} ${plural(a.next_level_at - a.count, "zápis", "zápisy", "zápisů")}` : "nejvyšší úroveň";

  return (
    <Sheet title={`${a.icon ? `${a.icon} ` : ""}${a.name}`} onClose={onClose} tall>
      <div className="space-y-4">
        <p className="-mt-2 text-sm text-zinc-400">
          {a.count ? `${a.level_name} · ${a.count}× · od ${formatDay(a.first_on!)} · ${next}` : "Zatím bez zápisu"}
        </p>

        {mode === "view" && (
          <>
            <ol className="relative space-y-3 border-l-2 border-zinc-800 pl-4">
              {a.entries.map((e) => (
                <li key={`${e.habit_id}:${e.date}`} className="relative">
                  <span className="absolute -left-[21px] top-1.5 size-2.5 rounded-full bg-emerald-500" />
                  <p className="text-xs text-zinc-500">
                    <span className="capitalize">{formatDay(e.date)}</span> · {e.habit_title}
                  </p>
                  {e.rating ? <Stars value={e.rating} /> : null}
                  {e.note && <p className="text-sm whitespace-pre-line text-zinc-200">{e.note}</p>}
                </li>
              ))}
            </ol>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="ghost" onClick={() => (setName(a.name), setIcon(a.icon ?? ""), setMode("edit"))}>
                Upravit
              </Button>
              <Button variant="ghost" disabled={!others.length} onClick={() => setMode("merge")}>
                Sloučit s…
              </Button>
            </div>
            <Button
              variant="danger"
              className="w-full"
              onClick={() => (confirmDelete ? edit.mutate({ id, kind: "delete" }, { onSuccess: onClose }) : setConfirmDelete(true))}
            >
              {confirmDelete ? "Opravdu smazat? Poznámky zůstanou" : "Smazat dovednost"}
            </Button>
          </>
        )}

        {mode === "edit" && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              edit.mutate({ id, kind: "update", name: name.trim(), icon: icon.trim() || null }, { onSuccess: () => setMode("view") });
            }}
          >
            <label className="block text-sm text-zinc-400">
              Název
              <input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} className={input} required />
            </label>
            <label className="block text-sm text-zinc-400">
              Ikona (emoji)
              <input value={icon} maxLength={8} onChange={(e) => setIcon(e.target.value)} placeholder="🧗" className={input} />
            </label>
            <div className="grid grid-cols-[auto_1fr] gap-2">
              <Button type="button" variant="ghost" onClick={() => setMode("view")}>
                Zpět
              </Button>
              <Button type="submit" disabled={!name.trim() || edit.isPending}>
                Uložit
              </Button>
            </div>
          </form>
        )}

        {mode === "merge" && (
          <div className="space-y-2">
            <p className="text-sm text-zinc-400">Všechny zápisy {a.name} se přesunou do vybrané dovednosti a {a.name} zmizí.</p>
            <div className="flex flex-wrap gap-1.5">
              {others.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => edit.mutate({ id, kind: "merge", intoId: o.id }, { onSuccess: onClose })}
                  className="min-h-10 rounded-full bg-zinc-800 px-3 text-sm active:bg-zinc-700"
                >
                  {o.name}
                </button>
              ))}
            </div>
            <Button variant="ghost" className="w-full" onClick={() => setMode("view")}>
              Zpět
            </Button>
          </div>
        )}
        {error && <p className="text-sm text-red-300">{error}</p>}
      </div>
    </Sheet>
  );
}
