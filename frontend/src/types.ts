export type Category = string;
export type Kind = 'movie' | 'series' | 'episode';

export interface VideoFile {
  path: string;
  name: string;
  uploaded: boolean;
}

export interface Season {
  number: number;
  label: string;
  path: string;
  episode_count: number;
  size: string;
  langs: string[];
  lang_scanned: boolean;
  already_uploaded: boolean;
  uploaded_episodes: number;
  all_episodes_uploaded: boolean;
  video_files: VideoFile[];
}

export interface LibraryItem {
  name: string;
  path: string;
  category: Category;
  kind: 'movie' | 'series';
  title: string;
  year: string;
  size: string;
  total_files: number;
  tmdb_id: string;
  tmdb_kind: string;
  tmdb_title_en: string;
  tmdb_original_title: string;
  tmdb_poster: string;
  tmdb_overview: string;
  tmdb_overview_en: string;
  langs: string[];
  lang_scanned: boolean;
  already_uploaded: boolean;
  seasons?: Season[];
  all_seasons_uploaded?: boolean;
  video_files?: VideoFile[];
}

export interface TrackerStatus { name: string; online: boolean; configured?: boolean; }

export interface VersionTarget {
  current: string | null;
  latest: string | null;
  newer: boolean;
}

export interface VersionAppTarget extends VersionTarget {
  release?: {
    version: string;
    body: string;
    html_url: string;
    published_at: string;
    name: string;
  } | null;
}

export interface VersionBotTarget extends VersionTarget {
  installed: boolean;
  repo_path?: string;
}

export interface VersionInfo {
  app: VersionAppTarget;
  webup: VersionBotTarget;
  can_update_app: boolean;
  can_update_webup?: boolean;
  docker?: boolean;
}

export interface WebupHealth {
  ok: boolean;
  base_url?: string;
  version?: string;
  scan_path?: string;
  torrent_archive_path?: string;
  torrent_client?: string;
  latency_ms?: number;
  ws_connected?: boolean;
  error?: string;
}

export interface UploadedRecord {
  id: number;
  category: Category;
  kind: Kind;
  source_path: string;
  seeding_path: string;
  tmdb_id: string;
  title: string;
  year: string;
  final_name: string;
  uploaded_at: string;
  unit3dup_exit_code: number | null;
  hardlink_only: boolean;
  duplicate_skipped?: boolean;
  duplicate_info?: {
    id?: string | number;
    name?: string;
    size?: number;
    type?: string;
    resolution?: string;
    uploader?: string;
    seeders?: number;
    leechers?: number;
    created_at?: string;
    details_link?: string;
    tmdb_id?: number;
  } | null;
}

export interface QueueTorrent {
  hash: string;
  name: string;
  size: number;
  progress: number;
  state: string;
  ratio: number;
  category: string;
  tracker: string;
  save_path: string;
}

export interface SearchResult {
  tracker: string;
  id: number;
  name: string;
  type: string;
  resolution: string;
  size: string;
  seeders: number;
  leechers: number;
  uploader: string;
  url: string;
}

export interface ReseedTorrent {
  tracker: string;
  id: number;
  name: string;
  type: string;
  size: number;
  size_human: string;
  resolution: string;
  seeders: number;
  leechers: number;
  details_link: string;
  download_link: string;
}

export interface ReseedCandidate {
  source_path: string;
  item_name: string;
  category: string;
  kind: string;          // 'movie' | 'episode'
  season: number | null;
  episode: number | null;
  local_size: number;
  local_size_human: string;
  torrent: ReseedTorrent;
}

export interface ReseedMatch {
  source_path: string;
  item_name: string;
  category: string;
  kind: string;
  size: number;
  size_human: string;
}

export interface ReseedSuggest {
  torrent: ReseedTorrent | null;
  matches: ReseedMatch[];
}

// A manual-search result: only torrents the user can reseed (exact size match),
// each carrying its matching local file(s).
export interface ReseedSearchResult {
  torrent: ReseedTorrent;
  local_matches: ReseedMatch[];
}

// Drives ReseedWizardModal. Auto mode presets both `torrent` and `local`;
// manual mode leaves them undefined and the wizard loads the torrent + the
// size-matched local files from /reseed/suggest.
export interface ReseedCtx {
  tracker: string;
  torrentId: number;
  torrentName: string;
  torrent?: ReseedTorrent;
  local?: ReseedMatch;
}

export type LogKind = 'info' | 'ok' | 'warn' | 'error' | 'debug';

export type LogSource =
  | 'app'
  | 'http'
  | 'upload'
  | 'client'
  | 'tracker'
  | 'wizard'
  | 'webup'
  | 'system';

export interface LogLine {
  ts: string;
  kind: LogKind;
  name: string;
  msg: string;
  source?: LogSource | string;
  event?: string;
  count?: number;
}

export interface WizardState {
  path: string;
  category: Category;
  kind: Kind;
  step: string;
  audio_ok: boolean;
  audio_override?: boolean;
  tmdb_id: string;
  tmdb_kind: string;
  tmdb_title: string;
  tmdb_year: string;
  tmdb_poster: string;
  tmdb_overview: string;
  final_names: Record<string, string>;
  folder_name: string;
  seeding_path: string;
  upload_done: boolean;
  exit_code: number | null;
  hardlink_only: boolean;
}

export interface WizardCtx {
  kind: Kind;
  path: string;
  category: Category;
  tmdbId?: string;
  title?: string;
  year?: string;
  name?: string;
  overview?: string;
  season?: {
    n: number;
    path: string;
    episodes: number;
  };
}
