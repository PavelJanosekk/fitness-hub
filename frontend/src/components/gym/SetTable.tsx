import { useState } from "react";
import type { SetType } from "../../api/gym";
import { Button, Sheet } from "../ui";

/** Compact set tables shared by the active workout and the template editor (Strong-style rows). */
export const SET_TYPES: Record<SetType, { label: string; short: string; color: string }> = {
  normal: { label: "Normální", short: "", color: "text-zinc-300" },
  warmup: { label: "Zahřívací", short: "W", color: "text-amber-300" },
  drop: { label: "Drop", short: "D", color: "text-violet-300" },
  failure: { label: "Do selhání", short: "F", color: "text-red-300" },
};

/** Input styling for kg / reps cells: 16px text so iOS doesn't zoom on focus. */
export const cellInput = (completed = false) =>
  `h-9 w-full min-w-0 rounded-lg ${completed ? "bg-transparent" : "bg-zinc-800"} text-center text-base font-semibold tabular-nums outline-none focus:ring-1 focus:ring-emerald-500 placeholder:text-sm placeholder:font-normal placeholder:text-zinc-600`;

export function TableHeader({ columns, className }: { columns: string[]; className: string }) {
  return (
    <div className={`grid items-center gap-1.5 px-1 pb-1 text-[11px] font-medium tracking-wide text-zinc-500 uppercase ${className}`}>
      {columns.map((c, i) => (
        <span key={i} className="text-center first:text-left">
          {c}
        </span>
      ))}
    </div>
  );
}

/**
 * The set label cell: working sets are numbered (warm-ups don't count), other types show a letter.
 * Tapping it opens a sheet to change the type or delete the set.
 */
export function SetLabel({
  types,
  index,
  onType,
  onRemove,
  canRemove = true,
}: {
  types: SetType[];
  index: number;
  onType: (type: SetType) => void;
  onRemove: () => void;
  canRemove?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const type = types[index];
  const number = types.slice(0, index + 1).filter((t) => t !== "warmup").length;
  return (
    <>
      <button
        type="button"
        aria-label={`Série ${index + 1}: typ nebo smazat`}
        onClick={() => setOpen(true)}
        className={`flex h-9 w-8 items-center justify-center rounded-lg text-sm font-semibold tabular-nums active:bg-zinc-700 ${SET_TYPES[type].color}`}
      >
        {SET_TYPES[type].short || number}
      </button>
      {open && (
        <Sheet title={`Série ${index + 1}`} onClose={() => setOpen(false)}>
          <div className="mb-3 grid grid-cols-2 gap-2">
            {(Object.keys(SET_TYPES) as SetType[]).map((t) => (
              <button
                key={t}
                onClick={() => (onType(t), setOpen(false))}
                className={`min-h-11 rounded-xl px-3 text-left text-sm ${t === type ? "bg-zinc-700 text-white" : "bg-zinc-800 text-zinc-300 active:bg-zinc-700"}`}
              >
                <span className={`mr-2 inline-block w-4 font-semibold ${SET_TYPES[t].color}`}>{SET_TYPES[t].short || "1"}</span>
                {SET_TYPES[t].label}
              </button>
            ))}
          </div>
          {canRemove && (
            <Button variant="danger" className="w-full" onClick={() => (onRemove(), setOpen(false))}>
              Smazat sérii
            </Button>
          )}
        </Sheet>
      )}
    </>
  );
}

export function AddSetButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="mt-1 w-full rounded-lg py-1.5 text-sm text-emerald-400 active:bg-zinc-800">
      + Přidat sérii
    </button>
  );
}
