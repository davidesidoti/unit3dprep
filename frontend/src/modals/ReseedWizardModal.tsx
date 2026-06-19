import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { api, ApiError, openSSE } from '../api';
import type { ReseedCtx, ReseedMatch, ReseedSuggest, ReseedTorrent } from '../types';

type StepId = 'select' | 'confirm' | 'run';

export function ReseedWizardModal({
  ctx, onClose,
}: { ctx: ReseedCtx; onClose: (completed?: boolean) => void }) {
  const { t } = useTranslation();
  const presetLocal = ctx.local ?? null;
  const [step, setStep] = useState<StepId>(presetLocal ? 'confirm' : 'select');
  const [torrent, setTorrent] = useState<ReseedTorrent | null>(ctx.torrent ?? null);
  const [local, setLocal] = useState<ReseedMatch | null>(presetLocal);
  const [matches, setMatches] = useState<ReseedMatch[]>([]);
  const [loadingSuggest, setLoadingSuggest] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [err, setErr] = useState('');

  // Manual mode: resolve the torrent (with byte size + download link) and the
  // size-matched local files.
  useEffect(() => {
    if (presetLocal) return;
    setLoadingSuggest(true);
    api.get<ReseedSuggest>(`/api/reseed/suggest?torrent_id=${ctx.torrentId}`)
      .then((r) => { setTorrent(r.torrent); setMatches(r.matches); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : 'failed'))
      .finally(() => setLoadingSuggest(false));
  }, []);

  const STEPS: { id: StepId; labelKey: string }[] = presetLocal
    ? [{ id: 'confirm', labelKey: 'reseed.stepConfirm' }, { id: 'run', labelKey: 'reseed.stepRun' }]
    : [
        { id: 'select', labelKey: 'reseed.stepSelect' },
        { id: 'confirm', labelKey: 'reseed.stepConfirm' },
        { id: 'run', labelKey: 'reseed.stepRun' },
      ];
  const idx = STEPS.findIndex((s) => s.id === step);

  const start = async () => {
    if (!local) return;
    try {
      const r = await api.post<{ token: string }>('/api/reseed/start', {
        tracker: ctx.tracker,
        torrent_id: ctx.torrentId,
        source_path: local.source_path,
        category: local.category,
        kind: local.kind,
        title: local.item_name,
      });
      setToken(r.token);
      setStep('run');
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'failed');
    }
  };

  return createPortal(
    <div className="u3d-overlay-in" style={{
      position: 'fixed', inset: 0, background: 'rgba(2,4,8,0.85)',
      zIndex: 100, display: 'flex', alignItems: 'center',
      justifyContent: 'center', padding: 20,
    }}>
      <div className="u3d-modal-in" style={{
        width: 'min(720px, 100%)', maxHeight: '92vh',
        background: '#0a0c12', border: '1px solid var(--border)',
        borderRadius: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{
              fontSize: 15, fontWeight: 700, color: 'var(--fg-1)',
              fontFamily: 'var(--font-display)',
            }}>{t('reseed.wizardTitle')}</div>
            <div style={{
              fontSize: 11, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)',
              marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>{ctx.torrentName}</div>
          </div>
          <button
            onClick={() => onClose()}
            style={{
              marginLeft: 'auto', background: 'transparent', border: 'none',
              color: 'var(--fg-3)', cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 4,
            }}
          >×</button>
        </div>

        <div style={{
          display: 'flex', padding: '0 20px', gap: 2,
          borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-base)',
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
              }}>{t(s.labelKey)}</div>
            );
          })}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {err && (
            <div style={{ padding: 20, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{err}</div>
          )}

          {step === 'select' && (
            <SelectStep
              loading={loadingSuggest}
              torrent={torrent}
              matches={matches}
              onPick={(m) => { setLocal(m); setStep('confirm'); }}
            />
          )}

          {step === 'confirm' && torrent && local && (
            <ConfirmStep torrent={torrent} local={local} onStart={start} />
          )}

          {step === 'run' && token && (
            <RunStep token={token} onFinish={(ok) => onClose(ok)} />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

// --------------------------------------------------------------------------

function KV({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '4px 0' }}>
      <span style={{
        fontSize: 11, color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
        textTransform: 'uppercase', letterSpacing: 'var(--tracking-wide)',
      }}>{label}</span>
      <span style={{
        fontSize: 12, color: 'var(--fg-1)',
        fontFamily: mono ? 'var(--font-mono)' : 'var(--font-display)',
        textAlign: 'right', wordBreak: 'break-word',
      }}>{value}</span>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '12px 16px', flex: 1, minWidth: 0,
    }}>
      <div style={{
        fontSize: 10, fontWeight: 700, color: 'var(--fg-3)',
        letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
        fontFamily: 'var(--font-display)', marginBottom: 8,
      }}>{title}</div>
      {children}
    </div>
  );
}

function SelectStep({ loading, torrent, matches, onPick }: {
  loading: boolean; torrent: ReseedTorrent | null;
  matches: ReseedMatch[]; onPick: (m: ReseedMatch) => void;
}) {
  const { t } = useTranslation();
  return (
    <div style={{ padding: '16px 24px' }}>
      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 14, fontFamily: 'var(--font-display)' }}>
        {t('reseed.selectDesc')}
      </div>
      {torrent && (
        <div style={{ marginBottom: 16 }}>
          <Panel title={t('reseed.torrentLabel')}>
            <KV label={t('reseed.localFile')} value={torrent.name} mono />
            <KV label={t('reseed.sizeLabel')} value={torrent.size_human} mono />
            <KV label={t('reseed.resolutionLabel')} value={torrent.resolution} />
          </Panel>
        </div>
      )}
      {loading ? (
        <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {t('reseed.loadingSuggest')}
        </div>
      ) : matches.length === 0 ? (
        <div style={{
          padding: '14px 16px', background: 'var(--yellow-dim)',
          border: '1px solid var(--yellow)', borderRadius: 6,
          color: 'var(--yellow)', fontSize: 12, fontFamily: 'var(--font-mono)',
        }}>{t('reseed.selectNoMatches')}</div>
      ) : (
        <div className="u3d-stagger">
          {matches.map((m) => (
            <div
              key={m.source_path}
              className="u3d-card"
              onClick={() => onPick(m)}
              style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                borderRadius: 6, padding: '10px 14px', marginBottom: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: 10, cursor: 'pointer',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, color: 'var(--fg-1)', fontFamily: 'var(--font-mono)', wordBreak: 'break-word' }}>{m.item_name}</div>
                <div style={{ fontSize: 10, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>{m.category} · {m.size_human}</div>
              </div>
              <span style={{
                fontSize: 11, fontWeight: 700, color: 'var(--blue-bright)',
                fontFamily: 'var(--font-display)', flexShrink: 0,
              }}>{t('reseed.selectUse')} →</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConfirmStep({ torrent, local, onStart }: {
  torrent: ReseedTorrent; local: ReseedMatch; onStart: () => void;
}) {
  const { t } = useTranslation();
  const sizeMatch = torrent.size === local.size;
  return (
    <div style={{ padding: '16px 24px' }}>
      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 14, fontFamily: 'var(--font-display)' }}>
        {t('reseed.confirmDesc')}
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <Panel title={t('reseed.torrentLabel')}>
          <KV label="" value={torrent.name} mono />
          <KV label={t('reseed.sizeLabel')} value={torrent.size_human} mono />
          <KV label={t('reseed.resolutionLabel')} value={torrent.resolution} />
          <KV label={t('reseed.seedersLabel')} value={String(torrent.seeders)} mono />
        </Panel>
        <Panel title={t('reseed.localLabel')}>
          <KV label="" value={local.item_name} mono />
          <KV label={t('reseed.sizeLabel')} value={local.size_human} mono />
          <KV label="" value={local.category} />
        </Panel>
      </div>
      <div style={{
        padding: '10px 14px', borderRadius: 6, marginBottom: 16,
        background: sizeMatch ? 'var(--green-dim)' : 'var(--yellow-dim)',
        border: `1px solid ${sizeMatch ? 'var(--green)' : 'var(--yellow)'}`,
        color: sizeMatch ? 'var(--green)' : 'var(--yellow)',
        fontSize: 12, fontFamily: 'var(--font-mono)',
      }}>{sizeMatch ? t('reseed.sizeMatch') : t('reseed.sizeMismatchWarn')}</div>
      <button
        onClick={onStart}
        className="u3d-pressable"
        style={{
          background: 'var(--blue)', border: 'none', borderRadius: 6,
          padding: '10px 20px', fontSize: 13, fontWeight: 600, color: '#fff',
          cursor: 'pointer', fontFamily: 'var(--font-display)',
        }}
      >{t('reseed.startBtn')} →</button>
    </div>
  );
}

type RPhase = 'download' | 'hardlink' | 'recheck';
const RPHASES: { id: RPhase; key: string }[] = [
  { id: 'download', key: 'reseed.phaseDownload' },
  { id: 'hardlink', key: 'reseed.phaseHardlink' },
  { id: 'recheck', key: 'reseed.phaseRecheck' },
];

function RunStep({ token, onFinish }: { token: string; onFinish: (ok: boolean) => void }) {
  const { t } = useTranslation();
  const [lines, setLines] = useState<{ t: string; msg: string }[]>([]);
  const [phase, setPhase] = useState<RPhase | ''>('');
  const [pct, setPct] = useState(0);
  const [done, setDone] = useState(false);
  const [ok, setOk] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = openSSE(`/api/reseed/${token}/run`, {
      onEvent: (name, data) => {
        if (name === 'log') setLines((l) => [...l, { t: 'info', msg: data }]);
        else if (name === 'progress') {
          try {
            const p = JSON.parse(data);
            if (p.phase) setPhase(p.phase as RPhase);
            if (typeof p.pct === 'number') setPct(p.pct);
          } catch { /* */ }
        } else if (name === 'error') setLines((l) => [...l, { t: 'error', msg: data }]);
        else if (name === 'done') {
          try { setOk(!!JSON.parse(data).ok); } catch { /* */ }
          setDone(true);
          close();
        }
      },
      onError: () => { /* server closed the stream — ignore, 'done' drives state */ },
    });
    return close;
  }, [token]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  const phaseIdx = phase ? RPHASES.findIndex((p) => p.id === phase) : -1;
  const barColor = done ? (ok ? 'var(--green)' : 'var(--red)') : 'var(--blue-bright)';
  const barPct = done ? 100 : Math.max(0, Math.min(100, pct));

  return (
    <div style={{ padding: '16px 24px' }}>
      <div style={{
        fontSize: 13, color: 'var(--fg-2)', marginBottom: 10,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: 9999,
          background: done ? (ok ? 'var(--green)' : 'var(--red)') : 'var(--blue)',
          animation: done ? '' : 'pulse 1.5s infinite',
        }} />
        {done ? (ok ? t('reseed.completed') : t('reseed.failed')) : t('reseed.running')}
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{
          height: 6, background: 'var(--bg-base)', borderRadius: 3,
          overflow: 'hidden', position: 'relative', border: '1px solid var(--border-subtle)',
        }}>
          <div style={{
            height: '100%', width: `${barPct}%`, background: barColor,
            transition: 'width 250ms ease-out', borderRadius: 3,
            position: 'relative', overflow: 'hidden',
          }}>
            {!done && barPct > 0 && barPct < 100 && <div className="u3d-shimmer-overlay" />}
          </div>
        </div>
        <div style={{
          display: 'flex', justifyContent: 'space-between', marginTop: 4,
          fontSize: 9, fontFamily: 'var(--font-display)', color: 'var(--fg-4)',
          letterSpacing: 'var(--tracking-wide)',
        }}>
          {RPHASES.map((p, i) => {
            const reached = phaseIdx >= 0 && i <= phaseIdx;
            const current = phaseIdx === i && !done;
            return (
              <span key={p.id} style={{
                color: done && ok ? 'var(--green)' : current ? 'var(--blue-bright)' : reached ? 'var(--fg-2)' : 'var(--fg-4)',
                fontWeight: current ? 700 : 500,
              }}>{t(p.key)}</span>
            );
          })}
        </div>
      </div>

      <div
        ref={logRef}
        style={{
          background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
          borderRadius: 6, padding: 12, height: 260, overflowY: 'auto',
          fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.7, marginTop: 10,
        }}
      >
        {lines.map((l, i) => (
          <div key={i} style={{ color: l.t === 'error' ? 'var(--red)' : 'var(--fg-2)' }}>
            <span style={{ color: 'var(--fg-4)', marginRight: 8 }}>{String(i + 1).padStart(3, '0')}</span>
            {l.msg}
          </div>
        ))}
      </div>

      {done && (
        <div style={{
          marginTop: 12, padding: '10px 14px',
          background: ok ? '#0a2a1a' : '#2a0a0a',
          border: `1px solid ${ok ? 'var(--green)' : 'var(--red)'}`,
          borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
        }}>
          <button
            onClick={() => onFinish(ok)}
            style={{
              background: ok ? 'var(--green)' : 'var(--blue)', border: 'none',
              color: 'var(--bg-base)', padding: '6px 16px', borderRadius: 4,
              fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font-display)',
            }}
          >{t('reseed.finish')}</button>
        </div>
      )}
    </div>
  );
}
