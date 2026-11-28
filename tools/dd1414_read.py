"""Readers for the FY2026 DD 1414 PDF (DBDP-134).

Three readings of the same pinned bytes, each converted to one frame: crop-local
points, origin at the CropBox lower-left, y up (design c10824 section C).

* pdfminer.six 20260107: glyphs (box, origin, font, size, fill colour), vector
  objects and annotation appearance strokes. Primary reader.
* Poppler pdftotext -bbox-layout -cropbox: word boxes. Amount-cell verifier.
* Poppler pdftohtml -xml -zoom 1 -noroundcoord: text runs with colour. Colour
  cross-check.
* Poppler pdftoppm -cropbox -r 300: RGB render. Strike pixel verifier.

Nothing here decides what a row means; that is dd1414_grammar.py.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
import html
import re
import subprocess
import tempfile
from pathlib import Path

from defusedxml import ElementTree

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar, LTCurve, LTLine, LTRect
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager, PDFContentParser
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1, PDFStream
from pdfminer.psparser import PSKeyword, PSLiteral
from pdfminer import utils


class ReadStop(ValueError):
    """A reader found something the design says must stop the build."""


def demand(ok, message):
    if not ok:
        raise ReadStop(message)


def q2(value):
    """Round half-even to 0.01 pt (c10764 section 4)."""
    return float(Decimal(repr(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def fmt2(value):
    return "" if value is None else f"{q2(value):.2f}"


# ---------------------------------------------------------------- colour

def colour_hex(space, components):
    """Fixed formulas from c10752 section 5. Returns (hex, resolved)."""
    comps = tuple(float(c) for c in components)
    if space == "DeviceGray" and len(comps) == 1:
        v = round(comps[0] * 255)
        rgb = (v, v, v)
    elif space == "DeviceRGB" and len(comps) == 3:
        rgb = tuple(round(c * 255) for c in comps)
    elif space == "DeviceCMYK" and len(comps) == 4:
        c, m, y, k = comps
        rgb = tuple(round(255 * (1 - min(1.0, v + k))) for v in (c, m, y))
    else:
        return "", False
    return "".join(f"{max(0, min(255, v)):02X}" for v in rgb), True


def _space_name(ncs):
    name = getattr(ncs, "name", None)
    return str(name) if name is not None else ""


def _components(value):
    if value is None:
        return ()
    if isinstance(value, (int, float)):
        return (float(value),)
    return tuple(float(v) for v in value)


# ---------------------------------------------------------------- pdfminer reading

@dataclass
class Glyph:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    ox: float          # origin, as pdfminer places it
    oy: float
    rule_ox: float     # origin under the PDF character-spacing rule (content stream)
    font: str
    size: float
    space: str
    components: tuple
    hex: str
    resolved: bool
    string_id: int     # index of the text-showing operation that drew it
    basefont: str = "" # BaseFont of the font resource (pdfminer's fontname is the descriptor's)


@dataclass
class Vector:
    kind: str          # rect, line, curve, annot_stroke
    x0: float
    y0: float
    x1: float
    y1: float
    stroke: bool
    fill: bool
    stroke_hex: str
    fill_hex: str
    linewidth: float
    points: tuple = ()
    annotation: str = ""


@dataclass
class Annotation:
    subtype: str
    name: str
    subject: str
    flags: int
    rect: tuple
    strokes: list = field(default_factory=list)   # Vector, crop-local


@dataclass
class MinerPage:
    number: int
    media: tuple
    crop: tuple
    rotate: int
    glyphs: list
    vectors: list
    annotations: list
    max_rule_drift: float


class _RuleAggregator(PDFPageAggregator):
    """pdfminer's aggregator, recording for each glyph the text operation that drew
    it and its origin under the PDF rule that character spacing (Tc) follows every
    glyph, the last of a string included.

    pdfminer.six 20260107 adds Tc only between glyphs of one string (see
    pdfdevice.render_string_horizontal). Its own glyph positions are kept as the
    primary reading; the rule origin is a second reading of the same drawing
    instructions, used for token boundaries and the A-58 duplicate test that Peter
    approved in c10834.
    """

    def __init__(self, rsrcmgr):
        super().__init__(rsrcmgr, laparams=None)
        self.meta = {}
        self.basefonts = {}
        self._string = 0
        self._last = None
        self._drift = 0.0

    def begin_page(self, page, ctm):
        super().begin_page(page, ctm)
        self.meta = {}
        self._last = None
        self._drift = 0.0

    def render_string(self, textstate, seq, ncs, graphicstate):
        start = tuple(textstate.linematrix)
        tm = tuple(textstate.matrix)
        if self._last != (tm, start):
            self._drift = 0.0
        self._string += 1
        matrix = utils.mult_matrix(textstate.matrix, self.ctm)
        before = len(self.cur_item._objs)
        super().render_string(textstate, seq, ncs, graphicstate)
        drift_device = self._drift * matrix[0]
        glyphs = 0
        for obj in self.cur_item._objs[before:]:
            if isinstance(obj, LTChar):
                self.meta[id(obj)] = (self._string, obj.matrix[4] + drift_device, self.basefonts.get(id(textstate.font), str(textstate.font.basefont)))
                glyphs += 1
        if glyphs:
            self._drift += textstate.charspace * textstate.scaling * 0.01
        self._last = (tm, tuple(textstate.linematrix))


class _Interpreter(PDFPageInterpreter):
    """Records the BaseFont of each font resource as the page names it. For a
    Type0 font pdfminer keeps only the descendant's name, which Acrobat's edit
    fonts share (A-58), while Poppler reports the Type0 BaseFont."""

    def init_resources(self, resources):
        super().init_resources(resources)
        fonts = resolve1(dict(resources or {}).get("Font")) or {}
        for fontid, spec in dict(fonts).items():
            spec = resolve1(spec)
            base = spec.get("BaseFont") if isinstance(spec, dict) else None
            if fontid in self.fontmap and base is not None:
                self.device.basefonts[id(self.fontmap[fontid])] = base.name if isinstance(base, PSLiteral) else str(base)


def _box(obj):
    return resolve1(obj) if obj is not None else None


def _parse_appearance(stream, owner):
    """Strokes from an annotation appearance stream, in form space.

    Only path painting operators are supported; anything else stops the build so
    that no appearance is read halfway.
    """
    parser = PDFContentParser([stream])
    stack, segs = [], []
    ctm = (1, 0, 0, 1, 0, 0)
    saved = []
    width, colour = 1.0, ("DeviceGray", (0.0,))
    path, current = [], None
    allowed = {"q", "Q", "cm", "w", "RG", "G", "K", "rg", "g", "k", "m", "l", "h", "re",
               "S", "s", "f", "F", "f*", "B", "b", "n", "J", "j", "d", "M", "gs", "CS", "SC", "SCN",
               "cs", "sc", "scn", "BMC", "EMC", "BDC"}
    while True:
        try:
            _, obj = parser.nextobject()
        except Exception:
            break
        if isinstance(obj, PSKeyword):
            op = obj.name.decode("latin-1") if isinstance(obj.name, bytes) else str(obj.name)
            demand(op in allowed, f"Unsupported operator {op} in annotation appearance {owner}")
            args = stack
            stack = []
            if op == "q":
                saved.append((ctm, width, colour))
            elif op == "Q":
                ctm, width, colour = saved.pop()
            elif op == "cm":
                ctm = utils.mult_matrix(tuple(float(a) for a in args), ctm)
            elif op == "w":
                width = float(args[0])
            elif op == "RG":
                colour = ("DeviceRGB", tuple(float(a) for a in args))
            elif op == "G":
                colour = ("DeviceGray", tuple(float(a) for a in args))
            elif op == "K":
                colour = ("DeviceCMYK", tuple(float(a) for a in args))
            elif op in ("CS", "SC", "SCN"):
                demand(False, f"Unsupported stroke colour space in annotation appearance {owner}")
            elif op == "m":
                current = utils.apply_matrix_pt(ctm, (float(args[0]), float(args[1])))
                path.append([current])
            elif op == "l":
                current = utils.apply_matrix_pt(ctm, (float(args[0]), float(args[1])))
                demand(path, f"Line without moveto in annotation appearance {owner}")
                path[-1].append(current)
            elif op == "re":
                demand(False, f"Rectangle in annotation appearance {owner}")
            elif op in ("S", "s", "B", "b"):
                for sub in path:
                    for a, b in zip(sub, sub[1:]):
                        segs.append((a, b, width * abs(ctm[0]), colour))
                path = []
            elif op in ("f", "F", "f*", "n"):
                demand(not path or op == "n", f"Filled path in annotation appearance {owner}")
                path = []
        else:
            stack.append(obj)
    return segs


def _annotations(page, crop, number):
    out = []
    for ref in resolve1(page.annots) or []:
        annot = resolve1(ref)
        subtype = resolve1(annot.get("Subtype"))
        subtype = subtype.name if isinstance(subtype, PSLiteral) else str(subtype)
        name = resolve1(annot.get("NM"))
        name = name.decode("latin-1") if isinstance(name, bytes) else (name or "")
        subj = resolve1(annot.get("Subj"))
        subj = subj.decode("latin-1") if isinstance(subj, bytes) else (subj or "")
        flags = int(resolve1(annot.get("F")) or 0)
        rect = tuple(float(v) for v in resolve1(annot.get("Rect")))
        entry = Annotation(subtype, name, subj, flags, rect)
        ap = _box(annot.get("AP"))
        normal = _box(ap.get("N")) if ap else None
        if isinstance(normal, dict) and not isinstance(normal, PDFStream):
            demand(False, f"Annotation {name} on page {number} has appearance states")
        if isinstance(normal, PDFStream):
            bbox = tuple(float(v) for v in resolve1(normal.attrs.get("BBox")))
            matrix = tuple(float(v) for v in (resolve1(normal.attrs.get("Matrix")) or (1, 0, 0, 1, 0, 0)))
            # PDF 32000-1 12.5.5: transform BBox by Matrix, then map that box onto Rect.
            corners = [utils.apply_matrix_pt(matrix, p) for p in
                       ((bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[0], bbox[3]), (bbox[2], bbox[3]))]
            bx0 = min(p[0] for p in corners); bx1 = max(p[0] for p in corners)
            by0 = min(p[1] for p in corners); by1 = max(p[1] for p in corners)
            demand(bx1 > bx0 and by1 > by0, f"Degenerate appearance box on {name}")
            sx = (rect[2] - rect[0]) / (bx1 - bx0)
            sy = (rect[3] - rect[1]) / (by1 - by0)
            a = (sx, 0, 0, sy, rect[0] - bx0 * sx, rect[1] - by0 * sy)
            final = utils.mult_matrix(matrix, a)
            for p, r, width, colour in _parse_appearance(normal, name):
                (x0, y0) = utils.apply_matrix_pt(final, p)
                (x1, y1) = utils.apply_matrix_pt(final, r)
                x0 -= crop[0]; x1 -= crop[0]; y0 -= crop[1]; y1 -= crop[1]
                hexc, ok = colour_hex(colour[0], colour[1])
                demand(ok, f"Unresolved stroke colour on annotation {name}")
                entry.strokes.append(Vector("annot_stroke", min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
                                            True, False, hexc, "", width * abs(final[0]),
                                            ((x0, y0), (x1, y1)), name))
        out.append(entry)
    return out


def read_pdfminer(path):
    rsrc = PDFResourceManager(caching=True)
    device = _RuleAggregator(rsrc)
    interp = _Interpreter(rsrc, device)
    pages = []
    with open(path, "rb") as handle:
        document = PDFDocument(PDFParser(handle))
        for number, page in enumerate(PDFPage.create_pages(document), 1):
            media = tuple(float(v) for v in page.mediabox)
            crop = tuple(float(v) for v in page.cropbox)
            rotate = int(page.rotate or 0)
            interp.process_page(page)
            layout = device.get_result()
            width, height = media[2] - media[0], media[3] - media[1]
            # c10824 section C: pdfminer already removed the MediaBox origin.
            demand(tuple(round(v, 3) for v in layout.bbox) == (0, 0, round(width, 3), round(height, 3)),
                   f"pdfminer page frame on page {number} is {layout.bbox}, not (0, 0, {width}, {height})")
            dx, dy = crop[0] - media[0], crop[1] - media[1]
            glyphs, vectors = [], []
            drift = 0.0

            def visit(container):
                nonlocal drift
                for obj in container:
                    if isinstance(obj, LTChar):
                        demand(abs(obj.matrix[1]) < 1e-9 and abs(obj.matrix[2]) < 1e-9,
                               f"Rotated or skewed glyph on page {number}")
                        sid, rule, basefont = device.meta[id(obj)]
                        gs = obj.graphicstate
                        space = _space_name(obj.ncs)
                        comps = _components(gs.ncolor)
                        hexc, ok = colour_hex(space, comps)
                        drift = max(drift, abs(rule - obj.matrix[4]))
                        glyphs.append(Glyph(obj.get_text(), obj.x0 - dx, obj.y0 - dy, obj.x1 - dx, obj.y1 - dy,
                                            obj.matrix[4] - dx, obj.matrix[5] - dy, rule - dx,
                                            obj.fontname, obj.size, space, comps, hexc, ok, sid, basefont))
                    elif isinstance(obj, (LTRect, LTLine, LTCurve)):
                        kind = "rect" if isinstance(obj, LTRect) else "line" if isinstance(obj, LTLine) else "curve"
                        sh = colour_hex("DeviceRGB" if len(_components(obj.stroking_color)) == 3 else
                                        "DeviceCMYK" if len(_components(obj.stroking_color)) == 4 else "DeviceGray",
                                        _components(obj.stroking_color) or (0.0,))[0]
                        fh = colour_hex("DeviceRGB" if len(_components(obj.non_stroking_color)) == 3 else
                                        "DeviceCMYK" if len(_components(obj.non_stroking_color)) == 4 else "DeviceGray",
                                        _components(obj.non_stroking_color) or (0.0,))[0]
                        pts = tuple((x - dx, y - dy) for x, y in getattr(obj, "pts", ()))
                        vectors.append(Vector(kind, obj.x0 - dx, obj.y0 - dy, obj.x1 - dx, obj.y1 - dy,
                                              bool(obj.stroke), bool(obj.fill), sh, fh, float(obj.linewidth), pts))
                    elif hasattr(obj, "__iter__"):
                        visit(obj)
            visit(layout)
            annotations = _annotations(page, crop, number)
            pages.append(MinerPage(number, media, crop, rotate, glyphs, vectors, annotations, drift))
    return pages


def read_info(path):
    """Trailer IDs and Info dates, for the edition pin (c10764 section 3)."""
    with open(path, "rb") as handle:
        document = PDFDocument(PDFParser(handle))
        ids = [resolve1(v) for v in (resolve1(document.xrefs[0].trailer.get("ID")) if document.xrefs else [])]
        trailer_ids = [v.hex() if isinstance(v, bytes) else str(v) for v in ids]
        if not trailer_ids:
            for xref in document.xrefs:
                found = xref.trailer.get("ID") if hasattr(xref, "trailer") else None
                if found:
                    trailer_ids = [resolve1(v).hex() for v in resolve1(found)]
                    break
        info = resolve1(document.info[0]) if document.info else {}

        def text(key):
            value = resolve1(info.get(key)) if info else None
            return value.decode("latin-1") if isinstance(value, bytes) else (value or "")
        return {"trailer_ids": trailer_ids, "creation_date": text("CreationDate"), "mod_date": text("ModDate")}


# ---------------------------------------------------------------- Poppler readings

def poppler_version():
    out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
    found = re.search(r"pdftotext version (\S+)", out.stderr + out.stdout)
    demand(found is not None, "Cannot read the Poppler version")
    return found.group(1)


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def read_bbox_words(path):
    """pdftotext -bbox-layout -cropbox, converted to crop-local points."""
    raw = subprocess.run(["pdftotext", "-bbox-layout", "-cropbox", "-q", str(path), "-"],
                         check=True, capture_output=True).stdout
    raw = re.sub(rb"<!DOCTYPE[^>]*>", b"", raw)
    raw = raw.replace(b"&nbsp;", b" ")
    root = ElementTree.fromstring(raw)
    pages = []
    for page in root.iter():
        if not page.tag.endswith("page"):
            continue
        width, height = float(page.get("width")), float(page.get("height"))
        words = []
        for word in page.iter():
            if word.tag.endswith("word"):
                x0, y0p, x1, y1p = (float(word.get(k)) for k in ("xMin", "yMin", "xMax", "yMax"))
                words.append(Word(word.text or "", x0, height - y1p, x1, height - y0p))
        pages.append({"width": width, "height": height, "words": words})
    return pages


@dataclass
class Run:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    hex: str
    family: str
    size: float


def read_html_runs(path):
    """pdftohtml -xml -zoom 1 -noroundcoord: text runs with colour, crop-local."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "out"
        subprocess.run(["pdftohtml", "-xml", "-zoom", "1", "-noroundcoord", "-i", "-q", "-nodrm",
                        str(path), str(target)], check=True, capture_output=True)
        raw = (Path(tmp) / "out.xml").read_bytes()
    raw = re.sub(rb"<!DOCTYPE[^>]*>", b"", raw)
    root = ElementTree.fromstring(raw)
    fonts = {}
    pages = []
    for page in root.iter("page"):
        width, height = float(page.get("width")), float(page.get("height"))
        for spec in page.iter("fontspec"):
            fonts[spec.get("id")] = (spec.get("color", "").lstrip("#").upper(), spec.get("family", ""),
                                     float(spec.get("size", 0)))
        runs = []
        for text in page.iter("text"):
            content = "".join(text.itertext())
            colour, family, size = fonts[text.get("font")]
            top, left = float(text.get("top")), float(text.get("left"))
            w, h = float(text.get("width")), float(text.get("height"))
            runs.append(Run(html.unescape(content), left, height - top - h, left + w, height - top, colour, family, size))
        pages.append({"width": width, "height": height, "runs": runs})
    return pages


def render_page(path, number, directory, dpi=300):
    """pdftoppm -cropbox -r 300 RGB render of one page; returns (pixels, height_px)."""
    import numpy
    stem = Path(directory) / f"p{number}"
    subprocess.run(["pdftoppm", "-cropbox", "-r", str(dpi), "-f", str(number), "-l", str(number),
                    "-singlefile", str(path), str(stem)], check=True, capture_output=True)
    data = Path(str(stem) + ".ppm").read_bytes()
    Path(str(stem) + ".ppm").unlink()
    found = re.match(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s", data)
    demand(found is not None and found.group(3) == b"255", f"Unexpected render format on page {number}")
    w, h = int(found.group(1)), int(found.group(2))
    pixels = numpy.frombuffer(data, dtype=numpy.uint8, offset=found.end()).reshape(h, w, 3)
    return pixels
