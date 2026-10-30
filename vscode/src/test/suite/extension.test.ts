import * as assert from 'node:assert';
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import * as vscode from 'vscode';
import type { ThrubaseApi } from '../../extension';



async function api(): Promise<ThrubaseApi> {
  const ext = vscode.extensions.getExtension<ThrubaseApi>('regx64.thrubase');
  assert.ok(ext, 'extension present');
  return ext.activate();
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

suite('Thrubase extension', () => {
  test('activates in a Python workspace and registers its commands', async () => {
    const a = await api();
    assert.ok(a.cli);
    const commands = await vscode.commands.getCommands(true);
    for (const c of ['thrubase.buildMap', 'thrubase.climbFull', 'thrubase.climbDiff', 'thrubase.climbSince',
      'thrubase.setApiKey', 'thrubase.clearApiKey']) {
      assert.ok(commands.includes(c), c);
    }
  });

  test('finds the CLI and talks JSON-RPC', async function () {
    if (!process.env.THRUBASE_TEST_CLI) this.skip();
    const a = await api();
    const found = await a.cli.resolve(false);
    assert.ok(found, 'cli found');
    const m = await a.cli.request<{ entries: string[] }>('map.build', {});
    assert.deepStrictEqual(m.entries, ['app/cli.py::main']);
  });

  test('the next request succeeds after the process is killed', async function () {
    if (!process.env.THRUBASE_TEST_CLI) this.skip();
    const a = await api();
    await a.cli.request('trail.build', { kind: 'full' });
    a.cli.kill();
    assert.strictEqual(a.cli.running, false);
    const cur = await a.cli.request<{ trail: { id: string } } | null>('trail.current', {});
    assert.ok(cur && cur.trail.id);
    assert.ok(a.cli.running);
  });

  test('ten saves at once make one diff.count call', async function () {
    if (!process.env.THRUBASE_TEST_CLI) this.skip();
    const a = await api();
    const before = a.diffWatcher.calls;
    for (let i = 0; i < 10; i++) a.diffWatcher.trigger();
    await new Promise((r) => setTimeout(r, 1800));
    assert.strictEqual(a.diffWatcher.calls, before + 1);
  });

  test('the trail view mirrors core and the editor highlights the segment', async function () {
    if (!process.env.THRUBASE_TEST_CLI) this.skip();
    const a = await api();
    const trail = await a.cli.request<any>('trail.build', { kind: 'full' });
    a.state.observe('trail.build', trail);
    assert.ok(a.state.trail && a.state.trail.segments.length >= 12);
    const seg = a.state.trail!.segments[0];
    await a.editor.setSegment(seg.file, [seg.start_line, seg.end_line]);
    const editor = vscode.window.activeTextEditor;
    assert.ok(editor);
    assert.strictEqual(a.editor.relative(editor!.document.uri), seg.file);
  });

  test('a full climb from the command runs through the webview panel', async function () {
    if (!process.env.THRUBASE_TEST_CLI) this.skip();
    const a = await api();
    a.state.trail = undefined;
    const current = () => a.state.trail;
    await vscode.commands.executeCommand('thrubase.climbFull');
    const deadline = Date.now() + 30000;
    while (!current() && Date.now() < deadline) await new Promise((r) => setTimeout(r, 200));
    const trail = current();
    assert.ok(trail, 'the panel built a trail through the bridge');
    assert.strictEqual(trail.kind, 'full');
    // The panel reports the current segment, which the editor highlights.
    const until = Date.now() + 10000;
    while (a.state.focus === undefined && Date.now() < until) await new Promise((r) => setTimeout(r, 200));
    assert.strictEqual(a.state.focus, a.state.progress?.current ?? trail.segments[0].order);
  });

  test('the LLM key reaches the CLI only through its environment', async function () {
    if (!process.env.THRUBASE_TEST_CLI) this.skip();
    const a = await api();
    const secret = 'sk-thrubase-test-0123456789';
    const ws = process.env.THRUBASE_TEST_WORKSPACE!;
    const settingsPath = join(ws, '.vscode', 'settings.json');
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8'));
    writeFileSync(settingsPath, JSON.stringify({ ...settings, 'thrubase.llm.provider': 'openai-compatible', 'thrubase.llm.endpoint': 'http://127.0.0.1:9/v1' }));
    await new Promise((r) => setTimeout(r, 500));
    await (a as any).secrets.storage.store('thrubase.apiKey', secret);
    const env = await (a as any).secrets.environment();
    assert.strictEqual(env.THRUBASE_API_KEY, secret);
    a.cli.restart();
    const trail = await a.cli.request<any>('trail.build', { kind: 'full' });
    await a.cli.request('segment.guide', { trailId: trail.id, order: 1 }).catch(() => undefined);
    const home = process.env.THRUBASE_HOME!;
    for (const f of walk(home)) assert.ok(!readFileSync(f).includes(secret), `key found in ${f}`);
    writeFileSync(settingsPath, JSON.stringify(settings));
  });


});
