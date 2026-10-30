# Performance measurements

## Analysis (core, C/W)

Synthetic repository from `core/tests/perfgen.py`: 2,000 files, 40,980 definitions,
50,657 edges. `pytest -m perf -s` (CI uploads `perf.json` from the `golden` job).

| Date | Machine | First run | Cached (new process) | Peak RSS |
| --- | --- | --- | --- | --- |
| 2026-10-29 | dev container, Linux x64, Python 3.13 | 9.3 s | 0.85 s | 339 MB |

Budget: first run 30 s, cached 2 s, under 1 GB.

What made it fit: a sampled spring layout above 400 files (repulsion against 192 random
nodes per iteration), body hashes from byte ranges instead of token walks, cached type
hints in JSON decoding, and lazily built parse files, index and graph when the Map comes
from the cache.

## Terrain map (map-view, M3)

`npx playwright test perf.spec.ts`: 2,000 nodes, 20 wheel zoom steps with the spring
animation, frame intervals from `requestAnimationFrame` (written to
`packages/map-view/test-results/terrain-perf.json`).

| Date | Machine | Frames | p50 | p95 |
| --- | --- | --- | --- | --- |
| 2026-10-29 | dev container, headless Chromium (software rendering) | 95 | 16.7 ms (59.9 fps) | 16.7 ms |
