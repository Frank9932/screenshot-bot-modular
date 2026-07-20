# Worktree Inventory

- Version: 0.1
- Generated: 2026-07-20
- Owner: Inventory Agent
- Scope: `C:\Users\frank\screenshot-bot-modular` only (main worktree). No files were deleted,
  stashed, reset, or committed to produce this report; no branch switch was performed.

本报告是 MVP 集成前的一次性工作区清点，只读操作，不改变任何 Git 状态。

---

## 1. 当前分支

```
feature/user-scoped-storage-and-channels
```

HEAD 提交：`cbcc8ce` — "Add per-user storage, hidden backup/passcode-gated channels, and
permanent tunnel support"（2026-07-15）。本报告涉及的全部文件都是该提交之上的**未提交**改动
（18 个 modified + 32 个 untracked，含 `device-agent-mvp/` 内 9 个文件）。

---

## 2. 分类说明

| 类别 | 含义 |
|---|---|
| A | 已完成的主项目模块（已在 `WeChatImageReplyWorkflow.handle()` 或部署链路中实际串联） |
| B | Project OS 和恢复/交接文档（治理性文档，不含运行代码） |
| C | MVP demo 新增内容（仅用于 `scripts/demo_mvp.py` 本地演示，不在生产调用路径上） |
| D | `device-agent-mvp/` 实验代码（独立原型，明确未接入主产品） |
| E | 本地配置、密钥、运行文件 |
| F | 无法判断的变化 |

无 F 类文件——本次清点中，凭 `docs/PROJECT_SNAPSHOT.md`、`docs/STABILIZATION_PLAN.md`、
`docs/KNOWLEDGE_RECONCILIATION.md`、`docs/agents/mvp-integration-handoff.md` 及代码内容，
每个变化都能归类。

---

## 3. Modified 文件（tracked, 18 个）

| 文件 | 类别 | 进 MVP？ | 敏感信息 |
|---|---|---|---|
| `.gitignore` | B（治理修复，见 STABILIZATION_PLAN P0） | 否，但应先于任何 commit 落地 | 否 — 只新增忽略规则（`/storage/`、`config.json`、`device-agent-mvp/.env`、`device-agent-mvp/logs/`） |
| `README.md` | A | 是 | 否 |
| `ansible/README.md` | A（tunnel 部署文档） | 是 | 否 — 内含 `bot_tunnel_token=eyJhIjoi...` 属截断占位示例，非真实 token |
| `ansible/deploy.yml` | A（接入 `tasks/tunnel.yml`） | 是 | 否 |
| `config.example.json` | A | 是 | 否 — 仅 schema 示例，无真实值 |
| `docs/DEBUG_HANDOFF.md` | B（长期滚动故障档案） | 否 | 否 |
| `scripts/Bot.ps1` | A | 是 | 否 |
| `scripts/Start-WebhookBackground.ps1` | A | 是 | 否 |
| `scripts/Stop-WebhookBackground.ps1` | A | 是 | 否 |
| `src/screenshot_bot/browser/README.md` | A | 是 | 否 |
| `src/screenshot_bot/browser/cdp_multi_tab_service.py` | A | 是 | 否 |
| `src/screenshot_bot/browser/profile_manager.py` | A | 是 | 否 |
| `src/screenshot_bot/browser/screenshot_service.py` | A | 是 | 否 |
| `src/screenshot_bot/screenshot_store/README.md` | A | 是 | 否 |
| `src/screenshot_bot/wechat/README.md` | A | 是 | 否 |
| `src/screenshot_bot/wechat/official_api.py` | A | 是 | 否 |
| `src/screenshot_bot/wechat/webhook_server.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/README.md` | A | 是 | 否 |
| `src/screenshot_bot/workflow/help_text.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/wechat_image_reply.py` | A（核心编排器，452 行改动，接入 equipment catalog 流程） | 是 | 否 |

---

## 4. Untracked 文件（32 个）

| 文件 | 类别 | 进 MVP？ | 敏感信息 |
|---|---|---|---|
| `ansible/tasks/tunnel.yml` | A（被 `deploy.yml` 引用） | 是 | 否 — 仅引用 `{{ bot_tunnel_token }}` 变量，无字面密钥 |
| `config.mvp_demo.json` | C | 否（demo-only 配置，指向 gitignored 的 `runtime/mvp-demo/`） | 否 |
| `device-agent-mvp/.env.example` | D | 否 | 否 — 占位模板（`OPENAI_API_KEY=paste-key-here`） |
| `device-agent-mvp/agent.py` | D | 否 | 否 |
| `device-agent-mvp/app.py` | D | 否 | 否 |
| `device-agent-mvp/commands.json` | D | 否 | 否 |
| `device-agent-mvp/data/hvac_equipment.csv` | D | 否 | 低 — 内含内部 IP `10.121.0.14` 及 BMS 图形路径，但该 IP 已在 `docs/PROJECT_SNAPSHOT.md` 等文档中公开记录，非新增泄露 |
| `device-agent-mvp/devices.py` | D | 否 | 否 |
| `device-agent-mvp/executor.py` | D | 否 | 否 |
| `device-agent-mvp/models.py` | D | 否 | 否 |
| `device-agent-mvp/requirements.txt` | D | 否 | 否 |
| `docs/KNOWLEDGE_RECONCILIATION.md` | B | 否 | 否 |
| `docs/MVP_DEMO.md` | C | 否（描述 demo，本身可随 C 类一起提交作为文档） | 否 |
| `docs/PROJECT_RULES.md` | B | 否 | 否 |
| `docs/PROJECT_SNAPSHOT.md` | B | 否 | 否 |
| `docs/STABILIZATION_PLAN.md` | B | 否 | **文档本身不含密钥，但记录了 P0-1 密钥泄露事件**（见第 5 节） |
| `docs/TASK_STATUS.md` | B | 否 | 否 |
| `docs/agents/bot-ps1-cli-help-handoff.md` | B | 否 | 否 |
| `docs/agents/browser-session-recovery-handoff.md` | B | 否 | 否 |
| `docs/agents/cdp-webstation-login-integration-handoff.md` | B | 否 | 否 |
| `docs/agents/claude-sonnet-5-handoff.md` | B | 否 | 否 |
| `docs/agents/mvp-integration-handoff.md` | B | 否 | 否 |
| `docs/agents/screenshot-store-incoming-images-handoff.md` | B | 否 | 否 |
| `docs/agents/tab-not-debuggable-fix-handoff.md` | B | 否 | 否 |
| `docs/agents/user-scoped-storage-and-tunnel-handoff.md` | B | 否 | 否 |
| `docs/agents/wechat-bot-ops-handoff.md` | B | 否 | 否 |
| `scripts/Watch-WebhookLog.ps1` | A（运维工具） | 是 | 否 |
| `scripts/crawl_graphics_tree.py` | A（生成 equipment catalog 所用的真实 CSV 数据） | 是 | 否 |
| `scripts/demo_mvp.py` | C | 否 | 否 |
| `scripts/run_wechat_menu_sync.py` | A（配合 `wechat/menu_manager.py`） | 是 | 否 |
| `scripts/screenshot_equipment_list.py` | A（同 `crawl_graphics_tree.py`，数据采集工具） | 是 | 否 |
| `src/screenshot_bot/browser/equipment_navigation.py` | A | 是 | 否 |
| `src/screenshot_bot/wechat/menu_manager.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/equipment_catalog.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/equipment_prompts.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/equipment_selection_tracker.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/menu.py` | A | 是 | 否 |
| `src/screenshot_bot/workflow/message_router.py` | A | 是 | 否 |

> 分类依据：`docs/agents/mvp-integration-handoff.md` 明确记录，equipment catalog / menu /
> message_router 等模块**已经**被 `WeChatImageReplyWorkflow.handle()` 实际调用（非新增胶水代码），
> 因此归为 A 而非 C；只有 `scripts/demo_mvp.py`、`config.mvp_demo.json`、`docs/MVP_DEMO.md` 是
> demo 专用、不在生产调用路径上，归为 C。`device-agent-mvp/` 全目录按
> `docs/TASK_STATUS.md` Task 12（"暂不接入主产品"）和 `.gitignore` 注释（"unrelated standalone
> prototype"）归为 D。

---

## 5. 重要发现：敏感信息（磁盘存在，但不在上述 git 列表中）

`device-agent-mvp/.env` **文件存在于磁盘**，但因本次 `.gitignore` 修改已被正确排除，
不出现在 `git status --short` / `git ls-files --others --exclude-standard` 的输出中。

- **内容**：真实的 `OPENAI_API_KEY`（前缀 `sk-or-...`，OpenRouter 格式），明文存储。
- **历史**：`git log --all --full-history -- device-agent-mvp/.env` 为空——从未被提交，未泄露到
  Git 历史。
- **当前状态**：已被 `.gitignore` 新规则覆盖，不会被 `git add -A` 等操作纳入。
- **未完成事项**：`docs/TASK_STATUS.md` Task 13 标记为 `Blocked`，需要人工在 OpenRouter/OpenAI
  控制台轮换该密钥——**本报告不代为执行，也不会触碰该文件**。
- 同目录下 `device-agent-mvp/logs/executions.jsonl` 和 `__pycache__/*.pyc` 同样存在于磁盘，
  同样已被新 `.gitignore` 规则（`device-agent-mvp/logs/`）或全局 Python 忽略规则覆盖。

**结论：当前 `git status` 所反映的 32 个 untracked 文件本身不含明文密钥；风险文件
`device-agent-mvp/.env` 已经被正确 gitignore，但密钥轮换仍是待办人工事项。**

---

## 6. 推荐 commit 分组

不建议一次性 `git add -A`。按类别拆分为 4-5 个逻辑提交：

1. **Commit A1 — 核心功能：equipment catalog / menu 集成**
   `src/screenshot_bot/workflow/wechat_image_reply.py`、
   `src/screenshot_bot/workflow/equipment_catalog.py`、
   `src/screenshot_bot/workflow/equipment_prompts.py`、
   `src/screenshot_bot/workflow/equipment_selection_tracker.py`、
   `src/screenshot_bot/workflow/menu.py`、
   `src/screenshot_bot/workflow/message_router.py`、
   `src/screenshot_bot/browser/equipment_navigation.py`、
   `src/screenshot_bot/wechat/menu_manager.py`、
   `src/screenshot_bot/workflow/help_text.py`、
   相关 README（`browser/README.md`、`workflow/README.md`、`wechat/README.md`、
   `screenshot_store/README.md`）
   + 支持数据采集脚本 `scripts/crawl_graphics_tree.py`、`scripts/screenshot_equipment_list.py`、
   `scripts/run_wechat_menu_sync.py`

2. **Commit A2 — 部署/运维：permanent tunnel + 运维脚本**
   `ansible/deploy.yml`、`ansible/tasks/tunnel.yml`、`ansible/README.md`、
   `scripts/Bot.ps1`、`scripts/Start-WebhookBackground.ps1`、
   `scripts/Stop-WebhookBackground.ps1`、`scripts/Watch-WebhookLog.ps1`、
   `src/screenshot_bot/browser/cdp_multi_tab_service.py`、
   `src/screenshot_bot/browser/profile_manager.py`、
   `src/screenshot_bot/browser/screenshot_service.py`、
   `src/screenshot_bot/wechat/official_api.py`、
   `src/screenshot_bot/wechat/webhook_server.py`、
   `config.example.json`、`README.md`

3. **Commit E — 安全治理（建议优先/单独提交，且先于任何 `git add -A`）**
   `.gitignore`（新增 `/storage/`、`config.json`、`device-agent-mvp/.env`、
   `device-agent-mvp/logs/` 规则）
   人工待办：轮换 `device-agent-mvp/.env` 中的 OpenRouter/OpenAI 密钥（不在本次 commit 范围内）

4. **Commit B — Project OS / 恢复文档**
   `docs/PROJECT_SNAPSHOT.md`、`docs/STABILIZATION_PLAN.md`、
   `docs/KNOWLEDGE_RECONCILIATION.md`、`docs/PROJECT_RULES.md`、`docs/TASK_STATUS.md`、
   `docs/DEBUG_HANDOFF.md`（modified）、`docs/agents/*.md`（9 个 handoff 文档）

5. **Commit C — MVP demo（可选，与 A1 分开，避免把 demo-only 代码混进生产路径 diff）**
   `scripts/demo_mvp.py`、`config.mvp_demo.json`、`docs/MVP_DEMO.md`

6. **不提交（D 类，明确排除）**
   `device-agent-mvp/`（全部内容）——按 `docs/TASK_STATUS.md` Task 12 和
   `docs/STABILIZATION_PLAN.md`，该目录是独立原型，且 `.env` 密钥轮换未完成前不应涉及任何
   会被提交的操作。

---

## 7. 未执行的操作（按指令要求）

本次清点未执行：`git add`、`git commit`、`git stash`、`git reset`、`git checkout`/分支切换、
文件删除。以上分组仅为建议，供人工确认后自行执行。
