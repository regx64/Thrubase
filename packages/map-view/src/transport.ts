// One interface, two transports: HTTP for the local web UI and postMessage inside VS Code.
// Method names and parameters are identical to the JSON-RPC methods in core.

export class RemoteError extends Error {
  constructor(public code: number, message: string) {
    super(message);
  }
}

export interface HostEvents {
  /** VS Code: a line the user clicked in the editor (answers locate questions). */
  onLocate?: (file: string, line: number) => void;
  /** VS Code: the extension asks the view to start a climb (status bar, commands). */
  onStartClimb?: (kind: 'full' | 'diff', since?: string) => void;
  /** VS Code: the user picked a segment in the sidebar trail list. */
  onSelectSegment?: (order: number) => void;
}

export interface Transport {
  readonly host: 'web' | 'vscode';
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>;
  /** $/progress and other notifications */
  onNotification(cb: (method: string, params: Record<string, unknown>) => void): () => void;
  /** Open a file in the editor (VS Code) — the web shows code itself. */
  openFile?(file: string, line: number, endLine?: number): void;
  /** Tell the host which segment is current so it can highlight it (VS Code). */
  setCurrent?(trailId: string, order: number | null, file?: string, range?: [number, number]): void;
  listen(events: HostEvents): () => void;
}

type Listener = (method: string, params: Record<string, unknown>) => void;

export class HttpTransport implements Transport {
  readonly host = 'web' as const;
  private listeners = new Set<Listener>();
  private polling = 0;
  private timer: ReturnType<typeof setInterval> | undefined;

  constructor(private token: string, private base = '') {}

  async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const slow = method === 'map.build' || method === 'trail.build';
    if (slow) this.startPolling();
    try {
      const res = await fetch(`${this.base}/api/${method}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Thrubase-Token': this.token },
        body: JSON.stringify(params),
      });
      const data = await res.json();
      if (data.error) throw new RemoteError(data.error.code, data.error.message);
      return data.result as T;
    } finally {
      if (slow) this.stopPolling();
    }
  }

  private startPolling() {
    this.polling += 1;
    if (this.timer) return;
    this.timer = setInterval(async () => {
      try {
        const p = await this.call<Record<string, unknown>>('$/progress');
        this.listeners.forEach((l) => l('$/progress', p));
      } catch {
        /* progress is best effort */
      }
    }, 250);
  }

  private stopPolling() {
    this.polling -= 1;
    if (this.polling <= 0 && this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
      this.polling = 0;
    }
  }

  onNotification(cb: Listener) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  listen() {
    return () => {};
  }
}

interface VsCodeApi {
  postMessage(message: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
}

declare global {
  interface Window {
    acquireVsCodeApi?: () => VsCodeApi;
  }
}

export class PostMessageTransport implements Transport {
  readonly host = 'vscode' as const;
  private next = 1;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private listeners = new Set<Listener>();
  private events = new Set<HostEvents>();

  constructor(private api: VsCodeApi, target: Window = window) {
    target.addEventListener('message', (event: MessageEvent) => this.receive(event.data));
  }

  private receive(msg: any) {
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'response') {
      const p = this.pending.get(msg.id);
      if (!p) return;
      this.pending.delete(msg.id);
      if (msg.error) p.reject(new RemoteError(msg.error.code, msg.error.message));
      else p.resolve(msg.result);
    } else if (msg.type === 'notification') {
      this.listeners.forEach((l) => l(msg.method, msg.params ?? {}));
    } else if (msg.type === 'locate') {
      this.events.forEach((e) => e.onLocate?.(msg.file, msg.line));
    } else if (msg.type === 'startClimb') {
      this.events.forEach((e) => e.onStartClimb?.(msg.kind, msg.since));
    } else if (msg.type === 'selectSegment') {
      this.events.forEach((e) => e.onSelectSegment?.(msg.order));
    }
  }

  call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const id = this.next++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.api.postMessage({ type: 'request', id, method, params });
    });
  }

  onNotification(cb: Listener) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  openFile(file: string, line: number, endLine?: number) {
    this.api.postMessage({ type: 'openFile', file, line, endLine });
  }

  setCurrent(trailId: string, order: number | null, file?: string, range?: [number, number]) {
    this.api.postMessage({ type: 'current', trailId, order, file, range });
  }

  listen(events: HostEvents) {
    this.events.add(events);
    return () => this.events.delete(events);
  }
}

/** Picks the transport for where the UI runs. The web token arrives once in the URL and is
 * then kept only in sessionStorage, so it does not linger in history or referrers. */
export function createTransport(win: Window = window): Transport {
  if (typeof win.acquireVsCodeApi === 'function') {
    return new PostMessageTransport(win.acquireVsCodeApi(), win);
  }
  const url = new URL(win.location.href);
  let token = url.searchParams.get('token') ?? '';
  try {
    if (token) {
      win.sessionStorage.setItem('thrubase-token', token);
      url.searchParams.delete('token');
      win.history.replaceState(null, '', url.pathname + url.search + url.hash);
    } else {
      token = win.sessionStorage.getItem('thrubase-token') ?? '';
    }
  } catch {
    /* storage can be unavailable; the token from the URL still works for this page */
  }
  return new HttpTransport(token);
}
