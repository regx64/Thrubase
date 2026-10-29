"""Prepare the validation repositories in THRUBASE_VALIDATION_DIR (or the given folder).

* flask and requests: shallow clones pinned by commit SHA, so golden values never drift.
* ai-service: the AI-generated service with its commit history, rebuilt from this repository.

    python tests/validation/fetch.py ~/.cache/thrubase-validation
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def fetch(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    repos = json.loads((HERE / "repos.json").read_text())
    for name, spec in repos.items():
        dest = target / name
        if "sha" in spec:
            if (dest / ".git").is_dir():
                head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True,
                                      text=True).stdout.strip()
                if head == spec["sha"]:
                    print(f"{name}: cached at {head[:10]}")
                    continue
            dest.mkdir(parents=True, exist_ok=True)
            run("git", "init", "-q", cwd=dest)
            run("git", "fetch", "-q", "--depth", "1", spec["url"], spec["sha"], cwd=dest)
            run("git", "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD", cwd=dest)
            print(f"{name}: {spec['ref']} @ {spec['sha'][:10]}")
        else:
            run(sys.executable, str(HERE.parent / spec["build"]), str(dest))
            print(f"{name}: built")


if __name__ == "__main__":
    fetch(Path(sys.argv[1] if len(sys.argv) > 1 else os.environ["THRUBASE_VALIDATION_DIR"]))
