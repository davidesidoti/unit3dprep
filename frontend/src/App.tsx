import { useEffect, useState } from 'react';
import { api } from './api';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { LibraryView } from './views/LibraryView';
import { QueueView } from './views/QueueView';
import { UploadedView } from './views/UploadedView';
import { SearchView } from './views/SearchView';
import { SettingsView } from './views/SettingsView';
import { LogsView } from './views/LogsView';
import { LoginView } from './views/LoginView';
import { UploadModal } from './modals/UploadModal';
import { WizardModal } from './modals/WizardModal';
import { ChangelogModal } from './modals/ChangelogModal';
import type { WizardCtx, VersionInfo } from './types';

type View =
  | 'queue' | 'library' | 'uploaded' | 'upload'
  | 'search' | 'settings' | 'logs';

const VALID_VIEWS: View[] = ['queue', 'library', 'uploaded', 'search', 'settings', 'logs'];
const STORAGE_KEY = 'u3d_view';

export function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [view, setView] = useState<View>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as View | null;
    return stored && VALID_VIEWS.includes(stored) ? stored : 'library';
  });
  const [showUpload, setShowUpload] = useState(false);
  const [wizardCtx, setWizardCtx] = useState<WizardCtx | null>(null);
  const [queueFilter, setQueueFilter] = useState('');
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [pendingChangelog, setPendingChangelog] = useState<
    { target: 'app' | 'unit3dup'; from: string; to: string } | null
  >(null);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    api.get<{ authenticated: boolean }>('/api/me')
      .then((r) => setAuthed(r.authenticated))
      .catch(() => setAuthed(false));
    const onUnauth = () => setAuthed(false);
    window.addEventListener('app:unauthenticated', onUnauth);
    return () => window.removeEventListener('app:unauthenticated', onUnauth);
  }, []);

  useEffect(() => {
    if (view !== 'upload') localStorage.setItem(STORAGE_KEY, view);
  }, [view]);

  useEffect(() => {
    if (!authed) return;
    let cancelled = false;
    const fetchVersion = async () => {
      try {
        const v = await api.get<VersionInfo>('/api/version/info');
        if (!cancelled) setVersionInfo(v);
      } catch { /* ignore */ }
    };
    fetchVersion();
    const iv = window.setInterval(fetchVersion, 15 * 60_000);
    return () => { cancelled = true; window.clearInterval(iv); };
  }, [authed]);

  useEffect(() => {
    if (!authed) return;
    try {
      const raw = localStorage.getItem('itatorrents.pendingChangelog');
      if (!raw) return;
      const j = JSON.parse(raw);
      if (j && j.target && j.to) {
        setPendingChangelog({ target: j.target, from: j.from || '', to: j.to });
      }
    } catch { /* noop */ }
    localStorage.removeItem('itatorrents.pendingChangelog');
  }, [authed]);

  if (authed === null) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', color: 'var(--fg-3)', fontFamily: 'var(--font-mono)',
      }}>loading…</div>
    );
  }

  if (!authed) return <LoginView onLoggedIn={() => setAuthed(true)} />;

  const handleSetView = (v: View) => {
    setDrawerOpen(false);
    if (v === 'upload') { setShowUpload(true); return; }
    setView(v);
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', position: 'relative' }}>
      <Sidebar
        activeView={view}
        setActiveView={handleSetView}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
        versionInfo={versionInfo}
        onUpdateCompleted={(target, from, to) => setPendingChangelog({ target, from, to })}
      />
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        overflow: 'hidden', background: 'var(--bg-surface)', minWidth: 0,
      }}>
        <TopBar
          activeView={view}
          onUploadClick={() => setShowUpload(true)}
          queueFilter={queueFilter}
          onQueueFilterChange={setQueueFilter}
          isMobile={isMobile}
          onMenuClick={() => setDrawerOpen(true)}
        />
        <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          {view === 'queue' && <QueueView nameFilter={queueFilter} />}
          {view === 'library' && <LibraryView onStartWizard={setWizardCtx} isMobile={isMobile} />}
          {view === 'uploaded' && <UploadedView />}
          {view === 'search' && <SearchView />}
          {view === 'settings' && <SettingsView isMobile={isMobile} />}
          {view === 'logs' && <LogsView />}
        </div>
      </div>
      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
      {wizardCtx && <WizardModal ctx={wizardCtx} onClose={() => setWizardCtx(null)} />}
      {pendingChangelog && (
        <ChangelogModal
          target={pendingChangelog.target}
          from={pendingChangelog.from}
          to={pendingChangelog.to}
          onClose={() => setPendingChangelog(null)}
        />
      )}
    </div>
  );
}
