"""Build the AI-generated validation repository (tasknest) with its commit history.

``validation/ai_service/NN-name/`` holds the files a coding agent wrote or changed in each
step, with the commit message in ``NN-name.MESSAGE`` and removed paths in ``NN-name.DELETED``.
Steps are committed in order; the ``99-uncommitted`` step is applied but not committed, so
the working tree carries real uncommitted agent changes for diff climbs.

    python tests/validation/build_ai_service.py /path/to/ai-service
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent / "ai_service"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "coding-agent", "GIT_AUTHOR_EMAIL": "agent@example.com",
    "GIT_COMMITTER_NAME": "coding-agent", "GIT_COMMITTER_EMAIL": "agent@example.com",
}


def git(root: Path, *args: str, date: str | None = None) -> None:
    env = dict(ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


def overlay(step: Path, root: Path) -> None:
    for src in sorted(step.rglob("*")):
        if src.is_file():
            dst = root / src.relative_to(step)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    deleted = step.with_suffix(".DELETED")
    if deleted.is_file():
        for rel in deleted.read_text().split():
            (root / rel).unlink(missing_ok=True)


def build(root: Path, *, uncommitted: bool = True, upto: str | None = None) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    steps = sorted(p for p in HERE.iterdir() if p.is_dir())
    for i, step in enumerate(steps):
        if step.name.startswith("99-"):
            if uncommitted:
                overlay(step, root)
            continue
        overlay(step, root)
        message = step.with_suffix(".MESSAGE").read_text().strip()
        git(root, "add", "-A")
        git(root, "commit", "-qm", message, date=f"2026-10-0{i + 1}T10:00:00")
        if upto and step.name == upto:
            break


if __name__ == "__main__":
    build(Path(sys.argv[1]), uncommitted="--committed-only" not in sys.argv)
