import { chartGeometry } from "./chart";

const days = [
  { date: "2026-11-01", count: 0 },
  { date: "2026-11-02", count: 4 },
  { date: "2026-11-03", count: 10 },
];

it("draws straight segments from the first to the last day, left to right", () => {
  const g = chartGeometry(days, 300, 100);
  const xs = g.points.map((p) => p.x);
  expect(xs).toEqual([0, 150, 300]);
  expect(g.path.startsWith("M0")).toBe(true);
  expect(g.path.match(/L/g)).toHaveLength(2);
});

it("puts zero on the baseline and scales the busiest day against the top gridline", () => {
  const g = chartGeometry(days, 300, 100);
  expect(g.points[0].y).toBe(100);
  expect(g.gridlines[3].y).toBe(0);
  expect(g.points[2].y).toBeCloseTo(100 - (10 / 12) * 100);
});

it("has exactly four gridlines at round values", () => {
  const g = chartGeometry(days, 300, 100);
  expect(g.gridlines.map((l) => l.value)).toEqual([3, 6, 9, 12]);
});

it("keeps four gridlines and a flat line when every day is zero", () => {
  const g = chartGeometry([{ date: "a", count: 0 }, { date: "b", count: 0 }], 200, 80);
  expect(g.gridlines.map((l) => l.value)).toEqual([1, 2, 3, 4]);
  expect(g.points.every((p) => p.y === 80)).toBe(true);
});

it("handles a single day without dividing by zero", () => {
  const g = chartGeometry([{ date: "a", count: 2 }], 200, 80);
  expect(g.points).toHaveLength(1);
  expect(Number.isFinite(g.points[0].x)).toBe(true);
});

it("labels four dates along the axis, first and last included", () => {
  const many = Array.from({ length: 14 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 10, i + 1)).toISOString().slice(0, 10),
    count: i,
  }));
  const labels = chartGeometry(many, 300, 100).xLabels;
  expect(labels).toHaveLength(4);
  expect(labels[0].text).toBe("1 Nov");
  expect(labels[3].text).toBe("14 Nov");
});
