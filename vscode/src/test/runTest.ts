import { cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { downloadAndUnzipVSCode, resolveCliArgsFromVSCodeExecutablePath, runTests } from '@vscode/test-electron';

/** `1.131.2026090407` (installed pack) -> `1.131.0` */
function languagePackVersion(cliArgs: string[]): string | undefined {
  const flag = cliArgs.find((a) => a.startsWith('--extensions-dir'));
  const dir = flag?.includes('=') ? flag.split('=')[1] : flag ? cliArgs[cliArgs.indexOf(flag) + 1] : undefined;
  if (!dir || !existsSync(dir)) return undefined;
  const pack = readdirSync(dir).find((d) => d.toLowerCase().startsWith('ms-ceintl.vscode-language-pack-ko-'));
  if (!pack) return undefined;
  const version = String(JSON.parse(readFileSync(join(dir, pack, 'package.json'), 'utf8')).version ?? '');
  const m = /^(\d+)\.(\d+)\./.exec(version);
  return m ? `${m[1]}.${m[2]}.0` : undefined;
}

async function main() {
  const extensionDevelopmentPath = resolve(__dirname, '../../');
  const extensionTestsPath = resolve(__dirname, './suite/index');
  // A throwaway workspace: the calls_app fixture from core plus workspace settings.
  const workspace = mkdtempSync(join(tmpdir(), 'thrubase-ws-'));
  cpSync(resolve(extensionDevelopmentPath, '../core/tests/fixtures/calls_app'), workspace, { recursive: true });
  const home = mkdtempSync(join(tmpdir(), 'thrubase-home-'));
  const settings = { 'thrubase.cliPath': process.env.THRUBASE_TEST_CLI ?? '', 'thrubase.diffSuggestThreshold': 1 };
  require('node:fs').mkdirSync(join(workspace, '.vscode'), { recursive: true });
  writeFileSync(join(workspace, '.vscode', 'settings.json'), JSON.stringify(settings));
  const common = ['--disable-workspace-trust', '--skip-welcome', '--skip-release-notes'];
  const vscodeExecutablePath = await downloadAndUnzipVSCode(process.env.VSCODE_TEST_VERSION ?? 'stable');
  await runTests({
    vscodeExecutablePath,
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: [workspace, ...common, '--disable-extensions'],
    extensionTestsEnv: { THRUBASE_HOME: home, THRUBASE_TEST_WORKSPACE: workspace },
  });
  // V9: command names and runtime strings in a Korean VS Code (needs the Korean language pack).
  const installPack = (executable: string): string[] => {
    const [cli, ...cliArgs] = resolveCliArgsFromVSCodeExecutablePath(executable);
    const install = spawnSync(cli, [...cliArgs, '--install-extension', 'MS-CEINTL.vscode-language-pack-ko', '--force'],
      { encoding: 'utf-8', stdio: 'inherit', shell: process.platform === 'win32' });
    if (install.status !== 0) throw new Error('could not install the Korean language pack');
    return cliArgs;
  };
  // Language packs only apply to the VS Code minor version they were built for, and the
  // Marketplace pack can lag behind stable: run the Korean suite on the pack's version, and
  // install the pack again with that version's CLI so it registers the translations.
  const cliArgs = installPack(vscodeExecutablePath);
  const koVersion = process.env.VSCODE_KO_VERSION ?? languagePackVersion(cliArgs);
  console.log(`Korean run on VS Code ${koVersion ?? 'stable'}`);
  const koExecutable = koVersion ? await downloadAndUnzipVSCode(koVersion) : vscodeExecutablePath;
  if (koExecutable !== vscodeExecutablePath) installPack(koExecutable);
  await runTests({
    vscodeExecutablePath: koExecutable,
    extensionDevelopmentPath,
    extensionTestsPath: resolve(__dirname, './warmup/index'),
    launchArgs: [workspace, ...common, '--locale', 'ko'],
  });
  await runTests({
    vscodeExecutablePath: koExecutable,
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: [workspace, ...common, '--locale', 'ko'],
    extensionTestsEnv: { THRUBASE_HOME: home, THRUBASE_TEST_WORKSPACE: workspace, THRUBASE_TEST_LOCALE: 'ko' },
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
