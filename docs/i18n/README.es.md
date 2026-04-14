[English](../../README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | **Español**

# Cascade

Un framework de planificación de tareas multi-agente basado en DAG. Los agentes reclaman tareas de un grafo de dependencias, pasan contexto a través de contratos en las aristas (edge contracts) y se coordinan mediante estado compartido en archivos. El grafo puede editarse dinámicamente durante la ejecución — dividir, refinar, rehacer — manteniendo la consistencia.

## Instalación

```bash
uv sync
```

## Inicio rápido

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

## Principios de diseño

- **Contratos en las aristas** — cada arista lleva un `Contract(expectation, promise)`, ambos obligatorios. Distintos nodos descendentes pueden recibir diferentes promesas del mismo nodo ascendente.
- **Estado de disponibilidad calculado** — sin `in_degree` en caché. Un Node está READY cuando todas sus dependencias están COMPLETED, derivado del grafo en tiempo real.
- **Retroalimentación solo hacia adelante** — el retrabajo crea nodos correctivos que hacen crecer el grafo hacia adelante. Nunca se muta trabajo completado, nunca se crean aristas inversas.
- **Planificación por ruta crítica** — `get_task` asigna el Node READY con la cadena descendente más profunda primero, minimizando el tiempo total de finalización.
- **Event sourcing** — cada mutación se registra en `events.jsonl` de solo adición. Auditoría, viaje en el tiempo, reproducción.
- **Propagación de contexto en 3 niveles** — `critical` (clave-valor, infinito), `summary` (texto, 2 saltos), `artifacts` (referencia a archivo, infinito).

## Estructura de módulos

Cadena de dependencias (verificada acíclica mediante ordenamiento topológico):

```
types → core → context → view → operations → tools
```

| Paquete | Propósito |
|---------|-----------|
| `types` | Tipos de valor: `Contract`, `Context`, `EdgeId`, `ContextLevel` — cero dependencias internas |
| `core` | Grafo `Cascade`, `Node`, `NodeState` con reglas de transición |
| `context` | Propagación de contexto + `CancellationToken` al estilo Go |
| `view` | Capa de presentación para agentes (`get_node_view`) |
| `events` | Registro de eventos de solo adición (`EventStore`) |
| `operations` | Mutaciones compuestas: `SplitOperation`, `RemoveOperation`, `ReworkOperation` |
| `storage` | Persistencia JSON con bloqueo de archivos `fcntl` |
| `tools` | Interfaz orientada a LLM — la frontera de serialización |

## Estados de los Nodes

```
PENDING → READY → ACTIVE → COMPLETED
                    ↕ release      ↘ FAILED
                                   ↘ CANCELLED
```

## Herramientas

Funciones agnósticas al framework: `(GraphStorage, dict) → dict`.

| Categoría | Herramientas | Descripción |
|-----------|-------------|-------------|
| Estructura | `add_node` | Crear un nodo de tarea |
| | `remove_node` | Eliminar un nodo (cascada opcional) |
| | `split_node` | Dividir una tarea en subtareas |
| | `refine_node` | Agregar una dependencia a un nodo existente |
| | `edit_node` | Actualizar estado o contexto |
| Ejecución | `get_task` | Reclamar una tarea (prioridad por ruta crítica) |
| | `finish_task` | Completar / fallar / liberar una tarea |
| Retroalimentación | `rework` | Solicitar corrección ascendente (solo hacia adelante) |
| Monitoreo | `check_timeouts` | Liberar tareas estancadas |
| Consulta | `list_nodes` | Ver todas las tareas y estados |
| | `history` | Consultar el registro de eventos |

## Ejecución de tests

```bash
uv run pytest tests/
```

## Licencia

Apache-2.0
