# Knowledge Reconciliation Report

生成于 2026-07-20，角色：Knowledge Auditor（非 Recovery Agent，非开发者）。目标：建立本项目
唯一可信知识基线，供以后任何新 Agent 优先阅读。

事实优先级：**Current Code > Git History > Project Snapshot > Agent Handoff > 聊天内容（不可
访问，未使用）**。本报告中每一条结论都标注了证据来源；没有直接证据支持的内容一律标记
`Unknown`，不猜测。

---

## Sources

实际参与本次核对的来源：

- `docs/PROJECT_SNAPSHOT.md`（本 Agent 上一阶段产出）
- `docs/STABILIZATION_PLAN.md`（本 Agent 上一阶段产出）
- `docs/agents/*.md`（8 份，来自不同/并行会话的交接文档）：
  `claude-sonnet-5-handoff.md`、`browser-session-recovery-handoff.md`、
  `wechat-bot-ops-handoff.md`、`bot-ps1-cli-help-handoff.md`、
  `cdp-webstation-login-integration-handoff.md`、
  `user-scoped-storage-and-tunnel-handoff.md`、
  `screenshot-store-incoming-images-handoff.md`、
  `tab-not-debuggable-fix-handoff.md`
- `docs/DEBUG_HANDOFF.md`（长期滚动的故障档案，性质上也是一份 handoff，本报告单独列出核对）
- 当前代码（`src/screenshot_bot/**`、`scripts/**`、`ansible/**`，工作区实际内容，非文档描述）
- Git 历史（`git log`、`git show abbcefb`、`git log --all --full-history`、`gh pr list`）

未使用、也不可访问：本次或此前对话的聊天记录本身。凡是某份 handoff 只援引"对话中如何如何"
而代码/Git 里找不到对应证据的，一律按 `Unknown` 处理，不采信。

---

## Overall Confidence

| 维度 | 置信度 | 依据 |
|---|---|---|
| Architecture（模块划分、依赖方向、workflow 是唯一编排层） | **95%** | 每个模块的 README 断言都逐条与当前源码核对过（`route_message` 签名、`capture()` 签名、`screenshot_store` key 格式等），全部吻合。5% 的不确定性来自尚未对每一行代码做逐字节 diff。 |
| Module boundaries / 公共接口 | **93%** | 关键公共方法签名（`BrowserScreenshotService.capture`、`message_router.route_message`、`WeChatImageReplyWorkflow.__init__`）均已用 `grep`/`Read` 直接核对，与模块 README 描述一致。 |
| Deployment（部署机制 vs. 主机当前实际状态） | **55%** | 部署**机制**（`ansible/deploy.yml`、`Bot.ps1`、`tunnel.yml` 的接线）置信度接近 95%——都是本地可读的代码/playbook。但 **bot-1/bot-2/bot-3 三台主机此刻的真实运行状态**完全无法从本地仓库验证（见"Missing Knowledge"），拉低了整体分数。 |
| Testing | **20%** | "当前没有任何自动化测试"这一事实本身置信度是 100%（`find`/`Glob` 直接证实）。分数低是因为：没有测试意味着几乎所有"某功能已验证"的说法，都只能靠各份 handoff 自称的手工/live 测试来支撑，而这些手工测试大多**不可重现、不可独立复核**（脚本在会话级 scratchpad，已确认丢失——见 `browser-session-recovery-handoff.md` §7）。 |
| Historical decisions / 事故根因 | **60%** | 多个"根因"结论是被后续会话**自我推翻或修正**过的（split-brain 至少有三轮不同的根因假设，见"Conflicts"），最新版本已在当前代码中体现，但连最新版本自己也承认"未针对真正失败场景复测"。 |
| 并发/锁正确性（`cdp_multi_tab_service.py` 的多套锁机制） | **50%** | 代码层面三个来源（Incident-1 的进程内锁、`_lock_for` 逐 tab 锁、`browser-session-recovery-handoff.md` 的自动重登录）**确认共存**且互相兼容（`navigate()`/`login()` 均已被 `_lock_for` 包裹，见下方"Conflicts"第 2 条），但没有任何自动化测试或最近的 live soak test 记录能证明这套组合在生产环境下真正稳定。 |
| Unknowns（整体画像中无法从仓库验证的比例） | **约 25–30%** | 主要集中在：三台主机的实时状态、equipment/menu 功能是否曾用真实微信账号验证、`device-agent-mvp` 的 bug 修复是否曾被验证、多轮 soak test 的最终日志内容。 |

---

## Handoff Verification

### `docs/agents/tab-not-debuggable-fix-handoff.md`
**负责范围**：CDP 多标签页集成 + 三次 "tab not debuggable" / 孤儿进程事故排查（2026-07-05～07）
**状态**：**Confirmed**
**证据**：
- 文档自称"全部改动已进入 `abbcefb`"。`git show abbcefb --stat` 确认提交存在，作者/日期/文件列表与文档描述一致。
- 当前 `scripts/Stop-WebhookBackground.ps1` 中确有 `throw`（第 50/73 行）而非 `Write-Warning`，与文档描述的"失败改为硬失败"一致。
- 当前 `scripts/Bot.ps1`、`scripts/Start-PublicTunnel.ps1`/`Stop-PublicTunnel.ps1`、`ansible/bot.yml` 等均存在。
**引用**：`git show abbcefb`；`scripts/Stop-WebhookBackground.ps1:50,73`

### `docs/agents/cdp-webstation-login-integration-handoff.md`
**负责范围**：CDP 多标签服务 + WebStation 登录/保活/刷新集成（早期会话，具体日期未知）
**状态**：**Partially Confirmed / 部分 Stale**
**证据**：
- 文档自报"写作时 `cdp_multi_tab_service.py` ~492 行、`profile_manager.py` ~158 行"——与**当前**实际行数（492 / 158，见 `wc -l`）完全一致，说明这两个文件此后再未被大幅改动（增量都是同一批后续会话叠加的，行数巧合吻合）。
- **Stale 项**：文档描述 `keep_alive()` 最终选择了 `GetServersInfo`（理由：`PeekObjects` 需要一个当时没有的有效路径）。**当前代码与此矛盾**——`cdp_multi_tab_service.py:268-301` 使用的是 `PeekObjects`，路径从 `window.location.hash` 读取，并且代码自带注释明确说"An earlier version of this sent a GetServersInfo ping instead (a guess...) — that guess returned a plain HTTP 200 forever, including for hours after the session had actually died"。即：该 handoff 描述的"最终方案"其实是**后来被发现是 bug 并已被替换掉的早期版本**。当前 `browser/README.md`（Recovery 阶段已核对）与代码一致，是可信版本。
- 文档中"文档更新了 `browser/README.md`"等表述无法进一步细分核实（README 历经多轮重写），按"文档存在且当前描述准确"计为 Confirmed。
**引用**：`src/screenshot_bot/browser/cdp_multi_tab_service.py:268-301`；`src/screenshot_bot/browser/README.md`"Session keep-alive"章节

### `docs/agents/browser-session-recovery-handoff.md`
**负责范围**：会话保活失败后的自动重新登录恢复机制
**状态**：**Confirmed**（含一条已被后续代码解决的自报风险）
**证据**：
- `cdp_multi_tab_service.py:338` 确有 `start_keep_alive(self, name, interval_seconds=60, on_failure=None, ...)`。
- `cdp_multi_tab_service.py:380` 确有 `def navigate(self, name, url, timeout_seconds=10)`。
- `cdp_multi_tab_service.py:330` 确有 `logged_out = "LOGGED_OUT" in body or on_login_page`（body 检查 + URL 检查双信号），与文档描述的"URL 检查是后加的加固"一致。
- `profile_manager.py:130-144` 确有 `_recover(error)` 闭包，调用 `log_line`（已 import）+ `navigate` + `login`，作为 `on_failure` 传入 `start_keep_alive`，与文档描述完全一致。
- **该文档自报的"最高优先级、未验证"风险**——"`navigate()` 和 `profile_manager._recover()` 里的 `login()` 调用是否被 `_lock_for()` 包裹"——**本次核对已确认两者均被包裹**（`cdp_multi_tab_service.py:215` 的 `login()`、`:389` 的 `navigate()` 均以 `with self._lock_for(name), DevToolsWebSocket(...)` 开头）。**这条风险目前应视为已解决**，但文档本身没有更新，仍标注"未验证"——下游读者如果只读这份文档会以为风险仍然存在。
**引用**：`cdp_multi_tab_service.py:215,330,338,380,389`；`profile_manager.py:130-144`

### `docs/agents/wechat-bot-ops-handoff.md`
**负责范围**：WeChat 点击菜单 + 设备选型引导流程功能开发；bot-3 三个真实 bug 的诊断与修复
**状态**：**Confirmed**（代码部分）/ **Unknown**（部署生效部分）
**证据**：
- `src/screenshot_bot/wechat/webhook_server.py:59-89` 确认签名校验失败会写 `log_line` + JSONL，与文档描述的"bug #3 修复"逐字匹配（连注释措辞都高度一致）。
- `scripts/Stop-WebhookBackground.ps1:53-73` 确认存在 `Get-NetTCPConnection` 端口兜底检查，与"bug #2 修复"一致。
- `cdp_multi_tab_service.py` 的 `_lock_for`/`_tab_locks`（第 88-107 行）覆盖全部六个 CDP 方法（`screenshot`/`login`/`keep_alive`/`navigate`/`refresh`/`navigate_equipment`），与"bug #1 修复"一致。
- `message_router.py`、`menu.py`、`wechat/menu_manager.py`、`workflow/equipment_catalog.py` 等文档提到的新文件全部存在于工作区（`git status` untracked），签名与文档描述一致（`route_message` 的 `equipment_*` 参数、`capture()` 的 `equipment_path` 参数均已核对）。
- **无法验证**："已 `ansible-playbook deploy.yml --tags app --limit win11-bot-03` 部署成功"、"bot-3 当前仍在跑修复前代码，等待用户重启"——这两条描述的是**远程主机的实时状态**，本地仓库无法验证，按 `Unknown` 处理，不代表怀疑其真实性。
**引用**：`webhook_server.py:59-89`；`Stop-WebhookBackground.ps1:53-73`；`cdp_multi_tab_service.py:88-107`；`workflow/message_router.py:53-64`

### `docs/agents/bot-ps1-cli-help-handoff.md`
**负责范围**：`scripts/Bot.ps1` CLI 入口易用性改造
**状态**：**Confirmed**
**证据**：
- 当前 `Bot.ps1` 未见 `Mandatory`/`ValidateSet`（`grep` 无匹配），与"改为普通字符串参数 + 默认值"一致。
- `$script:Commands`（第 60 行起）、`Show-Help`（第 69 行）均存在。
**引用**：`scripts/Bot.ps1:17,60,69,126-142`

### `docs/agents/user-scoped-storage-and-tunnel-handoff.md`
**负责范围**：本分支主体功能（存储路径重排、频道模型、私密频道口令、隧道管理重构）+ bot-1/2/3 运维排查纪要
**状态**：**Confirmed**（自身编写部分）/ **Partially Confirmed**（引用其他并行会话部分，已如实标注不确定性）
**证据**：
- `screenshot_service.py:123-131,154-156` 确认存储 key 为 `{user_id}/channel_{id}/{original,watermarked}`，与"存储路径顺序反转"描述一致，且是当前唯一有效版本。
- `target_config.py:20` 确认 `visible_targets` 属性存在；`user_team_tracker.py:51,54` 确认 `has_unlocked_private`/`unlock_private` 存在。
- `src/screenshot_bot/desktop/` 已确认从代码中整体删除（`git diff --stat master...HEAD` 显示全部为删除行），与"彻底移除 virtual_desktop"一致。
- 该文档自己已经非常谨慎地区分了"本对话亲自验证过的"与"来自并行会话、本对话未审查"的部分（第 2 节），这种自我标注本身经核对是准确的——`wechat-bot-ops-handoff.md` 描述的三个 bot-3 bug 修复确实分别对应 `webhook_server.py`/`Stop-WebhookBackground.ps1`/`cdp_multi_tab_service.py` 的改动,与其转述一致。
**引用**：`screenshot_service.py:123-131`；`target_config.py:20`；`git diff --stat master...HEAD`（`desktop/*` 全部删除）

### `docs/agents/screenshot-store-incoming-images-handoff.md`
**负责范围**：`screenshot_store` 模块 + 微信用户上传图片的存储
**状态**：**Partially Confirmed / 大部分 Stale（作者自认）**
**证据**：
- 文档自己非常明确地区分了"仍与我写的一致"（`screenshot_store/models.py`、`store.py`、`media_downloader.py`、`official_api.py` 里的 `download_media`）与"被外部并发改动重写"（`wechat_image_reply.py` 构造函数、`screenshot_service.py`）两类。
- 核对结果：前者（`ScreenshotStore`、`WeChatMediaDownloader`）确认仍是当前代码的公共接口,未被替换。
- 后者：`wechat_image_reply.py.__init__` 当前签名为 `(config_path, image_sender, browser, screenshot_dir, media_downloader, incoming_image_store, private_image_store=None)`——**确认已不含 `desktop`/`virtual_desktop` 参数**，与文档描述的"这两个参数消失了"完全一致；该文档留下的疑问"这是否是有意为之"，现已可以从 `git diff --stat master...HEAD`（`desktop/` 整体删除）和 `docs/PROJECT_SNAPSHOT.md`（记录为"PR #4 明确的产品决策"）确认——**是有意为之，不是意外**，该文档的这条 §5 风险可以标记为已解答。
- 文档自己写的两轮 smoke test 已确认作废（构造函数签名已变），与文档自我披露一致。
**引用**：`wechat_image_reply.py:42-51`；`docs/PROJECT_SNAPSHOT.md`"已移除"段落；`git diff --stat master...HEAD`

### `docs/agents/claude-sonnet-5-handoff.md`
**负责范围**：`device-agent-mvp/` 独立 CLI 原型（与主产品无关）
**状态**：**Partially Confirmed**
**证据**：
- 文档描述的 `parse_index_reference()` 函数、`_candidate_pool()` 优先检查该函数的逻辑，**确认存在于当前 `device-agent-mvp/devices.py`/`agent.py`**（Stabilization 阶段已直接读取源码核对）。
- **但该文档自己写明这个修复"未经测试，无论是 live 还是 offline"**，本报告没有找到任何后续验证记录（无对应的第二份 device-agent-mvp handoff、无测试文件、无日志）——修复的**存在**是 Confirmed，修复的**有效性**是 `Unknown`。
- `.env` 内含真实密钥的描述已在 `docs/STABILIZATION_PLAN.md` 中处理（`.gitignore` + `.env.example`），密钥轮换本身仍需人工执行，未变。
**引用**：`device-agent-mvp/devices.py`（`parse_index_reference`）、`device-agent-mvp/agent.py`（`_candidate_pool`）

### `docs/DEBUG_HANDOFF.md`（滚动故障档案，非 `docs/agents/` 目录下的一次性交接）
**负责范围**：跨多个会话持续追加的技术事故记录
**状态**：**Confirmed**（历史部分）/ **此前已发现并修复 Stale 问题**（07-17 章节相对工作区曾经过时，已在 Stabilization 阶段补写 07-20 章节修正）
**证据**：本报告与 `docs/PROJECT_SNAPSHOT.md`/`docs/STABILIZATION_PLAN.md` 阶段已核实并修正过一次；本次复核确认修正内容（equipment/menu/message_router 相关文件清单）与当前 `git status` 仍然一致，未发现新的漂移。
**引用**：`docs/DEBUG_HANDOFF.md`"Status as of 2026-07-20"章节

---

## Conflicts

### 冲突 1：`keep_alive()` 实际发送的命令
- **`cdp-webstation-login-integration-handoff.md` 描述**：最终选择 `GetServersInfo`（因为 `PeekObjects` 需要当时未知的路径）。
- **当前代码**：`PeekObjects`，路径从 `window.location.hash` 读取；代码注释明确说 `GetServersInfo` 是被淘汰的早期猜测，且**曾经是一个真实 bug**（会把已死会话误判为存活，长达数小时）。
- **建议**：以当前代码（`cdp_multi_tab_service.py:268-301`）和 `browser/README.md` 为事实。该文档这一段描述作废,应视为 Stale。**未找到任何一份 handoff 记录这次切换本身**——这是一个真实的文档空白（见"Missing Knowledge"）。

### 冲突 2：`navigate()`/`login()` 是否被逐 tab 锁保护
- **`browser-session-recovery-handoff.md` 描述**：这是"最高优先级、未验证"的风险,不确定。
- **当前代码**：两者均已确认被 `_lock_for(name)` 包裹（第 215、389 行）。
- **建议**：以当前代码为事实——**该风险已解决**，但因为没有任何一份 handoff 回头更新这条记录，任何只读该文档的后续读者会继续把它当作未解决的高优先级风险。本报告在此正式close这条风险。

### 冲突 3：截图/上传图片的存储 key 格式，三代演变
- **`tab-not-debuggable-fix-handoff.md`（最早，已提交 `abbcefb`）**：`{user_id}/tab_{N}`。
- **`screenshot-store-incoming-images-handoff.md`（中间）**：作者原始设计是纯 `{OpenID}`（一人一个平铺目录）。
- **`user-scoped-storage-and-tunnel-handoff.md` / 当前代码**：`{user_id}/channel_{team_id}/{original,watermarked}`。
- **建议**：以当前代码（已直接核对 `screenshot_service.py`）为准，这是三代演变中的最新且唯一生效版本,不是相互矛盾的说法,而是被文档记录下来的真实迭代过程。`screenshot_store/README.md` 已在 Recovery 阶段修正为与此一致。

### 冲突 4："split-brain" 根因,三轮不同解释
- **第一轮（`abbcefb`，已提交）**：计划任务 `/RL HIGHEST` 提权 vs. 用户手动非提权重启的权限不对等。已修复（去掉 `/RL HIGHEST`）。
- **第二轮（`user-scoped-storage-and-tunnel-handoff.md`）**：怀疑是"WinRM/Tailscale 传输层双重执行"——**该文档自己承认这只是未证实的猜测**。
- **第三轮（`wechat-bot-ops-handoff.md`，更可信）**：`Stop-WebhookBackground.ps1` 的 `CommandLine -match $null` 恒假的可见性盲区,导致"看起来停止成功、实际没停止"。已修复（端口兜底检查,当前代码已确认存在）。
- **建议**：以第三轮解释 + 其代码修复为当前最可信版本,第二轮的"WinRM 双重执行"猜测应视为已被更好的解释取代，不建议继续深挖（多份文档已达成一致意见）。**但注意：所有修复都只在 ansible/WinRM（提权）路径下验证过，没有一次是通过真正失败的触发场景（用户本机非提权手动重启）复测的**——这条本身在四份不同 handoff 里被反复提及,是一个仍然真实存在的验证缺口,不是文档冲突。

### 冲突 5（轻微）：Bot-1 是否"不可触碰"
- **`browser-session-recovery-handoff.md`/`tab-not-debuggable-fix-handoff.md` 时期**：bot-1 是主要测试/部署目标，可以正常操作。
- **`user-scoped-storage-and-tunnel-handoff.md`（07-17）及以后**：bot-1 变成"生产环境，用户手动管理，未经明确要求不要碰"。
- **建议**：这不是矛盾，是**项目状态随时间演变**（bot-1 从测试机变成生产机）。以最新状态（`docs/DEBUG_HANDOFF.md`"Status as of 2026-07-17/07-20"章节 + 本 Agent 自身 memory 记录）为准：**当前必须视 bot-1 为生产环境,未经明确要求不得触碰**。

---

## Missing Knowledge

以下内容本地仓库状态无法回答，且没有任何文档给出确定性证据，需要人工补充或者已经确认为不可恢复：

- **`keep_alive()` 从 `GetServersInfo` 切换到 `PeekObjects` 这次改动本身是哪次会话做的**——代码和 README 都记录了"为什么"，但没有一份 `docs/agents/*.md` 记录"是谁、什么时候"改的。这是本次核对发现的、目前唯一"代码有据可查、但完全没有对应 handoff"的真实功能变更。
- **三台主机（bot-1/2/3）此刻的真实运行状态**——是否已重启、是否已应用最新代码、equipment/menu 功能是否已在任何一台上用真实微信账号验证过。所有相关 handoff 都明确写"未验证"或"部署但未生效"。
- **四轮 WebStation 会话保活 soak test 中，第 4 轮（v4，port 9339）的最终结果**——`browser-session-recovery-handoff.md` §7 记录了测试脚本路径，但明确说日志"从未被读取"，且脚本本身位于会话级临时目录，**大概率已经不存在**。
- **soak test 1 的 47 分钟"卡死"究竟是真实会话过期，还是一次瞬时 CDP 错误触发了不必要的强制重登录**——`browser-session-recovery-handoff.md` §4 明确记录两个假设从未被证伪任一个。
- **`device-agent-mvp` 的 `parse_index_reference`/`_candidate_pool` 修复是否真的解决了原始 bug**——代码修复存在，但从未被 live 或 offline 复测（见"Handoff Verification"对应条目）。
- **PID 15872（`tab-not-debuggable-fix-handoff.md` 提到的交互式控制台）当时是否真的是非提权（Medium integrity）**——该文档自己说这只是"吻合所有现象的理论，从未直接验证"。
- **是否已有人工确认过 `device-agent-mvp/.env` 里 OpenRouter 密钥的当前有效性/额度**——`STABILIZATION_PLAN.md` 已记录，本次复核无新证据，仍是 Unknown。
- **`ansible/inventory.yml`/`group_vars/screenshot_bot_modular.yml` 里具体的 WinRM 凭据、隧道 token 的当前有效性**——本报告确认这两个文件本地存在、从未进入 Git 历史（`git log --all --full-history` 为空），但内容本身不应被读取/复述，有效性无法也不应由 Agent 验证。

---

## Project Truth

以下内容综合"Current Code > Git History"两级最高优先级来源，是本项目**当前唯一可信的事实基线**。
任何新 Agent 应该先读这一节，而不是从任意一份 `docs/agents/*.md` 或 `DEBUG_HANDOFF.md` 直接取信息。

### 当前架构
`scripts/` → `workflow/`（唯一编排层，内部再分为纯函数 `message_router.route_message` 决策层 +
`WeChatImageReplyWorkflow` 执行层）→ `browser/` + `wechat/` + `runtime/` + `screenshot_store/`。
`wechat/webhook_server.py` 只依赖注入的 `message_processor.handle(...)`，不做任何截图/业务判断。

### 当前模块关系
- `browser/`：一个共享 Chrome 进程（`CdpMultiTabService`），每个 `team_id` 映射到一个命名 tab；
  六个会触及 CDP 的方法（`screenshot`/`login`/`keep_alive`/`navigate`/`refresh`/
  `navigate_equipment`）全部被 per-tab `threading.Lock`（`_lock_for`）保护；`start_keep_alive`
  在检测到死会话（body 含 `LOGGED_OUT` 或 URL 落在 `login.html`）时通过 `on_failure` 回调触发
  `profile_manager._recover()` 自动重新登录。
- `screenshot_store/`：任意 key 路径的字节持久化；`browser/screenshot_service.py` 用
  `{user_id}/channel_{team_id}/{original,watermarked}`；`workflow/wechat_image_reply.py` 用
  `{user_id}/channel_{joined_channel_id or 'unassigned'}` 存微信用户上传的图片。这是当前**唯一**
  有效的存储路径格式（早期的 `{user_id}/tab_{N}`、纯 `{OpenID}` 均已作废）。
- `workflow/`：`message_router.route_message(msg_type, content, channel_id, private_unlocked,
  all_channel_ids, ignore_message_types, equipment_catalog_enabled=False, equipment_stage=None,
  equipment_categories=None, equipment_items=None)` 是当前签名，同时覆盖频道/私密频道/水印指令/
  设备选型四类决策。`equipment_catalog_enabled` 默认 `False`，未启用时整套设备选型代码路径完全不
  激活。
- `desktop/`（虚拟桌面截图能力）**已被整体删除**，不是"未来要删"，是已完成的既定产品决策。

### 当前部署方式
Ansible over WinRM，目标 `win11-bot-01/02/03`；入口 `ansible/deploy.yml`；日常操作走
`scripts/Bot.ps1` 或 `ansible/bot.yml` 包装；永久隧道（cloudflared Windows 服务）通过
`ansible/tasks/tunnel.yml`（已确认接入 `deploy.yml`，`tags: tunnel`）在 `bot_tunnel_token` 存在
时自动安装。**三台主机各自当前的实际运行状态是 Unknown**，不要假设任何一台"应该"是最新代码在跑。

### 当前配置
`config.example.json`（已提交模板）+ `config.json`（本地专用，已被 `.gitignore` 保护，Stabilization
阶段确认其内容 schema 落后于当前代码，仍含已删除的 `virtual_desktop` 字段，但不影响运行，因为
死字段不会被读取）。必需环境变量：`WECHAT_APPID`/`WECHAT_APPSECRET`/
`WECHAT_OFFICIAL_WEBHOOK_TOKEN`；可选 `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD`（仅当某
target `login.enabled: true`）。

### 当前未完成工作（严格区分"已实现但未验证" vs "讨论过未实现"）
**已实现但从未用真实微信/真实 Chrome 端到端验证过**（Unimplemented-verification，不是
Unimplemented-code）：
- 设备选型引导流程（`equipment_catalog.enabled` 在所有已知配置里都是 `false`）
- WeChat 点击菜单（`menu.py`/`menu_manager.py`）
- 微信用户上传图片存储链路（`_store_incoming_image`）的真实微信联调
- bot-3 上的三处 bug 修复（CDP 锁、stop 验证、签名日志）——已部署但运行进程未重启，未生效
- `device-agent-mvp` 的候选列表污染 bug 修复

**讨论过、明确未实现**（Unimplemented）：
- 跨进程互斥锁（防止两个独立 Python 进程同时管理同一个共享 Chrome 调试端口）——多份文档反复
  提到，从未实现，是 split-brain 结构性缺口的根本性解法，目前仍然没有。
- `device-agent-mvp` 的中文数字序数词解析（"二号"/"第二个"）与真实 676 设备目录的别名表。
- `refresh()` 增加"落回 login.html"检测作为纵深防御——早期讨论过，从未实现（实际修复走的是
  `keep_alive()` 那条路）。

**本次 Knowledge Reconciliation 新发现，需要人工决定**：
- `keep_alive()` 命令从 `GetServersInfo` 切换到 `PeekObjects` 缺少对应 handoff，建议以后任何
  重大功能变更即使不提交 git，也应该留一份对应的 `docs/agents/*.md`。

---

## Recommendations

**可以归档**（历史价值已被后续文档/代码完全吸收,不再需要作为"当前状态"来源）：
- `docs/agents/cdp-webstation-login-integration-handoff.md` — 除 `GetServersInfo`/`PeekObjects`
  那段（已被证明过时）外，其余内容已被 `browser-session-recovery-handoff.md` 和当前代码完全覆盖。
  建议保留但在文件顶部加一行"keep_alive 命令描述已过时，见 KNOWLEDGE_RECONCILIATION.md 冲突1"。
- `docs/agents/tab-not-debuggable-fix-handoff.md` — 已完整提交为 `abbcefb`，`git show` 本身就是
  比这份文档更权威的记录；文档的价值仅剩"决策过程的叙事"，可归档为历史参考。

**已过期，建议标注但不删除**（仍有部分内容有效，不能整份作废）：
- `docs/agents/screenshot-store-incoming-images-handoff.md` — 作者自己已经详尽标注了哪部分过期，
  建议保留，其"哪些接口仍然稳定可用"那部分（`ScreenshotStore`、`WeChatMediaDownloader`）仍有效。
- `docs/agents/user-scoped-storage-and-tunnel-handoff.md` — 主体内容 Confirmed，但引用其他并行
  会话的部分本质是转述，建议以本报告的"Handoff Verification"对应条目为准,不要单独引用转述部分。

**仍具长期价值，建议保留且优先阅读**：
- `docs/agents/browser-session-recovery-handoff.md` — 关于会话死亡两个竞争假设从未证伪、
  `_lock_for` 覆盖范围的详细记录，即使风险已解决，机制本身的设计推理仍有参考价值。
- `docs/agents/wechat-bot-ops-handoff.md` — 三个真实 bug 的根因分析质量高、证据链完整，是目前
  关于 bot-3 运维问题最可信的单一来源。
- `docs/DEBUG_HANDOFF.md` — 仍是项目的主故障档案，应继续维护，但**新 Agent 应先读本报告的
  "Project Truth"一节，再读它**，避免把某一时刻的排查记录误当作当前状态。
- 本报告（`docs/KNOWLEDGE_RECONCILIATION.md`）与 `docs/PROJECT_SNAPSHOT.md` —
  建议作为以后新 Agent 的**第一入口**，其余 `docs/agents/*.md` 降级为"背景/取证材料"。

---

## 限制声明（本轮遵守）

本次 Knowledge Reconciliation 未修改任何生产代码、未新增功能、未重构、未运行任何部署操作、
未修改任何测试（因为当前没有测试）。发现的新风险（`GetServersInfo`→`PeekObjects` 缺少对应
handoff）仅记录在本报告，未采取任何行动。

完成，暂停等待下一阶段（Test Baseline / commit B）指示。
