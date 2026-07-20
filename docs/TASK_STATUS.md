# Task Status

- Version: 0.1
- Status: Active
- Owner: Project Coordinator
- Last Updated: 2026-07-20

本文件只记录任务进度，不定义项目事实。项目事实以 `docs/PROJECT_SNAPSHOT.md` 为准（见
`docs/PROJECT_RULES.md` Rule 3/Rule 5）。

允许的状态取值：`Not Started` / `In Progress` / `Blocked` / `Review` / `Merged` / `Completed`。

---

## Tasks

| ID | Task | Owner | Status | Verification | Next Step |
|---|---|---|---|---|---|
| 1 | Project Recovery | Recovery Agent | Completed | PROJECT_SNAPSHOT 已生成并完成核对 | None |
| 2 | Stabilization Audit | Recovery Agent | Completed | STABILIZATION_PLAN 已生成 | 执行测试基线和后续工程治理 |
| 3 | Knowledge Reconciliation | Knowledge Auditor | Completed | KNOWLEDGE_RECONCILIATION 已生成 | None |
| 4 | Project OS v0.1 | Project Coordinator | Completed | 本轮创建 PROJECT_RULES 和 TASK_STATUS | None |
| 5 | Minimal Test Baseline / Commit B | QA Agent | Not Started | 当前没有自动化测试 | 为 message_router、equipment catalog、screenshot_store 和 WeChat routing 建立最小 pytest 测试 |
| 6 | Ruff / Quality Tooling | QA Agent | Not Started | 尚未实施 | Test Baseline 完成后执行 |
| 7 | CI Quality Gate | QA Agent | Not Started | 当前没有 CI | 在测试与 Ruff 稳定后实施 |
| 8 | Equipment Menu Live Verification | Workflow Agent | Blocked | 代码已存在，但未完成真实微信端到端验证 | 在测试基线建立后安排真实环境验证 |
| 9 | Incoming WeChat Image Storage Verification | Workflow Agent | Blocked | 代码已存在，但未完成真实微信联调 | 安排真实媒体下载和存储验证 |
| 10 | Browser Session Recovery Verification | Browser Agent | Blocked | 锁和恢复逻辑存在，但缺少可重复自动化测试和最终 soak test 证据 | 建立可重复测试或受控 live 验证 |
| 11 | Non-elevated Manual Restart Verification | Operations Agent | Blocked | split-brain 修复未针对真正失败场景复测 | 在非生产目标机复现并验证 |
| 12 | Device Agent MVP | Device Agent | Blocked | parse_index_reference 修复存在，但未验证 | 使用离线设备目录补测试；暂不接入主产品 |
| 13 | API Key Rotation | Human Operator | Blocked | 仓库忽略规则已修复，但密钥轮换需要人工完成 | 手动轮换 OpenRouter/API 密钥并确认旧密钥失效 |
| 14 | Project-level MVP Integration | Integration Agent | Review | 已整合 WeChat、routing、equipment catalog、browser、screenshot storage 和 reply 流程；本轮对 Workflow/Browser/Storage-Reply 三个模块级 MVP（均已 Review）的全部接口衔接点做了独立复核，逐一核对了 `route_message` 的每个 kind、`capture()` 返回字段、`ScreenshotStore`/`WeChatImageSender` 的输入输出，均与消费方一致，**未发现新的集成缺陷**；重跑完整测试套件（110 项全部通过）与 `scripts/demo_mvp.py`（退出码0），并针对性重跑 storage/sender 失败场景的单元测试（20 项全部通过）；详见 `docs/MVP_DEMO.md`、`docs/agents/mvp-integration-handoff.md`（早期审计）、`docs/agents/project-mvp-integration-handoff.md`（本轮最终整合报告） | 等待人工 Review/Commit 决定；如需更高 Level 需真实微信凭据 + 真实 Chrome/网络可达 10.121.0.14 + 明确授权；另有三项产品层面决策待人工裁定（重复确认 UX、状态过期、微信发送重试策略），详见最终整合报告"Next Step" |
| 15 | Workflow MVP | Workflow Agent | Review | 复核 `message_router`/`equipment_catalog`/`equipment_selection_tracker`/`equipment_prompts`/`user_team_tracker` 全部状态转换与边界情况；修复三处真实缺口（取消仅在 awaiting_confirm 生效、非数字输入在选择阶段被误判为 guidance、`cancel()` 引入多余的 "none" 状态）并统一 `equipment_selected` 返回字段；新增 `tests/workflow/`（72 项用例，全部通过）；重跑 `scripts/demo_mvp.py` 确认无回归；详见 `docs/agents/workflow-mvp-handoff.md` | 等待人工 Review/Commit 决定；是否需要为"重复确认"和"状态过期"补充专门的产品行为需人工决定，详见 handoff "Next Step" |
| 16 | Browser MVP | Browser Agent | Review | 梳理并文档化 `BrowserScreenshotService.capture()` 的完整契约（输入/输出/成功与失败表示/超时/连接与登录行为）；修复一处真实缺口（`wechat_image_reply.py`'s `_run_capture` 异常分支此前只生成本地占位图片、从未通过 `send_image_file` 发给用户，导致捕获失败时 `ok=True` 但用户静默收不到任何回复，与 `MVP_DEMO.md` 描述不符）；新增 `tests/browser/`（18 项用例，全部通过，覆盖成功/CDP不可用/浏览器进程不可用/tab不可用/登录失效/导航超时/设备页不存在/截图失败/畸形路径等场景，均使用 fake 隔离真实 Chrome）；重跑完整测试套件（90 项全部通过）与 `scripts/demo_mvp.py`（退出码0，确认修复生效）；详见 `docs/agents/browser-mvp-handoff.md` | 等待人工 Review/Commit 决定；真实 Chrome/CDP/WebStation 端到端验证仍待 Task 8/10 的前置条件（真实凭据+网络可达10.121.0.14+明确授权） |
| 17 | Storage / Reply MVP | Storage / Reply Agent | Review | 梳理并文档化 `ScreenshotStore.save_screenshot()` 与 `WeChatImageSender.send_image_file()` 的完整契约（输入/输出/目录布局/用户频道隔离/失败表示）；修复三处真实缺口：(1) `ScreenshotStore` 同毫秒+相同 duration_ms 的重复保存会静默覆盖前一次结果，新增 `_dedupe_path` 计数后缀；(2) `WeChatImageSender._upload_and_send` 对 `upload["media_id"]` 直接取下标，若响应缺失该字段会抛出无法诊断的裸 `KeyError`，改为显式校验后抛出清晰 `RuntimeError`；(3) `wechat_image_reply.py`'s `_run_capture` 两处 `send_image_file` 调用此前均未加保护，发送失败会导致异常逃逸出 `.handle()`、丢失已采集的截图/存储阶段信息，新增 `_send_capture_reply` 辅助方法统一收敛为真实的 `ok=False`/`send_error` 结果且保留阶段字段。新增 `tests/storage/`（9 项）、`tests/wechat/`（8 项）、`tests/workflow/test_reply_failure_boundary.py`（3 项工作流边界测试）；重跑完整测试套件（110 项全部通过，较此前 90 项新增 20 项）与 `scripts/demo_mvp.py`（退出码0，确认无回归）；详见 `docs/agents/storage-reply-mvp-handoff.md` | 等待人工 Review/Commit 决定；真实微信 API 上传/发送验证仍待 Task 9 的前置条件（真实凭据+明确授权） |
| 18 | QA Acceptance | QA Acceptance Agent | Review | 对完整 MVP 链路（Router → Equipment Selection → Browser Capture → ScreenshotStore → WeChat Reply）做独立验收，不采信此前任何 Agent 的结论，逐行重读全部相关源码并重跑全部命令：`pytest tests -v`（110 passed, 7 subtests passed, 0 failed, 2.16s，与此前声称完全一致）、`python scripts/demo_mvp.py`（退出码0，六项场景逐行核对与 `MVP_DEMO.md` 描述一致）。逐条核实此前四份 handoff（workflow/browser/storage-reply/project-integration）所声称的全部修复，均与当前代码一致，未发现新的、破坏既有 MVP 行为的代码缺陷。发现两项此前未被标记的 Major 测试覆盖缺口（`watermark_commands.py`/`menu.py`/`watermark_settings.py`/`wechat/official_api.py`/`wechat/media_downloader.py` 零测试覆盖；私密频道口令流程 `unlock_private`/`join_private`/`private_photo` 零专门测试），以及一处已确认的文档不一致（`PROJECT_SNAPSHOT.md` Known Issue #2 与 `storage-reply-mvp-handoff.md` 均声称 `screenshot_store/README.md` 仍是过期的，但 `git diff` 证实该文件已经是最新版本，只是未被任何 handoff 记功）。按本任务范围（仅在导致 MVP 行为不正确时才修复）未做任何代码修改。详见 `docs/MVP_TEST_REPORT.md` | Level C（本地/mock 边界）验收通过（Go）；生产级（真实微信/Chrome/WebStation）验证仍属 Task 8/9/10 未决事项；建议将两项 Major 测试覆盖缺口纳入 Task 5（Minimal Test Baseline） |
| 19 | Live Validation | Live Validation Agent | Review | 在本机（`DESKTOP-CQ4DBDE`，非部署机 bot-1/2/3）针对真实 WeChat/Chrome-CDP/真实 WebStation（`10.121.0.14`）做端到端真实环境验证：真实登录、真实频道截图、真实设备选择流程截图（`RYG1 - CDU`/`CDU-DH01-01-RYG1A-F1`）、真实 ScreenshotStore 落盘与隔离、真实微信 access_token/上传/发送（真实用户菜单点击与文本消息触发，收到真实 `errcode:0` 确认发送成功）、真实公网隧道信令验证均通过。发现并修复一项真实 Major 缺口：全新/未截过图的浏览器 tab 首次截图必超时（Chrome 后台标签页渲染节流），已加 `--disable-backgrounding-occluded-windows` 等标志并加回归测试（`tests/browser/test_cdp_multi_tab_service.py`），现场验证有改善但未 100% 消除；另记录一次已自行诊断并恢复的操作事故（本 Agent 自己起的一次性诊断脚本与正在运行的 webhook 进程发生跨进程 Chrome tab 管理冲突，导致 4 个 tab 被意外关闭，已通过仅重启 webhook 进程恢复，未触及 Chrome 本身，恢复后 5 个频道全部 `errors: []`）。重跑 `pytest tests -v`（112 passed，较此前 110 新增 2 项，0 failed）与 `scripts/demo_mvp.py`（退出码0）。详见 `docs/LIVE_VALIDATION_REPORT.md` | 用户已在真实微信客户端确认收到图片，端到端真实链路（签名验证→路由→截图尝试→存储→上传/发送→客户端收图）全部确认；等待人工 Review/Commit 决定；首触发截图超时未 100% 解决，建议后续任务收尾；本会话遗留一个多余的 quick tunnel 进程待清理（被环境权限分类器阻止，本 Agent 无法自行停止） |

---

## Update Triggers

只在以下事件发生时更新状态：

- 任务正式开始
- 任务被阻塞
- 任务进入 Review
- 代码合并
- 任务确认完成或取消

不得用主观百分比描述进度。

**Completed 与 Merged 的区别：**

- **Merged**：代码已经合并，但可能仍等待真实环境验证、发布或知识更新。
- **Completed**：任务目标和必要验证均已完成，不再需要后续动作。
