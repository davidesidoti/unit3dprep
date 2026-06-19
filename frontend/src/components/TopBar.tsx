import { Menu, Search as SearchIcon, UploadCloud } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LangSwitcher } from './LangSwitcher';

interface Props {
  activeView: string;
  onUploadClick: () => void;
  queueFilter: string;
  onQueueFilterChange: (v: string) => void;
  isMobile?: boolean;
  onMenuClick?: () => void;
}

export function TopBar({
  activeView, onUploadClick, queueFilter, onQueueFilterChange, isMobile, onMenuClick,
}: Props) {
  const { t } = useTranslation();
  const TITLES: Record<string, string> = {
    queue: t('topbar.queue'),
    upload: t('topbar.upload'),
    library: t('topbar.library'),
    uploaded: t('topbar.uploaded'),
    search: t('topbar.search'),
    reseed: t('topbar.reseed'),
    settings: t('topbar.settings'),
    logs: t('topbar.logs'),
  };
  const showQueueFilter = activeView === 'queue' && !isMobile;
  return (
    <div style={{
      height: 52, background: '#0a0c12',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: isMobile ? '0 12px' : '0 24px', flexShrink: 0, gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        {isMobile && (
          <button
            onClick={onMenuClick}
            aria-label={t('topbar.openMenu')}
            style={{
              background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 6, color: 'var(--fg-2)', cursor: 'pointer',
              padding: '7px 9px', display: 'flex',
              alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}
          ><Menu size={16} /></button>
        )}
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: 15,
          fontWeight: 600, color: 'var(--fg-1)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{TITLES[activeView] ?? t('topbar.default')}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <LangSwitcher />
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
              placeholder={t('topbar.filterTorrents')}
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
          className="u3d-pressable"
          style={{
            background: 'var(--blue)', color: '#fff', border: 'none',
            borderRadius: 6, padding: '6px 14px', fontSize: 12,
            fontWeight: 600, cursor: 'pointer',
            fontFamily: 'var(--font-display)',
            display: 'flex', alignItems: 'center', gap: 6,
            transition: 'background 150ms, transform var(--dur-fast) var(--ease-out)',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--blue-bright)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--blue)')}
        >
          <UploadCloud size={13} />{!isMobile && t('topbar.uploadBtn')}
        </button>
      </div>
    </div>
  );
}
