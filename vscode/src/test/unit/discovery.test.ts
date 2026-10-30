import assert from 'node:assert/strict';
import { test } from 'node:test';
import { compatible, discover, installCommand, parseVersion, pipxCandidates, which, type Env } from '../../discovery';
import { Debouncer } from '../../debounce';

const env = (platform: NodeJS.Platform, vars: Record<string, string>, files: string[], home = '/home/u'): Env => ({
  platform,
  env: vars,
  home,
  isFile: (p) => files.includes(p),
});

test('finds the .exe entry point on Windows through PATHEXT', () => {
  const e = env('win32', { Path: 'C:\\Python\\Scripts;C:\\Users\\u\\.local\\bin', PATHEXT: '.COM;.EXE;.BAT' },
    ['C:\\Users\\u\\.local\\bin\\thrubase.exe']);
  assert.equal(which('thrubase', e), 'C:\\Users\\u\\.local\\bin\\thrubase.exe');
  assert.deepEqual(discover('', e), { command: 'C:\\Users\\u\\.local\\bin\\thrubase.exe', prefix: [], source: 'path' });
});

test('order: setting, PATH, pipx, uvx', () => {
  const files = ['/opt/custom/thrubase', '/usr/bin/thrubase', '/home/u/.local/bin/thrubase', '/usr/bin/uvx'];
  assert.equal(discover('/opt/custom/thrubase', env('linux', { PATH: '/usr/bin' }, files))?.source, 'setting');
  assert.equal(discover('', env('linux', { PATH: '/usr/bin' }, files))?.source, 'path');
  assert.equal(discover('', env('linux', { PATH: '/usr/bin' }, files.slice(2)))?.command, '/home/u/.local/bin/thrubase');
  const uvx = discover('', env('linux', { PATH: '/usr/bin' }, ['/usr/bin/uvx']));
  assert.deepEqual(uvx, { command: '/usr/bin/uvx', prefix: ['thrubase'], source: 'uvx' });
  assert.equal(discover('', env('linux', { PATH: '/usr/bin' }, [])), undefined);
  assert.equal(discover('/missing', env('linux', { PATH: '/usr/bin' }, files)), undefined);
});

test('pipx candidates honour PIPX_BIN_DIR', () => {
  const c = pipxCandidates(env('darwin', { PIPX_BIN_DIR: '/pipx/bin' }, []));
  assert.equal(c[0], '/pipx/bin/thrubase');
  assert.ok(pipxCandidates(env('win32', {}, [], 'C:\\Users\\u')).includes('C:\\Users\\u\\.local\\bin\\thrubase.exe'));
});

test('version compatibility is by minor version', () => {
  assert.equal(parseVersion('thrubase 0.1.3\n'), '0.1.3');
  assert.equal(parseVersion('garbage'), undefined);
  assert.ok(compatible('0.1.9', '0.1.0'));
  assert.ok(!compatible('0.2.0', '0.1.0'));
  assert.ok(!compatible('1.1.0', '0.1.0'));
  assert.match(installCommand('linux'), /pipx install thrubase/);
});

test('debouncer collapses bursts into one call', async () => {
  let calls = 0;
  const d = new Debouncer(30, () => calls++);
  for (let i = 0; i < 10; i++) d.trigger();
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(calls, 1);
  d.trigger();
  d.dispose();
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(calls, 1);
});
