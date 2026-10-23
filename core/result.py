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


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            text = f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            return text.replace(".", ",")
        size /= 1024
    return f"{size:.1f} GB".replace(".", ",")


@dataclass
class FileResult:
    """Outcome of processing a single document."""

    source: Path
    output: Path | None = None
    status: Status = Status.SKIPPED
    kind: str = "unknown"
    actions: list[str] = field(default_factory=list)
    message: str = ""
    size_before: int = 0
    size_after: int = 0
    # Set when the user kept passwords: the PDF was saved with its original
    # encryption (`locked`), or the Office file must be re-encrypted with
    # this password after every other step (`relock`).
    locked: bool = False
    relock: str | None = field(default=None, repr=False)

    def add(self, action: str) -> None:
        self.actions.append(action)

    @property
    def actions_text(self) -> str:
        if not self.actions:
            return "-"
        text = " · ".join(self.actions)
        return text[0].upper() + text[1:]

    @property
    def size_text(self) -> str:
        if not self.size_after:
            return human_size(self.size_before) if self.size_before else "-"
        text = f"{human_size(self.size_before)} → {human_size(self.size_after)}"
        if self.size_before and self.size_after != self.size_before:
            delta = round(100 * (self.size_after - self.size_before) / self.size_before)
            text += f" ({delta:+d}%)"
        return text
