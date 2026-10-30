"""Helpers that write small Python repositories from call graphs (for trail and property tests)."""

from __future__ import annotations

from pathlib import Path


def write_graph_repo(root: Path, n: int, edges: list[tuple[int, int]], files: int = 1) -> dict[int, str]:
    """Functions ``f0``..``f{n-1}`` spread over ``files`` modules; ``f0`` is called from a
    ``__main__`` block. Calls are written in the order given. Returns index -> node id."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pkg").mkdir(exist_ok=True)
    (root / "pkg" / "__init__.py").write_text("")
    module_of = {i: i % files for i in range(n)}
    calls: dict[int, list[int]] = {i: [] for i in range(n)}
    for a, b in edges:
        calls[a].append(b)
    ids: dict[int, str] = {}
    for m in range(files):
        lines: list[str] = []
        imported = sorted({module_of[b] for i in range(n) if module_of[i] == m for b in calls[i]} - {m})
        for other in imported:
            lines.append(f"from . import m{other}")
        lines.append("")
        for i in range(n):
            if module_of[i] != m:
                continue
            ids[i] = f"pkg/m{m}.py::f{i}"
            lines.append("")
            lines.append(f"def f{i}():")
            body = []
            for b in calls[i]:
                target = f"f{b}" if module_of[b] == m else f"m{module_of[b]}.f{b}"
                body.append(f"    {target}()")
            body.append(f"    return {i}")
            lines.extend(body)
        if m == 0:
            lines += ["", "", 'if __name__ == "__main__":', "    f0()"]
        (root / "pkg" / f"m{m}.py").write_text("\n".join(lines) + "\n")
    return ids
