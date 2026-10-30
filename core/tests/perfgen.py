"""Synthetic repository for performance measurements: ``files`` modules in nested packages,
each with classes and functions that call into other modules."""

from __future__ import annotations

import random
from pathlib import Path


def write_synthetic(root: Path, files: int = 2000, seed: int = 1) -> None:
    rng = random.Random(seed)
    root.mkdir(parents=True, exist_ok=True)
    pkgs = max(1, files // 40)
    modules: list[tuple[str, str]] = []  # (dotted, path)
    for p in range(pkgs):
        d = root / "app" / f"pkg{p:03}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("")
    (root / "app" / "__init__.py").write_text("")
    count = pkgs + 1
    i = 0
    while count < files:
        p = i % pkgs
        modules.append((f"app.pkg{p:03}.mod{i:04}", f"app/pkg{p:03}/mod{i:04}.py"))
        i += 1
        count += 1
    for idx, (_dotted, path) in enumerate(modules):
        others = rng.sample(modules[: max(1, idx)], k=min(3, max(1, idx))) if idx else []
        lines = ["from __future__ import annotations", ""]
        for o, _ in others:
            lines.append(f"import {o} as m_{o.rsplit('.', 1)[1]}")
        lines.append("")
        for c in range(2):
            lines += [f"class Service{c}:", "    def __init__(self, value: int) -> None:",
                      "        self.value = value", ""]
            for m in range(3):
                lines += [f"    def step{m}(self, x: int) -> int:", f"        y = self.helper{m}(x)"]
                for o, _ in others[:2]:
                    lines.append(f"        y += m_{o.rsplit('.', 1)[1]}.func{m}(y)")
                lines += ["        if y > 100:", "            raise ValueError(y)", "        return y", ""]
                lines += [f"    def helper{m}(self, x: int) -> int:", f"        return x * {m + 1}", ""]
            lines.append("")
        for f in range(4):
            lines += [f"def func{f}(x: int) -> int:", f"    s = Service{f % 2}(x)",
                      f"    return s.step{f % 3}(x)", "", ""]
        if idx == 0:
            lines += ['if __name__ == "__main__":', "    func0(1)"]
        (root / path).write_text("\n".join(lines) + "\n")
