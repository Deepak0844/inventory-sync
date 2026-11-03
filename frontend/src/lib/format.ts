const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

/** "30 min ago", "5 h ago", "1 d ago". */
export function ago(iso: string, now: number): string {
  const diff = Math.max(0, now - Date.parse(iso));
  if (diff >= DAY) return `${Math.floor(diff / DAY)} d ago`;
  if (diff >= HOUR) return `${Math.floor(diff / HOUR)} h ago`;
  return `${Math.floor(diff / MIN)} min ago`;
}

/** "14:02" in the viewer's time zone. */
export function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** "9:41" for a countdown in seconds. */
export function mmss(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
