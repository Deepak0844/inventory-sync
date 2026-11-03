import { useState } from "react";

import type { Page } from "../../api/types";

interface QueryResult<T> {
  currentData?: Page<T>;
  isFetching: boolean;
  isError: boolean;
  fulfilledTimeStamp?: number;
  refetch: () => unknown;
}

/**
 * Cursor paging for a list screen: earlier pages are kept while the next one loads, and any
 * change to `args` (a filter, the search) starts again from the first page. No effects: the
 * kept pages live in state keyed by the args they belong to.
 */
export function usePagedQuery<T, A extends object>(
  useQuery: (arg: A & { cursor?: string }) => QueryResult<T>,
  args: A,
) {
  const key = JSON.stringify(args);
  const [state, setState] = useState<{ key: string; cursor?: string; pages: Page<T>[] }>({ key, pages: [] });
  const live = state.key === key ? state : { key, cursor: undefined, pages: [] };
  const query = useQuery({ ...args, cursor: live.cursor });
  const current = query.currentData;
  const next = current?.next_cursor ?? null;
  const items = [...live.pages.flatMap((p) => p.items), ...(current?.items ?? [])];
  return {
    items,
    total: current?.total ?? live.pages.at(-1)?.total ?? 0,
    loading: query.isFetching && items.length === 0,
    error: query.isError,
    lastUpdated: query.fulfilledTimeStamp,
    retry: () => void query.refetch(),
    loadMore:
      current && next ? () => setState({ key, cursor: next, pages: [...live.pages, current] }) : undefined,
  };
}
