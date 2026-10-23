"""Shrink embedded TrueType fonts down to the glyphs a PDF can draw.

Word and most Office exports embed the *whole* font (Calibri is ~200 KB
per weight) even when they tag it as a subset (ABCDEE+Calibri). This
cuts each FontFile2 down with fontTools, keeping glyph ids unchanged
(retain_gids), so content streams, widths and CID maps stay valid and
nothing else in the file has to be rewritten.

What each font keeps:
- Simple /TrueType fonts: every glyph any of the 256 codes can reach,
  through every cmap subtable and the /Differences names. Usage is not
  parsed, so text added later through the same font still renders.
- /Type0 fonts with Identity-H/V and a CIDFontType2: the glyphs the
  content actually shows (pages, forms, annotation appearances, tiling
  patterns). Fonts in the AcroForm /DR are skipped: form fields may type
  any character into them.

A font file shared by a font this cannot reason about is left whole, and
any failure leaves that font untouched.
"""
from __future__ import annotations

import io
import logging

import pikepdf

log = logging.getLogger(__name__)

_TEXT_OPS = "q Q Tf Tj TJ ' \" Do"
_IDENTITY = ("/Identity-H", "/Identity-V")
# Tables a PDF renderer never reads: OpenType layout, colour, variations.
_DROP = ["GSUB", "GPOS", "GDEF", "BASE", "JSTF", "MATH", "kern", "DSIG",
         "morx", "feat", "COLR", "CPAL", "SVG ", "sbix", "CBDT", "CBLC",
         "fvar", "gvar", "avar", "HVAR", "MVAR", "STAT", "meta"]


def _codes2(data: bytes) -> set[int]:
    return {(data[i] << 8) | data[i + 1] for i in range(0, len(data) - 1, 2)}


def used_cids(pdf: pikepdf.Pdf) -> dict[tuple[int, int], set[int]]:
    """Codes shown with each Identity-encoded Type0 font, by font id."""
    used: dict[tuple[int, int], set[int]] = {}
    seen: set[tuple[int, int]] = set()

    def walk(stream, resources, depth: int) -> None:
        if depth > 12 or resources is None:
            return
        key = stream.objgen if isinstance(stream, pikepdf.Object) else None
        if key and key != (0, 0):
            if key in seen:
                return
            seen.add(key)
        fonts = resources.get("/Font")
        xobjects = resources.get("/XObject")
        patterns = resources.get("/Pattern")
        if patterns is not None:
            for _, pat in patterns.items():
                if isinstance(pat, pikepdf.Stream):
                    walk(pat, pat.get("/Resources", resources), depth + 1)
        try:
            ops = pikepdf.parse_content_stream(stream, _TEXT_OPS)
        except pikepdf.PdfError:
            return
        font, stack = None, []
        for operands, op in ops:
            name = str(op)
            if name == "q":
                stack.append(font)
            elif name == "Q":
                font = stack.pop() if stack else font
            elif name == "Tf" and operands:
                font = fonts.get(operands[0]) if fonts is not None else None
                if font is not None and font.get("/Subtype") != "/Type0":
                    font = None
            elif name in ("Tj", "'", '"') and operands and font is not None:
                used.setdefault(font.objgen, set()).update(_codes2(bytes(operands[-1])))
            elif name == "TJ" and operands and font is not None:
                bucket = used.setdefault(font.objgen, set())
                for item in operands[0]:
                    if isinstance(item, pikepdf.String):
                        bucket.update(_codes2(bytes(item)))
            elif name == "Do" and operands and xobjects is not None:
                xobj = xobjects.get(operands[0])
                if isinstance(xobj, pikepdf.Stream) and xobj.get("/Subtype") == "/Form":
                    walk(xobj, xobj.get("/Resources", resources), depth + 1)

    for page in pdf.pages:
        res = page.obj.get("/Resources")
        walk(page, res, 0)
        for annot in page.obj.get("/Annots", []):
            ap = annot.get("/AP") if isinstance(annot, pikepdf.Dictionary) else None
            if ap is None:
                continue
            for _, look in ap.items():
                states = [look] if isinstance(look, pikepdf.Stream) else [v for _, v in look.items()] if isinstance(look, pikepdf.Dictionary) else []
                for st in states:
                    if isinstance(st, pikepdf.Stream):
                        walk(st, st.get("/Resources", res), 1)
    return used


def _form_fonts(pdf: pikepdf.Pdf) -> set[tuple[int, int]]:
    acro = pdf.Root.get("/AcroForm")
    dr = acro.get("/DR") if acro is not None else None
    fonts = dr.get("/Font") if dr is not None else None
    return {f.objgen for _, f in fonts.items()} if fonts is not None else set()


def _simple_glyphs(tt, font) -> set[str]:
    """Every glyph a one-byte code can select in a simple TrueType font."""
    order = set(tt.getGlyphOrder())
    unis: set[int] = set()
    for c in range(256):
        unis.add(c)
        for enc in ("cp1252", "mac_roman", "latin-1"):
            try:
                unis.add(ord(bytes([c]).decode(enc)))
            except (UnicodeDecodeError, TypeError):
                pass
    names: set[str] = set()
    enc = font.get("/Encoding")
    if isinstance(enc, pikepdf.Dictionary):
        from fontTools.agl import toUnicode
        for item in enc.get("/Differences", []):
            if isinstance(item, pikepdf.Name):
                n = str(item)[1:]
                names.add(n)
                u = toUnicode(n)
                if len(u) == 1:
                    unis.add(ord(u))
    for table in tt["cmap"].tables:
        for cp, glyph in table.cmap.items():
            if cp < 256 or (cp & 0xFF00) in (0xF000, 0xF100, 0xF200) or cp in unis:
                names.add(glyph)
    return names & order


def subset_fonts(pdf: pikepdf.Pdf) -> int:
    """Subset every eligible FontFile2 in place. Returns how many shrank."""
    from fontTools import subset
    from fontTools.ttLib import TTFont

    used = used_cids(pdf)
    protected = _form_fonts(pdf)
    # font file id -> (stream, [(kind, font dict, extra)])
    files: dict[tuple[int, int], list] = {}
    blocked: set[tuple[int, int]] = set()

    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary) or obj.get("/Type") != "/Font":
            continue
        sub = obj.get("/Subtype")
        if sub == "/Type0":
            desc = obj.get("/DescendantFonts")
            cid = desc[0] if desc is not None and len(desc) else None
            fd = cid.get("/FontDescriptor") if cid is not None else None
        elif sub in ("/TrueType", "/Type1", "/MMType1", "/Type3"):
            cid, fd = None, obj.get("/FontDescriptor")
        else:
            continue
        ff = fd.get("/FontFile2") if fd is not None else None
        if not isinstance(ff, pikepdf.Stream):
            continue
        entry = files.setdefault(ff.objgen, [ff, []])
        ok = (
            obj.objgen not in protected
            and (sub == "/TrueType"
                 or (sub == "/Type0"
                     and str(obj.get("/Encoding")) in _IDENTITY
                     and cid is not None
                     and cid.get("/Subtype") == "/CIDFontType2"
                     and obj.objgen in used))
        )
        if not ok:
            blocked.add(ff.objgen)
        entry[1].append((sub, obj, cid))

    shrunk = 0
    for key, (ff, users) in files.items():
        if key in blocked:
            continue
        try:
            raw = ff.read_bytes()
            tt = TTFont(io.BytesIO(raw), lazy=False)
            order = tt.getGlyphOrder()
            keep: set[str] = set()
            simple = False
            for sub, font, cid in users:
                if sub == "/TrueType":
                    simple = True
                    keep |= _simple_glyphs(tt, font)
                    continue
                c2g = cid.get("/CIDToGIDMap")
                codes = used[font.objgen]
                if c2g is None or c2g == pikepdf.Name.Identity:
                    gids = codes
                elif isinstance(c2g, pikepdf.Stream):
                    m = c2g.read_bytes()
                    gids = {(m[2 * c] << 8) | m[2 * c + 1] for c in codes if 2 * c + 1 < len(m)}
                else:
                    raise ValueError("CIDToGIDMap")
                keep |= {order[g] for g in gids if g < len(order)}
            if len(keep) >= len(order) - 1:
                continue
            cmap = TTFont(io.BytesIO(raw))["cmap"] if simple else None

            opts = subset.Options()
            opts.retain_gids = True
            opts.notdef_outline = True
            opts.glyph_names = True
            opts.name_IDs = ["*"]
            opts.name_languages = ["*"]
            opts.name_legacy = True
            opts.layout_features = []
            opts.drop_tables = list(opts.drop_tables) + _DROP
            opts.hinting = True
            opts.legacy_kern = False
            opts.prune_unicode_ranges = False
            opts.recalc_bounds = False
            sub_ = subset.Subsetter(opts)
            sub_.populate(glyphs=sorted(keep))
            sub_.subset(tt)
            if cmap is not None:
                # Simple fonts also select glyphs through the legacy (1,0)
                # and (3,0) subtables, which the subsetter drops: put the
                # original cmap back, minus glyphs that no longer exist.
                names = set(tt.getGlyphOrder())
                for table in cmap.tables:
                    table.cmap = {cp: g for cp, g in table.cmap.items() if g in names}
                tt["cmap"] = cmap
            out = io.BytesIO()
            tt.save(out)
            data = out.getvalue()
        except Exception:
            log.debug("font %s left whole", key, exc_info=True)
            continue
        if len(data) >= len(raw):
            continue
        ff.write(data)
        ff.Length1 = len(data)
        shrunk += 1
    return shrunk
