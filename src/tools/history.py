# Copyright 2026 Hangzhou Autoseek Information Technology Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""History Tool — query the event log.

Provides read access to the append-only event log for audit trails,
debugging, and time-travel inspection.
"""

from datetime import UTC, datetime
from typing import Any

from cascade.events import EventType
from cascade.storage.graph_storage import GraphStorage


def history(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Query the event history.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, optional): Filter events for a specific node
            - event_type (str, optional): Filter by event type
            - last_n (int, optional): Return only the last N events
            - summary (bool, optional): If True, return event count by type

    Returns:
        Dict with events or summary.
    """
    try:
        event_store = storage.events

        if params.get("summary"):
            counts = event_store.summary()
            return {
                "success": True,
                "message": f"{sum(counts.values())} total events",
                "data": {"summary": counts, "total": sum(counts.values())},
            }

        # Fetch events with filters
        node_id = params.get("node_id")
        event_type_str = params.get("event_type")

        if node_id:
            events = event_store.read_by_node(node_id)
        elif event_type_str:
            try:
                et = EventType(event_type_str)
            except ValueError:
                valid = [e.value for e in EventType]
                return {
                    "success": False,
                    "message": f"Invalid event_type: {event_type_str}. Valid: {valid}",
                    "data": {},
                }
            events = event_store.read_by_type(et)
        else:
            events = event_store.read_all()

        # Apply last_n
        last_n = params.get("last_n")
        if last_n and isinstance(last_n, int) and last_n > 0:
            events = events[-last_n:]

        # Format for output
        formatted = []
        for event in events:
            ts = datetime.fromtimestamp(event.timestamp, tz=UTC).isoformat()
            formatted.append({
                "type": event.type.value,
                "timestamp": ts,
                "data": event.data,
            })

        return {
            "success": True,
            "message": f"{len(formatted)} event(s)",
            "data": {"events": formatted, "count": len(formatted)},
        }

    except Exception as e:
        return {"success": False, "message": f"Failed to read history: {e}", "data": {}}
