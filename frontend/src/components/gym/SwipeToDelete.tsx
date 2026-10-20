import { Trash2 } from "lucide-react";
import { type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type ReactNode, useEffect, useRef, useState } from "react";

const REVEAL = 64; // px the row slides open to show the trash button
const SLOP = 8; // px before a gesture picks its axis
const FULL = 0.5; // a swipe past this share of the row's width deletes right away
const AGAIN = 24; // px of a second left swipe on an open row that delete it
const ANIMATION = 200; // ms

type Gesture = { id: number; x: number; y: number; base: number; axis: "x" | "y" | null };

/**
 * iOS-style swipe-to-delete for a list row, with pointer events (touch + mouse), no library.
 * Swiping left slides the row open over a red trash button; tapping the button, swiping the open row left
 * again, or one long swipe deletes it. Vertical pans stay page scrolls (`touch-action: pan-y`).
 */
export function SwipeToDelete({ onDelete, label, children }: { onDelete: () => void; label: string; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const gesture = useRef<Gesture | null>(null);
  const offsetRef = useRef(0);
  const swallowClick = useRef(false);
  const [offset, setOffsetState] = useState(0); // <= 0
  const [dragging, setDragging] = useState(false);
  const [removing, setRemoving] = useState(false);
  const setOffset = (value: number) => ((offsetRef.current = value), setOffsetState(value));

  // An open row closes when anything else is touched
  useEffect(() => {
    if (offset === 0 || dragging || removing) return;
    const close = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOffset(0);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [offset, dragging, removing]);

  const remove = () => {
    const el = root.current;
    if (!el || removing) return;
    // Slide out, then collapse the height so the rows below move up smoothly
    el.style.maxHeight = `${el.offsetHeight}px`;
    setRemoving(true);
    setOffset(-el.offsetWidth);
    requestAnimationFrame(() => requestAnimationFrame(() => (el.style.maxHeight = "0px")));
    setTimeout(onDelete, ANIMATION + 60);
  };

  const onPointerDown = (e: ReactPointerEvent) => {
    if (removing || (e.pointerType === "mouse" && e.button !== 0)) return;
    // A tap on an open row only closes it: no focus on the input under the finger
    if (offsetRef.current < 0 && !(e.target as HTMLElement).closest("[data-swipe-trash]")) e.preventDefault();
    gesture.current = { id: e.pointerId, x: e.clientX, y: e.clientY, base: offsetRef.current, axis: null };
  };

  const onPointerMove = (e: ReactPointerEvent) => {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    const dx = e.clientX - g.x;
    const dy = e.clientY - g.y;
    if (g.axis === null) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < SLOP) return;
      // A closed row only reacts to a swipe to the left
      g.axis = Math.abs(dx) > Math.abs(dy) && (g.base < 0 || dx < 0) ? "x" : "y";
      if (g.axis === "y") return;
      try {
        root.current?.setPointerCapture(e.pointerId);
      } catch {
        // a pointer the browser no longer tracks: the drag still works while it stays over the row
      }
      (document.activeElement as HTMLElement | null)?.blur?.();
      setDragging(true);
    }
    if (g.axis === "x") setOffset(Math.min(0, g.base + dx));
  };

  const onPointerEnd = (e: ReactPointerEvent) => {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    gesture.current = null;
    if (g.axis !== "x") return;
    setDragging(false);
    // The tap that ends a drag must not tick the set or focus an input
    swallowClick.current = true;
    setTimeout(() => (swallowClick.current = false), 400);
    const width = root.current?.offsetWidth ?? 320;
    const moved = offsetRef.current - g.base;
    if (e.type === "pointercancel") setOffset(g.base);
    else if (-offsetRef.current > width * FULL || (g.base < 0 && moved < -AGAIN)) remove();
    else setOffset(-offsetRef.current > REVEAL / 2 ? -REVEAL : 0);
  };

  const onClickCapture = (e: ReactMouseEvent) => {
    const onTrash = (e.target as HTMLElement).closest("[data-swipe-trash]");
    if (swallowClick.current || (offsetRef.current < 0 && !onTrash)) {
      e.preventDefault();
      e.stopPropagation();
      if (!swallowClick.current) setOffset(0);
    }
  };

  const transition = dragging ? "none" : `transform ${ANIMATION}ms ease-out, width ${ANIMATION}ms ease-out`;
  return (
    <div
      ref={root}
      className="relative overflow-hidden rounded-lg"
      style={{ touchAction: "pan-y", transition: `max-height ${ANIMATION}ms ease-in, opacity ${ANIMATION}ms ease-in`, opacity: removing ? 0 : 1 }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onClickCapture={onClickCapture}
    >
      {offset < 0 && (
        <button
          type="button"
          data-swipe-trash
          aria-label={label}
          onClick={remove}
          className="absolute inset-y-0 right-0 flex items-center justify-center rounded-lg bg-red-500 text-white"
          style={{ width: Math.max(-offset, 0), transition }}
        >
          <Trash2 size={18} className="shrink-0" />
        </button>
      )}
      <div style={{ transform: `translateX(${offset}px)`, transition }}>{children}</div>
    </div>
  );
}
