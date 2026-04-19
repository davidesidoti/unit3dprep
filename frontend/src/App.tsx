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
import type { WizardCtx } from './types';

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
    if (v === 'upload') { setShowUpload(true); return; }
    setView(v);
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar activeView={view} setActiveView={handleSetView} />
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        overflow: 'hidden', background: 'var(--bg-surface)',
      }}>
        <TopBar
          activeView={view}
          onUploadClick={() => setShowUpload(true)}
          queueFilter={queueFilter}
          onQueueFilterChange={setQueueFilter}
        />
        <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          {view === 'queue' && <QueueView nameFilter={queueFilter} />}
          {view === 'library' && <LibraryView onStartWizard={setWizardCtx} />}
          {view === 'uploaded' && <UploadedView />}
          {view === 'search' && <SearchView />}
          {view === 'settings' && <SettingsView />}
          {view === 'logs' && <LogsView />}
        </div>
      </div>
      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
      {wizardCtx && <WizardModal ctx={wizardCtx} onClose={() => setWizardCtx(null)} />}
    </div>
  );
}
