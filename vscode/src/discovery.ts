// CLI discovery without any VS Code dependency, so it can be unit tested:
// configured path → `thrubase` on PATH → pipx environment → `uvx thrubase`.
import { execFile } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, join } from 'node:path';

export interface CliCommand {
  /** executable to spawn */
  command: string;
  /** arguments before the subcommand (`uvx thrubase …` needs one) */
  prefix: string[];
  source: 'setting' | 'path' | 'pipx' | 'uvx';
}

export interface Env {
  platform: NodeJS.Platform;
  env: NodeJS.ProcessEnv;
  home: string;
  isFile(path: string): boolean;
}

export const realEnv = (): Env => ({
  platform: process.platform,
  env: process.env,
  home: homedir(),
  isFile: (p) => {
    try {
      return existsSync(p) && statSync(p).isFile();
    } catch {
      return false;
    }
  },
});

/** Finds an executable on PATH, honouring PATHEXT on Windows (thrubase.exe, .cmd, .bat). */
export function which(name: string, e: Env): string | undefined {
  const pathVar = e.env.PATH ?? e.env.Path ?? '';
  const sep = e.platform === 'win32' ? ';' : delimiter;
  const exts = e.platform === 'win32'
    ? (e.env.PATHEXT ?? '.EXE;.CMD;.BAT;.COM').split(';').filter(Boolean).map((x) => x.toLowerCase())
    : [''];
  const joiner = e.platform === 'win32' ? '\\' : '/';
  for (const dir of pathVar.split(sep).filter(Boolean)) {
    for (const ext of exts) {
      const candidate = `${dir.replace(/[\\/]+$/, '')}${joiner}${name}${ext}`;
      if (e.isFile(candidate)) return candidate;
    }
  }
  return undefined;
}

/** Where pipx puts entry points: PIPX_BIN_DIR, else ~/.local/bin (also on Windows). */
export function pipxCandidates(e: Env): string[] {
  const win = e.platform === 'win32';
  const sepJoin = (...parts: string[]) => (win ? parts.map((p) => p.replace(/[\\/]+$/, '')).join('\\') : join(...parts));
  const dirs = [e.env.PIPX_BIN_DIR, sepJoin(e.home, '.local', 'bin')].filter((d): d is string => !!d);
  const names = win ? ['thrubase.exe', 'thrubase.cmd'] : ['thrubase'];
  return dirs.flatMap((d) => names.map((n) => sepJoin(d, n)));
}

export function discover(configured: string, e: Env = realEnv()): CliCommand | undefined {
  if (configured.trim()) {
    return e.isFile(configured.trim()) ? { command: configured.trim(), prefix: [], source: 'setting' } : undefined;
  }
  const onPath = which('thrubase', e);
  if (onPath) return { command: onPath, prefix: [], source: 'path' };
  const pipx = pipxCandidates(e).find((p) => e.isFile(p));
  if (pipx) return { command: pipx, prefix: [], source: 'pipx' };
  const uvx = which('uvx', e);
  if (uvx) return { command: uvx, prefix: ['thrubase'], source: 'uvx' };
  return undefined;
}

/** `thrubase 0.1.3` → `0.1.3` */
export function parseVersion(output: string): string | undefined {
  return /(\d+)\.(\d+)\.(\d+)/.exec(output)?.[0];
}

/** The extension accepts only a CLI with the same minor version. */
export function compatible(cli: string, extension: string): boolean {
  const [a, b] = [cli.split('.'), extension.split('.')];
  return a[0] === b[0] && a[1] === b[1];
}

export function installCommand(platform: NodeJS.Platform = process.platform): string {
  return platform === 'win32' ? 'py -m pip install --user pipx && py -m pipx install thrubase' : 'pipx install thrubase';
}

export function upgradeCommand(source: CliCommand['source']): string {
  return source === 'uvx' ? 'uv cache clean thrubase' : 'pipx upgrade thrubase';
}

export function cliVersion(cli: CliCommand, timeoutMs = 15000): Promise<string | undefined> {
  return new Promise((resolve) => {
    execFile(cli.command, [...cli.prefix, '--version'], { timeout: timeoutMs, windowsHide: true }, (err, stdout) => {
      resolve(err ? undefined : parseVersion(String(stdout)));
    });
  });
}
