import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { UploadedRecord } from '../types';

const kindColors: Record<string, { bg: string; fg: string }> = {
  movie:   { bg: 'var(--blue-dim)',   fg: 'var(--blue-bright)' },
  episode: { bg: '#2a1d5a',           fg: '#a78bfa' },
  series:  { bg: 'var(--green-dim)',  fg: 'var(--green)' },
};

export function UploadedView() {
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

  const stats = {
    total: records.length,
    success: records.filter((r) => r.unit3dup_exit_code === 0 && !r.hardlink_only).length,
    failed: records.filter((r) => r.unit3dup_exit_code !== null && r.unit3dup_exit_code !== 0).length,
    manual: records.filter((r) => r.hardlink_only).length,
  };

  const del = async (id: number) => {
    if (!confirm('Delete this record?')) return;
    try { await api.del(`/api/uploaded/${id}`); load(); } catch { /* ignore */ }
  };

  return (
    <div style={{
      padding: '18px 22px', display: 'flex', flexDirection: 'column',
      gap: 14, height: '100%', minHeight: 0, overflow: 'auto',
    }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        <StatCard value={stats.total} label="Total uploads" />
        <StatCard value={stats.success} label="Successful" color="var(--green)" />
        <StatCard value={stats.failed} label="Failed" color="var(--red)" />
        <StatCard value={stats.manual} label="Hardlink only" color="var(--yellow)" />
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
          >{k[0].toUpperCase() + k.slice(1)}</button>
        ))}
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search history…"
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
        borderRadius: 8, overflowX: 'hidden', overflowY: 'auto',
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 90px 180px 100px 140px' }}>
          {['Kind', 'Title / Final Name', 'TMDB', 'Uploaded', 'Status', 'Actions'].map((h) => (
            <div key={h} style={th}>{h}</div>
          ))}
        </div>
        {filtered.map((r) => {
          const c = kindColors[r.kind] ?? kindColors.movie;
          const expanded = selected === r.id;
          return (
            <div key={r.id}>
              <div
                onClick={() => setSelected(expanded ? null : r.id)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '80px 1fr 90px 180px 100px 140px',
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
                  {r.hardlink_only
                    ? <span style={{ color: 'var(--yellow)', fontWeight: 600 }}>manual</span>
                    : r.unit3dup_exit_code === 0
                      ? <span style={{ color: 'var(--green)', fontWeight: 600 }}>✓ exit 0</span>
                      : r.unit3dup_exit_code === null
                        ? <span style={{ color: 'var(--yellow)' }}>pending</span>
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
                  >Delete</button>
                </div>
              </div>
              {expanded && (
                <div style={{
                  padding: '14px 18px', background: 'var(--bg-base)',
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  <div style={{
                    display: 'grid', gridTemplateColumns: '140px 1fr',
                    gap: 8, fontSize: 11, fontFamily: 'var(--font-mono)',
                    lineHeight: 1.8,
                  }}>
                    <KV k="ID" v={r.id} />
                    <KV k="Category" v={r.category} />
                    <KV k="Source path" v={r.source_path} />
                    <KV k="Seeding path" v={r.seeding_path} />
                    <KV k="Final name" v={r.final_name} color="var(--blue-bright)" />
                    <KV k="TMDB ID" v={r.tmdb_id || '—'} />
                    <KV k="Uploaded at" v={r.uploaded_at} />
                    <KV k="unit3dup exit" v={r.unit3dup_exit_code ?? 'pending'}
                        color={r.unit3dup_exit_code === 0 ? 'var(--green)'
                          : r.unit3dup_exit_code ? 'var(--red)' : 'var(--yellow)'} />
                    <KV k="Hardlink only" v={r.hardlink_only ? 'yes' : 'no'} />
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && (
          <div style={{
            padding: '40px 20px', textAlign: 'center',
            color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 12,
          }}>No upload history matches.</div>
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
