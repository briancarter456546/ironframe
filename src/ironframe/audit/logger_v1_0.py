# ============================================================================
# ironframe/audit/logger_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Append-only JSONL audit logger. Write-before-release for non-streaming.
#
# Pattern follows scimode_recorder_v1_0.py and checkin_logger_v1_0.py:
#   - JSONL format, one JSON object per line
#   - ensure_ascii=True for safe output
#   - UTF-8 encoding on all I/O
#   - Directory auto-created on first write
#
# Usage:
#   from ironframe.audit.logger_v1_0 import AuditLogger
#   logger = AuditLogger()  # uses config defaults
#   logger.log_event('model_call', 'mal.client', {'model_id': 'haiku'})
#   logger.log_audit_event(audit_event)  # pass AuditEvent directly
# ============================================================================

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ironframe.audit.schema_v1_0 import AuditEvent


class AuditLogger:
    """Append-only JSONL audit logger.

    Thread-safe. Writes are atomic per-event (single line append).
    Write-before-release: the log method writes to disk and flushes
    before returning. If the write fails, the caller gets the exception.

    v1.0 C27 update: if a writer is injected (or one is resolved from
    environment via ironframe.audit.writer_v1_0.writer_from_env), events
    flow through that writer as well as the local file. This adds the
    collector transport without breaking the local cache contract.
    """

    def __init__(
        self,
        output_dir: str = "output/ironframe",
        filename: str = "audit.jsonl",
        writer=None,
    ):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._filepath = self._output_dir / filename
        self._lock = threading.Lock()
        self._event_count = 0
        # C27: optional AppendOnlyWriter. If None, we retain the legacy
        # behaviour (local file write only) so existing callers see no
        # change until they opt in.
        self._writer = writer

    @property
    def filepath(self) -> Path:
        return self._filepath

    @property
    def event_count(self) -> int:
        return self._event_count

    def log_audit_event(self, event: AuditEvent) -> None:
        """Write an AuditEvent to the log. Write-before-release: blocks until
        the event is flushed to disk."""
        self._append_line(event.to_json())

    def log_event(
        self,
        event_type: str,
        component: str,
        details: Optional[Dict[str, Any]] = None,
        session_id: str = "",
        **kwargs,
    ) -> AuditEvent:
        """Convenience method: create an AuditEvent and log it in one call.

        Returns the created AuditEvent for reference.
        """
        event = AuditEvent.create(
            event_type=event_type,
            component=component,
            session_id=session_id,
            **kwargs,
        )
        # Merge any extra details into data_lineage
        if details:
            event.data_lineage = {**event.data_lineage, **details}
        self.log_audit_event(event)
        return event

    def _append_line(self, line: str) -> None:
        """Thread-safe append of a single line to the JSONL file.

        C27: if a writer is attached, also hand the parsed event off to the
        writer. Writer failure does not affect the local append -- this
        matches the "local file = advisory cache" contract.
        """
        with self._lock:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
            self._event_count += 1
        if self._writer is not None:
            try:
                event_dict = json.loads(line)
                self._writer.append(event_dict)
            except Exception:
                # Fail-graceful -- writer problems must not break logging.
                pass

    def read_events(self, limit: int = 100) -> list:
        """Read recent events from the log (most recent last). For diagnostics."""
        if not self._filepath.exists():
            return []
        lines = self._filepath.read_text(encoding="utf-8").strip().splitlines()
        recent = lines[-limit:] if len(lines) > limit else lines
        events = []
        for line in recent:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
