# Gate 4 · MVP done

Every item in the definition of done holds, and 0.1.0 is released.

| Definition of done | Evidence | Status |
| --- | --- | --- |
| `pipx install thrubase` then `thrubase map .` works on flask, requests and the AI-generated repository | CI `golden` job; wheel smoke test in CI `wheel` job | automated ✓, needs PyPI release |
| First analysis of 2,000 files ≤ 30 s, cached ≤ 2 s | `pytest -m perf` (9 s / 0.9 s / 340 MB on the dev container) | ✓ |
| An entry point is detected in all three; a person agrees with the top 10 | `core/tests/golden/*.json`, [gate 1](gate-1.md) | entries ✓, agreement pending |
| Full trail has 12–15 segments, each with a static checkpoint | golden test asserts 12–15 main segments and ≥ 1 checkpoint per segment; property test | ✓ |
| Diff climb over real uncommitted changes in the AI repo, with correct added/removed-edge questions | `test_diff.py`, golden ai-service, [gate 2](gate-2.md) | automated ✓, human climb pending |
| Works without an LLM key; with a key, guides from cache on the second run | `test_guide.py` | ✓ |
| VS Code status bar suggestion over the threshold; clicking starts a climb | `diffWatcher.ts`, extension tests, [gate 3](gate-3.md) | automated ✓, human check pending |
| A climb started in VS Code continues in `thrubase serve` (shared progress) | progress lives in `~/.thrubase/progress/` behind file locks; `test_progress.py` (second session sees the same state) | ✓ |
| UI switches between English and Korean | map-view tests, Playwright "Korean UI", VS Code Korean run, `thrubase --lang ko` | ✓ |
| CI passes on Windows 11, macOS and Ubuntu | `.github/workflows/ci.yml` | pending first CI run |
| PyPI `thrubase` 0.1.0 and Marketplace `regx64.thrubase` 0.1.0 published | `.github/workflows/release.yml` on tag `v0.1.0` | pending (needs the release prerequisites below) |

## Before the first release

- [ ] Publish `thrubase` 0.1.0a1 to PyPI to claim the name (end of phase 2)
- [ ] Create the Marketplace publisher `regx64` in Azure DevOps; store the PAT as the repository secret `VSCE_PAT`
- [ ] Create the Open VSX namespace `regx64`; store the token as `OVSX_PAT`
- [ ] Register `release.yml` of `regx64/thrubase` as a PyPI Trusted Publisher (environment `pypi`)
- [ ] Once the logo is final, prepare the Marketplace icon (128px PNG) and README screenshots
- [ ] Publish the AI-generated validation repository as `regx64/thrubase-fixture-ai` (built by `core/tests/validation/build_ai_service.py`)
- [x] README: install, VS Code extension link, and "Code is never executed / nothing is sent without a key"
- [ ] README: terminal-climb GIF
