# Project Rules

- Version: 0.1
- Status: Active
- Owner: Project Coordinator
- Last Updated: 2026-07-20

---

## Rule 1 — 开始任务

开始任何开发任务前，必须阅读：

- `docs/PROJECT_SNAPSHOT.md`
- `docs/TASK_STATUS.md`

如任务涉及历史事故、旧实现或并行 Agent，再按需阅读：

- `docs/KNOWLEDGE_RECONCILIATION.md`
- `docs/agents/` 对应 handoff

不要默认依赖聊天记录。

## Rule 2 — 完成与交接

开发任务完成、暂停、阻塞或对话即将结束时，必须生成或更新对应的：

`docs/agents/<agent-or-task>-handoff.md`

handoff 至少包含：

- 本次任务目标
- 已完成内容
- 未完成内容
- 修改过的文件
- 测试或验证情况
- 已知风险
- 下一步建议

## Rule 3 — 项目事实更新

只有代码已经完成 Review 并合并到项目主分支后，才能把该变化写入：

`docs/PROJECT_SNAPSHOT.md`

开发中、仅讨论、未验证或未合并的内容，不得写成项目事实。

## Rule 4 — Bug 修复

Bug 修复应优先增加回归测试。

如果当前无法增加自动化测试，handoff 必须明确记录：

- 为什么无法测试
- 已采用什么手工验证
- 仍存在哪些验证缺口

## Rule 5 — 事实优先级

项目知识优先级固定为：

Current Code
>
Git History
>
PROJECT_SNAPSHOT
>
KNOWLEDGE_RECONCILIATION
>
Agent Handoff
>
聊天内容

出现冲突时，以更高优先级来源为准，不得猜测。

---

## Future Evolution

v0.1 故意保持最小化——只定义五条规则，不引入任何强制执行机制或自动化。未来可以在此基础上增加，
但本轮不实施：

- Coordinator Agent
- PR 检查清单
- CI 强制规则
- 任务依赖
- 自动状态更新
- 自动 Knowledge Reconciliation 触发
- 自动文档一致性检查
