"""Format detection by magic bytes with extension fallback."""
from __future__ import annotations

import zipfile
from pathlib import Path

# OOXML part that identifies each Office format inside the ZIP container.
_OOXML_MARKERS = {
    "docx": "word/",
    "xlsx": "xl/",
    "pptx": "ppt/",
}


def detect(path: Path) -> str:
    """Return a canonical kind: pdf, docx, xlsx, pptx, ole, or unknown.

    OLE ('ole') is the legacy/encrypted Office container (.doc or an
    OOXML file wrapped in CFB encryption). The caller decides what to do.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return "unknown"

    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole"  # CFB: legacy Office or password-encrypted OOXML
    if head.startswith(b"PK\x03\x04"):
        return _sniff_ooxml(path)
    return "unknown"


def _sniff_ooxml(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return "unknown"
    for kind, marker in _OOXML_MARKERS.items():
        if any(n.startswith(marker) for n in names):
            return kind
    return "unknown"
