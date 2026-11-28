"""Tiny hand-written PDFs for the DBDP-134 reader and strike tests.

No PDF library is needed: each page is one uncompressed content stream using the
standard Helvetica font, so every byte of the test input is visible here.
"""


def pdf_bytes(pages):
    """pages: list of dicts with 'content' (str), optional 'media' and 'crop' boxes."""
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id = len(objects) + 1 + 2 * len(pages)
    kids = []
    for page in pages:
        data = page["content"].encode("latin-1")
        stream = add(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
        media = page.get("media", (0, 0, 612, 792))
        crop = page.get("crop", media)
        box = lambda b: ("[%s]" % " ".join(f"{v:g}" for v in b)).encode()
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox " % pages_id + box(media)
                        + b" /CropBox " + box(crop)
                        + b" /Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (font, stream)))
    assert add(b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids)
               + b"] /Count %d >>" % len(kids)) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (b"trailer\n<< /Size %d /Root %d 0 R /ID [<00112233445566778899AABBCCDDEEFF> "
            b"<00112233445566778899AABBCCDDEEFF>] >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref))
    return bytes(out)


def text(x, y, value, rgb=(0, 0, 0), size=10):
    r, g, b = rgb
    return f"BT /F1 {size} Tf {r:g} {g:g} {b:g} rg {x:g} {y:g} Td ({value}) Tj ET\n"


def line(x0, x1, y, rgb=(0, 0, 0), width=0.8):
    r, g, b = rgb
    return f"q {r:g} {g:g} {b:g} RG {width:g} w {x0:g} {y:g} m {x1:g} {y:g} l S Q\n"


def bar(x0, x1, y, rgb=(0, 0, 0), height=0.8):
    r, g, b = rgb
    return f"q {r:g} {g:g} {b:g} rg {x0:g} {y - height / 2:g} {x1 - x0:g} {height:g} re f Q\n"
