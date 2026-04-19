import { useEffect, useMemo, useState } from 'react';
import { Film, Tv, Sparkles, RefreshCw, Database, Headphones } from 'lucide-react';
import { api, openSSE } from '../api';
import type { Category, LibraryItem, Season, WizardCtx } from '../types';
import { LangChip, Badge } from '../components/primitives';

const CATS: { id: Category; label: string; icon: any }[] = [
  { id: 'movies', label: 'Movies', icon: Film },
  { id: 'series', label: 'Series', icon: Tv },
  { id: 'anime',  label: 'Anime',  icon: Sparkles },
];

const gradient = (seed: string) => {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) | 0;
  const hue = Math.abs(h) % 360;
  return `linear-gradient(160deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.75) 100%), `
    + `linear-gradient(135deg, hsl(${hue} 40% 22%) 0%, var(--bg-base) 100%)`;
};

const posterBg = (item: LibraryItem) =>
  item.tmdb_poster
    ? `linear-gradient(160deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.75) 100%), url("${item.tmdb_poster}") center/cover`
    : gradient(item.name);

export function LibraryView({ onStartWizard }: { onStartWizard: (c: WizardCtx) => void }) {
  const [category, setCategory] = useState<Category>('movies');
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [hideUploaded, setHideUploaded] = useState(true);
  const [search, setSearch] = useState('');
  const [enriching, setEnriching] = useState(false);
  const [scanning, setScanning] = useState(false);

  const load = async (cat: Category) => {
    setLoading(true); setSelected(null);
    try {
      const r = await api.get<{ items: LibraryItem[] }>(`/api/library/${cat}`);
      setItems(r.items);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(category); }, [category]);

  const filtered = useMemo(() => items.filter((it) => {
    if (search && !it.title.toLowerCase().includes(search.toLowerCase())
        && !it.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (!hideUploaded) return true;
    if (it.seasons) return !(it.all_seasons_uploaded);
    return !it.already_uploaded;
  }), [items, search, hideUploaded]);

  const needTmdb = filtered.filter((i) => !i.tmdb_id).length;
  const needLangs = filtered.filter((i) => !i.lang_scanned).length;

  const runEnrich = () => {
    setEnriching(true);
    const close = openSSE(`/api/library/${category}/enrich`, {
      onEvent: (name) => {
        if (name === 'done') { close(); setEnriching(false); load(category); }
      },
      onError: () => { close(); setEnriching(false); },
    });
  };

  const runScanLangs = () => {
    setScanning(true);
    const close = openSSE(`/api/library/${category}/scan-langs`, {
      onEvent: (name) => {
        if (name === 'done') { close(); setScanning(false); load(category); }
      },
      onError: () => { close(); setScanning(false); },
    });
  };

  const startWizard = (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => {
    if (!selected) return;
    onStartWizard({
      kind,
      path,
      category,
      tmdbId: selected.tmdb_id,
      title: selected.tmdb_title_en || selected.title,
      year: selected.year,
      name: selected.name,
      overview: selected.tmdb_overview,
      season: season ? { n: season.number, path: season.path, episodes: season.episode_count } : undefined,
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '12px 18px', borderBottom: '1px solid var(--border-subtle)',
        background: '#0a0c12', display: 'flex', alignItems: 'center',
        gap: 10, flexShrink: 0, flexWrap: 'wrap',
      }}>
        <div style={{
          display: 'flex', gap: 3, background: 'var(--bg-card)',
          borderRadius: 6, padding: 3, border: '1px solid var(--border)',
        }}>
          {CATS.map((c) => {
            const Icon = c.icon;
            const active = category === c.id;
            return (
              <button
                key={c.id}
                onClick={() => setCategory(c.id)}
                style={{
                  padding: '6px 12px', borderRadius: 4, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 12, fontWeight: 600,
                  fontFamily: 'var(--font-display)',
                  background: active ? 'var(--blue)' : 'transparent',
                  color: active ? '#fff' : 'var(--fg-2)',
                  border: 'none',
                }}
              >
                <Icon size={12} />{c.label}
              </button>
            );
          })}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by title…"
          style={{
            flex: 1, minWidth: 180, background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '6px 10px', fontSize: 12, color: 'var(--fg-1)',
            fontFamily: 'var(--font-mono)',
          }}
        />
        <button
          disabled={scanning}
          onClick={() => load(category)}
          style={actionBtn}
        >
          <RefreshCw size={11} style={{ animation: loading ? 'spin 1s linear infinite' : '' }} />
          {loading ? 'Scanning…' : 'Rescan'}
        </button>
        <button disabled={enriching} onClick={runEnrich} style={actionBtn}>
          <Database size={11} />
          {enriching ? 'Enriching…' : 'Auto-TMDB'}
        </button>
        <button disabled={scanning} onClick={runScanLangs} style={actionBtn}>
          <Headphones size={11} />
          {scanning ? 'Scanning…' : 'Scan Langs'}
        </button>
      </div>

      <div style={{
        padding: '8px 18px', display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: '1px solid var(--border-subtle)',
        background: '#0a0c12', flexShrink: 0,
      }}>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
            fontSize: 11, fontWeight: 600, color: 'var(--fg-2)',
            fontFamily: 'var(--font-display)',
          }}
          onClick={() => setHideUploaded(!hideUploaded)}
        >
          <div style={{
            width: 14, height: 14, borderRadius: 3,
            border: `1px solid ${hideUploaded ? 'var(--blue)' : 'var(--border)'}`,
            background: hideUploaded ? 'var(--blue)' : 'var(--bg-card)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 9, color: '#fff',
          }}>{hideUploaded && '✓'}</div>
          Hide already uploaded
        </div>
        {needTmdb > 0 && (
          <span style={warnChip}>⚠ {needTmdb} without TMDB match</span>
        )}
        {needLangs > 0 && (
          <span style={warnChip}>⚠ {needLangs} need lang scan</span>
        )}
        <span style={{
          marginLeft: 'auto', fontSize: 11, color: 'var(--fg-3)',
          fontFamily: 'var(--font-display)',
        }}>{filtered.length} of {items.length} titles</span>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{
          flex: 1, display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
          gridAutoRows: 'min-content',
          gap: 10, padding: '14px 18px', overflowY: 'auto', alignContent: 'start',
        }}>
          {filtered.map((item) => {
            const isSeries = !!item.seasons;
            const uploaded = isSeries
              ? item.seasons!.filter((s) => s.already_uploaded || s.all_episodes_uploaded).length
              : 0;
            const totalSeasons = isSeries ? item.seasons!.length : 0;
            const selectedHere = selected?.path === item.path;
            return (
              <div
                key={item.path}
                onClick={() => setSelected(item)}
                style={{
                  background: 'var(--bg-card)',
                  border: selectedHere
                    ? '1px solid var(--blue)'
                    : '1px solid var(--border)',
                  borderRadius: 6, overflow: 'hidden', cursor: 'pointer',
                  transition: 'all 150ms',
                  display: 'flex', flexDirection: 'column',
                }}
              >
                <div style={{
                  aspectRatio: '2/3', background: posterBg(item),
                  position: 'relative', display: 'flex', alignItems: 'flex-end',
                  padding: 8,
                }}>
                  <div style={{
                    position: 'absolute', top: 6, left: 6,
                    display: 'flex', gap: 3, flexWrap: 'wrap', maxWidth: '65%',
                  }}>
                    {item.langs.slice(0, 2).map((l) => <LangChip key={l} lang={l} />)}
                    {!item.lang_scanned && !item.langs.length && (
                      <Badge color="var(--yellow)" bg="rgba(245,166,35,0.15)">? langs</Badge>
                    )}
                  </div>
                  <div style={{ position: 'absolute', top: 6, right: 6 }}>
                    {item.tmdb_id
                      ? <Badge>TMDB ✓</Badge>
                      : <Badge color="var(--red)" bg="var(--red-dim)">no TMDB</Badge>}
                  </div>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 700,
                    color: 'rgba(255,255,255,0.85)', lineHeight: 1.3,
                    textShadow: '0 1px 3px rgba(0,0,0,0.8)',
                  }}>
                    {item.title}
                    {item.year && <span style={{ opacity: 0.7 }}> · {item.year}</span>}
                  </div>
                </div>
                <div style={{ padding: '7px 10px' }}>
                  <div style={{
                    fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
                    color: 'var(--fg-1)', marginBottom: 3,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>{item.title}</div>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', fontSize: 10,
                    fontFamily: 'var(--font-mono)',
                  }}>
                    {isSeries ? (
                      <>
                        <span style={{
                          color: uploaded === totalSeasons ? 'var(--green)'
                            : uploaded > 0 ? 'var(--yellow)' : 'var(--fg-3)',
                        }}>{uploaded}/{totalSeasons} seasons</span>
                        <span style={{ color: 'var(--fg-4)' }}>
                          {item.seasons!.reduce((a, s) => a + s.episode_count, 0)} ep
                        </span>
                      </>
                    ) : (
                      <span style={{
                        color: item.already_uploaded ? 'var(--green)' : 'var(--fg-3)',
                      }}>{item.already_uploaded ? '✓ uploaded' : item.size}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          {!loading && filtered.length === 0 && (
            <div style={{
              gridColumn: '1/-1', padding: '60px 20px', textAlign: 'center',
              color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
            }}>
              <div style={{ fontSize: 48, marginBottom: 10, opacity: 0.3 }}>∅</div>
              Nothing to show. {hideUploaded && 'Try unchecking "Hide already uploaded".'}
            </div>
          )}
        </div>

        {selected && (
          <DetailPanel
            item={selected}
            category={category}
            onStart={startWizard}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
    </div>
  );
}

function DetailPanel({
  item, category, onStart,
}: {
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onClose: () => void;
}) {
  return (
    <div style={{
      width: 360, borderLeft: '1px solid var(--border-subtle)',
      display: 'flex', flexDirection: 'column', background: '#0a0c12',
      overflowY: 'auto', flexShrink: 0,
    }}>
      <div style={{
        height: 200, background: posterBg(item),
        display: 'flex', alignItems: 'flex-end', padding: 14, flexShrink: 0,
      }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700,
            color: '#fff', lineHeight: 1.2,
            textShadow: '0 2px 5px rgba(0,0,0,0.8)',
          }}>{item.title}</div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: 'rgba(255,255,255,0.7)', marginTop: 4,
          }}>{item.year}</div>
        </div>
      </div>
      <div style={{ padding: 16, flex: 1 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '8px 10px', background: 'var(--bg-card)',
          borderRadius: 6, border: '1px solid var(--border)', marginBottom: 10,
          fontSize: 11, fontFamily: 'var(--font-mono)',
        }}>
          <span style={{ color: 'var(--fg-3)' }}>TMDB</span>
          <span style={{ color: 'var(--blue-bright)', fontWeight: 600 }}>
            {item.tmdb_id || 'not matched'}
          </span>
          <span style={{
            marginLeft: 'auto',
            color: item.tmdb_id ? 'var(--green)' : 'var(--yellow)',
            fontWeight: 600,
          }}>{item.tmdb_id ? '✓' : 'manual'}</span>
        </div>
        {item.tmdb_overview && (
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 12,
            color: 'var(--fg-3)', lineHeight: 1.6, marginBottom: 12,
          }}>{item.tmdb_overview}</div>
        )}

        <SectionHeader title="Audio Languages" rightNote={item.lang_scanned ? 'cached' : ''} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginBottom: 10 }}>
          {item.langs.length
            ? item.langs.map((l) => <LangChip key={l} lang={l} />)
            : <span style={{
                fontSize: 11, color: 'var(--yellow)',
                fontFamily: 'var(--font-display)',
              }}>Not scanned yet · click Scan Langs</span>}
        </div>

        <SectionHeader title="Source Path" />
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-2)',
          background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
          borderRadius: 4, padding: '6px 8px', marginBottom: 8, wordBreak: 'break-all',
        }}>{item.path}</div>

        {item.seasons ? (
          <>
            <SectionHeader title="Seasons & Episodes" right={
              <button
                onClick={() => onStart('series', item.path)}
                style={{
                  background: 'var(--blue)', border: 'none', borderRadius: 4,
                  padding: '3px 7px', fontSize: 10, fontWeight: 600,
                  color: '#fff', cursor: 'pointer',
                  fontFamily: 'var(--font-display)',
                }}
              >Upload all seasons →</button>
            }/>
            {item.seasons.map((s) => <SeasonRow key={s.number} season={s} item={item} category={category} onStart={onStart} />)}
          </>
        ) : (
          <>
            <SectionHeader title="Files" />
            {item.video_files?.map((vf) => (
              <div key={vf.path} style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: vf.uploaded ? 'var(--green)' : 'var(--fg-2)',
                marginBottom: 4, wordBreak: 'break-all',
              }}>{vf.uploaded ? '✓' : '·'} {vf.name}</div>
            ))}
            <button
              disabled={item.already_uploaded}
              onClick={() => onStart('movie', item.path)}
              style={{
                width: '100%', background: item.already_uploaded ? 'var(--border)' : 'var(--blue)',
                border: 'none', borderRadius: 6, padding: 10,
                fontSize: 12, fontWeight: 600, color: '#fff',
                cursor: item.already_uploaded ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-display)', marginTop: 8, marginBottom: 6,
              }}
            >
              {item.already_uploaded ? 'Already uploaded' : 'Start upload wizard →'}
            </button>
            <MarkUploadedBtn category={category} name={item.name} />
          </>
        )}
      </div>
    </div>
  );
}

function SeasonRow({
  season, item, category, onStart,
}: {
  season: Season;
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
}) {
  const pct = Math.round((season.uploaded_episodes / Math.max(1, season.episode_count)) * 100);
  return (
    <div style={{
      padding: '8px 10px', background: 'var(--bg-card)',
      borderRadius: 6, border: '1px solid var(--border)', marginBottom: 6,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', marginBottom: 5,
      }}>
        <div>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
            color: 'var(--fg-1)',
          }}>{season.label}</span>
          {season.already_uploaded && (
            <span style={{ marginLeft: 6 }}><Badge>uploaded ✓</Badge></span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {!season.already_uploaded && (
            <button
              onClick={() => onStart('series', season.path, season)}
              style={{
                background: 'var(--blue)', border: 'none', borderRadius: 4,
                padding: '3px 7px', fontSize: 10, fontWeight: 600,
                color: '#fff', cursor: 'pointer',
                fontFamily: 'var(--font-display)',
              }}
            >Bulk upload season</button>
          )}
        </div>
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
      }}>
        {season.episode_count} ep · {season.size}
        {season.langs.length > 0 && <span style={{ marginLeft: 8 }}>{season.langs.join(' / ')}</span>}
        {!season.langs.length && <span style={{ marginLeft: 8, color: 'var(--yellow)' }}>? langs</span>}
      </div>
      {!season.already_uploaded && season.uploaded_episodes > 0 && (
        <>
          <div style={{
            height: 2, background: 'var(--bg-base)', borderRadius: 9999,
            overflow: 'hidden', marginTop: 5,
          }}>
            <div style={{
              height: '100%', background: 'var(--yellow)',
              width: `${pct}%`, borderRadius: 9999,
            }}/>
          </div>
          <div style={{
            fontSize: 9, color: 'var(--yellow)',
            fontFamily: 'var(--font-mono)', marginTop: 3,
          }}>{season.uploaded_episodes}/{season.episode_count} episodes uploaded</div>
        </>
      )}
      {!season.already_uploaded && (
        <div style={{ marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {season.video_files.map((vf) => (
            <button
              key={vf.path}
              disabled={vf.uploaded}
              onClick={() => !vf.uploaded && onStart('episode', vf.path, season)}
              style={{
                background: 'var(--bg-base)',
                border: '1px solid var(--border)', borderRadius: 4,
                padding: '2px 5px', fontSize: 9, fontWeight: 600,
                color: vf.uploaded ? 'var(--green)' : 'var(--fg-2)',
                cursor: vf.uploaded ? 'default' : 'pointer',
                fontFamily: 'var(--font-display)',
                opacity: vf.uploaded ? 0.4 : 1,
              }}
            >{vf.uploaded ? '✓ ' : ''}{vf.name.replace(/\.[^.]+$/, '').slice(0, 14)}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function MarkUploadedBtn({ category, name }: { category: Category; name: string }) {
  const [done, setDone] = useState(false);
  const mark = async () => {
    try {
      await api.post(`/api/library/${category}/${encodeURIComponent(name)}/mark-uploaded`, {});
      setDone(true);
    } catch { /* ignore */ }
  };
  return (
    <button
      onClick={mark}
      disabled={done}
      style={{
        width: '100%', background: 'transparent',
        border: '1px solid var(--border)', borderRadius: 6,
        padding: 8, fontSize: 11, fontWeight: 600,
        color: done ? 'var(--green)' : 'var(--fg-2)',
        cursor: done ? 'default' : 'pointer',
        fontFamily: 'var(--font-display)', marginBottom: 6,
      }}
    >{done ? '✓ Marked' : 'Mark as uploaded manually'}</button>
  );
}

function SectionHeader({ title, right, rightNote }: {
  title: string;
  right?: React.ReactNode;
  rightNote?: string;
}) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700,
      letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
      color: 'var(--fg-4)', marginBottom: 8, marginTop: 12,
      paddingBottom: 4, borderBottom: '1px solid var(--border-subtle)',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    }}>
      <span>{title} {rightNote && (
        <span style={{
          color: 'var(--fg-3)', fontWeight: 400, textTransform: 'none',
          letterSpacing: 0, marginLeft: 6,
        }}>{rightNote}</span>
      )}</span>
      {right}
    </div>
  );
}

const actionBtn: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '6px 12px', fontSize: 11, fontWeight: 600,
  color: 'var(--fg-2)', cursor: 'pointer',
  fontFamily: 'var(--font-display)',
  display: 'flex', alignItems: 'center', gap: 5,
};

const warnChip: React.CSSProperties = {
  fontSize: 10, fontWeight: 600, padding: '3px 8px', borderRadius: 4,
  background: 'rgba(245,166,35,0.1)', color: 'var(--yellow)',
  border: '1px solid var(--yellow)', fontFamily: 'var(--font-display)',
};
