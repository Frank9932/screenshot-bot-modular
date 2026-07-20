# Handoff：CDP 多标签页集成 + tab-not-debuggable / 孤儿进程三连环故障排查

**范围**：本文档只覆盖“本对话”这一条会话线所做的工作，即从 `CdpMultiTabService` 多标签页浏览器集成开始，
到最终定位并修复三次递归出现的 "tab not debuggable" 故障为止。仓库里同时存在其他会话产出的内容
（channel/watermark 重构、tap-menu/equipment 流程、`device-agent-mvp/`、多份 `docs/agents/*-handoff.md`），
**均不属于本对话**，下文会明确指出边界。

**结论先说**：本对话的全部改动已经进入 git 提交历史，即 commit
`abbcefb Fix tab-not-debuggable orphan-process incidents; add Bot.ps1 CLI and public tunnel tooling`
（2026-07-07）。`git show abbcefb` 是本对话产出的唯一可信来源，优先于任何文字复述（包括本文档）。

---

## 1. 本对话完成了什么

- 用新的 `CdpMultiTabService`（共享一个 Chrome 进程、多标签页管理）替换了旧的"每个 target 一个 Chrome 进程"模型。
- 验证了登录态站点（Schneider Electric EcoStruxure WebStation，`10.121.0.14`）的自动登录 + kill/relaunch 测试。
- 把 `browser_targets` 配置从"多个互不相关的 target"重新设计为：WeChat team id `1`-`5` 分别对应
  **同一个** WebStation 登录会话下的 5 个标签页（`webstation-test`, `..._tab1`~`_tab4`）；截图存储按
  `{user_id}/tab_{N}` 归档。
- 按用户指示把测试/部署主目标切换到 `win11-bot-01`（100.97.205.111），并明确不再触碰 `win11-golden-test-01`。
- 诊断了一次真实的"发消息不回复"生产事故（账号 `oerGt3IRCp6LagUl5ZkRRTIUVuaM`）——根因是隧道重启后
  URL 变了但没有明确提醒用户去 WeChat 后台更新。
- 搭建了一套运维工具链：
  - `scripts/Bot.ps1`——统一 CLI 入口（`status` / `webhook start|stop|restart|status|logs` /
    `browser restart|warmup` / `tunnel start|stop|status`）。
  - `scripts/Start-PublicTunnel.ps1` / `Stop-PublicTunnel.ps1`——Cloudflare quick tunnel，
    通过隔离 `USERPROFILE` 避开了机器上已有的 named tunnel 配置劫持 `--url` 请求的问题。
  - `ansible/bot.yml`、`tunnel-start.yml`、`tunnel-stop.yml`、`tunnel-status.yml`、
    `webhook-restart.yml`——上述脚本的 ansible 薄封装。
- 定位并修复了导致 "tab not debuggable" 反复出现的 **三个独立故障**（详见 §2/§4），
  每次都是"以为修好了→用户反馈依然存在/又发现新现象→继续深挖"的循环：
  1. **Incident 1**：`ensure_tab()` 里 `warm_up()` 后台线程与并发抓图请求之间的 TOCTOU 竞态。
  2. **Incident 2**：`ansible/webhook-start.yml` 从未在可靠的 WinRM 会话里显式停止旧进程，
     只依赖新计划任务自己内部的 stop 调用——而那个调用跑在不同 session 里，杀不掉旧进程。
  3. **Incident 3**：计划任务用 `/RL HIGHEST`（提权）启动，导致用户手动在自己控制台（非提权）
     重启时杀不掉这个更高权限的旧进程，产生了两个进程同时争抢同一组 Chrome 标签页的
     **真实 split-brain**。
- 期间一次诊断脚本（`kill_orphan_pair2.ps1`）因 keep-set 逻辑写反，误杀了真正在监听端口的合法进程，
  造成短暂真实中断——发现后立即坦白并用 `webhook-restart.yml` 恢复。
- 全程维护 `docs/DEBUG_HANDOFF.md` 作为故障排查的连续记录（该文件现已被后续会话大幅追加，见 §5）。

## 2. 哪些已经进入代码

以下内容均已确认存在于当前 `HEAD`（即 commit `abbcefb`，2026-07-07），可用 `git show abbcefb` 复核：

| 文件 | 改动 |
|---|---|
| [`src/screenshot_bot/browser/profile_manager.py`](../../src/screenshot_bot/browser/profile_manager.py) | `ensure_tab()` 外层加 `threading.Lock()`，串行化标签页创建，避免 warm_up 与真实抓图请求之间的竞态 |
| [`src/screenshot_bot/browser/cdp_multi_tab_service.py`](../../src/screenshot_bot/browser/cdp_multi_tab_service.py) | `_get_page()` 改为最长重试 3 秒（每 200ms 轮询一次），而不是立刻抛错——新建标签页的 devtools target 可能要过一瞬间才暴露 `webSocketDebuggerUrl` |
| [`ansible/webhook-start.yml`](../../ansible/webhook-start.yml)、[`webhook-restart.yml`](../../ansible/webhook-restart.yml)、[`ansible/tasks/startup.yml`](../../ansible/tasks/startup.yml) | 在 WinRM 会话里显式调用一次 `Stop-WebhookBackground.ps1`（而不是只信任计划任务内部的 stop）；**并且三处的 `schtasks /Create` 都去掉了 `/RL HIGHEST`** |
| [`scripts/Stop-WebhookBackground.ps1`](../../scripts/Stop-WebhookBackground.ps1) | 5 次重试杀进程循环；5 次后仍有残留时改为 **`throw`**（原来是 `Write-Warning`，会被静默吞掉） |
| [`scripts/Start-WebhookBackground.ps1`](../../scripts/Start-WebhookBackground.ps1) | 内部无条件调用一次 `Stop-WebhookBackground.ps1` |
| `scripts/Bot.ps1`（新增） | 统一 CLI 入口 |
| `scripts/Start-PublicTunnel.ps1` / `Stop-PublicTunnel.ps1`（新增） | quick tunnel + `USERPROFILE` 隔离 |
| `ansible/bot.yml`、`tunnel-start.yml`、`tunnel-stop.yml`、`tunnel-status.yml`（新增） | 上述脚本的 ansible 封装 |
| `docs/DEBUG_HANDOFF.md`（新增，当时 286 行） | 三次事故的完整记录（现已被追加，见 §5） |
| `README.md`、`ansible/README.md`、`docs/ARCHITECTURE.md` | 配套文档更新 |

**需要留意**：`cdp_multi_tab_service.py` 目前**同时还包含** `_tab_locks`/`_lock_for()` 这套按标签页加锁的机制——
这不是本对话加的，是后续另一个会话（见 `docs/agents/browser-session-recovery-handoff.md`）加的，
且那份文档自己也承认"从未和本对话的改动做过协调测试"。两套锁机制目前共存于同一个文件，兼容性未经验证。

## 3. 哪些只是讨论，没有落地

- **跨进程互斥锁**（named mutex 或 `run_wechat_official_webhook.py` 启动时检查的 lock file）——
  用来彻底堵住"两个独立进程同时管理同一个共享 Chrome 调试端口"的结构性缺口。多次在"下一步建议"里提到，
  **从未实现**。目前的 `threading.Lock()`（Incident 1 的修复）只是进程内锁，管不住第二个进程。
- **Incident 3 修复后从未用真实场景复测过**：所有验证都是走 ansible/WinRM（提权）路径，
  而这条路径本来就不是当初失败的那条。真正的失败场景——用户直接在 `win11-bot-01` 自己的控制台上
  手动跑一次非提权的重启——修复之后一次都没有重新触发验证过。
- **PID 15872 那个交互式控制台是否真的是非提权（Medium integrity）**：这只是一个吻合所有观察现象的理论，
  从未直接查过那个 token 的实际权限级别去确认。
- **本地竞态复现测试的有效性存疑**：针对 mock 登录站点，加锁和不加锁分别测了并发场景，
  结果都是 3/3 通过——说明本地 mock（localhost、速度快）根本没能复现生产环境里真实的竞态窗口，
  加锁这个修复的必要性是从生产现象反推出来的，不是被受控实验直接证明的。
- **修复后没有观察到任何一条真实 WeChat 消息命中过 webhook**：所有验证都停留在"重启路径干净"这一层，
  没有验证过一次真实的截图请求端到端不报 "tab not debuggable"。
- 是否提交/推送/开新 PR 这件事本身，在对话里的表述一直是"等用户明确要求"——但从 git 历史看，
  这批改动最终确实进了 `abbcefb`，说明用户后来确实提出了要求（或者是本对话后续、
  已被压缩掉的部分执行的），细节不在当前可见的上下文里。

## 4. 哪些决策后来被推翻

- **计划任务提权（`/RL HIGHEST`）**：最初是有意这么设计的，目的是让 Chrome 落在用户可见的交互式桌面
  （session 1）而不是不可见的 session 0。**这个决策在 Incident 3 里被推翻**——三处 `schtasks /Create`
  全部去掉了 `/RL HIGHEST`，因为"计划任务用提权启动、手动重启用非提权控制台"这个权限不对等，
  正是导致真实 split-brain 的根因：非提权进程杀不掉提权进程，`Stop-Process -ErrorAction SilentlyContinue`
  又把这个失败悄悄吞掉了。
- **`Stop-WebhookBackground.ps1` 的失败处理方式**：原来 5 次重试后仍有残留只是 `Write-Warning`（软失败，
  不阻断后续流程）。**被推翻为 `throw`（硬失败）**——因为软失败会让 `Start-WebhookBackground.ps1`
  在杀不掉旧进程的情况下继续启动新进程，两个进程一起抢同一批 Chrome 标签页而没有任何人知道。
- **"Incident 1 的锁+重试修复已经解决问题"这个初步结论**：用户反馈"相同问题依然存在"后被推翻，
  引出 Incident 2 的真正根因（`webhook-start.yml` 缺少显式停止调用）。
- **对用户宣布的"验证完成，修复生效"结论本身也是不成立的**：Incident 2 修复验证完成后大约 37 分钟，
  Incident 3 通过一个完全不同的触发路径（用户手动、非提权重启）再次复现了同样的症状——说明当时
  "确认修好了"这句话需要补一个"仅限于当时验证过的那条触发路径"的限定。
- **`kill_orphan_pair2.ps1` 的"保留 tracked PID + 其父进程"逻辑**：被证明是错的（杀掉了真正在监听端口的
  合法进程），后来的判断标准统一改成了"杀之前先用 `Get-NetTCPConnection` 核对谁才是真正的端口监听者"。

## 5. 哪些风险仍存在

- **最大的风险：Incident 3 的修复（去掉 `/RL HIGHEST`）从未针对真正失败的场景复测过。**
  所有验证都走的是 ansible/WinRM 这条本来就没失败过的提权路径。下一次有人在 `win11-bot-01`
  自己的控制台上手动重启浏览器/webhook，才是真正的检验时刻。
- **split-brain 的结构性缺口仍然存在**：即使权限对齐了，也只是堵住了"这一种"触发方式。
  没有任何机制阻止未来出现的第二种触发路径让两个独立进程同时管理同一个共享 Chrome 调试端口。
- **`cdp_multi_tab_service.py` 已被后续会话继续修改**，加入了 `_tab_locks`/`_lock_for()` 这套独立的
  按标签页加锁机制，且明确记录"从未和本对话的改动核对过"。两套锁（本对话的进程内 `threading.Lock()`
  + 后续会话的按标签页锁）目前共存，组合行为未经验证。
- **`docs/DEBUG_HANDOFF.md` 已经被后续两个不相关的会话大幅追加**（一次 2026-07-17 的 channel/watermark
  会话，一次 2026-07-20 的"仅基于仓库状态、非实时调试"的恢复性梳理）。本对话最初写的记录仍然完整保留在
  文件里（从标题 "Historical: tab-not-debuggable / orphan-process incident (2026-07-05, resolved)" 开始），
  但物理位置已经被顶到文件中段，只看文件开头的人会完全错过本对话的排查记录。
- **`win11-bot-01` 现在被标记为"用户手动管理，未经明确要求不要部署/重启/触碰其运行进程"**
  （这条指示是在后续的 07-17 会话里记录下来的）。这和上一条风险直接冲突：Incident 3 的修复本身没验证过，
  但要验证它就得重启这台机器，而这台机器现在默认是"不能碰"的。
- 当前工作树里同时混着好几个跟本对话无关的功能分支产出（`menu.py`、`equipment_catalog.py`、
  `device-agent-mvp/` 等）。本对话自己的改动是安全的（已提交为 `abbcefb`），但如果直接对工作树跑
  `git status`/`git diff`，会看到一个大得多、来源混杂的 diff——需要靠本文档 + `git log` 来分辨哪部分
  是哪次对话的产出。

## 6. 下一位 Agent 必须知道什么

- 本对话的全部产出已经进了 git：`git show abbcefb` 就是唯一可信来源，别从任何文字总结（包括本文档）
  反推细节，直接看 diff。
- 三次事故的完整记录在 `docs/DEBUG_HANDOFF.md` 里，标题是
  "Historical: tab-not-debuggable / orphan-process incident (2026-07-05, resolved)"——
  文件会被后续会话不断在前面追加新内容，所以按标题搜索，别记行号。
- **动 `win11-bot-01` 之前先确认当前的站立指示**——后续会话已经把它标记成"用户自己管理，未经明确要求
  不要碰"，哪怕是为了验证本对话自己遗留的修复也一样，先问。
- 如果要继续做"堵住跨进程 split-brain 缺口"这件事，注意 `cdp_multi_tab_service.py` 里已经有另一个
  会话独立加的 `_tab_locks` 锁机制——先把本对话的 `profile_manager.py` 锁和那套锁放在一起读一遍，
  确认它们没有互相打架，再决定要不要加第三套机制。
- Incident 2、Incident 3 的修复都只验证过"重启路径本身干净"，**没有一次是通过真实 WeChat 消息端到端
  验证的**，也没有一次是通过真正的非提权手动重启验证的。不要把这两个修复当作已经证明有效。
- 项目里反复确认过的规矩：**只有用户明确要求才能 commit/push/开 PR**——本对话的改动虽然确实进了 git，
  但那是因为用户当时提出了要求（或本对话被压缩掉的后续部分代为执行），不代表以后可以不问自主提交。
- 另外两条已经记在长期 memory 里、同样适用的规矩：本机（开发机）上不要无差别 `taskkill chrome.exe`，
  只在远程测试机上这么做；bot-1/2/3 上只能诊断/修复/kill，不能主动启动或重启 webhook 进程，
  启动永远是用户自己来做。
