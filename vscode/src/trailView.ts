// Sidebar trail list (TreeView), following the design system TrailList: status as icon +
// color, only the current row stands out, detours are indented under the segment they
// branch from, have no number and say "detour".
import * as vscode from 'vscode';
import type { ClimbState, Segment, Status } from './model';

const ICONS: Record<Status | 'current', [string, string | undefined]> = {
  passed: ['check', 'charts.green'],
  weak: ['warning', 'charts.yellow'],
  skipped: ['debug-step-over', 'descriptionForeground'],
  current: ['location', 'charts.blue'],
  todo: ['chevron-right', 'descriptionForeground'],
};

export class TrailItem extends vscode.TreeItem {
  constructor(readonly segment: Segment, number: number | undefined, status: Status | 'current', hasDetours: boolean) {
    super(segment.title, hasDetours ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None);
    const [icon, color] = ICONS[status];
    this.iconPath = new vscode.ThemeIcon(icon, color ? new vscode.ThemeColor(color) : undefined);
    const words: Record<Status | 'current', string> = {
      passed: vscode.l10n.t('Passed'), weak: vscode.l10n.t('Unsure'), skipped: vscode.l10n.t('Skipped'),
      current: vscode.l10n.t('Current'), todo: vscode.l10n.t('Not yet'),
    };
    this.label = number === undefined ? segment.title : `${number}. ${segment.title}`;
    this.description = segment.detour ? vscode.l10n.t('detour') : segment.file;
    this.tooltip = new vscode.MarkdownString(
      `**${segment.title}** — ${words[status]}\n\n\`${segment.file}\` · ${segment.start_line}–${segment.end_line}` +
        (segment.changed ? `\n\n$(git-compare) ${vscode.l10n.t('Changed')}` : ''),
      true,
    );
    this.accessibilityInformation = { label: `${this.label}, ${words[status]}, ${segment.file}` };
    this.contextValue = `segment.${status}`;
    this.id = `segment-${segment.order}`;
    this.command = { command: 'thrubase.openSegment', title: '', arguments: [segment.order] };
  }
}

export class TrailView implements vscode.TreeDataProvider<TrailItem> {
  private readonly emitter = new vscode.EventEmitter<TrailItem | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;

  constructor(private readonly state: ClimbState) {
    state.onDidChange(() => this.emitter.fire(undefined));
  }

  private statusOf(s: Segment): Status | 'current' {
    return s.order === this.state.focus ? 'current' : this.state.status(s);
  }

  getTreeItem(item: TrailItem): vscode.TreeItem {
    return item;
  }

  getChildren(parent?: TrailItem): TrailItem[] {
    const segments = this.state.trail?.segments ?? [];
    if (parent) {
      const i = segments.indexOf(parent.segment);
      const out: TrailItem[] = [];
      for (let j = i + 1; j < segments.length && segments[j].detour; j++) {
        out.push(new TrailItem(segments[j], undefined, this.statusOf(segments[j]), false));
      }
      return out;
    }
    const out: TrailItem[] = [];
    let number = 0;
    segments.forEach((s, i) => {
      if (s.detour && i > 0) return; // shown under the segment it branches from
      number += 1;
      const hasDetours = !!segments[i + 1]?.detour;
      out.push(new TrailItem(s, s.detour ? undefined : number, this.statusOf(s), hasDetours));
    });
    return out;
  }

  dispose(): void {
    this.emitter.dispose();
  }
}
