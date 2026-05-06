# Cascade

[![CI](https://github.com/autoseek/cascade/actions/workflows/ci.yml/badge.svg)](https://github.com/autoseek/cascade/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](../../LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

[English](../../README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | **Español**


Una fábrica de agentes con planificación dinámica de DAG. Los orquestadores construyen y adaptan grafos de tareas en tiempo real mientras los trabajadores sin estado reclaman, ejecutan y entregan — coordinándose mediante contratos en las aristas y flujo de contexto atribuido.

## Características Principales

- **DAG dinámico** — dividir, rehacer, refinar y eliminar tareas durante la ejecución
- **Contexto atribuido** — cada contribución upstream se mantiene separada con procedencia (ruta, distancia, contrato)
- **Aristas basadas en contratos** — cada arista lleva `expectation` (lo que necesita el consumidor) y `promise` (lo que entrega el productor)
- **Planificación por ruta crítica** — las tareas READY se priorizan por profundidad downstream
- **Protocolo de cancelación** — pull (verificar token) o push (CancelNotifier) entre procesos
- **Protección de nodos ACTIVE** — no se pueden eliminar/dividir nodos con agentes activos
- **Event sourcing** — cada mutación registrada con `reason` opcional para auditoría

## Instalación

```bash
# Como herramienta CLI
pipx install cascade-auto
# o
uv tool install cascade-auto

# Como biblioteca Python
pip install cascade-auto
```

Para desarrollo:

```bash
git clone https://github.com/autoseek-ai/Cascade.git
cd Cascade
uv sync
```

## Inicio Rápido

```python
from cascade import CascadeClient, Contract

cascade = CascadeClient()

# Construir un grafo de tareas — dividir horizontalmente para paralelismo
cascade.add("analyze")
cascade.add("design", deps={
    "analyze": Contract("Feature requirements and constraints", "Deliver prioritized feature list"),
})

# El agente reclama una tarea — ruta crítica primero
r = cascade.claim("agent-001")

# Completar con contexto que fluye a los agentes downstream
# El framework inyecta produced_at y git_ref en critical automáticamente
cascade.complete("analyze",
    summary="Requirements: JWT auth + REST API",
    critical={"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
)
```

Cuando `agent-002` reclama `design`, ve:

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
      "critical": {
        "auth_type": "JWT",
        "endpoints": ["/users", "/posts"],
        "produced_at": 1778050765.98,
        "git_ref": "a3f8c2e..."
      }
    }
  }]
}
```

Sin fusión, sin sobrescritura — cada fuente upstream es una entrada separada.

## Arquitectura

```
types → core → context → view → operations → tools
```

| Paquete | Propósito |
|---------|-----------|
| `types` | Tipos de valor: `Contract`, `Context`, `ContextEntry`, `TokenStatus` |
| `core` | Grafo `Cascade`, `Node`, `NodeState` (FSM de 6 estados) |
| `context` | Propagación de ancestros por BFS + cancelación (en proceso) |
| `view` | Constructor de vista upstream (`get_node_view`) |
| `events` | Log de eventos append-only (14 tipos de evento) |
| `operations` | Mutaciones compuestas: Split, Remove, Rework |
| `storage` | Persistencia JSON + bloqueo de archivos + almacén de tokens |
| `tools` | 12 funciones para LLM — la frontera de serialización |
| `client` | `CascadeClient` — API Python tipada con soporte IDE que envuelve tools |

## Herramientas

La API Python tipada es `CascadeClient`. Todos los métodos retornan `Result`; proyecciones tipadas vía `TaskView.from_result()` y `NodeInfo.list_from_result()`. La capa de herramientas subyacente usa firmas `(StorageProtocol, dict) → dict` para los límites CLI y JSON.

| Categoría | Herramientas |
|-----------|-------------|
| Estructura | `add_node`, `remove_node`, `split_node`, `refine_node`, `edit_node` |
| Ejecución | `get_task`, `finish_task` |
| Retroalimentación | `rework` |
| Cancelación | `check_task` |
| Monitoreo | `check_timeouts` |
| Consulta | `list_nodes`, `history` |

Todas las herramientas de mutación soportan `reason` para auditoría del log de eventos.

## Flujo de Contexto

Tres canales, cada entrada upstream atribuida con procedencia:

| Canal | Propagación | Usar para |
|-------|-------------|-----------|
| `critical` | Indefinida | Datos KV estructurados (decisiones, configuraciones) |
| `summary` | 2 saltos | Descripción breve en texto |
| `artifacts` | Indefinida | Documentos completos, código, especificaciones |

## Cancelación

Una semántica, dos implementaciones:

| Escenario | Mecanismo |
|-----------|-----------|
| Entre procesos (CLI, multi-máquina) | `TokenStore` — respaldado en archivos `.cascade/tokens/` |
| En proceso (integración con framework) | `CancellationToken` — en memoria, callbacks instantáneos |

Ambos usan el protocolo `CancelNotifier` para notificaciones push.

## Ejecutar Tests

```bash
uv run pytest tests/        # 298 tests
uv run ruff check src tests  # lint
```

## Documentación

- [Guía](../guide.md) — recorrido completo
- [Arquitectura](../architecture.md) — diseño del sistema, máquina de estados, diagramas Mermaid
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — guías de desarrollo
- [SECURITY.md](../../SECURITY.md) — reporte de vulnerabilidades y modelo de seguridad

## Licencia

Apache-2.0 — ver [LICENSE](../../LICENSE).
