// Single fetch/SSE layer. Handles ROOT_PATH (read from BASE_URL or window.location)
// and 401 → redirect to /login.

const base = (() => {
  // Backend injects `window.__ROOT_PATH__` into index.html at serve time so
  // the SPA knows its reverse-proxy mount (e.g. '/itatorrents').
  const w = window as unknown as { __ROOT_PATH__?: string };
  if (typeof w.__ROOT_PATH__ === 'string') return w.__ROOT_PATH__.replace(/\/$/, '');
  return '';
})();

export function apiUrl(path: string): string {
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(apiUrl(path), {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    ...init,
  });
  if (res.status === 401) {
    // Let the app shell redirect to login — we fire a custom event.
    window.dispatchEvent(new CustomEvent('app:unauthenticated'));
    throw new ApiError(401, 'Not authenticated');
  }
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* noop */ }
    let msg = `HTTP ${res.status}`;
    if (body && typeof body === 'object' && 'detail' in body) {
      msg = String((body as { detail: unknown }).detail);
    }
    throw new ApiError(res.status, msg, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get:  <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put:  <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  del:  <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

// -------------------------------------------------------------------- SSE --

export interface SseHandlers {
  onEvent?: (name: string, data: string) => void;
  onError?: (ev: Event) => void;
  onOpen?: () => void;
}

export function openSSE(path: string, handlers: SseHandlers): () => void {
  const es = new EventSource(apiUrl(path), { withCredentials: true });
  es.onopen = () => handlers.onOpen?.();
  es.onerror = (e) => handlers.onError?.(e);
  // Named events are the primary channel; default 'message' mirrors to onEvent.
  es.onmessage = (e) => handlers.onEvent?.('message', e.data);
  const named = [
    'line', 'log', 'progress', 'input_needed', 'error',
    'done', 'file_result', 'enriched', 'lang_scanned', 'ping',
  ];
  const listeners: Array<[string, (e: MessageEvent) => void]> = [];
  for (const name of named) {
    const h = (e: MessageEvent) => handlers.onEvent?.(name, e.data);
    es.addEventListener(name, h as EventListener);
    listeners.push([name, h]);
  }
  return () => {
    for (const [n, h] of listeners) es.removeEventListener(n, h as EventListener);
    es.close();
  };
}
