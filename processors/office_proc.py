"""Office cleaning for OOXML (docx/xlsx/pptx) and encrypted OLE containers.

An OOXML file is a ZIP of XML parts. Edit protection lives in a handful of
parts as plain elements/attributes; removing them unlocks editing without
touching content. Metadata lives in docProps/core.xml and docProps/app.xml.

A file that is a CFB/OLE container ('ole' kind) is either legacy binary
Office or an OOXML file wrapped in password encryption. We decrypt it with
the supplied password via msoffcrypto, then clean the recovered OOXML.
With options.passwords off, the pipeline encrypts the result again with the
same password once every other step (compression included) is done.
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

    def process(self, src, dst, result, password, options):
        source = src
        tmp: Path | None = None

        if result.kind == "ole":
            decrypted = self._decrypt_ole(src, dst, result, password)
            if decrypted is None:
                return  # status already set (NEEDS_PASSWORD / SKIPPED / ERROR)
            source, tmp = decrypted, decrypted
            if options.passwords:
                result.add("contraseña quitada")
            else:
                result.relock = password
            if not zipfile.is_zipfile(decrypted):
                # Encrypted legacy binary .doc/.xls/.ppt: hand back the
                # decrypted file; its protection flags are not OOXML parts.
                decrypted.replace(dst)
                result.relock = None  # msoffcrypto cannot re-encrypt these
                result.add("binario antiguo: solo descifrado")
                result.output = dst
                result.status = Status.OK
                return

        try:
            self._clean_ooxml(source, dst, result, options)
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink()

        result.output = dst
        result.status = Status.OK
        if not result.actions:
            result.add("nada que quitar")

    @staticmethod
    def encrypt(path: Path, password: str) -> None:
        """Encrypt an OOXML file in place with `password` (ECMA-376 agile)."""
        from msoffcrypto.format.ooxml import OOXMLFile

        tmp = path.with_suffix(path.suffix + ".enc.tmp")
        try:
            with path.open("rb") as fin, tmp.open("wb") as fout:
                OOXMLFile(fin).encrypt(password, fout)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)

    # -- OLE / encrypted ---------------------------------------------------
    def _decrypt_ole(self, src, dst, result, password) -> Path | None:
        try:
            import msoffcrypto
        except ImportError:
            result.status = Status.ERROR
            result.message = "Falta msoffcrypto-tool (cifrado)"
            return None

        with src.open("rb") as fh:
            office = msoffcrypto.OfficeFile(fh)
            if not office.is_encrypted():
                # CFB but not encrypted: legacy binary .doc/.xls, not OOXML.
                result.status = Status.SKIPPED
                result.message = "Binario antiguo sin cifrar: convertir a .docx/.xlsx/.pptx"
                return None
            if not password:
                result.status = Status.NEEDS_PASSWORD
                result.message = "Cifrado: falta contraseña de apertura"
                return None
            # A wrong password may pass load_key and only fail in decrypt(),
            # so both steps count as "wrong password", and the temp goes.
            tmp = dst.with_suffix(dst.suffix + ".dec.tmp")
            try:
                office.load_key(password=password, verify_password=True)
                with tmp.open("wb") as out:
                    office.decrypt(out)
            except Exception:
                tmp.unlink(missing_ok=True)
                result.status = Status.NEEDS_PASSWORD
                result.message = "Contraseña incorrecta"
                return None

        result.add("descifrado")
        return tmp

    # -- OOXML -------------------------------------------------------------
    def _clean_ooxml(self, src: Path, dst: Path, result: FileResult, options) -> None:
        protection_hits = 0
        meta_hits = 0
        buffer = io.BytesIO()

        with zipfile.ZipFile(src) as zin:
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)

                    if item.filename in _META_PARTS:
                        if options.metadata:
                            data, changed = self._blank_metadata(item.filename, data)
                            meta_hits += changed
                    elif options.protection:
                        data, n = self._strip_protection(data)
                        protection_hits += n

                    zout.writestr(item, data)

        with dst.open("wb") as out:
            out.write(buffer.getvalue())

        if protection_hits:
            result.add(f"protección quitada ({protection_hits})")
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
