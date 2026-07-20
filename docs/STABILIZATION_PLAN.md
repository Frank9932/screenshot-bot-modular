# Stabilization Plan

生成于 2026-07-20，基于 `docs/PROJECT_SNAPSHOT.md` 的项目恢复结果。目标不是新增功能，
而是把项目从"能运行但状态不受控"整理为"可维护、可验证、可交接"。

本文档只覆盖**仓库/工程治理**层面的问题（密钥、测试、文档一致性、仓库边界），不覆盖
`docs/DEBUG_HANDOFF.md` 中记录的运行时基础设施问题（如 bot-3 的 split-brain 事件）——
那些已经在那份文档里被追踪，不在本次治理范围内重复。

**本轮已经直接执行的变更**（低风险、不改变运行行为，详见下方 P0 章节）：
- `.gitignore` 新增 `/storage/`、`config.json`、`device-agent-mvp/.env`、
  `device-agent-mvp/logs/`
- 新增 `device-agent-mvp/.env.example`（占位模板，不含真实值）

其余章节（P1 分析、测试基线设计、质量工具建议、`device-agent-mvp/` 归属建议）均为
**计划**，尚未执行，等待确认——见文末"变更计划与暂停点"。

---

## 风险清单

### P0 — 安全或数据泄漏风险

#### P0-1: `device-agent-mvp/.env` 内含明文 API Key
- **问题**：`device-agent-mvp/.env` 中 `OPENAI_API_KEY` 是一个未脱敏的真实密钥（前缀
  `sk-or-...`，看起来是 OpenRouter 密钥），以明文形式存在于工作目录，且此前未被
  `.gitignore` 覆盖。
- **证据**：读取 `device-agent-mvp/.env` 内容；`git status` 显示 `device-agent-mvp/`
  整体为未跟踪（尚未提交），但 `.gitignore` 修改前没有任何规则阻止它被
  `git add -A` 一类的操作纳入版本库。**本文档不复述密钥本身**。
- **风险**：一旦被提交并推送到 `origin`（该仓库是私有还是公开未在本地状态中确认——
  见"未知项"），密钥即永久留在 Git 历史中，即使之后删除文件也无法撤回；即使仓库私有，
  密钥也已经暴露给本次及此前对话式 Agent 会话的上下文，存在留存风险。
- **建议动作**：
  1. （已执行）`.gitignore` 新增 `device-agent-mvp/.env`，防止未来被提交。
  2. （已执行）新增 `device-agent-mvp/.env.example` 占位模板。
  3. **人工必须做**：轮换（作废并重新生成）这个 OpenRouter/OpenAI 密钥。这一步我不会
     代为执行——不会调用、验证或使密钥失效，需要你在 OpenRouter/OpenAI 控制台自己操作。
  4. 轮换后，把新密钥只写入本地 `.env`（已被忽略），不要写回任何会被提交的文件。
- **是否会修改运行行为**：不会。`.gitignore`/`.env.example` 变更不影响任何已运行代码；
  轮换密钥后需要你手动更新本地 `.env` 才能让 `device-agent-mvp` 继续工作。
- **验证方法**：`git status` 确认 `device-agent-mvp/.env` 不再出现在待跟踪文件列表；
  `git log --all --full-history -- device-agent-mvp/.env` 确认历史上从未有该文件的提交
  记录（本地检查确认为空，见"已确认基线"）。密钥是否已轮换只能由你在服务商控制台确认，
  我无法替你验证。

#### P0-2: `storage/` 运行时目录未被 `.gitignore` 覆盖
- **问题**：`config.example.json`/`config.json` 中 `incoming_image_dir`
  (`storage/incoming`)、`private_channel.save_dir` (`storage/private`)、
  `browser_targets.store_dir` (默认 `storage/screenshots`) 都指向仓库根目录下的
  `storage/`，但修改前的 `.gitignore` 完全没有这个目录的规则（对比之下 `/runtime/`、
  `/logs/`、`/screenshots/` 都已经被忽略）。
- **证据**：`.gitignore`（修改前）内容 vs. `config.example.json`/`docs/ARCHITECTURE.md`
  中反复出现的 `storage/{incoming,private,screenshots}` 路径；本地检查确认
  `storage/` 目录当前在这台机器上不存在（尚未运行到会写入的地步），所以此刻没有真实
  文件泄漏，但这是一个"下一次本地运行就会触发"的结构性缺口。
- **风险**：这个目录会累积**真实微信用户上传的照片**、**私密频道内容**（按设计本就是
  用户主动要求隐藏的敏感内容）、**内部仪表盘截图**（`10.121.0.14` 站点的运营数据）。
  一旦有人在这台或任何部署机器上跑过 bot 之后执行 `git add -A`/`git add .`，这些内容
  会被整批提交。
- **建议动作**：（已执行）`.gitignore` 新增 `/storage/`。
- **是否会修改运行行为**：不会，纯 Git 层面的排除规则。
- **验证方法**：`git check-ignore -v storage/incoming/anyuser/channel_1/x.png`（可用
  假路径测试，无需真实文件存在）应输出匹配到 `/storage/` 规则。

#### P0-3: `config.json` 含机器本地绝对路径，未与模板分离
- **问题**：`config.json`（未跟踪，此前也未被 `.gitignore` 覆盖）中
  `private_channel.save_dir` 的值是 `C:\Users\frank\Documents\screenshots`——一个
  包含本机用户名的绝对路径，且这个 schema 本身已经过时（仍保留已从代码中删除的
  `virtual_desktop` 配置块、`screenshot_tool`/`capture_message_types` 等旧字段，
  与当前 `config.example.json` 的 schema 不一致）。
- **证据**：直接读取 `config.json` 全文，对比 `config.example.json` 与
  `src/screenshot_bot/browser/`（无 `virtual_desktop` 相关代码，已在上次 recovery
  中确认该模块已被整体删除）。
- **风险**：本身不含密钥（凭据仍通过 env var 名称间接引用，符合项目约定），但含个人
  机器路径信息，且是一个可能已经"跑不动"的过期本地配置（见 P1 基线部分）；混在仓库根
  目录、无 `.gitignore` 保护，容易被误提交，或者被后来者误当作"当前有效配置"参考。
- **建议动作**：（已执行）`.gitignore` 新增 `config.json`。是否需要更新这份本地文件
  本身的内容（比如同步到当前 schema）不在本次安全清理范围内，留给你决定——见"未知项"。
- **是否会修改运行行为**：`.gitignore` 变更本身不影响任何行为；这份本地配置目前指向
  `browser_targets.enabled: false`，即使已经过时，只要本机不真的用它跑生产流量，行为
  不受影响。
- **验证方法**：`git check-ignore -v config.json` 应输出匹配到新规则；
  `git status` 中 `config.json` 不再出现在 untracked 列表。

#### 已排查、未发现新问题的部分
- 全仓库（排除 `runtime/`、`.git/`）按常见密钥模式（`sk-`、`AKIA`、`api_key=`、
  `password=`、`Bearer `、`xoxb-`、`ghp_` 等）扫描，命中的 5 处中 4 处是文档/模板里的
  占位符或 Ansible Vault 变量引用（`{{ vault_windows_admin_password }}`、
  `"paste-password-here"` 等），真实凭据只有 `device-agent-mvp/.env` 这一处（已处理，
  见 P0-1）。
- `secrets.local.ps1`、`ansible/inventory.yml`、
  `ansible/group_vars/screenshot_bot_modular.yml`、`ansible/files/secrets.local.ps1`
  在修改前的 `.gitignore` 中已经被正确排除，且本次检查确认这几个文件从未出现在
  `git log` 历史中（见"已确认基线"）。
- `10.121.0.14` 这个内网 IP 反复出现在 README/ARCHITECTURE/config 示例中——这是项目
  已经公开承认并作为文档主体的真实生产目标地址，不算"意外泄漏"，但如果这个仓库未来
  会变成公开仓库或分享给外部人员，值得你重新评估是否要把它当作敏感信息处理（不在本次
  安全清理的自动处理范围内，仅提示）。

### P1 — 可能导致项目不可维护或不可验证的问题

#### P1-1: 全仓库零自动化测试
- **问题**：没有任何 `tests/` 目录或 `test_*.py` 文件，尽管 `pyproject.toml` 已声明
  `[tool.pytest.ini_options] pythonpath = ["src"]`。所有模块 README 里的"Test"章节
  都是手工 PowerShell/REPL 片段，不是可被 CI 执行的东西。
- **证据**：`find . -iname "*test*"` 在排除 `runtime/`/`.git/` 后无匹配文件；
  `pyproject.toml` 全文只有 `pythonpath` 声明，没有任何测试文件与之对应。
- **风险**：`browser/`、`workflow/` 两个模块的 README 里记录了大量细节的并发/状态机
  行为（每 tab 锁、`message_router` 的多阶段 equipment 状态机、私密频道解锁逻辑），
  这些行为目前只能靠"改完之后手动跑一遍再部署到真实主机观察"来验证——任何回归都只会
  在生产环境（真实微信用户）身上暴露。
- **建议动作**：见下方"测试基线设计"章节（本次只出计划，不写代码）。
- **是否会修改运行行为**：新增测试文件本身不修改任何生产代码路径，风险为零；但如果
  测试过程中发现被测代码有真实 bug，修复该 bug 会改变行为——这类修复需要单独出
  commit，不与"新增测试"混在一起。
- **验证方法**：`pytest` 能发现并运行新增测试且全部通过；测试运行不依赖网络（可用
  `pytest -p no:cacheprovider --strict-markers` 或直接检查测试中没有真实 HTTP/CDP/
  WeChat 调用来确认隔离性）。

#### P1-2: `message_router.py` 等核心决策逻辑是纯函数却无验证
- **问题**：`workflow/message_router.py` 被设计为"给定消息+发送者状态，返回决策"的
  纯函数（无 I/O），`workflow/README.md` 明确说这是为了"可以完全脱离真实微信/浏览器
  单独调试"——但目前唯一的验证方式是人工跑 `python -m
  screenshot_bot.workflow.message_router` 交互式 REPL，没有任何自动化断言。
- **证据**：`workflow/README.md` → "Message routing (debuggable in isolation)" 章节；
  代码里确实找不到对应的自动化测试。
- **风险**：这个函数覆盖了频道加入/重新截图/水印命令/私密频道解锁/设备目录多阶段状态
  机等几乎全部业务规则分支，是这个项目里最该有测试、又最容易测（纯函数、无 I/O）的
  一块代码，目前完全没有测试杠杆。
- **建议动作**：作为测试基线设计的第一优先级（见下）。
- **是否会修改运行行为**：不会（纯新增测试）。
- **验证方法**：同 P1-1。

#### P1-3: `config.json` 本地基线已经与当前代码 schema 不同步
- **问题**：`config.json` 里仍配置着 `virtual_desktop`/`screenshot_tool`/
  `capture_message_types`/`state_path`/`url_file` 等字段，但对应的 `desktop/` 模块
  已经在本分支被整体删除（`git diff --stat master...HEAD` 显示
  `src/screenshot_bot/desktop/*` 全部为删除行）。当前代码不会读取这些废弃字段，所以
  不会报错，但这份本地配置本身处于"半退休"状态，如果有人拿它当"当前有效配置"的参考
  会被误导。
- **证据**：见 P0-3 的证据；另见 `docs/PROJECT_SNAPSHOT.md`"已移除"段落。
- **风险**：中等——不影响当前行为（死字段被忽略），但属于"未验证推断"的一个具体例子：
  没有人确认过这份本地配置在当前代码上完整跑通过。
- **建议动作**：不在本次安全清理范围内自动修改这份本地文件内容；建议你决定是否要
  把它重新对齐到 `config.example.json` 的当前 schema，或者直接归档/删除后按需从模板
  重新生成。
- **是否会修改运行行为**：不会（本项仅为记录，未采取行动）。
- **验证方法**：人工用当前 `config.example.json` 做 diff 确认差异范围。

#### P1-4: 没有 CI，质量门槛完全靠人工记忆执行
- **问题**：仓库里没有任何 CI 配置（未找到 `.github/workflows/`、`azure-pipelines.yml`
  等），`pyproject.toml` 也没有声明任何 lint/format 工具。
- **证据**：`Glob "**/*"` 未见 CI 配置文件；`pyproject.toml` 全文只有 `Pillow` 依赖
  和 pytest 路径声明。
- **风险**：即使按本计划补上测试和 lint 配置，如果没有任何自动触发机制，它们的价值
  取决于每个人是否记得手动运行——对"可交接"目标而言是个缺口。
- **建议动作**：见"质量门槛工具建议"，本次只给出本地可执行命令层面的建议，是否接入
  GitHub Actions 等 CI 平台留给你决定（仓库当前托管在 GitHub，`gh` 已确认可用）。
- **是否会修改运行行为**：不会。
- **验证方法**：本地能跑通 `pytest`/`ruff check`/`ruff format --check` 三个命令。

### P2 — 结构和文档质量问题

#### P2-1: `device-agent-mvp/` 完全未被任何项目文档提及（结构边界问题，详见下方专门章节）
已在 `docs/PROJECT_SNAPSHOT.md` 中记录；本文档"仓库边界评估"章节给出处理选项。

#### P2-2: 已合并分支 `feature/team-per-tab-browser-module` 未清理
- **问题**：`git branch -a` 显示本地和远程都还保留着
  `feature/team-per-tab-browser-module`，而 `gh pr list --state all` 确认它承载的
  PR #1/#2/#3 早已全部 `MERGED`。
- **证据**：见上方两条命令输出。
- **风险**：低——不影响任何运行行为，纯粹是认知负担（后来者可能误以为它还是活跃分支）。
- **建议动作**：确认无人还在这条分支上有未合并的本地提交后，删除本地和远程分支
  （`git branch -d` / `git push origin --delete`）。**这是一个会修改远程仓库状态的
  操作，按你的标准工作流需要你明确批准后才执行**，本次不自动做。
- **是否会修改运行行为**：不会（不影响代码，只影响 Git 引用）。
- **验证方法**：删除前 `git log feature/team-per-tab-browser-module ^master` 应为
  空（确认没有 master 里没有的提交）。

#### P2-3: `screenshot_store/README.md` 过时的 key 格式说明（已处理）
上次 recovery 会话中已修复（`{user_id}/tab_{tab}` → `{user_id}/channel_{id}/
{original,watermarked}`），本次不再重复处理，仅记录在案供审计。

#### P2-4: `pyproject.toml` 未声明任何工具依赖，仅有一个字段
`[tool.pytest.ini_options]` 是全文件里唯一的工具配置，`dependencies = ["Pillow"]`
也没有区分开发依赖和运行依赖（比如未来加的 `pytest`/`ruff` 该放
`[project.optional-dependencies]` 还是单独的 `requirements-dev.txt`，需要你选一个
约定）。见"质量门槛工具建议"。

### P3 — 以后可以优化的问题

#### P3-1: `config.example.json` 中 8 个高度重复的 channel 配置块
文档里已经承认这是"team-per-tab"模式的预期写法（每个 channel 只是复制整块再改一个
`tab` 字段），不是违规，但如果未来 channel 数量继续增长，缺少配置层面的"N 个 tab 的
同一目标"简写语法，会让 `config.example.json` 越来越长。不建议现在处理——不属于治理
阶段目标（会改变配置格式，属于功能/结构变更）。

#### P3-2: 跨进程并发锁问题（split-brain 根因未确认）
`docs/DEBUG_HANDOFF.md` 里已经详细记录：`profile_manager.py` 的 `threading.Lock()`
只能防止同进程内的竞争，无法防止两个独立 Python 进程同时管理同一个 Chrome 调试端口。
这是一个运行时可靠性问题，不是仓库治理问题，且已经有专门的文档在追踪，本次治理计划
不重复处理，仅在此列出交叉引用避免遗漏。

---

## 已确认基线 vs. 未知项

### 已确认（可从仓库状态直接验证）

| 项目 | 结论 | 依据 |
|---|---|---|
| 主入口 | `scripts/run_wechat_official_webhook.py` | 该脚本构建 `WeChatWebhookServer` 并调用 `serve_forever()`；`Bot.ps1`/ansible playbook 最终都落到这里 |
| 本地启动方式 | `scripts/Start-WebhookOnly.ps1 -ConfigPath <path>`（前台，测试用）；`scripts/Start-WebhookBackground.ps1`（后台，先调用 `Stop-WebhookBackground.ps1` 再启动，生产/计划任务用） | 脚本内容 + `README.md`"Local Run"章节 + `ansible/README.md` |
| 必需配置 | 一个 JSON 配置文件（`config.example.json`/`config.json`，`browser_targets`/`watermark`/`wechat_official_webhook` 等段）+ 环境变量 `WECHAT_APPID`/`WECHAT_APPSECRET`/`WECHAT_OFFICIAL_WEBHOOK_TOKEN`（必需）+ 可选的 `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD`（仅当某 target 的 `login.enabled=true`） | `secrets.local.example.ps1`；`browser/README.md`"Credentials"章节 |
| 外部依赖 | 一个真实 Chrome（`chrome_path` 指向的可执行文件，通过 CDP 远程调试端口控制）；WeChat Official Account 开放平台 API；可选 `cloudflared.exe`（仅隧道功能） | `browser/README.md`；`ansible/deploy.yml` 里的 cloudflared 安装步骤 |
| 部署方式 | Ansible over WinRM，目标 Windows 11 主机（`win11-bot-01/02/03`），playbook 入口 `ansible/deploy.yml`，日常操作通过 `scripts/Bot.ps1` 或 `ansible/bot.yml` 包装 | `ansible/README.md` 全文 |
| 自动化测试 | 不存在 | 见 P1-1 |
| CI | 不存在 | 见 P1-4 |
| Git 历史中是否曾提交过任何已知敏感文件 | 本地检查显示未曾提交（`git log --all --full-history` 对 `secrets.local.ps1`/`device-agent-mvp/.env`/`config.json`/`ansible/inventory.yml` 均无历史记录） | 见下方命令，建议你自己也跑一遍复核 |

```bash
git log --all --full-history -- secrets.local.ps1 device-agent-mvp/.env config.json ansible/inventory.yml
# 本地执行结果：无输出（无历史提交记录）
```

### 未知（无法仅从本地仓库状态确认，需要你补充或另行核实）

- **`device-agent-mvp/` 这次何时/由谁/为何被加入这个仓库**，与当前 WeChat 截图机器人
  产品是否有计划中的关联（比如未来想让设备选择走对话式 LLM），还是纯粹的技术验证，
  本地状态无法回答，只能靠你确认。
- **GitHub 仓库 `Frank9932/screenshot-bot-modular` 是私有还是公开**——这直接影响
  P0-1 的实际暴露面（`gh` 命令本身没有在这次检查里被要求核实这一点，按你的指示我不会
  自行发起额外的验证性调用去确认）。
- **`equipment_catalog`/`menu.py`/`message_router.py` 这批未提交的新功能是否已经在
  任何一台 bot-1/2/3 上部署或用真实微信账号验证过** —— 上次 recovery 已标记为
  Unknown，本次治理分析同样无法从本地状态回答。
- **`config.json` 里那份过期 schema 是否还在被实际使用**（比如是不是还有某个本地
  运行流程依赖它），还是纯粹的历史遗留——需要你确认后再决定是否更新/归档。
- **是否已有人工确认过 OpenRouter 密钥目前的有效性/额度状态**——按指示我不会代为
  调用验证。

---

## 测试基线设计（计划，尚未编写代码）

目标：为四类现有代码建立**不依赖外部系统**的自动化测试骨架，用 mock/fake/fixture
隔离真实微信、真实 Chrome、真实 Cloudflare Tunnel、真实网络。这是"最小基线"，不追求
覆盖率指标。

| 优先级 | 目标 | 建议测试文件 | 隔离方式 | 覆盖要点 |
|---|---|---|---|---|
| 1 | `message_router.route_message` 纯决策逻辑 | `tests/workflow/test_message_router.py` | 无需 mock——函数本身零 I/O，直接传参断言返回的 `kind`/字段 | 频道加入/重新截图/未加入频道收到图片/水印命令识别/帮助文本触发/私密频道口令解锁前后行为/backup 频道可用但不出现在提示中/equipment 各阶段状态转移（含越界数字、非法阶段下的确认取消） |
| 2 | channel / equipment catalog 选择逻辑 | `tests/workflow/test_equipment_catalog.py`, `tests/workflow/test_equipment_selection_tracker.py` | `equipment_catalog.load_categories/load_equipment` 用临时 CSV fixture（`tmp_path`），不读真实 `runtime/cdp-explore-out/hvac_equipment.csv`；`EquipmentSelectionTracker` 用 `tmp_path` 下的临时 JSON 文件 | CSV 解析的类别去重与顺序、越界/空目录/文件缺失时的兜底行为、tracker 的阶段持久化与重启后恢复 |
| 3 | `screenshot_store` 路径与读写行为 | `tests/screenshot_store/test_store.py` | 全程用 `tmp_path` 作 `base_dir`，不碰真实 `storage/` | 文件名格式（时间戳+耗时）、目录按 key 自动创建、返回的 `ScreenshotRecord` 字段、`size_bytes` 与实际写入字节数一致 |
| 4 | WeChat 消息输入 → workflow 决策关键路径 | `tests/workflow/test_wechat_image_reply.py` | 复用 `workflow/README.md`"Test"章节里已经写好的 `MockSender`/`MockBrowser`/`MockMediaDownloader` 思路，包成 pytest fixture；`UserTeamTracker`/`incoming_image_store` 指向 `tmp_path` | 帮助文本路径、频道加入+首次入群提示、图片重新截图路径、水印命令路径整条链路的 `ok=True` 与关键返回字段 |

**明确不做**：不测 `wechat/webhook_server.py` 的真实 HTTP/签名细节（可选的第五类，
优先级低于以上四类，如果做也应该只测 `verify_wechat_signature`/`parse_xml_message`
这些纯函数部分，不起真实 HTTP server）；不测 `browser/cdp_multi_tab_service.py`
真实 CDP 交互（需要真实 Chrome，超出"最小基线"范围，且 `browser/README.md` 里已经
记录了这部分是靠人工对真实站点验证的）。

---

## 质量门槛工具建议

现状：`pyproject.toml` 只声明了 `Pillow` 一个运行依赖和 pytest 的 `pythonpath`。

建议（尽量少引入新工具，优先复用已声明的栈）：

| 用途 | 建议工具 | 理由 |
|---|---|---|
| 测试 | `pytest`（已在 `pyproject.toml` 声明路径，只是从未真正安装/使用） | 已经是项目既定选择，不需要新决策 |
| Lint + Format | `ruff`（`ruff check`、`ruff format`） | 一个工具覆盖 lint 和 format 两件事，避免同时引入 `flake8`+`black`+`isort` 三个工具；对纯 stdlib+Pillow 的中小型代码库足够，安装/配置成本最低 |
| 静态类型检查 | **暂不引入** | 当前代码几乎没有类型注解（`config.py`/`store.py` 等函数签名普遍无类型），引入 `mypy` 现在只会产生大量噪音而非真实收益；等类型注解自然积累到一定比例后再考虑 |

建议的 `pyproject.toml` 追加内容（仅供本次计划展示，未落地）：
```toml
[project.optional-dependencies]
dev = ["pytest", "ruff"]

[tool.ruff]
line-length = 100
target-version = "py310"
```

本地可执行的质量命令（提案）：
```powershell
pytest
ruff check .
ruff format --check .
```

是否要把这些接入 GitHub Actions CI 是一个独立决定（见 P1-4），本次只建议先把命令在
本地跑顺，再决定要不要自动化触发。

---

## 仓库边界评估：`device-agent-mvp/`

### 证据
- 代码层面与 `screenshot_bot` 包**零耦合**：不 import `screenshot_bot` 的任何模块，
  也没有被 `screenshot_bot` 的任何模块引用。
- 技术栈完全独立：`openai`、`pydantic`、`python-dotenv`（见
  `device-agent-mvp/requirements.txt`），均不在根目录 `requirements.txt`/
  `pyproject.toml` 里。
- 问题域相邻但不同：`screenshot_bot` 是"微信用户发数字/图片 → 截图机器人"；
  `device-agent-mvp` 是"用户自然语言描述设备 → LLM 从 676 行 HVAC 设备 CSV 里挑一个
  → mock 执行 open/status 命令"的对话式 CLI 原型，**跑在同一份设备 CSV 数据集
  （HVAC equipment）上**，这点和 `workflow/equipment_catalog.py` 读的
  `hvac_equipment.csv` 数据性质相似，可能是同一批业务数据的两次不同尝试。
- 完全未被任何项目文档（`README.md`/`docs/ARCHITECTURE.md`/`docs/DEBUG_HANDOFF.md`/
  模块 README）提及。
- 含真实凭据（见 P0-1），且没有 `.gitignore` 保护（本次已修复）。
- 没有自己的 `README.md`，没有测试，没有可执行入口说明之外的任何文档。

### 选项（不自动执行，等待你确认）

| 选项 | 适用场景 | 代价 |
|---|---|---|
| **移动到 `experiments/device-agent-mvp/`** | 如果这是一次探索性验证，未来可能会继续 迭代但暂时不是正式产品的一部分，想保留在同一仓库里方便找 | 低：`git mv`，一次 commit，需要同步更新任何硬编码相对路径（目前看代码里用 `Path(__file__).parent`，应该不受目录改名影响，但需要验证） |
| **拆到独立仓库** | 如果这实际上是一个独立方向（对话式设备控制），未来会有自己的部署/发布节奏，不希望和截图机器人共享 commit 历史/CI | 中：需要新建仓库、迁移历史（或者放弃历史直接复制）、更新任何外部引用 |
| **保留原地，但补齐文档** | 如果就是想让它继续留在这里，只是之前忘了写文档 | 低：加一份 `device-agent-mvp/README.md` 说明用途/关系/运行方式 |
| **删除** | 如果这只是一次性实验，没有继续开发的打算 | 需要先确认没有人还需要这份代码/数据；`device-agent-mvp/data/hvac_equipment.csv` 这份数据本身可能有价值，删除前建议单独确认是否要保留数据文件 |

我的初步判断（仅供参考，不代表已经决定）：从代码质量看这不是随手写的脚本（有结构化
的 `models.py`/候选检索去重逻辑/日志记录），值得保留；但它现在完全游离于项目文档之外，
**至少需要在文档层面明确它的定位**，无论最终选哪个选项。四个选项都不会改变
`screenshot_bot` 主产品的任何运行行为。

---

## 变更计划与暂停点

按照要求，在进行下一步（写测试代码 / 落地 `pyproject.toml` 工具配置 / 移动或拆分
`device-agent-mvp/`）之前，在这里暂停，等待你的确认。

### 本轮已经落地的变更（供你审查，尚未 commit）
| 文件 | 变更 | 是否改变运行行为 |
|---|---|---|
| `.gitignore` | 新增 `/storage/`、`config.json`、`device-agent-mvp/.env`、`device-agent-mvp/logs/` 四条规则 | 否 |
| `device-agent-mvp/.env.example`（新建） | 占位符模板，不含真实值 | 否 |
| `src/screenshot_bot/screenshot_store/README.md` | 上次会话已修正过时的 key 格式说明（非本轮新增，随手确认仍然正确） | 否 |
| `docs/DEBUG_HANDOFF.md` | 上次会话已补充 2026-07-20 状态段（非本轮新增） | 否 |
| `docs/PROJECT_SNAPSHOT.md`（新建） | 上次会话产出 | 否 |
| `docs/STABILIZATION_PLAN.md`（新建） | 本轮产出，即本文档 | 否 |

以上都是纯文档/忽略规则变更，不触碰任何 `src/`/`scripts/`/`ansible/` 下的产品代码。

### P0 / P1 风险摘要（供快速审阅）
- **P0**：明文密钥（`device-agent-mvp/.env`，需人工轮换）、`storage/` 未被忽略、
  `config.json` 未被忽略且已过期——三项均已通过 `.gitignore` 处理，密钥轮换本身
  必须由你完成。
- **P1**：零自动化测试（尤其 `message_router.py` 这个本该最容易测的纯函数模块）、
  `config.json` 基线与当前代码不同步、无 CI。

### 下一步待确认后再执行的工作，及建议的 commit 拆分

如果你确认继续，我会把接下来的工作拆成互不混合的独立 commit（不会把安全清理、测试
补充、结构重构、文档整理混在一个 commit 里；本轮已做的安全清理和文档新增本身也建议
单独成一个 commit，与下面几项分开）：

1. **commit A（本轮已做的安全清理，待你确认后再提交）**：`.gitignore` 四条新规则 +
   `device-agent-mvp/.env.example`。不改变运行行为。
2. **commit B（待确认）**：`tests/` 目录 + 上表四类最小测试（`message_router`、
   equipment catalog/tracker、`screenshot_store`、`wechat_image_reply` 关键路径）。
   纯新增文件，不改变任何生产代码，除非测试过程中发现真实 bug——那种情况我会先向你
   报告发现了什么，单独讨论是否修，而不是顺手改掉混进这个 commit。
3. **commit C（待确认）**：`pyproject.toml` 的 `[project.optional-dependencies]` +
   `[tool.ruff]` 配置，纯声明性变更，不改变运行行为。
4. **commit D 或独立任务（待你先选一个选项后再动手）**：`device-agent-mvp/` 归属
   处理——移动 / 拆分 / 补文档 / 删除四选一，取决于你的决定。**不会自动执行**，见上方
   "仓库边界评估"。
5. **不属于本次 commit 计划、留给你手动处理**：轮换 OpenRouter/OpenAI 密钥（P0-1）；
   删除已合并的 `feature/team-per-tab-browser-module` 分支（P2-2，涉及远程仓库状态
   变更）；是否/如何更新 `config.json` 本地内容本身（P1-3）。

请告诉我：commit A 是否可以直接提交；要不要现在就开始写 commit B 的测试；
`device-agent-mvp/` 选哪个选项；以及 `pyproject.toml`/ruff 的建议是否认可。
