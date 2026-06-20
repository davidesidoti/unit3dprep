import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { api, openSSE } from '../api';
import type { ReseedCandidate, ReseedCtx, ReseedSearchResult } from '../types';
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
  const [total, setTotal] = useState(0);
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
    if (offset === 0) { setCands([]); setUnenriched(0); setHasMore(false); setTotal(0); }
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
              setTotal(d.total ?? 0);
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
      </div>

      {category && (scanning || total > 0) && (
        <div style={{
          marginBottom: 14, fontSize: 11, color: 'var(--fg-3)',
          fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {scanning && <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />}
          <span>
            {total > 0 ? t('reseed.progress', { scanned: nextOffset, total }) : t('reseed.scanning')}
            {total > 0 && ` · ${t('reseed.foundNote', { count: cands.length })}`}
            {unenriched > 0 && ` · ${t('reseed.unenrichedNote', { count: unenriched })}`}
          </span>
        </div>
      )}

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
        >{t('reseed.loadMoreCount', { count: Math.max(0, total - nextOffset) })}</button>
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
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [category, setCategory] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ReseedSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; category: string } | null>(null);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);
  const closeRef = useRef<null | (() => void)>(null);

  useEffect(() => {
    api.get<{ categories: CategoryInfo[] }>('/api/library/categories')
      .then((r) => setCategories(r.categories))
      .catch(() => { /* ignore */ });
    return () => { closeRef.current?.(); };
  }, []);

  // Streamed search: progress per local category scanned (the slow part), then
  // a result per reseedable torrent. An optional category narrows the scan.
  const run = () => {
    if (!query.trim()) return;
    closeRef.current?.();
    setLoading(true); setError(''); setSearched(true); setResults([]); setProgress(null);
    const close = openSSE(
      `/api/reseed/search/stream?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}`,
      {
        onEvent: (name, data) => {
          if (name === 'progress') {
            try { setProgress(JSON.parse(data)); } catch { /* */ }
          } else if (name === 'result') {
            try { setResults((p) => [...p, JSON.parse(data) as ReseedSearchResult]); } catch { /* */ }
          } else if (name === 'done') {
            setLoading(false);
            closeRef.current?.();
            closeRef.current = null;
          }
        },
        onError: () => {
          setLoading(false);
          closeRef.current?.();
          closeRef.current = null;
        },
      },
    );
    closeRef.current = close;
  };

  // Only reseedable torrents come back. If exactly one local file matches,
  // preset it so the wizard skips straight to confirm; otherwise the wizard
  // loads the size-matched candidates for the user to pick.
  const startReseed = (r: ReseedSearchResult) => {
    const single = r.local_matches.length === 1 ? r.local_matches[0] : undefined;
    onReseed({
      tracker: r.torrent.tracker, torrentId: r.torrent.id,
      torrentName: r.torrent.name, torrent: r.torrent, local: single,
    });
  };

  const pct = progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 14, fontFamily: 'var(--font-display)' }}>
        {t('reseed.manualDesc')}
      </div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap' }}>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          title={t('reseed.filterCategoryHint')}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '9px 10px', fontSize: 13,
            color: 'var(--fg-1)', fontFamily: 'var(--font-display)',
          }}
        >
          <option value="">{t('reseed.allCategories')}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(); }}
          placeholder={t('reseed.searchPlaceholder')}
          style={{
            flex: 1, minWidth: 160, background: 'var(--bg-card)', border: '1px solid var(--border)',
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
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          {loading && <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />}
          {loading ? t('reseed.searching') : t('reseed.searchBtn')}
        </button>
      </div>

      {error && (
        <div style={{
          padding: 14, background: 'var(--red-dim)', border: '1px solid var(--red)',
          borderRadius: 6, color: 'var(--red)', fontFamily: 'var(--font-mono)', marginBottom: 16,
        }}>{error}</div>
      )}

      {loading && (
        <div style={{
          padding: '28px 20px', display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: 12, color: 'var(--fg-3)',
          fontFamily: 'var(--font-display)',
        }}>
          <RefreshCw size={22} style={{ animation: 'spin 1s linear infinite', color: 'var(--blue)' }} />
          <span style={{ fontSize: 12, textAlign: 'center' }}>{t('reseed.searchingHint')}</span>
          {progress && progress.total > 0 && (
            <div style={{ width: 'min(320px, 85%)' }}>
              <div style={{
                height: 6, background: 'var(--bg-base)', borderRadius: 3,
                overflow: 'hidden', border: '1px solid var(--border-subtle)',
              }}>
                <div style={{
                  height: '100%', width: `${pct}%`, background: 'var(--blue-bright)',
                  transition: 'width 200ms ease-out', borderRadius: 3,
                }} />
              </div>
              <div style={{
                marginTop: 6, fontSize: 10, color: 'var(--fg-4)',
                fontFamily: 'var(--font-mono)', textAlign: 'center',
              }}>
                {t('reseed.scanProgress', { done: progress.done, total: progress.total })}
                {progress.category ? ` · ${progress.category}` : ''}
              </div>
            </div>
          )}
        </div>
      )}

      <div className={results.length > 0 ? 'u3d-stagger' : undefined}>
        {results.map((r) => {
          const m = r.local_matches;
          const localLabel = m.length === 1
            ? t('reseed.youHave', { name: m[0].item_name })
            : t('reseed.youHaveMulti', { count: m.length });
          return (
            <div
              key={`${r.torrent.tracker}-${r.torrent.id}`}
              className="u3d-card"
              style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                borderRadius: 6, padding: '12px 16px', marginBottom: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <a
                  href={r.torrent.details_link} target="_blank" rel="noreferrer"
                  style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)', display: 'block', wordBreak: 'break-word' }}
                >{r.torrent.name}</a>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}>
                  <Chip label={r.torrent.type} color="var(--blue-bright)" bg="var(--blue-dim)" />
                  <Chip label={r.torrent.resolution} />
                  <span style={{ fontSize: 10, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>{r.torrent.size_human}</span>
                  <span style={{
                    fontSize: 10, color: r.torrent.seeders > 0 ? 'var(--green)' : 'var(--red)',
                    fontFamily: 'var(--font-mono)',
                  }}>↑ {r.torrent.seeders} {t('reseed.seedersLabel')}</span>
                  <span style={{ fontSize: 10, color: 'var(--green)', fontFamily: 'var(--font-mono)' }}>✓ {localLabel}</span>
                </div>
              </div>
              <button
                onClick={() => startReseed(r)}
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
        })}
      </div>

      {!loading && results.length === 0 && !error && searched && (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontFamily: 'var(--font-display)' }}>
          {t('reseed.noReseedable')}
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
