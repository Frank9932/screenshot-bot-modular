# Handoff: device-agent-mvp CLI Chat MVP

**Agent:** claude-sonnet-5
**Scope of this doc:** everything done in this conversation building `device-agent-mvp/` — a standalone Python CLI chat MVP that uses an LLM to disambiguate a device from a real HVAC equipment catalog and produce a confirmed, mock-executed command. Not related to the rest of the `screenshot-bot-modular` repo's WeChat/browser work except that it reuses one data file from it.

Location: `device-agent-mvp/` at repo root, **untracked, uncommitted**.

---

## 1. What this conversation accomplished

- Implemented the full CLI Chat MVP per the user's original Chinese spec: multi-turn dialogue, device disambiguation, mid-conversation target changes, command preview, explicit y/N confirmation, mock execution, JSONL execution logging, `/reset`, `exit`.
- Swapped the spec's illustrative 3-device `devices.json` for the **real** equipment catalog: 676 HVAC devices loaded from `runtime/cdp-explore-out/hvac_equipment.csv` (categories: CDU, CRAH, DHU, EAF, FAHU, FWU, VRF), copied into `device-agent-mvp/data/hvac_equipment.csv`.
- Because 676 devices can't be sent to the LLM every turn, added a **local deterministic retrieval layer** (`devices.py: find_candidates`) that narrows the pool via normalized substring matching on `device_id` / category before it ever reaches the LLM. The LLM only ever sees a capped, enumerated subset (`MAX_CANDIDATES = 25`).
- Wired the OpenAI SDK's `chat.completions.parse()` with a Pydantic `response_format` (`AgentDecision`) for structured output.
- Implemented local (non-LLM) validation in `app.py:handle_ready` — any `device_id`/`action` the model returns that isn't actually in the loaded device list / `commands.json` / that device's `allowed_actions` is rejected with `[ERROR] Model returned an invalid device_id.` and never executed or logged.
- `MockExecutor.execute()` — `open` returns the device's **real BMS URL** from the CSV `url` column (not the spec's placeholder `mock-bms.local`); `status` returns a fixed mock state.
- JSONL logging to `logs/executions.jsonl` on every confirm *and* every cancel, schema matches spec (`timestamp, user_input, device_id, action, command, confirmed, result`).
- Installed `openai==2.46.0`, `pydantic==2.13.4`, `python-dotenv` into the machine's global/base Python (no venv exists for this subproject).
- Ran an offline test suite (mocked OpenAI client, no network) covering: device count (676), `find_candidates` exact/prefix/category matches, `MockExecutor` open/status, multi-turn agent flow (ambiguous → clarify → ready, not_found, unsupported_action), local rejection of a hallucinated `device_id`, and `handle_ready`'s confirm/cancel/logging behavior.
- User asked to make it "manual test ready" with a **real OpenRouter key** already placed in `device-agent-mvp/.env`. In response, found and fixed two real bugs (see §2) and confirmed one live structured-output call through OpenRouter succeeded.
- User then hit a **third, still-open bug** while testing manually (see §5) — conversation was stopped here to produce this handoff instead of continuing to fix it live.

## 2. What's actually in the code (verified on disk)

```
device-agent-mvp/
├── app.py            CLI loop, handle_ready() (validate/preview/confirm/execute/log),
│                      load_commands(), log_execution(), UTF-8 console fix, missing-key guard
├── agent.py           DeviceAgent, SYSTEM_PROMPT (Chinese), make_client() with
│                      OpenRouter auto-detection, _candidate_pool(), process()
├── devices.py         load_devices() CSV loader, _normalize(), find_candidates(),
│                      parse_index_reference() (new, UNVERIFIED — see §5), MAX_CANDIDATES=25
├── executor.py        MockExecutor.execute() for open/status
├── models.py           Device, AgentDecision (Pydantic)
├── commands.json       open/status → device-cli templates
├── requirements.txt     openai, pydantic, python-dotenv
├── data/hvac_equipment.csv   676-row copy of the real equipment catalog
├── logs/                empty (test-run residue was deleted before handoff)
└── .env                 contains a live OpenRouter API key (sk-or-v1... prefix) in plaintext
```

Two real bugs found and fixed while enabling live testing:

1. **Env-load ordering crash.** `agent.py` read `OPENAI_API_KEY` / decided OpenRouter routing at *module import time*, before `app.py`'s `load_dotenv()` (called inside `main()`) had run — first real run crashed with `openai.OpenAIError: Missing credentials`. Fixed by calling `load_dotenv()` directly at the top of `agent.py`.
2. **Windows console encoding crash.** Default stdout/stdin on this machine's Python is `cp1252`; printing/reading Chinese text crashed with `UnicodeEncodeError`. Fixed with `sys.stdout.reconfigure(encoding="utf-8")` / `sys.stdin.reconfigure(encoding="utf-8")` guarded by `sys.platform == "win32"` near the top of `app.py`.

Also added: **OpenRouter auto-detection** in `agent.py` — if `OPENAI_API_KEY` starts with `sk-or-`, `base_url` defaults to `https://openrouter.ai/api/v1` and `DEVICE_AGENT_MODEL` defaults to `openai/gpt-4o-mini` (OpenRouter requires provider-prefixed model names). Confirmed live with one successful structured-output call.

## 3. What was only discussed, not built

- No web frontend — explicitly out of scope per the user's original instruction ("不做网页").
- No real BMS integration — mock execution only, by design (spec says swap `MockExecutor` later).
- No Chinese alias table for the real 676-device catalog. The spec's own illustrative example used curated aliases ("二号冷冻水泵" → `CHWP-02`); the real CSV has no such aliases, so natural-language references only work via literal ID fragments or category keywords (e.g. `CDU-DH01`, `CRAH`). Flagged as a known limitation, not implemented.
- A live reproduction of the `"10"` index-reply bug (`process('打开EAF设备')` then `process('10')`) was proposed but the tool call was **interrupted/rejected by the user** before it ran. So the fix described in §5 is written but not exercised at all yet.

## 4. Decisions that were reversed or superseded

- **Provider**: spec assumed direct OpenAI (`OPENAI_API_KEY` against api.openai.com). Superseded once the user supplied a real OpenRouter key — `agent.py` now conditionally targets OpenRouter while still using the OpenAI SDK (OpenRouter is OpenAI-compatible).
- **Candidate-pool merge logic**: the original `_candidate_pool()` always ran a fresh full-catalog `find_candidates()` and merged it *ahead of* `active_candidates`. This was identified as the root cause of a real bug (see §5) and was changed to short-circuit and reuse `active_candidates` verbatim when the user's reply is a bare index/ordinal reference. This change is on disk but **unverified**.
- **False lead, ruled out**: at one point suspected the LLM had hallucinated a nonexistent device (`EAF-BATT-DH03-B-01-RYG1A-F1`). Verified via `grep` that this device **is real** (CSV line 310). The actual cause of the wrong resolution was the retrieval bug in §5, not model hallucination — don't re-chase this lead.

## 5. Risks / open items (most important first)

1. **UNVERIFIED FIX — do this first.** User reported: in a multi-turn session, an ambiguous query returned a candidate list where `EAF-BATT-DH03-B-01-RYG1A-F1` was shown as item **#10**. User replied `10` intending "item 10 from that list." The agent instead resolved to `CDU-DH01-10-RYG1A-F1` — a different device from a different category. Root cause: `find_candidates("10", devices)` did a catalog-wide substring match, and `"10"` is a substring of hundreds of device IDs, so the fresh match flooded out and reordered the previous (correct) candidate list before the LLM ever saw it.

   Fix applied (not yet tested, live or offline):
   - `devices.py` adds `parse_index_reference(text) -> int | None`, matching bare patterns like `"10"`, `"03"`, `"第10个"`, `"10号"`.
   - `agent.py:_candidate_pool()` now checks this first: if `self.active_candidates` is non-empty and the message parses as an index reference, it returns `self.active_candidates` **unchanged** (same list, same order) instead of running a fresh catalog search.

   **Next agent must verify this** — recommended: an offline test (no API cost) asserting `agent._candidate_pool("10")` returns the prior `active_candidates` list unmodified when one exists, plus one live re-run of the user's exact scenario (ambiguous EAF query → `"10"` → must resolve to the actual item at position 10, not a CDU device).

2. The index-reference regex only covers **digit-based** ordinals (`10`, `第10个`, `10号`). It does **not** cover Chinese-numeral ordinals like `"二号"` / `"第二个"` (no digits). A bare reply like `"二"` alone would still fall through to the normal fresh-search path and could in theory hit a similar (if rarer) pollution issue. Not analyzed or fixed.

3. No full live run of the original spec's 10 acceptance scenarios has happened since the OpenRouter/UTF-8 fixes landed — only one ad hoc single-turn live call succeeded before the user took over manual testing and hit the bug in item 1.

4. `MAX_CANDIDATES = 25`: broad category-only queries (e.g. bare `"CRAH"` matched 151 devices in offline testing) only show the first 25 in file order, with a text note that more exist. No pagination or smarter ranking beyond that — could still strand a user if their device is beyond position 25 and they don't type a more specific follow-up.

5. `device-agent-mvp/.env` holds a **live OpenRouter key in plaintext**. Whether it's excluded from git (via a `.gitignore` entry covering this new subfolder) has **not been checked** in this conversation — verify before any `git add`/commit anywhere near this directory.

6. No virtualenv for `device-agent-mvp`; dependencies were pip-installed into whatever global Python `python`/`pip` resolve to on this machine. Could collide with the root `screenshot-bot-modular/requirements.txt` pins if that project's own dependencies are later touched.

7. `device-agent-mvp/` is a new, fully untracked directory inside the `screenshot-bot-modular` git repo. Nothing here has been `git add`ed or committed.

## 6. What the next agent must know

- **Run it**: `cd device-agent-mvp && python app.py` (`.env` already has a working `OPENAI_API_KEY` set to an OpenRouter key). The dotenv-ordering fix and the UTF-8 console fix are already applied — don't redo them, don't re-diagnose those specific crashes if they reappear elsewhere; check for regressions instead.
- **Immediate next step**: verify the §5.1 fix (`parse_index_reference` / `_candidate_pool`) before doing anything else. This is the reason the conversation was paused.
- **Invariant to protect going forward**: any future change to `_candidate_pool()` must preserve — *a bare numeric/ordinal reply, when a previous candidate list exists, must never trigger a fresh full-catalog substring search that can reorder or evict that list.*
- The user may still be mid-session in an interactive `python app.py` run — confirm current state with them rather than assuming a clean slate.
- If scope expands toward natural-language device references (like the spec's demo "二号冷冻水泵"), that requires either a curated alias file for the real 676-device catalog or extending `parse_index_reference`-style handling to Chinese numerals — neither exists yet.
