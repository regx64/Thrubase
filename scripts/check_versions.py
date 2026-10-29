"""Release check: the tag, core/pyproject.toml, vscode/package.json and thrubase.__version__
must all carry the same version.

    python scripts/check_versions.py v0.1.0
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def versions() -> dict[str, str]:
    pyproject = (ROOT / "core" / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "core" / "src" / "thrubase" / "__init__.py").read_text(encoding="utf-8")
    pkg = json.loads((ROOT / "vscode" / "package.json").read_text(encoding="utf-8"))
    py = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    dunder = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    return {
        "core/pyproject.toml": py.group(1) if py else "?",
        "thrubase.__version__": dunder.group(1) if dunder else "?",
        "vscode/package.json": str(pkg.get("version", "?")),
    }


def main(tag: str | None) -> int:
    found = versions()
    if tag is not None:
        found["tag"] = tag.removeprefix("refs/tags/").removeprefix("v")
    for where, v in found.items():
        print(f"{where:24} {v}")
    if len(set(found.values())) != 1:
        print("error: versions differ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
