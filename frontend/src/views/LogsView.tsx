import { useEffect, useMemo, useRef, useState } from 'react';
import { openSSE } from '../api';
import type { LogLine, LogKind } from '../types';

const kindColors: Record<string, string> = {
  info: 'var(--blue-bright)',
  ok: 'var(--green)',
  warn: 'var(--yellow)',
  error: 'var(--red)',
  debug: 'var(--fg-3)',
};
const kindPrefixes: Record<string, string> = {
  info: '[log]',
  ok: '[ok] ',
  warn: '[warn]',
  error: '[err]',
  debug: '[dbg]',
};

type SourceKey = 'app' | 'http' | 'unit3dup' | 'wizard' | 'client' | 'tracker' | 'system' | 'upload';
const SOURCES: { key: SourceKey; label: string }[] = [
  { key: 'app', label: 'App' },
  { key: 'wizard', label: 'Wizard' },
  { key: 'unit3dup', label: 'Unit3Dup' },
  { key: 'upload', label: 'Upload' },
  { key: 'client', label: 'Client' },
  { key: 'tracker', label: 'Tracker' },
  { key: 'http', label: 'HTTP' },
  { key: 'system', label: 'System' },
];

const sourceBadge: Record<string, string> = {
  app: 'var(--blue)',
  http: 'var(--fg-3)',
  upload: 'var(--accent)',
  client: 'var(--purple, #a78bfa)',
  tracker: 'var(--teal, #5eead4)',
  wizard: 'var(--accent)',
  unit3dup: 'var(--yellow)',
  system: 'var(--fg-3)',
};

const ALL_KINDS: LogKind[] = ['info', 'ok', 'warn', 'error', 'debug'];

function normalizeSource(s: string | undefined): string {
  return s || 'app';
}

const LS_SOURCES = 'itatorrents.logs.hiddenSources';
const LS_KINDS = 'itatorrents.logs.hiddenKinds';
const LS_AUTO = 'itatorrents.logs.autoScroll';

function loadSet<T extends string>(key: string, fallback: T[]): Set<T> {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return new Set(fallback);
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed as T[]);
  } catch { /* ignore */ }
  return new Set(fallback);
}

function loadBool(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return raw === 'true';
  } catch {
    return fallback;
  }
}

export function LogsView() {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState<boolean>(() => loadBool(LS_AUTO, true));
  const [search, setSearch] = useState('');
  // Default: hide 'http' (still noisy even after backend fix) to keep the tail readable.
  const [hiddenSources, setHiddenSources] = useState<Set<string>>(() => loadSet<string>(LS_SOURCES, ['http']));
  // Default: hide 'debug' so unit3dup decorative lines stay folded.
  const [hiddenKinds, setHiddenKinds] = useState<Set<LogKind>>(() => loadSet<LogKind>(LS_KINDS, ['debug']));
  const boxRef = useRef<HTMLDivElement>(null);
  const bufferRef = useRef<LogLine[]>([]);
  const pausedRef = useRef(false);

  useEffect(() => { pausedRef.current = paused; }, [paused]);

  useEffect(() => {
    const close = openSSE('/api/logs/stream', {
      onEvent: (name, data) => {
        if (name !== 'line') return;
        try {
          const entry = JSON.parse(data) as LogLine;
          bufferRef.current = [...bufferRef.current.slice(-1999), entry];
          if (!pausedRef.current) setLines(bufferRef.current);
        } catch { /* ignore */ }
      },
    });
    return close;
  }, []);

  // Flush buffer on unpause so user catches up with everything that streamed while paused.
  useEffect(() => {
    if (!paused) setLines(bufferRef.current);
  }, [paused]);

  useEffect(() => {
    try { localStorage.setItem(LS_SOURCES, JSON.stringify([...hiddenSources])); } catch { /* ignore */ }
  }, [hiddenSources]);
  useEffect(() => {
    try { localStorage.setItem(LS_KINDS, JSON.stringify([...hiddenKinds])); } catch { /* ignore */ }
  }, [hiddenKinds]);
  useEffect(() => {
    try { localStorage.setItem(LS_AUTO, String(autoScroll)); } catch { /* ignore */ }
  }, [autoScroll]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return lines.filter((l) => {
      if (hiddenSources.has(normalizeSource(l.source))) return false;
      if (hiddenKinds.has(l.kind)) return false;
      if (q && !l.msg.toLowerCase().includes(q) && !l.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [lines, search, hiddenSources, hiddenKinds]);

  useEffect(() => {
    if (!autoScroll) return;
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [visible, autoScroll]);

  const toggleSource = (s: string) => {
    setHiddenSources((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s); else next.add(s);
      return next;
    });
  };
  const toggleKind = (k: LogKind) => {
    setHiddenKinds((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  };
  const clear = () => {
    bufferRef.current = [];
    setLines([]);
  };

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
      <div
        style={{
          display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center',
          padding: '10px 12px', background: 'var(--bg-elev)',
          border: '1px solid var(--border)', borderRadius: 8,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {SOURCES.map((s) => {
            const active = !hiddenSources.has(s.key);
            return (
              <button
                key={s.key}
                onClick={() => toggleSource(s.key)}
                style={{
                  padding: '4px 10px', borderRadius: 999, fontSize: 12,
                  border: `1px solid ${active ? sourceBadge[s.key] : 'var(--border)'}`,
                  background: active ? `${sourceBadge[s.key]}22` : 'transparent',
                  color: active ? sourceBadge[s.key] : 'var(--fg-3)',
                  cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}
              >
                {s.label}
              </button>
            );
          })}
        </div>

        <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />

        <div style={{ display: 'flex', gap: 6 }}>
          {ALL_KINDS.map((k) => {
            const active = !hiddenKinds.has(k);
            return (
              <button
                key={k}
                onClick={() => toggleKind(k)}
                style={{
                  padding: '4px 8px', borderRadius: 4, fontSize: 11,
                  border: `1px solid ${active ? kindColors[k] : 'var(--border)'}`,
                  background: active ? `${kindColors[k]}22` : 'transparent',
                  color: active ? kindColors[k] : 'var(--fg-3)',
                  cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}
              >
                {k}
              </button>
            );
          })}
        </div>

        <div style={{ flex: 1 }} />

        <input
          type="search"
          placeholder="Cerca…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 12,
            border: '1px solid var(--border)', background: 'var(--bg-base)',
            color: 'var(--fg-1)', minWidth: 160, fontFamily: 'var(--font-mono)',
          }}
        />
        <button
          onClick={() => setPaused((p) => !p)}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
            border: '1px solid var(--border)',
            background: paused ? 'var(--yellow)22' : 'var(--bg-base)',
            color: paused ? 'var(--yellow)' : 'var(--fg-2)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {paused ? 'Resume' : 'Pause'}
        </button>
        <button
          onClick={() => setAutoScroll((a) => !a)}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
            border: '1px solid var(--border)',
            background: autoScroll ? 'var(--bg-base)' : 'var(--bg-elev)',
            color: 'var(--fg-2)', fontFamily: 'var(--font-mono)',
          }}
        >
          Auto {autoScroll ? 'on' : 'off'}
        </button>
        <button
          onClick={clear}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
            border: '1px solid var(--border)', background: 'var(--bg-base)',
            color: 'var(--fg-3)', fontFamily: 'var(--font-mono)',
          }}
        >
          Clear
        </button>
      </div>

      <div
        ref={boxRef}
        style={{
          background: 'var(--bg-base)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '16px 20px',
          fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.9,
          maxHeight: 'calc(100vh - 210px)', overflow: 'auto', flex: 1, minHeight: 0,
        }}
      >
        {visible.length === 0 && (
          <div style={{ color: 'var(--fg-3)' }}>
            {lines.length === 0 ? 'Waiting for log output…' : 'Nessuna riga corrisponde ai filtri.'}
          </div>
        )}
        {visible.map((l, i) => {
          const src = normalizeSource(l.source);
          const badgeColor = sourceBadge[src] ?? 'var(--fg-3)';
          return (
            <div
              key={i}
              style={{
                color: kindColors[l.kind] ?? 'var(--fg-2)',
                display: 'flex', gap: 8, alignItems: 'baseline',
              }}
            >
              <span style={{ color: 'var(--fg-4)', minWidth: 32 }}>
                {String(i + 1).padStart(3, '0')}
              </span>
              <span style={{ color: 'var(--fg-3)', minWidth: 42 }}>
                {kindPrefixes[l.kind] ?? '[   ]'}
              </span>
              <span style={{ color: 'var(--fg-3)', minWidth: 64 }}>
                {l.ts}
              </span>
              <span
                style={{
                  display: 'inline-block',
                  padding: '0 6px',
                  borderRadius: 4,
                  fontSize: 10,
                  lineHeight: 1.5,
                  background: `${badgeColor}22`,
                  color: badgeColor,
                  border: `1px solid ${badgeColor}44`,
                  minWidth: 60,
                  textAlign: 'center',
                }}
              >
                {src}
              </span>
              {l.event && (
                <span style={{ color: 'var(--fg-4)', fontSize: 10 }}>
                  {l.event}
                </span>
              )}
              <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', flex: 1 }}>
                {l.msg}
                {l.count && l.count > 1 && (
                  <span style={{ color: 'var(--fg-4)', marginLeft: 8 }}>×{l.count}</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
