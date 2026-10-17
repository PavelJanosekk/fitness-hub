const dateFormat = new Intl.DateTimeFormat("cs-CZ", { weekday: "short", day: "numeric", month: "numeric" });
const timeFormat = new Intl.DateTimeFormat("cs-CZ", { hour: "2-digit", minute: "2-digit" });

/** Local calendar date as YYYY-MM-DD (the backend's day key). */
export function isoDate(date: Date = new Date()): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T12:00:00`);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

export const formatDay = (iso: string) => dateFormat.format(new Date(iso.length === 10 ? `${iso}T12:00:00` : iso));
/** "12.10." without a weekday, for week ranges. */
export const formatDayMonth = (iso: string) => `${Number(iso.slice(8, 10))}.${Number(iso.slice(5, 7))}.`;
export const formatTime = (iso: string) => timeFormat.format(new Date(iso));

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "–";
  return value.toLocaleString("cs-CZ", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function formatPace(secondsPerKm: number | null | undefined): string {
  if (!secondsPerKm) return "–";
  const rounded = Math.round(secondsPerKm);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}
