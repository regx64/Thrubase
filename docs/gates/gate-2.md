# Gate 2 · Trails, diff, checkpoints, CLI

Climb the validation repositories to the summit using only the CLI, and complete a diff
climb over real changes in the AI-generated repository. While climbing, mark questions
that did not help understanding; if more than 30% are marked, revisit T5. Publish
0.1.0a1 to PyPI first to claim the name.

## Checklist

- [ ] `thrubase climb` to the summit on flask
- [ ] `thrubase climb` to the summit on requests
- [ ] `thrubase climb` to the summit on ai-service
- [ ] `thrubase climb --diff` on ai-service over its uncommitted changes (added- and removed-edge questions appear and are graded correctly)
- [ ] Questions marked "did not help": ____ of ____ (≤ 30%)
- [ ] `thrubase` 0.1.0a1 published to PyPI

## Question log

| Repository | Segment | Question | Helped? | Note |
| --- | --- | --- | --- | --- |
| | | | | |

## Recorded results

| Date | Who | Result |
| --- | --- | --- |
| 2026-10-29 | implementer (scripted, not the gate sign-off) | The real terminal climb (`tui.Climb`) reached the summit on flask (25 answers), requests (26) and ai-service (20), and the Korean diff climb on ai-service reached the summit (36 answers, 15 main segments). One answer in three was wrong on purpose to exercise hint → revealed. The diff climb asks "Which function now calls `TaskService._announce_completed`?" and "Which function no longer calls `normalize_name`?", and explains that `normalize_name` became an isolated zone. **Usefulness of questions still needs a person**; 0.1.0a1 is not published. |
