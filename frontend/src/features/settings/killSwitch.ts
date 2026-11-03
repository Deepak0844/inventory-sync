/** The API stores the kill switch threshold as a fraction (0.3); the form shows a percent (30). */
export const fractionToPercent = (fraction: number): number => Number((fraction * 100).toFixed(2));
export const percentToFraction = (percent: number): number => Number((percent / 100).toFixed(4));
