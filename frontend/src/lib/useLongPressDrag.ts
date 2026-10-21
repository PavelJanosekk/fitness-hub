import {
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

const HOLD_MS = 400; // press this long without moving to pick the row up
const SLOP = 8; // px a finger may wander during the hold; more is a scroll, so the press is dropped
const EDGE = 96; // px from the top/bottom of the viewport where dragging auto-scrolls the page
const BOTTOM_BAR = 80; // the fixed tab bar covers the bottom of the viewport on the phone
const MAX_SPEED = 14; // px per frame

/** The row being dragged: its rect when picked up, how far the finger moved, and the drop zone under it. */
export type LongPressDrag<T> = { value: T; rect: DOMRect; dx: number; dy: number; over: string | null };

/** Props for the row the finger holds (spread onto it). */
export type PressProps = {
  onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  onContextMenu: (event: ReactMouseEvent) => void;
  onClickCapture: (event: ReactMouseEvent) => void;
  style: CSSProperties;
};

type Session<T> = {
  value: T;
  row: HTMLElement;
  rect: DOMRect;
  anchored: boolean;
  startX: number;
  startY: number;
  x: number;
  y: number;
  over: string | null;
  frame: number;
};

/**
 * Long-press drag and drop with pointer events (touch + mouse), no library. A short tap stays a tap and a quick
 * swipe still scrolls; holding still picks the row up, then the finger carries it over drop zones marked with
 * `data-drop={key}` inside `container`, and the page auto-scrolls near the viewport edges.
 */
export function useLongPressDrag<T>(container: RefObject<HTMLElement | null>, onDrop: (value: T, zone: string) => void) {
  const [drag, setDrag] = useState<LongPressDrag<T> | null>(null);
  const session = useRef<Session<T> | null>(null);
  const cancel = useRef<() => void>(() => {});
  const suppressClick = useRef(false);
  const latestOnDrop = useRef(onDrop);
  latestOnDrop.current = onDrop;

  // While a row is up the finger must not scroll the page. iOS only honours preventDefault from a non-passive
  // listener that existed when the touch began, so it stays on the container and checks for a session.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const block = (e: TouchEvent) => {
      if (session.current) e.preventDefault();
    };
    el.addEventListener("touchmove", block, { passive: false });
    return () => el.removeEventListener("touchmove", block);
  }, [container]);

  useEffect(() => () => cancel.current(), []);

  const update = (s: Session<T>) => {
    const zone = document.elementFromPoint(s.x, s.y)?.closest<HTMLElement>("[data-drop]");
    s.over = zone && container.current?.contains(zone) ? (zone.dataset.drop ?? null) : null;
    setDrag({ value: s.value, rect: s.rect, dx: s.x - s.startX, dy: s.y - s.startY, over: s.over });
  };

  // Picking a row up may change the layout around it (drop zones appear); scroll so the row stays under the finger
  const active = drag !== null;
  useLayoutEffect(() => {
    const s = session.current;
    if (!active || !s || s.anchored) return;
    s.anchored = true;
    const shift = s.row.getBoundingClientRect().top - s.rect.top;
    if (shift) {
      window.scrollBy(0, shift);
      update(s);
    }
  });

  const autoScroll = () => {
    const s = session.current;
    if (!s) return;
    const bottom = window.innerHeight - BOTTOM_BAR;
    const speed = s.y < EDGE ? -MAX_SPEED * (1 - s.y / EDGE) : s.y > bottom - EDGE ? MAX_SPEED * Math.min(1, (s.y - bottom + EDGE) / EDGE) : 0;
    if (speed) {
      window.scrollBy(0, speed);
      update(s);
    }
    s.frame = requestAnimationFrame(autoScroll);
  };

  const press = (value: T) => (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || session.current) return;
    const row = event.currentTarget;
    const startX = event.clientX;
    const startY = event.clientY;
    let last = { x: startX, y: startY };

    const onMove = (e: PointerEvent) => {
      last = { x: e.clientX, y: e.clientY };
      const s = session.current;
      if (s) {
        s.x = e.clientX;
        s.y = e.clientY;
        update(s);
      } else if (Math.hypot(e.clientX - startX, e.clientY - startY) > SLOP) finish(false);
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);

    const finish = (dropped: boolean) => {
      window.clearTimeout(timer);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      cancel.current = () => {};
      const s = session.current;
      if (!s) return;
      cancelAnimationFrame(s.frame);
      session.current = null;
      setDrag(null);
      // the release still fires a click on the row; it must not open the item
      suppressClick.current = true;
      window.setTimeout(() => (suppressClick.current = false), 0);
      if (dropped && s.over) latestOnDrop.current(s.value, s.over);
    };

    const timer = window.setTimeout(() => {
      const s: Session<T> = { value, row, rect: row.getBoundingClientRect(), anchored: false, startX, startY, x: last.x, y: last.y, over: null, frame: 0 };
      session.current = s;
      navigator.vibrate?.(10);
      window.getSelection()?.removeAllRanges();
      update(s);
      s.frame = requestAnimationFrame(autoScroll);
    }, HOLD_MS);

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    cancel.current = () => finish(false);
  };

  const pressProps = (value: T): PressProps => ({
    onPointerDown: press(value),
    onContextMenu: (e) => e.preventDefault(),
    onClickCapture: (e) => {
      if (suppressClick.current) {
        e.preventDefault();
        e.stopPropagation();
      }
    },
    style: { WebkitTouchCallout: "none", WebkitUserSelect: "none", userSelect: "none" },
  });

  return { drag, pressProps };
}
