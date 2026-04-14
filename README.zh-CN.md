[English](README.md) | **中文** | [日本語](README.ja.md) | [Español](README.es.md)

# Cascade
### 基于 DAG 的多智能体任务调度框架

一个基于 DAG 的多智能体任务调度框架。智能体从依赖图中认领任务，通过边上的 Contract 传递上下文，并借助共享文件状态进行协调。执行过程中可以动态编辑图结构 -- 拆分、细化、返工 -- 同时保持一致性。

## 安装

```bash
uv sync
```

## 快速开始

```python
from cascade import GraphStorage
from tools import add_node, get_task, finish_task

storage = GraphStorage(".cascade")

# Build a task graph with contracts on edges
add_node(storage, {"node_id": "analyze"})
add_node(storage, {
    "node_id": "design",
    "dependencies": ["analyze"],
    "expectations": [{
        "node_id": "analyze",
        "expectation": "Feature requirements and constraints",
        "promise": "Deliver prioritized feature list",
    }],
})

# Agent claims a task — prioritized by critical path
task = get_task(storage, {"agent_id": "agent-001"})

# Complete with context that flows to downstream agents
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements analyzed: auth + REST API",
    "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
})
```

## 设计原则

- **边上的 Contract** -- 每条边都携带 `Contract(expectation, promise)`，两者均为必填。不同的下游 Node 可以从同一个上游 Node 获得不同的 promise。
- **计算得出的就绪状态** -- 没有缓存的 `in_degree`。一个 Node 是否处于 READY 状态，取决于其所有依赖是否都已 COMPLETED，该状态从图中实时推导。
- **只向前的反馈** -- 返工会创建纠正性 Node，使图向前生长。永远不修改已完成的工作，永远不创建反向边。
- **关键路径调度** -- `get_task` 优先分配下游链最深的 READY Node，最小化总完成时间。
- **事件溯源** -- 每次变更都记录在仅追加的 `events.jsonl` 中。支持审计追踪、时间旅行和重放。
- **三级上下文传播** -- `critical`（键值对，无限传播）、`summary`（文本，传播 2 跳）、`artifacts`（文件引用，无限传播）。

## 模块结构

依赖链（通过拓扑排序验证无环）：

```
types → core → context → view → operations → tools
```

| 包 | 用途 |
|---------|---------|
| `types` | 值类型：`Contract`、`Context`、`EdgeId`、`ContextLevel` -- 零内部依赖 |
| `core` | `Cascade` 图、`Node`、`NodeState` 及其状态转换规则 |
| `context` | 上下文传播 + Go 风格的 `CancellationToken` |
| `view` | 面向智能体的展示层（`get_node_view`） |
| `events` | 仅追加的事件日志（`EventStore`） |
| `operations` | 复合变更操作：`SplitOperation`、`RemoveOperation`、`ReworkOperation` |
| `storage` | 基于 `fcntl` 文件锁的 JSON 持久化 |
| `tools` | 面向 LLM 的接口 -- 序列化边界 |

## Node 状态

```
PENDING → READY → ACTIVE → COMPLETED
                    ↕ release      ↘ FAILED
                                   ↘ CANCELLED
```

## 工具

与框架无关的函数：`(GraphStorage, dict) → dict`。

| 类别 | 工具 | 描述 |
|----------|-------|-------------|
| 结构 | `add_node` | 创建一个任务 Node |
| | `remove_node` | 删除一个 Node（可选级联删除） |
| | `split_node` | 将一个任务拆分为子任务 |
| | `refine_node` | 为现有 Node 添加依赖 |
| | `edit_node` | 更新状态或上下文 |
| 执行 | `get_task` | 认领任务（关键路径优先） |
| | `finish_task` | 完成 / 失败 / 释放任务 |
| 反馈 | `rework` | 请求上游修正（只向前） |
| 监控 | `check_timeouts` | 释放超时停滞的任务 |
| 查询 | `list_nodes` | 查看所有任务及其状态 |
| | `history` | 查询事件日志 |

## 运行测试

```bash
uv run pytest tests/
```

## 许可证

Apache-2.0
