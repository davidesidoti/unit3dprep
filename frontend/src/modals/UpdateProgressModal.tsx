import { useEffect, useRef, useState } from 'react';
import { X, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { openSSE } from '../api';

interface Props {
  target: 'app' | 'webup';
  onClose: () => void;
  onCompleted: (target: 'app' | 'webup', from: string, to: string) => void;
}

type Phase = 'running' | 'error' | 'done' | 'countdown';

export function UpdateProgressModal({ target, onClose, onCompleted }: Props) {
  const { t } = useTranslation();
  const [lines, setLines] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>('running');
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState<string>('');
  const [to, setTo] = useState<string>('');
  const [count, setCount] = useState(5);
  const logRef = useRef<HTMLDivElement>(null);
  const closeSSE = useRef<(() => void) | null>(null);
  const phaseRef = useRef<Phase>('running');
  const doneRef = useRef(false);

  const setPhaseSafe = (p: Phase) => { phaseRef.current = p; setPhase(p); };

  useEffect(() => {
    const path = target === 'app'
      ? '/api/version/update/app/stream'
      : '/api/version/update/webup/stream';
    const push = (s: string) => setLines((l) => [...l, s]);

    closeSSE.current = openSSE(path, {
      onEvent: (name, data) => {
        if (name === 'log') push(data);
        else if (name === 'start') {
          try {
            const j = JSON.parse(data);
            if (j.current) setFrom(j.current);
          } catch { /* noop */ }
        } else if (name === 'error') {
          try {
            const j = JSON.parse(data);
            const msg = j.message || data;
            setError(msg);
            push(`ERROR: ${msg}`);
          } catch {
            setError(data);
            push(`ERROR: ${data}`);
          }
          setPhaseSafe('error');
        } else if (name === 'done') {
          doneRef.current = true;
          // Close SSE immediately: the backend is about to restart systemd,
          // which would trigger onerror → EventSource auto-reconnect → loop.
          closeSSE.current?.();
          closeSSE.current = null;
          try {
            const j = JSON.parse(data);
            if (j.ok) {
              setFrom(j.from || from);
              setTo(j.to || '');
              setPhaseSafe('countdown');
            } else if (phaseRef.current !== 'error') {
              setPhaseSafe('error');
            }
          } catch {
            setPhaseSafe('error');
          }
        }
      },
      onError: () => {
        if (doneRef.current) return;
        if (phaseRef.current === 'countdown' || phaseRef.current === 'error') return;
        // Force-close so EventSource doesn't auto-reconnect and re-trigger
        // the update on the server.
        closeSSE.current?.();
        closeSSE.current = null;
        push('(stream closed)');
        setError(t('update.connectionLost'));
        setPhaseSafe('error');
      },
    });
    return () => { closeSSE.current?.(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  useEffect(() => {
    if (phase !== 'countdown') return;
    try {
      localStorage.setItem('unit3dprep.pendingChangelog', JSON.stringify({
        target, from, to, at: Date.now(),
      }));
    } catch { /* noop */ }
    let n = 5;
    setCount(n);
    const iv = window.setInterval(() => {
      n -= 1;
      setCount(n);
      if (n <= 0) {
        window.clearInterval(iv);
        window.location.reload();
      }
    }, 1000);
    return () => window.clearInterval(iv);
  }, [phase, target, from, to]);

  const title = target === 'app' ? t('update.appTitle') : t('update.webupTitle');

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget && phase !== 'running' && phase !== 'countdown') onClose();
      }}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 16,
      }}
    >
      <div style={{
        background: 'var(--bg-surface)', borderRadius: 10,
        border: '1px solid var(--border)', width: '100%', maxWidth: 640,
        maxHeight: '80vh', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14,
            color: 'var(--fg-1)', display: 'flex', alignItems: 'center', gap: 8,
          }}>
            {phase === 'running' && (
              <RefreshCw size={14} style={{ animation: 'spin 1.2s linear infinite' }} />
            )}
            {phase === 'error' && <AlertCircle size={14} color="var(--red)" />}
            {(phase === 'done' || phase === 'countdown') && <CheckCircle size={14} color="var(--green)" />}
            {title}
          </div>
          {(phase === 'error') && (
            <button
              onClick={onClose}
              style={{
                background: 'transparent', border: 'none',
                color: 'var(--fg-3)', cursor: 'pointer', padding: 4,
              }}
            ><X size={16} /></button>
          )}
        </div>

        <div
          ref={logRef}
          style={{
            flex: 1, overflow: 'auto', padding: 12,
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: 'var(--fg-2)', background: '#0a0c10',
            lineHeight: 1.55, minHeight: 200,
          }}
        >
          {lines.length === 0 && (
            <div style={{ color: 'var(--fg-4)' }}>{t('update.starting')}</div>
          )}
          {lines.map((l, i) => (
            <div key={i} style={{
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              color: l.startsWith('ERROR:') ? 'var(--red)' :
                     l.startsWith('$ ') ? 'var(--blue-bright)' : 'var(--fg-2)',
            }}>{l}</div>
          ))}
        </div>

        {phase === 'countdown' && (
          <div style={{
            padding: '14px 18px', borderTop: '1px solid var(--border-subtle)',
            textAlign: 'center', fontFamily: 'var(--font-display)',
            color: 'var(--green)',
          }}>
            <div style={{ fontSize: 13, marginBottom: 4 }}>
              {target === 'app' ? `app ${from} → ${to}` : `webup ${from} → ${to}`}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>
              {t('update.autoRefreshIn')} {count}…
            </div>
          </div>
        )}
        {phase === 'error' && (
          <div style={{
            padding: '12px 18px', borderTop: '1px solid var(--border-subtle)',
            display: 'flex', justifyContent: 'flex-end',
          }}>
            <button
              onClick={onClose}
              style={{
                background: 'var(--red-dim)', border: '1px solid var(--red)',
                color: 'var(--red)', padding: '6px 14px', borderRadius: 6,
                cursor: 'pointer', fontFamily: 'var(--font-display)',
                fontSize: 12, fontWeight: 600,
              }}
            >{t('update.close')}</button>
          </div>
        )}
      </div>
    </div>
  );
}
