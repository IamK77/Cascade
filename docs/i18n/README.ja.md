# Cascade

[![CI](https://github.com/autoseek/cascade/actions/workflows/ci.yml/badge.svg)](https://github.com/autoseek/cascade/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

[English](../../README.md) | [中文](README.zh-CN.md) | **日本語** | [Español](README.es.md)


動的DAGスケジューリングによるエージェントファクトリー。オーケストレーターがタスクグラフをリアルタイムに構築・適応させ、ステートレスなワーカーがタスクを取得・実行・納品します。Edge上のContractと帰属付きコンテキストフローによって連携を実現します。

## 主な特徴

- **動的DAG** — 実行中にタスクの分割・手戻り・詳細化・削除が可能
- **帰属付きコンテキスト** — 各上流の寄与を出所情報（パス、距離、Contract）とともに個別に保持
- **Contract駆動のEdge** — すべてのEdgeが `expectation`（消費者の要求）と `promise`（生産者の提供内容）を持つ
- **クリティカルパススケジューリング** — 下流の深さに基づきREADYタスクを優先
- **キャンセルプロトコル** — プロセス間でpull（トークン確認）またはpush（CancelNotifier）方式
- **ACTIVEノード保護** — アクティブなエージェントが割り当てられたノードの削除・分割を防止
- **イベントソーシング** — すべての変更を監査用の `reason` 付きで記録

## インストール

```bash
pip install cascade-auto
```

## クイックスタート

```python
from cascade import GraphStorage
from tools import add_node, get_task, finish_task

storage = GraphStorage(".cascade")

# タスクグラフを構築 — 並列化のために水平分割
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

# エージェントがタスクを取得 — クリティカルパス優先
result = get_task(storage, {"agent_id": "agent-001"})

# 下流エージェントに伝播するコンテキスト付きでタスクを完了
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements: JWT auth + REST API",
    "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
})
```

`agent-002` が `design` を取得すると、以下の情報が得られます：

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

マージも上書きもなし — 各上流ソースは個別のエントリとして保持されます。

## アーキテクチャ

```
types → core → context → view → operations → tools
```

| パッケージ | 役割 |
|---------|---------|
| `types` | 値型: `Contract`, `Context`, `ContextEntry`, `TokenStatus` |
| `core` | `Cascade` グラフ、`Node`、`NodeState`（6状態FSM） |
| `context` | BFS祖先伝播 + キャンセル（プロセス内） |
| `view` | 上流ビュービルダー（`get_node_view`） |
| `events` | 追記専用イベントログ（14種類のイベント型） |
| `operations` | 複合変更操作: Split, Remove, Rework |
| `storage` | JSON永続化 + ファイルロック + トークンストア |
| `tools` | 12個のLLM向け関数 — シリアライズ境界 |

## ツール

`(GraphStorage, dict) → dict` — フレームワーク非依存。

| カテゴリ | ツール |
|----------|-------|
| 構造 | `add_node`, `remove_node`, `split_node`, `refine_node`, `edit_node` |
| 実行 | `get_task`, `finish_task` |
| フィードバック | `rework` |
| キャンセル | `check_task` |
| 監視 | `check_timeouts` |
| クエリ | `list_nodes`, `history` |

すべての変更ツールはイベントログ監査用の `reason` をサポートしています。

## コンテキストフロー

3つのチャネル、各上流エントリに出所情報が付与されます：

| チャネル | 伝播範囲 | 用途 |
|---------|-------------|---------|
| `critical` | 無制限 | 構造化KVデータ（意思決定、設定） |
| `summary` | 2ホップ | 簡潔なテキスト説明 |
| `artifacts` | 無制限 | 完全なドキュメント、コード、仕様書 |

## キャンセル

1つのセマンティクス、2つの実装：

| シナリオ | メカニズム |
|----------|-----------|
| プロセス間（CLI、マルチマシン） | `TokenStore` — ファイルベースの `.cascade/tokens/` |
| プロセス内（フレームワーク組み込み） | `CancellationToken` — メモリ上、即時コールバック |

いずれも `CancelNotifier` プロトコルによるpush通知を使用します。

## テストの実行

```bash
uv run pytest tests/        # 196 tests
uv run ruff check src tests  # lint
```

## ドキュメント

- [ガイド](docs/guide.md) — 包括的なウォークスルー
- [CONTRIBUTING.md](CONTRIBUTING.md) — 開発ガイドライン

## ライセンス

Apache-2.0 — [LICENSE](LICENSE) を参照。
