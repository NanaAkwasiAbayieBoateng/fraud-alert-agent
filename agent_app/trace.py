"""JSONL tracer: every step of an investigation is recorded with its
prompts, tool calls, results, and latency. All text passes through PII
redaction before it is stored, in memory and on disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .guardrails import redact_pii


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_pii(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


class Tracer:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self.events: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **fields: Any) -> dict:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        for key, value in fields.items():
            entry[key] = _redact_value(value)
        self.events.append(entry)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        return entry

    def events_of(self, event: str) -> list[dict]:
        return [e for e in self.events if e["event"] == event]
