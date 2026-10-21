"""Per-file processing result model."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    OK = "OK"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    NEEDS_PASSWORD = "NEEDS_PASSWORD"


@dataclass
class FileResult:
    """Outcome of processing a single document."""

    source: Path
    output: Path | None = None
    status: Status = Status.SKIPPED
    kind: str = "unknown"
    actions: list[str] = field(default_factory=list)
    message: str = ""

    def add(self, action: str) -> None:
        self.actions.append(action)

    @property
    def actions_text(self) -> str:
        return ", ".join(self.actions) if self.actions else "-"
