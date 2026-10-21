"""Abstract processor contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.result import FileResult


class Processor(ABC):
    """Handles one or more document kinds.

    A processor never writes over the source. It reads `src` and writes the
    cleaned document to `dst`, recording what it did on `result`.
    """

    kinds: tuple[str, ...] = ()

    def handles(self, kind: str) -> bool:
        return kind in self.kinds

    @abstractmethod
    def process(
        self, src: Path, dst: Path, result: FileResult, password: str | None
    ) -> None:
        ...
