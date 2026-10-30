// The climb state the extension mirrors from core responses (for the sidebar and editor).
import * as vscode from 'vscode';

export type Status = 'passed' | 'weak' | 'skipped' | 'todo';

export interface Segment {
  order: number;
  title: string;
  file: string;
  start_line: number;
  end_line: number;
  nodes: string[];
  detour: boolean;
  changed: boolean;
  checkpoints: { id: string; type: 'flow' | 'locate' | 'diff_edge' }[];
}

export interface Trail {
  id: string;
  kind: 'full' | 'diff';
  segments: Segment[];
}

export interface Progress {
  trail_id: string;
  segments: Record<string, { status: Status }>;
  current: number | null;
}

export const segmentKey = (s: Segment) => [...s.nodes].sort().join('|');

export class ClimbState {
  trail: Trail | undefined;
  progress: Progress | undefined;
  /** the segment open in the panel */
  focus: number | undefined;
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChange = this.emitter.event;

  status(s: Segment): Status {
    return this.progress?.segments[segmentKey(s)]?.status ?? 'todo';
  }

  /** Mirrors what core returned; called for every RPC result passing through the panel. */
  observe(method: string, result: any): void {
    if (!result || typeof result !== 'object') return;
    if (method === 'trail.build') {
      const { progress, ...trail } = result;
      this.trail = trail as Trail;
      this.progress = progress as Progress;
      this.focus = this.progress?.current ?? undefined;
    } else if (method === 'trail.current') {
      this.trail = result.trail as Trail;
      this.progress = result.progress as Progress;
      this.focus = this.focus ?? this.progress?.current ?? undefined;
    } else if (method === 'checkpoint.answer') {
      this.progress = result.progress as Progress;
    } else if (method === 'checkpoint.skip' || method === 'progress.reset') {
      this.progress = result as Progress;
    } else {
      return;
    }
    this.emitter.fire();
  }

  setFocus(order: number | undefined): void {
    this.focus = order;
    this.emitter.fire();
  }

  dispose(): void {
    this.emitter.dispose();
  }
}
