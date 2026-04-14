[English](README.md) | [中文](README.zh-CN.md) | **日本語** | [Español](README.es.md)

# Cascade
**DAGベースのマルチエージェントタスクスケジューリングフレームワーク**

エージェントが依存関係グラフからタスクを取得し、Edge Contract を通じてコンテキストを受け渡し、共有ファイル状態を介して連携します。グラフは実行中でも動的に編集可能で、分割・詳細化・手戻りを行いながら一貫性を維持します。

## インストール

```bash
uv sync
```

## クイックスタート

```python
from cascade import GraphStorage
from tools import add_node, get_task, finish_task

storage = GraphStorage(".cascade")

# Edge に Contract を持つタスクグラフを構築
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
task = get_task(storage, {"agent_id": "agent-001"})

# コンテキストを下流エージェントに伝播しつつタスクを完了
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements analyzed: auth + REST API",
    "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
})
```

## 設計原則

- **Edge 上の Contract** — すべての Edge は `Contract(expectation, promise)` を持ち、両方とも必須です。同じ上流 Node からでも、異なる下流 Node に対して異なる promise を設定できます。
- **算出された準備状態** — キャッシュされた `in_degree` は使いません。Node が READY かどうかは、すべての依存先が COMPLETED であるかをグラフからリアルタイムに導出して判定します。
- **前方のみのフィードバック** — 手戻りは修正用の Node を新たに作成してグラフを前方に拡張します。完了済みの作業を変更したり、逆方向の Edge を作成することはありません。
- **クリティカルパススケジューリング** — `get_task` は下流チェーンが最も深い READY Node を優先的に割り当て、全体の完了時間を最小化します。
- **イベントソーシング** — すべての変更は追記専用の `events.jsonl` に記録されます。監査証跡、タイムトラベル、リプレイが可能です。
- **3層コンテキスト伝播** — `critical`（KV形式、無制限）、`summary`（テキスト、2ホップ）、`artifacts`（ファイル参照、無制限）。

## モジュール構成

依存チェーン（トポロジカルソートにより非循環を検証済み）：

```
types → core → context → view → operations → tools
```

| パッケージ | 役割 |
|---------|---------|
| `types` | 値型: `Contract`, `Context`, `EdgeId`, `ContextLevel` — 内部依存なし |
| `core` | `Cascade` グラフ、`Node`、遷移ルール付きの `NodeState` |
| `context` | コンテキスト伝播 + Go スタイルの `CancellationToken` |
| `view` | エージェント向け表示レイヤー（`get_node_view`） |
| `events` | 追記専用イベントログ（`EventStore`） |
| `operations` | 複合変更操作: `SplitOperation`, `RemoveOperation`, `ReworkOperation` |
| `storage` | `fcntl` ファイルロックによる JSON 永続化 |
| `tools` | LLM 向けインターフェース — シリアライズ境界 |

## Node の状態遷移

```
PENDING → READY → ACTIVE → COMPLETED
                    ↕ release      ↘ FAILED
                                   ↘ CANCELLED
```

## ツール一覧

フレームワーク非依存の関数: `(GraphStorage, dict) → dict`

| カテゴリ | ツール | 説明 |
|----------|-------|-------------|
| 構造 | `add_node` | タスク Node を作成 |
| | `remove_node` | Node を削除（カスケード削除オプションあり） |
| | `split_node` | タスクをサブタスクに分割 |
| | `refine_node` | 既存の Node に依存関係を追加 |
| | `edit_node` | 状態またはコンテキストを更新 |
| 実行 | `get_task` | タスクを取得（クリティカルパス優先） |
| | `finish_task` | タスクの完了 / 失敗 / リリース |
| フィードバック | `rework` | 上流への修正依頼（前方のみ） |
| 監視 | `check_timeouts` | 停滞したタスクをリリース |
| クエリ | `list_nodes` | すべてのタスクと状態を表示 |
| | `history` | イベントログを照会 |

## テストの実行

```bash
uv run pytest tests/
```

## ライセンス

Apache-2.0
