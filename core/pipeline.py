"""Batch orchestration: detect, route to a processor, write to output dir."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from core.detect import detect
from core.result import FileResult, Status
from processors.base import Processor
from processors.office_proc import OfficeProcessor
from processors.pdf_proc import PdfProcessor

SUPPORTED_EXT = {".pdf", ".docx", ".xlsm", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}

ProgressFn = Callable[[FileResult], None]


class Pipeline:
    def __init__(self, processors: list[Processor] | None = None) -> None:
        self.processors = processors or [PdfProcessor(), OfficeProcessor()]

    def _route(self, kind: str) -> Processor | None:
        for proc in self.processors:
            if proc.handles(kind):
                return proc
        return None

    def gather(self, paths: Iterable[Path]) -> list[Path]:
        """Expand folders into their supported files; keep explicit files."""
        files: list[Path] = []
        for p in paths:
            if p.is_dir():
                files.extend(
                    f for f in sorted(p.rglob("*"))
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
                )
            elif p.is_file():
                files.append(p)
        return files

    def run(
        self,
        paths: Iterable[Path],
        out_dir: Path,
        password: str | None = None,
        progress: ProgressFn | None = None,
    ) -> list[FileResult]:
        out_dir.mkdir(parents=True, exist_ok=True)
        results: list[FileResult] = []

        for src in self.gather(paths):
            result = FileResult(source=src)
            result.kind = detect(src)
            dst = self._unique_dst(out_dir, src)

            proc = self._route(result.kind)
            if proc is None:
                result.status = Status.SKIPPED
                result.message = f"Formato no soportado ({result.kind})."
            else:
                try:
                    proc.process(src, dst, result, password)
                except Exception as exc:  # keep the batch going
                    result.status = Status.ERROR
                    result.message = str(exc)
                    if dst.exists():
                        dst.unlink(missing_ok=True)

            results.append(result)
            if progress is not None:
                progress(result)

        return results

    @staticmethod
    def _unique_dst(out_dir: Path, src: Path) -> Path:
        dst = out_dir / src.name
        i = 1
        while dst.exists():
            dst = out_dir / f"{src.stem} ({i}){src.suffix}"
            i += 1
        return dst
