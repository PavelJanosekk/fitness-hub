import { ArrowDown, ArrowUp, Bot, Flame, Gift, Pause, Play, Skull, Trash2, Zap } from "lucide-react";
import { Link } from "react-router";
import { useState } from "react";
import { RPG_SUMMARY_PROMPT } from "../api/coach";
import { type Pause as PauseRow, useCharacter, usePauses, useSavePause, useXpHistory } from "../api/rpg";
import { Card } from "../components/Layout";
import { LevelBadge, signed, XpBar } from "../components/rpg/CharacterCard";
import { BossCard } from "../components/rpg/BossCard";
import { BadgesCard, QuestsCard } from "../components/rpg/QuestsCard";
import { SkillsCard } from "../components/rpg/SkillsCard";
import { Button, Sheet } from "../components/ui";
import { addDays, formatDay, formatDayMonth, formatNumber, isoDate } from "../lib/format";

const PAGE_DAYS = [30, 90, 365, 3650];

export function Hero() {
  const { data: c } = useCharacter();
  const [range, setRange] = useState(0);
  const history = useXpHistory(PAGE_DAYS[range]);

  return (
    <>
      <div className="space-y-3">
        {c && (
          <Card className="space-y-4">
            <div className="flex items-center gap-4">
              <LevelBadge level={c.level} size={68} />
              <div className="min-w-0">
                <div className="text-xl font-bold">{c.title}</div>
                <div className="text-[13px] text-zinc-400">
                  {c.next_title ? `další titul na levelu ${c.next_title.level}: ${c.next_title.title}` : "nejvyšší titul"}
                </div>
              </div>
            </div>
            <XpBar c={c} />
            <div className="grid grid-cols-3 gap-2 text-center">
              <Stat label="Tento týden" value={`${signed(c.week_xp)} XP`} tone={c.week_xp < 0 ? "bad" : undefined} />
              <Stat label="Týdny v řadě" value={String(c.week_streak)} />
              <Stat label="Násobič" value={`×${formatNumber(c.multiplier, 1)}`} />
            </div>
            <p className="text-xs text-zinc-500">
              {c.forgiven_this_month
                ? `Odpuštěný den tento měsíc už padl na ${formatDayMonth(c.forgiven_this_month)} Další vynechaný den se trestá.`
                : "Tento měsíc máš ještě jeden odpuštěný den."}{" "}
              Týden pod 60 % a den pod 30 % rutiny berou XP i level.
            </p>
          </Card>
        )}

        {c && (c.tired || c.cursed.length > 0) && (
          <Card className="space-y-2 border-red-500/30!">
            <h2 className="font-semibold text-red-300">Debuffy</h2>
            {c.tired && (
              <p className="flex items-start gap-2 text-sm">
                <Zap size={16} className="mt-0.5 shrink-0 text-red-300" />
                Únava: XP ×0,8, dokud tento týden nebude rutina na 60 %.
              </p>
            )}
            {c.cursed.map((title) => (
              <p key={title} className="flex items-start gap-2 text-sm">
                <Skull size={16} className="mt-0.5 shrink-0 text-red-300" />
                Prokletý návyk {title}: splnění = dvojnásobné XP, vynechání = mínus XP.
              </p>
            ))}
          </Card>
        )}

        <Link
          to={`/coach?ask=${encodeURIComponent(RPG_SUMMARY_PROMPT)}`}
          className="ui-card flex items-center gap-3 p-4 active:bg-zinc-800/60"
        >
          <Bot size={22} className="shrink-0 text-emerald-400" />
          <span className="min-w-0 flex-1">
            <span className="block font-semibold">RPG shrnutí týdne od kouče</span>
            <span className="text-xs text-zinc-400">XP, tresty a proč, výpravy, boss a rady na příští týden</span>
          </span>
          <Flame size={18} className="shrink-0 text-amber-400" />
        </Link>

        <QuestsCard />

        <BossCard />

        {c?.skills?.length ? <SkillsCard skills={c.skills} /> : null}

        <BadgesCard />

        <PauseCard />

        <section className="space-y-2">
          <h2 className="px-0.5 pt-1 font-semibold">Historie XP</h2>
          {history.isPending ? (
            <p className="text-zinc-500">Načítám…</p>
          ) : (
            history.data?.map((day) => (
              <Card key={day.date} className="space-y-1.5 py-3!">
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-medium capitalize">{day.date === isoDate() ? "Dnes" : formatDay(day.date)}</span>
                  <Amount value={day.total} bold />
                </div>
                {day.entries.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 text-[13px]">
                    <EntryIcon kind={e.kind} />
                    <span className={`min-w-0 flex-1 ${e.amount === 0 ? "text-zinc-400" : "text-zinc-200"}`}>{e.text}</span>
                    {e.amount !== 0 && <Amount value={e.amount} />}
                  </div>
                ))}
              </Card>
            ))
          )}
          {range < PAGE_DAYS.length - 1 && (
            <Button variant="ghost" className="w-full" onClick={() => setRange(range + 1)}>
              Starší historie
            </Button>
          )}
        </section>
      </div>
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "bad" }) {
  return (
    <div className="rounded-xl bg-zinc-800/60 px-2 py-2">
      <div className="text-[11px] text-zinc-400">{label}</div>
      <div className={`text-base font-semibold tabular-nums ${tone === "bad" ? "text-red-300" : ""}`}>{value}</div>
    </div>
  );
}

function Amount({ value, bold = false }: { value: number; bold?: boolean }) {
  const color = value > 0 ? "text-emerald-300" : value < 0 ? "text-red-300" : "text-zinc-500";
  return <span className={`shrink-0 tabular-nums ${bold ? "text-sm font-semibold" : "text-[13px]"} ${color}`}>{signed(value)} XP</span>;
}

function EntryIcon({ kind }: { kind: string }) {
  const icon =
    kind === "level_up" ? <ArrowUp size={13} className="text-emerald-400" /> :
    kind === "level_down" ? <ArrowDown size={13} className="text-red-400" /> :
    kind === "forgiven" ? <Gift size={13} className="text-sky-400" /> :
    kind === "pause" ? <Pause size={13} className="text-zinc-400" /> : null;
  return <span className="flex h-[18px] w-3.5 shrink-0 items-center">{icon}</span>;
}

function PauseCard() {
  const pauses = usePauses();
  const save = useSavePause();
  const [starting, setStarting] = useState(false);
  const today = isoDate();
  const active = pauses.data?.find((p) => p.start_date <= today && (p.end_date === null || p.end_date >= today));
  const past = (pauses.data ?? []).filter((p) => p !== active).slice(0, 5);

  const end = (p: PauseRow) =>
    p.start_date >= today ? save.mutate({ id: p.id, remove: true }) : save.mutate({ id: p.id, end_date: addDays(today, -1) });

  return (
    <Card className="space-y-2.5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Pauza</h2>
          <p className="text-xs text-zinc-400">Nemoc nebo dovolená: dny v pauze se nepočítají, žádné XP ani tresty.</p>
        </div>
        {active ? (
          <Button variant="ghost" onClick={() => end(active)} disabled={save.isPending} className="flex shrink-0 items-center gap-1.5">
            <Play size={16} /> Ukončit
          </Button>
        ) : (
          <Button variant="ghost" onClick={() => setStarting(true)} className="flex shrink-0 items-center gap-1.5">
            <Pause size={16} /> Zapnout
          </Button>
        )}
      </div>
      {active && (
        <p className="rounded-xl bg-zinc-800/70 px-3 py-2 text-sm">
          Pauza od {formatDayMonth(active.start_date)}
          {active.end_date ? ` do ${formatDayMonth(active.end_date)}` : ""}
          {active.note ? ` · ${active.note}` : ""}. Ukončením začne počítat dnešek.
        </p>
      )}
      {past.map((p) => (
        <div key={p.id} className="flex items-center gap-2 text-[13px] text-zinc-400">
          <span className="flex-1">
            {formatDayMonth(p.start_date)}–{p.end_date ? formatDayMonth(p.end_date) : "…"}
            {p.note ? ` · ${p.note}` : ""}
          </span>
          <button type="button" aria-label="Smazat pauzu" onClick={() => save.mutate({ id: p.id, remove: true })} className="flex size-9 items-center justify-center rounded-full text-zinc-500 active:bg-zinc-800">
            <Trash2 size={15} />
          </button>
        </div>
      ))}
      {save.isError && <p className="text-sm text-red-300">Nepovedlo se uložit (překrývá se s jinou pauzou, nebo jsi offline).</p>}
      {starting && <PauseSheet onClose={() => setStarting(false)} />}
    </Card>
  );
}

function PauseSheet({ onClose }: { onClose: () => void }) {
  const save = useSavePause();
  const today = isoDate();
  const [start, setStart] = useState(today);
  const [endDate, setEndDate] = useState("");
  const [note, setNote] = useState("");
  const input = "mt-1 min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-base text-zinc-100 outline-none focus:border-emerald-500";
  return (
    <Sheet title="Zapnout pauzu" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ start_date: start, end_date: endDate || null, note: note.trim() || null }, { onSuccess: onClose });
        }}
      >
        <label className="block text-sm text-zinc-400">
          Od
          <input type="date" value={start} max={today} onChange={(e) => setStart(e.target.value)} className={input} />
        </label>
        <label className="block text-sm text-zinc-400">
          Do (prázdné = dokud ji neukončíš)
          <input type="date" value={endDate} min={start} onChange={(e) => setEndDate(e.target.value)} className={input} />
        </label>
        <label className="block text-sm text-zinc-400">
          Důvod
          <input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder="např. chřipka" className={input} />
        </label>
        {save.isError && <p className="text-sm text-red-300">Pauza se překrývá s jinou, nebo jsi offline.</p>}
        <Button type="submit" disabled={!start || save.isPending} className="w-full">
          Zapnout pauzu
        </Button>
      </form>
    </Sheet>
  );
}
