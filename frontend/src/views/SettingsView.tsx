import { useEffect, useState } from 'react';
import {
  Activity, HardDrive, Sliders, Image as ImageIcon, Folder as FolderIcon,
  GitBranch, Terminal, CheckCircle,
} from 'lucide-react';
import { api } from '../api';
import { Toggle, GROUP_LABEL, LABEL_CSS } from '../components/primitives';

type Section = 'tracker' | 'client' | 'prefs' | 'imghost' | 'paths' | 'seeding' | 'console';

const SECTIONS: { id: Section; label: string; icon: any }[] = [
  { id: 'tracker',  label: 'Trackers',       icon: Activity },
  { id: 'client',   label: 'Torrent Client', icon: HardDrive },
  { id: 'prefs',    label: 'Preferences',    icon: Sliders },
  { id: 'imghost',  label: 'Image Hosts',    icon: ImageIcon },
  { id: 'paths',    label: 'Paths',          icon: FolderIcon },
  { id: 'seeding',  label: 'Seeding Flow',   icon: GitBranch },
  { id: 'console',  label: 'Console',        icon: Terminal },
];

const IMAGE_HOSTS = [
  { key: 'PTSCREENS', label: 'PtScreens',  url: 'ptscreens.com' },
  { key: 'PASSIMA',   label: 'PassIMA',    url: 'passtheima.ge' },
  { key: 'IMGBB',     label: 'ImgBB',      url: 'imgbb.com' },
  { key: 'IMGFI',     label: 'ImgFI',      url: 'imgfi.com' },
  { key: 'FREE_IMAGE',label: 'FreeImage',  url: 'freeimage.host' },
  { key: 'LENSDUMP',  label: 'LensDump',   url: 'lensdump.com' },
  { key: 'IMARIDE',   label: 'ImaRide',    url: 'imageride.net' },
];

type SettingsResponse = {
  config: Record<string, any>;
  env: Record<string, string>;
  config_path: string;
};

export function SettingsView({ isMobile }: { isMobile?: boolean } = {}) {
  const [section, setSection] = useState<Section>('tracker');
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<SettingsResponse>('/api/settings').then(setData).catch(() => {});
  }, []);

  if (!data) {
    return <div style={{ padding: 24, color: 'var(--fg-3)' }}>loading settings…</div>;
  }

  const cfg = data.config;
  const set = (key: string, value: any) =>
    setData((d) => d && ({ ...d, config: { ...d.config, [key]: value } }));

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put<{ config: Record<string, any> }>('/api/settings', cfg);
      setData((d) => d && ({ ...d, config: r.config }));
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } finally { setSaving(false); }
  };

  const navStyle = isMobile
    ? {
        display: 'flex', gap: 4, padding: '8px 10px',
        borderBottom: '1px solid var(--border-subtle)',
        overflowX: 'auto' as const, overflowY: 'hidden' as const,
        flexShrink: 0, WebkitOverflowScrolling: 'touch' as const,
      }
    : {
        width: 160, borderRight: '1px solid var(--border-subtle)',
        padding: '10px 6px', flexShrink: 0,
      };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', flex: 1, overflow: 'hidden',
        flexDirection: isMobile ? 'column' : 'row',
      }}>
        <div style={navStyle}>
          {SECTIONS.map((s) => {
            const Icon = s.icon;
            const active = section === s.id;
            return (
              <div
                key={s.id}
                onClick={() => setSection(s.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', borderRadius: 6,
                  marginBottom: isMobile ? 0 : 2,
                  flexShrink: 0, whiteSpace: 'nowrap',
                  cursor: 'pointer',
                  background: active ? 'var(--blue-muted)' : 'transparent',
                  color: active ? 'var(--blue-bright)' : 'var(--fg-3)',
                  fontSize: 12, fontWeight: active ? 600 : 500,
                  fontFamily: 'var(--font-display)',
                  border: active
                    ? '1px solid rgba(59,130,246,0.2)'
                    : '1px solid transparent',
                }}
              >
                <Icon size={13} />{s.label}
              </div>
            );
          })}
        </div>

        <div style={{
          flex: 1, minWidth: 0,
          padding: isMobile ? '14px' : '18px 20px',
          overflowY: 'auto',
        }}>
          {section === 'tracker' && <TrackerSection cfg={cfg} set={set} isMobile={isMobile} />}
          {section === 'client' && <ClientSection cfg={cfg} set={set} isMobile={isMobile} />}
          {section === 'prefs' && <PrefsSection cfg={cfg} set={set} />}
          {section === 'imghost' && <ImageHostsSection cfg={cfg} set={set} />}
          {section === 'paths' && <PathsSection cfg={cfg} set={set} isMobile={isMobile} />}
          {section === 'seeding' && <SeedingSection cfg={cfg} set={set} env={data.env} isMobile={isMobile} />}
          {section === 'console' && <ConsoleSection cfg={cfg} set={set} />}
        </div>
      </div>

      <div style={{
        padding: '12px 20px', borderTop: '1px solid var(--border-subtle)',
        display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0,
      }}>
        <button
          onClick={save}
          disabled={saving}
          style={{
            background: 'var(--blue)', border: 'none', borderRadius: 6,
            padding: '7px 18px', fontSize: 12, fontWeight: 600,
            color: '#fff', cursor: saving ? 'default' : 'pointer',
            fontFamily: 'var(--font-display)',
          }}
        >{saving ? 'Saving…' : 'Save to Unit3Dbot.json'}</button>
        {saved && (
          <span style={{
            fontSize: 12, color: 'var(--green)',
            fontFamily: 'var(--font-display)',
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <CheckCircle size={13} /> Saved successfully
          </span>
        )}
        <span style={{
          marginLeft: 'auto', fontSize: 11, color: 'var(--fg-4)',
          fontFamily: 'var(--font-mono)',
        }}>{data.config_path}</span>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- Helpers
type SetFn = (k: string, v: any) => void;
type Cfg = Record<string, any>;

function Field({
  cfg, set, k, label, type = 'text', masked = false, wide = false,
}: {
  cfg: Cfg; set: SetFn; k: string; label: string;
  type?: string; masked?: boolean; wide?: boolean;
}) {
  const val = cfg[k];
  const display = masked && val === '__SET__' ? '' : (val ?? '');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={LABEL_CSS}>{label}</label>
      <input
        type={masked ? 'password' : type}
        value={display}
        placeholder={masked && val === '__SET__' ? '••••••• (set)' : ''}
        onChange={(e) => set(k, type === 'number' ? Number(e.target.value) : e.target.value)}
        style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 6, padding: '7px 10px', fontSize: 12,
          color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
          width: wide ? '100%' : undefined,
        }}
      />
    </div>
  );
}

function ToggleRow({
  cfg, set, k, label, sub,
}: {
  cfg: Cfg; set: SetFn; k: string; label: string; sub: string;
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '7px 0', borderBottom: '1px solid var(--border-subtle)',
    }}>
      <div>
        <div style={{
          fontSize: 13, color: 'var(--fg-2)',
          fontFamily: 'var(--font-display)',
        }}>{label}</div>
        <div style={{
          fontSize: 11, color: 'var(--fg-4)',
          fontFamily: 'var(--font-display)',
        }}>{sub}</div>
      </div>
      <Toggle on={!!cfg[k]} onToggle={() => set(k, !cfg[k])} />
    </div>
  );
}

// -------------------------------------------------------------- Sections ----

function TrackerSection({ cfg, set, isMobile }: { cfg: Cfg; set: SetFn; isMobile?: boolean }) {
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10, marginBottom: 10,
  };
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>ITT — ITA Torrents</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="ITT_URL" label="ITT_URL" />
        <Field cfg={cfg} set={set} k="ITT_APIKEY" label="ITT_APIKEY" masked />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="ITT_PID" label="ITT_PID" masked />
      </div>

      <div style={GROUP_LABEL}>PTT — Polish Torrent</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="PTT_URL" label="PTT_URL" />
        <Field cfg={cfg} set={set} k="PTT_APIKEY" label="PTT_APIKEY" masked />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="PTT_PID" label="PTT_PID" masked />
      </div>

      <div style={GROUP_LABEL}>SIS</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="SIS_URL" label="SIS_URL" />
        <Field cfg={cfg} set={set} k="SIS_APIKEY" label="SIS_APIKEY" masked />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="SIS_PID" label="SIS_PID" masked />
      </div>

      <div style={GROUP_LABEL}>Active Trackers</div>
      <MultiTrackerRow cfg={cfg} set={set} />

      <div style={GROUP_LABEL}>External APIs</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TMDB_APIKEY" label="TMDB_APIKEY" masked />
        <Field cfg={cfg} set={set} k="TVDB_APIKEY" label="TVDB_APIKEY" masked />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="YOUTUBE_KEY" label="YOUTUBE_KEY" masked />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="IGDB_CLIENT_ID" label="IGDB_CLIENT_ID" masked />
        <Field cfg={cfg} set={set} k="IGDB_ID_SECRET" label="IGDB_ID_SECRET" masked />
      </div>
    </>
  );
}

function MultiTrackerRow({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  const TRACKERS = [
    { id: 'itt', label: 'ITT' },
    { id: 'ptt', label: 'PTT' },
    { id: 'sis', label: 'SIS' },
  ];
  const active: string[] = Array.isArray(cfg.MULTI_TRACKER)
    ? cfg.MULTI_TRACKER : ['itt'];
  const toggle = (id: string) => {
    const next = active.includes(id)
      ? active.filter((x) => x !== id)
      : [...active, id];
    set('MULTI_TRACKER', next.length ? next : ['itt']);
  };
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {TRACKERS.map((t) => {
        const on = active.includes(t.id);
        return (
          <button
            key={t.id}
            onClick={() => toggle(t.id)}
            style={{
              padding: '6px 12px', borderRadius: 6, cursor: 'pointer',
              fontSize: 12, fontWeight: 600,
              fontFamily: 'var(--font-display)',
              background: on ? 'var(--blue)' : 'var(--bg-card)',
              color: on ? '#fff' : 'var(--fg-2)',
              border: `1px solid ${on ? 'var(--blue)' : 'var(--border)'}`,
            }}
          >{on ? '✓ ' : ''}{t.label}</button>
        );
      })}
    </div>
  );
}

function ClientSection({ cfg, set, isMobile }: { cfg: Cfg; set: SetFn; isMobile?: boolean }) {
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10, marginBottom: 10,
  };
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Active Client</div>
      <div style={grid2}>
        <div>
          <label style={LABEL_CSS}>TORRENT_CLIENT</label>
          <select
            value={cfg.TORRENT_CLIENT ?? 'qbittorrent'}
            onChange={(e) => set('TORRENT_CLIENT', e.target.value)}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '7px 10px', fontSize: 12,
              color: 'var(--fg-1)', fontFamily: 'var(--font-display)',
              width: '100%',
            }}
          >
            <option value="qbittorrent">qbittorrent</option>
            <option value="transmission">transmission</option>
            <option value="rtorrent">rtorrent</option>
          </select>
        </div>
        <Field cfg={cfg} set={set} k="TAG" label="TAG" />
      </div>

      <div style={GROUP_LABEL}>qBittorrent</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="QBIT_HOST" label="QBIT_HOST" />
        <Field cfg={cfg} set={set} k="QBIT_PORT" label="QBIT_PORT" />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="QBIT_USER" label="QBIT_USER" />
        <Field cfg={cfg} set={set} k="QBIT_PASS" label="QBIT_PASS" masked />
      </div>
      <div style={{ ...grid2, gridTemplateColumns: '1fr' }}>
        <Field cfg={cfg} set={set} k="SHARED_QBIT_PATH" label="SHARED_QBIT_PATH" wide />
      </div>

      <div style={GROUP_LABEL}>Transmission</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TRASM_HOST" label="TRASM_HOST" />
        <Field cfg={cfg} set={set} k="TRASM_PORT" label="TRASM_PORT" />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TRASM_USER" label="TRASM_USER" />
        <Field cfg={cfg} set={set} k="TRASM_PASS" label="TRASM_PASS" masked />
      </div>
      <div style={{ ...grid2, gridTemplateColumns: '1fr' }}>
        <Field cfg={cfg} set={set} k="SHARED_TRASM_PATH" label="SHARED_TRASM_PATH" wide />
      </div>

      <div style={GROUP_LABEL}>rTorrent</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="RTORR_HOST" label="RTORR_HOST" />
        <Field cfg={cfg} set={set} k="RTORR_PORT" label="RTORR_PORT" />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="RTORR_USER" label="RTORR_USER" />
        <Field cfg={cfg} set={set} k="RTORR_PASS" label="RTORR_PASS" masked />
      </div>
      <div style={{ ...grid2, gridTemplateColumns: '1fr' }}>
        <Field cfg={cfg} set={set} k="SHARED_RTORR_PATH" label="SHARED_RTORR_PATH" wide />
      </div>
    </>
  );
}

function PrefsSection({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  const upload = [
    ['DUPLICATE_ON',    'Duplicate Check',       'DUPLICATE_ON — check for existing uploads'],
    ['SKIP_DUPLICATE',  'Skip Duplicates',       'SKIP_DUPLICATE — skip without asking'],
    ['SKIP_TMDB',       'Skip TMDB Lookup',      'SKIP_TMDB — skip title matching'],
    ['SKIP_YOUTUBE',    'Skip YouTube Trailer',  'SKIP_YOUTUBE — skip trailer fetch'],
    ['ANON',            'Anonymous Upload',      'ANON — hide username from tracker'],
    ['PERSONAL_RELEASE','Personal Release',      'PERSONAL_RELEASE — mark as personal'],
  ] as const;
  const scr = [
    ['WEBP_ENABLED',  'WebP Screenshots',  'WEBP_ENABLED — convert to WebP'],
    ['CACHE_SCR',     'Cache Screenshots',  'CACHE_SCR — reuse cached screenshots'],
    ['RESIZE_SCSHOT', 'Resize Screenshots', 'RESIZE_SCSHOT — resize before upload'],
  ] as const;
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 10,
  };
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Upload Behaviour</div>
      {upload.map(([k, l, s]) =>
        <ToggleRow key={k} cfg={cfg} set={set} k={k} label={l} sub={s} />)}

      <div style={GROUP_LABEL}>Screenshots</div>
      {scr.map(([k, l, s]) =>
        <ToggleRow key={k} cfg={cfg} set={set} k={k} label={l} sub={s} />)}
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="NUMBER_OF_SCREENSHOTS" label="NUMBER_OF_SCREENSHOTS" type="number" />
        <Field cfg={cfg} set={set} k="COMPRESS_SCSHOT" label="COMPRESS_SCSHOT (1–5)" type="number" />
      </div>

      <div style={GROUP_LABEL}>Cache & Database</div>
      <ToggleRow cfg={cfg} set={set} k="CACHE_DBONLINE"
                 label="Cache Online DB Results"
                 sub="CACHE_DBONLINE — cache TMDB/TVDB responses" />
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="SIZE_TH" label="SIZE_TH (GB threshold)" type="number" />
        <Field cfg={cfg} set={set} k="FAST_LOAD" label="FAST_LOAD" type="number" />
      </div>

      <div style={GROUP_LABEL}>YouTube</div>
      <ToggleRow cfg={cfg} set={set} k="YOUTUBE_CHANNEL_ENABLE"
                 label="Prefer Favourite Channel" sub="YOUTUBE_CHANNEL_ENABLE" />
      <div style={{ ...grid2, gridTemplateColumns: '1fr' }}>
        <Field cfg={cfg} set={set} k="YOUTUBE_FAV_CHANNEL_ID" label="YOUTUBE_FAV_CHANNEL_ID" wide />
      </div>

      <div style={GROUP_LABEL}>Watcher</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="WATCHER_INTERVAL" label="WATCHER_INTERVAL (sec)" type="number" />
      </div>

      <div style={GROUP_LABEL}>Release Metadata</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TORRENT_COMMENT" label="TORRENT_COMMENT" />
        <Field cfg={cfg} set={set} k="PREFERRED_LANG" label="PREFERRED_LANG" />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="RELEASER_SIGN" label="RELEASER_SIGN (max 20 chars)" />
      </div>

      <div style={GROUP_LABEL}>Tag Order (read-only)</div>
      <p style={{
        fontSize: 11, color: 'var(--fg-4)',
        fontFamily: 'var(--font-display)', marginBottom: 8,
      }}>Ordering used when building release names. Edit directly in Unit3Dbot.json for now.</p>
      <TagOrderChips title="TAG_ORDER_MOVIE" tags={cfg.TAG_ORDER_MOVIE ?? []} />
      <TagOrderChips title="TAG_ORDER_SERIE" tags={cfg.TAG_ORDER_SERIE ?? []} />
    </>
  );
}

function TagOrderChips({ title, tags }: { title: string; tags: string[] }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ ...LABEL_CSS, marginBottom: 6, display: 'block' }}>{title}</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {tags.length === 0 && (
          <span style={{
            fontSize: 11, color: 'var(--fg-4)',
            fontFamily: 'var(--font-display)',
          }}>— empty —</span>
        )}
        {tags.map((t, i) => (
          <span key={`${t}-${i}`} style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', borderRadius: 4,
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)',
          }}>
            <span style={{ color: 'var(--fg-4)' }}>{i + 1}</span>
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

function ImageHostsSection({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  const order: string[] = cfg.IMAGE_HOST_ORDER ?? IMAGE_HOSTS.map((h) => h.key);
  const move = (idx: number, dir: -1 | 1) => {
    const next = [...order];
    const swap = idx + dir;
    if (swap < 0 || swap >= next.length) return;
    [next[idx], next[swap]] = [next[swap], next[idx]];
    set('IMAGE_HOST_ORDER', next);
  };
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Priority Order</div>
      <p style={{
        fontSize: 12, color: 'var(--fg-3)',
        fontFamily: 'var(--font-display)', marginBottom: 12, lineHeight: 1.6,
      }}>
        Use arrows to reorder. The bot tries each host in order and falls back on failure.
      </p>
      {order.map((key, idx) => {
        const host = IMAGE_HOSTS.find((h) => h.key === key);
        if (!host) return null;
        return (
          <div key={key} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 10px', background: 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6, marginBottom: 6,
          }}>
            <span style={{
              width: 20, height: 20, borderRadius: '50%',
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 700, color: 'var(--blue)',
              fontFamily: 'var(--font-mono)',
            }}>{idx + 1}</span>
            <div style={{ flex: 1 }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                color: 'var(--fg-1)',
              }}>{host.label}</div>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
              }}>{host.url}</div>
            </div>
            <input
              type="password"
              value={cfg[`${key}_KEY`] === '__SET__' ? '' : (cfg[`${key}_KEY`] ?? '')}
              placeholder={cfg[`${key}_KEY`] === '__SET__' ? '••••••• (set)' : `${key}_KEY`}
              onChange={(e) => set(`${key}_KEY`, e.target.value)}
              style={{
                background: 'var(--bg-surface)', border: '1px solid var(--border)',
                borderRadius: 4, padding: '5px 8px', fontSize: 11,
                color: 'var(--fg-2)', width: 140,
                fontFamily: 'var(--font-mono)',
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <button onClick={() => move(idx, -1)} style={arrowBtn}>▲</button>
              <button onClick={() => move(idx, +1)} style={arrowBtn}>▼</button>
            </div>
          </div>
        );
      })}
    </>
  );
}

function PathsSection({ cfg, set, isMobile }: { cfg: Cfg; set: SetFn; isMobile?: boolean }) {
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10, marginBottom: 10,
  };
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Storage Paths</div>
      <div style={{ display: 'grid', gap: 10, marginBottom: 10 }}>
        <Field cfg={cfg} set={set} k="TORRENT_ARCHIVE_PATH" label="TORRENT_ARCHIVE_PATH" wide />
        <Field cfg={cfg} set={set} k="CACHE_PATH" label="CACHE_PATH" wide />
        <Field cfg={cfg} set={set} k="WATCHER_PATH" label="WATCHER_PATH" wide />
        <Field cfg={cfg} set={set} k="WATCHER_DESTINATION_PATH" label="WATCHER_DESTINATION_PATH" wide />
      </div>

      <div style={GROUP_LABEL}>FTP (ftpx)</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="FTPX_IP" label="FTPX_IP" />
        <Field cfg={cfg} set={set} k="FTPX_PORT" label="FTPX_PORT" />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="FTPX_USER" label="FTPX_USER" />
        <Field cfg={cfg} set={set} k="FTPX_PASS" label="FTPX_PASS" masked />
      </div>
      <div style={{ display: 'grid', gap: 10, marginBottom: 10 }}>
        <Field cfg={cfg} set={set} k="FTPX_LOCAL_PATH" label="FTPX_LOCAL_PATH" wide />
        <Field cfg={cfg} set={set} k="FTPX_ROOT" label="FTPX_ROOT" wide />
      </div>
      <ToggleRow cfg={cfg} set={set} k="FTPX_KEEP_ALIVE"
        label="Keep FTP connection alive" sub="FTPX_KEEP_ALIVE — reuse session across uploads" />
    </>
  );
}

type FsCheck = {
  media_root: string;
  seedings_dir: string;
  media_exists: boolean;
  seedings_exists: boolean;
  same_fs: boolean;
};

type Categories = {
  root: string;
  root_exists: boolean;
  categories: { id: string; label: string; count: number }[];
};

function SeedingSection({
  cfg, set, env, isMobile,
}: { cfg: Cfg; set: SetFn; env: Record<string, string>; isMobile?: boolean }) {
  const twoCols = isMobile ? '1fr' : '1fr 1fr';
  const [fsCheck, setFsCheck] = useState<FsCheck | null>(null);
  const [cats, setCats] = useState<Categories | null>(null);

  useEffect(() => {
    api.get<FsCheck>('/api/settings/fs-check').then(setFsCheck).catch(() => {});
    api.get<Categories>('/api/library/categories').then(setCats).catch(() => {});
  }, [cfg.U3DP_MEDIA_ROOT, cfg.U3DP_SEEDINGS_DIR]);

  const restartNote = (
    <span style={{
      fontSize: 10, color: 'var(--yellow)',
      fontFamily: 'var(--font-display)', marginLeft: 6,
    }}>· requires restart</span>
  );

  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Media Library Root</div>
      <p style={{
        fontSize: 12, color: 'var(--fg-3)',
        fontFamily: 'var(--font-display)', marginBottom: 10, lineHeight: 1.6,
      }}>
        Subfolders of this directory are auto-discovered as library categories.
        Env U3DP_MEDIA_ROOT overrides this value until unset.
      </p>
      <Field cfg={cfg} set={set} k="U3DP_MEDIA_ROOT" label="U3DP_MEDIA_ROOT" wide />
      {cats && (
        <div style={{
          marginTop: 8, padding: '8px 10px', background: 'var(--bg-card)',
          border: '1px solid var(--border)', borderRadius: 6,
          fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--fg-3)',
          display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center',
        }}>
          <span style={{ color: 'var(--fg-4)' }}>Discovered:</span>
          {cats.categories.length === 0 && <span>— no subfolders yet —</span>}
          {cats.categories.map((c) => (
            <span key={c.id} style={{
              padding: '2px 6px', background: 'var(--bg-base)',
              border: '1px solid var(--border)', borderRadius: 4,
              color: 'var(--fg-2)',
            }}>{c.label} <span style={{ color: 'var(--fg-4)' }}>({c.count})</span></span>
          ))}
        </div>
      )}

      <div style={GROUP_LABEL}>Seedings (Hardlink Target)</div>
      <Field cfg={cfg} set={set} k="U3DP_SEEDINGS_DIR" label="U3DP_SEEDINGS_DIR" wide />
      {fsCheck && (
        <div style={{
          marginTop: 8, display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 11, fontFamily: 'var(--font-display)',
          color: fsCheck.same_fs ? 'var(--green)' : 'var(--yellow)',
        }}>
          <span style={{
            padding: '2px 8px', borderRadius: 9999, fontWeight: 700,
            background: fsCheck.same_fs ? 'var(--green-dim)' : 'rgba(245,166,35,0.1)',
            border: `1px solid ${fsCheck.same_fs ? 'var(--green)' : 'var(--yellow)'}`,
          }}>
            {fsCheck.same_fs ? '✓ same filesystem' : '⚠ different filesystem'}
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-4)',
          }}>
            hardlinks require both paths to live on the same device
          </span>
        </div>
      )}

      <div style={GROUP_LABEL}>Upload History Database</div>
      <div style={{ display: 'grid', gap: 10 }}>
        <Field cfg={cfg} set={set} k="U3DP_DB_PATH" label="U3DP_DB_PATH" wide />
        <Field cfg={cfg} set={set} k="U3DP_TMDB_CACHE_PATH" label="U3DP_TMDB_CACHE_PATH" wide />
        <Field cfg={cfg} set={set} k="U3DP_LANG_CACHE_PATH" label="U3DP_LANG_CACHE_PATH" wide />
      </div>

      <div style={GROUP_LABEL}>Web UI Server</div>
      <p style={{
        fontSize: 11, color: 'var(--fg-4)',
        fontFamily: 'var(--font-display)', marginBottom: 8,
      }}>
        Host, port, proxy prefix and TLS toggle are read at startup. Save here, then restart
        the service for changes to take effect.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: twoCols, gap: 10 }}>
        <Field cfg={cfg} set={set} k="U3DP_HOST" label="U3DP_HOST" />
        <Field cfg={cfg} set={set} k="U3DP_PORT" label="U3DP_PORT" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: twoCols, gap: 10, marginTop: 10 }}>
        <Field cfg={cfg} set={set} k="U3DP_ROOT_PATH" label="U3DP_ROOT_PATH (nginx prefix)" />
        <Field cfg={cfg} set={set} k="U3DP_TMDB_LANG" label="U3DP_TMDB_LANG" />
      </div>
      <div style={{ marginTop: 10 }}>
        <ToggleRow
          cfg={cfg} set={set} k="U3DP_HTTPS_ONLY"
          label="HTTPS-only session cookies"
          sub="U3DP_HTTPS_ONLY — restart required"
        />
      </div>

      <div style={GROUP_LABEL}>App Auto-Update</div>
      <p style={{
        fontSize: 11, color: 'var(--fg-4)',
        fontFamily: 'var(--font-display)', marginBottom: 8,
      }}>
        Name of the systemd user unit that runs this service. Used by the "Update app"
        button to check unit availability and trigger <code>systemctl --user restart</code>{' '}
        after a successful update. Default: <code>unit3dprep-web.service</code>.
      </p>
      <Field cfg={cfg} set={set} k="U3DP_SYSTEMD_UNIT" label="U3DP_SYSTEMD_UNIT" wide />

      <div style={GROUP_LABEL}>Effective Values (live)</div>
      <p style={{
        fontSize: 11, color: 'var(--fg-4)',
        fontFamily: 'var(--font-display)', marginBottom: 8,
      }}>
        Env vars still override Unit3Dbot.json. Auth secrets (U3DP_SECRET, U3DP_PASSWORD_HASH,
        UNIT3DUP_CONFIG) stay env-only.{restartNote}
      </p>
      <div style={{ display: 'grid', gap: 4 }}>
        {Object.entries(env).map(([k, v]) => (
          <div key={k} style={{
            display: 'grid', gridTemplateColumns: '220px 1fr', alignItems: 'center',
            gap: 10, padding: '4px 0', borderBottom: '1px solid var(--border-subtle)',
          }}>
            <label style={{ ...LABEL_CSS, marginBottom: 0 }}>{k}</label>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)',
              wordBreak: 'break-all',
            }}>{v || '—'}</span>
          </div>
        ))}
      </div>

      <div style={GROUP_LABEL}>Wizard Defaults</div>
      <ToggleRow cfg={cfg} set={set} k="W_AUDIO_CHECK"
        label="Always run audio-check" sub="W_AUDIO_CHECK — verify ITA audio before upload" />
      <ToggleRow cfg={cfg} set={set} k="W_AUTO_TMDB"
        label="Auto-match TMDB" sub="W_AUTO_TMDB — run TMDB enrichment automatically" />
      <ToggleRow cfg={cfg} set={set} k="W_HIDE_UPLOADED"
        label="Hide already uploaded" sub="W_HIDE_UPLOADED — default state of Library filter" />
      <ToggleRow cfg={cfg} set={set} k="W_HIDE_NO_ITALIAN"
        label="Only with Italian audio" sub="W_HIDE_NO_ITALIAN — default Library filter hiding media without an ITA track" />
      <ToggleRow cfg={cfg} set={set} k="W_HARDLINK_ONLY"
        label="Hardlink-only mode" sub="W_HARDLINK_ONLY — skip unit3dup and only create hardlinks" />
      <ToggleRow cfg={cfg} set={set} k="W_CONFIRM_NAMES"
        label="Confirm renamed files" sub="W_CONFIRM_NAMES — always show the rename review step" />
    </>
  );
}

function ConsoleSection({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  const keys = [
    'NORMAL_COLOR', 'ERROR_COLOR', 'QUESTION_MESSAGE_COLOR',
    'WELCOME_MESSAGE_COLOR', 'WELCOME_MESSAGE_BORDER_COLOR',
    'PANEL_MESSAGE_COLOR', 'PANEL_MESSAGE_BORDER_COLOR',
  ];
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Console Colors</div>
      {keys.map((k) => (
        <div key={k} style={{
          display: 'grid', gridTemplateColumns: '220px 1fr',
          gap: 10, marginBottom: 8, alignItems: 'center',
        }}>
          <label style={{ ...LABEL_CSS, marginBottom: 0 }}>{k}</label>
          <input
            value={cfg[k] ?? ''}
            onChange={(e) => set(k, e.target.value)}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '7px 10px', fontSize: 12,
              color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
      ))}
      <div style={{ ...GROUP_LABEL, marginTop: 16 }}>Welcome Message</div>
      <Field cfg={cfg} set={set} k="WELCOME_MESSAGE" label="WELCOME_MESSAGE" wide />
    </>
  );
}

const arrowBtn: React.CSSProperties = {
  background: 'none', border: '1px solid var(--border)',
  borderRadius: 4, width: 22, height: 22,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', color: 'var(--fg-3)', padding: 0, fontSize: 9,
};
