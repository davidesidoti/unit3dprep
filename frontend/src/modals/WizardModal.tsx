import { useEffect, useRef, useState } from 'react';
import { api, openSSE } from '../api';
import type { WizardCtx } from '../types';

type StepId = 'audio' | 'tmdb' | 'names' | 'hardlink' | 'upload';

const STEPS: { id: StepId; label: string; icon: string }[] = [
  { id: 'audio',    label: 'Audio Check', icon: '🎧' },
  { id: 'tmdb',     label: 'TMDB Match',  icon: '🎬' },
  { id: 'names',    label: 'Rename',      icon: '✎' },
  { id: 'hardlink', label: 'Hardlink',    icon: '⇢' },
  { id: 'upload',   label: 'Upload',      icon: '⬆' },
];

export function WizardModal({ ctx, onClose }: { ctx: WizardCtx; onClose: () => void }) {
  const [token, setToken] = useState<string | null>(null);
  const [step, setStep] = useState<StepId>('audio');
  const [startError, setStartError] = useState('');

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

  const kindLabel = { movie: 'Single movie', episode: 'Single episode', series: ctx.season ? 'Bulk season' : 'Whole series' }[ctx.kind];
  const idx = STEPS.findIndex((s) => s.id === step);

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(2,4,8,0.85)',
      zIndex: 100, display: 'flex', alignItems: 'center',
      justifyContent: 'center', padding: 20,
    }}>
      <div style={{
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
            }}>Upload Wizard</div>
            <div style={{
              fontSize: 11, color: 'var(--fg-3)',
              fontFamily: 'var(--font-mono)', marginTop: 2,
            }}>
              {kindLabel} · {ctx.title || ctx.name}
              {ctx.season && ` · S${String(ctx.season.n).padStart(2, '0')}`}
            </div>
          </div>
          <button
            onClick={onClose}
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
                <span style={{ marginRight: 5 }}>{s.icon}</span>{s.label}
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
            }}>starting wizard…</div>
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
            <NamesStep token={token} onNext={() => setStep('hardlink')} />
          )}
          {token && step === 'hardlink' && (
            <HardlinkStep
              token={token}
              onNext={() => setStep('upload')}
              onFinishOnly={onClose}
            />
          )}
          {token && step === 'upload' && (
            <UploadStep token={token} onClose={onClose} />
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
        Scanning each video file for an Italian audio track (required by ItaTorrents).
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
          <div style={{ padding: 14, color: 'var(--fg-3)' }}>scanning…</div>
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
          >Override &amp; continue anyway</button>
        ) : <span />}
        <button
          onClick={onNext}
          disabled={!allOk}
          style={{
            background: allOk ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: allOk ? '#fff' : 'var(--fg-3)',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: allOk ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >Next: TMDB Match →</button>
      </div>
    </div>
  );
}

function TmdbStep({ token, ctx, onNext }: {
  token: string; ctx: WizardCtx; onNext: () => void;
}) {
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
      }}>Enter the TMDB ID — titles are fetched bilingual (IT + EN).</div>
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
          placeholder="TMDB ID e.g. 155"
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
          style={{
            background: tmdbId && !loading ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: tmdbId && !loading ? '#fff' : 'var(--fg-3)',
            padding: '8px 16px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: tmdbId && !loading ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >{loading ? '…' : 'Lookup'}</button>
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
        <div style={{
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
            }}>Year {matched.year} · TMDB {tmdbId} · {kind}</div>
            <div style={{
              fontSize: 11, color: 'var(--fg-2)', lineHeight: 1.5,
            }}>{matched.overview}</div>
            <div style={{
              marginTop: 8, fontSize: 10,
              fontFamily: 'var(--font-mono)', color: 'var(--green)',
            }}>✓ Bilingual metadata cached</div>
          </div>
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
        <button
          onClick={onNext}
          disabled={!matched}
          style={{
            background: matched ? 'var(--blue)' : 'var(--border)',
            border: 'none', color: matched ? '#fff' : 'var(--fg-3)',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: matched ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-display)',
          }}
        >Next: Rename →</button>
      </div>
    </div>
  );
}

function NamesStep({ token, onNext }: { token: string; onNext: () => void; }) {
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

  if (loading) return <div style={{ padding: 30, color: 'var(--fg-3)' }}>loading proposed names…</div>;

  const entries = Object.entries(names);

  return (
    <div style={{ padding: '20px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 14, lineHeight: 1.6,
      }}>
        Proposed names follow ItaTorrents nomenclature.
        <span style={{ color: 'var(--yellow)' }}> Edit anything that looks wrong before creating hardlinks.</span>
      </div>
      {folder && (
        <div style={{ marginBottom: 12 }}>
          <label style={{
            fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: 'var(--tracking-wider)', color: 'var(--fg-4)',
            display: 'block', marginBottom: 4,
          }}>Folder name (seedings/…)</label>
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
          style={{
            background: 'var(--blue)', border: 'none', color: '#fff',
            padding: '8px 18px', borderRadius: 6, fontSize: 12,
            fontWeight: 600, cursor: 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >Next: Hardlink →</button>
      </div>
    </div>
  );
}

function HardlinkStep({ token, onNext, onFinishOnly }: {
  token: string; onNext: () => void; onFinishOnly: () => void;
}) {
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
        About to create {count} hardlink{count > 1 ? 's' : ''}. No disk copy — same inode, same filesystem.
      </div>
      <div style={{
        background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
        borderRadius: 6, padding: 14, marginBottom: 14,
      }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '90px 1fr', gap: 8,
          fontSize: 11, fontFamily: 'var(--font-mono)',
        }}>
          <span style={{ color: 'var(--fg-3)' }}>Source</span>
          <span style={{ color: 'var(--fg-1)', wordBreak: 'break-all' }}>{state?.path}</span>
          <span style={{ color: 'var(--fg-3)' }}>Files</span>
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
        Hardlink only — skip unit3dup upload (mark as manually uploaded)
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
          style={{
            width: '100%', background: running ? 'var(--border)' : 'var(--blue)',
            border: 'none', color: '#fff', padding: 10,
            borderRadius: 6, fontSize: 12, fontWeight: 600,
            cursor: running ? 'default' : 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >{running ? 'Linking…' : 'Execute hardlink'}</button>
      ) : (
        <div style={{
          background: '#0a0c12', border: '1px solid var(--green-dim)',
          borderRadius: 6, padding: 12,
          color: 'var(--green)', fontSize: 12, fontFamily: 'var(--font-mono)',
          wordBreak: 'break-all',
        }}>✓ Hardlinked to {seedingPath}</div>
      )}
      {done && (
        <div style={{
          display: 'flex', justifyContent: 'flex-end', marginTop: 18, gap: 8,
        }}>
          {hardlinkOnly ? (
            <button
              onClick={finishOnly}
              style={{
                background: 'var(--green)', border: 'none', color: 'var(--bg-base)',
                padding: '8px 18px', borderRadius: 6, fontSize: 12,
                fontWeight: 700, cursor: 'pointer',
                fontFamily: 'var(--font-display)',
              }}
            >Finish (no upload) ✓</button>
          ) : (
            <button
              onClick={onNext}
              style={{
                background: 'var(--blue)', border: 'none', color: '#fff',
                padding: '8px 18px', borderRadius: 6, fontSize: 12,
                fontWeight: 600, cursor: 'pointer',
                fontFamily: 'var(--font-display)',
              }}
            >Run unit3dup →</button>
          )}
        </div>
      )}
    </div>
  );
}

function UploadStep({ token, onClose }: { token: string; onClose: () => void; }) {
  type Line = { t: string; msg: string };
  const [lines, setLines] = useState<Line[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<{ kind: string; text: string } | null>(null);
  const [done, setDone] = useState(false);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [manual, setManual] = useState('');
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = openSSE(`/api/wizard/${token}/upload`, {
      onEvent: (name, data) => {
        if (name === 'log') setLines((l) => [...l, { t: 'info', msg: data }]);
        else if (name === 'progress') setProgress(data);
        else if (name === 'error') setLines((l) => [...l, { t: 'error', msg: data }]);
        else if (name === 'input_needed') {
          try { setPrompt(JSON.parse(data)); } catch {/* */}
        } else if (name === 'done') {
          try { setExitCode(JSON.parse(data).exit_code); } catch {/* */}
          setDone(true); setProgress(null); close();
        }
      },
    });
    return close;
  }, [token]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines, progress]);

  const respond = async (value: string) => {
    setLines((l) => [...l, { t: 'info', msg: `[User] → ${value}` }]);
    setPrompt(null);
    try { await api.post(`/api/wizard/${token}/stdin`, { value }); } catch {/* */}
  };

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
        Streaming unit3dup output via SSE
      </div>
      <div
        ref={logRef}
        style={{
          background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
          borderRadius: 6, padding: 12, height: 340, overflowY: 'auto',
          fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.7,
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
        {progress && (
          <div style={{ color: 'var(--blue-bright)' }}>
            <span style={{ color: 'var(--fg-4)', marginRight: 8 }}>
              {String(lines.length + 1).padStart(3, '0')}
            </span>
            {progress}
          </div>
        )}
      </div>

      {prompt && (
        <div style={{
          marginTop: 12, padding: 12, background: 'rgba(245,166,35,0.08)',
          border: '1px solid var(--yellow)', borderRadius: 6,
        }}>
          <div style={{
            fontSize: 12, color: 'var(--yellow)',
            fontFamily: 'var(--font-mono)', marginBottom: 8,
          }}>⚠ {prompt.text}</div>
          {prompt.kind === 'duplicate' ? (
            <div style={{ display: 'flex', gap: 6 }}>
              {[['c', 'Continue', 'var(--blue)', '#fff'],
                ['s', 'Skip',     'var(--bg-card)', 'var(--fg-1)'],
                ['q', 'Quit',     'var(--red-dim)', 'var(--red)']].map(([v, l, bg, fg]) => (
                <button
                  key={v}
                  onClick={() => respond(v)}
                  style={{
                    background: bg, border: '1px solid var(--border)',
                    color: fg, padding: '6px 14px', borderRadius: 4,
                    fontSize: 11, fontWeight: 600, cursor: 'pointer',
                    fontFamily: 'var(--font-display)',
                  }}
                >({(v as string).toUpperCase()}) {l}</button>
              ))}
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                autoFocus
                value={manual}
                onChange={(e) => setManual(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') respond(manual || '0'); }}
                placeholder="TMDB ID"
                style={{
                  flex: 1, background: 'var(--bg-base)',
                  border: '1px solid var(--border)', borderRadius: 4,
                  padding: '6px 10px', fontSize: 11, color: 'var(--fg-1)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
              <button
                onClick={() => respond(manual || '0')}
                style={{
                  background: 'var(--yellow)', border: 'none',
                  color: 'var(--bg-base)', padding: '6px 14px', borderRadius: 4,
                  fontSize: 11, fontWeight: 700, cursor: 'pointer',
                  fontFamily: 'var(--font-display)',
                }}
              >Send</button>
            </div>
          )}
        </div>
      )}

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
            {exitCode === 0 ? '✓ Upload completed' : '✗ Upload failed'} · exit code {exitCode}
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
          >Finish</button>
        </div>
      )}
    </div>
  );
}
