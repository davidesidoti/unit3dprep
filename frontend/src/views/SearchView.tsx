import { useState } from 'react';
import { api, ApiError } from '../api';
import type { SearchResult } from '../types';

export function SearchView() {
  const [query, setQuery] = useState('');
  const [tracker, setTracker] = useState('ITT');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('All');

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true); setError('');
    try {
      const r = await api.get<{ results: SearchResult[] }>(
        `/api/search?q=${encodeURIComponent(query)}&tracker=${tracker}`,
      );
      setResults(r.results);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const filtered = filter === 'All' ? results : results.filter((r) =>
    r.type === filter || r.resolution === filter || r.tracker === filter,
  );

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <select
          value={tracker}
          onChange={(e) => setTracker(e.target.value)}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '9px 10px', fontSize: 13,
            color: 'var(--fg-1)', fontFamily: 'var(--font-display)',
          }}
        >
          {['ITT', 'PTT', 'SIS'].map((t) => <option key={t}>{t}</option>)}
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(); }}
          placeholder="Search by title, TMDB ID, uploader…"
          style={{
            flex: 1, background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '9px 14px', fontSize: 13, color: 'var(--fg-1)',
            fontFamily: 'var(--font-display)',
          }}
        />
        <button
          onClick={run}
          disabled={!query.trim() || loading}
          style={{
            background: 'var(--blue)', border: 'none', borderRadius: 6,
            padding: '9px 18px', fontSize: 12, fontWeight: 600,
            color: '#fff', cursor: 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >{loading ? 'Searching…' : 'Search'}</button>
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        {['All', 'Movie', 'Serie', 'Game', '1080p', '4K', 'ITT', 'PTT'].map((f) => (
          <span
            key={f}
            onClick={() => setFilter(f)}
            style={{
              fontSize: 11, fontWeight: 600, padding: '3px 10px',
              borderRadius: 9999,
              background: filter === f ? 'var(--blue)' : 'var(--bg-card)',
              color: filter === f ? '#fff' : 'var(--fg-3)',
              cursor: 'pointer',
              border: '1px solid var(--border)',
              fontFamily: 'var(--font-display)',
            }}
          >{f}</span>
        ))}
      </div>

      {error && (
        <div style={{
          padding: 14, background: 'var(--red-dim)',
          border: '1px solid var(--red)', borderRadius: 6,
          color: 'var(--red)', fontFamily: 'var(--font-mono)', marginBottom: 16,
        }}>{error}</div>
      )}

      {filtered.map((r) => (
        <div
          key={`${r.tracker}-${r.id}`}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '12px 16px', marginBottom: 8,
            display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', cursor: 'pointer',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-card-hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--bg-card)')}
        >
          <div>
            <a
              href={r.url}
              target="_blank"
              rel="noreferrer"
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 12,
                color: 'var(--fg-1)', marginBottom: 5, display: 'block',
              }}
            >{r.name}</a>
            <div style={{ display: 'flex', gap: 6 }}>
              <Chip label={r.type} color="var(--blue-bright)" bg="var(--blue-dim)" />
              <Chip label={r.resolution} color="var(--fg-1)" bg="var(--bg-card)"
                    border="1px solid var(--border)" />
              <span style={{
                fontSize: 10, color: 'var(--fg-3)',
                fontFamily: 'var(--font-mono)', padding: '2px 6px',
              }}>{r.size}</span>
              <span style={{
                fontSize: 10, color: 'var(--green)',
                fontFamily: 'var(--font-mono)', padding: '2px 6px',
              }}>↑ {r.seeders} seeders</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 11,
              color: 'var(--blue)',
            }}>{r.tracker}</span>
          </div>
        </div>
      ))}

      {!loading && filtered.length === 0 && !error && query && (
        <div style={{
          padding: 20, textAlign: 'center',
          color: 'var(--fg-3)', fontFamily: 'var(--font-display)',
        }}>No results.</div>
      )}
    </div>
  );
}

function Chip({ label, color, bg, border }: {
  label: string; color: string; bg: string; border?: string;
}) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
      background: bg, color, border,
      fontFamily: 'var(--font-display)',
    }}>{label}</span>
  );
}
