const FALLBACK = "Couldn't save the flow. Try again.";

/** Turn an RTK Query error from saving a flow into messages a person can act on. */
export function flowErrors(error: unknown): string[] {
  const detail = (error as { data?: { detail?: unknown } } | undefined)?.data?.detail;
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((entry: { loc?: unknown[]; msg?: string }) => {
      const where = (entry.loc ?? []).filter((part) => part !== "body").join(".");
      return where ? `${where}: ${entry.msg}` : String(entry.msg);
    });
  }
  return [FALLBACK];
}

/** Parse what was typed into the flow editor. A flow is always a JSON object. */
export function parseFlowJson(
  text: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; message: string } {
  try {
    const value: unknown = JSON.parse(text);
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return { ok: false, message: "A flow is a JSON object." };
    }
    return { ok: true, value: value as Record<string, unknown> };
  } catch {
    return { ok: false, message: "That isn't valid JSON." };
  }
}
