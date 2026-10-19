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

/** A nutrient amount with as many decimals as its size needs, without trailing zeros (1 mg, 0,9 mg, 2,4 µg). */
export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 1 ? 1 : 2;
  return value.toLocaleString("cs-CZ", { maximumFractionDigits: digits });
}

export function formatPace(secondsPerKm: number | null | undefined): string {
  if (!secondsPerKm) return "–";
  const rounded = Math.round(secondsPerKm);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

/** "45:07" or "1:23:45". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "–";
  const s = Math.round(seconds);
  const [h, m, sec] = [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60];
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}
