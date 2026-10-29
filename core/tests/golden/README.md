# Golden values

Human-reviewed expectations for the three validation repositories (gate 1 and gate 2).
`tests/test_golden.py` fails when the analysis drifts from these files. Regenerate on purpose
with `pytest tests/test_golden.py --update-golden` and review the diff in the PR.

The validation repositories are prepared with `python tests/validation/fetch.py <dir>` and
found through `THRUBASE_VALIDATION_DIR`:

| Name | Source | Pin |
| --- | --- | --- |
| flask | pallets/flask | tag 3.1.2, 2c1b30d0503cfb064f1cb252e6614a06915a362a |
| requests | psf/requests | tag v2.32.3, 0e322af87745eff34caffe4df68456ebc20d9068 |
| ai-service | built from `tests/validation/ai_service/` | 4 agent commits + uncommitted changes |

## Tuning log (C8)

| Date | Change | Reason |
| --- | --- | --- |
| 2026-10-29 | α 0.5 · β 0.3 · γ 0.2 kept; the PageRank term blends forward (25%) and reverse (75%) rank, mixed before normalizing | Forward-only PageRank made small shared helpers (`Flask.ensure_sync`, `RequestException`) the summits of every repository. Reverse rank lifts what drives the most code (`Session.request`, `Flask.wsgi_app`); mixing raw ranks keeps a helper with six callers above its callers in synthetic star graphs. |
