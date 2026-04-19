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

export function SettingsView() {
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{
          width: 160, borderRight: '1px solid var(--border-subtle)',
          padding: '10px 6px', flexShrink: 0,
        }}>
          {SECTIONS.map((s) => {
            const Icon = s.icon;
            const active = section === s.id;
            return (
              <div
                key={s.id}
                onClick={() => setSection(s.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', borderRadius: 6, marginBottom: 2,
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

        <div style={{ flex: 1, padding: '18px 20px', overflowY: 'auto' }}>
          {section === 'tracker' && <TrackerSection cfg={cfg} set={set} />}
          {section === 'client' && <ClientSection cfg={cfg} set={set} />}
          {section === 'prefs' && <PrefsSection cfg={cfg} set={set} />}
          {section === 'imghost' && <ImageHostsSection cfg={cfg} set={set} />}
          {section === 'paths' && <PathsSection cfg={cfg} set={set} />}
          {section === 'seeding' && <SeedingSection env={data.env} />}
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

function TrackerSection({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10,
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

      <div style={GROUP_LABEL}>SIS</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="SIS_URL" label="SIS_URL" />
        <Field cfg={cfg} set={set} k="SIS_APIKEY" label="SIS_APIKEY" masked />
      </div>

      <div style={GROUP_LABEL}>External APIs</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TMDB_APIKEY" label="TMDB_APIKEY" masked />
        <Field cfg={cfg} set={set} k="TVDB_APIKEY" label="TVDB_APIKEY" masked />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="YOUTUBE_KEY" label="YOUTUBE_KEY" masked />
        <Field cfg={cfg} set={set} k="IGDB_CLIENT_ID" label="IGDB_CLIENT_ID" masked />
      </div>
    </>
  );
}

function ClientSection({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10,
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

      <div style={GROUP_LABEL}>Transmission</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TRASM_HOST" label="TRASM_HOST" />
        <Field cfg={cfg} set={set} k="TRASM_PORT" label="TRASM_PORT" />
      </div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="TRASM_USER" label="TRASM_USER" />
        <Field cfg={cfg} set={set} k="TRASM_PASS" label="TRASM_PASS" masked />
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
    </>
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

function PathsSection({ cfg, set }: { cfg: Cfg; set: SetFn }) {
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Storage Paths</div>
      <div style={{ display: 'grid', gap: 10, marginBottom: 10 }}>
        <Field cfg={cfg} set={set} k="TORRENT_ARCHIVE_PATH" label="TORRENT_ARCHIVE_PATH" wide />
        <Field cfg={cfg} set={set} k="CACHE_PATH" label="CACHE_PATH" wide />
        <Field cfg={cfg} set={set} k="WATCHER_PATH" label="WATCHER_PATH" wide />
        <Field cfg={cfg} set={set} k="WATCHER_DESTINATION_PATH" label="WATCHER_DESTINATION_PATH" wide />
      </div>
    </>
  );
}

function SeedingSection({ env }: { env: Record<string, string> }) {
  return (
    <>
      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Environment (read-only)</div>
      <p style={{
        fontSize: 12, color: 'var(--fg-3)',
        fontFamily: 'var(--font-display)', marginBottom: 12, lineHeight: 1.6,
      }}>
        Set via ITA_* env vars on the host. Edit via the systemd service unit or shell, not here.
      </p>
      <div style={{ display: 'grid', gap: 10 }}>
        {Object.entries(env).map(([k, v]) => (
          <div key={k} style={{
            display: 'grid', gridTemplateColumns: '220px 1fr', alignItems: 'center',
            gap: 10, padding: '6px 0', borderBottom: '1px solid var(--border-subtle)',
          }}>
            <label style={{ ...LABEL_CSS, marginBottom: 0 }}>{k}</label>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)',
              wordBreak: 'break-all',
            }}>{v || '—'}</span>
          </div>
        ))}
      </div>
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
