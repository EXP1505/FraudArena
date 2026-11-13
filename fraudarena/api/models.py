"""Owner: M2. Pydantic request/response models derived from fa.contracts."""
from __future__ import annotations

from fa.contracts import Decision, Event  # re-exported for route modules

__all__ = ["Event", "Decision"]
