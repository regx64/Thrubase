// Watches change volume and suggests a diff climb in the status bar once uncommitted changes
// cross the threshold. Saves from the editor and writes from agents (file system events) are
// debounced into one `diff.count` call.
import * as vscode from 'vscode';
import { RpcError, type ThrubaseCli } from './cli';
import { Debouncer } from './debounce';

export class DiffWatcher implements vscode.Disposable {
  readonly item: vscode.StatusBarItem;
  private readonly debouncer: Debouncer;
  private readonly subs: vscode.Disposable[] = [];
  /** number of diff.count calls, for tests */
  calls = 0;
  lastCount = 0;

  constructor(private readonly cli: ThrubaseCli, delayMs = 1000) {
    // Right-aligned, theme default colors: a suggestion, not a warning.
    this.item = vscode.window.createStatusBarItem('thrubase.diffSuggestion', vscode.StatusBarAlignment.Right, 100);
    this.item.name = 'Thrubase';
    this.item.command = 'thrubase.climbDiff';
    this.item.tooltip = vscode.l10n.t('Thrubase: climb the uncommitted changes');
    this.debouncer = new Debouncer(delayMs, () => void this.check());
    const watcher = vscode.workspace.createFileSystemWatcher('**/*.py');
    this.subs.push(
      watcher,
      watcher.onDidChange(() => this.debouncer.trigger()),
      watcher.onDidCreate(() => this.debouncer.trigger()),
      watcher.onDidDelete(() => this.debouncer.trigger()),
      vscode.workspace.onDidSaveTextDocument((d) => d.languageId === 'python' && this.debouncer.trigger()),
      vscode.workspace.onDidChangeConfiguration((e) => e.affectsConfiguration('thrubase.diffSuggestThreshold') && this.debouncer.trigger()),
    );
  }

  get threshold(): number {
    return vscode.workspace.getConfiguration('thrubase').get<number>('diffSuggestThreshold', 5);
  }

  trigger(): void {
    this.debouncer.trigger();
  }

  async check(): Promise<void> {
    this.calls += 1;
    try {
      const counts = await this.cli.request<{ changedFunctions: number }>('diff.count', {});
      this.lastCount = counts.changedFunctions;
      if (counts.changedFunctions >= this.threshold) {
        this.item.text = vscode.l10n.t('$(debug-start) Climb {0} changes', counts.changedFunctions);
        this.item.show();
      } else {
        this.item.hide();
      }
    } catch (e) {
      // Not a git repository, or the CLI is missing: no suggestion, no noise.
      if (!(e instanceof RpcError)) console.error(e);
      this.item.hide();
    }
  }

  dispose(): void {
    this.debouncer.dispose();
    this.subs.forEach((d) => d.dispose());
    this.item.dispose();
  }
}
