import { type CSSProperties, type PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from "react";

const EDGE = 96; // px from the top/bottom of the viewport where dragging auto-scrolls the page
const BOTTOM_BAR = 80; // the fixed tab bar covers the bottom of the viewport on the phone
const MAX_SPEED = 14; // px per frame

type Drag = { from: number; to: number; dy: number };
type Session = { from: number; to: number; startY: number; tops: number[]; heights: number[]; gap: number; clientY: number; frame: number };

/**
 * Drag-and-drop reordering of a vertical list with pointer events (touch + mouse), no library.
 * The handle starts the drag; the item follows the finger, the others slide aside, and the page
 * auto-scrolls near the viewport edges so long lists of tall cards still work.
 */
export function useDragReorder(onMove: (from: number, to: number) => void) {
  const items = useRef<(HTMLElement | null)[]>([]);
  const session = useRef<Session | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const latestOnMove = useRef(onMove);
  latestOnMove.current = onMove;

  useEffect(() => () => cancelAnimationFrame(session.current?.frame ?? 0), []);

  const measure = (s: Session) => {
    const pageY = s.clientY + window.scrollY;
    const dy = pageY - s.startY;
    const center = s.tops[s.from] + s.heights[s.from] / 2 + dy;
    let to = 0;
    s.tops.forEach((top, i) => {
      if (i !== s.from && top + s.heights[i] / 2 < center) to += 1;
    });
    s.to = to;
    setDrag({ from: s.from, to, dy });
  };

  const autoScroll = () => {
    const s = session.current;
    if (!s) return;
    const bottom = window.innerHeight - BOTTOM_BAR;
    const speed =
      s.clientY < EDGE ? -MAX_SPEED * (1 - s.clientY / EDGE) : s.clientY > bottom - EDGE ? MAX_SPEED * Math.min(1, (s.clientY - bottom + EDGE) / EDGE) : 0;
    if (speed) {
      window.scrollBy(0, speed);
      measure(s);
    }
    s.frame = requestAnimationFrame(autoScroll);
  };

  const start = (index: number) => (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || session.current) return;
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const rects = items.current.map((el) => el?.getBoundingClientRect());
    const tops = rects.map((r) => (r?.top ?? 0) + window.scrollY);
    const heights = rects.map((r) => r?.height ?? 0);
    const gap = rects.length > 1 && rects[0] && rects[1] ? rects[1].top - rects[0].bottom : 0;
    const s: Session = { from: index, to: index, startY: event.clientY + window.scrollY, tops, heights, gap, clientY: event.clientY, frame: 0 };
    session.current = s;
    setDrag({ from: index, to: index, dy: 0 });
    s.frame = requestAnimationFrame(autoScroll);

    const onPointerMove = (e: PointerEvent) => {
      s.clientY = e.clientY;
      measure(s);
    };
    const end = (e: PointerEvent) => {
      handle.removeEventListener("pointermove", onPointerMove);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      cancelAnimationFrame(s.frame);
      session.current = null;
      setDrag(null);
      if (e.type === "pointerup" && s.to !== s.from) latestOnMove.current(s.from, s.to);
    };
    handle.addEventListener("pointermove", onPointerMove);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  };

  /** Props for the element that moves (wrap the whole list item). */
  const itemProps = (index: number): { ref: (el: HTMLElement | null) => void; style: CSSProperties; "data-dragging"?: true } => {
    const ref = (el: HTMLElement | null) => {
      items.current[index] = el;
    };
    if (!drag) return { ref, style: {} };
    if (index === drag.from)
      return { ref, "data-dragging": true, style: { transform: `translateY(${drag.dy}px)`, position: "relative", zIndex: 10, touchAction: "none" } };
    const s = session.current;
    const shift = (s?.heights[drag.from] ?? 0) + (s?.gap ?? 0);
    const offset = drag.from < index && index <= drag.to ? -shift : drag.to <= index && index < drag.from ? shift : 0;
    return { ref, style: { transform: offset ? `translateY(${offset}px)` : undefined, transition: "transform 150ms ease" } };
  };

  /** Props for the grip the finger presses to start dragging. */
  const handleProps = (index: number) => ({
    onPointerDown: start(index),
    style: { touchAction: "none", cursor: drag ? "grabbing" : "grab" } as CSSProperties,
  });

  return { itemProps, handleProps, dragging: drag !== null };
}

/** Move one element of a list to a new index. */
export function moveItem<T>(list: T[], from: number, to: number): T[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
