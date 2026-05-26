import { useEffect, useRef, useState } from 'react';
import { X, File as FileIcon, FolderOpen, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, openSSE } from '../api';
import { FileBrowser } from '../components/FileBrowser';
import { Toggle } from '../components/primitives';

type Mode = 'u' | 'f' | 'scan';

interface Log { t: 'log' | 'ok' | 'warn' | 'err'; msg: string; }

export function UploadModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [path, setPath] = useState('');
  const [mode, setMode] = useState<Mode>('u');
  const [tracker, setTracker] = useState('ITT');
  const [opts, setOpts] = useState({
    screenshots: true, skipTmdb: false, skipYoutube: false, anon: false, webp: false,
  });
  const [job, setJob] = useState<string | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [done, setDone] = useState(false);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const logRef = useRef<HTMLDivElement>(null);
  const closeSSE = useRef<(() => void) | null>(null);

  useEffect(() => () => { closeSSE.current?.(); }, []);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs, progress]);

  const startUpload = async () => {
    setStarting(true); setError('');
    try {
      const r = await api.post<{ job: string }>('/api/upload/quick', {
        path, mode, tracker,
        screenshots: opts.screenshots,
        skip_tmdb: opts.skipTmdb,
        skip_youtube: opts.skipYoutube,
        anon: opts.anon,
        webp: opts.webp,
      });
      setJob(r.job);
      openStream(r.job);
      setStep(2);
    } catch (e: any) {
      setError(e.message || 'failed');
    } finally {
      setStarting(false);
    }
  };

  const openStream = (jobId: string) => {
    const close = openSSE(`/api/upload/${jobId}/stream`, {
      onEvent: (name, data) => {
        if (name === 'log') setLogs((l) => [...l, { t: 'log', msg: data }]);
        else if (name === 'progress') {
          try { setProgress(JSON.parse(data) as ProgressInfo); } catch { /* */ }
        }
        else if (name === 'error') setLogs((l) => [...l, { t: 'err', msg: data }]);
        else if (name === 'job_done') {
          try {
            const j = JSON.parse(data);
            setLogs((l) => [...l, {
              t: j.exit_code === 0 ? 'ok' : 'err',
              msg: `[${j.exit_code === 0 ? '✓' : '✗'}] ${j.path || j.job_id}`,
            }]);
          } catch { /* */ }
        } else if (name === 'done') {
          try { setExitCode(JSON.parse(data).exit_code); } catch {/* */}
          setDone(true);
          setProgress((p) => p ? { ...p, pct: 100 } : null);
          close();
        }
      },
      onError: () => { setLogs((l) => [...l, { t: 'err', msg: 'SSE connection lost' }]); close(); },
    });
    closeSSE.current = close;
  };

  const steps = [t('upload.stepPath'), t('upload.stepOptions'), t('upload.stepUpload')];
  const logColors: Record<string, string> = {
    log: 'var(--blue-bright)', ok: 'var(--green)',
    warn: 'var(--yellow)', err: 'var(--red)',
  };

  const modes = [
    { id: 'u' as Mode, icon: FileIcon, label: t('upload.modeFileLabel'), desc: t('upload.modeFile') },
    { id: 'f' as Mode, icon: FolderOpen, label: t('upload.modeFolderLabel'), desc: t('upload.modeFolder') },
    { id: 'scan' as Mode, icon: RefreshCw, label: t('upload.modeRecursiveLabel'), desc: t('upload.modeRecursive') },
  ];

  const uploadOpts: [keyof typeof opts, string, string][] = [
    ['screenshots', t('upload.optScreenshots'), 'Extract frames via ffmpeg'],
    ['skipTmdb', t('upload.optSkipTmdb'), 'SKIP_TMDB'],
    ['skipYoutube', t('upload.optSkipYoutube'), 'SKIP_YOUTUBE'],
    ['anon', t('upload.optAnon'), 'Hide username (ANON)'],
    ['webp', t('upload.optWebp'), 'WEBP_ENABLED'],
  ];

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="u3d-mobile-modal"
        style={{
          background: 'var(--bg-surface)', border: '1px solid var(--border)',
          borderRadius: 8, width: 560,
          maxWidth: 'calc(100vw - 24px)', maxHeight: '90vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: '1px solid var(--border)',
        }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 600,
            color: 'var(--fg-1)',
          }}>{t('upload.title')}</span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: 'var(--fg-3)',
              cursor: 'pointer', padding: 4, display: 'flex', borderRadius: 4,
            }}
          ><X size={15} /></button>
        </div>

        <div style={{
          display: 'flex', padding: '12px 18px', gap: 6,
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          {steps.map((label, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
              color: i <= step ? 'var(--blue-bright)' : 'var(--fg-4)',
            }}>
              <span style={{
                width: 20, height: 20, borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 700,
                background: i < step ? 'var(--blue)'
                  : i === step ? 'rgba(59,130,246,0.2)' : 'var(--bg-card)',
                color: i <= step ? 'var(--blue-bright)' : 'var(--fg-4)',
                border: i <= step ? '1px solid var(--blue)' : '1px solid var(--border)',
              }}>{i < step ? '✓' : i + 1}</span>
              {label}
              {i < steps.length - 1 && (
                <span style={{ color: 'var(--fg-4)', fontSize: 12, marginLeft: 6 }}>›</span>
              )}
            </div>
          ))}
        </div>

        <div style={{ padding: '16px 18px', overflowY: 'auto', flex: 1 }}>
          {step === 0 && (
            <>
              <label style={labelStyle}>{t('upload.modeLabel')}</label>
              <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                {modes.map((m) => {
                  const Icon = m.icon;
                  const active = mode === m.id;
                  return (
                    <div
                      key={m.id}
                      onClick={() => setMode(m.id)}
                      style={{
                        flex: 1, padding: '8px 10px', borderRadius: 6,
                        cursor: 'pointer',
                        border: active ? '1px solid var(--blue)' : '1px solid var(--border)',
                        background: active ? 'rgba(59,130,246,0.08)' : 'var(--bg-card)',
                        display: 'flex', alignItems: 'center', gap: 7,
                      }}
                    >
                      <Icon size={13} color={active ? 'var(--blue-bright)' : 'var(--fg-3)'} />
                      <div>
                        <div style={{
                          fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
                          color: active ? 'var(--blue-bright)' : 'var(--fg-2)',
                        }}>{m.label}</div>
                        <div style={{
                          fontFamily: 'var(--font-display)', fontSize: 10,
                          color: 'var(--fg-3)',
                        }}>{m.desc}</div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <label style={labelStyle}>{t('upload.browseLabel')}</label>
              <FileBrowser onSelect={setPath} />

              <label style={labelStyle}>{t('upload.selectedPath')}</label>
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/home/user/ITT/upload/..."
                style={{ ...inputStyle, marginBottom: 10 }}
              />

              <label style={labelStyle}>{t('upload.targetTracker')}</label>
              <select
                value={tracker}
                onChange={(e) => setTracker(e.target.value)}
                style={{
                  ...inputStyle,
                  fontFamily: 'var(--font-display)',
                }}
              >
                <option>ITT</option>
                <option>PTT</option>
                <option>Multi (ITT + PTT)</option>
              </select>
            </>
          )}

          {step === 1 && (
            <>
              <label style={labelStyle}>{t('upload.optionsLabel')}</label>
              {uploadOpts.map(([k, l, s]) => (
                <div key={k} style={{
                  display: 'flex', alignItems: 'center',
                  justifyContent: 'space-between', padding: '7px 0',
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  <div>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 13,
                      color: 'var(--fg-2)',
                    }}>{l}</div>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 11,
                      color: 'var(--fg-4)',
                    }}>{s}</div>
                  </div>
                  <Toggle
                    on={opts[k]}
                    onToggle={() => setOpts((o) => ({ ...o, [k]: !o[k] }))}
                  />
                </div>
              ))}
            </>
          )}

          {step === 2 && (
            <>
              {error && (
                <div style={{
                  padding: 10, color: 'var(--red)',
                  background: 'var(--red-dim)', borderRadius: 6, marginBottom: 10,
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                }}>{error}</div>
              )}
              <UploadProgressBar progress={progress} done={done} success={exitCode === 0} />
              <div
                ref={logRef}
                style={{
                  background: 'var(--bg-base)',
                  border: '1px solid var(--border)',
                  borderRadius: 6, padding: '10px 12px',
                  fontFamily: 'var(--font-mono)', fontSize: 11,
                  lineHeight: 1.85, maxHeight: 240, overflowY: 'auto',
                  marginBottom: 10, marginTop: 10,
                }}
              >
                {logs.map((l, i) => (
                  <div key={i} style={{ color: logColors[l.t] }}>{l.msg}</div>
                ))}
              </div>

              {done && (
                <div style={{
                  padding: '10px 14px',
                  background: exitCode === 0 ? 'var(--green-dim)' : 'var(--red-dim)',
                  border: `1px solid ${exitCode === 0 ? 'var(--green)' : 'var(--red)'}`,
                  borderRadius: 6,
                  color: exitCode === 0 ? 'var(--green)' : 'var(--red)',
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                }}>
                  {exitCode === 0 ? t('upload.completed') : t('upload.failed')} · {t('upload.exit')} {exitCode}
                </div>
              )}
            </>
          )}
        </div>

        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 18px', borderTop: '1px solid var(--border-subtle)',
        }}>
          <button
            onClick={step === 0 ? onClose : () => setStep((s) => s - 1)}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '6px 14px', fontSize: 12,
              fontWeight: 600, cursor: 'pointer', color: 'var(--fg-2)',
              fontFamily: 'var(--font-display)',
            }}
          >{step === 0 ? t('upload.cancel') : t('upload.back')}</button>
          <button
            disabled={step === 0 && !path || starting}
            onClick={() => {
              if (step === 0) setStep(1);
              else if (step === 1) startUpload();
              else onClose();
            }}
            style={{
              background: (step === 0 && !path) || starting ? 'var(--border)' : 'var(--blue)',
              border: 'none', borderRadius: 6,
              padding: '6px 14px', fontSize: 12, fontWeight: 600,
              cursor: (step === 0 && !path) || starting ? 'not-allowed' : 'pointer',
              color: '#fff', fontFamily: 'var(--font-display)',
            }}
          >
            {step === 2 ? (done ? t('upload.done') : t('upload.waiting'))
              : step === 1 ? (starting ? t('upload.starting') : t('upload.startBtn'))
                : t('upload.next')}
          </button>
        </div>
      </div>
    </div>
  );
}

interface ProgressInfo { phase?: string; label?: string; pct: number; sub_pct?: number; }

const PROGRESS_PHASES: { id: string; short: string }[] = [
  { id: 'setenv',      short: 'Setup' },
  { id: 'scan',        short: 'Scan' },
  { id: 'maketorrent', short: 'Torrent' },
  { id: 'upload',      short: 'Upload' },
  { id: 'seed',        short: 'Seed' },
];

function UploadProgressBar({ progress, done, success }: {
  progress: ProgressInfo | null; done: boolean; success: boolean;
}) {
  const pct = done ? 100 : Math.max(0, Math.min(100, progress?.pct ?? 0));
  const phaseIdx = progress?.phase ? PROGRESS_PHASES.findIndex((p) => p.id === progress.phase) : -1;
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
        }} />
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', marginTop: 4,
        fontSize: 9, fontFamily: 'var(--font-display)', color: 'var(--fg-4)',
        letterSpacing: 'var(--tracking-wide)',
      }}>
        {PROGRESS_PHASES.map((p, i) => {
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

const labelStyle: React.CSSProperties = {
  fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600,
  color: 'var(--fg-3)', letterSpacing: 'var(--tracking-wide)',
  textTransform: 'uppercase', marginBottom: 5, display: 'block',
};

const inputStyle: React.CSSProperties = {
  width: '100%', background: 'var(--bg-card)',
  border: '1px solid var(--border)', borderRadius: 6,
  padding: '7px 10px', fontSize: 12, color: 'var(--fg-1)',
  fontFamily: 'var(--font-mono)', outline: 'none',
  boxSizing: 'border-box',
};
