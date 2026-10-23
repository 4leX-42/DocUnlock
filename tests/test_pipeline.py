"""End-to-end checks on synthetic documents. Run: python -m unittest -v

Builds every fixture on the fly (no real documents in the repo): a protected
docx with a heavy photo, the same docx password-encrypted with msoffcrypto,
a PDF with an open password, a PDF with owner-only permissions and a 300 dpi
"scan", and a folder with duplicate names in subfolders.
"""
from __future__ import annotations

import io
import random
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pikepdf  # noqa: E402
from PIL import Image  # noqa: E402

from core.options import Options  # noqa: E402
from core.pipeline import Pipeline  # noqa: E402
from core.result import Status  # noqa: E402

PW = "Prueba-2026"


def _photo(w: int, h: int) -> Image.Image:
    """Noisy gradient: compresses like a real photo/scan, not like flat colour."""
    rnd = random.Random(42)
    img = Image.linear_gradient("L").resize((w, h)).convert("RGB")
    noise = Image.frombytes("RGB", (w, h), rnd.randbytes(w * h * 3))
    return Image.blend(img, noise, 0.35)


def _docx(path: Path) -> None:
    jpg = io.BytesIO()
    _photo(4000, 3000).save(jpg, "JPEG", quality=95)
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="jpeg" ContentType="image/jpeg"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Contenido intacto</w:t></w:r></w:p></w:body></w:document>"
        ),
        "word/settings.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:writeProtection w:recommended="1"/>'
            '<w:documentProtection w:edit="readOnly" w:enforcement="1"/>'
            "</w:settings>"
        ),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:creator>Autor Secreto</dc:creator></cp:coreProperties>"
        ),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            zf.writestr(name, text)
        zf.writestr("word/media/image1.jpeg", jpg.getvalue())


def _scan_pdf(path: Path, pages: int = 2) -> None:
    imgs = [_photo(2480, 3508) for _ in range(pages)]  # A4 at 300 dpi
    imgs[0].save(path, "PDF", resolution=300, save_all=True,
                 append_images=imgs[1:], quality=95)


ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")


def _text_pdf(path: Path) -> None:
    """One page of text in a fully embedded simple TrueType font, the way
    Word exports Calibri/Arial."""
    with pikepdf.new() as p:
        data = ARIAL.read_bytes()
        ff = pikepdf.Stream(p, data)
        ff.Length1 = len(data)
        desc = p.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.FontDescriptor, FontName=pikepdf.Name("/ABCDEE+Arial"),
            Flags=32, FontBBox=[-665, -325, 2000, 1040], ItalicAngle=0,
            Ascent=905, Descent=-212, CapHeight=716, StemV=80, FontFile2=ff,
        ))
        font = p.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Font, Subtype=pikepdf.Name.TrueType,
            BaseFont=pikepdf.Name("/ABCDEE+Arial"), Encoding=pikepdf.Name.WinAnsiEncoding,
            FirstChar=32, LastChar=126, Widths=[556] * 95, FontDescriptor=desc,
        ))
        page = p.add_blank_page()
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.Contents = p.make_stream(b"BT /F1 24 Tf 72 720 Td (Hola mundo) Tj ET")
        p.save(path)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "in"
        self.src.mkdir()
        self.out = self.dir / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *paths, **kw):
        return Pipeline().run(list(paths), self.out, **kw)

    def test_docx_protection_and_metadata(self):
        doc = self.src / "protegido.docx"
        _docx(doc)
        [r] = self._run(doc)
        self.assertIs(r.status, Status.OK, r.message)
        with zipfile.ZipFile(r.output) as zf:
            settings = zf.read("word/settings.xml")
            self.assertNotIn(b"documentProtection", settings)
            self.assertNotIn(b"writeProtection", settings)
            self.assertNotIn(b"Autor Secreto", zf.read("docProps/core.xml"))
            self.assertIn(b"Contenido intacto", zf.read("word/document.xml"))
        self.assertGreater(doc.stat().st_size, 0)  # original untouched

    def test_encrypted_docx(self):
        from msoffcrypto.format.ooxml import OOXMLFile

        plain = self.dir / "plain.docx"
        _docx(plain)
        enc = self.src / "cifrado.docx"
        with plain.open("rb") as fin, enc.open("wb") as fout:
            OOXMLFile(fin).encrypt(PW, fout)

        [r] = self._run(enc)
        self.assertIs(r.status, Status.NEEDS_PASSWORD)

        [r] = Pipeline().run([enc], self.out, password="mala")
        self.assertIs(r.status, Status.NEEDS_PASSWORD)
        self.assertIn("incorrecta", r.message)

        [r] = Pipeline().run([enc], self.out, password=PW)
        self.assertIs(r.status, Status.OK, r.message)
        self.assertIn("descifrado", r.actions)
        with zipfile.ZipFile(r.output) as zf:
            self.assertNotIn(b"documentProtection", zf.read("word/settings.xml"))
        self.assertEqual(list(self.out.glob("*.tmp")), [])

    def test_pdf_open_password(self):
        pdf = self.src / "cerrado.pdf"
        with pikepdf.new() as p:
            p.add_blank_page()
            p.docinfo["/Author"] = "Autor Secreto"
            p.save(pdf, encryption=pikepdf.Encryption(owner="dueno", user=PW))

        [r] = self._run(pdf)
        self.assertIs(r.status, Status.NEEDS_PASSWORD)
        self.assertFalse(any(self.out.iterdir()))  # nothing half-written

        [r] = Pipeline().run([pdf], self.out, password=PW)
        self.assertIs(r.status, Status.OK, r.message)
        with pikepdf.open(r.output) as p:
            self.assertFalse(p.is_encrypted)
            self.assertNotIn("/Info", p.trailer)

    def test_pdf_owner_permissions(self):
        pdf = self.src / "permisos.pdf"
        _scan_pdf(self.dir / "plain.pdf", pages=1)
        with pikepdf.open(self.dir / "plain.pdf") as p:
            p.save(pdf, encryption=pikepdf.Encryption(
                owner="dueno", user="",
                allow=pikepdf.Permissions(extract=False, modify_other=False),
            ))
        [r] = self._run(pdf)
        self.assertIs(r.status, Status.OK, r.message)
        with pikepdf.open(r.output) as p:
            self.assertFalse(p.is_encrypted)

    def test_compress_pdf(self):
        pdf = self.src / "escaneo.pdf"
        _scan_pdf(pdf)
        [r] = self._run(pdf, options=Options(compress="ebook"))
        self.assertIs(r.status, Status.OK, r.message)
        self.assertLess(r.size_after, r.size_before * 0.6, r.actions_text)
        with pikepdf.open(r.output) as p:
            self.assertEqual(len(p.pages), 2)
            self.assertNotIn("/Info", p.trailer)  # compression adds no Producer
            self.assertNotIn("/Metadata", p.Root)

    def test_compress_docx_images(self):
        doc = self.src / "fotos.docx"
        _docx(doc)
        [r] = self._run(doc, options=Options(compress="ebook"))
        self.assertIs(r.status, Status.OK, r.message)
        self.assertLess(r.size_after, r.size_before, r.actions_text)
        with zipfile.ZipFile(r.output) as zf:
            img = Image.open(io.BytesIO(zf.read("word/media/image1.jpeg")))
            self.assertEqual(img.format, "JPEG")
            self.assertLessEqual(max(img.size), 1920)

    def test_folder_layout_and_rerun(self):
        for sub in ("a", "b"):
            (self.src / sub).mkdir()
            _docx(self.src / sub / "factura.docx")
        out = self.src / "DocUnlock_out"  # output inside the input folder

        first = Pipeline().run([self.src], out)
        self.assertEqual(len(first), 2)
        self.assertTrue((out / "a" / "factura.docx").is_file())
        self.assertTrue((out / "b" / "factura.docx").is_file())

        second = Pipeline().run([self.src], out)  # must not eat its own output
        self.assertEqual(len(second), 2)
        self.assertTrue((out / "a" / "factura (1).docx").is_file())

    def test_keep_passwords_pdf(self):
        pdf = self.src / "cerrado.pdf"
        with pikepdf.new() as p:
            p.add_blank_page()
            p.docinfo["/Author"] = "Autor Secreto"
            p.save(pdf, encryption=pikepdf.Encryption(owner="dueno", user=PW))
        opts = Options(passwords=False)
        [r] = Pipeline().run([pdf], self.out, password=PW, options=opts)
        self.assertIs(r.status, Status.OK, r.message)
        with self.assertRaises(pikepdf.PasswordError):
            pikepdf.open(r.output)  # still asks for the password
        with pikepdf.open(r.output, password=PW) as p:
            self.assertNotIn("/Author", p.docinfo)  # but metadata went

    def test_keep_passwords_docx(self):
        from msoffcrypto.format.ooxml import OOXMLFile

        plain = self.dir / "plain.docx"
        _docx(plain)
        enc = self.src / "cifrado.docx"
        with plain.open("rb") as fin, enc.open("wb") as fout:
            OOXMLFile(fin).encrypt(PW, fout)
        opts = Options(passwords=False, metadata=False)
        [r] = Pipeline().run([enc], self.out, password=PW, options=opts)
        self.assertIs(r.status, Status.OK, r.message)

        import msoffcrypto

        with r.output.open("rb") as fh:
            office = msoffcrypto.OfficeFile(fh)
            self.assertTrue(office.is_encrypted())
            office.load_key(password=PW)
            clear = io.BytesIO()
            office.decrypt(clear)
        with zipfile.ZipFile(clear) as zf:
            self.assertNotIn(b"documentProtection", zf.read("word/settings.xml"))
            self.assertIn(b"Autor Secreto", zf.read("docProps/core.xml"))

    def test_compress_only(self):
        doc = self.src / "fotos.docx"
        _docx(doc)
        opts = Options(metadata=False, signatures=False, protection=False,
                       passwords=False, compress="ebook")
        [r] = self._run(doc, options=opts)
        self.assertIs(r.status, Status.OK, r.message)
        with zipfile.ZipFile(r.output) as zf:
            self.assertIn(b"documentProtection", zf.read("word/settings.xml"))
            self.assertIn(b"Autor Secreto", zf.read("docProps/core.xml"))
        self.assertLess(r.size_after, r.size_before)

    @unittest.skipUnless(ARIAL.is_file(), "Arial no disponible")
    def test_compress_pdf_subsets_full_font(self):
        pdf = self.src / "word.pdf"
        _text_pdf(pdf)
        [r] = self._run(pdf, options=Options(compress="ebook"))
        self.assertIs(r.status, Status.OK, r.message)
        self.assertLess(r.size_after, r.size_before * 0.5, r.actions_text)
        from fontTools.ttLib import TTFont

        with pikepdf.open(r.output) as p:
            font = p.pages[0].Resources.Font.F1
            tt = TTFont(io.BytesIO(font.FontDescriptor.FontFile2.read_bytes()))
            glyf = tt["glyf"]
            for ch in "Hola":  # glyphs of every code survive, ids unchanged
                self.assertGreater(glyf[tt.getBestCmap()[ord(ch)]].numberOfContours, 0)
            self.assertIn(b"Hola", p.pages[0].Contents.read_bytes())

    def test_compress_pdf_dedupes_and_keeps_password(self):
        pdf = self.src / "repetido.pdf"
        _scan_pdf(self.dir / "plain.pdf", pages=3)  # three identical pages
        with pikepdf.open(self.dir / "plain.pdf") as p:
            p.save(pdf, encryption=pikepdf.Encryption(owner="dueno", user=PW))
        opts = Options(passwords=False, compress="ebook")
        [r] = Pipeline().run([pdf], self.out, password=PW, options=opts)
        self.assertIs(r.status, Status.OK, r.message)
        with pikepdf.open(r.output, password=PW) as p:
            self.assertTrue(p.is_encrypted)
            images = {pg.Resources.XObject[k].objgen
                      for pg in p.pages for k in pg.Resources.XObject.keys()}
            self.assertEqual(len(images), 1)
        self.assertLess(r.size_after, r.size_before * 0.2, r.actions_text)

    def test_legacy_and_unknown(self):
        (self.src / "nota.pdf").write_bytes(b"no soy un pdf")
        [r] = self._run(self.src / "nota.pdf")
        self.assertIs(r.status, Status.SKIPPED)


if __name__ == "__main__":
    unittest.main()
