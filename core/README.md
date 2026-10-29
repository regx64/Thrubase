# thrubase

Climb a codebase. Thrubase reads a Python repository without running it, draws a terrain
map of its functions by importance (altitude), and walks you along a trail of 12–15
segments from the entry points to the summits, with a short comprehension checkpoint at
the end of each segment. A diff climb does the same for uncommitted changes.

```bash
pipx install thrubase
thrubase map .            # terrain map summary
thrubase climb .          # full climb in the terminal
thrubase climb . --diff   # climb the uncommitted changes
thrubase serve .          # local web UI
```

Code is never executed. Nothing is sent anywhere unless you configure an LLM key for
optional reading guides.

See https://github.com/regx64/thrubase for the VS Code extension and documentation.
