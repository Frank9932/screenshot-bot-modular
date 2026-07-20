# 交接文档 — user-scoped-storage-and-tunnel

**Agent:** claude-sonnet-5
日期：2026-07-17
分支：`feature/user-scoped-storage-and-channels`
关联 PR：[#4](https://github.com/Frank9932/screenshot-bot-modular/pull/4)（`open`，未合并）

> ⚠️ **`docs/agents/` 目录下同时存在其他三份交接文档**（`bot-ps1-cli-help-handoff.md`、
> `browser-session-recovery-handoff.md`、`wechat-bot-ops-handoff.md`，以及一份**同名但完全无关**
> 的 `claude-sonnet-5-handoff.md`——那份实际是另一个会话做 `device-agent-mvp/` 独立 CLI 工具的
> 交接，与本仓库的 WeChat/浏览器主线无关，本文档特意改用更具体的文件名以避免覆盖它）。这些文档
> 看起来分别来自**并行/不同的会话**，各自处理了本仓库的不同部分，其中两份与本文档描述的工作**直
> 接相关、互相印证**，接手前建议全部读一遍，不要只读本文档。

本文档由本 Agent 在收到"停止开发，仅整理交接文档"指令后生成，不再包含任何新的代码修改或方案讨论。

---

## 1. 本对话完成了什么

按时间顺序：

1. **bot-2 回复变慢排查** — 给 WeChat API 调用（access_token / 素材上传 / 消息发送）分别打点计时，定位瓶颈在素材上传（`upload_ms` 12–15 秒）。根因确认为 bot-2（Hyper-V 虚拟机）虚拟网卡的 **LSO（Large Send Offload）** 问题。
2. **修复 LSO 引发的副作用** — 在 bot-1（宿主机）关闭 LSO 时引发链路闪断，导致 bot-2 到 BMS 设备（10.121.0.14，被动设备）的 ARP 状态损坏。通过重连虚拟网卡 + guest 内触发免费 ARP 广播解决。
3. **"tab not debuggable" / 进程分裂（split-brain）排查** — 在 bot-1、bot-3 上多次复现"两个 webhook 进程同时监听同一端口"的症状。
   - bot-1 上找到并移除了根因：一个遗留的 Windows 计划任务（旧启动脚本、不同 Python 解释器）。
   - bot-3 上**同样症状复现多次，本对话没有排查出根因**（计划任务/服务/启动项/WMI 订阅均排查为空）——**但见下方"第 5 节"，另一个并行会话（`wechat-bot-ops-handoff.md`）后来找到了更可信的解释，本对话当时的"WinRM 双重执行"猜测很可能不是真正原因。**
   - 无论根因是什么，额外做了防御性修复：`webhook_server.py` 里 `allow_reuse_address = False`，让端口冲突直接报错崩溃而不是静默共存——这是这类 bug 能反复"悄悄"发生的底层原因。
4. **新增 bot-3 主机** — 加入 ansible inventory，完整部署，配置**永久隧道**（cloudflared 作为 Windows 服务绑定具名 Cloudflare Tunnel），区别于 bot-1/bot-2 的一次性 quick tunnel。
5. **大范围功能重设计**（本分支主体）：
   - 存储路径顺序：`channel_{id}/{user_id}/...` → 最终改为 `{user_id}/channel_{id}/...`（用户 ID 最外层）。
   - 彻底移除 `virtual_desktop` / 桌面截图能力模块（从未真正启用，属死代码）。
   - 频道数量改为完全配置驱动；新增 3 个"备用频道"（6/7/8，功能完整但不出现在帮助文案里）。
   - 私密频道改为口令解锁（`11223344`）。
   - 用户首次加入任意频道时追加一条"图片按用户 ID 归档"的提示。
   - **将交互判断逻辑解耦为独立纯函数模块 `message_router.py`**（`route_message(...)`），不含 I/O，可脱离浏览器/WeChat API/配置文件单独调试（`python -m screenshot_bot.workflow.message_router` 提供 REPL）。**⚠️ 这个文件后来被另一个并行会话进一步扩展**，加入了设备选型引导流程的路由逻辑（见第 2 节）。
   - 隧道管理改进：永久隧道安装接入 `deploy.yml` 默认流程；`Bot.ps1 all kill`/`all restart` 不再触碰任何隧道；`Bot.ps1 status` 同时显示永久隧道与 quick tunnel 状态。
   - 新增专业级实时日志查看工具 `Watch-WebhookLog.ps1`，逐行着色解析 JSONL 事件日志，支持过滤；通过 `Bot.ps1 webhook watch` 以分离、非阻塞方式在新终端窗口启动。
6. **顺带修复的真实 bug**：
   - PowerShell `2>&1` 重定向原生程序 stderr 配合脚本级 `$ErrorActionPreference = "Stop"`，把 cloudflared 的正常 INFO 日志当成致命错误——修复 `tunnel permanent-install`。
   - `Get-Content` 缺少 `-Encoding UTF8` 读取本项目 UTF-8 日志导致中文乱码/`??`——修复 `Invoke-WebhookLogs` 与 `Watch-WebhookLog.ps1`，并额外发现需要 `[Console]::OutputEncoding = UTF8` 才能让终端**显示**正确（两个独立问题）。
7. **部署动作**：
   - bot-3：完整部署 + 首次配置永久隧道 + 多次代码同步（跳过 secrets，未动其独立 WeChat 凭据）。**webhook/Chrome 目前未在 bot-3 上运行**——用户多次远程启动失败后明确要求"我自己来启动"。**另见第 5 节：另一个并行会话在 bot-3 上还发现并修复了三个真实 bug（详见下方），同样部署未生效，等待用户重启。**
   - bot-1（生产环境）：会话前期"不要碰运行中的实例"，会话末尾用户明确改口"部署到 bot-1"，已执行**仅文件同步**，未重启。**bot-1 当前运行进程仍是旧代码。**
8. **文档更新**：`docs/DEBUG_HANDOFF.md` 顶部新增"当前会话状态"章节，保留下方 2026-07-05 的历史 incident 记录。

---

## 2. 哪些已经进入代码

**本对话直接编写并验证过：**
- `src/screenshot_bot/wechat/webhook_server.py` — `allow_reuse_address = False`
- `src/screenshot_bot/browser/screenshot_service.py` — 存储路径改为 `{user_id}/channel_{id}/...`
- `src/screenshot_bot/browser/target_config.py` — `visible_targets` 属性
- `src/screenshot_bot/workflow/user_team_tracker.py` — `unlock_private`/`has_unlocked_private`
- `src/screenshot_bot/workflow/help_text.py` — 动态频道列表文案、口令解锁文案
- `src/screenshot_bot/workflow/message_router.py`（新建）— 纯函数消息路由层（本对话创建的版本；后被另一会话扩展，见下）
- `src/screenshot_bot/workflow/wechat_image_reply.py` — 改为薄执行层；存储路径改动；移除 `virtual_desktop` 相关代码（后被另一会话进一步重构，见下）
- `src/screenshot_bot/wechat/image_sender.py` — `token_ms`/`upload_ms`/`send_ms` 分段计时
- `config.example.json` / `ansible/group_vars/screenshot_bot_modular.example.yml` / `ansible/group_vars/screenshot_bot_modular.yml`（后者未受 git 跟踪、本地真实文件）— 频道 1–8、移除 `virtual_desktop` 相关键
- `scripts/Bot.ps1` — `all kill`/`all restart`（移除隧道调用）、`tunnel permanent-install`、`webhook watch`、`status` 展示永久隧道状态
- `scripts/Watch-WebhookLog.ps1`（新建）
- `ansible/tasks/tunnel.yml`（新建）+ 接入 `ansible/deploy.yml`
- `ansible/tunnel-permanent-install.yml`（新建）
- `ansible/inventory.yml`（未受 git 跟踪）— 新增 bot-3 及其 `bot_tunnel_token`
- 已删除：`src/screenshot_bot/desktop/` 整个目录
- 各模块 `README.md`、根 `README.md`、`docs/ARCHITECTURE.md`、`docs/DEBUG_HANDOFF.md`

**⚠️ 由另一个并行会话完成、本对话未审查未测试，但已确认来源和范围（见 `wechat-bot-ops-handoff.md`）：**
- 新增 WeChat 自定义菜单（`menu.py`、`menu_manager.py`）+ 设备选型引导流程（`equipment_catalog.py`、`equipment_prompts.py`、`equipment_selection_tracker.py`、`equipment_navigation.py`）——**默认关闭**（`equipment_catalog.enabled: false`），通过 `equipment_catalog_enabled` 参数完全网关在 `message_router.py` 里，理论上不影响本对话设计的频道/私密频道逻辑，但**未经本对话验证**。
- 同一会话还在 `wechat_image_reply.py` 里把截图路径重构成了共享的 `_run_capture()` 辅助函数——即本对话写的 `_capture_and_reply` 可能已被改名/重构，接手前需要重新读一遍这个文件的当前状态。
- 该会话还在 bot-3 上发现并修复了三个独立的真实 bug（CDP 单 tab 缺锁导致 tab 永久卡死、`Stop-WebhookBackground.ps1` 的权限可见性盲区导致"看起来停止成功但进程还活着"、签名校验失败没有任何日志痕迹）——**详见第 5 节**。

**其余显示为已修改、本对话上下文中未见直接编辑记录的文件**（`profile_manager.py`、`official_api.py`、`Start-WebhookBackground.ps1`、`Stop-WebhookBackground.ps1`、`screenshot_store/README.md`、`.gitignore`）——`wechat-bot-ops-handoff.md` 的 bug #2 修复了 `Stop-WebhookBackground.ps1`，`browser-session-recovery-handoff.md` 大概率涉及 `profile_manager.py`（keep-alive/session 相关），可以解释这两个文件的改动来源；`official_api.py` 的改动很可能是 `wechat-bot-ops-handoff.md` 里新增的 `create_menu`/`get_menu`。总之——**这些改动分别来自其他交接文档描述的会话，不是本对话遗漏的记录**。

---

## 3. 哪些只是讨论，没有落地

- bot-3 split-brain 的"WinRM/Tailscale 双重执行"理论——本对话内从未证实，仅仅是猜测（见第 5 节，现在有更可信的替代解释）。
- 本地测试实例（端口 8792）配合现有隧道工具重定向测试——只完成了"尝试启动"，健康检查失败，根因从未诊断（调查被打断，转去处理文档交接）。

---

## 4. 哪些决策后来被推翻

1. **存储路径嵌套顺序**：`channel_{id}/{user_id}/...` → 用户明确要求反转为 `{user_id}/channel_{id}/...`。**当前代码是反转后的版本。**
2. **私密频道解锁提示文案**：最初包含"发送"私密"（或 private）即可进入"的提示，用户要求移除。**当前只剩一句确认，不再提示怎么进入。**
3. **`Bot.ps1 all kill`/`all restart` 是否管理隧道**：最初会顺带停止/启动 quick tunnel，用户明确要求"重启不应该再包含隧道"，已移除。**隧道现在完全独立于 bot 重启生命周期。**
4. **bot-3 webhook 启动方式**：尝试过把 `Bot.ps1 webhook start` 包一层 detached `Start-Process` 规避 split-brain——导致 webhook 在 WinRM 会话关闭后被杀掉，方法已放弃，退回直接调用方式。
5. **ansible inventory 分组名**：`win11-bot-03` 分组一度被改成 `windows_wechat_bot`，后经用户明确选择改回 `screenshot_bot_modular`。
6. **是否碰 bot-1**：会话前期"不要碰"，会话末尾用户主动改口"部署到 bot-1"——不是矛盾，是用户主动扩大授权范围，且只做了文件同步。

---

## 5. 哪些风险仍然存在

1. **bot-3 早期"split-brain"症状的真正根因，本对话没有确认，但另一个并行会话（`wechat-bot-ops-handoff.md`）给出了更可信的解释**：`Stop-WebhookBackground.ps1` 用 `CommandLine -match` 过滤存活进程，但该字段在查询会话权限不足时会返回 `$null`，而 `$null -match` 恒为 `$false`——导致"看起来 Webhook stopped 打印成功，实际进程完全没被杀掉"，这完全能解释本对话观察到的"两个进程同时存在、时间戳几乎相同"的现象。那个会话已经修复（增加基于端口监听者的兜底检查）。**本对话原先怀疑的"WinRM 传输层双重执行"理论，现在看很可能是错误方向，不建议继续深挖。**
2. **同一会话还在 bot-3 上发现了 CDP 单 tab 并发访问缺锁的问题**：`keep_alive`（60s 一次）和 `refresh`（3600s 一次）各自开独立后台线程访问同一个 tab 的 CDP WebSocket，互相之间、以及和 `login()`/截图请求之间都没有互斥，实测会导致 tab 在首次定时 refresh 后 ~10 秒内永久卡死、且不会自愈。已修复（加了逐 tab 锁）。**这与本对话早期做的 `keep_alive` PeekObjects 修复是同一子系统,但是更深层的并发问题,不是本对话发现的。**
3. **`browser-session-recovery-handoff.md`（另一并行会话）发现了一个更根本的问题，与本对话早期的 keep-alive 工作直接相关**：`start_keep_alive()` 的后台循环只是把 `keep_alive()` 抛出的异常记下日志，从来不会真正重新登录；而 `ensure_tab()` 在整个进程生命周期里只会调用一次 `login()`。也就是说，**一旦会话真的死透一次，在下次进程重启之前会一直死着，不会自愈**。这是本对话此前所做的 auto-logout 修复（PeekObjects + 定时刷新）都没有覆盖到的场景——那两个修复能*延缓*会话过期，但如果两个机制同时失效导致会话真正死亡，目前没有任何自动恢复路径。**这是留给后续所有 Agent 的重要背景，不是本对话能解决的范围内问题，但强烈建议下一步优先看这份文档的具体修复方案（如果有）。**
4. **上述三个 bot-3 相关修复（CDP 锁、stop 验证盲区、签名日志）均已写入代码但尚未生效**——bot-3 上跑的还是修复前的旧进程。任何人都**不要**自行重启 bot-3 的 webhook，这是用户明确保留给自己的操作。
5. **本地测试实例（端口 8792）从未成功启动，根因未诊断**。`Start-WebhookOnly.ps1 -Port 8792` 分离启动后健康检查立即失败，具体报错从未被抓取（诊断被打断）。下一步应直接前台运行该脚本查看真实报错，而不是分离窗口。
6. **bot-1 当前运行中的进程是旧代码**——文件已同步，用户尚未重启，本分支所有改动对 bot-1 线上行为暂未生效。
7. **bot-2 状态本对话长时间未复核**，最后已知状态是 LSO/ARP 修复后健康。
8. **设备选型功能（equipment_catalog 等）默认关闭，但已深度嵌入 `message_router.py`/`wechat_image_reply.py` 核心逻辑**，只在 `equipment_catalog_enabled=True` 时才会激活分支——理论上对现有频道逻辑无侵入，但本对话未做任何验证。
9. **分支尚未合并、未经正式代码评审**（PR #4 open）。本地在 PR #4 之上还有大量未提交改动（本对话 + 另外两个并行会话的成果混在一起）。
10. **`ansible/inventory.yml` 含明文 WinRM 凭据和 Cloudflare 隧道 token**——不要粘贴进日志、commit 或本可信上下文之外的任何地方（这条是另一并行会话强调的，此处一并转达）。

---

## 6. 下一位 Agent 必须知道什么

- **先读完 `docs/agents/` 目录下全部四份交接文档，再决定下一步**——本文档只覆盖其中一条线索，`wechat-bot-ops-handoff.md` 和 `browser-session-recovery-handoff.md` 都包含直接相关、可能改变优先级判断的信息。`claude-sonnet-5-handoff.md` 与本仓库主线无关（`device-agent-mvp/` 独立工具），可以跳过。
- **不要在未被明确要求的情况下碰 bot-1 正在运行的进程。**
- **不要在未被明确要求的情况下尝试远程启动/重启 bot-3 的 webhook。** 多个会话都独立得出了同一条结论：这是用户明确保留给自己的操作。
- **`docs/DEBUG_HANDOFF.md`** 是本项目的技术事故档案，比本文档更详细，遇到"进程数不对"/"tab not debuggable"类问题前应先读。
- **`message_router.py` 是测试交互逻辑的正确入口**——但注意它已经被扩展支持设备选型流程，接手前重新读一遍当前完整内容，不要假设它还是本对话最初写的那个简单版本。
- **隧道现在和 bot 重启完全解耦**——不要假设 `all restart` 会修复隧道问题。
- **PowerShell 反复踩过的坑**：`win_shell` 注释里的撇号会破坏 ansible 解析；`2>&1` 重定向原生程序 stderr 配合 `$ErrorActionPreference = "Stop"` 会把非错误输出当致命错误；`Get-Content` 读本项目日志必须带 `-Encoding UTF8`，显示中文还需要 `[Console]::OutputEncoding = UTF8`。
- **除非用户明确要求，不要执行 `git commit`/`git push`。** 目前分支上除 PR #4 已提交内容外，还有大量来自多个会话的未提交改动混在一起。
