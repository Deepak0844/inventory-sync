import { fractionToPercent, percentToFraction } from "./killSwitch";

it("shows the stored fraction as a percent and back", () => {
  expect(fractionToPercent(0.3)).toBe(30);
  expect(percentToFraction(30)).toBe(0.3);
});

it("does not leak float noise", () => {
  expect(fractionToPercent(0.07)).toBe(7);
  expect(percentToFraction(7)).toBe(0.07);
});
