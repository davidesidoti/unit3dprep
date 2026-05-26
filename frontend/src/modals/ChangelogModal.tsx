import { useEffect, useState } from 'react';
import { X, Sparkles, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';

interface Release {
  version: string;
  name?: string;
  body: string;
  html_url?: string;
  published_at?: string;
}

interface Props {
  target: 'app' | 'webup';
  from: string;
  to: string;
  onClose: () => void;
}

export function ChangelogModal({ target, from, to, onClose }: Props) {
  const { t } = useTranslation();
  const [release, setRelease] = useState<Release | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (target !== 'app') { setLoading(false); return; }
    api.get<Release>(`/api/version/changelog?v=${encodeURIComponent(to)}`)
      .then((r) => setRelease(r))
      .catch((e) => setError(e.message || t('changelog.unavailable')))
      .finally(() => setLoading(false));
  }, [target, to, t]);

  const title = target === 'app' ? t('changelog.appUpdated') : t('changelog.webupUpdated');

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 16,
      }}
    >
      <div style={{
        background: 'var(--bg-surface)', borderRadius: 10,
        border: '1px solid var(--border)', width: '100%', maxWidth: 640,
        maxHeight: '85vh', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14,
            color: 'var(--fg-1)', display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <Sparkles size={14} color="var(--blue-bright)" />
            {title}
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none',
              color: 'var(--fg-3)', cursor: 'pointer', padding: 4,
            }}
          ><X size={16} /></button>
        </div>

        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontFamily: 'var(--font-mono)', fontSize: 12,
            color: 'var(--fg-2)',
          }}>
            <span style={{
              padding: '2px 8px', borderRadius: 4, background: 'var(--border)',
              color: 'var(--fg-3)',
            }}>{from || '–'}</span>
            <span style={{ color: 'var(--fg-4)' }}>→</span>
            <span style={{
              padding: '2px 8px', borderRadius: 4,
              background: 'var(--blue-muted)', color: 'var(--blue-bright)',
              fontWeight: 600,
            }}>{to}</span>
          </div>
        </div>

        <div style={{
          flex: 1, overflow: 'auto', padding: '14px 18px',
          fontFamily: 'var(--font-mono)', fontSize: 12,
          color: 'var(--fg-2)', lineHeight: 1.6,
        }}>
          {loading && <div style={{ color: 'var(--fg-4)' }}>{t('changelog.loading')}</div>}
          {!loading && target !== 'app' && (
            <div style={{ color: 'var(--fg-3)' }}>
              {t('changelog.webupUpdatedTo')} <b>{to}</b>. {t('changelog.seeWebupRepo')}.
            </div>
          )}
          {!loading && target === 'app' && error && (
            <div style={{ color: 'var(--fg-3)' }}>
              {t('changelog.unavailable')} ({error}).
            </div>
          )}
          {!loading && target === 'app' && release && (
            <>
              {release.name && release.name !== to && (
                <div style={{
                  fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700,
                  color: 'var(--fg-1)', marginBottom: 10,
                }}>{release.name}</div>
              )}
              <pre style={{
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                margin: 0, fontFamily: 'inherit',
              }}>{release.body || t('changelog.noNotes')}</pre>
              {release.html_url && (
                <a
                  href={release.html_url}
                  target="_blank" rel="noreferrer"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    marginTop: 16, color: 'var(--blue-bright)',
                    fontFamily: 'var(--font-display)', fontSize: 12,
                    textDecoration: 'none',
                  }}
                >
                  <ExternalLink size={12} /> {t('changelog.openOnGithub')}
                </a>
              )}
            </>
          )}
        </div>

        <div style={{
          padding: '12px 18px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', justifyContent: 'flex-end',
        }}>
          <button
            onClick={onClose}
            style={{
              background: 'var(--blue-muted)', border: '1px solid rgba(59,130,246,0.35)',
              color: 'var(--blue-bright)', padding: '6px 16px', borderRadius: 6,
              cursor: 'pointer', fontFamily: 'var(--font-display)',
              fontSize: 12, fontWeight: 600,
            }}
          >{t('common.ok')}</button>
        </div>
      </div>
    </div>
  );
}
