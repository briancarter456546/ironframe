# ============================================================================
# ironframe/audit/writer_v1_0.py - v1.0
# Last updated: 2026-04-15
# ============================================================================
# C27: append-only audit transport.
#
# Up to C26.1b the authoritative audit store was a file Claude could write
# directly (output/ironframe/audit.jsonl). C23 detected post-hoc tampering
# at export time, but the writer itself was trusted. C27 moves the
# canonical record to a destination Claude cannot alter: a collector
# running on a separate host as a separate OS user.
#
# Three backends:
#   LocalFileWriter    -- appends to a local JSONL file. Dev default and
#                         the advisory cache when the collector is down.
#   HttpCollectorWriter -- HMAC-signs each event and POSTs it to the
#                          collector's /append endpoint. File-backed
#                          bounded buffer on failure; drains when
#                          connectivity returns.
#   DualWriter         -- writes to both. Default production mode.
#
# Configuration via environment variables:
#   IRONFRAME_AUDIT_WRITER = local | http | dual
#   IRONFRAME_COLLECTOR_URL
#   IRONFRAME_COLLECTOR_HMAC_KEY
#   IRONFRAME_COLLECTOR_TIMEOUT_SECONDS   (default 1.5)
#   IRONFRAME_COLLECTOR_BUFFER_PATH
#   IRONFRAME_COLLECTOR_BUFFER_MAX        (default 100_000)
# ============================================================================

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


DEFAULT_LOCAL_PATH = Path("output/ironframe/audit.jsonl")
DEFAULT_BUFFER_PATH = Path("output/ironframe/audit_buffer.jsonl")
DEFAULT_BUFFER_MAX = 100_000
DEFAULT_TIMEOUT_SECONDS = 1.5


def _canonical_json(body: Dict[str, Any]) -> str:
    """Byte-stable JSON encoding, same shape as C23 uses for per-event SHA."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hmac_sign(key: str, body: str) -> str:
    if not key:
        return ""
    return hmac.new(
        key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class AppendOnlyWriter(ABC):
    """Append a single audit event to an append-only destination."""

    @abstractmethod
    def append(self, event: Dict[str, Any]) -> None:
        """Append one event. MUST NOT raise; fail-graceful is the contract."""
        raise NotImplementedError


class LocalFileWriter(AppendOnlyWriter):
    """Append a JSON line to a local file. Thread-safe, fail-graceful."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else DEFAULT_LOCAL_PATH
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: Dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event, ensure_ascii=True)
            with self._lock:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                    fh.flush()
        except Exception:
            return


@dataclass
class HttpCollectorConfig:
    url: str = ""
    hmac_key: str = ""
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    buffer_path: Path = field(default_factory=lambda: DEFAULT_BUFFER_PATH)
    buffer_max_lines: int = DEFAULT_BUFFER_MAX


class HttpCollectorWriter(AppendOnlyWriter):
    """POST each event to the collector. Buffer on failure, drain on success.

    The buffer is a local JSONL file. It is explicitly the known tamper-
    vulnerable cache: divergence between the buffer and the collector's
    canonical file is itself a tamper signal.
    """

    def __init__(self, config: HttpCollectorConfig, opener=None) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._opener = opener

    @property
    def config(self) -> HttpCollectorConfig:
        return self._cfg

    def _post(self, body: str, signature: str) -> bool:
        if not self._cfg.url:
            return False
        req = urllib_request.Request(
            self._cfg.url,
            data=body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Ironframe-Signature": signature,
            },
        )
        try:
            opener = self._opener or urllib_request
            resp = opener.urlopen(req, timeout=self._cfg.timeout_seconds)
            status = getattr(resp, "status", None) or resp.getcode()
            return 200 <= int(status) < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False
        except Exception:
            return False

    @staticmethod
    def _line_count(path: Path) -> int:
        n = 0
        with path.open("r", encoding="utf-8") as fh:
            for _ in fh:
                n += 1
        return n

    @staticmethod
    def _truncate_front(path: Path, keep_last: int) -> None:
        if keep_last <= 0:
            path.write_text("", encoding="utf-8")
            return
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        keep = lines[-keep_last:] if keep_last < len(lines) else lines
        with path.open("w", encoding="utf-8") as fh:
            fh.writelines(keep)

    def _append_to_buffer(self, event: Dict[str, Any]) -> None:
        try:
            self._cfg.buffer_path.parent.mkdir(parents=True, exist_ok=True)
            if self._cfg.buffer_path.exists() and self._cfg.buffer_max_lines > 0:
                try:
                    size = self._line_count(self._cfg.buffer_path)
                except Exception:
                    size = 0
                if size >= self._cfg.buffer_max_lines:
                    self._truncate_front(
                        self._cfg.buffer_path,
                        keep_last=self._cfg.buffer_max_lines - 1,
                    )
            line = json.dumps(event, ensure_ascii=True)
            with self._cfg.buffer_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        except Exception:
            return

    def _drain_buffer(self) -> int:
        """Try to ship buffered events. Returns count successfully sent."""
        if not self._cfg.buffer_path.exists():
            return 0
        try:
            with self._cfg.buffer_path.open("r", encoding="utf-8") as fh:
                lines = [l for l in fh.readlines() if l.strip()]
        except Exception:
            return 0

        shipped = 0
        remaining_start = len(lines)  # assume we drain everything unless broken
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            try:
                ev = json.loads(line)
            except Exception:
                # Corrupt line: skip it, keep moving.
                idx += 1
                continue
            body_str = _canonical_json(ev)
            sig = _hmac_sign(self._cfg.hmac_key, body_str)
            if self._post(body_str, sig):
                shipped += 1
                idx += 1
            else:
                remaining_start = idx
                break

        remaining = [
            l if l.endswith("\n") else l + "\n"
            for l in lines[remaining_start:]
        ]
        try:
            with self._cfg.buffer_path.open("w", encoding="utf-8") as fh:
                fh.writelines(remaining)
        except Exception:
            pass

        return shipped

    def append(self, event: Dict[str, Any]) -> None:
        with self._lock:
            body_str = _canonical_json(event)
            sig = _hmac_sign(self._cfg.hmac_key, body_str)
            if self._post(body_str, sig):
                try:
                    self._drain_buffer()
                except Exception:
                    pass
                return
            self._append_to_buffer(event)

    def is_reachable(self) -> bool:
        """Best-effort probe. True if the URL responds in the 2xx-4xx range."""
        if not self._cfg.url:
            return False
        req = urllib_request.Request(
            self._cfg.url,
            data=b"",
            method="OPTIONS",
        )
        try:
            opener = self._opener or urllib_request
            resp = opener.urlopen(req, timeout=self._cfg.timeout_seconds)
            status = getattr(resp, "status", None) or resp.getcode()
            return 200 <= int(status) < 500
        except (HTTPError, URLError, TimeoutError, OSError):
            return False
        except Exception:
            return False


class DualWriter(AppendOnlyWriter):
    """Write to both a local file and an HTTP collector. Neither affects the other."""

    def __init__(self, local: LocalFileWriter, http: HttpCollectorWriter) -> None:
        self._local = local
        self._http = http

    @property
    def local(self) -> LocalFileWriter:
        return self._local

    @property
    def http(self) -> HttpCollectorWriter:
        return self._http

    def append(self, event: Dict[str, Any]) -> None:
        try:
            self._local.append(event)
        except Exception:
            pass
        try:
            self._http.append(event)
        except Exception:
            pass


def writer_from_env(
    env: Optional[Dict[str, str]] = None,
    local_path: Optional[Path] = None,
) -> AppendOnlyWriter:
    """Construct an AppendOnlyWriter from environment variables.

    Resolution order:
      1. Explicit IRONFRAME_AUDIT_WRITER = local | http | dual
      2. Otherwise dual if IRONFRAME_COLLECTOR_URL is set, else local.
    """
    e = env if env is not None else os.environ

    mode = (e.get("IRONFRAME_AUDIT_WRITER", "") or "").strip().lower()
    collector_url = (e.get("IRONFRAME_COLLECTOR_URL", "") or "").strip()

    if not mode:
        mode = "dual" if collector_url else "local"

    local = LocalFileWriter(path=local_path)

    if mode == "local":
        return local

    try:
        timeout = float(e.get("IRONFRAME_COLLECTOR_TIMEOUT_SECONDS",
                              str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS

    try:
        buf_max = int(e.get("IRONFRAME_COLLECTOR_BUFFER_MAX",
                            str(DEFAULT_BUFFER_MAX)))
    except ValueError:
        buf_max = DEFAULT_BUFFER_MAX

    buf_path_str = (e.get("IRONFRAME_COLLECTOR_BUFFER_PATH", "") or "").strip()
    buf_path = Path(buf_path_str) if buf_path_str else DEFAULT_BUFFER_PATH

    cfg = HttpCollectorConfig(
        url=collector_url,
        hmac_key=(e.get("IRONFRAME_COLLECTOR_HMAC_KEY", "") or "").strip(),
        timeout_seconds=timeout,
        buffer_path=buf_path,
        buffer_max_lines=buf_max,
    )
    http_w = HttpCollectorWriter(cfg)

    if mode == "http":
        return http_w
    return DualWriter(local=local, http=http_w)
