import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { api, ApiError, openSSE } from '../api';
import type { ReseedCandidate, ReseedCtx, SearchResult } from '../types';
import { ReseedWizardModal } from '../modals/ReseedWizardModal';

interface CategoryInfo { id: string; label: string; count: number; }

export function ReseedView({ isMobile }: { isMobile?: boolean }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'auto' | 'manual'>('auto');
  const [ctx, setCtx] = useState<ReseedCtx | null>(null);

  const tabBtn = (id: 'auto' | 'manual', label: string) => (
    <button
      onClick={() => setTab(id)}
      style={{
        background: tab === id ? 'var(--blue)' : 'var(--bg-card)',
        color: tab === id ? '#fff' : 'var(--fg-3)',
        border: '1px solid var(--border)', borderRadius: 6,
        padding: '7px 16px', fontSize: 12, fontWeight: 600, cursor: 'pointer',
        fontFamily: 'var(--font-display)',
      }}
    >{label}</button>
  );

  return (
    <div style={{ padding: isMobile ? '16px 14px' : 24 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18 }}>
        {tabBtn('auto', t('reseed.tabAuto'))}
        {tabBtn('manual', t('reseed.tabManual'))}
      </div>

      {tab === 'auto'
        ? <AutoCandidates onReseed={setCtx} />
        : <ManualSearch onReseed={setCtx} />}

      {ctx && (
        <ReseedWizardModal ctx={ctx} onClose={() => setCtx(null)} />
      )}
    </div>
  );
}

// --------------------------------------------------------------- auto -----

function AutoCandidates({ onReseed }: { onReseed: (c: ReseedCtx) => void }) {
  const { t } = useTranslation();
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [category, setCategory] = useState('');
  const [maxSeeders, setMaxSeeders] = useState(0);
  const [cands, setCands] = useState<ReseedCandidate[]>([]);
  const [scanning, setScanning] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [unenriched, setUnenriched] = useState(0);
  const closeRef = useRef<null | (() => void)>(null);

  useEffect(() => {
    api.get<{ categories: CategoryInfo[] }>('/api/library/categories')
      .then((r) => setCategories(r.categories))
      .catch(() => { /* ignore */ });
    return () => { closeRef.current?.(); };
  }, []);

  const runScan = (cat: string, offset: number, ms: number = maxSeeders) => {
    if (!cat) return;
    closeRef.current?.();
    setScanning(true);
    if (offset === 0) { setCands([]); setUnenriched(0); setHasMore(false); }
    const close = openSSE(
      `/api/reseed/scan?category=${encodeURIComponent(cat)}&offset=${offset}&limit=20&max_seeders=${ms}`,
      {
        onEvent: (name, data) => {
          if (name === 'candidate') {
            try { setCands((p) => [...p, JSON.parse(data) as ReseedCandidate]); } catch { /* */ }
          } else if (name === 'done') {
            try {
              const d = JSON.parse(data);
              setNextOffset(d.next_offset ?? offset);
              setHasMore(!!d.has_more);
              setUnenriched((u) => (offset === 0 ? 0 : u) + (d.unenriched || 0));
            } catch { /* */ }
            setScanning(false);
            closeRef.current?.();
            closeRef.current = null;
          }
        },
        onError: () => {
          setScanning(false);
          closeRef.current?.();
          closeRef.current = null;
        },
      },
    );
    closeRef.current = close;
  };

  const onCategory = (cat: string) => { setCategory(cat); runScan(cat, 0); };

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 14, fontFamily: 'var(--font-display)' }}>
        {t('reseed.autoDesc')}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <select
          value={category}
          onChange={(e) => onCategory(e.target.value)}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '9px 10px', fontSize: 13,
            color: 'var(--fg-1)', fontFamily: 'var(--font-display)',
          }}
        >
          <option value="">— {t('reseed.selectCategory')} —</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.label} ({c.count})</option>
          ))}
        </select>
        <label style={{
          display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
          color: 'var(--fg-3)', fontFamily: 'var(--font-display)',
        }}>
          {t('reseed.maxSeeders')}
          <input
            type="number" min={0} max={100} value={maxSeeders}
            onChange={(e) => {
              const v = Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0));
              setMaxSeeders(v);
              if (category) runScan(category, 0, v);
            }}
            style={{
              width: 56, background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '7px 8px', fontSize: 13, color: 'var(--fg-1)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </label>
        {category && (
          <button
            onClick={() => runScan(category, 0)}
            disabled={scanning}
            className="u3d-pressable"
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '8px 14px', fontSize: 12, fontWeight: 600,
              color: 'var(--fg-2)', cursor: scanning ? 'default' : 'pointer',
              fontFamily: 'var(--font-display)', display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            <RefreshCw size={13} style={scanning ? { animation: 'spin 1s linear infinite' } : undefined} />
            {scanning ? t('reseed.scanning') : t('reseed.scan')}
          </button>
        )}
        {(cands.length > 0 || unenriched > 0) && !scanning && (
          <span style={{ fontSize: 11, color: 'var(--fg-4)', fontFamily: 'var(--font-mono)' }}>
            {t('reseed.foundNote', { count: cands.length })}
            {unenriched > 0 && ` · ${t('reseed.unenrichedNote', { count: unenriched })}`}
          </span>
        )}
      </div>

      {!category && (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontFamily: 'var(--font-display)' }}>
          {t('reseed.pickCategory')}
        </div>
      )}

      <div className={cands.length > 0 ? 'u3d-stagger' : undefined}>
        {cands.map((c) => (
          <CandidateRow key={`${c.torrent.id}-${c.source_path}`} c={c} onReseed={onReseed} />
        ))}
      </div>

      {category && !scanning && cands.length === 0 && (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontFamily: 'var(--font-display)' }}>
          {t('reseed.noCandidates')}
        </div>
      )}

      {hasMore && !scanning && (
        <button
          onClick={() => runScan(category, nextOffset)}
          className="u3d-pressable"
          style={{
            marginTop: 6, width: '100%', background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6, padding: '10px',
            fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', cursor: 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >{t('reseed.loadMore')}</button>
      )}
      {scanning && cands.length > 0 && (
        <div style={{ padding: 10, textAlign: 'center', color: 'var(--fg-4)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {t('reseed.scanning')}
        </div>
      )}
    </div>
  );
}

function CandidateRow({ c, onReseed }: { c: ReseedCandidate; onReseed: (c: ReseedCtx) => void }) {
  const { t } = useTranslation();
  const se = c.season != null
    ? ` · S${String(c.season).padStart(2, '0')}${c.episode != null ? `E${String(c.episode).padStart(2, '0')}` : ''}`
    : '';
  return (
    <div
      className="u3d-card"
      style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 6, padding: '12px 16px', marginBottom: 8,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}
    >
      <div style={{ minWidth: 0 }}>
        <a
          href={c.torrent.details_link} target="_blank" rel="noreferrer"
          style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)', display: 'block', wordBreak: 'break-word' }}
        >{c.torrent.name}</a>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}>
          <Chip label={c.torrent.resolution} />
          <span style={{ fontSize: 10, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>{c.torrent.size_human}</span>
          <span style={{ fontSize: 10, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>↓ {c.torrent.seeders} {t('reseed.seedersLabel')}</span>
          <span style={{ fontSize: 10, color: 'var(--fg-4)', fontFamily: 'var(--font-mono)' }}>
            {t('reseed.localFile')}: {c.item_name}{se}
          </span>
        </div>
      </div>
      <button
        onClick={() => onReseed({
          tracker: c.torrent.tracker, torrentId: c.torrent.id, torrentName: c.torrent.name,
          torrent: c.torrent,
          local: {
            source_path: c.source_path, item_name: c.item_name,
            category: c.category, kind: c.kind,
            size: c.local_size, size_human: c.local_size_human,
          },
        })}
        className="u3d-pressable"
        style={{
          background: 'var(--blue)', border: 'none', borderRadius: 6,
          padding: '8px 16px', fontSize: 12, fontWeight: 600, color: '#fff',
          cursor: 'pointer', fontFamily: 'var(--font-display)', flexShrink: 0,
          display: 'flex', alignItems: 'center', gap: 6,
        }}
      ><RefreshCw size={13} /> {t('reseed.reseedBtn')}</button>
    </div>
  );
}

// ------------------------------------------------------------- manual -----

function ManualSearch({ onReseed }: { onReseed: (c: ReseedCtx) => void }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true); setError('');
    try {
      const r = await api.get<{ results: SearchResult[] }>(
        `/api/search?q=${encodeURIComponent(query)}&tracker=ITT`,
      );
      setResults(r.results);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 14, fontFamily: 'var(--font-display)' }}>
        {t('reseed.manualDesc')}
      </div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(); }}
          placeholder={t('reseed.searchPlaceholder')}
          style={{
            flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '9px 14px', fontSize: 13, color: 'var(--fg-1)',
            fontFamily: 'var(--font-display)',
          }}
        />
        <button
          onClick={run}
          disabled={!query.trim() || loading}
          style={{
            background: 'var(--blue)', border: 'none', borderRadius: 6,
            padding: '9px 18px', fontSize: 12, fontWeight: 600, color: '#fff',
            cursor: 'pointer', fontFamily: 'var(--font-display)',
          }}
        >{loading ? t('reseed.searching') : t('reseed.searchBtn')}</button>
      </div>

      {error && (
        <div style={{
          padding: 14, background: 'var(--red-dim)', border: '1px solid var(--red)',
          borderRadius: 6, color: 'var(--red)', fontFamily: 'var(--font-mono)', marginBottom: 16,
        }}>{error}</div>
      )}

      <div className={results.length > 0 ? 'u3d-stagger' : undefined}>
        {results.map((r) => (
          <div
            key={`${r.tracker}-${r.id}`}
            className="u3d-card"
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '12px 16px', marginBottom: 8,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <a
                href={r.url} target="_blank" rel="noreferrer"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)', display: 'block', wordBreak: 'break-word' }}
              >{r.name}</a>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}>
                <Chip label={r.type} color="var(--blue-bright)" bg="var(--blue-dim)" />
                <Chip label={r.resolution} />
                <span style={{ fontSize: 10, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>{r.size}</span>
                <span style={{
                  fontSize: 10, color: r.seeders > 0 ? 'var(--green)' : 'var(--red)',
                  fontFamily: 'var(--font-mono)',
                }}>↑ {r.seeders} {t('reseed.seedersLabel')}</span>
              </div>
            </div>
            <button
              onClick={() => onReseed({ tracker: r.tracker, torrentId: r.id, torrentName: r.name })}
              className="u3d-pressable"
              style={{
                background: 'var(--blue)', border: 'none', borderRadius: 6,
                padding: '8px 16px', fontSize: 12, fontWeight: 600, color: '#fff',
                cursor: 'pointer', fontFamily: 'var(--font-display)', flexShrink: 0,
                display: 'flex', alignItems: 'center', gap: 6,
              }}
            ><RefreshCw size={13} /> {t('reseed.reseedBtn')}</button>
          </div>
        ))}
      </div>

      {!loading && results.length === 0 && !error && query && (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontFamily: 'var(--font-display)' }}>
          {t('reseed.noResults')}
        </div>
      )}
    </div>
  );
}

function Chip({ label, color = 'var(--fg-1)', bg = 'var(--bg-card)' }: {
  label: string; color?: string; bg?: string;
}) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
      background: bg, color, border: '1px solid var(--border)',
      fontFamily: 'var(--font-display)',
    }}>{label}</span>
  );
}
