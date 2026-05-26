import { useState } from 'react';
import { Download, Package, Box } from 'lucide-react';
import { UpdateProgressModal } from '../modals/UpdateProgressModal';
import type { VersionInfo } from '../types';

interface Props {
  info: VersionInfo | null;
  onCompleted: (target: 'app' | 'webup', from: string, to: string) => void;
}

export function UpdateBanner({ info, onCompleted }: Props) {
  const [target, setTarget] = useState<'app' | 'webup' | null>(null);

  if (!info) return null;
  const appAvail = info.app?.newer && !!info.app?.latest;
  const botAvail = info.webup?.newer && !!info.webup?.latest;
  if (!appAvail && !botAvail) return null;

  const appDisabled = !info.can_update_app;
  const botDisabled = !info.can_update_webup;

  const btn = (
    key: 'app' | 'webup', label: string, from: string, to: string,
    Icon: typeof Download, disabled = false, tip?: string,
  ) => (
    <button
      key={key}
      onClick={() => !disabled && setTarget(key)}
      title={disabled ? (tip || '') : `${from} → ${to}`}
      disabled={disabled}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        background: disabled ? 'transparent' : 'var(--blue-muted)',
        border: `1px solid ${disabled ? 'var(--border)' : 'rgba(59,130,246,0.35)'}`,
        borderRadius: 6, padding: '7px 10px',
        color: disabled ? 'var(--fg-4)' : 'var(--blue-bright)',
        fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        marginBottom: 6,
      }}
    >
      <Icon size={13} />
      <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9,
        color: disabled ? 'var(--fg-4)' : 'var(--blue)',
        padding: '1px 5px', borderRadius: 4,
        background: 'var(--bg-card)',
      }}>{to}</span>
    </button>
  );

  return (
    <>
      <div style={{
        padding: '10px 14px 6px', borderTop: '1px solid var(--border-subtle)',
      }}>
        <div style={{
          fontSize: 10, fontWeight: 600, color: 'var(--blue-bright)',
          letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
          fontFamily: 'var(--font-display)', marginBottom: 8,
          display: 'flex', alignItems: 'center', gap: 5,
        }}>
          <Download size={10} /> Update available
        </div>
        {appAvail && info.app.latest && btn(
          'app', 'App', info.app.current || '–', info.app.latest, Box,
          appDisabled, 'systemd unit not available in this environment',
        )}
        {botAvail && info.webup.latest && btn(
          'webup', 'Unit3DWebUp', info.webup.current || '–',
          info.webup.latest, Package, botDisabled,
          'unit3dwebup.service or WEBUP_REPO_PATH not configured',
        )}
      </div>
      {target && (
        <UpdateProgressModal
          target={target}
          onClose={() => setTarget(null)}
          onCompleted={onCompleted}
        />
      )}
    </>
  );
}
