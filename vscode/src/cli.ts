// CLI discovery, the child process and the JSON-RPC client. No analysis logic lives in the
// extension: everything goes to `thrubase rpc` over stdio.
import { spawn, type ChildProcess } from 'node:child_process';
import * as vscode from 'vscode';
import {
  CancellationTokenSource,
  createMessageConnection,
  StreamMessageReader,
  StreamMessageWriter,
  type MessageConnection,
} from 'vscode-jsonrpc/node';
import { cliVersion, compatible, discover, installCommand, upgradeCommand, type CliCommand } from './discovery';

export interface ProgressParams {
  stage: string;
  done: number;
  total: number;
}

export class RpcError extends Error {
  constructor(public readonly code: number, message: string) {
    super(message);
  }
}

const SLOW = new Set(['map.build', 'trail.build']);

export class ThrubaseCli implements vscode.Disposable {
  private proc: ChildProcess | undefined;
  private conn: MessageConnection | undefined;
  private starting: Promise<MessageConnection> | undefined;
  private restarts: number[] = [];
  private disposed = false;
  private readonly progressEmitter = new vscode.EventEmitter<ProgressParams>();
  readonly onProgress = this.progressEmitter.event;
  private readonly output: vscode.OutputChannel;
  cli: CliCommand | undefined;
  root: string | undefined;

  constructor(
    private readonly extensionVersion: string,
    private readonly env: () => Promise<Record<string, string>>,
    output?: vscode.OutputChannel,
  ) {
    this.output = output ?? vscode.window.createOutputChannel('Thrubase');
  }

  /** Finds the CLI and checks its version. Shows the install or upgrade prompt when needed. */
  async resolve(interactive = true): Promise<CliCommand | undefined> {
    const configured = vscode.workspace.getConfiguration('thrubase').get<string>('cliPath', '');
    const found = discover(configured);
    if (!found) {
      if (interactive) void this.promptInstall(configured);
      return undefined;
    }
    const version = await cliVersion(found);
    if (!version) {
      this.output.appendLine(`could not run ${found.command} --version`);
      if (interactive) void this.promptInstall(configured);
      return undefined;
    }
    if (!compatible(version, this.extensionVersion) && interactive) {
      const copy = vscode.l10n.t('Copy upgrade command');
      void vscode.window
        .showWarningMessage(
          vscode.l10n.t('Thrubase CLI {0} does not match the extension ({1}). Upgrade the CLI.', version, this.extensionVersion),
          copy,
        )
        .then((choice) => {
          if (choice === copy) void vscode.env.clipboard.writeText(upgradeCommand(found.source));
        });
    }
    this.output.appendLine(`using ${found.command} ${found.prefix.join(' ')} (${found.source}, ${version})`);
    this.cli = found;
    return found;
  }

  private async promptInstall(configured: string): Promise<void> {
    const copy = vscode.l10n.t('Copy install command');
    const settings = vscode.l10n.t('Open settings');
    const message = configured
      ? vscode.l10n.t('The Thrubase CLI was not found at {0}.', configured)
      : vscode.l10n.t('The Thrubase CLI was not found. Install it with: {0}', installCommand());
    const choice = await vscode.window.showErrorMessage(message, copy, settings);
    if (choice === copy) await vscode.env.clipboard.writeText(installCommand());
    if (choice === settings) await vscode.commands.executeCommand('workbench.action.openSettings', 'thrubase.cliPath');
  }

  private async start(): Promise<MessageConnection> {
    const cli = this.cli ?? (await this.resolve());
    if (!cli) throw new RpcError(-1, vscode.l10n.t('The Thrubase CLI was not found.'));
    const extraEnv = await this.env();
    const proc = spawn(cli.command, [...cli.prefix, 'rpc'], {
      cwd: this.root,
      env: { ...process.env, ...extraEnv, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.proc = proc;
    proc.stderr?.on('data', (d: Buffer) => this.output.append(d.toString('utf8')));
    const conn = createMessageConnection(new StreamMessageReader(proc.stdout!), new StreamMessageWriter(proc.stdin!));
    conn.onNotification('$/progress', (p: ProgressParams) => this.progressEmitter.fire(p));
    conn.listen();
    proc.on('exit', (code) => {
      this.output.appendLine(`thrubase rpc exited (${code})`);
      if (this.proc === proc) {
        this.proc = undefined;
        this.conn = undefined;
        conn.dispose();
      }
    });
    proc.on('error', (err) => this.output.appendLine(`thrubase rpc failed: ${err.message}`));
    this.conn = conn;
    const lang = resolveLang();
    await conn.sendRequest('initialize', { root: this.root, lang, clientVersion: this.extensionVersion });
    return conn;
  }

  /** The connection, starting the process if needed. One automatic restart is allowed per
   * minute when the process dies; after that the error is shown. */
  private async connection(): Promise<MessageConnection> {
    if (this.disposed) throw new RpcError(-1, 'disposed');
    if (this.conn) return this.conn;
    if (!this.starting) {
      const now = Date.now();
      this.restarts = this.restarts.filter((t) => now - t < 60_000);
      if (this.restarts.length > 1) {
        throw new RpcError(-1, vscode.l10n.t('The Thrubase CLI stopped unexpectedly. See the Thrubase output.'));
      }
      this.restarts.push(now);
      this.starting = this.start().finally(() => {
        this.starting = undefined;
      });
    }
    return this.starting;
  }

  async request<T>(method: string, params: Record<string, unknown> = {}, token?: vscode.CancellationToken): Promise<T> {
    const conn = await this.connection();
    const source = new CancellationTokenSource();
    const sub = token?.onCancellationRequested(() => source.cancel());
    try {
      return (await conn.sendRequest(method, params, source.token)) as T;
    } catch (e: any) {
      if (e && typeof e.code === 'number') throw new RpcError(e.code, e.message);
      throw e;
    } finally {
      sub?.dispose();
      source.dispose();
    }
  }

  /** Requests that can take a while report progress in the window. */
  async requestWithProgress<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (!SLOW.has(method)) return this.request<T>(method, params);
    return vscode.window.withProgress(
      { location: vscode.ProgressLocation.Window, title: 'Thrubase', cancellable: true },
      async (progress, token) => {
        const sub = this.onProgress((p) => {
          const label = p.stage === 'parse' ? `${p.done}/${p.total}` : p.stage;
          progress.report({ message: vscode.l10n.t('Building the terrain map ({0})', label) });
        });
        try {
          return await this.request<T>(method, params, token);
        } finally {
          sub.dispose();
        }
      },
    );
  }

  /** Stops the process (it is started again on the next request), e.g. after the key changed. */
  restart(): void {
    this.kill();
    this.restarts = [];
  }

  /** For tests: what a crash looks like. */
  kill(): void {
    this.conn?.dispose();
    this.conn = undefined;
    this.proc?.kill();
    this.proc = undefined;
  }

  get running(): boolean {
    return !!this.proc && this.proc.exitCode === null;
  }

  dispose(): void {
    this.disposed = true;
    this.kill();
    this.progressEmitter.dispose();
  }
}

export function resolveLang(): 'en' | 'ko' {
  const setting = vscode.workspace.getConfiguration('thrubase').get<string>('language', 'auto');
  if (setting === 'en' || setting === 'ko') return setting;
  return vscode.env.language.toLowerCase().startsWith('ko') ? 'ko' : 'en';
}
