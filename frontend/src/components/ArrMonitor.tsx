import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bookmark, BookmarkX } from 'lucide-react';
import { api, ApiError } from '../api';
import { Badge, ICON_BTN } from './primitives';

/** What a monitoring removal acts on. */
export type ArrTarget =
  | { kind: 'movie'; path: string }
  | { kind: 'series'; path: string }
  | { kind: 'season'; path: string; seasonNumber: number }
  | { kind: 'episodes'; episodeIds: number[] };

/**
 * Shown only when the item is monitored: anything unmonitored, or absent from
 * Radarr/Sonarr, renders nothing — so the grid highlights exactly what is left
 * to do.
 */
export function MonitorBadge({ monitored }: { monitored?: boolean }) {
  const { t } = useTranslation();
  if (!monitored) return null;
  return (
    <Badge color="var(--blue)" bg="rgba(74,144,226,0.15)">
      <Bookmark size={8} fill="var(--blue)" style={{ marginRight: 2, verticalAlign: '-1px' }} />
      {t('arr.monitoredBadge')}
    </Badge>
  );
}

function labelKeyFor(kind: ArrTarget['kind']): string {
  if (kind === 'movie') return 'arr.unmonitorMovie';
  if (kind === 'series') return 'arr.unmonitorSeries';
  if (kind === 'season') return 'arr.unmonitorSeason';
  return 'arr.unmonitorEpisode';
}

/**
 * Value-stable identity for a target, used to reset local state when this
 * component instance gets reused for a different item. `target` itself is a
 * fresh object literal on every parent render, so it can't be a dependency
 * directly — that would fire the reset effect on every render, including the
 * one right after a successful `run()`, wiping out `done` before the user
 * ever saw it.
 */
function targetKey(target: ArrTarget): string {
  if (target.kind === 'episodes') return `episodes:${target.episodeIds.join(',')}`;
  if (target.kind === 'season') return `season:${target.path}:${target.seasonNumber}`;
  return `${target.kind}:${target.path}`;
}

export function UnmonitorBtn({
  target, variant = 'full', onDone,
}: {
  target: ArrTarget;
  variant?: 'full' | 'icon' | 'chip';
  onDone?: () => void;
}) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const title = t(labelKeyFor(target.kind));

  // The grid re-renders this component at the same JSX position for whatever
  // item is selected now, not necessarily the one `run()` was called for —
  // e.g. the user picks a different card while the POST is in flight. Without
  // this, the new item's button would inherit the previous item's `done`
  // (permanently disabled) or `err` (stale failure message).
  const key = targetKey(target);
  useEffect(() => {
    setDone(false);
    setErr(null);
  }, [key]);

  const run = async () => {
    if (done || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await api.post('/api/arr/unmonitor', {
        kind: target.kind,
        path: 'path' in target ? target.path : '',
        season_number: target.kind === 'season' ? target.seasonNumber : null,
        episode_ids: target.kind === 'episodes' ? target.episodeIds : [],
      });
      setDone(true);
      onDone?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t('arr.unmonitorFailed'));
    }
    setBusy(false);
  };

  if (variant === 'icon') {
    return (
      <button
        onClick={run}
        disabled={done || busy}
        title={err || title}
        aria-label={title}
        style={{
          ...ICON_BTN,
          borderColor: err ? 'var(--red)' : done ? 'var(--green)' : 'var(--border)',
          color: err ? 'var(--red)' : done ? 'var(--green)' : 'var(--fg-3)',
        }}
      ><BookmarkX size={13} /></button>
    );
  }

  if (variant === 'chip') {
    return (
      <button
        onClick={run}
        disabled={done || busy}
        title={err || title}
        style={{
          background: 'transparent',
          border: '1px solid var(--border)', borderRadius: 4,
          padding: '2px 5px', fontSize: 9, fontWeight: 700,
          color: err ? 'var(--red)' : done ? 'var(--green)' : 'var(--fg-3)',
          cursor: done || busy ? 'default' : 'pointer',
          fontFamily: 'var(--font-display)',
          minWidth: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >{done ? '✓' : <BookmarkX size={10} />}</button>
    );
  }

  return (
    <button
      onClick={run}
      disabled={done || busy}
      title={err || undefined}
      style={{
        width: '100%', background: 'transparent',
        border: '1px solid var(--border)', borderRadius: 6,
        padding: 8, fontSize: 11, fontWeight: 600,
        color: err ? 'var(--red)' : done ? 'var(--green)' : 'var(--fg-2)',
        cursor: done || busy ? 'default' : 'pointer',
        fontFamily: 'var(--font-display)', marginBottom: 6,
      }}
    >{err || (done ? t('arr.unmonitored') : title)}</button>
  );
}
