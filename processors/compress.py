"""Size reduction pass, applied in place to an already cleaned output file.

PDF stays in-process with pikepdf (QPDF) and Pillow, no external binary:
every image XObject is measured where the pages actually draw it, images
above the profile resolution are downsampled, photos are re-encoded as
JPEG and flat artwork (few colours) stays lossless. Fully embedded
TrueType fonts are cut down to the glyphs they can draw (pdf_fonts.py).
The file is then saved with recompressed streams and object streams.
Text, vectors, forms, links and metadata are left untouched, and an
encrypted PDF kept locked is written back with its original encryption.

OOXML (docx/xlsx/pptx) recompresses the JPEG/PNG images under */media/
with Pillow, keeping each file name and format so content types and
relationships stay valid.

A compressed result only replaces the file when it is actually smaller.
"""
from __future__ import annotations

import hashlib
import io
import math
import re
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from core.result import FileResult
from processors.pdf_fonts import subset_fonts


@dataclass(frozen=True)
class Profile:
    label: str        # name shown in the GUI
    pdf_dpi: int      # target resolution of PDF images, pixels per inch
    pdf_quality: int  # JPEG quality of re-encoded PDF photos
    max_side: int     # longest image side in Office media, pixels
    jpeg_quality: int


PROFILES = {
    "screen": Profile("máxima", 72, 50, 1280, 60),      # smallest
    "ebook": Profile("equilibrada", 150, 60, 1920, 75),  # readable scans
    "printer": Profile("ligera", 300, 80, 3000, 85),     # light touch
}
DEFAULT_PROFILE = "ebook"

_MEDIA = re.compile(r"^(word|xl|ppt)/media/[^/]+\.(jpe?g|png)$", re.I)

# Only downsample when the image is this much above the target, so a
# 160 ppi scan is not resampled to 150 for a negligible gain.
_DOWNSAMPLE_THRESHOLD = 1.5
# Filters whose images are left alone: bilevel scans already compress far
# better than JPEG would, and JPEG 2000 is rare and costly to round-trip.
_SKIP_FILTERS = {"/JBIG2Decode", "/CCITTFaxDecode", "/JPXDecode"}

Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(m: Matrix, n: Matrix) -> Matrix:
    """m then n, in PDF row-vector order (cm sets CTM to m x CTM)."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D,
            c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F)


def _matrix(values) -> Matrix:
    a, b, c, d, e, f = (float(v) for v in values)
    return (a, b, c, d, e, f)


def image_ppi(pdf) -> dict[tuple[int, int], float]:
    """Lowest effective resolution at which each image XObject is drawn,
    keyed by object id. Walks page content and nested Form XObjects,
    following q/Q/cm. Images drawn nowhere are absent: they are not
    resized, since their real size on the page is unknown."""
    import pikepdf

    found: dict[tuple[int, int], float] = {}

    def walk(stream, resources, ctm: Matrix, depth: int) -> None:
        if depth > 12 or resources is None:
            return
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return
        stack: list[Matrix] = []
        try:
            ops = pikepdf.parse_content_stream(stream, "q Q cm Do")
        except pikepdf.PdfError:
            return
        for operands, op in ops:
            name = str(op)
            if name == "q":
                stack.append(ctm)
            elif name == "Q":
                ctm = stack.pop() if stack else ctm
            elif name == "cm" and len(operands) == 6:
                ctm = _mul(_matrix(operands), ctm)
            elif name == "Do" and operands:
                xobj = xobjects.get(operands[0])
                if not isinstance(xobj, pikepdf.Stream):
                    continue
                kind = xobj.get("/Subtype")
                if kind == "/Image":
                    w_pt = math.hypot(ctm[0], ctm[1])
                    h_pt = math.hypot(ctm[2], ctm[3])
                    if w_pt < 0.5 or h_pt < 0.5 or xobj.objgen == (0, 0):
                        continue
                    ppi = min(int(xobj.Width) * 72 / w_pt,
                              int(xobj.Height) * 72 / h_pt)
                    found[xobj.objgen] = min(found.get(xobj.objgen, ppi), ppi)
                elif kind == "/Form":
                    m = xobj.get("/Matrix")
                    form_m = _matrix(m) if m is not None and len(m) == 6 else _IDENTITY
                    walk(xobj, xobj.get("/Resources", resources),
                         _mul(form_m, ctm), depth + 1)

    for page in pdf.pages:
        walk(page, page.obj.get("/Resources"), _IDENTITY, 0)
    return found


def _salvage(pikepdf, obj, names: set[str], cs):
    """Decode a truncated or damaged Flate image as far as it goes and
    leave the rows it cannot read white: viewers paint nothing there, so
    the white page shows through. Only for plain 8-bit Gray, RGB or
    Indexed images without a predictor."""
    from PIL import Image

    if names != {"/FlateDecode"} or "/DecodeParms" in obj:
        return None
    w, h = int(obj.Width), int(obj.Height)
    if isinstance(cs, pikepdf.Array) and str(cs[0]) == "/Indexed" and str(cs[1]) == "/DeviceRGB":
        mode, comps = "P", 1
    elif cs == pikepdf.Name.DeviceRGB:
        mode, comps = "RGB", 3
    elif cs == pikepdf.Name.DeviceGray:
        mode, comps = "L", 1
    else:
        return None
    need = w * h * comps
    raw = obj.read_raw_bytes()
    z = zlib.decompressobj()
    chunks: list[bytes] = []
    got = 0
    for i in range(0, len(raw), 65536):
        try:
            part = z.decompress(raw[i:i + 65536])
        except zlib.error:
            break
        chunks.append(part)
        got += len(part)
        if got >= need:
            break
    rows = min(h, len(b"".join(chunks)) // (w * comps))
    if rows == 0:
        return None
    part = Image.frombytes(mode, (w, rows), b"".join(chunks)[: w * comps * rows])
    if mode == "P":
        lookup = cs[3]
        table = lookup.read_bytes() if isinstance(lookup, pikepdf.Stream) else bytes(lookup)
        part.putpalette(table[: 3 * (int(cs[2]) + 1)])
        part = part.convert("RGB")
    img = Image.new(part.mode, (w, h), "white")
    img.paste(part, (0, 0))
    return img


def _dedupe_images(pikepdf, pdf) -> int:
    """Point every copy of a byte-identical image at one object. Word and
    scanners often repeat the same logo or page as separate objects."""
    def fingerprint(obj):
        meta = sorted(
            (str(k), str(v.objgen) if getattr(v, "is_indirect", False) else repr(v))
            for k, v in obj.stream_dict.items() if k != "/Length"
        )
        return hashlib.sha256(obj.read_raw_bytes()).digest(), tuple(meta)

    first: dict = {}
    remap: dict[tuple[int, int], object] = {}
    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == "/Image":
            keep = first.setdefault(fingerprint(obj), obj)
            if keep.objgen != obj.objgen:
                remap[obj.objgen] = keep
    if not remap:
        return 0
    for obj in pdf.objects:
        if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
            continue
        for holder in (obj, obj.get("/Resources")):
            xobjects = holder.get("/XObject") if isinstance(holder, pikepdf.Dictionary) else None
            if not isinstance(xobjects, pikepdf.Dictionary):
                continue
            for name, val in list(xobjects.items()):
                if val.is_indirect and val.objgen in remap:
                    xobjects[name] = remap[val.objgen]
    return len(remap)


class Compressor:
    def __init__(self, profile: str = DEFAULT_PROFILE) -> None:
        if profile not in PROFILES:
            raise ValueError(f"Perfil desconocido: {profile}")
        self.name = profile
        self.profile = PROFILES[profile]
        self.label = self.profile.label

    def compress(
        self, path: Path, kind: str, result: FileResult, password: str | None = None
    ) -> None:
        if kind == "pdf":
            self._pdf(path, result, password)
        elif kind in ("docx", "xlsx", "pptx", "ole"):
            self._ooxml(path, result)

    # -- PDF ---------------------------------------------------------------
    def _pdf(self, path: Path, result: FileResult, password: str | None) -> None:
        import pikepdf
        from PIL import Image

        tmp = path.with_suffix(".pdf.tmp")
        try:
            try:
                pdf = pikepdf.open(path, password=password or "")
            except pikepdf.PasswordError:
                result.add("no comprimido: falta contraseña")
                return
            with pdf:
                placed = image_ppi(pdf)
                shrunk = 0
                for obj in pdf.objects:
                    if (isinstance(obj, pikepdf.Stream)
                            and obj.get("/Subtype") == "/Image"
                            and obj.objgen in placed
                            and self._pdf_image(pikepdf, Image, obj, placed[obj.objgen])):
                        shrunk += 1
                fonts = subset_fonts(pdf)
                _dedupe_images(pikepdf, pdf)
                pdf.remove_unreferenced_resources()
                # encryption=True writes the original encryption back when
                # the user chose to keep the password.
                pdf.save(
                    tmp,
                    compress_streams=True,
                    recompress_flate=True,
                    object_stream_mode=pikepdf.ObjectStreamMode.generate,
                    encryption=bool(result.locked),
                )
            parts = [f"{shrunk} imágenes" if shrunk else "", f"{fonts} fuentes" if fonts else ""]
            note = ", ".join(x for x in parts if x) or "solo estructura"
            self._keep_if_smaller(path, tmp, result, note=note)
        finally:
            tmp.unlink(missing_ok=True)

    def _pdf_image(self, pikepdf, Image, obj, ppi: float) -> bool:
        """Downsample/re-encode one image XObject in place. Returns True
        when it was replaced by something smaller."""
        if obj.get("/ImageMask") or "/Decode" in obj:
            return False  # stencil masks and remapped samples: leave as is
        if isinstance(obj.get("/Mask"), pikepdf.Array):
            return False  # colour-key mask needs exact sample values
        if int(obj.get("/BitsPerComponent", 8)) != 8:
            return False
        flt = obj.get("/Filter")
        if isinstance(flt, pikepdf.Array):
            names = {str(f) for f in flt}
        else:
            names = {str(flt)} if flt is not None else set()
        if names & _SKIP_FILTERS:
            return False
        smask = obj.get("/SMask")
        if smask is not None and "/Matte" in smask:
            return False  # Matte requires mask and image of equal size

        cs = obj.get("/ColorSpace")
        try:
            img = pikepdf.PdfImage(obj).as_pil_image()
        except pikepdf.DataDecodingError:
            img = _salvage(pikepdf, obj, names, cs)
            if img is None:
                return False
        except Exception:
            return False  # unsupported colour space or filter
        indexed = isinstance(cs, pikepdf.Array) and str(cs[0]) == "/Indexed"
        if img.mode == "P":
            img = img.convert("RGB")
        if img.mode not in ("RGB", "L"):
            return False  # CMYK, Lab, alpha...: JPEG round-trip is unsafe

        target = self.profile.pdf_dpi
        size = img.size
        if ppi > target * _DOWNSAMPLE_THRESHOLD:
            k = target / ppi
            size = (max(1, round(img.width * k)), max(1, round(img.height * k)))
        resized = size != img.size
        if resized:
            img = img.resize(size, Image.Resampling.LANCZOS)

        # Flat artwork (logos, screenshots, diagrams) blurs as JPEG: keep it
        # lossless. Photos and scans become JPEG.
        if "/DCTDecode" in names or img.getcolors(256) is None:
            out = io.BytesIO()
            img.save(out, "JPEG", quality=self.profile.pdf_quality, optimize=True)
            data, new_filter = out.getvalue(), pikepdf.Name.DCTDecode
        elif resized:
            data, new_filter = zlib.compress(img.tobytes(), 9), pikepdf.Name.FlateDecode
        else:
            return False  # lossless at the same size: the flate pass covers it

        if len(data) >= len(obj.read_raw_bytes()):
            return False
        obj.write(data, filter=new_filter)
        obj.Width, obj.Height = size
        obj.BitsPerComponent = 8
        if cs is None or indexed:
            obj.ColorSpace = pikepdf.Name.DeviceRGB if img.mode == "RGB" else pikepdf.Name.DeviceGray
        if "/DecodeParms" in obj:
            del obj["/DecodeParms"]
        if resized and smask is not None:
            self._pdf_smask(pikepdf, Image, smask, size)
        return True

    @staticmethod
    def _pdf_smask(pikepdf, Image, smask, size: tuple[int, int]) -> None:
        """Bring a soft mask down to its image's new size, losslessly."""
        try:
            mask = pikepdf.PdfImage(smask).as_pil_image().convert("L")
        except Exception:
            return
        if mask.width <= size[0]:
            return
        mask = mask.resize(size, Image.Resampling.LANCZOS)
        smask.write(zlib.compress(mask.tobytes(), 9), filter=pikepdf.Name.FlateDecode)
        smask.Width, smask.Height = size
        smask.BitsPerComponent = 8
        smask.ColorSpace = pikepdf.Name.DeviceGray
        if "/DecodeParms" in smask:
            del smask["/DecodeParms"]

    # -- Office ------------------------------------------------------------
    def _ooxml(self, path: Path, result: FileResult) -> None:
        try:
            from PIL import Image
        except ImportError:
            result.add("no comprimido: falta Pillow")
            return

        buffer = io.BytesIO()
        shrunk = 0
        with zipfile.ZipFile(path) as zin:
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if _MEDIA.match(item.filename):
                        smaller = self._image(Image, data)
                        if smaller is not None:
                            data = smaller
                            shrunk += 1
                    zout.writestr(item, data)

        if not shrunk:
            result.add("sin imágenes que comprimir")
            return
        tmp = path.with_suffix(".zip.tmp")
        try:
            tmp.write_bytes(buffer.getvalue())
            self._keep_if_smaller(path, tmp, result, note=f"{shrunk} imágenes")
        finally:
            tmp.unlink(missing_ok=True)

    def _image(self, Image, data: bytes) -> bytes | None:
        try:
            img = Image.open(io.BytesIO(data))
            fmt = img.format
            img.load()
        except Exception:
            return None  # unreadable or exotic image: leave as is
        if fmt not in ("JPEG", "PNG"):
            return None

        side = self.profile.max_side
        if max(img.size) > side:
            img.thumbnail((side, side), Image.Resampling.LANCZOS)

        out = io.BytesIO()
        if fmt == "JPEG":
            if img.mode not in ("RGB", "L", "CMYK"):
                img = img.convert("RGB")
            img.save(out, "JPEG", quality=self.profile.jpeg_quality,
                     optimize=True, progressive=True)
        else:
            img.save(out, "PNG", optimize=True)
        packed = out.getvalue()
        return packed if len(packed) < len(data) else None

    # -- shared ------------------------------------------------------------
    def _keep_if_smaller(
        self, path: Path, tmp: Path, result: FileResult, note: str = ""
    ) -> None:
        before, after = path.stat().st_size, tmp.stat().st_size
        if after >= before:
            result.add("compresión sin ganancia")
            return
        tmp.replace(path)
        detail = f" ({note})" if note else ""
        result.add(f"comprimido{detail}")  # the saving itself is in size_text
