import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const styles = {
    primary: "bg-emerald-500 text-on-accent active:bg-emerald-400 disabled:bg-zinc-700 disabled:text-zinc-400",
    ghost: "bg-zinc-800 text-zinc-100 active:bg-zinc-700",
    danger: "bg-red-500/15 text-red-300 active:bg-red-500/25",
  }[variant];
  return (
    <button className={`ui-btn ui-btn-${variant} min-h-11 rounded-xl px-4 font-medium transition-colors ${styles} ${className}`} {...props}>
      {children}
    </button>
  );
}

/** Text input that opens the decimal keypad on phones and accepts a Czech decimal comma. */
export function DecimalInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <input
      type="text"
      inputMode="decimal"
      aria-label={ariaLabel}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/[^\d.,]/g, ""))}
      className={`min-h-11 w-full rounded-xl border border-zinc-700 bg-zinc-950 px-3 text-lg tabular-nums outline-none focus:border-emerald-500 ${className}`}
    />
  );
}

export const parseDecimal = (value: string): number | null => {
  const number = Number.parseFloat(value.replace(",", "."));
  return Number.isFinite(number) ? number : null;
};

/** The visible area above the on-screen keyboard (iOS keeps the layout viewport full-height and only shrinks this one). */
function useVisibleArea(): { top: number; height: number } | null {
  const [area, setArea] = useState<{ top: number; height: number } | null>(null);
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => setArea({ top: viewport.offsetTop, height: viewport.height });
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
    };
  }, []);
  return area;
}

/**
 * Bottom sheet on phones, centered dialog on desktop. It is sized to the area above the keyboard, so a search field
 * inside it never pushes the content under the keyboard. `tall` keeps a steady height (e.g. a filtered list).
 * Portaled to <body>: a glass card (backdrop-filter) would otherwise become the containing block of `fixed`.
 */
export function Sheet({ title, onClose, children, tall = false }: { title: string; onClose: () => void; children: React.ReactNode; tall?: boolean }) {
  const area = useVisibleArea();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div
      className="ui-scrim fixed inset-x-0 top-0 bottom-0 z-40 flex items-end justify-center md:items-center"
      style={area ? { top: area.top, bottom: "auto", height: area.height } : undefined}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={title}
        className="ui-sheet pb-safe max-h-[85dvh] w-full overflow-y-auto rounded-t-3xl border border-zinc-800 bg-zinc-900 p-4 md:max-w-lg md:rounded-3xl"
        style={area ? { maxHeight: area.height * 0.92, height: tall ? area.height * 0.92 : undefined } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button aria-label="Zavřít" onClick={onClose} className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: readonly (readonly [T, string])[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="ui-seg inline-flex rounded-xl p-1 text-sm">
      {options.map(([key, label]) => (
        <button key={String(key)} aria-pressed={value === key} onClick={() => onChange(key)} className="ui-seg-item min-h-9 rounded-lg px-3">
          {label}
        </button>
      ))}
    </div>
  );
}

/** One row of pill buttons; `null` is "all" when `allLabel` is given. */
export function Chips<T extends string>({
  options,
  value,
  onChange,
  allLabel,
  label,
  wrap = false,
}: {
  options: readonly (readonly [T, string])[];
  value: T | null;
  onChange: (value: T | null) => void;
  allLabel?: string;
  label: string;
  wrap?: boolean;
}) {
  const items: (readonly [T | null, string])[] = allLabel ? [[null, allLabel], ...options] : [...options];
  return (
    <div
      role="group"
      aria-label={label}
      className={wrap ? "flex flex-wrap gap-1.5" : "-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"}
    >
      {items.map(([key, text]) => (
        <button
          key={key ?? "all"}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          className={`min-h-9 shrink-0 rounded-full px-3 text-sm ${value === key ? "bg-emerald-500 font-medium text-on-accent" : "bg-zinc-800 text-zinc-300 active:bg-zinc-700"}`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

/** Prev/next with "2 / 5" between; renders nothing for a single page. */
export function Pager({ page, pages, onChange }: { page: number; pages: number; onChange: (page: number) => void }) {
  if (pages <= 1) return null;
  const button = "flex size-11 items-center justify-center rounded-lg text-zinc-300 active:bg-zinc-800 disabled:text-zinc-700";
  return (
    <div className="-my-2 -mr-2 flex items-center text-xs tabular-nums text-zinc-400">
      <button type="button" aria-label="Předchozí" className={button} disabled={page === 0} onClick={() => onChange(page - 1)}>
        <ChevronLeft size={18} />
      </button>
      {page + 1} / {pages}
      <button type="button" aria-label="Další" className={button} disabled={page >= pages - 1} onClick={() => onChange(page + 1)}>
        <ChevronRight size={18} />
      </button>
    </div>
  );
}
