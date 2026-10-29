import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import Mocha from 'mocha';

export function run(): Promise<void> {
  const mocha = new Mocha({ ui: 'tdd', color: true, timeout: 60000 });
  const dir = resolve(__dirname);
  const korean = process.env.THRUBASE_TEST_LOCALE === 'ko';
  for (const f of readdirSync(dir)) {
    if (!f.endsWith('.test.js')) continue;
    if ((f === 'l10n.test.js') === korean) mocha.addFile(resolve(dir, f));
  }
  return new Promise((ok, fail) => {
    mocha.run((failures) => (failures ? fail(new Error(`${failures} tests failed`)) : ok()));
  });
}
