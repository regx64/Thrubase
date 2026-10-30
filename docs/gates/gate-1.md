# Gate 1 · Core terrain map

A person looks at the entry points and the top 10 by altitude on the three validation
repositories and agrees with them. If not, tune the C8 weights, record the new values and
the reason in `core/tests/golden/`, then move on.

Values under review: [`core/tests/golden/flask.json`](../../core/tests/golden/flask.json),
[`requests.json`](../../core/tests/golden/requests.json),
[`ai-service.json`](../../core/tests/golden/ai-service.json) (`entries`, `top10`).

## Checklist

- [ ] flask: entry points and top 10 agreed
- [ ] requests: entry points and top 10 agreed
- [ ] ai-service: entry points and top 10 agreed
- [ ] Tuning (if any) recorded in [`core/tests/golden/README.md`](../../core/tests/golden/README.md)

## Recorded results

| Date | Who | Result |
| --- | --- | --- |
| 2026-10-29 | implementer (pre-review, not the gate sign-off) | Entry points found in all three repositories (flask: CLI script, `__main__`, click commands; requests: `__main__` blocks plus the exported API as library roots; ai-service: every FastAPI route and typer command). requests top 10 is the request pipeline. flask top 10 mixes the WSGI path with Jinja loader and blueprint plumbing; reverse PageRank was blended in (tuning log) to lift `wsgi_app`/`full_dispatch_request`. Resolution rates: flask 74%, requests 88%, ai-service 95%. **Needs a person's agreement.** |

Automated checks behind this gate: `pytest` (C1–C11), `pytest -m golden`, `pytest -m perf`
(2,000 files: first run 9 s, cached 0.9 s, 340 MB peak).
