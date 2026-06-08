import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import type { QueueTorrent } from '../types';
import { StatusPill } from '../components/primitives';

function humanSize(b: number): string {
  const u = ['TB', 'GB', 'MB', 'KB'];
  const s = [2**40, 2**30, 2**20, 2**10];
  for (let i = 0; i < u.length; i++) {
    if (b >= s[i]) return `${(b / s[i]).toFixed(1)} ${u[i]}`;
  }
  return `${b} B`;
}

export function QueueView({ nameFilter = '' }: { nameFilter?: string }) {
  const { t } = useTranslation();
  const [data, setData] = useState<{
    client: string;
    torrents: QueueTorrent[];
    error?: string;
  }>({ client: '', torrents: [] });
  const [filter, setFilter] = useState<'all' | string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const tick = () => api.get<typeof data>('/api/queue')
      .then((r) => { setData(r); setLoading(false); })
      .catch((e) => { setData({ client: '', torrents: [], error: e.message }); setLoading(false); });
    tick();
    const iv = window.setInterval(tick, 5_000);
    return () => window.clearInterval(iv);
  }, []);

  const filtered = useMemo(() => {
    const q = nameFilter.trim().toLowerCase();
    return data.torrents.filter((tor) => {
      if (filter !== 'all' && tor.state !== filter) return false;
      if (q && !tor.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data.torrents, filter, nameFilter]);

  const counts = {
    total: data.torrents.length,
    seeding: data.torrents.filter((tor) => tor.state === 'seeding').length,
    errors: data.torrents.filter((tor) => tor.state === 'error').length,
  };

  if (data.error) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{
          padding: 16, background: 'var(--red-dim)',
          border: '1px solid var(--red)', borderRadius: 8,
          color: 'var(--red)', fontFamily: 'var(--font-mono)',
        }}>{data.client || t('queue.client')}: {data.error}</div>
      </div>
    );
  }

  const filterDefs = [
    { key: 'all',      label: t('queue.filterAll') },
    { key: 'seeding',  label: t('queue.filterSeeding') },
    { key: 'uploading',label: t('queue.filterUploading') },
    { key: 'queued',   label: t('queue.filterQueued') },
    { key: 'paused',   label: t('queue.filterPaused') },
    { key: 'error',    label: t('queue.filterError') },
  ];

  const colHeaders = [
    t('queue.colName'),
    t('queue.colProgress'),
    t('queue.colSize'),
    t('queue.colRatio'),
    t('queue.colTracker'),
    t('queue.colStatus'),
  ];

  return (
    <div style={{ paddingBottom: 24 }}>
      <div style={{
        display: 'flex', gap: 24, padding: '12px 24px',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        <Stat value={counts.total} label={t('queue.total')} />
        <Stat value={counts.seeding} label={t('queue.seeding')} color="var(--green)" />
        <Stat value={counts.errors} label={t('queue.errors')} color="var(--red)" />
        <Stat value={data.client || '—'} label={t('queue.client')} color="var(--yellow)" />
      </div>
      <div style={{
        display: 'flex', gap: 6, padding: '14px 24px',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        {filterDefs.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            style={{
              fontSize: 11, fontWeight: 600, padding: '4px 12px',
              borderRadius: 9999, cursor: 'pointer', border: 'none',
              fontFamily: 'var(--font-display)',
              background: filter === f.key ? 'var(--blue)' : 'var(--bg-card)',
              color: filter === f.key ? '#fff' : 'var(--fg-3)',
            }}
          >{f.label}</button>
        ))}
      </div>

      {loading && <div style={{ padding: 24, color: 'var(--fg-3)' }}>{t('queue.loading')}</div>}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {colHeaders.map((h) => (
              <th key={h} style={{
                padding: '8px 16px', textAlign: 'left', fontSize: 10,
                fontWeight: 600, color: 'var(--fg-4)',
                letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
                borderBottom: '1px solid var(--border)',
                fontFamily: 'var(--font-display)', background: '#0a0c12',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="u3d-stagger">
          {filtered.map((tor) => (
            <tr key={tor.hash} className="u3d-row">
              <td style={tdStyle}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)',
                  maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap', display: 'block',
                }} title={tor.name}>{tor.name}</span>
              </td>
              <td style={tdStyle}>
                <div style={{
                  height: 4, width: 100, background: 'var(--bg-card)',
                  borderRadius: 9999, overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', width: `${tor.progress * 100}%`,
                    background: 'var(--blue)',
                  }}/>
                </div>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10,
                  color: 'var(--fg-3)', marginTop: 2, display: 'block',
                }}>{(tor.progress * 100).toFixed(1)}%</span>
              </td>
              <td style={tdStyle}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)',
                }}>{humanSize(tor.size)}</span>
              </td>
              <td style={tdStyle}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)',
                }}>{tor.ratio.toFixed(2)}</span>
              </td>
              <td style={tdStyle}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue)',
                }}>{tor.tracker.split('/')[2] ?? tor.tracker ?? '—'}</span>
              </td>
              <td style={tdStyle}><StatusPill status={tor.state} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!loading && filtered.length === 0 && (
        <div style={{
          padding: '40px 20px', textAlign: 'center',
          color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
        }}>{t('queue.noTorrents')}</div>
      )}
    </div>
  );
}

function Stat({ value, label, color = 'var(--fg-1)' }: {
  value: string | number; label: string; color?: string;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{
        fontFamily: 'var(--font-display)', fontSize: 20,
        fontWeight: 700, color,
      }}>{value}</span>
      <span style={{
        fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600,
        color: 'var(--fg-3)',
        letterSpacing: 'var(--tracking-wide)', textTransform: 'uppercase',
      }}>{label}</span>
    </div>
  );
}

const tdStyle: React.CSSProperties = {
  padding: '10px 16px', borderBottom: '1px solid var(--border-subtle)',
};
