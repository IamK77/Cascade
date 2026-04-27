# Cascade

[![CI](https://github.com/autoseek/cascade/actions/workflows/ci.yml/badge.svg)](https://github.com/autoseek/cascade/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](../../LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

[English](../../README.md) | **中文** | [日本語](README.ja.md) | [Español](README.es.md)


一个具备动态 DAG 调度能力的智能体工厂。编排器实时构建和调整任务图，无状态的工作器认领、执行和交付任务——通过边上的 Contract 和归因式上下文流进行协调。

## 核心特性

- **动态 DAG** — 执行过程中可拆分、返工、细化、移除任务
- **归因式上下文** — 每个上游贡献独立保存，并附带溯源信息（路径、距离、Contract）
- **Contract 驱动的边** — 每条边携带 `expectation`（消费者需求）和 `promise`（生产者交付）
- **关键路径调度** — READY 任务按下游深度优先分配
- **取消协议** — 跨进程支持拉取（检查 token）和推送（CancelNotifier）两种方式
- **ACTIVE 保护** — 无法移除或拆分有活跃智能体的节点
- **事件溯源** — 每次变更均被记录，支持可选的 `reason` 字段用于审计

## 安装

```bash
# 作为 CLI 工具
pipx install cascade-auto
# 或
uv tool install cascade-auto

# 作为 Python 库
pip install cascade-auto
```

开发环境：

```bash
git clone https://github.com/autoseek-ai/Cascade.git
cd Cascade
uv sync
```

## 快速开始

```python
from cascade import CascadeClient, Contract

cascade = CascadeClient()

# 构建任务图 — 水平拆分以实现并行
cascade.add("analyze")
cascade.add("design", deps={
    "analyze": Contract("Feature requirements and constraints", "Deliver prioritized feature list"),
})

# 智能体认领任务 — 关键路径优先
task = cascade.claim("agent-001")

# 完成任务并传递上下文给下游智能体
cascade.complete("analyze",
    summary="Requirements: JWT auth + REST API",
    critical={"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
)
```

当 `agent-002` 认领 `design` 时，它看到的是：

```json
{
  "upstream": [{
    "node_id": "analyze",
    "state": "COMPLETED",
    "distance": 1,
    "expectation": "Feature requirements and constraints",
    "promise": "Deliver prioritized feature list",
    "delivered": {
      "summary": "Requirements: JWT auth + REST API",
      "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]}
    }
  }]
}
```

不合并、不覆盖——每个上游来源都是独立的条目。

## 架构

```
types → core → context → view → operations → tools
```

| 包 | 用途 |
|---------|---------|
| `types` | 值类型：`Contract`、`Context`、`ContextEntry`、`TokenStatus` |
| `core` | `Cascade` 图、`Node`、`NodeState`（6 状态 FSM） |
| `context` | BFS 祖先传播 + 取消机制（进程内） |
| `view` | 上游视图构建器（`get_node_view`） |
| `events` | 仅追加的事件日志（14 种事件类型） |
| `operations` | 复合变更操作：Split、Remove、Rework |
| `storage` | JSON 持久化 + 文件锁 + token 存储 |
| `tools` | 12 个面向 LLM 的函数——序列化边界 |
| `client` | `CascadeClient` — 带 IDE 支持的类型化 Python API，封装 tools 层 |

## 工具

类型化 Python API 是 `CascadeClient`。底层工具层使用 `(GraphStorage, dict) → dict` 签名，用于 CLI 和 JSON 边界。

| 类别 | 工具 |
|----------|-------|
| 结构 | `add_node`、`remove_node`、`split_node`、`refine_node`、`edit_node` |
| 执行 | `get_task`、`finish_task` |
| 反馈 | `rework` |
| 取消 | `check_task` |
| 监控 | `check_timeouts` |
| 查询 | `list_nodes`、`history` |

所有变更工具均支持 `reason` 字段用于事件日志审计。

## 上下文流

三个通道，每个上游条目都附带溯源归因：

| 通道 | 传播范围 | 用途 |
|---------|-------------|---------|
| `critical` | 无限传播 | 结构化键值数据（决策、配置） |
| `summary` | 2 跳 | 简要文本描述 |
| `artifacts` | 无限传播 | 完整文档、代码、规格说明 |

## 取消机制

一种语义，两种实现：

| 场景 | 机制 |
|----------|-----------|
| 跨进程（CLI、多机器） | `TokenStore` — 基于文件的 `.cascade/tokens/` |
| 进程内（框架嵌入） | `CancellationToken` — 内存级，即时回调 |

两者都使用 `CancelNotifier` 协议实现推送通知。

## 运行测试

```bash
uv run pytest tests/        # 196 个测试
uv run ruff check src tests  # lint 检查
```

## 文档

- [指南](../guide.md) — 全面的使用教程
- [架构](../architecture.md) — 系统设计、状态机、Mermaid 图表
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — 开发指南
- [SECURITY.md](../../SECURITY.md) — 漏洞报告与安全模型

## 许可证

Apache-2.0 — 详见 [LICENSE](../../LICENSE)。
