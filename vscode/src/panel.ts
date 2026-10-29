// Hosts the shared map-view UI in a Webview panel (large terrain map + checkpoints) and in a
// sidebar WebviewView (small terrain map). Messages are bridged to `thrubase rpc`.
import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
import { RpcError, type ThrubaseCli } from './cli';
import type { EditorBridge } from './editor';
import type { ClimbState } from './model';

export const PANEL_TYPE = 'thrubase.panel';

interface Message {
  type: string;
  id?: number;
  method?: string;
  params?: Record<string, unknown>;
  file?: string;
  line?: number;
  endLine?: number;
  trailId?: string;
  order?: number | null;
  range?: [number, number];
}

export function webviewHtml(webview: vscode.Webview, extensionUri: vscode.Uri, lang: string, mode: 'panel' | 'map'): string {
  const media = vscode.Uri.joinPath(extensionUri, 'media', 'map-view');
  const script = webview.asWebviewUri(vscode.Uri.joinPath(media, 'assets', 'index.js'));
  const style = webview.asWebviewUri(vscode.Uri.joinPath(media, 'assets', 'index.css'));
  const nonce = randomBytes(16).toString('base64');
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${nonce}'`,
  ].join('; ');
  return `<!doctype html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="${style}">
<title>Thrubase</title>
</head>
<body>
<div id="root"></div>
<script nonce="${nonce}">window.__THRUBASE_LANG__ = ${JSON.stringify(lang)}; window.__THRUBASE_MODE__ = ${JSON.stringify(mode)};</script>
<script nonce="${nonce}" type="module" src="${script}"></script>
</body>
</html>`;
}

/** Connects one webview to the CLI, the editor and the shared climb state. */
export class Bridge implements vscode.Disposable {
  private readonly subs: vscode.Disposable[] = [];

  constructor(
    private readonly webview: vscode.Webview,
    private readonly cli: ThrubaseCli,
    private readonly editor: EditorBridge,
    private readonly state: ClimbState,
    private readonly primary: boolean,
    private readonly onReady: () => void = () => {},
  ) {
    this.subs.push(
      webview.onDidReceiveMessage((m: Message) => void this.receive(m)),
      cli.onProgress((p) => void webview.postMessage({ type: 'notification', method: '$/progress', params: p })),
    );
    if (primary) {
      this.subs.push(editor.onLocate(({ file, line }) => void webview.postMessage({ type: 'locate', file, line })));
    }
  }

  post(message: unknown): Thenable<boolean> {
    return this.webview.postMessage(message);
  }

  private async receive(m: Message): Promise<void> {
    if (m.type === 'ready') {
      this.onReady();
    } else if (m.type === 'request' && m.method) {
      try {
        const result = await this.cli.requestWithProgress(m.method, m.params ?? {});
        this.state.observe(m.method, result);
        if (m.method === 'checkpoint.answer') this.showEvidence(result);
        await this.webview.postMessage({ type: 'response', id: m.id, result });
      } catch (e) {
        const error = e instanceof RpcError ? { code: e.code, message: e.message } : { code: -32603, message: String(e) };
        await this.webview.postMessage({ type: 'response', id: m.id, error });
      }
    } else if (m.type === 'openFile' && m.file) {
      await this.editor.open(m.file, m.line ?? 1, m.endLine, false);
    } else if (m.type === 'current' && this.primary) {
      this.state.setFocus(m.order ?? undefined);
      await this.editor.setSegment(m.order == null ? undefined : m.file, m.range);
    }
  }

  private showEvidence(result: any): void {
    if (result?.file && Array.isArray(result.evidenceLines)) this.editor.showEvidence(result.file, result.evidenceLines);
  }

  dispose(): void {
    this.subs.forEach((d) => d.dispose());
  }
}

export class ClimbPanel implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private bridge: Bridge | undefined;
  private ready: Promise<void> = Promise.resolve();

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly cli: ThrubaseCli,
    private readonly editor: EditorBridge,
    private readonly state: ClimbState,
    private readonly lang: () => string,
  ) {}

  /** Opens (or reveals) the panel beside the editor. */
  show(): vscode.WebviewPanel {
    if (this.panel) {
      this.panel.reveal(vscode.ViewColumn.Beside, true);
      return this.panel;
    }
    const panel = vscode.window.createWebviewPanel(PANEL_TYPE, 'Thrubase', { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true }, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
    });
    this.attach(panel);
    return panel;
  }

  /** Used by the WebviewPanelSerializer to restore the panel after a restart. */
  attach(panel: vscode.WebviewPanel): void {
    this.panel = panel;
    panel.iconPath = vscode.Uri.joinPath(this.context.extensionUri, 'media', 'activitybar.svg');
    panel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
    };
    let ready: () => void = () => {};
    // Commands wait until the UI says it is listening.
    this.ready = new Promise((resolve) => {
      ready = resolve;
    });
    this.bridge = new Bridge(panel.webview, this.cli, this.editor, this.state, true, () => ready());
    panel.webview.html = webviewHtml(panel.webview, this.context.extensionUri, this.lang(), 'panel');
    panel.onDidDispose(() => {
      this.bridge?.dispose();
      this.bridge = undefined;
      this.panel = undefined;
      void this.editor.setSegment(undefined, undefined);
    });
  }

  async post(message: unknown): Promise<void> {
    this.show();
    await this.ready;
    await this.bridge?.post(message);
  }

  dispose(): void {
    this.panel?.dispose();
  }
}

export class MapView implements vscode.WebviewViewProvider, vscode.Disposable {
  private bridge: Bridge | undefined;
  private view: vscode.WebviewView | undefined;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly cli: ThrubaseCli,
    private readonly editor: EditorBridge,
    private readonly state: ClimbState,
    private readonly lang: () => string,
  ) {
    state.onDidChange(() => void this.view?.webview.postMessage({ type: 'refresh' }));
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
    };
    view.webview.html = webviewHtml(view.webview, this.context.extensionUri, this.lang(), 'map');
    this.bridge?.dispose();
    this.bridge = new Bridge(view.webview, this.cli, this.editor, this.state, false);
    view.onDidDispose(() => {
      this.bridge?.dispose();
      this.bridge = undefined;
      this.view = undefined;
    });
  }

  dispose(): void {
    this.bridge?.dispose();
  }
}
