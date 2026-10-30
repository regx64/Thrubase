// Shapes of what core returns (see core/schema/thrubase.schema.json). Answers never reach the UI.

export type Status = 'passed' | 'weak' | 'skipped' | 'current' | 'todo';
export type Lang = 'en' | 'ko';

export interface MapNode {
  id: string;
  kind: 'module' | 'class' | 'function' | 'method';
  name: string;
  qualname: string;
  file: string;
  start_line: number;
  end_line: number;
  loc: number;
  h: number;
  x: number;
  y: number;
  role: 'entry' | 'summit' | 'isolated' | null;
  entry_kind: string | null;
}

export interface MapEdge {
  src: string;
  dst: string | null;
  kind: 'call' | 'inherit' | 'ref';
  line: number;
  resolved: boolean;
  inferred: boolean;
}

export interface TerrainMapData {
  repo: { root: string; name: string; snapshot: string; files: number; skipped: number; languages: string[] };
  nodes: MapNode[];
  edges: MapEdge[];
  entries: string[];
  summits: string[];
  isolated: string[];
  stats: { files: number; resolution_rate: number; seconds: number };
}

export interface Option {
  id: string;
  label: string;
}

export interface Checkpoint {
  id: string;
  type: 'flow' | 'locate' | 'diff_edge';
  prompt: string;
  node: string;
  options: Option[];
  file: string;
}

export interface Segment {
  order: number;
  title: string;
  file: string;
  start_line: number;
  end_line: number;
  nodes: string[];
  detour: boolean;
  changed: boolean;
  isolated: boolean;
  checkpoints: Checkpoint[];
}

export interface CheckpointState {
  attempts: number;
  state: 'idle' | 'hint' | 'passed' | 'revealed' | 'skipped';
}

export interface SegmentProgress {
  key: string;
  status: 'passed' | 'weak' | 'skipped' | 'todo';
  checkpoints: Record<string, CheckpointState>;
}

export interface Progress {
  trail_id: string;
  kind: 'full' | 'diff';
  segments: Record<string, SegmentProgress>;
  current: number | null;
}

export interface Trail {
  id: string;
  kind: 'full' | 'diff';
  snapshot: string;
  segments: Segment[];
  path: string[];
  since: string | null;
  progress?: Progress;
}

export interface AnswerResult {
  result: 'correct' | 'hint' | 'revealed';
  hint?: string;
  explanation?: string;
  evidenceLines?: [number, number];
  file?: string;
  answer?: string | [number, number][];
  progress: Progress;
}

export interface CodeExcerpt {
  file: string;
  startLine: number;
  lines: string[];
  highlight: [number, number];
}

export interface InitializeResult {
  serverVersion: string;
  schemaVersion: number;
  languages: string[];
  lang: Lang;
  root: string | null;
  guides: boolean;
}

export const segmentKey = (s: Pick<Segment, 'nodes'>) => [...s.nodes].sort().join('|');
