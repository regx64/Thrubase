import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { test } from 'node:test';

const root = resolve(__dirname, '..', '..', '..');
const json = (p: string) => JSON.parse(readFileSync(join(root, p), 'utf8'));

test('package.nls.ko.json covers every contribution string', () => {
  assert.deepEqual(Object.keys(json('package.nls.ko.json')).sort(), Object.keys(json('package.nls.json')).sort());
  const manifest = readFileSync(join(root, 'package.json'), 'utf8');
  for (const key of manifest.match(/%([\w.]+)%/g) ?? []) {
    assert.ok(key.slice(1, -1) in json('package.nls.json'), key);
  }
});

test('the Korean l10n bundle covers every runtime string', () => {
  const bundle = json('l10n/bundle.l10n.ko.json');
  const src = join(root, 'src');
  const used = new Set<string>();
  for (const f of readdirSync(src).filter((n) => n.endsWith('.ts'))) {
    for (const m of readFileSync(join(src, f), 'utf8').matchAll(/l10n\.t\('((?:[^'\\]|\\.)*)'/g)) used.add(m[1]);
  }
  assert.ok(used.size > 10);
  for (const s of used) assert.ok(s in bundle, `missing Korean for: ${s}`);
});
