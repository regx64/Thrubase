# Gate 3 · VS Code extension

Right after an AI agent edits code, click the status bar suggestion and finish a diff
climb without leaving the editor. Install the `.vsix` directly and use it in real work for
a week.

## Checklist

- [ ] `.vsix` from CI installed with `code --install-extension thrubase-0.1.0.vsix`
- [ ] An agent edited ≥ 5 functions; the status bar showed `Climb N changes`
- [ ] Clicking it opened the panel and the diff climb reached the summit inside VS Code
- [ ] Locate questions answered by clicking a line in the editor
- [ ] The panel came back in place after restarting VS Code
- [ ] Light, dark and high-contrast themes look right
- [ ] Korean VS Code shows Korean command names and UI
- [ ] One week of real use; problems listed below

## Notes from the week

| Day | Repository | What happened |
| --- | --- | --- |
| | | |

## Recorded results

| Date | Who | Result |
| --- | --- | --- |
| 2026-10-29 | implementer (automated, not the gate sign-off) | `@vscode/test-electron` on Linux (VS Code 1.144): activation, all commands registered, CLI found and JSON-RPC working, the next request succeeds after killing the process, ten triggers produce one `diff.count`, a full climb from the command runs through the Webview bridge and the editor highlights the segment, the key is passed only through the environment (no file under `THRUBASE_HOME` contains it). Korean run (VS Code 1.131 + Korean language pack): command titles and runtime strings are Korean. `.vsix` packages to 170 KB. **The week of real use, panel restore after restart and theme review need a person.** |
