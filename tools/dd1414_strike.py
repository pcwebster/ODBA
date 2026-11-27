"""Strike detection for DD 1414 tokens (DBDP-134 design v5, c10824 section A).

Reading 1 is vector evidence from pdfminer.six (page paths and annotation
appearance strokes). Reading 2 is a pinned Poppler RGB render at 300 dpi.
Each token comes out struck, not_struck or ambiguous; ambiguous stops the build.
"""
from dataclasses import dataclass

import numpy

DPI = 300
PIXEL_TOL = 40          # per RGB channel
LINE_TOL_PX = 2         # +/- pixels around the predicted line
CONFIRM = 0.90          # Reading 2 coverage of a candidate
FULL = 0.80             # Reading 1 coverage of a token
PARTIAL = 0.20
BAND = (0.30, 0.70)     # middle band of the token's glyph boxes
RULE_GAP = 1.0          # a mark within 1.0 pt of a horizontal table rule is a rule
HORIZONTAL = 0.5
THIN = 1.5
BACKGROUNDS = ((255, 255, 255), (211, 211, 211), (192, 192, 192))   # white, 0.827 and 0.753 gray fills


@dataclass
class Mark:
    x0: float
    x1: float
    y: float
    hex: str
    width: float
    source: str          # annotation id, or "path"


def rgb(hexcode):
    return tuple(int(hexcode[i:i + 2], 16) for i in (0, 2, 4))


def near(a, b, tol=PIXEL_TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def page_marks(page):
    """Horizontal strike-shaped marks (Reading 1 candidates) and the table's
    horizontal rule heights."""
    marks, rules = [], []
    for v in page.vectors:
        h, w = v.y1 - v.y0, v.x1 - v.x0
        if v.kind == "rect" and v.fill and h <= THIN and w > THIN:
            if w > 100:
                rules.append((v.y0 + v.y1) / 2)
            marks.append(Mark(v.x0, v.x1, (v.y0 + v.y1) / 2, v.fill_hex, h, "path"))
        elif v.kind in ("line", "curve") and v.stroke and h <= HORIZONTAL and w > THIN:
            marks.append(Mark(v.x0, v.x1, (v.y0 + v.y1) / 2, v.stroke_hex, v.linewidth, "path"))
    for a in page.annotations:
        for s in a.strokes:
            if abs(s.y1 - s.y0) <= HORIZONTAL:
                marks.append(Mark(min(s.x0, s.x1), max(s.x0, s.x1), (s.y0 + s.y1) / 2, s.stroke_hex,
                                  s.linewidth, a.name))
    return marks, rules


def _px(x):
    return int(round(x * DPI / 72))


def _py(y, height):
    return int(round((height - y) * DPI / 72))


def confirm(mark, pixels, height):
    """Reading 2: share of the mark's length with stroke-coloured pixels on its line."""
    colour = numpy.array(rgb(mark.hex), dtype=int)
    x0, x1 = _px(mark.x0), _px(mark.x1)
    yc = _py(mark.y, height)
    if x1 <= x0:
        return 0.0
    window = pixels[max(yc - LINE_TOL_PX, 0):yc + LINE_TOL_PX + 1, x0:x1].astype(int)
    hit = (numpy.abs(window - colour).max(axis=2) <= PIXEL_TOL).any(axis=0)
    return float(hit.mean())


def _foreign(window, text_rgb):
    """Pixels that are neither the text colour, a background, nor a blend of the two."""
    p = window.reshape(-1, 3).astype(float)
    best = numpy.full(len(p), numpy.inf)
    a = numpy.array(text_rgb, dtype=float)
    for bg in BACKGROUNDS:
        b = numpy.array(bg, dtype=float)
        d = b - a
        t = numpy.clip(((p - a) @ d) / max(d @ d, 1e-9), 0, 1)
        dist = numpy.abs(p - (a + t[:, None] * d)).max(axis=1)
        best = numpy.minimum(best, dist)
    return (best > PIXEL_TOL).reshape(window.shape[:2])


def foreign_coverage(token, pixels, height):
    h = token.y1 - token.y0
    lo, hi = token.y0 + BAND[0] * h, token.y0 + BAND[1] * h
    x0, x1 = _px(token.x0), _px(token.x1)
    r0, r1 = _py(hi, height), _py(lo, height)
    if x1 <= x0 or r1 <= r0:
        return 0.0
    window = pixels[r0:r1 + 1, x0:x1]
    return float(_foreign(window, rgb(token.hex)).any(axis=0).mean())


def classify(token, marks, rules, column_edges, pixels, height):
    """Return (outcome, evidence) for one token."""
    h = token.y1 - token.y0
    lo, hi = token.y0 + BAND[0] * h, token.y0 + BAND[1] * h
    width = token.x1 - token.x0
    evidence = {"candidates": [], "reasons": []}
    full = []
    for m in marks:
        if not (lo <= m.y <= hi):
            continue
        cover = max(0.0, min(m.x1, token.x1) - max(m.x0, token.x0)) / width if width > 0 else 0.0
        if cover < PARTIAL:
            continue
        spans = any(m.x0 < left and m.x1 > right for left, right in column_edges)
        on_rule = any(abs(m.y - r) <= RULE_GAP for r in rules) and m.source == "path" and (m.x1 - m.x0) > 100
        entry = {"source": m.source, "x0": round(m.x0, 2), "x1": round(m.x1, 2), "y": round(m.y, 2),
                 "hex": m.hex, "width": round(m.width, 2), "coverage": round(cover, 3)}
        evidence["candidates"].append(entry)
        if spans or on_rule:
            evidence["reasons"].append("mark could be a table rule or a strike")
            continue
        if cover < FULL:
            evidence["reasons"].append(f"strike coverage {cover:.2f} is between 0.20 and 0.80")
            continue
        full.append((m, entry))
    run = foreign_coverage(token, pixels, height)
    evidence["foreign_coverage"] = round(run, 3)
    if evidence["reasons"]:
        return "ambiguous", evidence
    if full:
        for m, entry in full:
            if near(rgb(m.hex), rgb(token.hex)):
                evidence["reasons"].append("strike colour is within tolerance of the text colour")
                return "ambiguous", evidence
            entry["confirmed"] = round(confirm(m, pixels, height), 3)
            if entry["confirmed"] < CONFIRM:
                evidence["reasons"].append("render does not confirm the vector strike")
                return "ambiguous", evidence
        return "struck", evidence
    if run >= PARTIAL:
        evidence["reasons"].append("render shows a stroke-coloured run with no vector mark")
        return "ambiguous", evidence
    return "not_struck", evidence
