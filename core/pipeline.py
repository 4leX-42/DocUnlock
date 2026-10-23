"""Batch orchestration: detect, route to a processor, write to output dir."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from core.detect import detect
from core.options import Options
from core.result import FileResult, Status
from processors.base import Processor
from processors.compress import Compressor
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

    def gather(
        self, paths: Iterable[Path], exclude: Path | None = None
    ) -> list[tuple[Path, Path]]:
        """Expand folders into (file, path relative to output) pairs.

        Files found inside a folder keep their subfolder layout, so two
        'factura.pdf' in different subfolders do not collide. Anything under
        `exclude` (the output folder) is skipped, so a rerun over the same
        folder never reprocesses its own output.
        """
        skip = exclude.resolve() if exclude is not None else None
        files: list[tuple[Path, Path]] = []
        seen: set[Path] = set()

        def take(f: Path, rel: Path) -> None:
            real = f.resolve()
            if real in seen or (skip is not None and real.is_relative_to(skip)):
                return
            seen.add(real)
            files.append((f, rel))

        for p in paths:
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
                        take(f, f.relative_to(p))
            elif p.is_file():
                take(p, Path(p.name))
        return files

    def run(
        self,
        paths: Iterable[Path],
        out_dir: Path,
        password: str | None = None,
        progress: ProgressFn | None = None,
        options: Options | None = None,
        files: list[tuple[Path, Path]] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[FileResult]:
        """Process every file into out_dir with the steps in `options`
        (default: full cleaning, no compression). `files` takes a list
        already built by gather() so a caller that counted it first does
        not walk the folders twice. `cancelled` is checked between files:
        the file in progress always finishes, so no half-written copy is
        left behind."""
        options = options or Options()
        out_dir.mkdir(parents=True, exist_ok=True)
        compressor = Compressor(options.compress) if options.compress else None
        results: list[FileResult] = []
        if files is None:
            files = self.gather(paths, exclude=out_dir)

        for src, rel in files:
            if cancelled is not None and cancelled():
                break
            result = FileResult(source=src, size_before=src.stat().st_size)
            result.kind = detect(src)
            dst = self._unique_dst(out_dir / rel)

            proc = self._route(result.kind)
            if proc is None:
                result.status = Status.SKIPPED
                result.message = f"Formato no soportado ({result.kind})"
            else:
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    proc.process(src, dst, result, password, options)
                    if compressor is not None and result.status is Status.OK:
                        compressor.compress(dst, result.kind, result, password)
                    if result.relock and result.status is Status.OK:
                        OfficeProcessor.encrypt(dst, result.relock)
                        result.add("contraseña conservada")
                    if result.status is Status.OK:
                        result.size_after = dst.stat().st_size
                except Exception as exc:  # keep the batch going
                    result.status = Status.ERROR
                    result.message = f"Ilegible: dañado o formato desconocido ({exc})"
                    result.output = None
                    dst.unlink(missing_ok=True)

            results.append(result)
            if progress is not None:
                progress(result)

        return results

    @staticmethod
    def _unique_dst(dst: Path) -> Path:
        """Never overwrite: 'doc.pdf' becomes 'doc (1).pdf', 'doc (2).pdf'..."""
        stem, suffix = dst.stem, dst.suffix
        i = 1
        while dst.exists():
            dst = dst.with_name(f"{stem} ({i}){suffix}")
            i += 1
        return dst
