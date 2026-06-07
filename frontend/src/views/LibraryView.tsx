import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Film, Tv, Sparkles, RefreshCw, Database, Headphones,
  Pencil, X, Search as SearchIcon, Star,
  ChevronDown, Folder, BookOpen, Music, Library as LibraryIcon,
  CheckSquare, Square,
} from 'lucide-react';
import { api, openSSE } from '../api';
import type { Category, LibraryItem, Season, WizardCtx } from '../types';
import { LangChip, Badge } from '../components/primitives';

type SortKey = 'name' | 'year' | 'size';
type SortDir = 'asc' | 'desc';

const sizeToBytes = (s: string): number => {
  if (!s) return 0;
  const m = String(s).match(/([\d.]+)\s*(TB|GB|MB|KB|B)/i);
  if (!m) return 0;
  const n = parseFloat(m[1]);
  const u = m[2].toUpperCase();
  const mult: Record<string, number> = { TB: 1e12, GB: 1e9, MB: 1e6, KB: 1e3, B: 1 };
  return n * (mult[u] || 1);
};

interface TmdbSearchResult {
  id: number | string;
  title: string;
  year?: string;
  overview?: string;
  poster?: string;
  vote?: number;
}

interface CategoryInfo { id: string; label: string; count: number; }

const CATEGORY_ICON_MAP: Record<string, any> = {
  movies: Film, film: Film, movie: Film,
  series: Tv, tv: Tv, shows: Tv,
  anime: Sparkles,
  documentaries: BookOpen, documentary: BookOpen, docs: BookOpen,
  concerts: Music, concert: Music, music: Music,
};

const iconFor = (id: string) => {
  const key = id.toLowerCase();
  return CATEGORY_ICON_MAP[key] || Folder;
};

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

export function LibraryView({ onStartWizard, isMobile, refreshSignal }: { onStartWizard: (c: WizardCtx) => void; isMobile?: boolean; refreshSignal?: number }) {
  const { t } = useTranslation();
  const [category, setCategory] = useState<Category>('');
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [hideUploaded, setHideUploaded] = useState(true);
  const [hideNoItalian, setHideNoItalian] = useState(false);
  const [search, setSearch] = useState('');
  const [enriching, setEnriching] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [tmdbEditOpen, setTmdbEditOpen] = useState(false);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [mediaRoot, setMediaRoot] = useState('');
  const [catPickerOpen, setCatPickerOpen] = useState(false);
  const catBtnRef = useRef<HTMLDivElement | null>(null);
  const [bulkMode, setBulkMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkToast, setBulkToast] = useState<string | null>(null);

  const loadCategories = async () => {
    try {
      const r = await api.get<{
        root: string;
        root_exists: boolean;
        categories: CategoryInfo[];
      }>('/api/library/categories');
      setCategories(r.categories);
      setMediaRoot(r.root);
      if (!category && r.categories.length) {
        setCategory(r.categories[0].id);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    loadCategories();
    api.get<{ config: Record<string, any> }>('/api/settings')
      .then((s) => {
        const v = s.config?.W_HIDE_UPLOADED;
        if (typeof v === 'boolean') setHideUploaded(v);
        const vi = s.config?.W_HIDE_NO_ITALIAN;
        if (typeof vi === 'boolean') setHideNoItalian(vi);
      })
      .catch(() => { /* ignore */ });
  }, []);

  useEffect(() => {
    if (!catPickerOpen) return;
    const close = (e: MouseEvent) => {
      if (catBtnRef.current && !catBtnRef.current.contains(e.target as Node)) {
        setCatPickerOpen(false);
      }
    };
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [catPickerOpen]);

  const load = async (cat: Category) => {
    if (!cat) return;
    setLoading(true); setSelected(null);
    try {
      const r = await api.get<{ items: LibraryItem[] }>(`/api/library/${cat}`);
      setItems(r.items);
    } finally { setLoading(false); }
  };

  const reloadKeepSelection = async (cat: Category) => {
    if (!cat) return;
    try {
      const r = await api.get<{ items: LibraryItem[] }>(`/api/library/${cat}`);
      setItems(r.items);
      setSelected((prev) => {
        if (!prev) return prev;
        return r.items.find((it) => it.name === prev.name) ?? prev;
      });
    } catch { /* ignore */ }
  };

  useEffect(() => { if (category) load(category); }, [category]);

  // Refresh library when the wizard signals a completed upload/hardlink
  // (refreshSignal === 0 at mount → no superfluous reload).
  useEffect(() => {
    if (category && refreshSignal) reloadKeepSelection(category);
  }, [refreshSignal]);

  useEffect(() => {
    setBulkMode(false);
    setSelectedPaths(new Set());
    setBulkToast(null);
  }, [category]);

  const currentCat = categories.find((c) => c.id === category);
  const currentIcon = currentCat ? iconFor(currentCat.id) : LibraryIcon;

  const itemBytes = (it: LibraryItem): number => {
    if (it.seasons && it.seasons.length > 0) {
      return it.seasons.reduce((a, s) => a + sizeToBytes(s.size), 0);
    }
    return sizeToBytes(it.size);
  };

  const filtered = useMemo(() => {
    const base = items.filter((it) => {
      if (search && !it.title.toLowerCase().includes(search.toLowerCase())
          && !it.name.toLowerCase().includes(search.toLowerCase())) return false;
      if (hideNoItalian && it.lang_scanned && !it.langs.includes('ITA')) return false;
      if (!hideUploaded) return true;
      if (it.seasons) return !(it.all_seasons_uploaded);
      return !it.already_uploaded;
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    return base.slice().sort((a, b) => {
      if (sortBy === 'year') {
        return ((parseInt(a.year || '0', 10) || 0) - (parseInt(b.year || '0', 10) || 0)) * dir;
      }
      if (sortBy === 'size') {
        return (itemBytes(a) - itemBytes(b)) * dir;
      }
      return a.title.localeCompare(b.title) * dir;
    });
  }, [items, search, hideUploaded, hideNoItalian, sortBy, sortDir]);

  const needTmdb = filtered.filter((i) => !i.tmdb_id).length;
  const needLangs = filtered.filter((i) => !i.lang_scanned).length;

  const selectableFiltered = useMemo(
    () => filtered.filter((it) => it.kind === 'movie' && !it.already_uploaded),
    [filtered],
  );
  const canBulk = selectableFiltered.length > 0;
  const selectedCount = selectedPaths.size;

  const toggleBulkMode = () => {
    setBulkMode((prev) => {
      const next = !prev;
      if (next) { setSelected(null); setBulkToast(null); }
      if (!next) setSelectedPaths(new Set());
      return next;
    });
  };

  const toggleItemSelected = (item: LibraryItem) => {
    if (item.kind !== 'movie' || item.already_uploaded) return;
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(item.path)) next.delete(item.path); else next.add(item.path);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedPaths(new Set(selectableFiltered.map((it) => it.path)));
  };

  const clearSelection = () => setSelectedPaths(new Set());

  const runBulkMark = async () => {
    if (bulkBusy || selectedCount === 0) return;
    const targets = items.filter(
      (it) => selectedPaths.has(it.path) && it.kind === 'movie' && !it.already_uploaded,
    );
    if (targets.length === 0) return;
    setBulkBusy(true);
    setBulkToast(null);
    const results = await Promise.allSettled(
      targets.map((it) =>
        api.post(
          `/api/library/${category}/${encodeURIComponent(it.name)}/mark-uploaded`,
          { season_path: '', episode_path: '' },
        ),
      ),
    );
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    setBulkToast(t('library.bulkDone', { ok, total: targets.length }));
    setBulkBusy(false);
    setSelectedPaths(new Set());
    setBulkMode(false);
    await reloadKeepSelection(category);
  };

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
        padding: isMobile ? '10px 14px' : '12px 18px',
        borderBottom: '1px solid var(--border-subtle)',
        background: '#0a0c12', display: 'flex', alignItems: 'center',
        gap: 10, flexShrink: 0, flexWrap: 'wrap',
      }}>
        <div ref={catBtnRef} style={{ position: 'relative' }}>
          <button
            onClick={() => setCatPickerOpen((v) => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '7px 10px', borderRadius: 6,
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              color: 'var(--fg-1)', fontSize: 12, fontWeight: 600,
              fontFamily: 'var(--font-display)', cursor: 'pointer',
              minWidth: 180,
            }}
          >
            {(() => { const I = currentIcon; return <I size={14} color="var(--blue-bright)" />; })()}
            <span style={{ flex: 1, textAlign: 'left' }}>
              {currentCat ? currentCat.label : t('library.selectCategory')}
            </span>
            {currentCat && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: 'var(--fg-3)',
              }}>{currentCat.count}</span>
            )}
            <ChevronDown size={13} color="var(--fg-3)"
              style={{ transition: 'transform 150ms',
                transform: catPickerOpen ? 'rotate(180deg)' : 'none' }} />
          </button>
          {catPickerOpen && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 6px)', left: 0,
              minWidth: 260, background: '#0a0c12',
              border: '1px solid var(--border)', borderRadius: 8,
              boxShadow: '0 12px 40px rgba(0,0,0,0.55)', zIndex: 50,
              overflow: 'hidden',
            }}>
              <div style={{
                padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)',
                display: 'flex', alignItems: 'center', gap: 6,
                fontSize: 10, fontWeight: 700,
                letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
                color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
              }}>
                <LibraryIcon size={11} /> {t('library.libraryRoot')}
                <span style={{
                  marginLeft: 'auto', fontFamily: 'var(--font-mono)',
                  fontSize: 10, fontWeight: 400, letterSpacing: 0,
                  textTransform: 'none', color: 'var(--fg-3)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  maxWidth: 160,
                }} title={mediaRoot}>{mediaRoot || '—'}</span>
              </div>
              {categories.length === 0 && (
                <div style={{
                  padding: 16, fontSize: 11, color: 'var(--fg-3)',
                  fontFamily: 'var(--font-display)', textAlign: 'center',
                }}>{t('library.noSubfolders')}</div>
              )}
              {categories.map((c) => {
                const Icon = iconFor(c.id);
                const active = c.id === category;
                return (
                  <div
                    key={c.id}
                    onClick={() => { setCategory(c.id); setCatPickerOpen(false); }}
                    style={{
                      padding: '9px 12px', cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: 8,
                      background: active ? 'rgba(59,130,246,0.08)' : 'transparent',
                      borderLeft: active ? '2px solid var(--blue)' : '2px solid transparent',
                      fontFamily: 'var(--font-display)',
                    }}
                    onMouseEnter={(e) => {
                      if (!active) (e.currentTarget as HTMLElement).style.background = 'var(--bg-card)';
                    }}
                    onMouseLeave={(e) => {
                      if (!active) (e.currentTarget as HTMLElement).style.background = 'transparent';
                    }}
                  >
                    <Icon size={13} color={active ? 'var(--blue-bright)' : 'var(--fg-2)'} />
                    <span style={{
                      flex: 1, fontSize: 12, fontWeight: 600,
                      color: active ? 'var(--fg-1)' : 'var(--fg-2)',
                    }}>{c.label}</span>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10,
                      color: c.count ? 'var(--fg-3)' : 'var(--fg-4)',
                    }}>{c.count || t('library.empty')}</span>
                  </div>
                );
              })}
              <div style={{
                padding: '8px 12px', borderTop: '1px solid var(--border-subtle)',
                fontSize: 10, color: 'var(--fg-4)',
                fontFamily: 'var(--font-display)',
              }}>{t('library.autoDiscover')}</div>
            </div>
          )}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('library.searchPlaceholder')}
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
          {loading ? t('library.scanning') : t('library.rescan')}
        </button>
        <button disabled={enriching} onClick={runEnrich} style={actionBtn}>
          <Database size={11} />
          {enriching ? t('library.enriching') : t('library.autoTmdb')}
        </button>
        <button disabled={scanning} onClick={runScanLangs} style={actionBtn}>
          <Headphones size={11} />
          {scanning ? t('library.scanning') : t('library.scanLangs')}
        </button>
        {canBulk && (
          <button
            onClick={toggleBulkMode}
            style={{
              ...actionBtn,
              background: bulkMode ? 'var(--blue)' : (actionBtn as any).background,
              color: bulkMode ? '#fff' : (actionBtn as any).color,
              borderColor: bulkMode ? 'var(--blue)' : (actionBtn as any).borderColor,
            }}
            title={t('library.bulkSelect')}
          >
            <CheckSquare size={11} />
            {bulkMode ? t('library.bulkCancel') : t('library.bulkSelect')}
          </button>
        )}
      </div>

      <div style={{
        padding: isMobile ? '8px 14px' : '8px 18px',
        display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: '1px solid var(--border-subtle)',
        background: '#0a0c12', flexShrink: 0, flexWrap: 'wrap',
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
          {t('library.hideUploaded')}
        </div>
        <div
          title={t('library.onlyItalian')}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
            fontSize: 11, fontWeight: 600, color: 'var(--fg-2)',
            fontFamily: 'var(--font-display)',
          }}
          onClick={() => setHideNoItalian(!hideNoItalian)}
        >
          <div style={{
            width: 14, height: 14, borderRadius: 3,
            border: `1px solid ${hideNoItalian ? 'var(--blue)' : 'var(--border)'}`,
            background: hideNoItalian ? 'var(--blue)' : 'var(--bg-card)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 9, color: '#fff',
          }}>{hideNoItalian && '✓'}</div>
          {t('library.onlyItalian')}
        </div>
        {needTmdb > 0 && (
          <span style={warnChip}>⚠ {t('library.withoutTmdb', { n: needTmdb })}</span>
        )}
        {needLangs > 0 && (
          <span style={warnChip}>⚠ {t('library.needLangScan', { n: needLangs })}</span>
        )}
        <div style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <span style={{
            fontSize: 10, fontWeight: 700,
            letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
            color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
          }}>{t('library.sort')}</span>
          <div style={{
            display: 'flex', gap: 2, background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6, padding: 2,
          }}>
            {([['name', t('library.sortName')], ['year', t('library.sortYear')], ['size', t('library.sortSize')]] as const).map(([k, l]) => (
              <button
                key={k}
                onClick={() => setSortBy(k)}
                style={{
                  padding: '3px 10px', borderRadius: 4, border: 'none', cursor: 'pointer',
                  fontSize: 11, fontWeight: 600,
                  fontFamily: 'var(--font-display)',
                  background: sortBy === k ? 'var(--blue)' : 'transparent',
                  color: sortBy === k ? '#fff' : 'var(--fg-3)',
                }}
              >{l}</button>
            ))}
          </div>
          <button
            onClick={() => setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}
            title={sortDir === 'asc' ? t('library.sortAsc') : t('library.sortDesc')}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
              color: 'var(--fg-3)', fontFamily: 'var(--font-mono)',
              fontSize: 11, fontWeight: 700,
              display: 'flex', alignItems: 'center', gap: 3,
            }}
          >{sortDir === 'asc' ? t('library.sortAsc') : t('library.sortDesc')}</button>
          <span style={{
            fontSize: 11, color: 'var(--fg-3)',
            fontFamily: 'var(--font-display)', marginLeft: 4,
          }}>{t('library.countOf', { filtered: filtered.length, total: items.length })}</span>
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{
          flex: 1, display: 'grid',
          gridTemplateColumns: isMobile
            ? 'repeat(auto-fill, minmax(110px, 1fr))'
            : 'repeat(auto-fill, minmax(150px, 1fr))',
          gridAutoRows: 'min-content',
          gap: isMobile ? 8 : 10,
          padding: isMobile ? '12px 14px' : '14px 18px',
          overflowY: 'auto', alignContent: 'start',
        }}>
          {filtered.map((item) => {
            const isSeries = !!item.seasons;
            const uploaded = isSeries
              ? item.seasons!.filter((s) => s.already_uploaded || s.all_episodes_uploaded).length
              : 0;
            const totalSeasons = isSeries ? item.seasons!.length : 0;
            const selectedHere = selected?.path === item.path;
            const bulkEligible = bulkMode && item.kind === 'movie';
            const bulkSelected = bulkEligible && selectedPaths.has(item.path);
            const bulkDisabled = bulkMode && (item.kind !== 'movie' || item.already_uploaded);
            const handleClick = () => {
              if (bulkMode) { toggleItemSelected(item); return; }
              setSelected(item);
            };
            const borderColor = bulkSelected
              ? 'var(--green)'
              : selectedHere && !bulkMode
                ? 'var(--blue)'
                : 'var(--border)';
            return (
              <div
                key={item.path}
                onClick={handleClick}
                style={{
                  background: 'var(--bg-card)',
                  border: `1px solid ${borderColor}`,
                  borderRadius: 6, overflow: 'hidden',
                  cursor: bulkDisabled ? 'not-allowed' : 'pointer',
                  opacity: bulkDisabled ? 0.45 : 1,
                  transition: 'all 150ms',
                  display: 'flex', flexDirection: 'column',
                  position: 'relative',
                }}
              >
                {bulkMode && (
                  <div style={{
                    position: 'absolute', top: 6, right: 6, zIndex: 2,
                    width: 22, height: 22, borderRadius: 4,
                    border: `1px solid ${bulkSelected ? 'var(--green)' : 'rgba(255,255,255,0.45)'}`,
                    background: bulkSelected ? 'var(--green)' : 'rgba(0,0,0,0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff',
                    boxShadow: '0 1px 4px rgba(0,0,0,0.5)',
                  }}>
                    {bulkSelected
                      ? <CheckSquare size={14} />
                      : <Square size={14} color={bulkDisabled ? 'var(--fg-4)' : '#fff'} />}
                  </div>
                )}
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
                  {!bulkMode && (
                    <div style={{ position: 'absolute', top: 6, right: 6 }}>
                      {item.tmdb_id
                        ? <Badge>TMDB ✓</Badge>
                        : <Badge color="var(--red)" bg="var(--red-dim)">no TMDB</Badge>}
                    </div>
                  )}
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
                        }}>{t('library.seasons', { uploaded, total: totalSeasons })}</span>
                        <span style={{ color: 'var(--fg-4)' }}>
                          {item.seasons!.reduce((a, s) => a + s.episode_count, 0)} {t('library.ep')}
                        </span>
                      </>
                    ) : (
                      <span style={{
                        color: item.already_uploaded ? 'var(--green)' : 'var(--fg-3)',
                      }}>{item.already_uploaded ? t('library.uploadedBadge') : item.size}</span>
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
              {t('library.nothingToShow')}{' '}
              {hideUploaded && t('library.tryUnhideUploaded')}
              {hideNoItalian && ' ' + t('library.tryUnhideItalian')}
            </div>
          )}
        </div>

        {!bulkMode && selected && (
          <DetailPanel
            item={selected}
            category={category}
            onStart={startWizard}
            onClose={() => setSelected(null)}
            onEditTmdb={() => setTmdbEditOpen(true)}
            onRescan={(langs) => setSelected((prev) => prev ? { ...prev, langs, lang_scanned: true } : prev)}
            onMarked={() => reloadKeepSelection(category)}
            isMobile={isMobile}
          />
        )}
      </div>
      {bulkMode && (
        <div style={{
          flexShrink: 0,
          background: '#0a0c12',
          borderTop: '1px solid var(--border)',
          padding: isMobile ? '10px 14px' : '10px 18px',
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        }}>
          <span style={{
            fontSize: 12, fontWeight: 700,
            color: selectedCount > 0 ? 'var(--green)' : 'var(--fg-3)',
            fontFamily: 'var(--font-display)',
          }}>
            {t('library.bulkSelectedCount', { count: selectedCount })}
          </span>
          <button
            onClick={selectAllVisible}
            disabled={selectableFiltered.length === 0 || bulkBusy}
            style={actionBtn}
          >
            {t('library.bulkSelectAll')}
          </button>
          <button
            onClick={clearSelection}
            disabled={selectedCount === 0 || bulkBusy}
            style={actionBtn}
          >
            {t('library.bulkClear')}
          </button>
          <div style={{ flex: 1 }} />
          <button
            onClick={toggleBulkMode}
            disabled={bulkBusy}
            style={actionBtn}
          >
            {t('library.bulkCancel')}
          </button>
          <button
            onClick={runBulkMark}
            disabled={selectedCount === 0 || bulkBusy}
            style={{
              background: selectedCount > 0 && !bulkBusy ? 'var(--green)' : 'var(--border)',
              border: 'none', borderRadius: 6,
              padding: '7px 14px', fontSize: 12, fontWeight: 700,
              color: '#fff',
              cursor: selectedCount > 0 && !bulkBusy ? 'pointer' : 'not-allowed',
              fontFamily: 'var(--font-display)',
            }}
          >
            {bulkBusy ? t('library.bulkMarking') : t('library.bulkMarkUploaded')}
          </button>
        </div>
      )}
      {bulkToast && (
        <div style={{
          position: 'fixed', bottom: 20, left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--bg-card)',
          border: '1px solid var(--green)',
          color: 'var(--green)',
          borderRadius: 6, padding: '8px 14px',
          fontSize: 12, fontWeight: 600,
          fontFamily: 'var(--font-display)',
          boxShadow: '0 6px 20px rgba(0,0,0,0.45)',
          zIndex: 300,
          display: 'flex', alignItems: 'center', gap: 10,
          animation: 'u3d-fade-in 150ms ease',
        }}>
          <span>{bulkToast}</span>
          <button
            onClick={() => setBulkToast(null)}
            style={{
              background: 'transparent', border: 'none',
              color: 'var(--fg-3)', cursor: 'pointer',
              padding: 0, display: 'flex', alignItems: 'center',
            }}
            aria-label={t('common.close')}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {tmdbEditOpen && selected && (
        <TmdbEditModal
          item={selected}
          category={category}
          onClose={() => setTmdbEditOpen(false)}
          onApplied={() => { setTmdbEditOpen(false); load(category); }}
        />
      )}
    </div>
  );
}

function DetailPanel({
  item, category, onStart, onClose, onEditTmdb, onRescan, onMarked, isMobile,
}: {
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onClose: () => void;
  onEditTmdb: () => void;
  onRescan?: (langs: string[]) => void;
  onMarked?: () => void;
  isMobile?: boolean;
}) {
  const { t } = useTranslation();
  const mobileOverlayStyle = isMobile
    ? {
        position: 'fixed' as const, inset: 0, zIndex: 100,
        background: '#0a0c12', width: 'auto', borderLeft: 'none',
      }
    : { width: 360, borderLeft: '1px solid var(--border-subtle)' };
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', background: '#0a0c12',
      overflowY: 'auto', flexShrink: 0,
      ...mobileOverlayStyle,
    }}>
      {isMobile && (
        <button
          onClick={onClose}
          style={{
            position: 'sticky', top: 0, zIndex: 2,
            alignSelf: 'flex-start', margin: 10,
            background: 'rgba(10,12,18,0.85)',
            backdropFilter: 'blur(6px)',
            border: '1px solid var(--border)', borderRadius: 6,
            padding: '6px 10px', color: 'var(--fg-1)', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
            fontFamily: 'var(--font-display)',
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          <X size={14} /> {t('library.backToLibrary')}
        </button>
      )}
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
            color: item.tmdb_id ? 'var(--green)' : 'var(--yellow)',
            fontWeight: 600,
          }}>{item.tmdb_id ? '✓' : 'manual'}</span>
          <button
            onClick={onEditTmdb}
            style={{
              marginLeft: 'auto', background: 'var(--bg-base)',
              border: '1px solid var(--border)', borderRadius: 4,
              padding: '3px 8px', fontSize: 10, fontWeight: 600,
              color: 'var(--fg-3)', cursor: 'pointer',
              fontFamily: 'var(--font-display)',
              display: 'flex', alignItems: 'center', gap: 4,
            }}
          ><Pencil size={9} /> Edit</button>
        </div>
        {item.tmdb_overview && (
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 12,
            color: 'var(--fg-3)', lineHeight: 1.6, marginBottom: 12,
          }}>{item.tmdb_overview}</div>
        )}

        <SectionHeader title={t('library.sectionAudio')} rightNote={item.lang_scanned ? t('library.cached') : ''} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginBottom: 10 }}>
          {item.langs.length
            ? item.langs.map((l) => <LangChip key={l} lang={l} />)
            : <span style={{
                fontSize: 11, color: 'var(--yellow)',
                fontFamily: 'var(--font-display)',
              }}>{t('library.notScanned')}</span>}
        </div>

        <SectionHeader title={t('library.sectionSourcePath')} />
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-2)',
          background: 'var(--bg-base)', border: '1px solid var(--border-subtle)',
          borderRadius: 4, padding: '6px 8px', marginBottom: 8, wordBreak: 'break-all',
        }}>{item.path}</div>

        {item.seasons ? (
          <>
            <SectionHeader title={t('library.sectionSeasons')} right={
              <button
                onClick={() => onStart('series', item.path)}
                style={{
                  background: 'var(--blue)', border: 'none', borderRadius: 4,
                  padding: '3px 7px', fontSize: 10, fontWeight: 600,
                  color: '#fff', cursor: 'pointer',
                  fontFamily: 'var(--font-display)',
                }}
              >{t('library.uploadAllSeasons')}</button>
            }/>
            {(() => {
              const firstOpenIdx = item.seasons.findIndex((s) => !s.already_uploaded);
              return item.seasons.map((s, idx) => (
                <SeasonRow
                  key={s.number}
                  season={s}
                  item={item}
                  category={category}
                  onStart={onStart}
                  onMarked={onMarked}
                  defaultOpen={idx === firstOpenIdx}
                />
              ));
            })()}
            {!item.all_seasons_uploaded && (
              <MarkUploadedBtn
                category={category}
                name={item.name}
                onMarked={onMarked}
                label={t('library.markSeries')}
              />
            )}
            <RescanLangsBtn category={category} name={item.name} onRescan={onRescan} />
          </>
        ) : (
          <>
            <SectionHeader title={t('library.sectionFiles')} />
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
              {item.already_uploaded ? t('library.alreadyUploaded') : t('library.startWizard')}
            </button>
            <MarkUploadedBtn category={category} name={item.name} onMarked={onMarked} />
            <RescanLangsBtn category={category} name={item.name} onRescan={onRescan} />
          </>
        )}
      </div>
    </div>
  );
}

function parseEpisode(filename: string, seriesName: string): { num: string; title: string } {
  const stem = filename.replace(/\.[^.]+$/, '');
  const m = stem.match(/[Ss](\d{1,2})[Ee](\d{1,3})/);
  const num = m ? `E${m[2].padStart(2, '0')}` : '';
  let rest = stem;
  if (m && m.index !== undefined) rest = stem.slice(m.index + m[0].length);
  rest = rest.replace(/^[\s._-]+/, '');
  rest = rest.split(/\b(1080p|720p|2160p|480p|WEB-?DL|WEBRip|BluRay|HDTV|x264|x265|H\.?264|H\.?265|HEVC|AAC|DDP?5\.1|DTS|AMZN|NF|HMAX|DSNP|ITA|ENG|MULTi)\b/i)[0];
  rest = rest.replace(/[._]+/g, ' ').replace(/\s+/g, ' ').trim();
  rest = rest.replace(/[\s-]+$/, '');
  const seriesLower = seriesName.toLowerCase();
  if (seriesName && rest.toLowerCase().startsWith(seriesLower)) {
    rest = rest.slice(seriesName.length).replace(/^[\s-]+/, '');
  }
  return { num, title: rest };
}

function SeasonRow({
  season, item, category, onStart, onMarked, defaultOpen,
}: {
  season: Season;
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onMarked?: () => void;
  defaultOpen?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen ?? false);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const pct = Math.round((season.uploaded_episodes / Math.max(1, season.episode_count)) * 100);
  const canToggle = !season.already_uploaded;
  return (
    <div style={{
      padding: '8px 10px', background: 'var(--bg-card)',
      borderRadius: 6, border: '1px solid var(--border)', marginBottom: 6,
    }}>
      <div
        onClick={() => { if (canToggle) setOpen((v) => !v); }}
        role={canToggle ? 'button' : undefined}
        aria-expanded={canToggle ? open : undefined}
        aria-label={canToggle ? t('library.toggleSeason') : undefined}
        style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', marginBottom: 5,
          cursor: canToggle ? 'pointer' : 'default',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {canToggle && (
            <ChevronDown
              size={14}
              style={{
                color: 'var(--fg-3)',
                transition: 'transform 0.15s ease',
                transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
              }}
            />
          )}
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
            color: 'var(--fg-1)',
          }}>{season.label}</span>
          {season.already_uploaded && (
            <span style={{ marginLeft: 6 }}><Badge>uploaded ✓</Badge></span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
          {!season.already_uploaded && (
            <>
              <button
                onClick={() => onStart('series', season.path, season)}
                style={{
                  background: 'var(--blue)', border: 'none', borderRadius: 4,
                  padding: '3px 7px', fontSize: 10, fontWeight: 600,
                  color: '#fff', cursor: 'pointer',
                  fontFamily: 'var(--font-display)',
                }}
              >{t('library.bulkUploadSeason')}</button>
              <MarkUploadedBtn
                category={category}
                name={item.name}
                seasonPath={season.path}
                variant="inline-sm"
                label={t('library.marked')}
                onMarked={onMarked}
              />
            </>
          )}
        </div>
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
      }}>
        {season.episode_count} {t('library.ep')} · {season.size}
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
          }}>{t('library.episodesUploaded', { done: season.uploaded_episodes, total: season.episode_count })}</div>
        </>
      )}
      {!season.already_uploaded && open && (
        <div style={{
          marginTop: 8, display: 'flex', flexDirection: 'column', gap: 2,
          animation: 'u3d-fade-in 0.18s ease',
        }}>
          {season.video_files.map((vf, idx) => {
            const { num, title } = parseEpisode(vf.name, item.name);
            const fallback = num
              ? t('library.episodeFallback', { n: parseInt(num.slice(1), 10) })
              : vf.name.replace(/\.[^.]+$/, '');
            const display = title || fallback;
            const isHover = hoverIdx === idx && !vf.uploaded;
            return (
              <div
                key={vf.path}
                onMouseEnter={() => setHoverIdx(idx)}
                onMouseLeave={() => setHoverIdx(null)}
                onClick={() => !vf.uploaded && onStart('episode', vf.path, season)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 8px', borderRadius: 4,
                  background: isHover ? 'var(--bg-base)' : 'transparent',
                  cursor: vf.uploaded ? 'default' : 'pointer',
                  opacity: vf.uploaded ? 0.55 : 1,
                  transition: 'background 0.12s ease',
                }}
              >
                <span style={{
                  fontSize: 11, width: 14, textAlign: 'center',
                  color: vf.uploaded ? 'var(--green)' : 'var(--fg-3)',
                }}>{vf.uploaded ? '✓' : '·'}</span>
                {num && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
                    color: vf.uploaded ? 'var(--green)' : 'var(--blue)',
                    minWidth: 28,
                  }}>{num}</span>
                )}
                <span
                  title={vf.name}
                  style={{
                    flex: 1, fontFamily: 'var(--font-display)', fontSize: 12,
                    color: 'var(--fg-1)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}
                >{num ? ' - ' : ''}{display}</span>
                {!vf.uploaded && (
                  <span onClick={(e) => e.stopPropagation()} style={{ flexShrink: 0 }}>
                    <MarkUploadedBtn
                      category={category}
                      name={item.name}
                      episodePath={vf.path}
                      variant="chip"
                      onMarked={onMarked}
                    />
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MarkUploadedBtn({
  category, name,
  seasonPath, episodePath,
  variant = 'full',
  label,
  onMarked,
}: {
  category: Category;
  name: string;
  seasonPath?: string;
  episodePath?: string;
  variant?: 'full' | 'inline-sm' | 'chip';
  label?: string;
  onMarked?: () => void;
}) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  const mark = async () => {
    if (done) return;
    try {
      await api.post(
        `/api/library/${category}/${encodeURIComponent(name)}/mark-uploaded`,
        {
          season_path: seasonPath ?? '',
          episode_path: episodePath ?? '',
        },
      );
      setDone(true);
      onMarked?.();
    } catch { /* ignore */ }
  };
  if (variant === 'inline-sm') {
    return (
      <button
        onClick={mark}
        disabled={done}
        title={t('library.markUploaded')}
        style={{
          background: 'transparent',
          border: '1px solid var(--border)', borderRadius: 4,
          padding: '3px 7px', fontSize: 10, fontWeight: 600,
          color: done ? 'var(--green)' : 'var(--fg-3)',
          cursor: done ? 'default' : 'pointer',
          fontFamily: 'var(--font-display)',
        }}
      >{done ? '✓' : (label ?? t('library.marked'))}</button>
    );
  }
  if (variant === 'chip') {
    return (
      <button
        onClick={mark}
        disabled={done}
        title={t('library.markUploaded')}
        style={{
          background: 'transparent',
          border: '1px solid var(--border)',
          borderRadius: '0 4px 4px 0',
          padding: '2px 5px', fontSize: 9, fontWeight: 700,
          color: done ? 'var(--green)' : 'var(--fg-3)',
          cursor: done ? 'default' : 'pointer',
          fontFamily: 'var(--font-display)',
          minWidth: 22,
        }}
      >{done ? '✓' : (label ?? '✓')}</button>
    );
  }
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
    >{done ? t('library.marked') : (label ?? t('library.markUploaded'))}</button>
  );
}

function RescanLangsBtn({
  category, name, onRescan,
}: { category: Category; name: string; onRescan?: (langs: string[]) => void }) {
  const { t } = useTranslation();
  const [state, setState] = useState<'idle' | 'loading' | 'done'>('idle');
  const rescan = async () => {
    setState('loading');
    try {
      const r = await api.post<{ ok: boolean; langs: string[] }>(
        `/api/library/${category}/${encodeURIComponent(name)}/rescan-langs`, {},
      );
      onRescan?.(r.langs);
      setState('done');
    } catch {
      setState('idle');
    }
  };
  return (
    <button
      onClick={rescan}
      disabled={state === 'loading'}
      style={{
        width: '100%', background: 'transparent',
        border: '1px solid var(--border)', borderRadius: 6,
        padding: 8, fontSize: 11, fontWeight: 600,
        color: state === 'done' ? 'var(--green)' : 'var(--fg-2)',
        cursor: state === 'loading' ? 'default' : 'pointer',
        fontFamily: 'var(--font-display)', marginBottom: 6,
      }}
    >
      {state === 'loading' ? t('library.scanning') : state === 'done' ? t('library.rescanDone') : t('library.rescanLangs')}
    </button>
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

function TmdbEditModal({
  item, category, onClose, onApplied,
}: {
  item: LibraryItem;
  category: Category;
  onClose: () => void;
  onApplied: () => void;
}) {
  const { t } = useTranslation();
  const kind = item.kind === 'series' ? 'tv' : 'movie';
  const [query, setQuery] = useState(item.tmdb_title_en || item.title || '');
  const [manualId, setManualId] = useState(item.tmdb_id || '');
  const [results, setResults] = useState<TmdbSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async (q: string) => {
    setQuery(q);
    if (!q.trim()) { setResults([]); return; }
    setSearching(true); setError(null);
    try {
      const year = item.year || '';
      const r = await api.get<{ results: TmdbSearchResult[] }>(
        `/api/tmdb/search?q=${encodeURIComponent(q)}&year=${encodeURIComponent(year)}&kind=${kind}`,
      );
      setResults(r.results || []);
    } catch (e: any) {
      setError(e?.message || 'search failed');
      setResults([]);
    } finally { setSearching(false); }
  };

  useEffect(() => { runSearch(query); }, []);

  const apply = async (id: string | number) => {
    setApplying(true); setError(null);
    try {
      await api.post('/api/tmdb/set', {
        source_path: item.path,
        tmdb_id: String(id),
        tmdb_kind: kind,
      });
      onApplied();
    } catch (e: any) {
      setError(e?.message || 'apply failed');
    } finally { setApplying(false); }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(2px)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 560, maxHeight: '80vh', background: '#0a0c12',
          border: '1px solid var(--border)', borderRadius: 8,
          boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        <div style={{
          padding: '14px 18px', borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <Database size={14} color="var(--blue)" />
          <div style={{ flex: 1 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: 14,
              fontWeight: 700, color: 'var(--fg-1)',
            }}>{t('library.tmdbEdit')}</div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: 'var(--fg-3)', marginTop: 2,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>{item.name}</div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none',
              color: 'var(--fg-3)', cursor: 'pointer',
              padding: 4, display: 'flex',
            }}
          ><X size={16} /></button>
        </div>

        <div style={{
          padding: '12px 18px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{
            fontSize: 10, fontWeight: 700,
            letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
            color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
            marginBottom: 6,
          }}>{t('library.tmdbSearch', { kind })}</div>
          <div style={{ position: 'relative' }}>
            <SearchIcon
              size={13}
              style={{
                position: 'absolute', left: 10, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--fg-3)',
              }}
            />
            <input
              autoFocus
              value={query}
              onChange={(e) => runSearch(e.target.value)}
              placeholder={t('library.searchPlaceholder')}
              style={{
                width: '100%', background: 'var(--bg-card)',
                border: '1px solid var(--border)', borderRadius: 6,
                padding: '8px 10px 8px 30px', fontSize: 12,
                color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        <div style={{
          flex: 1, overflowY: 'auto', padding: '8px 10px', minHeight: 200,
        }}>
          {error && (
            <div style={{
              padding: 12, margin: 6, borderRadius: 6,
              background: 'var(--red-dim)', color: 'var(--red)',
              fontSize: 11, fontFamily: 'var(--font-mono)',
            }}>{error}</div>
          )}
          {searching ? (
            <div style={{
              padding: 24, textAlign: 'center', fontSize: 11,
              color: 'var(--fg-3)', fontFamily: 'var(--font-mono)',
            }}>{t('library.tmdbSearching')}</div>
          ) : results.length === 0 ? (
            <div style={{
              padding: 24, textAlign: 'center', fontSize: 11,
              color: 'var(--fg-3)', fontFamily: 'var(--font-display)',
            }}>{t('library.tmdbNoResults')}</div>
          ) : results.map((r) => {
            const isCurrent = String(r.id) === String(item.tmdb_id);
            return (
              <div
                key={r.id}
                onClick={() => !applying && apply(r.id)}
                style={{
                  display: 'flex', gap: 10, padding: 8, borderRadius: 6,
                  cursor: applying ? 'wait' : 'pointer', marginBottom: 4,
                  border: isCurrent ? '1px solid var(--blue)' : '1px solid transparent',
                  background: isCurrent ? 'rgba(59,130,246,0.08)' : 'transparent',
                  opacity: applying ? 0.6 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!isCurrent) (e.currentTarget as HTMLElement).style.background = 'var(--bg-card)';
                }}
                onMouseLeave={(e) => {
                  if (!isCurrent) (e.currentTarget as HTMLElement).style.background = 'transparent';
                }}
              >
                <div style={{
                  width: 42, height: 62, borderRadius: 4, flexShrink: 0,
                  background: r.poster
                    ? `url("${r.poster}") center/cover`
                    : 'linear-gradient(135deg, var(--bg-card), var(--bg-base))',
                }}/>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                      color: 'var(--fg-1)',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>{r.title}</div>
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
                    }}>{r.year}</div>
                    {isCurrent && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, padding: '1px 5px',
                        borderRadius: 3, background: 'var(--green-dim)',
                        color: 'var(--green)',
                        fontFamily: 'var(--font-display)',
                      }}>{t('library.tmdbCurrent')}</span>
                    )}
                  </div>
                  {r.overview && (
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 11,
                      color: 'var(--fg-2)', lineHeight: 1.4, marginTop: 3,
                      display: '-webkit-box', WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    }}>{r.overview}</div>
                  )}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 10, marginTop: 4,
                    fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
                  }}>
                    <span>id: <span style={{ color: 'var(--blue-bright)' }}>{r.id}</span></span>
                    {typeof r.vote === 'number' && r.vote > 0 && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                        <Star size={9} color="var(--yellow)" />
                        <span style={{ color: 'var(--yellow)' }}>{r.vote.toFixed(1)}</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div style={{
          padding: '12px 18px', borderTop: '1px solid var(--border-subtle)',
          background: 'var(--bg-base)',
        }}>
          <div style={{
            fontSize: 10, fontWeight: 700,
            letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase',
            color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
            marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6,
          }}>
            {t('library.tmdbManualId')}
            <span style={{
              color: 'var(--fg-3)', fontWeight: 400,
              letterSpacing: 0, textTransform: 'none',
            }}>{t('library.tmdbManualHint')}</span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={manualId}
              onChange={(e) => setManualId(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="123456"
              style={{
                flex: 1, background: 'var(--bg-card)',
                border: '1px solid var(--border)', borderRadius: 6,
                padding: '8px 10px', fontSize: 12, color: 'var(--fg-1)',
                fontFamily: 'var(--font-mono)',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
            <button
              onClick={() => manualId && apply(manualId)}
              disabled={!manualId || applying}
              style={{
                background: manualId && !applying ? 'var(--blue)' : 'var(--bg-card)',
                border: 'none', borderRadius: 6, padding: '0 16px',
                fontSize: 11, fontWeight: 600,
                color: manualId && !applying ? '#fff' : 'var(--fg-4)',
                cursor: manualId && !applying ? 'pointer' : 'not-allowed',
                fontFamily: 'var(--font-display)',
              }}
            >{applying ? t('library.tmdbApplying') : t('library.tmdbApply')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
