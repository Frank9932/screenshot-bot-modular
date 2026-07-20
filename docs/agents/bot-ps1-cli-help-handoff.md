# Handoff: Bot.ps1 CLI 入口优化

**Agent:** claude-sonnet-5
**范围:** 本次对话仅完成 `scripts/Bot.ps1` 的 CLI 入口易用性改造（新增默认帮助输出、命令/参数校验、大小写不敏感等）。不涉及仓库其他未提交改动（README、ansible、wechat 相关文件等）——那些是对话开始前工作区里就已存在的改动，与本次任务无关，本次对话未触碰。

---

## 1. 本对话完成了什么

- 审查了 `scripts/Bot.ps1` 现有 CLI 入口的问题：
  - `Command` 参数为 `Mandatory = $true`，无参数运行脚本时 PowerShell 会进入交互式提示（"Supply values for the following parameters: Command:"）阻塞等待输入，而不是给出可读的用法说明。
  - `Command`/`Action` 用 `ValidateSet` 做校验，输错时抛出的是 PowerShell 原生的参数绑定异常，信息对用户不友好，也没有集中的帮助文本。
- 重新设计了命令分发前的校验/帮助层：新增 `help`/`-h`/`--help`/`-?`/`/?` 等多种触发帮助的方式、无参数时默认显示帮助、未知命令与缺失/非法 action 给出针对性提示、命令与 action 输入大小写不敏感。
- 用 PowerShell 实际执行验证了 4 种场景（见下），确认行为符合预期。

## 2. 哪些已经进入代码

文件：[scripts/Bot.ps1](../../scripts/Bot.ps1)（已用 Edit 工具直接写入磁盘，**尚未 git add / commit**，仍是工作区改动）。

具体改动：

- `param()` 块：`Command` 从 `Mandatory + ValidateSet` 改为普通字符串参数，默认值 `"help"`；`Action` 同样改为普通字符串（不再用 `ValidateSet`）；新增 `-Help` 开关，别名 `-h`、`-?`。
- 新增 `$script:Commands`（有序哈希表），集中定义 4 个命令（`status` / `webhook` / `browser` / `tunnel`）及各自允许的 action 列表和一句话描述，作为校验和帮助文本的唯一数据源。
- 新增 `Show-Help` 函数，输出 `USAGE` / `COMMANDS` / `OPTIONS` / `EXAMPLES` 格式的帮助文本。
- 新增顶部前置校验块（在原有业务函数定义之前）：
  - `-Help` 或空 `Command` 或 `Command` 属于 help 别名集合 → 打印帮助，`exit 0`。
  - `Command` 不在 `$script:Commands` 中 → `Write-Warning` 提示合法命令列表 + 打印帮助，`exit 1`。
  - 命令要求 action 但未提供或不合法 → `Write-Warning` 提示合法 action 列表 + 打印帮助，`exit 1`。
  - 校验通过后，`$Command` / `$Action` 会被规范化为小写，供后续逻辑使用。
- 原有的主 `switch ($Command) { ... }` 分发逻辑（调用各 `Invoke-*` 函数）**未改动**。其内部每个子 switch 里原有的 `default { throw ... }` 分支现在因为前置校验已保证合法性而**理论上不可达**，保留作为防御性兜底，未删除、未清理。

已用 PowerShell 手动执行验证的场景（均符合预期）：

1. `scripts\Bot.ps1`（无参数）→ 打印帮助，`exit 0`。
2. `scripts\Bot.ps1 bogus` → `WARNING: Unknown command: 'bogus'. ...` + 帮助，`exit 1`。
3. `scripts\Bot.ps1 webhook`（缺 action）→ `WARNING: 'webhook' requires an action. ...` + 帮助，`exit 1`。
4. `scripts\Bot.ps1 WEBHOOK STATUS`（大小写混合）→ 正常执行 `Invoke-WebhookStatus`，输出 JSON，`exit 0`。
5. `scripts\Bot.ps1 -h` → 打印帮助，`exit 0`。

## 3. 哪些只是讨论

- 无。用户直接给出明确需求（"优化 CLI 入口、让用户易懂、加默认帮助输出"），本次对话直接实现并验证完毕，没有产生未落地的方案讨论。

## 4. 哪些决策后来被推翻

- 无。本次对话内没有出现"先这样做、后来又改回去"的反复；实现思路一次到位，没有中途推翻的设计。

## 5. 哪些风险仍存在

- **未提交**：`scripts/Bot.ps1` 的改动仍只在工作区（`git status` 显示 `M scripts/Bot.ps1`），未 `git add`/`commit`。`git status` 里其余大量改动（README、ansible、wechat 相关文件等）是对话开始前就存在的、与本次任务无关的历史改动，未做任何处理——提交前需要用户自行确认哪些改动应该一起提交，避免误打包。
- **死代码未清理**：主 `switch` 内两处 `default { throw "... requires an action: ..." }` 分支现已不可达（前置校验层已经保证不会走到这里），保留但未删除。不影响当前功能，但如果以后有人重构前置校验层，需要注意这两处旧提示不会再触发，容易造成"改了提示语却没生效"的困惑。
- **仅做了手动验证**：只跑了上述 4 个场景的手动测试，没有自动化测试覆盖这个脚本。以后若再改动 param 校验逻辑，需要重新手动过一遍这几种场景（无参数 / 未知命令 / 缺 action / 大小写 / -h）。
- **未验证的调用方式**：没有验证非 `-File` 方式调用（例如 dot-source `. .\Bot.ps1` 或双击）时行为是否一致，理论上应该一致，但未实测。

## 6. 下一位 Agent 必须知道什么

- CLI 帮助/校验逻辑全部集中在 `scripts/Bot.ps1` 文件顶部（约第 41–102 行）。修改命令或 action 列表时，只需改 `$script:Commands` 这张表；`Show-Help` 里的文本是手写的，**不是**从 `$script:Commands` 自动生成的，两处需要手动保持同步。
- 命令与 action 在进入主 `switch` 分发前已经过 `ToLowerInvariant()` 规范化和合法性校验，因此新增命令时必须同步在 `$script:Commands` 里注册，否则会被顶部前置校验拦截为"未知命令"，永远走不到主 `switch` 里新加的分支。
- Memory 中记录的两条与本仓库相关的约束（与本次改动无关，但适用于后续在同一仓库的操作）：
  - 不要在本地开发机上无差别 `kill chrome.exe`（只能在远程测试机上这样做）。
  - 不要替用户远程在 bot-1/2/3 上启动/重启 webhook 进程（诊断/排查/kill 可以，start/restart 必须用户手动做）。
- 提交前建议先跑一次 `git status` / `git diff scripts/Bot.ps1`，确认只把本次任务范围内的改动打包提交。
