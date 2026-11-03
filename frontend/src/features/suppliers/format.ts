/** "Every 3 h" for whole hours, otherwise "Every 90 min". */
export function everyInterval(minutes: number): string {
  return minutes % 60 === 0 ? `Every ${minutes / 60} h` : `Every ${minutes} min`;
}

/** "45 min", "2 h", "3 d" for an age in seconds. */
export function sessionAge(seconds: number): string {
  if (seconds >= 86_400) return `${Math.floor(seconds / 86_400)} d`;
  if (seconds >= 3_600) return `${Math.floor(seconds / 3_600)} h`;
  return `${Math.floor(seconds / 60)} min`;
}

const WHOLE = "Enter a whole number, 1 or more.";
export { WHOLE as WHOLE_NUMBER_MESSAGE };
