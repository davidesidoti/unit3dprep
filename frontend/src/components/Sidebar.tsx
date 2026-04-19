import { useEffect, useState } from 'react';
import {
  List, Library, CheckCircle, UploadCloud, Search, Settings, Terminal, LogOut,
} from 'lucide-react';
import { api } from '../api';
import type { TrackerStatus } from '../types';

const NAV = [
  { id: 'queue',    icon: List,         label: 'Queue' },
  { id: 'library',  icon: Library,      label: 'Media Library' },
  { id: 'uploaded', icon: CheckCircle,  label: 'Upload History' },
  { id: 'upload',   icon: UploadCloud,  label: 'Quick Upload' },
  { id: 'search',   icon: Search,       label: 'Search' },
  { id: 'settings', icon: Settings,     label: 'Settings' },
  { id: 'logs',     icon: Terminal,     label: 'Logs' },
] as const;

interface Props {
  activeView: string;
  setActiveView: (v: any) => void;
}

export function Sidebar({ activeView, setActiveView }: Props) {
  const [trackers, setTrackers] = useState<TrackerStatus[]>([
    { name: 'ITT', online: false },
    { name: 'PTT', online: false },
    { name: 'SIS', online: false },
  ]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await api.get<{ trackers: TrackerStatus[] }>('/api/trackers/status');
        if (!cancelled) setTrackers(r.trackers);
      } catch { /* ignore */ }
    };
    tick();
    const iv = window.setInterval(tick, 60_000);
    return () => { cancelled = true; window.clearInterval(iv); };
  }, []);

  const logout = async () => {
    try { await api.post('/api/auth/logout'); } finally {
      window.dispatchEvent(new CustomEvent('app:unauthenticated'));
    }
  };

  return (
    <div style={{
      width: 220, minHeight: '100vh', background: '#07080b',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div style={{ padding: '20px 18px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700,
          color: 'var(--fg-1)', letterSpacing: 'var(--tracking-tight)',
        }}>
          Unit3<span style={{ color: 'var(--blue)' }}>Dup</span>
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--fg-3)', marginTop: 2,
        }}>v0.2.0</div>
      </div>

      <nav style={{ padding: '12px 8px', flex: 1 }}>
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = activeView === item.id;
          return (
            <div
              key={item.id}
              onClick={() => setActiveView(item.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 10px', borderRadius: 6, marginBottom: 2,
                cursor: 'pointer', transition: 'all 150ms ease',
                background: active ? 'var(--blue-muted)' : 'transparent',
                color: active ? 'var(--blue-bright)' : 'var(--fg-3)',
                fontFamily: 'var(--font-display)',
                fontSize: 13, fontWeight: active ? 600 : 500,
                border: active
                  ? '1px solid rgba(59,130,246,0.2)'
                  : '1px solid transparent',
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.background = 'var(--bg-card)';
                  (e.currentTarget as HTMLElement).style.color = 'var(--fg-2)';
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.background = 'transparent';
                  (e.currentTarget as HTMLElement).style.color = 'var(--fg-3)';
                }
              }}
            >
              <Icon size={15} />
              {item.label}
            </div>
          );
        })}
      </nav>

      <div style={{ padding: '12px 18px 10px', borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{
          fontSize: 10, fontWeight: 600, color: 'var(--fg-4)',
          letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
          fontFamily: 'var(--font-display)', marginBottom: 8,
        }}>Trackers</div>
        {trackers.filter((t) => t.configured !== false).map((t) => (
          <div key={t.name} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 6,
          }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)',
            }}>{t.name}</span>
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 9999,
              background: t.online ? 'var(--green-dim)' : 'var(--red-dim)',
              color: t.online ? 'var(--green)' : 'var(--red)',
              fontFamily: 'var(--font-display)',
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <span style={{
                width: 5, height: 5, borderRadius: '50%',
                background: t.online ? 'var(--green)' : 'var(--red)',
                display: 'inline-block',
              }} />
              {t.online ? 'Online' : 'Offline'}
            </span>
          </div>
        ))}
        <button
          onClick={logout}
          style={{
            marginTop: 10, width: '100%', background: 'transparent',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '6px 10px', cursor: 'pointer',
            color: 'var(--fg-3)', fontSize: 11, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 6,
            justifyContent: 'center',
          }}
        ><LogOut size={12} /> Logout</button>
      </div>
    </div>
  );
}
