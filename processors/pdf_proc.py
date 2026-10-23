"""PDF cleaning: drop encryption/permissions, signatures and metadata.

Uses pikepdf (QPDF). Opening a PDF whose only protection is an owner
password (permission flags, no open password) and saving it again drops
those permissions. If the PDF needs an open password, the caller-supplied
password is used; without it the file is reported as NEEDS_PASSWORD.

With options.passwords off, the original encryption is written back
(save(encryption=True)), so the copy asks for the same password and keeps
the same permission flags.
"""
from __future__ import annotations

import pikepdf

from core.result import FileResult, Status
from processors.base import Processor


class PdfProcessor(Processor):
    kinds = ("pdf",)

    def process(self, src, dst, result, password, options):
        try:
            pdf = pikepdf.open(src, password=password or "")
        except pikepdf.PasswordError:
            result.status = Status.NEEDS_PASSWORD
            result.message = "Cifrado: falta contraseña de apertura"
            return

        with pdf:
            keep_lock = pdf.is_encrypted and not options.passwords
            if pdf.is_encrypted and options.passwords:
                result.add("cifrado y permisos quitados")
            if keep_lock:
                result.locked = True
            if options.signatures:
                self._strip_signatures(pdf, result)
            if options.metadata:
                self._strip_metadata(pdf, result)

            # Saving without encrypt= drops all encryption and permissions;
            # encryption=True copies the original settings back.
            pdf.save(dst, fix_metadata_version=True, encryption=keep_lock)

        result.output = dst
        result.status = Status.OK
        if not result.actions:
            result.add("nada que quitar")

    @staticmethod
    def _is_signature(fld) -> bool:
        if fld.get("/FT") == pikepdf.Name("/Sig"):
            return True
        value = fld.get("/V")
        return (
            isinstance(value, pikepdf.Dictionary)
            and value.get("/Type") == pikepdf.Name("/Sig")
        )

    @staticmethod
    def _strip_signatures(pdf: pikepdf.Pdf, result: FileResult) -> None:
        root = pdf.Root
        acro = root.get("/AcroForm")
        if acro is None:
            return

        fields = acro.get("/Fields")
        removed = 0
        if fields is not None:
            kept = []
            for fld in list(fields):
                if PdfProcessor._is_signature(fld):
                    removed += 1
                    continue
                kept.append(fld)
            acro["/Fields"] = pikepdf.Array(kept)

        # Clear the signature flags and any certification (DocMDP) perms.
        if "/SigFlags" in acro:
            acro["/SigFlags"] = 0
        if "/Perms" in root:
            del root["/Perms"]
            removed += 1

        # Sweep the page-level widget annotations that rendered those sigs,
        # otherwise Acrobat warns about unreachable form widgets.
        for page in pdf.pages:
            annots = page.get("/Annots")
            if annots is None:
                continue
            kept = [a for a in annots if not PdfProcessor._is_signature(a)]
            if len(kept) != len(annots):
                page["/Annots"] = pikepdf.Array(kept)

        if removed:
            result.add(f"firmas quitadas ({removed})")

    @staticmethod
    def _strip_metadata(pdf: pikepdf.Pdf, result: FileResult) -> None:
        if strip_metadata(pdf):
            result.add("metadatos borrados")


def strip_metadata(pdf: pikepdf.Pdf) -> bool:
    """Drop DocInfo and the XMP stream. Returns True if anything was there."""
    touched = False
    if "/Info" in pdf.trailer:
        del pdf.trailer["/Info"]  # DocInfo dictionary
        touched = True
    if "/Metadata" in pdf.Root:
        del pdf.Root["/Metadata"]  # XMP stream
        touched = True
    return touched
