# Workflow MVP Handoff

- Task: Workflow MVP -- message routing + equipment-selection module review (see
  `docs/TASK_STATUS.md`, new row added by this session)
- Owner: Workflow Agent
- Date: 2026-07-20
- Status at handoff: local review + fixes + unit tests complete; not committed, not merged, no
  live-environment verification

## Goal

Bring `workflow/message_router.py`, `workflow/equipment_catalog.py`,
`workflow/equipment_selection_tracker.py`, `workflow/equipment_prompts.py`, and
`workflow/user_team_tracker.py` to a state ready for independent integration: verify every
state transition in the select-equipment flow (Idle -> Choose Category -> Choose Equipment ->
Pending Confirm -> Confirmed -> Capture), check the required edge cases (no/one/many
candidates, illegal index, cancel, duplicate confirm, lost state, expired state), unify
return-value formats, and add a minimal workflow unit-test suite -- without touching
`browser/`, `screenshot_store/`, or `wechat/image_sender.py`.

## Environment note (read this before trusting any file path below)

This session started in an isolated git worktree
(`.claude/worktrees/workflow-mvp-message-equipment-009636`, branch
`claude/workflow-mvp-message-equipment-009636`, based on commit `cbcc8ce`). That worktree has
**none** of the five target files, and none of `docs/PROJECT_RULES.md` /
`PROJECT_SNAPSHOT.md` / `TASK_STATUS.md` -- they only exist as **uncommitted changes** in the
main working tree (`C:\Users\frank\screenshot-bot-modular`, branch
`feature/user-scoped-storage-and-channels`, tip `cbcc8ce` + prior untracked/modified files).
This matches exactly what `docs/agents/mvp-integration-handoff.md` (Integration Agent, same
date) already recorded about its own session. **All reading and editing for this task was done
in that main working tree**; no files in the isolated
`workflow-mvp-message-equipment-009636` worktree were touched. Any future session that starts
in yet another fresh worktree will hit the same mismatch and should search the main working
tree the same way.

## What Was Found (state-transition + edge-case audit)

Read, in order: `docs/PROJECT_RULES.md`, `docs/PROJECT_SNAPSHOT.md`, `docs/TASK_STATUS.md`,
`docs/KNOWLEDGE_RECONCILIATION.md`, then the five target files plus the relevant slice of
`workflow/wechat_image_reply.py` (the consumer of `route_message`'s decisions) and
`docs/agents/mvp-integration-handoff.md` (prior session's audit of the same code, useful for
cross-checking what had already been exercised).

The state machine lives across two files: `EquipmentSelectionTracker` (persists the stage:
`awaiting_category` -> `awaiting_equipment` -> `awaiting_confirm` -> `confirmed`, or absent/`{}`
for Idle) and `message_router.route_message` (a pure function that reads that stage plus the
message and decides what happens next -- see that file's own docstring for why it's
deliberately I/O-free).

Real gaps found (all in `message_router.py`'s equipment block, `equipment_selection_tracker.py`'s
`cancel()`, and one consumer line in `wechat_image_reply.py`) -- **fixed this session**:

1. **"取消" (cancel) only worked from `awaiting_confirm`.** A sender who started picking a
   category or equipment and changed their mind had no way to back out except restarting the
   whole flow via "设备" -- typing "取消" mid-pick silently did nothing (fell through to
   generic guidance, state unchanged). Same gap existed after `confirmed`: a sender who
   confirmed and then wanted to redo their pick had no cancel path either. **Fix**: cancel now
   works from any active stage (`awaiting_category`, `awaiting_equipment`, `awaiting_confirm`,
   `confirmed`) -- see `message_router.py`'s widened `stage in (...)` check.
2. **Non-numeric input during `awaiting_category`/`awaiting_equipment` fell through to
   unrelated "guidance" text instead of being treated as an invalid selection.** Only an
   out-of-range *digit* was caught; a sender who typed anything non-numeric mid-pick got a
   disconnected guidance reply about channels, with no reminder they were still supposed to
   pick a number from the list they were just shown, and their stage stayed stuck. **Fix**:
   both stages now catch-all to `equipment_invalid_selection` for anything that isn't a valid
   in-range digit (out-of-range digit or non-numeric text alike), re-prompting the same list.
3. **`EquipmentSelectionTracker.cancel()` wrote `{"stage": "none"}`**, a third representation of
   "nothing active" distinct from both the real never-started state (`{}`) and every genuine
   `awaiting_*`/`confirmed` stage -- even though no code anywhere branched on the literal string
   `"none"` (confirmed by grep across `src/`). **Fix**: `cancel()` now writes `{}`, so
   "cancelled" and "never started" are the exact same Idle representation, with a docstring
   explaining why on purpose.
4. **`equipment_selected`'s return dict omitted `category`** even though `equipment_capture`
   (the terminal decision) bundles the full selection (`category`/`equipment`/`path`) -- the
   one consumer (`wechat_image_reply.py`) had to reach back into its own already-fetched
   `equipment_stage` dict to recover it, and the module's own interactive REPL mirror had the
   same asymmetry. **Fix**: `equipment_selected` now carries `category` too, so every
   equipment-flow decision that names a selection is self-contained; updated the one consumer
   line and the REPL mirror to use it instead of re-deriving from `equipment_stage`.

Things checked and confirmed **already correct, no change needed**:

- No-candidates cases (empty category list, empty equipment list, unknown category name) never
  raise -- `load_categories`/`load_equipment` return `[]`, and any digit against an empty list
  falls cleanly into `equipment_invalid_selection`.
- Single-candidate and multiple-candidate selection both resolve to the correct 1-indexed item.
- A channel digit sent while an equipment confirm/pick is pending resolves as a channel
  join/switch, not an equipment index -- channel state (`UserTeamTracker`) and equipment state
  (`EquipmentSelectionTracker`) are intentionally orthogonal/parallel, not one state machine, so
  this is correct behavior, not a bug.
- "设备"/`EQUIPMENT_START_WORDS` correctly restarts the flow from any stage, including
  `awaiting_confirm` and `confirmed`, both before and after this session's changes.
- Higher-precedence checks (`帮助`/general help, the private-channel passcode, watermark
  commands) all still win over the equipment block regardless of stage -- verified explicitly
  with tests, since the equipment block sits after them in `route_message` and must never
  shadow them.
- A malformed/incomplete persisted stage (missing `"stage"` key, or a stage value this version
  doesn't recognize) degrades to Idle rather than raising or matching any `awaiting_*` branch --
  `equipment_stage.get("stage")` returns `None` for both, and `None` matches none of the
  `stage ==` checks.
- `UserTeamTracker`/`EquipmentSelectionTracker`'s JSON persistence already handles a missing or
  corrupted file gracefully (`_read()` catches `FileNotFoundError`/`ValueError` and returns
  `{}`), and writes are atomic (`tmp` + `os.replace`), so a reader never observes a
  partially-written file.

**Duplicate confirm** (re-sending "确认" while already `confirmed`): confirmed as a real gap in
the sense that there's no dedicated reply for it, but it does **not** crash or corrupt state --
it simply falls through to the generic guidance reply, since `stage == "awaiting_confirm"` no
longer matches once confirmed. Left as-is rather than adding a new `kind` (e.g.
`equipment_already_confirmed`) for it: that would need a new prompt string in
`equipment_prompts.py` and a new branch in `wechat_image_reply.py`, which is new UX surface, not
a bug fix -- flagged in "Next Step" below for a product decision rather than made unilaterally.

**Expired/stale state**: confirmed as a **real, deliberate gap, not fixed**. Neither
`EquipmentSelectionTracker` nor `route_message` has any notion of time -- a stage persisted
arbitrarily long ago is indistinguishable from one set a second ago, and `route_message` takes
no timestamp parameter at all. No requirement anywhere (README, `PROJECT_SNAPSHOT.md`, prior
handoffs) specifies a TTL, so adding one now would be scope creep, not a bug fix. Documented as
a known limitation (see "Known Risks") and pinned with an explicit regression-style test
(`NoExpiryDocumentationTests` in `tests/workflow/test_message_router.py`) so a future session
that *does* add expiry has a concrete test to update rather than discovering the gap cold.

## What Was Done This Session

1. **Audit** of all five target files plus the relevant slice of `wechat_image_reply.py` (read
   only, to confirm how `route_message`'s decisions are actually consumed).
2. **`src/screenshot_bot/workflow/message_router.py`** -- widened cancel to work from any
   active equipment stage; widened `awaiting_category`/`awaiting_equipment` handling to treat
   any non-valid-digit input (not just out-of-range digits) as an invalid selection; added
   `category` to `equipment_selected`'s return dict; updated the module's own "kind" catalogue
   doc-comment to match; updated the interactive REPL's state-mirroring to match (uses the new
   `category` field, cancels to `{}` instead of `{"stage": "none"}`).
3. **`src/screenshot_bot/workflow/equipment_selection_tracker.py`** -- `cancel()` now resets to
   `{}` (same as never-started) instead of `{"stage": "none"}`; docstring updated to explain the
   Idle-convergence on purpose.
4. **`src/screenshot_bot/workflow/wechat_image_reply.py`** -- one-line follow-through for the
   `equipment_selected` contract change: reads `category` from the action dict instead of
   re-deriving it from `equipment_stage`. This is the only edit outside the five target files;
   everything else there (capture/storage/send orchestration) was read but not touched.
5. **New test suite** under `tests/workflow/` (repo had zero automated tests before this --
   confirmed via `Glob`/`git status`, consistent with `PROJECT_SNAPSHOT.md`'s "Known Issues" #3
   and `TASK_STATUS.md` Task 5, which is a separate, broader, not-yet-started QA task this
   session did not attempt to fully satisfy):
   - `test_message_router.py` -- 40 tests covering every stage transition in the diagram above,
     every edge case in the brief (no/single/multiple candidates, illegal index including
     non-numeric input, cancel from every stage, duplicate confirm, lost/malformed state, the
     no-expiry limitation), plus precedence checks and sanity checks that channel/private/photo
     routing wasn't disturbed.
   - `test_equipment_selection_tracker.py` -- 12 tests covering persistence, per-user isolation,
     the cancel-converges-to-Idle fix, and corrupted-file handling.
   - `test_user_team_tracker.py` -- 11 tests covering the same persistence properties for the
     channel/private-unlock tracker.
   - `test_equipment_catalog.py` -- 7 tests covering CSV loading order, dedup, empty/missing
     category, and a missing file raising `OSError` (documented, not swallowed, per the
     module's own docstring).
   - Installed `pytest` locally (`pip install pytest`, not previously present) to actually run
     these -- `pyproject.toml` already declared `[tool.pytest.ini_options] pythonpath =
     ["src"]`, implying pytest was the intended runner; it just wasn't installed yet. Not added
     to any dependency file since none of `pyproject.toml`'s `dependencies` list a dev/test
     group and adding one is out of this task's scope.
6. **This handoff file** (new).
7. **`docs/TASK_STATUS.md`** -- one row added ("Workflow MVP", status `Review`), no other edits
   to that file.

No other files were modified. `browser/`, `screenshot_store/`, and `wechat/image_sender.py`
were **not touched at all** -- confirmed by `git status` before finishing.

## Testing / Validation

| Validation | Command | Result |
|---|---|---|
| New unit test suite | `PYTHONPATH="$PWD/src" python -m pytest tests/workflow -v` | **72 passed, 4 subtests passed**, 0 failed |
| Existing end-to-end MVP demo still works after these edits | `PYTHONPATH="$PWD/src" python scripts/demo_mvp.py` | Exit code 0, no traceback; transcript unchanged from the prior session's (same categories/items/edge-case replies) |
| Manual confirmation no other files touched | `git status --short` scoped to `src/screenshot_bot/{browser,screenshot_store,wechat}` | No changes |

`scripts/demo_mvp.py` (from the prior Integration Agent session) exercises the real
`WeChatImageReplyWorkflow.handle()` end-to-end with a fake WeChat message and a real CSV/
tracker/storage underneath -- rerunning it after these edits is the closest thing this repo has
to an integration smoke test for the equipment flow, and it still passes byte-for-byte on the
transcript for every scenario it covers (none of which happened to exercise the cancel-from-
mid-flow or non-numeric-input cases this session added, which is exactly why the new unit tests
exist).

Per `PROJECT_RULES.md` Rule 4 (bug fixes should add regression tests, and handoffs must record
what couldn't be tested): everything in "What Was Found" above that involved a behavior change
has a corresponding new unit test. The two things this session explicitly did **not** attempt
to verify:
- **Live WeChat round trip** -- no credentials, no authorization, out of scope for an unattended
  session (same standing limitation as every prior handoff in this repo).
- **Real Chrome/CDP capture of an actual equipment graphic** -- `browser/` was intentionally not
  touched or exercised beyond what `scripts/demo_mvp.py`'s `DemoBrowser` stand-in already covers
  (per `docs/agents/mvp-integration-handoff.md`, this remains `TASK_STATUS.md` Task 8's
  existing, still-open gap, unchanged by this session).

## Known Risks

- **P1 -- No state-expiry mechanism** (see "What Was Found" above): a sender who abandons the
  flow mid-pick and returns days later resumes exactly where they left off, for better or
  worse. Not fixed here since it's not an established requirement; flagged for a product
  decision.
- **P2 -- Duplicate confirm has no dedicated UX**: falls to generic guidance rather than a
  tailored "you already confirmed X, send 获取截图 to capture it" reply. Not a crash, just a
  missed opportunity; a new `kind` would be needed to fix properly (see "Next Step").
- **P2 -- This session's fixes are unverified against a live WeChat account**, same as
  everything else in the equipment flow (`TASK_STATUS.md` Task 8, already `Blocked` before this
  session, unchanged).
- **P3 -- `equipment_catalog.enabled` still defaults to `false`** in `config.example.json` (an
  existing, intentional default, not something this session changed) -- a fresh deployment from
  the template alone still won't expose any of this flow, fixed or not.

## Next Step

1. Get the project owner's decision on whether duplicate-confirm deserves its own reply text/
   `kind`, or whether falling to generic guidance is acceptable UX -- this session treated it as
   out of scope for a bug-fix pass rather than deciding unilaterally.
2. Get the project owner's decision on whether state expiry is actually wanted; if so, the
   natural implementation point is adding a timestamp to `EquipmentSelectionTracker`'s persisted
   entry and a TTL check in the caller (`wechat_image_reply.py`) before passing `equipment_stage`
   into `route_message` -- `route_message` itself should probably stay time-unaware to preserve
   its pure-function guarantee, per its own docstring.
3. This mirrors every prior handoff's standing note: **do not commit** any of this without the
   user explicitly asking (per the project's working agreement, referenced in
   `docs/PROJECT_SNAPSHOT.md` and `docs/DEBUG_HANDOFF.md`).
4. Once/if a real automated-test-baseline task (`TASK_STATUS.md` Task 5) picks up, this
   session's `tests/workflow/` directory is ready to be folded into whatever broader
   pytest/ruff/CI setup that task establishes -- nothing here was designed to be throwaway.
