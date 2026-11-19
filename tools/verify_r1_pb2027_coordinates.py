"""Verify PB27 R-1 occurrence cells using a separate geometric extraction path."""
from collections import defaultdict
import hashlib
import re
import subprocess
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/1999/xhtml}"
COLUMN_RIGHTS = (395, 462, 520, 583, 650, 710, 771)
NUMBER = re.compile(r"-?\d+(?:,\d{3})*|\(\d+(?:,\d{3})*\)")

def check(pdf, candidate):
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest != candidate["source_sha256"]:
        raise ValueError("Candidate was not built from this PDF")
    tree = ET.fromstring(subprocess.run(
        ["pdftotext", "-bbox-layout", str(pdf), "-"],check=True,capture_output=True).stdout)
    expected = {}
    for row in candidate["detail"]:
        for o in row["source_occurrences"]:
            key = (o["physical_page"],row["printed_line"],row["program_element"],row["activity"])
            if key in expected:
                raise ValueError(f"Duplicate candidate occurrence: {key}")
            expected[key] = row["amount_k"]
    found = 0
    for page_number, page in enumerate(tree.iter(NS+"page"), 1):
        if page_number < 10:
            continue
        baselines = defaultdict(list)
        for word in page.iter(NS+"word"):
            baselines[round(float(word.get("yMin")),1)].append(
                (float(word.get("xMin")),float(word.get("xMax")),word.text))
        for baseline, words in baselines.items():
            if not 170 < baseline < 510:
                continue
            words.sort()
            if not (len(words)>=4 and words[0][0]<38 and re.fullmatch(r"\d{1,3}", words[0][2])
                    and 40<words[1][0]<57 and re.fullmatch(r"[A-Za-z0-9]{7,}", words[1][2])):
                continue
            activity = [t for x,_,t in words if 275<x<315 and re.fullmatch(r"\d{2}",t)]
            if len(activity)!=1:
                raise ValueError(f"Could not locate activity at page {page_number}, y={baseline}")
            key = (page_number,words[0][2],words[1][2],activity[0])
            values = [None]*7
            for left,right,token in words:
                if left < 330:
                    continue
                column = min(range(7),key=lambda k:abs(right-COLUMN_RIGHTS[k]))
                if not NUMBER.fullmatch(token) or values[column] is not None or abs(right-COLUMN_RIGHTS[column]) > 8:
                    raise ValueError(f"Unassignable token {token!r} at {key}")
                values[column] = int(token.replace(",","").replace("(","-").replace(")",""))
            if key not in expected or tuple(values)!=tuple(expected.pop(key)):
                raise ValueError(f"Unexpected occurrence or amount mismatch: {key}, {values}")
            found += 1
    if expected:
        raise ValueError(f"Missing occurrences: {list(expected)[:10]}")
    if found!=candidate["occurrence_count"]:
        raise ValueError(f"Count mismatch: {found}")
    return 7 * found
