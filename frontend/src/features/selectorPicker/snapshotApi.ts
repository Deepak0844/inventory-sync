import { api } from "../../api/api";

/**
 * The contract gives `html_url` as a path under /api. The slice's base query already adds
 * the base, so strip it; an absolute URL (used in tests) is left alone.
 */
export function snapshotPath(url: string): string {
  return url.startsWith("/api/") ? url.slice("/api".length) : url;
}

/** The cleaned page HTML of a Test run snapshot, added to the one API slice. */
export const snapshotApi = api.injectEndpoints({
  endpoints: (b) => ({
    snapshotHtml: b.query<string, string>({
      query: (url) => ({ url: snapshotPath(url), responseHandler: "text" }),
    }),
  }),
});

export const { useSnapshotHtmlQuery } = snapshotApi;
