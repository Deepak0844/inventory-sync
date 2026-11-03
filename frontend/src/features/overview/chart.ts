/** Geometry for the Sold Out by day line: straight segments, four gridlines, no legend. */

export interface Day {
  date: string;
  count: number;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const GRIDLINES = 4;

/** "2026-11-03" -> "3 Nov", without going through a time zone. */
function dayLabel(date: string): string {
  const [, month, day] = date.split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]}`;
}

/**
 * Lay the days out in a `width` x `height` box. The largest count is rounded up to four equal
 * gridline steps so the tick values are whole numbers; zero is the bottom edge.
 */
export function chartGeometry(days: Day[], width: number, height: number) {
  const max = Math.max(0, ...days.map((d) => d.count));
  const step = Math.max(1, Math.ceil(max / GRIDLINES));
  const top = step * GRIDLINES;
  const x = (i: number) => (days.length === 1 ? width / 2 : (i * width) / (days.length - 1));
  const y = (value: number) => height - (value / top) * height;

  const points = days.map((d, i) => ({ x: x(i), y: y(d.count) }));
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x} ${p.y}`).join(" ");
  const gridlines = Array.from({ length: GRIDLINES }, (_, i) => {
    const value = step * (i + 1);
    return { value, y: y(value) };
  });
  const picks = new Set([0, 1, 2, 3].map((i) => Math.round((i * (days.length - 1)) / 3)));
  const xLabels = [...picks].map((i) => ({ x: x(i), text: dayLabel(days[i].date) }));
  return { points, path, gridlines, xLabels };
}
