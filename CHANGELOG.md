# Changelog

## 0.1.0

First release: one Python repository can be climbed end to end in the terminal, in VS Code
and in the local web UI.

* Terrain map: tree-sitter parsing, name resolution (imports, `self`/`super()`, inheritance,
  annotations), six entry-point patterns, altitude, isolated zones, deterministic layout.
* Full climb (12–15 segments, detours) and diff climb (working tree or `--since REF`) with
  flow, locate and diff_edge checkpoints graded in core.
* Optional LLM guides (Anthropic, OpenAI-compatible), cached.
* `thrubase map | climb | serve | rpc | config`; JSON-RPC 2.0 over stdio and the same
  methods over HTTP on 127.0.0.1 with a per-run token.
* VS Code extension: trail view, terrain map, editor highlights, locate by clicking, status
  bar suggestion for diff climbs, key in SecretStorage.
* English and Korean.
