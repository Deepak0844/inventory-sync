import { navItems } from "./Nav";

const counted = (c: Parameters<typeof navItems>[0]) =>
  navItems(c).main.filter((i) => i.count).map((i) => `${i.label} ${i.count}`);

it("shows a count only on queues that need action", () => {
  expect(counted({ approvals: 2, orders: 4, notifications: 0 })).toEqual(["Approvals 2", "Orders 4"]);
});

it("shows no counts before the banner has loaded", () => {
  expect(counted(undefined)).toEqual([]);
});
