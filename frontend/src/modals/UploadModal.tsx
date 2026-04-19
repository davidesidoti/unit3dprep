import { useEffect, useRef, useState } from 'react';
import { X, File as FileIcon, FolderOpen, RefreshCw, AlertCircle } from 'lucide-react';
import { api, openSSE } from '../api';
import { FileBrowser } from '../components/FileBrowser';
import { Toggle } from '../components/primitives';

type Mode = 'u' | 'f' | 'scan';

interface Log { t: 'log' | 'ok' | 'warn' | 'err'; msg: string; }

export function UploadModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [path, setPath] = useState('');
  const [mode, setMode] = useState<Mode>('u');
  const [tracker, setTracker] = useState('ITT');
  const [opts, setOpts] = useState({
    screenshots: true, skipTmdb: false, skipYoutube: false, anon: false, webp: false,
  });
  const [job, setJob] = useState<string | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<{ kind: string; text: string } | null>(null);
  const [done, setDone] = useState(false);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [manualTmdb, setManualTmdb] = useState('');
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
        else if (name === 'progress') setProgress(data);
        else if (name === 'error') setLogs((l) => [...l, { t: 'err', msg: data }]);
        else if (name === 'input_needed') {
          try { setPrompt(JSON.parse(data)); } catch {/* */}
        } else if (name === 'done') {
          try { setExitCode(JSON.parse(data).exit_code); } catch {/* */}
          setDone(true); setProgress(null); close();
        }
      },
      onError: () => { setLogs((l) => [...l, { t: 'err', msg: 'SSE connection lost' }]); close(); },
    });
    closeSSE.current = close;
  };

  const respondPrompt = async (value: string) => {
    if (!job || !prompt) return;
    setLogs((l) => [...l, { t: 'log', msg: `→ ${value}` }]);
    setPrompt(null);
    try { await api.post(`/api/upload/${job}/stdin`, { value }); } catch { /* */ }
  };

  const steps = ['Path', 'Options', 'Upload'];
  const logColors: Record<string, string> = {
    log: 'var(--blue-bright)', ok: 'var(--green)',
    warn: 'var(--yellow)', err: 'var(--red)',
  };

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
        style={{
          background: 'var(--bg-surface)', border: '1px solid var(--border)',
          borderRadius: 8, width: 560, maxHeight: '90vh',
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
          }}>New Upload</span>
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
              <label style={labelStyle}>Upload Mode</label>
              <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                {([
                  { id: 'u', icon: FileIcon, label: '-u  file', desc: 'Single file' },
                  { id: 'f', icon: FolderOpen, label: '-f  folder', desc: 'Full folder' },
                  { id: 'scan', icon: RefreshCw, label: '-scan auto', desc: 'Recursive' },
                ] as const).map((m) => {
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

              <label style={labelStyle}>Browse &amp; Select</label>
              <FileBrowser onSelect={setPath} />

              <label style={labelStyle}>Selected Path</label>
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/home/user/ITT/upload/..."
                style={{ ...inputStyle, marginBottom: 10 }}
              />

              <label style={labelStyle}>Target Tracker</label>
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
              <label style={labelStyle}>Upload Options</label>
              {([
                ['screenshots', 'Capture Screenshots', 'Extract frames via ffmpeg'],
                ['skipTmdb', 'Skip TMDB Lookup', 'SKIP_TMDB'],
                ['skipYoutube', 'Skip YouTube Trailer', 'SKIP_YOUTUBE'],
                ['anon', 'Anonymous Upload', 'Hide username (ANON)'],
                ['webp', 'WebP Screenshots', 'WEBP_ENABLED'],
              ] as const).map(([k, l, s]) => (
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
                    on={(opts as any)[k]}
                    onToggle={() => setOpts((o) => ({ ...o, [k]: !(o as any)[k] }))}
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
              <div
                ref={logRef}
                style={{
                  background: 'var(--bg-base)',
                  border: '1px solid var(--border)',
                  borderRadius: 6, padding: '10px 12px',
                  fontFamily: 'var(--font-mono)', fontSize: 11,
                  lineHeight: 1.85, maxHeight: 260, overflowY: 'auto',
                  marginBottom: 10,
                }}
              >
                {logs.map((l, i) => (
                  <div key={i} style={{ color: logColors[l.t] }}>{l.msg}</div>
                ))}
                {progress && (
                  <div style={{ color: 'var(--blue-bright)' }}>{progress}</div>
                )}
              </div>

              {prompt && (
                <div style={{
                  background: 'rgba(245,166,35,0.05)',
                  border: '1px solid var(--yellow)', borderRadius: 6,
                  padding: '12px 14px', marginBottom: 10,
                }}>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
                    color: 'var(--yellow)', marginBottom: 8,
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <AlertCircle size={13} /> {prompt.text || 'Input required'}
                  </div>
                  {prompt.kind === 'duplicate' ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      {[['c', 'Continue', 'var(--blue)'],
                        ['s', 'Skip', 'var(--bg-card)'],
                        ['q', 'Quit', 'var(--red-dim)']].map(([v, l, bg]) => (
                        <button
                          key={v}
                          onClick={() => respondPrompt(v)}
                          style={{
                            background: bg,
                            border: '1px solid var(--border)',
                            color: v === 'q' ? 'var(--red)' : '#fff',
                            padding: '6px 14px', borderRadius: 4,
                            fontSize: 11, fontWeight: 600, cursor: 'pointer',
                            fontFamily: 'var(--font-display)',
                          }}
                        >({(v as string).toUpperCase()}) {l}</button>
                      ))}
                    </div>
                  ) : (
                    <>
                      <input
                        autoFocus
                        value={manualTmdb}
                        onChange={(e) => setManualTmdb(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') respondPrompt(manualTmdb || '0');
                        }}
                        placeholder="TMDB ID"
                        style={{
                          ...inputStyle, marginBottom: 8,
                          borderColor: 'var(--yellow-dim)',
                        }}
                      />
                      <button
                        onClick={() => respondPrompt(manualTmdb || '0')}
                        style={{
                          background: 'var(--yellow)', border: 'none', borderRadius: 6,
                          padding: '5px 12px', fontSize: 11, fontWeight: 600,
                          cursor: 'pointer', color: 'var(--bg-surface)',
                          fontFamily: 'var(--font-display)',
                        }}
                      >Submit &amp; Continue →</button>
                    </>
                  )}
                </div>
              )}

              {done && (
                <div style={{
                  padding: '10px 14px',
                  background: exitCode === 0 ? 'var(--green-dim)' : 'var(--red-dim)',
                  border: `1px solid ${exitCode === 0 ? 'var(--green)' : 'var(--red)'}`,
                  borderRadius: 6,
                  color: exitCode === 0 ? 'var(--green)' : 'var(--red)',
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                }}>
                  {exitCode === 0 ? '✓ Upload completed' : '✗ Upload failed'} · exit {exitCode}
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
          >{step === 0 ? 'Cancel' : '← Back'}</button>
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
            {step === 2 ? (done ? 'Done' : 'Waiting…')
              : step === 1 ? (starting ? 'Starting…' : 'Start Upload →')
                : 'Next →'}
          </button>
        </div>
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
