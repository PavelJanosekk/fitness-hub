/** Which habit day the entry sheet (EntrySheet.tsx) shows; one host in the Layout listens. */
export type EntryTarget = { habitId: number; day: string };

let target: EntryTarget | null = null;
const listeners = new Set<() => void>();

export const subscribeEntry = (listener: () => void) => (listeners.add(listener), () => void listeners.delete(listener));
export const entryTarget = () => target;
export function setEntryTarget(next: EntryTarget | null) {
  target = next;
  listeners.forEach((l) => l());
}
export const openEntrySheet = (habitId: number, day: string) => setEntryTarget({ habitId, day });
