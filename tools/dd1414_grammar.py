"""Geometry and row grammar for FY2026 DD 1414 data pages (DBDP-134).

Turns the pdfminer reading of one page into tokens, column bands, physical rows
(baseline clusters) and logical rows with exactly one row_kind each
(c10752 section 6 as changed by c10764 and c10775).

Stops are collected, not raised one at a time, so a run reports every problem.
"""
from dataclasses import dataclass, field
import re

try:
    from .dd1414_read import q2
except ImportError:
    from dd1414_read import q2

LANES = ("b", "c", "d", "e", "f", "g", "h", "i")
QUANTITY_LANES = ("b", "d", "f", "h")
AMOUNT_LANES = ("c", "e", "g", "i")
LANE_MEANING = {
    "b": "Quantity, program base presented to Congress in printed justification",
    "c": "Amount, program base presented to Congress in printed justification (Budget Request stage)",
    "d": "Quantity, approved changes prior to final congressional action (a change, not a stage)",
    "e": "Amount, approved changes prior to final congressional action (a change, not a stage)",
    "f": "Quantity, changes reflecting congressional action/intent (a change, not a stage)",
    "g": "Amount, changes reflecting congressional action/intent (a change, not a stage)",
    "h": "Quantity, program base reflecting congressional/presidential action",
    "i": "Amount, program base reflecting congressional/presidential action (Enacted stage)",
}
NUMBER = re.compile(r"-?\d{1,3}(?:,\d{3})*")
BA_CODE = re.compile(r"\d\d")
FOOTNOTES = re.compile(r"\d+(?:,\d+)*")
GP = re.compile(r"(?:Sec\.|Section)\s+\d{4}\b")
AVAIL = re.compile(r"\d{4}/(?:\d{4}|XXXX)")
ACCOUNT = re.compile(r"(?P<title>.+?),? (?P<avail>\d{4}/(?:\d{4}|XXXX)) \((?P<code>[0-9A-Z]{4,6})\)")
BASE_TEXT = "FY 2026 Appropriated Base"
TOKEN_GAP = 1.5
ROW_TOLERANCE = 1.0
EDGE_MARGIN = 0.5


def norm(text):
    return " ".join(text.split())


def value(text):
    t = text.strip()
    if t == "":
        return None
    if not NUMBER.fullmatch(t):
        return "bad"
    return int(t.replace(",", ""))


@dataclass
class Token:
    glyphs: list
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    font: str
    size: float
    space: str
    components: tuple
    hex: str
    resolved: bool
    rule_x: float
    edit: bool = False
    lane: str = ""
    spans: bool = False
    near_edge: bool = False
    outside: bool = False
    row: object = None
    strike: str = ""          # struck, not_struck, ambiguous
    strike_evidence: dict = field(default_factory=dict)
    disposition: str = ""     # owner, duplicate, evidence, auto, ""
    owner: tuple = ()
    exception_id: str = ""

    @property
    def bold(self):
        return "Bold" in self.font

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2


def tokens_of(page):
    """Group glyphs into tokens: same baseline (0.01 pt), drawn in sequence, gap at
    most 1.5 pt, same font, size and colour. A pen that moves back under the PDF
    character-spacing rule (an overprint) also starts a new token."""
    rows = {}
    for order, g in enumerate(page.glyphs):
        rows.setdefault(q2(g.oy), []).append((order, g))
    out = []
    for baseline in sorted(rows, reverse=True):
        glyphs = [g for _, g in sorted(rows[baseline], key=lambda p: p[0])]
        current = [glyphs[0]]

        def close():
            text = "".join(g.text for g in current)
            if text.strip():
                lead = next(g for g in current if g.text.strip())
                core = [g for g in current if g.text.strip()]
                out.append(Token(core, text.strip(), min(g.x0 for g in core), min(g.y0 for g in core),
                                 max(g.x1 for g in core), max(g.y1 for g in core), baseline,
                                 lead.basefont or lead.font, lead.size, lead.space, lead.components, lead.hex,
                                 all(g.resolved for g in core), lead.rule_ox))
        for g in glyphs[1:]:
            p = current[-1]
            gap = g.x0 - p.x1
            rule_back = g.string_id != p.string_id and g.rule_ox < p.rule_ox + (p.x1 - p.ox) - 0.5
            if (gap > TOKEN_GAP or gap < -0.5 or rule_back or g.basefont != p.basefont or g.font != p.font or abs(g.size - p.size) > 0.01
                    or g.hex != p.hex or g.components != p.components):
                close()
                current = [g]
            else:
                current.append(g)
        close()
    return out


def body_style(data_tokens):
    """Body colours and fonts: those drawn on at least two data pages. An Acrobat
    text edit embeds its own font subset for the page it touches, so an edit is
    drawn on one page only (c10824 section B)."""
    colours, fonts = {}, {}
    for number, tokens in data_tokens.items():
        for t in tokens:
            colours.setdefault(t.hex, set()).add(number)
            fonts.setdefault(t.font, set()).add(number)
    return ({c for c, pages in colours.items() if len(pages) >= 2},
            {f for f, pages in fonts.items() if len(pages) >= 2})


def mark_edits(tokens, colours, fonts):
    for t in tokens:
        t.edit = t.hex not in colours or t.font not in fonts or not t.resolved


def edit_whitespace(page, colours, fonts):
    """Whitespace-only glyphs in an edit font or colour: kept as diagnostics."""
    return [g for g in page.glyphs if not g.text.strip()
            and ((g.basefont or g.font) not in fonts or g.hex not in colours)]


@dataclass
class Geometry:
    header_y: float
    edges: list            # (left, right) of each of the 10 vertical rules
    table_bottom: float
    bands: dict            # lane -> (x0, x1)
    a_band: tuple


def geometry_of(page, tokens, stops):
    letters = [t for t in tokens if t.text in LANES and t.bold]
    by_row = {}
    for t in letters:
        by_row.setdefault(t.baseline, []).append(t)
    rows = [v for v in by_row.values() if sorted(t.text for t in v) == list(LANES)]
    if len(rows) != 1:
        stops.append(f"page {page.number}: lane-letter header row not found exactly once")
        return None
    hdr = sorted(rows[0], key=lambda t: t.x0)
    hy = hdr[0].baseline
    thin = [v for v in page.vectors if v.kind == "rect" and v.fill and v.fill_hex == "000000"
            and (v.x1 - v.x0) < 1.5 and (v.y1 - v.y0) > 5]
    rules = sorted({(q2(v.x0), q2(v.x1)) for v in thin if v.y0 < hy < v.y1})
    if len(rules) != 10:
        stops.append(f"page {page.number}: {len(rules)} vertical rules cross the lane-letter row, expected 10")
        return None
    bands = {}
    for k, lane in enumerate(LANES):
        bands[lane] = (rules[k + 1][1], rules[k + 2][0])
        if not (bands[lane][0] < hdr[k].cx < bands[lane][1]) or hdr[k].text != lane:
            stops.append(f"page {page.number}: lane letter {lane} is not inside its ruled band")
    # The body of the table: the rule segments that run down from the header rows.
    # A continuation page that holds only footnotes has no lane rules below the
    # header: its table is empty and everything below the header is notes.
    floors = []
    for x0, x1 in rules[1:9]:
        seg = [v for v in thin if q2(v.x0) == x0 and v.y1 > hy - 4 and v.y0 < hy - 5]
        if len(seg) > 1:
            stops.append(f"page {page.number}: lane rule at {x0} has more than one body segment")
            return None
        floors.append(seg[0].y0 if seg else None)
    if all(f is None for f in floors):
        floors = [hy - 3]
    elif any(f is None for f in floors):
        stops.append(f"page {page.number}: some lane rules have no body segment")
        return None
    if max(floors) - min(floors) > 0.5:
        stops.append(f"page {page.number}: lane rules end at different heights")
        return None
    bottom = max(floors)
    return Geometry(hy, list(rules), bottom, bands, (rules[0][1], rules[1][0]))


def place(token, geo):
    """Lane of a token by its centre (c10764 section 4)."""
    if token.x1 <= geo.a_band[1] + 0.0001 and token.x0 >= geo.a_band[0]:
        token.lane = "a"
    for lane, (x0, x1) in geo.bands.items():
        if x0 <= token.cx <= x1:
            token.lane = lane
    if token.cx < geo.a_band[1] and not token.lane:
        token.lane = "a"
    if token.x0 > geo.edges[9][1] or token.x1 > geo.edges[9][1] + 0.0001:
        token.outside = True
    for left, right in geo.edges[1:9]:
        if token.x0 < left and token.x1 > right:
            token.spans = True
        if token.lane != "a" and (abs(token.cx - left) <= EDGE_MARGIN or abs(token.cx - right) <= EDGE_MARGIN):
            token.near_edge = True


@dataclass
class Cluster:
    tokens: list
    top: float
    bottom: float

    @property
    def a(self):
        return sorted((t for t in self.tokens if t.lane == "a"), key=lambda t: t.x0)

    @property
    def lanes(self):
        return [t for t in self.tokens if t.lane in LANES]


def clusters_of(tokens):
    """Baseline clusters, 1.0 pt single linkage, top-down."""
    ordered = sorted(tokens, key=lambda t: -t.baseline)
    out = []
    for t in ordered:
        if out and out[-1].bottom - t.baseline <= ROW_TOLERANCE:
            out[-1].tokens.append(t)
            out[-1].bottom = t.baseline
        else:
            out.append(Cluster([t], t.baseline, t.baseline))
    return out


@dataclass
class Row:
    kind: str
    page: int
    page_code: str
    clusters: list
    title: str = ""
    ba: str = ""
    line_id: str = ""
    footnotes: str = ""
    label: str = ""
    organization: str = ""
    budget_activity: str = ""
    ba_title: str = ""
    account: dict = None
    parent: object = None
    children: list = field(default_factory=list)
    adjustments: list = field(default_factory=list)
    base_rows: list = field(default_factory=list)
    superseded: bool = False
    additive: bool = False
    subtype: str = ""
    key: tuple = ()
    seq: int = 0

    @property
    def tokens(self):
        return [t for c in self.clusters for t in c.tokens]

    def lane_tokens(self, lane):
        return [t for t in self.tokens if t.lane == lane and not t.edit]

    @property
    def top(self):
        return max(c.top for c in self.clusters)

    @property
    def bottom(self):
        return min(c.bottom for c in self.clusters)


KEYWORD_PREFIX = ("Budget Activity ", "Subtotal ", "Grand Total ", "TOTAL FINANCING", "APPROPRIATION, P.L.",
                  "Financing", "Footnotes:", BASE_TEXT)


def a_text(cluster):
    return norm(" ".join(t.text for t in cluster.a))


def header_of(page, tokens, geo, stops):
    """Account header and footer of one data page."""
    above = [t for t in tokens if t.baseline > geo.header_y + 1]
    lab = [t for t in above if t.text.startswith("Appropriation Account Title")]
    fy_lab = [t for t in above if t.text.startswith("Fiscal Year Program")]
    if len(lab) != 1 or len(fy_lab) != 1:
        stops.append(f"page {page.number}: account header labels not found")
        return None
    below = sorted((t for t in above if lab[0].baseline - 20 < t.baseline < lab[0].baseline - 5),
                   key=lambda t: (-t.baseline, t.x0))
    acct = [t for t in below if t.x0 < 500]
    fy = [t for t in below if t.x0 > 540]
    text = norm(" ".join(t.text for t in acct))
    m = ACCOUNT.fullmatch(text)
    if not m or len(fy) != 1 or not re.fullmatch(r"\d{4}", fy[0].text):
        stops.append(f"page {page.number}: account header {text!r} / fiscal year not parsed")
        return None
    foot = sorted((t for t in tokens if t.baseline < 25), key=lambda t: t.x0)
    if len(foot) != 3 or foot[0].text != "DD 1414":
        stops.append(f"page {page.number}: footer not parsed")
        return None
    return {"account_title": m.group("title"), "availability_raw": m.group("avail"),
            "account_code_raw": m.group("code"), "account_header_raw": text,
            "fiscal_year_program": fy[0].text, "volume": foot[1].text, "page_code": foot[2].text,
            "header_tokens": acct + fy, "footer_tokens": foot}


def parse_code_cluster(cluster):
    """BA code (+ optional line identifier) at the left of column a."""
    a = cluster.a
    if not a or not BA_CODE.fullmatch(a[0].text) or a[0].x0 > 70 or not a[0].bold:
        return None
    rest = a[1:]
    line_id = ""
    if rest and rest[0].x0 < 100 and rest[0].bold and " " not in rest[0].text:
        line_id = rest[0].text
        rest = rest[1:]
    return a[0].text, line_id, rest


class PageGrammar:
    """Row grammar. State (account, organization, budget activity, current owner)
    runs across pages of one account."""

    def __init__(self):
        self.rows = []
        self.state = {}
        self.stops = []
        self.seq = 0

    def stop(self, page, cluster, message):
        self.stops.append(f"page {page.number} y {cluster.top:.2f}: {message}: {a_text(cluster)!r}")

    def new(self, kind, page, hdr, clusters, **kw):
        self.seq += 1
        row = Row(kind, page.number, hdr["page_code"], list(clusters), account=hdr, seq=self.seq, **kw)
        row.organization = self.state.get("org", "")
        row.budget_activity = self.state.get("ba", "")
        row.ba_title = self.state.get("ba_title", "")
        for c in clusters:
            for t in c.tokens:
                t.row = row
        self.rows.append(row)
        return row

    def absorb(self, row, cluster):
        row.clusters.append(cluster)
        for t in cluster.tokens:
            t.row = row

    def page(self, page, hdr, clusters, geo):
        key = (hdr["account_code_raw"], hdr["availability_raw"], hdr["fiscal_year_program"])
        if self.state.get("account") != key:
            self.state = {"account": key, "org": "", "ba": "", "ba_title": "", "owner": None, "ba_row": None,
                          "open": None, "last": None, "section": "body"}
        st = self.state
        st["open"] = None
        floating = []
        for cl in clusters:
            if cl.top > geo.header_y - 1 or cl.top < 25:
                continue
            a = cl.a
            text = a_text(cl)
            lanes = cl.lanes
            body_lanes = [t for t in lanes if not t.edit]
            if cl.bottom < geo.table_bottom:
                # Footnote legend and notes: prose, which may run across the lane
                # columns. An amount-shaped token standing alone there is a stop.
                for t in cl.tokens:
                    t.row = "note"
                if any(t.edit for t in cl.tokens):
                    self.stop(page, cl, "edit token below the table")
                if not a and lanes and all(NUMBER.fullmatch(t.text) for t in lanes):
                    self.stop(page, cl, "amounts below the table")
                continue
            if not a and not body_lanes:
                floating.append(cl)          # edit tokens alone on a band: no row
                continue
            if any(t.outside and not t.edit for t in cl.tokens):
                self.stop(page, cl, "text outside the ruled table")
            if st["section"] == "financing":
                self.financing(page, hdr, cl, text)
                continue
            op = st["open"]
            # absorb into an open multi-cluster row
            if op is not None:
                if not a and body_lanes and not any(op.lane_tokens(t.lane) for t in body_lanes):
                    self.absorb(op, cl)
                    continue
                if op.kind == "line" and not op.ba:
                    code = parse_code_cluster(cl)
                    if code:
                        op.ba, op.line_id, rest = code
                        op.title = norm(op.title + " " + " ".join(t.text for t in rest))
                        self.absorb(op, cl)
                        continue
                if (op.kind == "line" and op.ba and a and all(t.bold for t in a) and not body_lanes
                        and not parse_code_cluster(cl) and not text.startswith(KEYWORD_PREFIX)
                        and a[0].x0 > 100):
                    op.title = norm(op.title + " " + text)
                    self.absorb(op, cl)
                    continue
                if op.kind == "grand_total" and not AVAIL.search(op.title.split()[-1] if op.title else ""):
                    if a and all(t.bold for t in a) and a[0].x0 < 70:
                        op.title = norm(op.title + " " + text)
                        self.absorb(op, cl)
                        continue
                if op.kind in ("ba_header",) and a and all(t.bold for t in a) and a[0].x0 < 70 \
                        and not text.startswith(KEYWORD_PREFIX) and not parse_code_cluster(cl) and not body_lanes:
                    op.title = norm(op.title + " " + text)
                    self.absorb(op, cl)
                    continue
                st["open"] = None
            self.body(page, hdr, cl, text)
        return floating

    def body(self, page, hdr, cl, text):
        st = self.state
        a = cl.a
        lanes = [t for t in cl.lanes if not t.edit]
        code = parse_code_cluster(cl)
        last = st["last"]
        if text.startswith("Budget Activity ") and a[0].bold and a[0].x0 < 70:
            m = re.fullmatch(r"Budget Activity (\w+): (.*)", text)
            if not m:
                return self.stop(page, cl, "budget activity heading not parsed")
            st["ba"], st["ba_title"] = m.group(1), m.group(2)
            row = self.new("ba_header", page, hdr, [cl], title=m.group(2))
            st["ba_row"] = row
            st["owner"] = row
            st["open"] = row
            st["last"] = row
            return
        if text.startswith("Subtotal ") and a[0].bold:
            if text in ("Subtotal General Provision Reductions", "Subtotal General Provisions"):
                return self.stop(page, cl, "general-provision subtotal outside Financing")
            sub = "budget_activity" if text.startswith("Subtotal Budget Activity") else "organization"
            row = self.new("subtotal", page, hdr, [cl], title=text, subtype=sub)
            if sub == "budget_activity":
                m = re.fullmatch(r"Subtotal Budget Activity (\w+): (.*)", text)
                if not m or m.group(1) != st["ba"]:
                    self.stop(page, cl, "budget activity subtotal does not match the open activity")
                st["ba"], st["ba_title"] = "", ""
            else:
                if text != "Subtotal " + st["org"]:
                    self.stop(page, cl, "organization subtotal does not match the open organization")
                st["org"] = ""
            st["ba_row"] = None
            st["owner"] = None
            st["last"] = row
            return
        if text.startswith("Grand Total ") and a[0].bold:
            row = self.new("grand_total", page, hdr, [cl], title=text)
            st["ba_row"] = None
            st["owner"] = None
            st["open"] = row
            st["last"] = row
            return
        if text == "Financing" and a[0].bold and not lanes:
            row = self.new("financing", page, hdr, [cl], title=text, subtype="heading")
            st["section"] = "financing"
            st["ba_row"] = None
            st["owner"] = None
            st["last"] = row
            return
        if text == BASE_TEXT and a[0].bold:
            owner = st["owner"]
            if owner is None or last is None or last is not owner:
                return self.stop(page, cl, "appropriated-base row without its line")
            row = self.new("appropriated_base", page, hdr, [cl], title=text, parent=owner)
            owner.base_rows.append(row)
            st["last"] = row
            st["open"] = None
            return
        if code:
            ba, line_id, rest = code
            if ba != st["ba"]:
                self.stop(page, cl, f"line code {ba} under budget activity {st['ba']!r}")
            title = norm(" ".join(t.text for t in rest))
            row = self.new("line", page, hdr, [cl], title=title, ba=ba, line_id=line_id)
            if st["ba_row"] is not None:
                # every line under an open budget-activity heading is its child, not only the first
                st["ba_row"].children.append(row)
                row.parent = st["ba_row"]
            st["owner"] = row
            st["open"] = row
            st["last"] = row
            return
        if a and all(t.bold for t in a) and a[0].x0 > 100 and not text.startswith(KEYWORD_PREFIX):
            # first title line of a line item whose code row follows
            row = self.new("line", page, hdr, [cl], title=text)
            if st["ba_row"] is not None:
                # every line under an open budget-activity heading is its child, not only the first
                st["ba_row"].children.append(row)
                row.parent = st["ba_row"]
            st["owner"] = row
            st["open"] = row
            st["last"] = row
            return
        if a and all(t.bold for t in a) and a[0].x0 < 70 and not lanes and not text.startswith(KEYWORD_PREFIX):
            # organization heading (Defense-Wide accounts)
            st["org"] = text
            st["ba"], st["ba_title"] = "", ""
            row = self.new("org_header", page, hdr, [cl], title=text)
            st["ba_row"] = None
            st["owner"] = None
            st["last"] = row
            return
        if a and not a[0].bold:
            fn, label, parts = "", "", list(a)
            if len(parts) >= 2 and FOOTNOTES.fullmatch(parts[0].text) and parts[1].text == "/":
                fn = parts[0].text
                parts = parts[2:]
            elif parts and re.fullmatch(r"(\d+(?:,\d+)*)\s*/", parts[0].text):
                fn = parts[0].text.rstrip("/ ").strip()
                parts = parts[1:]
            label = norm(" ".join(t.text for t in parts))
            if any(t.bold for t in parts):
                return self.stop(page, cl, "bold text in an adjustment row")
            # a label continuation carries no amount, an edited one included
            if not fn and not cl.lanes and last is not None and last.kind in ("adjustment", "general_provision"):
                last.label = norm(last.label + " " + label)
                self.absorb(last, cl)
                return
            owner = st["owner"]
            if owner is None or owner.kind != "line" and owner.kind != "ba_header":
                return self.stop(page, cl, "adjustment without an owning line")
            if not owner.base_rows:
                return self.stop(page, cl, "adjustment before the line's appropriated-base row")
            kind = "general_provision" if GP.match(label) else "adjustment"
            row = self.new(kind, page, hdr, [cl], label=label, footnotes=fn, parent=owner)
            owner.adjustments.append(row)
            st["last"] = row
            return
        self.stop(page, cl, "row the grammar cannot classify")

    def financing(self, page, hdr, cl, text):
        st = self.state
        a = cl.a
        lanes = [t for t in cl.lanes if not t.edit]
        if text.startswith("TOTAL FINANCING") and a and a[0].bold:
            row = self.new("financing", page, hdr, [cl], title=text, subtype="total_financing")
            st["section"] = "body"
            st["last"] = row
            return
        if text.startswith("APPROPRIATION, P.L."):
            row = self.new("financing", page, hdr, [cl], title=text, subtype="appropriation")
        elif text in ("Subtotal General Provision Reductions", "Subtotal General Provisions"):
            row = self.new("financing", page, hdr, [cl], title=text,
                           subtype="gp_reductions_subtotal" if "Reductions" in text else "gp_subtotal")
        elif GP.match(text) and a and not a[0].bold:
            row = self.new("financing", page, hdr, [cl], title=text, subtype="general_provision")
        elif not a and lanes and st["last"] is not None and st["last"].kind == "financing" \
                and not any(st["last"].lane_tokens(t.lane) for t in lanes):
            self.absorb(st["last"], cl)
            return
        else:
            return self.stop(page, cl, "row the Financing grammar cannot classify")
        st["last"] = row
