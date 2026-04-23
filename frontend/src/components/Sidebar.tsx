import { useEffect, useState } from 'react';
import {
  List, Library, CheckCircle, UploadCloud, Search, Settings, Terminal, LogOut, X,
} from 'lucide-react';
import { api } from '../api';
import type { TrackerStatus, VersionInfo } from '../types';
import { UpdateBanner } from './UpdateBanner';

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
  isMobile?: boolean;
  drawerOpen?: boolean;
  onCloseDrawer?: () => void;
  versionInfo?: VersionInfo | null;
  onUpdateCompleted?: (target: 'app' | 'unit3dup', from: string, to: string) => void;
}

export function Sidebar({
  activeView, setActiveView, isMobile, drawerOpen, onCloseDrawer,
  versionInfo, onUpdateCompleted,
}: Props) {
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

  const sidebarMobile = isMobile
    ? {
        position: 'fixed' as const, top: 0, left: 0, bottom: 0, zIndex: 201,
        transform: drawerOpen ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform 200ms ease',
        boxShadow: drawerOpen ? '0 0 40px rgba(0,0,0,0.7)' : 'none',
      }
    : {};

  return (
    <>
    {isMobile && drawerOpen && (
      <div
        onClick={onCloseDrawer}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.5)',
          animation: 'u3d-fade-in 180ms ease',
        }}
      />
    )}
    <div style={{
      width: 220, minHeight: '100vh', background: '#07080b',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
      ...sidebarMobile,
    }}>
      <div style={{
        padding: '20px 18px 16px', borderBottom: '1px solid var(--border-subtle)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700,
            color: 'var(--fg-1)', letterSpacing: 'var(--tracking-tight)',
          }}>
            Unit3<span style={{ color: 'var(--blue)' }}>Dup</span>
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            color: 'var(--fg-3)', marginTop: 2,
          }}>{versionInfo?.app?.current ? `v${versionInfo.app.current}` : '—'}</div>
        </div>
        {isMobile && (
          <button
            onClick={onCloseDrawer}
            aria-label="Close menu"
            style={{
              background: 'transparent', border: 'none', color: 'var(--fg-3)',
              cursor: 'pointer', padding: 6, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
            }}
          ><X size={18} /></button>
        )}
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

      <UpdateBanner
        info={versionInfo || null}
        onCompleted={(target, from, to) => onUpdateCompleted?.(target, from, to)}
      />
      <div style={{ padding: '12px 18px 10px', borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{
          fontSize: 10, fontWeight: 600, color: 'var(--fg-4)',
          letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
          fontFamily: 'var(--font-display)', marginBottom: 8,
        }}>Trackers</div>
        {trackers.map((t) => {
          const unconfigured = t.configured === false;
          const bg = unconfigured ? 'var(--border)' : t.online ? 'var(--green-dim)' : 'var(--red-dim)';
          const fg = unconfigured ? 'var(--fg-4)' : t.online ? 'var(--green)' : 'var(--red)';
          const dot = unconfigured ? 'var(--fg-4)' : t.online ? 'var(--green)' : 'var(--red)';
          const label = unconfigured ? 'Not set' : t.online ? 'Online' : 'Offline';
          return (
            <div key={t.name} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 6,
            }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                color: unconfigured ? 'var(--fg-4)' : 'var(--fg-2)',
              }}>{t.name}</span>
              <span style={{
                fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 9999,
                background: bg, color: fg,
                fontFamily: 'var(--font-display)',
                display: 'flex', alignItems: 'center', gap: 4,
              }}>
                <span style={{
                  width: 5, height: 5, borderRadius: '50%',
                  background: dot, display: 'inline-block',
                }} />
                {label}
              </span>
            </div>
          );
        })}
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
    </>
  );
}
