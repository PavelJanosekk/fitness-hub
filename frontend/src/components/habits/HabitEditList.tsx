import { Archive, ArchiveRestore, ChevronRight, GripVertical, Trash2 } from "lucide-react";
import { useState } from "react";
import { useDeleteHabit, useReorderHabits, useSaveHabit } from "../../api/habits";
import { AUTO_RULES, type HabitDays, skillLabel } from "../../lib/habits";
import { moveItem, useDragReorder } from "../../lib/useDragReorder";
import { Card } from "../Layout";
import { Button, Sheet } from "../ui";
import { HabitSheet } from "./HabitSheet";
import { SkillDot } from "./parts";

function meta(h: HabitDays): string {
  const parts = [h.frequency === "daily" ? "denně" : `týdně ${h.weekly_target}×`];
  if (skillLabel(h.skill)) parts.push(skillLabel(h.skill)!);
  parts.push(h.is_bonus ? `bonus +${h.points} b` : `${h.points} b`);
  if (h.auto_rule) parts.push(`auto: ${AUTO_RULES.find((a) => a.rule === h.auto_rule)?.label ?? h.auto_rule}`);
  return parts.join(" · ");
}

/** Edit mode: drag to reorder, tap to edit, archive (history stays) / restore / delete for good. */
export function HabitEditList({ habits }: { habits: HabitDays[] }) {
  const active = habits.filter((h) => h.archived_at === null);
  const archived = habits.filter((h) => h.archived_at !== null);
  const reorder = useReorderHabits();
  const save = useSaveHabit();
  const [editing, setEditing] = useState<HabitDays | null>(null);
  const [deleting, setDeleting] = useState<HabitDays | null>(null);
  const drag = useDragReorder((from, to) => reorder.mutate([...moveItem(active, from, to), ...archived].map((h) => h.id)));

  return (
    <div className="space-y-3">
      <p className="text-[13px] text-zinc-400">Přetáhni za úchyt pro změnu pořadí. Archivovaná rutina zmizí ze dne, ale její historie zůstane v grafech.</p>
      <div className="space-y-1.5">
        {active.map((h, index) => (
          <div key={h.id} {...drag.itemProps(index)} className="ui-card flex items-center gap-1 pr-1 data-dragging:bg-zinc-900 data-dragging:shadow-2xl">
            <button type="button" aria-label="Přetáhnout" {...drag.handleProps(index)} className="flex h-12 w-10 shrink-0 items-center justify-center text-zinc-500 select-none">
              <GripVertical size={18} />
            </button>
            <button type="button" onClick={() => setEditing(h)} className="flex min-h-14 min-w-0 flex-1 items-center gap-2 py-2 text-left">
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-[15px]">
                  <SkillDot skill={h.skill} />
                  <span className="truncate">{h.title}</span>
                </span>
                <span className="block truncate text-xs text-zinc-500">{meta(h)}</span>
              </span>
              <ChevronRight size={16} className="shrink-0 text-zinc-600" />
            </button>
            <button
              type="button"
              aria-label={`Archivovat ${h.title}`}
              onClick={() => save.mutate({ id: h.id, archived: true })}
              className="flex size-11 shrink-0 items-center justify-center rounded-full text-zinc-500 active:bg-zinc-800"
            >
              <Archive size={18} />
            </button>
          </div>
        ))}
      </div>
      {(reorder.isError || save.isError) && <p className="text-sm text-red-300">Změnu se nepodařilo uložit. Rutiny jde upravit jen s připojením.</p>}

      {archived.length > 0 && (
        <Card className="space-y-1">
          <h2 className="mb-1 font-semibold">Archivované</h2>
          {archived.map((h) => (
            <div key={h.id} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm text-zinc-400">{h.title}</span>
              <button
                type="button"
                aria-label={`Obnovit ${h.title}`}
                onClick={() => save.mutate({ id: h.id, archived: false })}
                className="flex size-11 items-center justify-center rounded-full text-zinc-400 active:bg-zinc-800"
              >
                <ArchiveRestore size={18} />
              </button>
              <button
                type="button"
                aria-label={`Smazat ${h.title}`}
                onClick={() => setDeleting(h)}
                className="flex size-11 items-center justify-center rounded-full text-red-300 active:bg-zinc-800"
              >
                <Trash2 size={18} />
              </button>
            </div>
          ))}
        </Card>
      )}

      {editing && <HabitSheet habit={editing} onClose={() => setEditing(null)} />}
      {deleting && <DeleteSheet habit={deleting} onClose={() => setDeleting(null)} />}
    </div>
  );
}

function DeleteSheet({ habit, onClose }: { habit: HabitDays; onClose: () => void }) {
  const remove = useDeleteHabit();
  return (
    <Sheet title="Smazat rutinu?" onClose={onClose}>
      <p className="mb-4 text-zinc-300">
        „{habit.title}“ se smaže i s celou historií ({habit.done.length} zaškrtnutých dní). Tohle nejde vrátit. Pokud chceš historii zachovat, nech ji
        archivovanou.
      </p>
      {remove.isError && <p className="mb-3 text-sm text-red-300">Smazání se nepovedlo. Jsi online?</p>}
      <div className="grid grid-cols-2 gap-2">
        <Button variant="ghost" onClick={onClose}>
          Zrušit
        </Button>
        <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(habit.id, { onSuccess: onClose })}>
          Smazat
        </Button>
      </div>
    </Sheet>
  );
}
