# Thrubase for VS Code

Climb a codebase without leaving the editor. Thrubase draws a **terrain map** of a Python
repository (altitude = how central the code is) and walks you along a **trail** of 12–15
segments from the entry points to the summits. Each segment ends with a short
**checkpoint**: which function runs next, which line does something, what a change did.

* **Full climb** — read an unfamiliar repository in call order.
* **Diff climb** — right after an AI agent edits code, the status bar offers
  `Climb 7 changes`. One click walks you through the changed functions, their callers and
  callees, and asks about added and removed calls.
* **Checkpoints work without any key.** Add an LLM key (Anthropic or any
  OpenAI-compatible endpoint, including Ollama) to get a two-sentence guide per segment.

Thrubase never executes your code. Nothing leaves your machine unless you add a key.

## Requirements

The extension talks to the `thrubase` command line tool:

```bash
pipx install thrubase
```

It is found on `PATH`, in the pipx environment, or through `uvx thrubase`; set
`thrubase.cliPath` to point at it explicitly. The CLI and the extension share their minor
version.

## Commands

| Command | |
| --- | --- |
| Thrubase: Start a full climb | Trail from entry points to summits |
| Thrubase: Start a diff climb | Trail over the uncommitted changes (also the status bar item) |
| Thrubase: Start a diff climb since… | Pick a base revision |
| Thrubase: Build the terrain map | Analyze again |
| Thrubase: Set / Delete the LLM key | Stored in SecretStorage, never on disk |

The same climb continues in the browser with `thrubase serve`.

License: AGPL-3.0.
