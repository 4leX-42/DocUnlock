"""Office cleaning for OOXML (docx/xlsx/pptx) and encrypted OLE containers.

An OOXML file is a ZIP of XML parts. Edit protection lives in a handful of
parts as plain elements/attributes; removing them unlocks editing without
touching content. Metadata lives in docProps/core.xml and docProps/app.xml.

A file that is a CFB/OLE container ('ole' kind) is either legacy binary
Office or an OOXML file wrapped in password encryption. We decrypt it with
the supplied password via msoffcrypto, then clean the recovered OOXML.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from core.result import FileResult, Status
from processors.base import Processor

# Elements/attributes that lock editing, per part prefix.
_PROTECTION_PATTERNS = (
    re.compile(rb"<w:documentProtection\b[^>]*/>"),
    re.compile(rb"<w:writeProtection\b[^>]*/>"),
    re.compile(rb"<w:writeProtection\b[^>]*>.*?</w:writeProtection>", re.S),
    re.compile(rb"<sheetProtection\b[^>]*/>"),
    re.compile(rb"<workbookProtection\b[^>]*/>"),
    re.compile(rb"<fileSharing\b[^>]*/>"),
    re.compile(rb"<p:modifyVerifier\b[^>]*/>"),
)

# Parts whose body we blank out to clear metadata.
_META_PARTS = ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml")


class OfficeProcessor(Processor):
    kinds = ("docx", "xlsx", "pptx", "ole")

    def process(self, src, dst, result, password):
        source = src
        tmp: Path | None = None

        if result.kind == "ole":
            decrypted = self._decrypt_ole(src, dst, result, password)
            if decrypted is None:
                return  # status already set (NEEDS_PASSWORD / ERROR)
            source, tmp = decrypted, decrypted

        try:
            self._clean_ooxml(source, dst, result)
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink()

        result.output = dst
        result.status = Status.OK
        if not result.actions:
            result.add("sin protecciones detectadas")

    # -- OLE / encrypted ---------------------------------------------------
    def _decrypt_ole(self, src, dst, result, password) -> Path | None:
        try:
            import msoffcrypto
        except ImportError:
            result.status = Status.ERROR
            result.message = "Falta msoffcrypto-tool para archivos cifrados."
            return None

        with src.open("rb") as fh:
            office = msoffcrypto.OfficeFile(fh)
            if not office.is_encrypted():
                # CFB but not encrypted: legacy binary .doc/.xls, not OOXML.
                result.status = Status.SKIPPED
                result.message = (
                    "Formato binario antiguo (.doc/.xls) sin cifrar. "
                    "Conviertelo a formato moderno para procesarlo."
                )
                return None
            if not password:
                result.status = Status.NEEDS_PASSWORD
                result.message = "Office cifrado. Indica la contrasena."
                return None
            try:
                office.load_key(password=password)
            except Exception:
                result.status = Status.NEEDS_PASSWORD
                result.message = "Contrasena incorrecta."
                return None

            tmp = dst.with_suffix(dst.suffix + ".dec.tmp")
            with tmp.open("wb") as out:
                office.decrypt(out)

        result.add("descifrado")
        return tmp

    # -- OOXML -------------------------------------------------------------
    def _clean_ooxml(self, src: Path, dst: Path, result: FileResult) -> None:
        protection_hits = 0
        meta_hits = 0
        buffer = io.BytesIO()

        with zipfile.ZipFile(src) as zin:
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)

                    if item.filename in _META_PARTS:
                        data, changed = self._blank_metadata(item.filename, data)
                        meta_hits += changed
                    else:
                        data, n = self._strip_protection(data)
                        protection_hits += n

                    zout.writestr(item, data)

        with dst.open("wb") as out:
            out.write(buffer.getvalue())

        if protection_hits:
            result.add(f"proteccion de edicion quitada ({protection_hits})")
        if meta_hits:
            result.add("metadatos borrados")

    @staticmethod
    def _strip_protection(data: bytes) -> tuple[bytes, int]:
        total = 0
        for pattern in _PROTECTION_PATTERNS:
            data, n = pattern.subn(b"", data)
            total += n
        return data, total

    @staticmethod
    def _blank_metadata(name: str, data: bytes) -> tuple[bytes, int]:
        # Keep the root element so the part stays valid; drop its children.
        if name.endswith("core.xml"):
            root = b"cp:coreProperties"
        elif name.endswith("app.xml"):
            root = b"Properties"
        else:
            root = b"Properties"
        m = re.search(rb"(<" + root + rb"\b[^>]*>).*(</" + root + rb">)", data, re.S)
        if not m:
            return data, 0
        rebuilt = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        rebuilt += m.group(1) + m.group(2)
        return rebuilt, 1
