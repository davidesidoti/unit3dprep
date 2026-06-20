import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import type { UploadedRecord } from '../types';
import { useIncremental } from '../hooks/useIncremental';
import { LoadMore } from '../components/primitives';

const kindColors: Record<string, { bg: string; fg: string }> = {
  movie:   { bg: 'var(--blue-dim)',   fg: 'var(--blue-bright)' },
  episode: { bg: '#2a1d5a',           fg: '#a78bfa' },
  series:  { bg: 'var(--green-dim)',  fg: 'var(--green)' },
};

export function UploadedView() {
  const { t } = useTranslation();
  const [records, setRecords] = useState<UploadedRecord[]>([]);
  const [filter, setFilter] = useState<'all' | 'movies' | 'series' | 'anime'>('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<number | null>(null);

  const load = () => api.get<{ records: UploadedRecord[] }>('/api/uploaded')
    .then((r) => setRecords(r.records))
    .catch(() => {});

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => records.filter((r) => {
    if (filter !== 'all' && r.category !== filter) return false;
    if (search && !r.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [records, filter, search]);

  const { visible, remaining, hasMore, loadMore } = useIncremental(filtered, 50, [filter, search]);

  const stats = {
    total: records.length,
    success: records.filter((r) => r.unit3dup_exit_code === 0 && !r.hardlink_only && !r.duplicate_skipped).length,
    failed: records.filter((r) => !r.duplicate_skipped && r.unit3dup_exit_code !== null && r.unit3dup_exit_code !== 0).length,
    manual: records.filter((r) => r.hardlink_only && !r.duplicate_skipped).length,
    skipped: records.filter((r) => r.duplicate_skipped).length,
  };

  const del = async (id: number) => {
    if (!confirm(t('uploaded.confirmDelete'))) return;
    try { await api.del(`/api/uploaded/${id}`); load(); } catch { /* ignore */ }
  };

  const filterLabels: Record<string, string> = {
    all: t('uploaded.filterAll'),
    movies: t('uploaded.filterMovies'),
    series: t('uploaded.filterSeries'),
    anime: t('uploaded.filterAnime'),
  };

  const colHeaders = [
    t('uploaded.colKind'),
    t('uploaded.colTitle'),
    t('uploaded.colTmdb'),
    t('uploaded.colUploaded'),
    t('uploaded.colStatus'),
    t('uploaded.colActions'),
  ];

  return (
    <div style={{
      padding: '18px 22px', display: 'flex', flexDirection: 'column',
      gap: 14, height: '100%', minHeight: 0, overflow: 'auto',
    }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 10,
      }}>
        <StatCard value={stats.total} label={t('uploaded.totalLabel')} />
        <StatCard value={stats.success} label={t('uploaded.successLabel')} color="var(--green)" />
        <StatCard value={stats.failed} label={t('uploaded.failedLabel')} color="var(--red)" />
        <StatCard value={stats.manual} label={t('uploaded.manualLabel')} color="var(--yellow)" />
        <StatCard value={stats.skipped} label={t('uploaded.skippedLabel')} color="var(--yellow)" />
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {(['all', 'movies', 'series', 'anime'] as const).map((k) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            style={{
              padding: '6px 12px', fontSize: 11, fontWeight: 600,
              borderRadius: 6, cursor: 'pointer',
              fontFamily: 'var(--font-display)',
              background: filter === k ? 'var(--blue)' : 'var(--bg-card)',
              color: filter === k ? '#fff' : 'var(--fg-2)',
              border: filter === k ? 'none' : '1px solid var(--border)',
            }}
          >{filterLabels[k]}</button>
        ))}
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('uploaded.searchPlaceholder')}
          style={{
            flex: 1, minWidth: 180, background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '7px 12px', fontSize: 12, color: 'var(--fg-1)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      <div style={{
        background: '#0a0c12', border: '1px solid var(--border-subtle)',
        borderRadius: 8, overflowX: 'auto', overflowY: 'auto',
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '80px minmax(240px, 1fr) 90px 180px 100px 140px',
          minWidth: 820,
        }}>
          {colHeaders.map((h) => (
            <div key={h} style={th}>{h}</div>
          ))}
        </div>
        <div className="u3d-stagger">
        {visible.map((r) => {
          const c = kindColors[r.kind] ?? kindColors.movie;
          const expanded = selected === r.id;
          return (
            <div key={r.id}>
              <div
                onClick={() => setSelected(expanded ? null : r.id)}
                className={expanded ? undefined : 'u3d-row'}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '80px minmax(240px, 1fr) 90px 180px 100px 140px',
                  minWidth: 820,
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: expanded ? '#14192a' : 'transparent',
                }}
              >
                <div style={td}>
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: '2px 6px',
                    borderRadius: 3, background: c.bg, color: c.fg,
                    fontFamily: 'var(--font-display)', textTransform: 'uppercase',
                  }}>{r.kind}</span>
                </div>
                <div style={td}>
                  <div style={{
                    color: 'var(--fg-1)', fontWeight: 600,
                    fontFamily: 'var(--font-display)', fontSize: 12, marginBottom: 2,
                  }}>
                    {r.title} <span style={{ color: 'var(--fg-3)', fontWeight: 400 }}>
                      · {r.year}
                    </span>
                  </div>
                  <div style={{
                    color: 'var(--blue-bright)', fontSize: 10,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    fontFamily: 'var(--font-mono)',
                  }}>{r.final_name || r.seeding_path}</div>
                </div>
                <div style={td}>
                  <span style={{
                    color: 'var(--blue-bright)',
                    fontFamily: 'var(--font-mono)',
                  }}>{r.tmdb_id || '—'}</span>
                </div>
                <div style={td}>
                  <span style={{
                    color: 'var(--fg-2)',
                    fontFamily: 'var(--font-mono)',
                  }}>{r.uploaded_at}</span>
                </div>
                <div style={td}>
                  {r.duplicate_skipped
                    ? <span style={{ color: 'var(--yellow)', fontWeight: 600 }}>⏭ {t('uploaded.statusDuplicateSkipped')}</span>
                    : r.hardlink_only
                    ? <span style={{ color: 'var(--yellow)', fontWeight: 600 }}>{t('uploaded.statusManual')}</span>
                    : r.unit3dup_exit_code === 0
                      ? <span style={{ color: 'var(--green)', fontWeight: 600 }}>✓ exit 0</span>
                      : r.unit3dup_exit_code === null
                        ? <span style={{ color: 'var(--yellow)' }}>{t('uploaded.statusPending')}</span>
                        : <span style={{ color: 'var(--red)', fontWeight: 600 }}>
                            ✗ exit {r.unit3dup_exit_code}
                          </span>}
                </div>
                <div style={td} onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => del(r.id)}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border)',
                      color: 'var(--red)', padding: '3px 8px',
                      fontSize: 10, fontWeight: 600, borderRadius: 4,
                      cursor: 'pointer', fontFamily: 'var(--font-display)',
                    }}
                  >{t('uploaded.deleteBtn')}</button>
                </div>
              </div>
              {expanded && (
                <div className="u3d-animate-in" style={{
                  padding: '14px 18px', background: 'var(--bg-base)',
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  <div style={{
                    display: 'grid', gridTemplateColumns: '140px 1fr',
                    gap: 8, fontSize: 11, fontFamily: 'var(--font-mono)',
                    lineHeight: 1.8,
                  }}>
                    <KV k="ID" v={r.id} />
                    <KV k={t('uploaded.detailCategory')} v={r.category} />
                    <KV k={t('uploaded.detailSourcePath')} v={r.source_path} />
                    <KV k={t('uploaded.detailSeedingPath')} v={r.seeding_path} />
                    <KV k={t('uploaded.detailFinalName')} v={r.final_name} color="var(--blue-bright)" />
                    <KV k={t('uploaded.detailTmdbId')} v={r.tmdb_id || '—'} />
                    <KV k={t('uploaded.detailUploadedAt')} v={r.uploaded_at} />
                    <KV k={t('uploaded.detailExit')} v={r.unit3dup_exit_code ?? t('uploaded.statusPending')}
                        color={r.unit3dup_exit_code === 0 ? 'var(--green)'
                          : r.unit3dup_exit_code ? 'var(--red)' : 'var(--yellow)'} />
                    <KV k={t('uploaded.detailHardlinkOnly')} v={r.hardlink_only ? t('common.yes') : t('common.no')} />
                  </div>
                </div>
              )}
            </div>
          );
        })}
        </div>
        {hasMore && (
          <div style={{ padding: '0 10px 10px' }}>
            <LoadMore remaining={remaining} onClick={loadMore} />
          </div>
        )}
        {filtered.length === 0 && (
          <div style={{
            padding: '40px 20px', textAlign: 'center',
            color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 12,
          }}>{t('uploaded.noMatches')}</div>
        )}
      </div>
    </div>
  );
}

function StatCard({ value, label, color = 'var(--fg-1)' }: {
  value: number; label: string; color?: string;
}) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '12px 14px',
    }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color,
      }}>{value}</div>
      <div style={{
        fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-wider)', color: 'var(--fg-3)',
        marginTop: 4, fontFamily: 'var(--font-display)',
      }}>{label}</div>
    </div>
  );
}

function KV({ k, v, color = 'var(--fg-1)' }: {
  k: string; v: React.ReactNode; color?: string;
}) {
  return (
    <>
      <span style={{ color: 'var(--fg-3)' }}>{k}</span>
      <span style={{ color, wordBreak: 'break-all' }}>{v}</span>
    </>
  );
}

const th: React.CSSProperties = {
  padding: '10px 14px', fontSize: 10, fontWeight: 700,
  textTransform: 'uppercase', letterSpacing: 'var(--tracking-wider)',
  color: 'var(--fg-4)', background: 'var(--bg-base)',
  borderBottom: '1px solid var(--border-subtle)',
  fontFamily: 'var(--font-display)',
};

const td: React.CSSProperties = {
  padding: '10px 14px', fontSize: 11,
  fontFamily: 'var(--font-mono)', color: 'var(--fg-1)',
  verticalAlign: 'top',
};
