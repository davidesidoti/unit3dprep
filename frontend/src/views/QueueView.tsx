import { useEffect, useMemo, useState } from 'react';
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
    return data.torrents.filter((t) => {
      if (filter !== 'all' && t.state !== filter) return false;
      if (q && !t.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data.torrents, filter, nameFilter]);

  const counts = {
    total: data.torrents.length,
    seeding: data.torrents.filter((t) => t.state === 'seeding').length,
    errors: data.torrents.filter((t) => t.state === 'error').length,
  };

  if (data.error) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{
          padding: 16, background: 'var(--red-dim)',
          border: '1px solid var(--red)', borderRadius: 8,
          color: 'var(--red)', fontFamily: 'var(--font-mono)',
        }}>{data.client || 'torrent client'}: {data.error}</div>
      </div>
    );
  }

  const filters = ['all', 'seeding', 'uploading', 'queued', 'paused', 'error'];

  return (
    <div style={{ paddingBottom: 24 }}>
      <div style={{
        display: 'flex', gap: 24, padding: '12px 24px',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        <Stat value={counts.total} label="Total" />
        <Stat value={counts.seeding} label="Seeding" color="var(--green)" />
        <Stat value={counts.errors} label="Errors" color="var(--red)" />
        <Stat value={data.client || '—'} label="Client" color="var(--yellow)" />
      </div>
      <div style={{
        display: 'flex', gap: 6, padding: '14px 24px',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              fontSize: 11, fontWeight: 600, padding: '4px 12px',
              borderRadius: 9999, cursor: 'pointer', border: 'none',
              fontFamily: 'var(--font-display)',
              background: filter === f ? 'var(--blue)' : 'var(--bg-card)',
              color: filter === f ? '#fff' : 'var(--fg-3)',
            }}
          >{f === 'all' ? 'All' : f[0].toUpperCase() + f.slice(1)}</button>
        ))}
      </div>

      {loading && <div style={{ padding: 24, color: 'var(--fg-3)' }}>loading…</div>}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {['Name', 'Progress', 'Size', 'Ratio', 'Tracker', 'Status'].map((h) => (
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
        <tbody>
          {filtered.map((t) => (
            <tr key={t.hash}>
              <td style={td}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)',
                  maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap', display: 'block',
                }} title={t.name}>{t.name}</span>
              </td>
              <td style={td}>
                <div style={{
                  height: 4, width: 100, background: 'var(--bg-card)',
                  borderRadius: 9999, overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', width: `${t.progress * 100}%`,
                    background: 'var(--blue)',
                  }}/>
                </div>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10,
                  color: 'var(--fg-3)', marginTop: 2, display: 'block',
                }}>{(t.progress * 100).toFixed(1)}%</span>
              </td>
              <td style={td}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)',
                }}>{humanSize(t.size)}</span>
              </td>
              <td style={td}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)',
                }}>{t.ratio.toFixed(2)}</span>
              </td>
              <td style={td}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue)',
                }}>{t.tracker.split('/')[2] ?? t.tracker ?? '—'}</span>
              </td>
              <td style={td}><StatusPill status={t.state} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!loading && filtered.length === 0 && (
        <div style={{
          padding: '40px 20px', textAlign: 'center',
          color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
        }}>No torrents.</div>
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

const td: React.CSSProperties = {
  padding: '10px 16px', borderBottom: '1px solid var(--border-subtle)',
};
