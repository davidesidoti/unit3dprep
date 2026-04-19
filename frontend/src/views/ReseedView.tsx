import { SearchView } from './SearchView';

// Reseed = search-with-intent. v1 reuses the Search UX; action button on
// each row will hit /api/reseed/{tracker}/{id} once implemented.
export function ReseedView() {
  return (
    <div>
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid var(--border-subtle)',
        fontSize: 12, color: 'var(--fg-3)', fontFamily: 'var(--font-display)',
      }}>
        Search a tracker, then use the Reseed action to re-torrent an existing
        release. Currently read-only — action endpoint pending.
      </div>
      <SearchView />
    </div>
  );
}
