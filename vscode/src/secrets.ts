// The LLM key lives only in SecretStorage and reaches the CLI only through the child
// process environment (THRUBASE_API_KEY). It is never written to disk.
import * as vscode from 'vscode';

const KEY = 'thrubase.apiKey';

export class Secrets {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChange = this.changed.event;

  constructor(readonly storage: vscode.SecretStorage) {
    storage.onDidChange((e) => e.key === KEY && this.changed.fire());
  }

  get(): Thenable<string | undefined> {
    return this.storage.get(KEY);
  }

  async set(): Promise<boolean> {
    const value = await vscode.window.showInputBox({
      title: vscode.l10n.t('Thrubase: LLM key'),
      prompt: vscode.l10n.t('Stored in VS Code SecretStorage and passed to the CLI only through its environment.'),
      password: true,
      ignoreFocusOut: true,
      validateInput: (v) => (v.trim() ? undefined : vscode.l10n.t('The key is empty.')),
    });
    if (!value) return false;
    await this.storage.store(KEY, value.trim());
    const provider = vscode.workspace.getConfiguration('thrubase').get<string>('llm.provider', 'none');
    if (provider === 'none') {
      const pick = await vscode.window.showQuickPick(['anthropic', 'openai-compatible'], {
        title: vscode.l10n.t('Which provider is this key for?'),
      });
      if (pick) await vscode.workspace.getConfiguration('thrubase').update('llm.provider', pick, vscode.ConfigurationTarget.Global);
    }
    void vscode.window.showInformationMessage(vscode.l10n.t('Thrubase: the LLM key is stored.'));
    return true;
  }

  async clear(): Promise<void> {
    await this.storage.delete(KEY);
    void vscode.window.showInformationMessage(vscode.l10n.t('Thrubase: the LLM key is deleted.'));
  }

  /** Environment for `thrubase rpc`: settings plus the key. */
  async environment(): Promise<Record<string, string>> {
    const cfg = vscode.workspace.getConfiguration('thrubase');
    const env: Record<string, string> = {
      THRUBASE_LLM_PROVIDER: cfg.get<string>('llm.provider', 'none'),
      THRUBASE_LLM_MODEL: cfg.get<string>('llm.model', ''),
      THRUBASE_LLM_ENDPOINT: cfg.get<string>('llm.endpoint', ''),
    };
    const key = await this.get();
    if (key) env.THRUBASE_API_KEY = key;
    for (const [k, v] of Object.entries(env)) if (!v) delete env[k];
    return env;
  }

  dispose(): void {
    this.changed.dispose();
  }
}
