import { useEffect, useState } from 'react';

/**
 * Render-only pagination. Caps how many items of `items` are actually rendered
 * and exposes a `loadMore` step. The visible count resets to `pageSize` whenever
 * any value in `deps` changes (filters, search, category, new query result, …)
 * so narrowing the list never leaves a stale, oversized slice.
 *
 * Use for lists whose full data is already in memory: it cuts DOM nodes (and the
 * `u3d-stagger` entrance animations that run per child), not the underlying fetch.
 * Keep `deps` to the filter/search inputs only — NOT the polled data array — so a
 * background refresh (e.g. the queue's 5s poll) doesn't reset the user's position.
 */
export function useIncremental<T>(
  items: T[],
  pageSize = 50,
  deps: unknown[] = [],
): { visible: T[]; remaining: number; hasMore: boolean; loadMore: () => void } {
  const [count, setCount] = useState(pageSize);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setCount(pageSize); }, deps);
  const visible = count >= items.length ? items : items.slice(0, count);
  const remaining = Math.max(0, items.length - count);
  return {
    visible,
    remaining,
    hasMore: remaining > 0,
    loadMore: () => setCount((c) => c + pageSize),
  };
}
