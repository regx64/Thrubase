"""Records core responses for the visual and accessibility tests (run from the repo root):

    python packages/map-view/tests/visual/record.py

Uses the AI-generated validation service, so the screenshots show a realistic terrain map.
The answer keys are written too: the Playwright mock grades like core does.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "core" / "tests" / "validation"))

from build_ai_service import build  # noqa: E402

from thrubase.api import Session  # noqa: E402
from thrubase.store import Store  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "tasknest"
        build(repo)
        session = Session(repo, store=Store(Path(tmp) / "home"), lang="en")
        init = session.dispatch("initialize", {"lang": "en"})
        init["root"] = "/work/tasknest"
        m = session.dispatch("map.build", {})
        m["repo"]["root"] = "/work/tasknest"
        trail = session.dispatch("trail.build", {"kind": "full"})
        full = session._load_trail(trail["id"])
        answers = {c.id: c.answer for s in full.segments for c in s.checkpoints}
        explanations = {c.id: c.explanation for s in full.segments for c in s.checkpoints}
        hints = {c.id: c.hint for s in full.segments for c in s.checkpoints}
        code = {s["order"]: session.dispatch("segment.code", {"trailId": trail["id"], "order": s["order"]})
                for s in trail["segments"]}
        session.dispatch("initialize", {"lang": "ko"})
        trail_ko = session.dispatch("trail.current", {})["trail"]
    out = {"initialize": init, "map": m, "trail": trail, "trail_ko": trail_ko, "answers": answers,
           "explanations": explanations, "hints": hints, "code": code}
    target = Path(__file__).parent / "api.json"
    target.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {target} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
