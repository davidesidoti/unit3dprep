import { useEffect, useState } from 'react';
import { FolderOpen, Folder, File as FileIcon, CornerLeftUp } from 'lucide-react';
import { api } from '../api';

interface Entry { name: string; path: string; type: 'dir' | 'file'; }
interface FsResponse { path: string; parent: string; entries: Entry[]; is_file: boolean; }

interface Props {
  onSelect: (path: string) => void;
  startPath?: string;
}

export function FileBrowser({ onSelect, startPath }: Props) {
  const [cwd, setCwd] = useState(startPath ?? '');
  const [data, setData] = useState<FsResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setError('');
    api.get<FsResponse>(`/api/fs${cwd ? `?path=${encodeURIComponent(cwd)}` : ''}`)
      .then((r) => { if (!cancelled) { setData(r); setCwd(r.path); } })
      .catch((e) => { if (!cancelled) setError(e.message || 'failed'); });
    return () => { cancelled = true; };
  }, [cwd]);

  const handleClick = (entry: Entry) => {
    setSelected(entry.path);
    onSelect(entry.path);
    if (entry.type === 'dir') setCwd(entry.path);
  };

  const crumbs = (data?.path || cwd || '').split(/[\\/]/).filter(Boolean);

  return (
    <div style={{
      background: 'var(--bg-base)', border: '1px solid var(--border)',
      borderRadius: 6, overflow: 'hidden', marginBottom: 12,
    }}>
      <div style={{
        padding: '6px 10px', background: '#0a0c12',
        borderBottom: '1px solid var(--border-subtle)',
        fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)',
        display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap',
      }}>
        <FolderOpen size={12} color="var(--yellow)" />
        {crumbs.map((c, i) => (
          <span key={i} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <span
              style={{ color: 'var(--blue)', cursor: 'pointer' }}
              onClick={() => setCwd('/' + crumbs.slice(0, i + 1).join('/'))}
            >{c}</span>
            {i < crumbs.length - 1 && <span>/</span>}
          </span>
        ))}
      </div>
      <div style={{ maxHeight: 180, overflowY: 'auto' }}>
        {error && (
          <div style={{ padding: 10, color: 'var(--red)', fontSize: 11 }}>
            {error}
          </div>
        )}
        {data && data.parent && data.parent !== data.path && (
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '6px 10px', cursor: 'pointer',
              borderBottom: '1px solid var(--bg-surface)',
            }}
            onClick={() => setCwd(data.parent)}
          >
            <CornerLeftUp size={13} color="var(--fg-3)" />
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)',
            }}>..</span>
          </div>
        )}
        {data?.entries.map((e) => (
          <div
            key={e.path}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '6px 10px', cursor: 'pointer',
              background: selected === e.path ? 'var(--blue-muted)' : 'transparent',
              borderBottom: '1px solid var(--bg-surface)',
            }}
            onClick={() => handleClick(e)}
          >
            {e.type === 'dir'
              ? <Folder size={13} color="var(--yellow)" />
              : <FileIcon size={13} color="var(--fg-2)" />}
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 12,
              color: e.type === 'dir' ? 'var(--fg-1)' : 'var(--fg-2)',
              flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>{e.name}</span>
            <span style={{
              fontSize: 10, color: 'var(--fg-4)',
              fontFamily: 'var(--font-display)',
            }}>{e.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
