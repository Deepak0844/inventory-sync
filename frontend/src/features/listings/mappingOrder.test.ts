import { moveMapping, removeMapping, addMapping } from "./mappingOrder";

const two = [{ listing_id: 1, priority: 1 }, { listing_id: 2, priority: 2 }];

it("moves a Listing down and renumbers priorities from 1", () => {
  expect(moveMapping(two, 1, "down")).toEqual([{ listing_id: 2, priority: 1 }, { listing_id: 1, priority: 2 }]);
});

it("moves a Listing up", () => {
  expect(moveMapping(two, 2, "up")).toEqual([{ listing_id: 2, priority: 1 }, { listing_id: 1, priority: 2 }]);
});

it("leaves the order alone at the ends", () => {
  expect(moveMapping(two, 1, "up")).toEqual(two);
  expect(moveMapping(two, 2, "down")).toEqual(two);
});

it("sorts by priority first, so a gap in the numbers does not matter", () => {
  const gappy = [{ listing_id: 5, priority: 9 }, { listing_id: 6, priority: 3 }];
  expect(moveMapping(gappy, 5, "up")).toEqual([{ listing_id: 5, priority: 1 }, { listing_id: 6, priority: 2 }]);
});

it("removes a Listing and renumbers", () => {
  expect(removeMapping(two, 1)).toEqual([{ listing_id: 2, priority: 1 }]);
});

it("adds a Listing last, and ignores one that is already mapped", () => {
  expect(addMapping(two, 3)).toEqual([...two, { listing_id: 3, priority: 3 }]);
  expect(addMapping(two, 2)).toEqual(two);
});
