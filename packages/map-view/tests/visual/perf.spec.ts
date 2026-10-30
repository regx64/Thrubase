import { expect, test } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { mockApi } from './mock';

// M3: the terrain map stays smooth at 2,000 nodes. Frame times during a zoom and pan are
// recorded to test-results/terrain-perf.json.
test('terrain map frame time at 2,000 nodes', async ({ page }) => {
  const api = await mockApi(page);
  const nodes = Array.from({ length: 2000 }, (_, i) => {
    const a = i * 2.399963;
    const r = 0.45 * Math.sqrt(i / 2000);
    return {
      id: `m${i}.py::f${i}`, kind: 'function', name: `f${i}`, qualname: `f${i}`, file: `m${i}.py`, start_line: 1,
      end_line: 5, loc: 5, h: 1 - i / 2000, x: 0.5 + r * Math.cos(a), y: 0.5 + r * Math.sin(a),
      role: i < 6 ? 'summit' : i % 400 === 7 ? 'entry' : null, entry_kind: null,
    };
  });
  await page.route('**/api/map.build', (route) => route.fulfill({ json: { result: { ...api.map, nodes } } }));
  await page.goto('/?token=t');
  const canvas = page.locator('canvas');
  await canvas.waitFor();
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const frames = await page.evaluate(async () => {
    const times: number[] = [];
    let last = performance.now();
    let running = true;
    const tick = (now: number) => {
      times.push(now - last);
      last = now;
      if (running) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    const el = document.querySelector('canvas')!;
    const r = el.getBoundingClientRect();
    for (let i = 0; i < 20; i++) {
      el.dispatchEvent(new WheelEvent('wheel', { deltaY: i < 10 ? -120 : 120, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, bubbles: true, cancelable: true }));
      await new Promise((res) => setTimeout(res, 50));
    }
    await new Promise((res) => setTimeout(res, 600));
    running = false;
    return times.slice(2);
  });
  frames.sort((a, b) => a - b);
  const p50 = frames[Math.floor(frames.length * 0.5)];
  const p95 = frames[Math.floor(frames.length * 0.95)];
  const report = { nodes: 2000, frames: frames.length, p50_ms: +p50.toFixed(2), p95_ms: +p95.toFixed(2), fps_p50: +(1000 / p50).toFixed(1) };
  writeFileSync(fileURLToPath(new URL('../../test-results/terrain-perf.json', import.meta.url)), JSON.stringify(report, null, 2));
  console.log(report);
  expect(p50).toBeLessThan(1000 / 55);
});
