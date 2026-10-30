import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const api = JSON.parse(readFileSync(fileURLToPath(new URL('./api.json', import.meta.url)), 'utf8'));

/** Mocks /api/* like core: same methods, grading against the recorded answer keys. */
export async function mockApi(page: Page, opts: { lang?: 'en' | 'ko' } = {}) {
  let lang = opts.lang ?? 'en';
  const attempts: Record<string, number> = {};
  const progress = structuredClone(api.trail.progress);
  const segOf = (id: string) => api.trail.segments.find((s: any) => s.order === Number(id.split(':')[1]));
  const key = (s: any) => [...s.nodes].sort().join('|');
  const refresh = () => {
    const next = api.trail.segments.find((s: any) => !s.detour && progress.segments[key(s)].status === 'todo');
    progress.current = next ? next.order : null;
  };
  await page.route('**/api/**', async (route) => {
    const method = route.request().url().split('/api/')[1];
    const params = route.request().postDataJSON() ?? {};
    const ok = (result: unknown) => route.fulfill({ json: { result } });
    switch (method) {
      case 'initialize':
        if (params.lang) lang = params.lang;
        return ok({ ...api.initialize, lang });
      case 'map.build':
        return ok(api.map);
      case 'trail.current':
        return ok(null);
      case 'trail.build':
        return ok({ ...(lang === 'ko' ? api.trail_ko : api.trail), progress });
      case 'segment.guide':
        return ok({ guide: null, cached: false });
      case 'segment.code':
        return ok(api.code[params.order]);
      case '$/progress':
        return ok({ stage: 'parse', done: 10, total: 48 });
      case 'checkpoint.answer': {
        const id = params.checkpointId;
        const s = segOf(id);
        const n = (attempts[id] = (attempts[id] ?? 0) + 1);
        const want = api.answers[id];
        const right = Array.isArray(want) ? want.some(([a, b]: number[]) => params.answer >= a && params.answer <= b) : params.answer === want;
        const result = right ? 'correct' : n === 1 ? 'hint' : 'revealed';
        const slot = id.split(':')[2];
        progress.segments[key(s)].checkpoints[slot] = { attempts: n, state: result === 'correct' ? 'passed' : result };
        if (result !== 'hint') progress.segments[key(s)].status = result === 'correct' ? 'passed' : 'weak';
        refresh();
        if (result === 'hint') return ok({ result, hint: api.hints[id], progress });
        return ok({ result, explanation: api.explanations[id], answer: want, evidenceLines: [1, 1], file: s.file, progress });
      }
      case 'checkpoint.skip': {
        const s = segOf(params.checkpointId);
        progress.segments[key(s)].status = 'skipped';
        refresh();
        return ok(progress);
      }
      default:
        return route.fulfill({ status: 404, json: { error: { code: -32601, message: method } } });
    }
  });
  return api;
}

export const HIGH_CONTRAST = `
  body { --vscode-foreground:#ffffff; --vscode-editor-background:#000000; --vscode-sideBar-background:#000000;
    --vscode-editorWidget-background:#0c141f; --vscode-panel-border:#6fc3df; --vscode-contrastBorder:#6fc3df;
    --vscode-input-border:#6fc3df; --vscode-descriptionForeground:#ffffffcc; --vscode-charts-green:#89d185;
    --vscode-charts-yellow:#ffd700; --vscode-errorForeground:#f48771; --vscode-focusBorder:#f38518;
    --vscode-font-family:-apple-system, "Segoe UI", sans-serif; --vscode-editor-font-family:"JetBrains Mono", monospace; }`;
