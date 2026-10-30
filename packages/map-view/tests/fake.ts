// An in-memory stand-in for core, used by the App tests.
import type { Transport, HostEvents } from '../src/transport';
import { RemoteError } from '../src/transport';
import type { Progress, Trail } from '../src/types';

const seg = (order: number, title: string, type: 'flow' | 'locate', detour = false) => ({
  order, title, file: `app/m${order}.py`, start_line: 10 * order, end_line: 10 * order + 5, nodes: [`app/m${order}.py::${title}`],
  detour, changed: false, isolated: false,
  checkpoints: [{
    id: `t1:${order}:s`, type, prompt: `Question ${order}?`, node: `app/m${order}.py::${title}`, file: `app/m${order}.py`,
    options: type === 'flow' ? [{ id: 'a', label: `${title}_a` }, { id: 'b', label: `${title}_b` }] : [],
  }],
});

export class FakeCore implements Transport {
  readonly host: 'web' | 'vscode';
  calls: [string, Record<string, unknown>][] = [];
  answers: Record<string, unknown> = { 't1:1:s': 'a', 't1:2:s': 22, 't1:3:s': 'b' };
  attempts: Record<string, number> = {};
  progress: Progress;
  trail: Trail;
  events = new Set<HostEvents>();
  opened: [string, number][] = [];
  diffError: number | null = null;

  constructor(host: 'web' | 'vscode' = 'web') {
    this.host = host;
    this.trail = {
      id: 't1', kind: 'full', snapshot: 's', since: null, path: [],
      segments: [seg(1, 'main', 'flow'), seg(2, 'load', 'locate'), seg(3, 'run', 'flow'), seg(4, 'extra', 'flow', true)],
    };
    this.progress = this.freshProgress();
  }

  freshProgress(): Progress {
    const segments: Progress['segments'] = {};
    for (const s of this.trail.segments) {
      segments[s.nodes.join('|')] = { key: s.nodes.join('|'), status: 'todo', checkpoints: { s: { attempts: 0, state: 'idle' } } };
    }
    return { trail_id: 't1', kind: 'full', segments, current: 1 };
  }

  private seg(cpId: string) {
    const order = Number(cpId.split(':')[1]);
    return this.trail.segments.find((s) => s.order === order)!;
  }

  private update() {
    const next = this.trail.segments.find((s) => !s.detour && this.progress.segments[s.nodes.join('|')].status === 'todo');
    this.progress = { ...this.progress, current: next ? next.order : null };
  }

  async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    this.calls.push([method, params]);
    const r = (v: unknown) => Promise.resolve(v as T);
    switch (method) {
      case 'initialize':
        return r({ serverVersion: '0.1.0', schemaVersion: 1, languages: ['python'], lang: params.lang ?? 'en', root: '/r', guides: false });
      case 'map.build':
        return r({
          repo: { root: '/r', name: 'demo', snapshot: 's', files: 3, skipped: 0, languages: ['python'] },
          nodes: this.trail.segments.map((s, i) => ({
            id: s.nodes[0], kind: 'function', name: s.title, qualname: s.title, file: s.file, start_line: s.start_line,
            end_line: s.end_line, loc: 5, h: 1 - i * 0.2, x: 0.2 + i * 0.2, y: 0.5, role: i === 0 ? 'entry' : null, entry_kind: null,
          })),
          edges: [], entries: [this.trail.segments[0].nodes[0]], summits: [], isolated: [],
          stats: { files: 3, resolution_rate: 1, seconds: 0.1 },
        });
      case 'trail.current':
        return r(null);
      case 'trail.build':
        if (params.kind === 'diff' && this.diffError) throw new RemoteError(this.diffError, 'diff error');
        return r({ ...this.trail, progress: this.progress });
      case 'segment.guide':
        return r({ guide: null, cached: false });
      case 'segment.code': {
        const s = this.trail.segments.find((x) => x.order === params.order)!;
        return r({ file: s.file, startLine: s.start_line, lines: Array.from({ length: 6 }, (_, i) => `line ${s.start_line + i}`), highlight: [s.start_line, s.end_line] });
      }
      case 'checkpoint.answer': {
        const id = String(params.checkpointId);
        const s = this.seg(id);
        const key = s.nodes.join('|');
        const n = (this.attempts[id] = (this.attempts[id] ?? 0) + 1);
        const right = params.answer === this.answers[id];
        const result = right ? 'correct' : n === 1 ? 'hint' : 'revealed';
        const state = result === 'correct' ? 'passed' : result === 'hint' ? 'hint' : 'revealed';
        const status = result === 'correct' ? 'passed' : result === 'revealed' ? 'weak' : 'todo';
        this.progress = { ...this.progress, segments: { ...this.progress.segments, [key]: { key, status, checkpoints: { s: { attempts: n, state } } } } };
        this.update();
        if (result === 'hint') return r({ result, hint: 'Look again at lines 10–15.', progress: this.progress });
        const answer = typeof this.answers[id] === 'number' ? [[this.answers[id], this.answers[id]]] : this.answers[id];
        return r({ result, explanation: 'Because.', evidenceLines: [10, 10], file: s.file, answer, progress: this.progress });
      }
      case 'checkpoint.skip': {
        const s = this.seg(String(params.checkpointId));
        const key = s.nodes.join('|');
        this.progress = { ...this.progress, segments: { ...this.progress.segments, [key]: { key, status: 'skipped', checkpoints: { s: { attempts: 0, state: 'skipped' } } } } };
        this.update();
        return r(this.progress);
      }
      case 'progress.reset':
        this.progress = this.freshProgress();
        return r(this.progress);
      default:
        throw new RemoteError(-32601, method);
    }
  }

  onNotification() {
    return () => {};
  }

  openFile(file: string, line: number) {
    this.opened.push([file, line]);
  }

  listen(events: HostEvents) {
    this.events.add(events);
    return () => this.events.delete(events);
  }
}
