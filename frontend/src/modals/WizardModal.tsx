import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, openSSE } from '../api';
import type { WizardCtx } from '../types';

type StepId = 'audio' | 'tmdb' | 'names' | 'duplicate' | 'hardlink' | 'upload';

const STEPS: { id: StepId; labelKey: string; icon: string }[] = [
  { id: 'audio',    labelKey: 'wizard.stepAudio',    icon: '🎧' },
  { id: 'tmdb',     labelKey: 'wizard.stepTmdb',     icon: '🎬' },
  { id: 'names',    labelKey: 'wizard.stepNames',    icon: '✎' },
  { id: 'hardlink', labelKey: 'wizard.stepHardlink', icon: '⇢' },
  { id: 'upload',   labelKey: 'wizard.stepUpload',   icon: '⬆' },
];

type DuplicateInfo = {
  id?: string | number;
  name?: string;
  size?: number;
  type?: string;
  resolution?: string;
  category?: string;
  uploader?: string;
  seeders?: number;
  leechers?: number;
  created_at?: string;
  details_link?: string;
  tmdb_id?: number;
};

export function WizardModal({ ctx, onClose }: { ctx: WizardCtx; onClose: (completed?: boolean) => void }) {
  const { t } = useTranslation();
  const [token, setToken] = useState<string | null>(null);
  const [step, setStep] = useState<StepId>('audio');
  const [startError, setStartError] = useState('');
  const [duplicate, setDuplicate] = useState<DuplicateInfo | null>(null);

  useEffect(() => {
    api.post<{ token: string }>('/api/wizard/start', {
      path: ctx.path,
      category: ctx.category,
      kind: ctx.kind,
      tmdb_id: ctx.tmdbId ?? '',
      tmdb_kind: ctx.kind === 'movie' ? 'movie' : 'tv',
      hardlink_only: false,
    })
      .then((r) => setToken(r.token))
      .catch((e) => setStartError(e.message || 'failed'));
  }, [ctx]);

  const kindLabel = {
    movie:   t('wizard.kindMovie'),
    episode: t('wizard.kindEpisode'),
    series:  ctx.season ? t('wizard.kindBulkSeason') : t('wizard.kindSeries'),
  }[ctx.kind];

  // 'duplicate' is a transient sub-step of 'names' — keep the stepper showing
  // names as active when we're presenting the duplicate-found panel.
  const stepperStep: StepId = step === 'duplicate' ? 'names' : step;
  const idx = STEPS.findIndex((s) => s.id === stepperStep);

  return (
    <div className="u3d-overlay-in" style={{
      position: 'fixed', inset: 0, background: 'rgba(2,4,8,0.85)',
      zIndex: 100, display: 'flex', alignItems: 'center',
      justifyContent: 'center', padding: 20,
    }}>
      <div className="u3d-modal-in" style={{
        width: 'min(820px, 100%)', maxHeight: '92vh',
        background: '#0a0c12', border: '1px solid var(--border)',
        borderRadius: 10, display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div>
            <div style={{
              fontSize: 15, fontWeight: 700, color: 'var(--fg-1)',
              fontFamily: 'var(--font-display)',
            }}>{t('wizard.title')}</div>
            <div style={{
              fontSize: 11, color: 'var(--fg-3)',
              fontFamily: 'var(--font-mono)', marginTop: 2,
            }}>
              {kindLabel} · {ctx.title || ctx.name}
              {ctx.season && ` · S${String(ctx.season.n).padStart(2, '0')}`}
            </div>
          </div>
          <button
            onClick={() => onClose()}
            style={{
              marginLeft: 'auto', background: 'transparent', border: 'none',
              color: 'var(--fg-3)', cursor: 'pointer', fontSize: 20,
              lineHeight: 1, padding: 4,
            }}
          >×</button>
        </div>

        <div style={{
          display: 'flex', padding: '0 20px', gap: 2,
          borderBottom: '1px solid var(--border-subtle)',
          background: 'var(--bg-base)',
        }}>
          {STEPS.map((s, i) => {
            const active = s.id === step;
            const reached = i <= idx;
            return (
              <div key={s.id} style={{
                flex: 1, padding: '10px 6px', textAlign: 'center',
                fontSize: 10, fontWeight: 700,
                letterSpacing: 'var(--tracking-wide)', textTransform: 'uppercase',
                color: active ? 'var(--blue)' : reached ? 'var(--fg-2)' : 'var(--fg-4)',
                borderBottom: active ? '2px solid var(--blue)' : '2px solid transparent',
                fontFamily: 'var(--font-display)',
              }}>
                <span style={{ marginRight: 5 }}>{s.icon}</span>{t(s.labelKey)}
              </div>
            );
          })}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {startError && (
            <div style={{
              padding: 20, color: 'var(--red)',
              fontFamily: 'var(--font-mono)',
            }}>{startError}</div>
          )}
          {!token && !startError && (
            <div style={{
              padding: 40, textAlign: 'center', color: 'var(--fg-3)',
            }}>{t('wizard.starting')}</div>
          )}
          {token && step === 'audio' && (
            <AudioStep
              token={token}
              onNext={() => setStep('tmdb')}
              onOverride={() => setStep('tmdb')}
            />
          )}
          {token && step === 'tmdb' && (
            <TmdbStep token={token} ctx={ctx} onNext={() => setStep('names')} />
          )}
          {token && step === 'names' && (
            <NamesStep
              token={token}
              onNext={async () => {
                try {
                  const r = await api.post<{ enabled: boolean; duplicate: DuplicateInfo | null }>(
                    `/api/wizard/${token}/duplicate-check`,
                  );
                  if (r.duplicate) {
                    setDuplicate(r.duplicate);
                    setStep('duplicate');
                  } else {
                    setStep('hardlink');
                  }
                } catch {
                  // On API failure proceed: dup check is best-effort.
                  setStep('hardlink');
                }
              }}
            />
          )}
          {token && step === 'duplicate' && duplicate && (
            <DuplicateStep
              token={token}
              duplicate={duplicate}
              onContinue={() => setStep('hardlink')}
              onCancel={onClose}
            />
          )}
          {token && step === 'hardlink' && (
            <HardlinkStep
              token={token}
              onNext={() => setStep('upload')}
              onFinishOnly={() => onClose(true)}
            />
          )}
          {token && step === 'upload' && (
            <UploadStep token={token} onClose={() => onClose(true)} />
          )}
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- Steps

function AudioStep({ token, onNext, onOverride }: {
  token: string; onNext: () => void; onOverride: () => void;
}) {
  const { t } = useTranslation();
  const [files, setFiles] = useState<{ name: string; ok?: boolean; error?: string }[]>([]);
  const [done, setDone] = useState(false);
  const [allOk, setAllOk] = useState(false);

  useEffect(() => {
    const close = openSSE(`/api/wizard/${token}/audio`, {
      onEvent: (name, data) => {
        if (name === 'file_result') {
          try {
            const r = JSON.parse(data);
            setFiles((list) => [...list, { name: r.file, ok: r.ok, error: r.error }]);
          } catch {/* */}
        } else if (name === 'done') {
          try { setAllOk(JSON.parse(data).all_ok); } catch {/* */}
          setDone(true); close();
        }
      },
    });
    return close;
  }, [token]);

  const override = async () => {
    await api.post(`/api/wizard/${token}/audio-override`);
    onOverride();
  };

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 14, lineHeight: 1.6,
      }}>
        {t('wizard.audioDesc')}
      </div>
      <div style={{
        background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
        borderRadius: 6, maxHeight: 280, overflowY: 'auto',
      }}>
        {files.map((r, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '8px 12px',
            borderBottom: i < files.length - 1 ? '1px solid var(--border-subtle)' : 'none',
          }}>
            <div style={{
              width: 18, height: 18, borderRadius: 9,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: r.ok ? 'var(--green-dim)' : 'var(--red-dim)',
              color: r.ok ? 'var(--green)' : 'var(--red)',
              fontSize: 10, fontWeight: 700,
            }}>{r.ok ? '✓' : '✗'}</div>
            <span style={{
              flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11,
              color: 'var(--fg-1)',
            }}>{r.name}</span>
            <span style={{
              fontSize: 10, color: r.ok ? 'var(--green)' : 'var(--red)',
              fontFamily: 'var(--font-mono)',
            }}>{r.ok ? 'ITA ✓' : r.error || 'no ITA'}</span>
          </div>
        ))}
        {!files.length && !done && (
          <div style={{ padding: 14, color: 'var(--fg-3)' }}>{t('wizard.audioScanning')}</div>
        )}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
        {done && !allOk ? (
          <button
            onClick={override}
            style={{
              background: 'transparent', border: '1px solid var(--yellow)',
              color: 'var(--yellow)', padding: '8px 14px', borderRadius: 6,
              fontSize: 11, fontWeight: 600, cursor: 'pointer',
              fontFamily: 'var(--font-display)',
            }}
          >{t('wizard.audioOverride')}</button>
        ) : <span />}
        <button
          onClick={onNext}
          disabled={!allOk}
          className="u3d-pressable"
          style={{
            background: allOk ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: allOk ? '#fff' : 'var(--fg-3)',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: allOk ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >{t('wizard.audioNext')}</button>
      </div>
    </div>
  );
}

function TmdbStep({ token, ctx, onNext }: {
  token: string; ctx: WizardCtx; onNext: () => void;
}) {
  const { t } = useTranslation();
  const [tmdbId, setTmdbId] = useState(ctx.tmdbId ?? '');
  const [kind, setKind] = useState(ctx.kind === 'movie' ? 'movie' : 'tv');
  const [loading, setLoading] = useState(false);
  const [matched, setMatched] = useState<{
    title: string; year: string; poster: string; overview: string;
  } | null>(null);
  const [error, setError] = useState('');

  const lookup = async () => {
    setLoading(true); setError('');
    try {
      const r = await api.post<{ tmdb: any }>(`/api/wizard/${token}/tmdb`, {
        tmdb_id: tmdbId, tmdb_kind: kind,
      });
      setMatched(r.tmdb);
    } catch (e: any) {
      setError(e.message || 'lookup failed');
      setMatched(null);
    } finally { setLoading(false); }
  };

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 14,
      }}>{t('wizard.tmdbDesc')}</div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        <select
          value={kind}
          onChange={(e) => { setKind(e.target.value); setMatched(null); }}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '8px 10px', fontSize: 12,
            color: 'var(--fg-1)', fontFamily: 'var(--font-display)',
          }}
        >
          <option value="movie">Movie</option>
          <option value="tv">TV</option>
        </select>
        <input
          value={tmdbId}
          onChange={(e) => { setTmdbId(e.target.value); setMatched(null); }}
          placeholder={t('wizard.tmdbPlaceholder')}
          style={{
            flex: 1, background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '8px 12px', fontSize: 12,
            color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
          }}
        />
        <button
          onClick={lookup}
          disabled={!tmdbId || loading}
          className="u3d-pressable"
          style={{
            background: tmdbId && !loading ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: tmdbId && !loading ? '#fff' : 'var(--fg-3)',
            padding: '8px 16px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: tmdbId && !loading ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >{loading ? '…' : t('wizard.tmdbLookup')}</button>
      </div>
      {error && (
        <div style={{
          padding: 10, background: 'var(--red-dim)',
          border: '1px solid var(--red)', borderRadius: 6,
          color: 'var(--red)', fontFamily: 'var(--font-mono)', fontSize: 12,
          marginBottom: 12,
        }}>{error}</div>
      )}
      {matched && (
        <div className="u3d-animate-in" style={{
          display: 'flex', gap: 14, padding: 14,
          background: '#0a0c12', border: '1px solid var(--green-dim)',
          borderRadius: 6,
        }}>
          <div style={{
            width: 90, aspectRatio: '2/3', borderRadius: 4,
            background: matched.poster
              ? `url("${matched.poster}") center/cover, #1a2a4a`
              : '#1a2a4a',
            flexShrink: 0,
          }} />
          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 15, fontWeight: 700, color: 'var(--fg-1)',
              fontFamily: 'var(--font-display)',
            }}>{matched.title}</div>
            <div style={{
              fontSize: 11, color: 'var(--fg-3)',
              fontFamily: 'var(--font-mono)', marginTop: 2, marginBottom: 8,
            }}>{t('wizard.tmdbYear')} {matched.year} · TMDB {tmdbId} · {kind}</div>
            <div style={{
              fontSize: 11, color: 'var(--fg-2)', lineHeight: 1.5,
            }}>{matched.overview}</div>
            <div style={{
              marginTop: 8, fontSize: 10,
              fontFamily: 'var(--font-mono)', color: 'var(--green)',
            }}>{t('wizard.tmdbBilingual')}</div>
          </div>
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
        <button
          onClick={onNext}
          disabled={!matched}
          className="u3d-pressable"
          style={{
            background: matched ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: matched ? '#fff' : 'var(--fg-3)',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: matched ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >{t('wizard.tmdbNext')}</button>
      </div>
    </div>
  );
}

function NamesStep({ token, onNext }: { token: string; onNext: () => void; }) {
  const { t } = useTranslation();
  const [names, setNames] = useState<Record<string, string>>({});
  const [folder, setFolder] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<any>(`/api/wizard/${token}`).then((s) => {
      setNames(s.final_names || {});
      setFolder(s.folder_name || '');
      setLoading(false);
    });
  }, [token]);

  const submit = async () => {
    await api.post(`/api/wizard/${token}/names`, {
      final_names: names, folder_name: folder,
    });
    onNext();
  };

  if (loading) return <div style={{ padding: 30, color: 'var(--fg-3)' }}>{t('wizard.namesLoading')}</div>;

  const entries = Object.entries(names);

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 14, lineHeight: 1.6,
      }}>
        {t('wizard.namesDesc')}
        <span style={{ color: 'var(--yellow)' }}>{t('wizard.namesWarning')}</span>
      </div>
      {folder && (
        <div style={{ marginBottom: 12 }}>
          <label style={{
            fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: 'var(--tracking-wider)', color: 'var(--fg-4)',
            display: 'block', marginBottom: 4,
          }}>{t('wizard.namesFolderLabel')}</label>
          <input
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            style={{
              width: '100%', background: 'var(--bg-card)',
              border: '1px solid var(--border)', borderRadius: 6,
              padding: '7px 10px', fontSize: 11,
              color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
      )}
      <div style={{
        background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
        borderRadius: 6, maxHeight: 300, overflowY: 'auto',
      }}>
        {entries.map(([file, name], i) => (
          <div key={file} style={{
            padding: '8px 12px',
            borderBottom: i < entries.length - 1 ? '1px solid var(--border-subtle)' : 'none',
          }}>
            <div style={{
              fontSize: 10, color: 'var(--fg-4)',
              fontFamily: 'var(--font-mono)', marginBottom: 3,
            }}>{file.split(/[\\/]/).pop()} →</div>
            <input
              value={name}
              onChange={(e) =>
                setNames((ns) => ({ ...ns, [file]: e.target.value }))
              }
              style={{
                width: '100%', background: 'transparent', border: 'none',
                fontSize: 11, color: 'var(--fg-1)',
                fontFamily: 'var(--font-mono)', outline: 'none',
              }}
            />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
        <button
          onClick={submit}
          className="u3d-pressable"
          style={{
            background: 'var(--blue)', border: 'none', color: '#fff',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >{t('wizard.namesNext')}</button>
      </div>
    </div>
  );
}

function formatBytes(n: number | undefined | null): string {
  if (!n || n <= 0) return '—';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 2 : 1)} ${units[i]}`;
}

function DuplicateStep({ token, duplicate, onContinue, onCancel }: {
  token: string;
  duplicate: DuplicateInfo;
  onContinue: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const [skipping, setSkipping] = useState(false);

  const confirm = async () => {
    setConfirming(true);
    try {
      await api.post(`/api/wizard/${token}/duplicate-confirm`);
      onContinue();
    } finally {
      setConfirming(false);
    }
  };

  const cancel = async () => {
    setSkipping(true);
    try {
      await api.post(`/api/wizard/${token}/duplicate-skip`);
    } catch {
      // even if recording fails, close the wizard — user clearly doesn't want to upload
    } finally {
      setSkipping(false);
      onCancel();
    }
  };

  const busy = confirming || skipping;

  return (
    <div style={{ padding: '24px' }}>
      <div style={{
        background: 'rgba(234, 179, 8, 0.08)',
        border: '1px solid rgba(234, 179, 8, 0.35)',
        borderRadius: 8, padding: '14px 16px', marginBottom: 16,
      }}>
        <div style={{
          fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: 'var(--tracking-wider)', color: 'var(--yellow)',
          fontFamily: 'var(--font-display)', marginBottom: 6,
        }}>{t('wizard.duplicateTitle')}</div>
        <div style={{ fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
          {t('wizard.duplicateDesc')}
        </div>
      </div>

      <div style={{
        background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
        borderRadius: 8, padding: 16, fontFamily: 'var(--font-mono)', fontSize: 11,
      }}>
        <DupRow label={t('wizard.duplicateName')} value={duplicate.name || '—'} mono />
        <DupRow label={t('wizard.duplicateSize')} value={formatBytes(duplicate.size)} />
        <DupRow label={t('wizard.duplicateType')} value={
          [duplicate.type, duplicate.resolution].filter(Boolean).join(' · ') || '—'
        } />
        {duplicate.uploader && <DupRow label={t('wizard.duplicateUploader')} value={duplicate.uploader} />}
        <DupRow label={t('wizard.duplicateSeeders')} value={
          `${duplicate.seeders ?? 0} S · ${duplicate.leechers ?? 0} L`
        } />
        {duplicate.created_at && (
          <DupRow label={t('wizard.duplicateCreated')} value={
            new Date(duplicate.created_at).toLocaleString()
          } />
        )}
        {duplicate.details_link && (
          <div style={{ marginTop: 10 }}>
            <a
              href={duplicate.details_link}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--blue)', fontSize: 11, textDecoration: 'none' }}
            >{t('wizard.duplicateOpenLink')} ↗</a>
          </div>
        )}
      </div>

      <div style={{
        display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20,
      }}>
        <button
          onClick={cancel}
          disabled={busy}
          style={{
            background: 'transparent', border: '1px solid var(--border)',
            color: 'var(--fg-2)', padding: '8px 18px', borderRadius: 6,
            fontSize: 12, fontWeight: 600,
            cursor: busy ? 'not-allowed' : 'pointer',
            fontFamily: 'var(--font-display)', opacity: busy ? 0.5 : 1,
          }}
        >{skipping ? '…' : t('wizard.duplicateCancel')}</button>
        <button
          onClick={confirm}
          disabled={busy}
          style={{
            background: 'var(--yellow)', border: 'none', color: '#0a0c12',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 700,
            cursor: busy ? 'not-allowed' : 'pointer',
            fontFamily: 'var(--font-display)', opacity: busy ? 0.6 : 1,
          }}
        >{confirming ? '…' : t('wizard.duplicateContinue')}</button>
      </div>
    </div>
  );
}

function DupRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{
      display: 'flex', gap: 12, padding: '4px 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <span style={{
        color: 'var(--fg-4)', fontSize: 10, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-wider)', minWidth: 90,
        fontFamily: 'var(--font-display)',
      }}>{label}</span>
      <span style={{
        color: 'var(--fg-1)', flex: 1, wordBreak: 'break-all',
        fontFamily: mono ? 'var(--font-mono)' : 'inherit',
      }}>{value}</span>
    </div>
  );
}

function HardlinkStep({ token, onNext, onFinishOnly }: {
  token: string; onNext: () => void; onFinishOnly: () => void;
}) {
  const { t } = useTranslation();
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [seedingPath, setSeedingPath] = useState('');
  const [error, setError] = useState('');
  const [hardlinkOnly, setHardlinkOnly] = useState(false);
  const [state, setState] = useState<any | null>(null);

  useEffect(() => { api.get(`/api/wizard/${token}`).then(setState); }, [token]);

  const execute = async () => {
    setRunning(true); setError('');
    try {
      const r = await api.post<{ seeding_path: string }>(`/api/wizard/${token}/hardlink`);
      setSeedingPath(r.seeding_path);
      setDone(true);
    } catch (e: any) {
      setError(e.message || 'hardlink failed');
    } finally { setRunning(false); }
  };

  const finishOnly = async () => {
    await api.post(`/api/wizard/${token}/finish-hardlink`);
    onFinishOnly();
  };

  const count = Object.keys(state?.final_names ?? {}).length || 1;

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 14, lineHeight: 1.6,
      }}>
        {t('wizard.hardlinkAbout', { count })}
      </div>
      <div style={{
        background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
        borderRadius: 6, padding: 14, marginBottom: 14,
      }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '90px 1fr', gap: 8,
          fontSize: 11, fontFamily: 'var(--font-mono)',
        }}>
          <span style={{ color: 'var(--fg-3)' }}>{t('wizard.hardlinkSource')}</span>
          <span style={{ color: 'var(--fg-1)', wordBreak: 'break-all' }}>{state?.path}</span>
          <span style={{ color: 'var(--fg-3)' }}>{t('wizard.hardlinkFiles')}</span>
          <span style={{ color: 'var(--fg-1)' }}>{count}</span>
        </div>
      </div>
      <label style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14,
        cursor: 'pointer', fontSize: 12, color: 'var(--fg-2)',
        fontFamily: 'var(--font-display)',
      }}>
        <input
          type="checkbox"
          checked={hardlinkOnly}
          onChange={(e) => setHardlinkOnly(e.target.checked)}
          style={{ accentColor: 'var(--blue)' }}
        />
        {t('wizard.hardlinkOnlyLabel')}
      </label>
      {error && (
        <div style={{
          padding: 10, color: 'var(--red)',
          background: 'var(--red-dim)', borderRadius: 6,
          marginBottom: 10, fontFamily: 'var(--font-mono)', fontSize: 12,
        }}>{error}</div>
      )}
      {!done ? (
        <button
          onClick={execute}
          disabled={running}
          className="u3d-pressable"
          style={{
            width: '100%', background: running ? 'var(--border)' : 'var(--blue)',
            border: 'none', color: '#fff', padding: 10,
            borderRadius: 6, fontSize: 12, fontWeight: 600,
            cursor: running ? 'default' : 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >{running ? t('wizard.hardlinkLinking') : t('wizard.hardlinkExecute')}</button>
      ) : (
        <div style={{
          background: '#0a0c12', border: '1px solid var(--green-dim)',
          borderRadius: 6, padding: 12,
          color: 'var(--green)', fontSize: 12, fontFamily: 'var(--font-mono)',
          wordBreak: 'break-all',
        }}>{t('wizard.hardlinkDone', { path: seedingPath })}</div>
      )}
      {done && (
        <div style={{
          display: 'flex', justifyContent: 'flex-end', marginTop: 18, gap: 8,
        }}>
          {hardlinkOnly ? (
            <button
              onClick={finishOnly}
              className="u3d-pressable"
              style={{
                background: 'var(--green)', border: 'none', color: 'var(--bg-base)',
                padding: '8px 18px', borderRadius: 6, fontSize: 12,
                fontWeight: 700, cursor: 'pointer',
                fontFamily: 'var(--font-display)',
              }}
            >{t('wizard.hardlinkFinishOnly')}</button>
          ) : (
            <button
              onClick={onNext}
              className="u3d-pressable"
              style={{
                background: 'var(--blue)', border: 'none', color: '#fff',
                padding: '8px 18px', borderRadius: 6, fontSize: 12,
                fontWeight: 600, cursor: 'pointer',
                fontFamily: 'var(--font-display)',
              }}
            >{t('wizard.hardlinkRunUnit3dup')}</button>
          )}
        </div>
      )}
    </div>
  );
}

interface ProgressInfo { phase?: string; label?: string; pct: number; sub_pct?: number; }

const PHASES: { id: string; short: string }[] = [
  { id: 'setenv',      short: 'Setup' },
  { id: 'scan',        short: 'Scan' },
  { id: 'maketorrent', short: 'Torrent' },
  { id: 'upload',      short: 'Upload' },
  { id: 'seed',        short: 'Seed' },
];

function ProgressBar({ progress, done, success }: {
  progress: ProgressInfo | null; done: boolean; success: boolean;
}) {
  const pct = done ? 100 : Math.max(0, Math.min(100, progress?.pct ?? 0));
  const phaseIdx = progress?.phase ? PHASES.findIndex((p) => p.id === progress.phase) : -1;
  const barColor = done
    ? (success ? 'var(--green)' : 'var(--red)')
    : 'var(--blue-bright)';
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: 10, fontFamily: 'var(--font-display)', fontWeight: 600,
        marginBottom: 6, color: 'var(--fg-3)',
        letterSpacing: 'var(--tracking-wide)', textTransform: 'uppercase',
      }}>
        <span>
          {progress?.label || (done ? (success ? 'Completato' : 'Errore') : 'In avvio…')}
          {progress?.sub_pct !== undefined && progress.sub_pct > 0 && progress.sub_pct < 100 && !done && (
            <span style={{
              marginLeft: 8, color: 'var(--fg-4)', fontFamily: 'var(--font-mono)',
            }}>{progress.sub_pct.toFixed(0)}%</span>
          )}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div style={{
        height: 6, background: 'var(--bg-base)', borderRadius: 3,
        overflow: 'hidden', position: 'relative',
        border: '1px solid var(--border-subtle)',
      }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: barColor,
          transition: 'width 250ms ease-out',
          borderRadius: 3,
          position: 'relative', overflow: 'hidden',
        }}>
          {!done && pct > 0 && pct < 100 && <div className="u3d-shimmer-overlay" />}
        </div>
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', marginTop: 4,
        fontSize: 9, fontFamily: 'var(--font-display)', color: 'var(--fg-4)',
        letterSpacing: 'var(--tracking-wide)',
      }}>
        {PHASES.map((p, i) => {
          const reached = phaseIdx >= 0 && i <= phaseIdx;
          const current = phaseIdx === i && !done;
          return (
            <span key={p.id} style={{
              color: done && success ? 'var(--green)' : current ? 'var(--blue-bright)' : reached ? 'var(--fg-2)' : 'var(--fg-4)',
              fontWeight: current ? 700 : 500,
            }}>{p.short}</span>
          );
        })}
      </div>
    </div>
  );
}

function UploadStep({ token, onClose }: { token: string; onClose: () => void; }) {
  const { t } = useTranslation();
  type Line = { t: string; msg: string };
  const [lines, setLines] = useState<Line[]>([]);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [done, setDone] = useState(false);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = openSSE(`/api/wizard/${token}/upload`, {
      onEvent: (name, data) => {
        if (name === 'log') setLines((l) => [...l, { t: 'info', msg: data }]);
        else if (name === 'progress') {
          try { setProgress(JSON.parse(data) as ProgressInfo); } catch { /* */ }
        }
        else if (name === 'error') setLines((l) => [...l, { t: 'error', msg: data }]);
        else if (name === 'done') {
          try { setExitCode(JSON.parse(data).exit_code); } catch {/* */}
          setDone(true);
          setProgress((p) => p ? { ...p, pct: 100 } : null);
          close();
        }
      },
    });
    return close;
  }, [token]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  const colors: Record<string, string> = {
    info: 'var(--fg-2)', error: 'var(--red)',
  };

  return (
    <div style={{ padding: '16px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 10,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: 9999,
          background: done ? (exitCode === 0 ? 'var(--green)' : 'var(--red)') : 'var(--blue)',
          animation: done ? '' : 'pulse 1.5s infinite',
        }} />
        {t('wizard.uploadStreaming')}
      </div>

      <ProgressBar progress={progress} done={done} success={exitCode === 0} />

      <div
        ref={logRef}
        style={{
          background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
          borderRadius: 6, padding: 12, height: 300, overflowY: 'auto',
          fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.7,
          marginTop: 10,
        }}
      >
        {lines.map((l, i) => (
          <div key={i} style={{ color: colors[l.t] ?? 'var(--fg-2)' }}>
            <span style={{ color: 'var(--fg-4)', marginRight: 8 }}>
              {String(i + 1).padStart(3, '0')}
            </span>
            {l.msg}
          </div>
        ))}
      </div>

      {done && (
        <div style={{
          marginTop: 12, padding: '10px 14px',
          background: exitCode === 0 ? '#0a2a1a' : '#2a0a0a',
          border: `1px solid ${exitCode === 0 ? 'var(--green)' : 'var(--red)'}`,
          borderRadius: 6,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{
            fontSize: 12, color: exitCode === 0 ? 'var(--green)' : 'var(--red)',
            fontFamily: 'var(--font-mono)',
          }}>
            {exitCode === 0 ? t('wizard.uploadCompleted') : t('wizard.uploadFailed')} · {t('wizard.uploadExitCode')} {exitCode}
          </div>
          <button
            onClick={onClose}
            style={{
              background: exitCode === 0 ? 'var(--green)' : 'var(--blue)',
              border: 'none', color: 'var(--bg-base)',
              padding: '6px 16px', borderRadius: 4, fontSize: 11,
              fontWeight: 700, cursor: 'pointer',
              fontFamily: 'var(--font-display)',
            }}
          >{t('wizard.uploadFinish')}</button>
        </div>
      )}
    </div>
  );
}
