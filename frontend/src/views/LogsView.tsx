import { useEffect, useRef, useState } from 'react';
import { openSSE } from '../api';
import type { LogLine } from '../types';

const colors: Record<string, string> = {
  info: 'var(--blue-bright)',
  ok: 'var(--green)',
  warn: 'var(--yellow)',
  error: 'var(--red)',
  debug: 'var(--fg-3)',
};
const prefixes: Record<string, string> = {
  info: '[log] ',
  ok: '[ok]  ',
  warn: '[warn]',
  error: '[err] ',
  debug: '[dbg]',
};

export function LogsView() {
  const [lines, setLines] = useState<LogLine[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // History + live stream via SSE (backend replays history on connect).
    const close = openSSE('/api/logs/stream', {
      onEvent: (name, data) => {
        if (name !== 'line') return;
        try {
          const entry = JSON.parse(data) as LogLine;
          setLines((prev) => [...prev.slice(-999), entry]);
        } catch { /* ignore */ }
      },
    });
    return close;
  }, []);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines]);

  return (
    <div style={{ padding: 24 }}>
      <div
        ref={boxRef}
        style={{
          background: 'var(--bg-base)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '16px 20px',
          fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.9,
          maxHeight: 'calc(100vh - 150px)', overflow: 'auto',
        }}
      >
        {lines.length === 0 && (
          <div style={{ color: 'var(--fg-3)' }}>Waiting for log output…</div>
        )}
        {lines.map((l, i) => (
          <div key={i} style={{ color: colors[l.kind] ?? 'var(--fg-2)' }}>
            <span style={{ color: 'var(--fg-4)', marginRight: 8 }}>
              {String(i + 1).padStart(3, '0')}
            </span>
            <span style={{ color: 'var(--fg-3)', marginRight: 12 }}>
              {prefixes[l.kind] ?? '[   ]'}
            </span>
            <span style={{ color: 'var(--fg-3)', marginRight: 8 }}>{l.ts}</span>
            <span style={{ color: 'var(--fg-4)', marginRight: 8 }}>{l.name}</span>
            {l.msg}
          </div>
        ))}
      </div>
    </div>
  );
}
