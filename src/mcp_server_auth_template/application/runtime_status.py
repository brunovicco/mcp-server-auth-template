"""Process-local runtime readiness state."""

from dataclasses import dataclass, field
from threading import Lock


@dataclass(slots=True)
class RuntimeStatus:
    """Track whether this worker has completed MCP runtime startup."""

    _ready: bool = False
    _lock: Lock = field(default_factory=Lock, repr=False)

    def is_ready(self) -> bool:
        """Return whether this worker is ready to accept MCP traffic."""
        with self._lock:
            return self._ready

    def mark_ready(self) -> None:
        """Mark this worker ready after the MCP lifespan has started."""
        with self._lock:
            self._ready = True

    def mark_not_ready(self) -> None:
        """Mark this worker not ready before runtime resources are released."""
        with self._lock:
            self._ready = False
