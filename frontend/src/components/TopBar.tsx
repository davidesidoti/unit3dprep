import { Search as SearchIcon, UploadCloud } from 'lucide-react';

const TITLES: Record<string, string> = {
  queue: 'Upload Queue',
  upload: 'New Upload',
  library: 'Media Library',
  uploaded: 'Upload History',
  search: 'Search Tracker',
  settings: 'Configuration',
  logs: 'Activity Log',
};

interface Props {
  activeView: string;
  onUploadClick: () => void;
  queueFilter: string;
  onQueueFilterChange: (v: string) => void;
}

export function TopBar({ activeView, onUploadClick, queueFilter, onQueueFilterChange }: Props) {
  const showQueueFilter = activeView === 'queue';
  return (
    <div style={{
      height: 52, background: '#0a0c12',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 24px', flexShrink: 0,
    }}>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: 15,
        fontWeight: 600, color: 'var(--fg-1)',
      }}>{TITLES[activeView] ?? 'Unit3Dup'}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {showQueueFilter && (
          <div style={{ position: 'relative' }}>
            <span style={{
              position: 'absolute', left: 8, top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--fg-3)', pointerEvents: 'none',
              display: 'flex',
            }}>
              <SearchIcon size={13} />
            </span>
            <input
              value={queueFilter}
              onChange={(e) => onQueueFilterChange(e.target.value)}
              placeholder="Filter torrents…"
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)', borderRadius: 6,
                padding: '5px 10px 5px 30px', fontSize: 12,
                color: 'var(--fg-2)', width: 200,
                fontFamily: 'var(--font-display)',
              }}
            />
          </div>
        )}
        <button
          onClick={onUploadClick}
          style={{
            background: 'var(--blue)', color: '#fff', border: 'none',
            borderRadius: 6, padding: '6px 14px', fontSize: 12,
            fontWeight: 600, cursor: 'pointer',
            fontFamily: 'var(--font-display)',
            display: 'flex', alignItems: 'center', gap: 6,
            transition: 'background 150ms',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--blue-bright)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--blue)')}
        >
          <UploadCloud size={13} /> Upload
        </button>
      </div>
    </div>
  );
}
