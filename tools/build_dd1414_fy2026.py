"""Build the FY2026 DD 1414 enacted-base sidecar from the pinned PDF (DBDP-134).

Design record: c10752 as changed by c10764 and c10775, decisions c10758,
approvals c10795 and c10800, revision v5 c10824 with Peter's guardrail c10827,
reviewed dispositions c10829, c10834 and c10836, published rounding c10838,
and the N-29 blank repeat c10839 and c10840.

Every check is a hard stop unless it is named a diagnostic. Stops are collected
so one run reports all of them; while any stands, nothing is written.

    python3 tools/build_dd1414_fy2026.py --pdf <original> [--check]

--check builds in memory and compares with the committed files (check 8).
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import tempfile

if __package__:
    from . import dd1414_read as R
    from . import dd1414_grammar as G
    from . import dd1414_strike as S
else:
    import dd1414_read as R
    import dd1414_grammar as G
    import dd1414_strike as S

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data/dd1414/fy2026"
SOURCE_FILE = "FY_2026_DD_1414_Base_for_Reprogramming_Actions.pdf"
SOURCE_URL = ("https://comptroller.war.gov/Portals/45/Documents/execution/"
              "FY_2026_DD_1414_Base_for_Reprogramming_Actions.pdf")
PIN = {
    "sha256": "4cef3b41d68da3812828993bbb4b110d1aca5d5b0a67b1cb9eee8961324a96a3",
    "bytes": 10582173,
    "pages": 304,
    "trailer_ids": ["87a0d522222b084ba7c91d5c7acb6633", "af652bcc76a31544ae03ce2034b86e3a"],
    "creation_date": "D:20260305092233-05'00'",
    "mod_date": "D:20260810111147-04'00'",
}
POPPLER = "24.02.0"
PDFMINER = "20260107"
FORM = "DD1414"
DESIGN = {"design": ["10752", "10764", "10775"], "decisions": ["10758"], "approvals": ["10795", "10800"],
          "revision_v5": "10824", "guardrail": "10827", "pdfminer_install": "10828",
          "dispositions": ["10829", "10834", "10836"], "published_rounding": "10838",
          "build_mandate": "10832"}
EDIT_EXCEPTIONS = "edit_exceptions.json"
PUBLISHED_DIFFERENCES = "published_differences.json"
MATCH = 0.05            # committed positions, points
READER_TOL = 0.5        # pdfminer against Poppler, points (c10824 section C)
DUPLICATE_TOL = 0.1     # c10824 section B
LANE_COLUMNS = tuple(f"lane_{lane}" for lane in G.LANES)


class Stops:
    def __init__(self):
        self.items = []

    def __call__(self, check, message):
        self.items.append(f"[check {check}] {message}")

    def __bool__(self):
        return bool(self.items)


def nz(text):
    return "".join(text.split())


def num(v):
    return "" if v is None else str(v)


def z(v):
    return v if isinstance(v, int) else 0


def r2(v):
    return R.fmt2(v)


def record_id(key):
    return "dd1414-fy26-" + hashlib.sha256("\x1f".join(str(p) for p in key).encode("utf-8")).hexdigest()[:20]


# ------------------------------------------------------------------ pin and pages

def check_pin(pdf, stops):
    data = Path(pdf).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PIN["sha256"] or len(data) != PIN["bytes"]:
        stops("1", f"source is {digest} ({len(data)} bytes), not the pinned {PIN['sha256']}")
        return False
    info = R.read_info(pdf)
    for key in ("trailer_ids", "creation_date", "mod_date"):
        if info[key] != PIN[key]:
            stops("1", f"{key} is {info[key]!r}, not {PIN[key]!r}")
    version = R.poppler_version()
    if version != POPPLER:
        stops("1", f"Poppler is {version}; the build is pinned to {POPPLER}")
    import pdfminer
    if pdfminer.__version__ != PDFMINER:
        stops("1", f"pdfminer.six is {pdfminer.__version__}; the build is pinned to {PDFMINER}")
    return not stops


PAGE_CLASSES = (
    ("data", lambda t: "Appropriation Account Title:" in t and "Fiscal Year Program" in t),
    ("contents", lambda t: "TABLE OF CONTENTS" in t.upper()),
    ("blank", lambda t: "INTENTIONALLY LEFT BLANK" in t.upper()),
    ("letter", lambda t: "UNDER SECRETARY OF" in t.upper() and ("Dear" in t or "Sincerely" in t)),
    ("notice", lambda t: "cost" in t.lower() and "report" in t.lower() and len(t) < 1500),
    ("title", lambda t: "BASE FOR REPROGRAMMING" in t.upper()),
)


def classify_pages(pages, stops):
    out, boxes = {}, {}
    for page in pages:
        text = " ".join("".join(g.text for g in page.glyphs).split())
        kind = next((name for name, test in PAGE_CLASSES if test(text)), None)
        if kind is None:
            stops("2", f"page {page.number} cannot be classified")
            continue
        out[page.number] = kind
        same = tuple(round(v, 4) for v in page.media) == tuple(round(v, 4) for v in page.crop)
        if kind == "data" and not same:
            stops("2", f"data page {page.number}: CropBox differs from MediaBox")
        elif not same:
            boxes[page.number] = {"media_box": [r2(v) for v in page.media], "crop_box": [r2(v) for v in page.crop]}
    return out, boxes


def html_to_crop(html, w, h):
    """pdftohtml -xml prints the page size truncated to whole points (791 x 611 for a
    791.9996 x 611.9998 CropBox) and measures top from that truncated height. Assert exactly
    that, then shift its runs into the crop-local frame (c10824 section C). Returns a stop
    message, or "" once the runs are converted in place."""
    if html["width"] != math.floor(w + 1e-9) or html["height"] != math.floor(h + 1e-9):
        return (f"pdftohtml page size {html['width']} x {html['height']} is not the CropBox "
                f"{w:.4f} x {h:.4f} truncated to whole points")
    shift = h - html["height"]
    for run in html["runs"]:
        run.y0 += shift
        run.y1 += shift
    return ""


def check_inputs(exceptions, differences, stops):
    """The committed inputs are registries: every id and every match key is used once. A repeated
    entry would let a later one silently shadow an earlier one when the lists become dicts, so it
    stops the build before anything is read (OpenAI review of PR #30, item 1; c10824, c10838)."""
    def unique(label, check, items, key):
        for k, n in Counter(key(e) for e in items).items():
            if n > 1:
                stops(check, f"{label}: {k!r} appears {n} times")

    lists = {name: exceptions.get(name, []) for name in ("entries", "diagnostics", "repeated_blank_lines")}
    every = [e for items in lists.values() for e in items]
    if any(not e.get("id") for e in every) or any(not d.get("id") for d in differences.get("entries", [])):
        stops("9c", "a committed exception or published difference has no id")
    unique(EDIT_EXCEPTIONS + " id", "9c", every, lambda e: e.get("id"))
    unique(EDIT_EXCEPTIONS + " entry", "9c", lists["entries"],
           lambda e: (e["page_code"], e["text"], e["hex"], e["font"], tuple(e["pdfminer"])))
    unique(EDIT_EXCEPTIONS + " diagnostic", "9c", lists["diagnostics"],
           lambda d: (d["page_code"], d["line_identifier"], d["row_kind"], d["lane"]))
    unique(EDIT_EXCEPTIONS + " repeated blank line", "7", lists["repeated_blank_lines"],
           lambda e: (e["page_code"], e["account_code_raw"], e["availability_raw"], e["budget_activity"],
                      e["line_identifier"], e["title"]))
    unique(PUBLISHED_DIFFERENCES + " id", "6", differences.get("entries", []), lambda d: d.get("id"))
    unique(PUBLISHED_DIFFERENCES + " entry", "6", differences.get("entries", []),
           lambda d: (d["page_code"], d["control_title"], d["lane"]))
    return not stops


# ------------------------------------------------------------------ build

class Build:
    def __init__(self, pdf, exceptions, differences):
        self.pdf = Path(pdf)
        self.stops = Stops()
        self.exceptions = exceptions
        self.differences = differences
        self.diagnostics = []
        self.edit_records = []
        self.strike_records = []

    def inputs(self):
        return check_inputs(self.exceptions, self.differences, self.stops)

    # -------------------------------------------------- read (checks 1 to 3)
    def read(self):
        stops = self.stops
        if not check_pin(self.pdf, stops):
            return False
        self.pages = R.read_pdfminer(self.pdf)
        if len(self.pages) != PIN["pages"]:
            stops("1", f"{len(self.pages)} pages, expected {PIN['pages']}")
            return False
        self.classes, self.odd_boxes = classify_pages(self.pages, stops)
        self.words = R.read_bbox_words(self.pdf)
        self.runs = R.read_html_runs(self.pdf)
        if len(self.words) != PIN["pages"] or len(self.runs) != PIN["pages"]:
            stops("3", "Poppler page count differs")
            return False
        for p in self.pages:
            if self.classes.get(p.number) != "data":
                continue
            w, h = p.crop[2] - p.crop[0], p.crop[3] - p.crop[1]
            words, html = self.words[p.number - 1], self.runs[p.number - 1]
            if abs(words["width"] - w) > 0.01 or abs(words["height"] - h) > 0.01:
                stops("3", f"page {p.number}: pdftotext page size {words['width']} x {words['height']} "
                           f"is not the CropBox {w:.4f} x {h:.4f}")
            problem = html_to_crop(html, w, h)
            if problem:
                stops("3", f"page {p.number}: {problem}")
        return not stops

    # -------------------------------------------------- parse
    def parse(self):
        stops = self.stops
        self.data = [p for p in self.pages if self.classes.get(p.number) == "data"]
        self.tokens = {p.number: G.tokens_of(p) for p in self.data}
        self.colours, self.fonts = G.body_style(self.tokens)
        self.grammar = G.PageGrammar()
        self.info = {}
        for p in self.data:
            toks = self.tokens[p.number]
            G.mark_edits(toks, self.colours, self.fonts)
            for g in G.edit_whitespace(p, self.colours, self.fonts):
                self.diagnostics.append({
                    "kind": "edit_font_whitespace", "page": p.number, "x0": r2(g.x0), "baseline": r2(g.oy),
                    "font": g.basefont or g.font, "hex": g.hex,
                    "note": "whitespace-only glyph drawn in an edit font; it holds no text"})
            found = []
            geo = G.geometry_of(p, toks, found)
            hdr = None
            if geo is not None:
                for t in toks:
                    G.place(t, geo)
                hdr = G.header_of(p, toks, geo, found)
            for s in found:
                stops("2", s)
            if hdr is None:
                continue
            for t in toks:
                if t.baseline >= geo.header_y - 1:
                    t.row = "page_header"
                elif t.baseline <= 25:
                    t.row = "page_footer"
            body = [t for t in toks if t.row is None]
            floating = self.grammar.page(p, hdr, G.clusters_of(body), geo)
            self.info[p.number] = {"geo": geo, "hdr": hdr, "floating": floating}
        for s in self.grammar.stops:
            stops("6", s)
        for p in self.data:
            for t in self.tokens[p.number]:
                if t.row is None and not t.edit and nz(t.text):
                    stops("6", f"page {p.number}: {t.text!r} at {r2(t.x0)}, {r2(t.baseline)} belongs to no row")
        self.rows = self.grammar.rows
        return not stops

    # -------------------------------------------------- strikes (check 9b)
    def strikes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for p in self.data:
                info = self.info[p.number]
                marks, rules = S.page_marks(p)
                pixels = R.render_page(self.pdf, p.number, tmp)
                height = p.crop[3] - p.crop[1]
                if abs(pixels.shape[0] - round(height * S.DPI / 72)) > 1:
                    self.stops("9b", f"page {p.number}: render height {pixels.shape[0]} px is not the CropBox height")
                    continue
                for t in self.tokens[p.number]:
                    if not nz(t.text):
                        t.strike = "not_struck"
                        continue
                    t.strike, t.strike_evidence = S.classify(t, marks, rules, info["geo"].edges[1:9], pixels, height)
                    if t.strike == "ambiguous":
                        self.stops("9b", f"page {p.number}: {t.text!r} at {r2(t.x0)}, {r2(t.baseline)} is "
                                         f"ambiguous: {'; '.join(t.strike_evidence['reasons'])}")
                    elif t.strike == "struck":
                        self.strike_records.append({
                            "page": p.number, "page_code": info["hdr"]["page_code"], "text": t.text,
                            "lane": t.lane, "x0": r2(t.x0), "baseline": r2(t.baseline),
                            "marks": t.strike_evidence["candidates"]})
                        if t.edit:
                            self.stops("9b", f"page {p.number}: edit token {t.text!r} is struck")
        return not self.stops

    # -------------------------------------------------- row kinds (c10764, c10775)
    def finalize_rows(self):
        stops = self.stops
        for r in self.rows:
            r.out_kind = r.kind
            r.footnote_edit = False
            title = [t for t in r.tokens if t.lane == "a" and nz(t.text) and not t.edit]
            struck = [t.strike == "struck" for t in title]
            r.superseded = bool(struck) and all(struck)
            if any(struck) and not all(struck):
                stops("5e", f"{r.page_code}: row {r.title or r.label!r} is partly struck")
            if r.superseded and r.kind not in ("adjustment", "general_provision"):
                stops("5e", f"{r.page_code}: struck {r.kind} row {r.title!r}")
        for r in self.rows:
            if r.kind == "ba_header":
                priced = bool(r.base_rows) or any(r.lane_tokens(lane) for lane in G.LANES)
                if priced and r.children:
                    r.out_kind = "parent"
                    if r.adjustments or r.base_rows:
                        stops("5c", f"{r.page_code}: priced budget activity {r.title!r} has lines and its own "
                                    f"base or adjustments")
                elif priced:
                    r.out_kind = "line"          # budget-activity grain line
                elif r.children:
                    r.out_kind = "parent"
                else:
                    stops("6", f"{r.page_code}: budget activity heading {r.title!r} has no amounts and no lines")
            elif r.kind == "org_header":
                r.out_kind = "parent"
        self.repeated_blank_lines()
        for r in self.rows:
            r.live_adjustments = [a for a in r.adjustments if not a.superseded]
        self.owners = [r for r in self.rows if r.out_kind == "line"]
        for r in self.owners:
            if len(r.base_rows) != 1:
                stops("5", f"{r.page_code}: line {r.line_id} {r.title!r} has {len(r.base_rows)} "
                           f"appropriated-base rows")
        for r in self.rows:
            if r.kind in ("adjustment", "general_provision") and not r.superseded \
                    and (r.parent is None or r.parent.out_kind != "line"):
                stops("6b", f"{r.page_code}: adjustment {r.label!r} has no additive parent line")
        return not stops

    @staticmethod
    def printed(row):
        """Any non-blank token in an amount lane, edits included."""
        return any(nz(t.text) for t in row.tokens if t.lane in G.LANES)

    def repeated_blank_lines(self):
        """Peter's c10840 (option 1 of c10839): a listed blank repeat of a priced line's key is kept in
        source_cells and left out of the additive set. The repeat must be blank in every lane, line and
        appropriated-base rows alike, with no adjustments; anything else stops the build (check 7)."""
        self.repeat_records = []
        for e in self.exceptions.get("repeated_blank_lines", []):
            if e.get("disposition") != "repeated_blank_line":
                self.stops("7", f"exception {e['id']}: unknown disposition {e.get('disposition')!r}")
                continue
            same = [r for r in self.rows if r.out_kind == "line" and r.page_code == e["page_code"]
                    and r.account["account_code_raw"] == e["account_code_raw"]
                    and r.account["availability_raw"] == e["availability_raw"]
                    and r.budget_activity == e["budget_activity"] and r.line_id == e["line_identifier"]
                    and nz(r.title) == nz(e["title"])]
            blank = [r for r in same if not r.adjustments and not self.printed(r)
                     and not any(self.printed(b) for b in r.base_rows)]
            priced = [r for r in same if r not in blank]
            if len(same) != 2 or len(blank) != 1 or len(priced) != 1:
                self.stops("7", f"exception {e['id']}: expected one priced and one blank {e['title']!r} on "
                                f"{e['page_code']}, found {len(priced)} priced and {len(blank)} blank")
                continue
            r = blank[0]
            r.out_kind = "repeated_blank_line"
            self.repeat_records.append({"id": e["id"], "page": r.page, "page_code": r.page_code,
                                        "title": r.title, "base_rows": len(r.base_rows),
                                        "disposition": e["disposition"], "approval": e["approval"]})

    # -------------------------------------------------- edits (check 9c)
    @staticmethod
    def line_of(r):
        return r if r.kind in ("line", "ba_header", "org_header") else r.parent

    def select(self, page, selector):
        out = []
        for r in self.rows:
            if r.page != page or r.superseded or r.out_kind != selector["row_kind"]:
                continue
            line = self.line_of(r)
            if line is None or line.line_id != selector["line_identifier"]:
                continue
            if "text" in selector and nz(r.label or r.title) != nz(selector["text"]):
                continue
            out.append(r)
        return out

    def poppler_words(self, page, t):
        return [w for w in self.words[page - 1]["words"] if nz(w.text) == nz(t.text)
                and abs(w.x0 - t.x0) <= READER_TOL and abs(w.y0 - t.y0) <= READER_TOL]

    def html_runs(self, page, t):
        return [x for x in self.runs[page - 1]["runs"] if nz(x.text) == nz(t.text) and x.hex == t.hex
                and abs(x.x0 - t.x0) <= READER_TOL and abs((x.y0 + x.y1) - (t.y0 + t.y1)) / 2 <= 1.5]

    def edits(self):
        stops = self.stops
        self.cell_owner = {}
        self.dupes = set()
        self.dupe_runs = Counter()
        entries = self.exceptions.get("entries", [])
        used = Counter()
        codes = {info["hdr"]["page_code"] for info in self.info.values()}
        for e in entries:
            if e["page_code"] not in codes:
                stops("9c", f"exception {e['id']}: {e['page_code']} is not a data page")
        for p in self.data:
            number = p.number
            code = self.info[number]["hdr"]["page_code"]
            for t in self.tokens[number]:
                if not (t.edit and nz(t.text)):
                    continue
                words, runs = self.poppler_words(number, t), self.html_runs(number, t)
                row = t.row if isinstance(t.row, G.Row) else None
                rec = {"page": number, "page_code": code, "text": t.text, "hex": t.hex, "font": t.font,
                       "size": r2(t.size), "lane": t.lane, "pdfminer": [r2(t.x0), r2(t.baseline)],
                       "rule_origin_x": r2(t.rule_x),
                       "pdftotext": [[r2(w.x0), r2(w.y0)] for w in words],
                       "pdftohtml": [[r2(x.x0), r2(x.y0)] for x in runs]}
                hit = [e for e in entries if e["page_code"] == code and e["text"] == t.text and e["hex"] == t.hex
                       and e["font"] == t.font and abs(e["pdfminer"][0] - t.x0) <= MATCH
                       and abs(e["pdfminer"][1] - t.baseline) <= MATCH]
                if len(hit) > 1:
                    stops("9c", f"{code}: {t.text!r} matches {len(hit)} exception entries")
                    continue
                if hit:
                    e = hit[0]
                    used[e["id"]] += 1
                    rec.update(disposition=e["disposition"], exception=e["id"], approval=e["approval"])
                    t.disposition, t.exception_id = e["disposition"], e["id"]
                    if not self.positions_match(e, words, runs):
                        stops("9c", f"{code}: exception {e['id']}: reader positions differ from the entry")
                        continue
                    handler = getattr(self, "exception_" + e["disposition"], None)
                    if handler is None:
                        stops("9c", f"exception {e['id']}: unknown disposition {e['disposition']!r}")
                        continue
                    handler(number, code, t, e, rec)
                    self.edit_records.append(rec)
                    continue
                reason = self.automatic_reason(t, row, words, runs)
                if reason:
                    stops("9c", f"{code}: edit token {t.text!r} at {r2(t.x0)}, {r2(t.baseline)} has no "
                                f"automatic owner ({reason}) and no exception entry")
                    continue
                rec["disposition"] = t.disposition = "automatic"
                self.assign(row, t.lane, t, rec)
                self.edit_records.append(rec)
        for e in entries:
            if used[e["id"]] != 1:
                stops("9c", f"exception {e['id']} matched {used[e['id']]} tokens, expected 1")
        return not stops

    @staticmethod
    def positions_match(e, words, runs):
        def same(expected, got):
            got = sorted([a, b] for a, b in got)
            return len(expected) == len(got) and all(
                abs(a[0] - b[0]) <= MATCH and abs(a[1] - b[1]) <= MATCH for a, b in zip(sorted(expected), got))
        return same(e["pdftotext"], [(w.x0, w.y0) for w in words]) and \
            same(e["pdftohtml"], [(x.x0, x.y0) for x in runs])

    @staticmethod
    def automatic_reason(t, row, words, runs):
        """c10824 section B: all four conditions hold, or the reason one fails."""
        if row is None:
            return "its baseline is in no row band"
        if t.lane not in G.AMOUNT_LANES or t.spans or t.near_edge or t.outside:
            return "its centre is not inside exactly one amount lane"
        if row.superseded:
            return "its row is superseded"
        if t.lane == "i" and row.out_kind not in ("line", "appropriated_base", "line_repeat"):
            return f"a {row.out_kind} row does not print lane i"
        if row.out_kind not in ("line", "appropriated_base", "line_repeat", "adjustment", "general_provision"):
            return f"a {row.out_kind} row is not a priced row"
        body = [u for u in row.tokens if u.lane == t.lane and not u.edit and nz(u.text)]
        others = [u for u in row.tokens if u.lane == t.lane and u.edit and u is not t and nz(u.text)]
        if others or len(body) > 1 or (body and body[0].strike != "struck"):
            return "the cell holds another live value"
        if len(words) != 1 or len(runs) != 1:
            return "the readers do not agree on its text and position"
        return None

    def exception_owner(self, number, code, t, e, rec):
        target = self.select(number, e["owner"]["row"])
        if len(target) != 1:
            self.stops("9c", f"{code}: exception {e['id']} names {len(target)} rows")
            return
        lane = e["owner"]["lane"]
        if t.lane != lane and not t.spans:
            self.stops("9c", f"{code}: exception {e['id']} puts {t.text!r} in lane {lane}; it sits in {t.lane!r}")
            return
        body = [u for u in target[0].tokens if u.lane == lane and not u.edit and nz(u.text)]
        if len(body) > 1 or (body and body[0].strike != "struck"):
            self.stops("9c", f"{code}: exception {e['id']}: the target cell holds another live value")
            return
        if e["owner"]["role"] != target[0].out_kind:
            self.stops("9c", f"{code}: exception {e['id']} role {e['owner']['role']} is not {target[0].out_kind}")
            return
        self.assign(target[0], lane, t, rec)

    def exception_duplicate(self, number, code, t, e, rec):
        """c10824 section B duplicate test, as Peter decided it in c10834: pdfminer draws the run twice with
        rule origins within 0.1 pt, and pdftohtml reports both drawings at the rule origin."""
        twins = [u for u in self.tokens[number]
                 if u is not t and u.edit and u.text == t.text and u.hex == t.hex and u.font == t.font
                 and abs(u.size - t.size) < 0.01 and abs(u.rule_x - t.rule_x) <= DUPLICATE_TOL
                 and abs(u.baseline - t.baseline) <= DUPLICATE_TOL]
        runs = [x for x in self.runs[number - 1]["runs"] if nz(x.text) == nz(t.text) and x.hex == t.hex
                and abs(x.x0 - t.rule_x) <= DUPLICATE_TOL and abs((x.y0 + x.y1) - (t.y0 + t.y1)) / 2 <= 1.5]
        if len(twins) != 1 or len(runs) != 2 or abs(runs[0].y0 - runs[1].y0) > DUPLICATE_TOL:
            self.stops("9c", f"{code}: duplicate test fails for exception {e['id']}")
            return
        self.dupes.add(id(t))
        self.dupe_runs[number] += 1
        rec["duplicate_of"] = [r2(twins[0].x0), r2(twins[0].baseline)]
        rec["pdftohtml_drawings"] = sorted([r2(x.x0), r2(x.y0)] for x in runs)
        self.diagnostics.append({
            "kind": "reader_quirk", "page": number, "page_code": code, "text": t.text,
            "pdfminer_x0": r2(t.x0), "rule_origin_x": r2(t.rule_x), "shift": r2(t.x0 - t.rule_x),
            "note": (f"pdfminer.six {PDFMINER} places this second drawing of the run {r2(t.x0 - t.rule_x)} pt right "
                     f"of where the PDF text-positioning rule puts it; collapsed as a duplicate under "
                     f"{e['approval']}")})

    def exception_footnote_owner(self, number, code, t, e, rec):
        target = self.select(number, e["owner"]["row"])
        if len(target) != 1 or t.row is not target[0] or t.lane != "a":
            self.stops("9c", f"{code}: footnote exception {e['id']} does not fit {t.text!r}")
            return
        if target[0].footnotes != t.text:
            self.stops("9c", f"{code}: footnote is {target[0].footnotes!r}; the edit token is {t.text!r}")
            return
        target[0].footnote_edit = True
        t.owner = (target[0], "footnote_codes_raw")
        line = self.line_of(target[0])
        rec["owner"] = {"row_kind": target[0].out_kind, "line_identifier": line.line_id, "line_title": line.title,
                        "text": target[0].label, "field": "footnote_codes_raw", "in_place_edit": True}

    def exception_evidence(self, number, code, t, e, rec):
        rec["owner"] = None

    def assign(self, row, lane, token, rec):
        k = (id(row), lane)
        if k in self.cell_owner:
            self.stops("5d", f"{row.page_code}: two edit tokens own {row.title or row.label!r} lane {lane}")
            return
        self.cell_owner[k] = token
        token.owner = (row, "lane_" + lane)
        line = self.line_of(row)
        rec["owner"] = {"row_kind": row.out_kind, "line_identifier": line.line_id, "line_title": line.title,
                        "text": row.label if row.kind in ("adjustment", "general_provision") else "",
                        "lane": lane, "role": row.out_kind}

    # -------------------------------------------------- values
    def value(self, row, lane, first_printed=False):
        if not first_printed and (id(row), lane) in self.cell_owner:
            v = G.value(self.cell_owner[(id(row), lane)].text)
        else:
            ts = [t for t in row.tokens if t.lane == lane and not t.edit and nz(t.text)
                  and (first_printed or t.strike != "struck")]
            if not ts:
                return None
            if len(ts) > 1:
                self.stops("5d", f"{row.page_code}: {row.title or row.label!r} lane {lane} holds {len(ts)} values")
                return None
            v = G.value(ts[0].text)
        if v == "bad":
            self.stops("3", f"{row.page_code}: {row.title or row.label!r} lane {lane} is not a number")
            return None
        return v

    def values(self):
        self.V = {id(r): {lane: self.value(r, lane) for lane in G.LANES} for r in self.rows}
        for p in self.data:
            for t in self.tokens[p.number]:
                if t.strike == "struck" and t.lane in G.LANES and isinstance(t.row, G.Row) \
                        and not t.row.superseded and (id(t.row), t.lane) not in self.cell_owner:
                    self.stops("5e", f"{t.row.page_code}: struck {t.text!r} in lane {t.lane} has no replacement")
        for r in self.rows:
            if r.kind in ("adjustment", "general_provision") and not r.superseded:
                extra = [lane for lane in G.LANES if lane not in ("f", "g") and self.V[id(r)][lane] is not None]
                if extra:
                    self.stops("6b", f"{r.page_code}: adjustment {r.label!r} prints lanes {extra}")
            if r.superseded and any(self.V[id(r)][lane] is not None for lane in G.LANES):
                self.stops("5e", f"{r.page_code}: superseded row {r.label!r} keeps a live amount")
        return not self.stops

    # -------------------------------------------------- keys (check 7)
    def key_of(self, r):
        if r.kind in ("adjustment", "general_provision"):
            return self.key_of(r.parent) + (r.kind, r.footnotes, r.label)
        if r.kind == "appropriated_base":
            return self.key_of(r.parent) + ("appropriated_base",)
        a = r.account
        base = (FORM, a["fiscal_year_program"], a["account_code_raw"], a["availability_raw"], r.organization)
        if r.out_kind in ("line", "parent"):
            ba = "" if r.kind == "org_header" else r.budget_activity
            return base + (ba, r.out_kind, "", r.line_id, r.title)
        return base + (r.budget_activity if r.subtype == "budget_activity" else "", r.kind, r.subtype, r.title)

    def keys(self):
        self.ids = {}
        groups = {"line": [r for r in self.rows if r.out_kind in ("line", "parent")],
                  "adjustment": [a for o in self.owners for a in o.live_adjustments],
                  "control": [r for r in self.rows if r.kind in ("subtotal", "grand_total", "financing")],
                  "appropriated_base": [r for r in self.rows if r.kind == "appropriated_base"
                                        and r.parent.out_kind != "repeated_blank_line"]}
        seen = {}
        for name, rows in groups.items():
            for k, n in Counter(self.key_of(r) for r in rows).items():
                if n > 1:
                    self.stops("7", f"{name} key repeats {n} times: {k}")
            for r in rows:
                k = self.key_of(r)
                rid = record_id(k)
                if seen.setdefault(rid, k) != k:
                    self.stops("7", f"record_id {rid} collides")
                self.ids[id(r)] = rid
        return not self.stops

    # -------------------------------------------------- arithmetic (checks 4 to 6, 5b to 5f)
    def arithmetic(self):
        stops, V = self.stops, self.V
        expected = {(d["page_code"], d["line_identifier"], d["row_kind"], d["lane"]): d
                    for d in self.exceptions.get("diagnostics", [])}
        used = Counter()
        self.first_printed = []
        for r in self.owners:
            v = V[id(r)]
            if z(v["c"]) + z(v["e"]) + z(v["g"]) != z(v["i"]):
                stops("4", f"{r.page_code} {r.line_id} {r.title!r}: c + e + g = "
                           f"{z(v['c']) + z(v['e']) + z(v['g'])}, i = {v['i']}")
            if any(v[lane] is not None for lane in G.QUANTITY_LANES) and z(v["b"]) + z(v["d"]) + z(v["f"]) != z(v["h"]):
                stops("4", f"{r.page_code} {r.line_id} {r.title!r}: quantities b + d + f differ from h")
            adj = r.live_adjustments
            if sum(z(V[id(a)]["g"]) for a in adj) != z(v["g"]):
                stops("5", f"{r.page_code} {r.line_id} {r.title!r}: adjustments sum to "
                           f"{sum(z(V[id(a)]['g']) for a in adj)}, g = {v['g']}")
            if (any(V[id(a)]["f"] is not None for a in adj) or v["f"] is not None) \
                    and sum(z(V[id(a)]["f"]) for a in adj) != z(v["f"]):
                stops("4b", f"{r.page_code} {r.line_id} {r.title!r}: adjustment quantities do not sum to f")
            for b in r.base_rows:
                for lane in G.LANES:
                    if V[id(b)][lane] == v[lane]:
                        continue
                    k = (b.page_code, r.line_id, "appropriated_base", lane)
                    d = expected.get(k)
                    if d and d["published"] == V[id(b)][lane] and d["line"] == v[lane]:
                        used[k] += 1
                        self.diagnostics.append({"kind": "as_printed_mismatch_non_additive_row", **d})
                    else:
                        stops("5", f"{b.page_code} {r.line_id} {r.title!r}: appropriated-base lane {lane} is "
                                   f"{V[id(b)][lane]}, the line is {v[lane]}")
            rows = [r] + r.base_rows + r.adjustments
            if any((id(x), lane) in self.cell_owner for x in rows for lane in G.LANES) or \
                    any(t.strike == "struck" for x in rows for t in x.tokens):
                fp = {lane: self.value(r, lane, first_printed=True) for lane in G.AMOUNT_LANES}
                self.first_printed.append({
                    "page_code": r.page_code, "line_identifier": r.line_id, "title": r.title,
                    "first_printed": fp, "owned": {lane: v[lane] for lane in G.AMOUNT_LANES},
                    "first_printed_c_plus_e_plus_g_equals_i": z(fp["c"]) + z(fp["e"]) + z(fp["g"]) == z(fp["i"]),
                    "first_printed_adjustments_g": sum(z(self.value(a, "g", first_printed=True))
                                                       for a in r.adjustments)})
        for k, d in expected.items():
            if used[k] != 1:
                stops("9c", f"diagnostic entry {d['id']} matched {used[k]} cells, expected 1")
        for r in self.rows:
            if r.out_kind == "parent" and any(V[id(r)][lane] is not None for lane in G.LANES):
                for lane in G.LANES:
                    if z(V[id(r)][lane]) != sum(z(V[id(c)][lane]) for c in r.children):
                        stops("5c", f"{r.page_code}: parent {r.title!r} lane {lane} is not the sum of its children")
        self.controls()

    def controls(self):
        stops, V = self.stops, self.V
        entries = {(d["page_code"], d["control_title"], d["lane"]): d for d in self.differences.get("entries", [])}
        used = Counter()
        self.sums, self.rounding = {}, {}
        accounts = defaultdict(list)
        for r in self.rows:
            accounts[(r.account["account_code_raw"], r.account["availability_raw"],
                      r.account["fiscal_year_program"])].append(r)
        self.accounts = accounts
        for acct, rs in accounts.items():
            owners = [r for r in rs if r.out_kind == "line"]
            gts = [r for r in rs if r.kind == "grand_total"]
            if len(gts) != 1:
                stops("6", f"account {acct}: {len(gts)} grand totals")
            for r in rs:
                if r.kind == "subtotal" and r.subtype == "budget_activity":
                    ba = re.match(r"Subtotal Budget Activity (\w+):", r.title).group(1)
                    group = [o for o in owners if o.budget_activity == ba and o.organization == r.organization]
                    adj = sum(z(V[id(a)]["g"]) for o in group for a in o.live_adjustments)
                    if adj != sum(z(V[id(o)]["g"]) for o in group):
                        stops("5b", f"{r.page_code} {r.title!r}: adjustments sum to {adj}, the lines' g to "
                                    f"{sum(z(V[id(o)]['g']) for o in group)}")
                elif r.kind == "subtotal":
                    group = [o for o in owners if o.organization == r.title[len("Subtotal "):]]
                elif r.kind == "grand_total":
                    group = owners
                else:
                    continue
                if not group:
                    stops("6", f"{r.page_code} {r.title!r} covers no lines")
                sums = {}
                for lane in G.LANES:
                    total = sum(z(V[id(o)][lane]) for o in group)
                    sums[lane] = total
                    printed = V[id(r)][lane]
                    if lane in G.QUANTITY_LANES:
                        if printed is not None:
                            stops("6", f"{r.page_code} {r.title!r} prints a quantity in lane {lane}")
                        continue
                    if total == z(printed):
                        continue
                    d = entries.get((r.page_code, r.title, lane))
                    if d and d["printed"] == printed and d["line_sum"] == total:
                        used[(r.page_code, r.title, lane)] += 1
                        self.rounding[(id(r), lane)] = d["id"]
                    else:
                        stops("6", f"{r.page_code} {r.title!r} lane {lane}: the lines sum to {total}, "
                                   f"printed {printed}")
                self.sums[id(r)] = sums
            fin = defaultdict(list)
            for r in rs:
                if r.kind == "financing":
                    fin[r.subtype].append(r)
            if [len(fin[k]) for k in ("heading", "appropriation", "total_financing")] != [1, 1, 1] or len(gts) != 1:
                stops("6", f"account {acct}: the Financing section is incomplete")
                continue
            gt, ap, tf, gps = gts[0], fin["appropriation"][0], fin["total_financing"][0], fin["general_provision"]
            gp = sum(z(V[id(x)]["g"]) for x in gps)
            for lane in G.AMOUNT_LANES:
                if V[id(tf)][lane] != V[id(gt)][lane]:
                    stops("6", f"{tf.page_code}: TOTAL FINANCING lane {lane} is {V[id(tf)][lane]}, "
                               f"the grand total {V[id(gt)][lane]}")
            if gps:
                if z(V[id(ap)]["g"]) + gp != z(V[id(gt)]["g"]) or z(V[id(ap)]["i"]) + gp != z(V[id(tf)]["i"]):
                    stops("6", f"{tf.page_code}: the appropriation plus general provisions does not tie")
                if len(fin["gp_reductions_subtotal"]) != 1 or len(fin["gp_subtotal"]) != 1:
                    stops("6", f"{tf.page_code}: general-provision subtotals missing")
                for sub in fin["gp_reductions_subtotal"] + fin["gp_subtotal"]:
                    if z(V[id(sub)]["i"]) != gp:
                        stops("6", f"{sub.page_code}: {sub.title!r} is {V[id(sub)]['i']}, the general "
                                   f"provisions sum to {gp}")
            elif any(V[id(ap)][lane] != V[id(gt)][lane] for lane in G.AMOUNT_LANES):
                stops("6", f"{ap.page_code}: the appropriation differs from the grand total with no general "
                           f"provisions")
        for k, d in entries.items():
            if used[k] != 1:
                stops("6", f"published difference {d['id']} matched {used[k]} controls, expected 1")

    # -------------------------------------------------- two readers (checks 3, 6b, 9)
    def cell_key(self, t):
        if isinstance(t.row, G.Row):
            return ("row", t.row.seq, t.lane or "a")
        return (str(t.row), round(t.baseline), t.lane or "a")

    def readers(self):
        stops = self.stops
        self.reader_counts = {}
        for p in self.data:
            n = p.number
            toks = [t for t in self.tokens[n] if nz(t.text) and id(t) not in self.dupes]
            mine = defaultdict(list)
            for t in toks:
                mine[self.cell_key(t)].append(t)

            def assign(box):
                cy = (box.y0 + box.y1) / 2
                hits = [t for t in toks if min(box.x1, t.x1) - max(box.x0, t.x0) > 0.3 * min(box.x1 - box.x0, t.x1 - t.x0)
                        and t.y0 - 0.8 <= cy <= t.y1 + 0.8]
                keys = {self.cell_key(t) for t in hits}
                return (keys.pop(), max(t.baseline for t in hits)) if len(keys) == 1 else (None, len(keys))

            for reader, items in (("pdftotext", self.words[n - 1]["words"]), ("pdftohtml", self.runs[n - 1]["runs"])):
                theirs = defaultdict(list)
                skip = self.dupe_runs[n] if reader == "pdftohtml" else 0
                for item in items:
                    if not nz(item.text):
                        continue
                    k, line = assign(item)
                    if k is None:
                        stops("3", f"page {n}: {reader} text {item.text!r} at {r2(item.x0)}, {r2(item.y0)} "
                                   f"{'matches no' if line == 0 else 'straddles more than one'} pdfminer cell")
                        continue
                    theirs[k].append((line, item))
                for k in sorted(set(mine) | set(theirs), key=str):
                    a_items = sorted(mine[k], key=lambda t: (-round(t.baseline, 1), t.x0))
                    b_items = [i for _, i in sorted(theirs[k], key=lambda q: (-round(q[0], 1), q[1].x0))]
                    a, b = nz("".join(t.text for t in a_items)), nz("".join(i.text for i in b_items))
                    if a != b and skip and b == a + a and all(t.edit for t in a_items):
                        skip -= 1            # the collapsed duplicate: pdftohtml reports both drawings
                        b_items, b = b_items[:1], a
                    if a != b:
                        stops("3", f"page {n} cell {k}: pdfminer {a!r}, {reader} {b!r}")
                        continue
                    if reader == "pdftohtml":
                        ca = self.colour_runs([(t.text, t.hex) for t in a_items])
                        cb = self.colour_runs([(i.text, i.hex) for i in b_items])
                        if ca != cb:
                            stops("9", f"page {n} cell {k}: colours pdfminer {ca}, pdftohtml {cb}")
                if skip:
                    stops("3", f"page {n}: the collapsed duplicate is not reported twice by pdftohtml")
            for t in toks:
                if not t.resolved:
                    stops("9", f"page {n}: {t.text!r} has an unresolved colour space {t.space!r}")
            adj = [r for r in self.rows if r.page == n and r.kind in ("adjustment", "general_provision")]
            self.reader_counts[n] = len(adj)
        return not stops

    @staticmethod
    def colour_runs(items):
        out = []
        for text, colour in items:
            s = nz(text)
            if not s:
                continue
            if out and out[-1][1] == colour:
                out[-1] = (out[-1][0] + s, colour)
            else:
                out.append((s, colour))
        return out

    # -------------------------------------------------- check 10 (diagnostic only)
    def compare_sidecars(self):
        """Check 10, a diagnostic: lane i against FY26 enacted columns already committed.
        R-1 lines join on (account, program element). DD 1414 prints O&M at budget-activity grain,
        so O-1 rows are summed by (account, budget activity) and joined to BA-grain lines."""
        out = {}
        lines = {(r.account["account_code_raw"], r.line_id): r for r in self.owners if r.line_id}
        grain = Counter((r.account["account_code_raw"], r.budget_activity) for r in self.owners if not r.line_id)
        ba_lines = {(r.account["account_code_raw"], r.budget_activity): r for r in self.owners
                    if not r.line_id and grain[(r.account["account_code_raw"], r.budget_activity)] == 1}

        def read(path):
            with path.open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))

        def compare(rows, index, label):
            counts, differences = Counter(), []
            for k, theirs in rows:
                hit = index.get(k)
                if hit is None:
                    counts["sidecar_rows_with_no_dd1414_line"] += 1
                    continue
                ours = self.V[id(hit)]["i"]
                if theirs == ours:
                    counts["equal"] += 1
                else:
                    counts["different"] += 1
                    differences.append({"account_code_raw": k[0], label: k[1], "dd1414_lane_i": ours,
                                        "sidecar": theirs})
            return {"counts": dict(sorted(counts.items())), "differences": sorted(differences, key=lambda d: (d["account_code_raw"], d[label]))}

        r1 = ROOT / "data/r1/pb2027/detail_in_title.csv"
        if r1.exists():
            rows = [((row["appropriation"], row["program_element"]),
                     int(row["fy26_discretionary_enacted"]) if row["fy26_discretionary_enacted"] else None)
                    for row in read(r1)]
            out["r1_pb2027_fy26_discretionary_enacted"] = {
                "status": "compared on (account code, line identifier)",
                **compare(rows, lines, "line_identifier")}
        else:
            out["r1_pb2027_fy26_discretionary_enacted"] = {"status": "not compared: sidecar missing"}
        o1 = ROOT / "data/o1/pb2027_candidate/detail_candidate.csv"
        if o1.exists():
            sums = defaultdict(list)
            for row in read(o1):
                v = row["fy26_discretionary_enacted"]
                sums[(row["account_raw"], row["activity_raw"])].append(int(v) if v else None)
            rows = [(k, None if all(v is None for v in vs) else sum(v or 0 for v in vs))
                    for k, vs in sorted(sums.items())]
            out["o1_pb2027_fy26_discretionary_enacted"] = {
                "status": "O-1 detail summed by (account code, budget activity), compared with BA-grain lines",
                **compare(rows, ba_lines, "budget_activity")}
        else:
            out["o1_pb2027_fy26_discretionary_enacted"] = {"status": "not compared: sidecar missing"}
        out["m1_pb2027_milpers_navy"] = {
            "status": "compared in tests/fixtures/dd1414_fy2026_gold.json, entry M1-N: PB27 M-1 printed page 15, "
                      "Total Direct - Military Personnel, Navy, FY2026 discretionary enacted, against N-1 grand total "
                      "lane i (value sourced by the reviewer; M-1 is not parsed in the repo, DBDP-130)"}
        out["lane_c_against_fy26_request"] = {
            "status": "not compared: no FY26 request sidecar keyed to DD 1414 lines is committed"}
        return out

    # -------------------------------------------------- run
    def run(self):
        for step in (self.inputs, self.read, self.parse, self.strikes, self.finalize_rows, self.edits, self.values):
            if not step():
                return False
        self.keys()             # a key stop does not hide the checks after it
        self.arithmetic()
        self.readers()
        return not self.stops


# ------------------------------------------------------------------ outputs

def csv_bytes(header, rows):
    handle = io.StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


ACCOUNT_HEADER = ["form", "fiscal_year_program", "account_code_raw", "availability_raw", "account_title"]


def account_fields(r):
    a = r.account
    return [FORM, a["fiscal_year_program"], a["account_code_raw"], a["availability_raw"], a["account_title"]]


def outputs(b):
    V = b.V
    order = lambda r: r.seq
    lines = []
    for r in sorted((r for r in b.rows if r.out_kind in ("line", "parent")), key=order):
        is_line = r.out_kind == "line"
        parent = r.parent if r.kind == "line" and r.parent is not None else None
        edited = is_line and any((id(x), lane) in b.cell_owner for x in [r] + r.base_rows for lane in G.LANES)
        lines.append([b.ids[id(r)]] + account_fields(r) + [
            r.organization, "" if r.kind == "org_header" else r.budget_activity,
            "" if r.kind == "org_header" else r.ba_title, r.out_kind, "", r.line_id, r.title,
            "true" if is_line else "false", b.ids[id(parent)] if parent else ""] +
            [num(V[id(r)][lane]) if is_line else "" for lane in G.LANES] +
            [len(r.live_adjustments) if is_line else "", "true" if edited else "false",
             r.page, r.page_code, r.account["volume"]])
    adjustments = []
    for o in sorted(b.owners, key=order):
        for a in o.live_adjustments:
            edited = any((id(a), lane) in b.cell_owner for lane in G.LANES)
            adjustments.append([b.ids[id(a)], b.ids[id(o)], a.kind, a.footnotes,
                                "true" if a.footnote_edit else "false", a.label,
                                num(V[id(a)]["f"]), num(V[id(a)]["g"]), "true" if edited else "false",
                                a.page, a.page_code])
    controls = []
    for r in sorted((r for r in b.rows if r.kind in ("subtotal", "grand_total", "financing")), key=order):
        sums = b.sums.get(id(r))
        flags = ";".join(f"{lane}:{b.rounding[(id(r), lane)]}" for lane in G.LANES if (id(r), lane) in b.rounding)
        controls.append([b.ids[id(r)]] + account_fields(r) + [
            r.organization, r.budget_activity if r.subtype == "budget_activity" else "", r.kind, r.subtype, r.title,
            "false"] + [num(V[id(r)][lane]) for lane in G.LANES] +
            [num(sums[lane]) if sums and lane in G.AMOUNT_LANES else "" for lane in G.LANES] +
            [flags, r.page, r.page_code])
    cells = []
    for p in b.data:
        code = b.info[p.number]["hdr"]["page_code"]
        words, runs = b.words[p.number - 1]["words"], b.runs[p.number - 1]["runs"]
        for t in sorted(b.tokens[p.number], key=lambda t: (-R.q2(t.baseline), R.q2(t.x0), t.text)):
            if not nz(t.text):
                continue
            row = t.row if isinstance(t.row, G.Row) else None
            if row is None:
                kind, rid, line_rid = str(t.row or "floating"), "", ""
            else:
                kind = row.out_kind + (" (superseded)" if row.superseded else "")
                rid = b.ids.get(id(row), "")
                line = b.line_of(row)
                line_rid = b.ids.get(id(line), "") if line is not None else ""
            owner_rid, owner_field = (b.ids.get(id(t.owner[0]), ""), t.owner[1]) if t.owner else ("", "")
            mw = [w for w in words if t.x0 - 0.5 <= (w.x0 + w.x1) / 2 <= t.x1 + 0.5
                  and t.y0 - 0.8 <= (w.y0 + w.y1) / 2 <= t.y1 + 0.8]
            mr = [x for x in runs if min(x.x1, t.x1) - max(x.x0, t.x0) > 0 and t.y0 - 0.8 <= (x.y0 + x.y1) / 2 <= t.y1 + 0.8]
            marks = t.strike_evidence.get("candidates", []) if t.strike == "struck" else []
            parsed = G.value(t.text) if t.lane in G.LANES else None
            cells.append([p.number, code, kind, rid, line_rid, t.lane, t.text,
                          "" if parsed in (None, "bad") else parsed,
                          r2(t.x0), r2(t.y0), r2(t.x1), r2(t.y1), r2(t.baseline), t.font, r2(t.size),
                          "true" if t.bold else "false", t.space, " ".join(f"{c:g}" for c in t.components), t.hex,
                          "true" if t.resolved else "false", "true" if t.edit else "false", t.strike,
                          ";".join(sorted({m["hex"] for m in marks})), t.disposition, t.exception_id,
                          owner_rid, owner_field,
                          " ".join(w.text for w in sorted(mw, key=lambda w: w.x0)),
                          " ".join(nz(x.text) for x in sorted(mr, key=lambda x: x.x0)),
                          ";".join(sorted({x.hex for x in mr}))])
    return {
        "baseline_lines.csv": csv_bytes(
            ["record_id"] + ACCOUNT_HEADER + ["organization", "budget_activity", "budget_activity_title", "row_kind",
                                              "printed_line", "line_identifier", "title_norm", "is_additive",
                                              "parent_record_id"] + list(LANE_COLUMNS) +
            ["adjustment_count", "edited", "page", "page_code", "volume"], lines),
        "adjustments.csv": csv_bytes(
            ["record_id", "parent_record_id", "row_kind", "footnote_codes_raw", "footnote_code_edited", "text_norm",
             "quantity_lane_f", "amount_lane_g", "edited", "page", "page_code"], adjustments),
        "published_controls.csv": csv_bytes(
            ["record_id"] + ACCOUNT_HEADER + ["organization", "budget_activity", "row_kind", "subtype",
                                              "title_norm", "is_additive"] + list(LANE_COLUMNS) +
            [f"line_sum_{lane}" for lane in G.LANES] + ["published_rounding", "page", "page_code"], controls),
        "source_cells.csv": csv_bytes(
            ["page", "page_code", "row_kind", "row_record_id", "line_record_id", "field", "raw_text", "parsed_value",
             "x0", "y0", "x1", "y1", "baseline", "font", "size", "bold", "colour_space", "colour_raw", "colour_hex",
             "colour_resolved", "edit", "strike", "strike_hex", "disposition", "exception_id", "owner_record_id",
             "owner_field", "pdftotext_text", "pdftohtml_text", "pdftohtml_hex"], cells),
    }


EDIT_FINDING = (
    "In this edition only: Acrobat text edits appear on A-58 (red Arial runs replacing struck values, and one "
    "black amount in its own font subset) and on AF-43 (one black footnote code in its own font subset). Red "
    "here marks a published correction. It is not a rule for other forms or editions and not a funding-type "
    "classification; B4 does not classify (c10824 section D).")


def provenance(b, files, exceptions_bytes, differences_bytes):
    kinds = Counter(r.out_kind + (" (superseded)" if r.superseded else "") for r in b.rows)
    census = Counter((t.hex, t.font) for p in b.data for t in b.tokens[p.number] if nz(t.text))
    edits = Counter((rec["page_code"], rec["hex"], rec["font"]) for rec in b.edit_records)
    return {
        "ticket": "DBDP-134",
        "design_comments": DESIGN,
        "source": {
            "file": SOURCE_FILE, "official_url": SOURCE_URL, "url_receipt": "DBDP-89 c10373", **PIN,
            "delivered": "branch source/dd1414-fy26 commit 893c2ef1189b2e07150923131d81484d233f35a9 (never "
                         "merged); receipt DBDP-134 c10830",
            "http_last_modified_seen_by_peter": None,
            "acquisition_date": None,
            "open_items": [
                "Peter's download Last-Modified and acquisition date are not recorded on the ticket.",
                "The DBDP-89 c10373 survey (2026-07-15) saw Last-Modified 2026-03-05; this edition's ModDate is "
                "2026-08-10, so the published file was revised after that survey."],
        },
        "readers": {"pdfminer.six": PDFMINER, "poppler": POPPLER,
                    "poppler_tools": ["pdftotext -bbox-layout -cropbox", "pdftohtml -xml -zoom 1 -noroundcoord",
                                      "pdftoppm -cropbox -r 300"],
                    "frame": "crop-local points, origin CropBox lower-left, y up, half-even to 0.01 pt"},
        "lane_catalog": {lane: G.LANE_MEANING[lane] for lane in G.LANES},
        "pages": {"total": len(b.pages), "by_class": dict(sorted(Counter(b.classes.values()).items())),
                  "non_data_boxes_differ": {str(k): v for k, v in sorted(b.odd_boxes.items())}},
        "row_kinds": dict(sorted(kinds.items())),
        "counts": {"accounts": len(b.accounts), "additive_lines": len(b.owners),
                   "parents": sum(1 for r in b.rows if r.out_kind == "parent"),
                   "adjustments": sum(len(o.live_adjustments) for o in b.owners),
                   "superseded_rows": sum(1 for r in b.rows if r.superseded),
                   "published_controls": sum(1 for r in b.rows if r.kind in ("subtotal", "grand_total", "financing")),
                   "source_cells": files["source_cells.csv"].count(b"\n") - 1},
        "body_style": {"colours": sorted(b.colours), "fonts": sorted(b.fonts),
                       "rule": "drawn on at least two data pages (c10824 section B)"},
        "colour_census": [{"hex": h, "font": f, "tokens": n} for (h, f), n in sorted(census.items())],
        "edit_finding": EDIT_FINDING,
        "edit_census": [{"page_code": k[0], "hex": k[1], "font": k[2], "tokens": n} for k, n in sorted(edits.items())],
        "edits": b.edit_records,
        "strikes": {"struck_tokens": len(b.strike_records),
                    "by_page": dict(sorted(Counter(s["page_code"] for s in b.strike_records).items())),
                    "tokens": b.strike_records},
        "first_printed": b.first_printed,
        "diagnostics": b.diagnostics,
        "repeated_blank_lines": b.repeat_records,
        "published_rounding": sorted(({"record_id": b.ids[rid], "lane": lane, "id": did}
                                      for (rid, lane), did in b.rounding.items()),
                                     key=lambda d: (d["id"], d["lane"])),
        "reader_agreement": {"data_pages": len(b.reader_counts),
                             "adjustment_rows": sum(b.reader_counts.values()),
                             "rule": "every pdftotext word and pdftohtml run maps to exactly one pdfminer cell "
                                     "and each cell's text, whitespace removed, is identical (checks 3, 6b, 9)"},
        "check_10_diagnostic": b.compare_sidecars(),
        "inputs": {EDIT_EXCEPTIONS: hashlib.sha256(exceptions_bytes).hexdigest(),
                   PUBLISHED_DIFFERENCES: hashlib.sha256(differences_bytes).hexdigest()},
        "outputs": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }


README = """# FY2026 DD 1414 enacted base (DBDP-134)

Built by `tools/build_dd1414_fy2026.py` from the pinned FY 2026 DD 1414 Base for
Reprogramming Actions PDF (SHA-256 `{sha}`). The PDF is not committed, and the
build stops on any other file.

## Files

| File | Grain | Additive |
| --- | --- | --- |
| `baseline_lines.csv` | one row per `line` or `parent` (heading, no amounts) | only rows with `is_additive = true` |
| `adjustments.csv` | one row per congressional adjustment or general provision, with its parent line | lane g sums to its line's lane g |
| `published_controls.csv` | printed subtotals, grand totals and Financing rows, with the line sums beside them | no, tie-out only |
| `source_cells.csv` | one row per text token on a data page: both readers, font, size, colour, strike, edit disposition | no |
| `provenance.json` | source pin, readers, lane catalog, counts, colour and edit census, diagnostics, file hashes | |
| `edit_exceptions.json` | reviewed dispositions for edit tokens (committed input) | |
| `published_differences.json` | the 12 printed controls that miss their line sum by rounding (committed input) | |

## Lanes

Lane columns keep the form's letters. c is the request presented to Congress. e and g are
changes, not stages. i is the base after congressional and presidential action (enacted).
b, d, f and h are the matching quantities. No lane is relabeled or combined. Blank stays
blank and a printed zero stays zero.

## Keys

`record_id` is a hash of content fields only: form, fiscal year program, account code and
availability as printed, organization, budget activity, row kind, printed line (this edition
prints none), line identifier and normalized title. An adjustment adds its row kind, footnote
codes and text to its parent's key. A repeated key stops the build, with one reviewed
exception: on N-29, "CVN Refueling Overhauls" (1611N 2026/2030, BA 02) prints a second time
blank in every lane with no adjustments. That repeat stays in `source_cells.csv` as printed
and is left out of `baseline_lines.csv` (Peter, DBDP-134 c10840). If it ever shows a value,
the build stops.

## What not to sum

Sum only `baseline_lines.csv` rows with `is_additive = true`, or `adjustments.csv` lane g.
Never add `published_controls.csv` rows to anything. Appropriated-base rows repeat their line
and appear in `source_cells.csv` only.

## Edits and strikes in this edition

{finding}

Struck values never own an amount. A row whose title is struck is superseded and appears only in
`source_cells.csv`. `provenance.json` lists each edit token with its owner, the first-printed
values of edited lines, and each reviewed exception with its approval comment.

Twelve printed controls in RDT&E Navy and RDT&E Defense-Wide miss the sum of their lines by 1 or 2
(rounding as published). They are published as printed and flagged in `published_rounding`
(Peter, DBDP-134 c10838). Any other difference stops the build.

## Rebuild

```
python3 tools/build_dd1414_fy2026.py --pdf <path to the pinned PDF>
python3 tools/build_dd1414_fy2026.py --pdf <path to the pinned PDF> --check
```

Needs Poppler {poppler} and pdfminer.six {pdfminer} (requirements.txt). `--check` rebuilds in
memory and stops unless every file is byte-identical to the committed one.
"""


def build(pdf, destination=DEFAULT):
    destination = Path(destination)
    exceptions_bytes = (destination / EDIT_EXCEPTIONS).read_bytes()
    differences_bytes = (destination / PUBLISHED_DIFFERENCES).read_bytes()
    b = Build(pdf, json.loads(exceptions_bytes), json.loads(differences_bytes))
    if not b.run():
        return b, None
    files = outputs(b)
    prov = provenance(b, files, exceptions_bytes, differences_bytes)
    files["provenance.json"] = (json.dumps(prov, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    files["README.md"] = README.format(sha=PIN["sha256"], finding=EDIT_FINDING, poppler=POPPLER,
                                       pdfminer=PDFMINER).encode("utf-8")
    return b, files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--destination", default=str(DEFAULT))
    parser.add_argument("--check", action="store_true", help="compare with the committed files; write nothing")
    args = parser.parse_args(argv)
    destination = Path(args.destination)
    try:
        b, files = build(args.pdf, destination)
    except R.ReadStop as stop:
        print(f"STOP: {stop}", file=sys.stderr)
        return 2
    if files is None:
        for s in b.stops.items:
            print("STOP:", s, file=sys.stderr)
        print(f"{len(b.stops.items)} stops; nothing written", file=sys.stderr)
        return 2
    if args.check:
        drift = [name for name, data in sorted(files.items())
                 if not (destination / name).exists() or (destination / name).read_bytes() != data]
        if drift:
            print("STOP: [check 8] not byte-identical: " + ", ".join(drift), file=sys.stderr)
            return 2
        print(f"check 8: {len(files)} files byte-identical")
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(files.items()):
        (destination / name).write_bytes(data)
    print(f"wrote {len(files)} files to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
