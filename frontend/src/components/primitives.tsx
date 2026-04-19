import type { CSSProperties, ReactNode } from 'react';

export function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        width: 30, height: 17, borderRadius: 9999,
        background: on ? 'var(--blue)' : 'var(--border)',
        cursor: 'pointer', position: 'relative',
        transition: 'background 150ms', border: 'none', flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: 2, left: on ? 12 : 2,
        width: 13, height: 13, borderRadius: '50%',
        background: '#fff', transition: 'left 150ms',
      }} />
    </button>
  );
}

export function LangChip({ lang }: { lang: string }) {
  const isIta = lang === 'ITA';
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 3,
      background: isIta ? 'var(--green-dim)' : 'var(--bg-card)',
      color: isIta ? 'var(--green)' : 'var(--fg-2)',
      border: `1px solid ${isIta ? 'var(--green)' : 'var(--border)'}`,
      fontFamily: 'var(--font-mono)', marginRight: 3,
    }}>{lang}</span>
  );
}

export function Badge({
  children, color = 'var(--green)', bg = 'var(--green-dim)', style,
}: {
  children: ReactNode;
  color?: string;
  bg?: string;
  style?: CSSProperties;
}) {
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, padding: '2px 5px', borderRadius: 3,
      background: bg, color, border: `1px solid ${color}`,
      fontFamily: 'var(--font-display)', ...style,
    }}>{children}</span>
  );
}

const STATUS_MAP: Record<string, { bg: string; color: string; label: string }> = {
  seeding:   { bg: 'var(--green-dim)',  color: 'var(--green)',     label: 'Seeding' },
  uploading: { bg: 'var(--blue-dim)',   color: 'var(--blue-bright)', label: 'Uploading' },
  queued:    { bg: 'var(--yellow-dim)', color: 'var(--yellow)',    label: 'Queued' },
  paused:    { bg: 'var(--bg-card)',    color: 'var(--fg-2)',      label: 'Paused' },
  error:     { bg: 'var(--red-dim)',    color: 'var(--red)',       label: 'Error' },
  pending:   { bg: 'var(--bg-card)',    color: 'var(--fg-3)',      label: 'Pending' },
};

export function StatusPill({ status }: { status: string }) {
  const m = STATUS_MAP[status] ?? STATUS_MAP.pending;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 10, fontWeight: 600, padding: '2px 9px', borderRadius: 9999,
      background: m.bg, color: m.color,
      fontFamily: 'var(--font-display)',
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: '50%',
        background: m.color, display: 'inline-block',
      }} />
      {m.label}
    </span>
  );
}

export const BTN_PRIMARY: CSSProperties = {
  background: 'var(--blue)', border: 'none', color: '#fff',
  padding: '8px 18px', borderRadius: 6, fontSize: 12,
  fontWeight: 600, cursor: 'pointer',
  fontFamily: 'var(--font-display)',
};

export const BTN_SECONDARY: CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '6px 14px', fontSize: 12,
  fontWeight: 600, cursor: 'pointer', color: 'var(--fg-2)',
  fontFamily: 'var(--font-display)',
};

export const INPUT_CSS: CSSProperties = {
  width: '100%', background: 'var(--bg-card)',
  border: '1px solid var(--border)', borderRadius: 6,
  padding: '7px 10px', fontSize: 12, color: 'var(--fg-1)',
  fontFamily: 'var(--font-mono)',
  outline: 'none', boxSizing: 'border-box',
};

export const LABEL_CSS: CSSProperties = {
  fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600,
  color: 'var(--fg-3)', letterSpacing: 'var(--tracking-wide)',
  textTransform: 'uppercase', marginBottom: 5, display: 'block',
};

export const GROUP_LABEL: CSSProperties = {
  fontSize: 10, fontWeight: 600, color: 'var(--fg-4)',
  letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
  fontFamily: 'var(--font-display)', marginBottom: 10,
  paddingBottom: 6, borderBottom: '1px solid var(--border-subtle)',
  marginTop: 16,
};
