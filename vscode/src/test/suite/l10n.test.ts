import * as assert from 'node:assert';
import * as vscode from 'vscode';

suite('Thrubase in Korean', () => {
  test('command names and runtime strings are Korean', async () => {
    assert.strictEqual(vscode.env.language, 'ko');
    const ext = vscode.extensions.getExtension('regx64.thrubase');
    assert.ok(ext);
    await ext.activate();
    // Newer VS Code versions localize titles to { original, value }.
    const commands = ext.packageJSON.contributes.commands as { command: string; title: string | { value: string } }[];
    const title = (id: string) => {
      const t = commands.find((c) => c.command === id)?.title;
      return typeof t === 'string' ? t : t?.value;
    };
    assert.strictEqual(title('thrubase.climbFull'), '전체 등반 시작');
    assert.strictEqual(title('thrubase.climbDiff'), '변경 등반 시작');
    assert.strictEqual(title('thrubase.buildMap'), '지형도 만들기');
    assert.strictEqual(vscode.l10n.t('Passed'), '통과');
    assert.strictEqual(vscode.l10n.t('$(debug-start) Climb {0} changes', 7), '$(debug-start) 변경 7개 등반');
  });
});
