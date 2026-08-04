import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bookmark, BookmarkX } from 'lucide-react';
import { api } from '../api';
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
  const title = t(labelKeyFor(target.kind));

  const run = async () => {
    if (done || busy) return;
    setBusy(true);
    try {
      await api.post('/api/arr/unmonitor', {
        kind: target.kind,
        path: 'path' in target ? target.path : '',
        season_number: target.kind === 'season' ? target.seasonNumber : null,
        episode_ids: target.kind === 'episodes' ? target.episodeIds : [],
      });
      setDone(true);
      onDone?.();
    } catch { /* the failure is already in the server-side logs */ }
    setBusy(false);
  };

  if (variant === 'icon') {
    return (
      <button
        onClick={run}
        disabled={done || busy}
        title={title}
        aria-label={title}
        style={{
          ...ICON_BTN,
          borderColor: done ? 'var(--green)' : 'var(--border)',
          color: done ? 'var(--green)' : 'var(--fg-3)',
        }}
      ><BookmarkX size={13} /></button>
    );
  }

  if (variant === 'chip') {
    return (
      <button
        onClick={run}
        disabled={done || busy}
        title={title}
        style={{
          background: 'transparent',
          border: '1px solid var(--border)', borderRadius: 4,
          padding: '2px 5px', fontSize: 9, fontWeight: 700,
          color: done ? 'var(--green)' : 'var(--fg-3)',
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
      style={{
        width: '100%', background: 'transparent',
        border: '1px solid var(--border)', borderRadius: 6,
        padding: 8, fontSize: 11, fontWeight: 600,
        color: done ? 'var(--green)' : 'var(--fg-2)',
        cursor: done || busy ? 'default' : 'pointer',
        fontFamily: 'var(--font-display)', marginBottom: 6,
      }}
    >{done ? t('arr.unmonitored') : title}</button>
  );
}
