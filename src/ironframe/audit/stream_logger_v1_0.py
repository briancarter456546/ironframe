# ============================================================================
# ironframe/audit/stream_logger_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Streaming-aware audit logger using open/close pattern.
#
# CriticMode correction: standard write-before-release breaks for streaming
# because the full output isn't available until the stream completes.
#
# Pattern:
#   1. OPEN: when stream starts, log input + model + session (no output yet)
#   2. ACCUMULATE: track tokens as they arrive (in-memory only)
#   3. CLOSE: when stream ends, write final entry with output hash,
#      token count, confidence, cost. This is the immutable record.
#   4. ERROR: if stream fails mid-way, close entry with error status.
#
# The open entry is a placeholder. The close entry is the audit record.
# Both are written to the same JSONL log via AuditLogger.
#
# Usage:
#   from ironframe.audit.stream_logger_v1_0 import StreamAuditLogger
#   from ironframe.audit.logger_v1_0 import AuditLogger
#
#   logger = AuditLogger()
#   stream_log = StreamAuditLogger(logger, session_id='abc')
#   stream_log.open(model_id='haiku', provider='anthropic', input_text='...')
#   for chunk in stream:
#       stream_log.accumulate(chunk.text, chunk.tokens)
#   stream_log.close(cost_usd=0.001)
#   # If error:
#   stream_log.close_with_error('Connection reset', 'ConnectionError')
# ============================================================================

import hashlib
from typing import Optional

from ironframe.audit.schema_v1_0 import AuditEvent
from ironframe.audit.logger_v1_0 import AuditLogger


class StreamAuditLogger:
    """Manages the open/close lifecycle of a single streaming audit entry.

    One instance per stream. Not reusable -- create a new one per stream.
    """

    def __init__(self, logger: AuditLogger, session_id: str = "", component: str = "mal.client"):
        self._logger = logger
        self._session_id = session_id
        self._component = component

        # State
        self._is_open = False
        self._is_closed = False
        self._open_event_id = ""
        self._model_id = ""
        self._provider = ""
        self._input_text = ""

        # Accumulated during streaming
        self._output_chunks: list = []
        self._tokens_in = 0
        self._tokens_out = 0

    @property
    def is_open(self) -> bool:
        return self._is_open and not self._is_closed

    @property
    def event_id(self) -> str:
        return self._open_event_id

    def open(
        self,
        model_id: str,
        provider: str,
        input_text: str = "",
        tokens_in: int = 0,
    ) -> AuditEvent:
        """Log the stream-open event. Records input + model before any output."""
        if self._is_open:
            raise RuntimeError("StreamAuditLogger already open. Create a new instance per stream.")

        self._model_id = model_id
        self._provider = provider
        self._input_text = input_text
        self._tokens_in = tokens_in

        event = AuditEvent.create(
            event_type="stream_open",
            component=self._component,
            session_id=self._session_id,
            input_text=input_text,
            model_id=model_id,
            provider=provider,
            tokens_in=tokens_in,
            is_streaming=True,
            stream_status="open",
        )

        self._open_event_id = event.event_id
        self._is_open = True
        self._logger.log_audit_event(event)
        return event

    def accumulate(self, text_chunk: str, tokens: int = 0) -> None:
        """Track a chunk of streaming output. In-memory only -- no disk write."""
        if not self.is_open:
            raise RuntimeError("Cannot accumulate: stream not open or already closed.")
        self._output_chunks.append(text_chunk)
        self._tokens_out += tokens

    def close(
        self,
        cost_usd: float = 0.0,
        confidence_score: float = -1.0,
        confidence_signals: Optional[dict] = None,
        tokens_out_override: Optional[int] = None,
    ) -> AuditEvent:
        """Log the stream-close event. Writes the final immutable audit record."""
        if not self.is_open:
            raise RuntimeError("Cannot close: stream not open or already closed.")

        full_output = "".join(self._output_chunks)
        output_hash = hashlib.sha256(full_output.encode("utf-8")).hexdigest()
        tokens_out = tokens_out_override if tokens_out_override is not None else self._tokens_out

        # Truncate summary
        max_len = 500
        summary = full_output[:max_len] + "..." if len(full_output) > max_len else full_output

        event = AuditEvent.create(
            event_type="stream_close",
            component=self._component,
            session_id=self._session_id,
            input_text=self._input_text,
            output_summary=summary,
            output_text=full_output,
            model_id=self._model_id,
            provider=self._provider,
            tokens_in=self._tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            confidence_score=confidence_score,
            confidence_signals=confidence_signals,
            is_streaming=True,
            stream_status="closed",
            data_lineage={"stream_open_event_id": self._open_event_id},
        )

        self._is_closed = True
        self._logger.log_audit_event(event)
        return event

    def close_with_error(self, error: str, error_type: str = "StreamError") -> AuditEvent:
        """Close the stream with an error status. Partial output is preserved."""
        if not self.is_open:
            raise RuntimeError("Cannot close: stream not open or already closed.")

        partial_output = "".join(self._output_chunks)
        summary = partial_output[:500] + "..." if len(partial_output) > 500 else partial_output

        event = AuditEvent.create(
            event_type="stream_error",
            component=self._component,
            session_id=self._session_id,
            input_text=self._input_text,
            output_summary=summary,
            output_text=partial_output,
            model_id=self._model_id,
            provider=self._provider,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            is_streaming=True,
            stream_status="error",
            error=error,
            error_type=error_type,
            data_lineage={"stream_open_event_id": self._open_event_id},
        )

        self._is_closed = True
        self._logger.log_audit_event(event)
        return event
