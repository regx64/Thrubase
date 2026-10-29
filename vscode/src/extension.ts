import { execFile } from 'node:child_process';
import * as vscode from 'vscode';
import { resolveLang, RpcError, ThrubaseCli } from './cli';
import { DiffWatcher } from './diffWatcher';
import { EditorBridge } from './editor';
import { ClimbState } from './model';
import { ClimbPanel, MapView, PANEL_TYPE } from './panel';
import { Secrets } from './secrets';
import { TrailView } from './trailView';

export interface ThrubaseApi {
  cli: ThrubaseCli;
  secrets: Secrets;
  state: ClimbState;
  panel: ClimbPanel;
  diffWatcher: DiffWatcher;
  editor: EditorBridge;
}

function workspaceRoot(): vscode.Uri | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri;
}

/** Base refs for `thrubase.climbSince`: recent commits, branches and tags. */
function gitRefs(cwd: string): Promise<vscode.QuickPickItem[]> {
  return new Promise((resolve) => {
    execFile('git', ['for-each-ref', '--count=40', '--sort=-committerdate', '--format=%(refname:short)\t%(subject)',
      'refs/heads', 'refs/tags', 'refs/remotes'], { cwd, windowsHide: true }, (err, stdout) => {
      const items: vscode.QuickPickItem[] = [1, 2, 3, 5].map((n) => ({ label: `HEAD~${n}`, description: vscode.l10n.t('{0} commits back', n) }));
      if (!err) {
        for (const line of String(stdout).split('\n').filter(Boolean)) {
          const [label, detail] = line.split('\t');
          items.push({ label, detail });
        }
      }
      resolve(items);
    });
  });
}

export async function activate(context: vscode.ExtensionContext): Promise<ThrubaseApi> {
  const version = String(context.extension.packageJSON.version ?? '0.1.0');
  const secrets = new Secrets(context.secrets);
  const output = vscode.window.createOutputChannel('Thrubase');
  const cli = new ThrubaseCli(version, () => secrets.environment(), output);
  cli.root = workspaceRoot()?.fsPath;
  const state = new ClimbState();
  const editor = new EditorBridge(workspaceRoot);
  const panel = new ClimbPanel(context, cli, editor, state, resolveLang);
  const mapView = new MapView(context, cli, editor, state, resolveLang);
  const trailView = new TrailView(state);
  const diffWatcher = new DiffWatcher(cli);

  const climb = async (kind: 'full' | 'diff', since?: string) => {
    await panel.post({ type: 'startClimb', kind, since });
  };

  context.subscriptions.push(
    output, secrets, cli, state, editor, panel, mapView, trailView, diffWatcher,
    vscode.window.registerTreeDataProvider('thrubase.trail', trailView),
    vscode.window.registerWebviewViewProvider('thrubase.map', mapView, { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.window.registerWebviewPanelSerializer(PANEL_TYPE, {
      async deserializeWebviewPanel(webviewPanel: vscode.WebviewPanel) {
        panel.attach(webviewPanel);
      },
    }),
    vscode.commands.registerCommand('thrubase.openPanel', () => panel.show()),
    vscode.commands.registerCommand('thrubase.buildMap', async () => {
      panel.show();
      try {
        await cli.requestWithProgress('map.build', {});
        await panel.post({ type: 'refresh' });
      } catch (e) {
        if (e instanceof RpcError) void vscode.window.showErrorMessage(`Thrubase: ${e.message}`);
      }
    }),
    vscode.commands.registerCommand('thrubase.climbFull', () => climb('full')),
    vscode.commands.registerCommand('thrubase.climbDiff', () => climb('diff')),
    vscode.commands.registerCommand('thrubase.climbSince', async () => {
      const root = workspaceRoot();
      if (!root) return;
      const pick = await vscode.window.showQuickPick(gitRefs(root.fsPath), {
        title: vscode.l10n.t('Climb the changes since…'),
        placeHolder: vscode.l10n.t('Pick a base revision'),
        matchOnDetail: true,
      });
      if (pick) await climb('diff', pick.label);
    }),
    vscode.commands.registerCommand('thrubase.setApiKey', async () => {
      if (await secrets.set()) cli.restart();
    }),
    vscode.commands.registerCommand('thrubase.clearApiKey', async () => {
      await secrets.clear();
      cli.restart();
    }),
    vscode.commands.registerCommand('thrubase.openSegment', async (order: number) => {
      const seg = state.trail?.segments.find((s) => s.order === order);
      if (!seg) return;
      await panel.post({ type: 'selectSegment', order });
      state.setFocus(order);
      await editor.setSegment(seg.file, [seg.start_line, seg.end_line]);
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('thrubase.cliPath')) {
        cli.cli = undefined;
        cli.restart();
      } else if (e.affectsConfiguration('thrubase.llm') || e.affectsConfiguration('thrubase.language')) {
        cli.restart();
      }
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      cli.root = workspaceRoot()?.fsPath;
      cli.restart();
    }),
  );

  // Find the CLI quietly at start-up; the prompt appears when the user runs a command.
  void cli.resolve(false).then((found) => {
    if (found) {
      diffWatcher.trigger();
      void cli.request('trail.current', {}).then((r) => state.observe('trail.current', r), () => undefined);
    }
  });

  return { cli, secrets, state, panel, diffWatcher, editor };
}

export function deactivate(): void {
  // Disposables in context.subscriptions stop the CLI process.
}
