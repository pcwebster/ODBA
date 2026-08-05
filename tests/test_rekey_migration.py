# =============================================================================
# ODBA -- Open Defense Budget Analytics
# tests/test_rekey_migration.py  |  DBDP-106 re-key migration suite (TC-B1-RK-01)
# =============================================================================
# Permanent verification of the P-40/R-2/OP-5 re-key (DBDP-106; design c10434,
# GATE CLEARED c10436; ACs c10381/c10384). Standalone:
#   python tests/test_rekey_migration.py
# Exit 0 = all checks hold.
#
# The PRE-re-key artifact is reproduced from git history at the pinned base
# (git show <BASE_SHA>:output/fact_budget_line_items.parquet), so the suite is
# self-contained after merge. NO prefix-equality check appears here — by
# design (AR c10431 §2 / c10436): the re-key changes key content, so the
# committed migration map + this independent fingerprint are the receipt.
#
# Row fingerprint (c10434 §5, projection bound to COLUMNS at BASE_SHA per
# c10436 note 4): all COLUMNS minus record_id (38-1=37 fields), in order;
# strings via norm_key(); floats -> '.6f' (cost columns) / '.1f'
# (budget_year); null/NaN -> ""; SHA-256 full 64-hex over \x1f-joined UTF-8.
# Independent of the key: different fields (includes costs, excludes
# record_id), different algorithm (SHA-256 vs MD5), different separator.
# =============================================================================

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import etl_budget as etl

REPO      = Path(__file__).parent.parent
BASE_SHA  = "d8f7fd6f9e45c7bf0764913e7556df6477edb759"   # DBDP-106 pinned base
# DBDP-103 note: the MAP legs below verify the historical d8f7fd6 -> dc979fa
# migration, so they read the post-state from the DBDP-106 MERGE artifact.
# Pinning both endpoints keeps this a permanent, true regression test of that
# migration — later re-keys (e.g. DBDP-103's P-40 BSA broadening, verified by
# tests/test_b1_2_fy26.py) cannot make a correct historical receipt "fail".
# The LIVE-code legs (position-invariance, collision hard-fail, 20-hex over
# the full corpus) still run against HEAD, where they belong.
POST_SHA  = "dc979fa60e07d82eaceda8ad2343869b00ee8e8a"   # DBDP-106 merge
MAP_FILE  = REPO / "data" / "record_id_migration_dbdp106.json"
POST_PARQUET = REPO / "output" / "fact_budget_line_items.parquet"

FLOAT_1F = {"budget_year"}
FLOAT_6F = {c for c in etl.COLUMNS if c.startswith("cost_") and c != "cost_units"}
TARGET_FAMILIES = {"P-40", "R-2", "OP-5"}

results = []


def case(name, ok, detail=""):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))


def row_fingerprint(row):
    """c10434 §5 fingerprint over a dict-like row keyed by COLUMNS names."""
    parts = []
    for col in etl.COLUMNS:
        if col == "record_id":
            continue
        v = row[col]
        if v is None or (isinstance(v, float) and v != v):
            parts.append("")
        elif col in FLOAT_1F:
            parts.append(format(float(v), ".1f"))
        elif col in FLOAT_6F:
            parts.append(format(float(v), ".6f"))
        else:
            parts.append(etl.norm_key(v))
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def fingerprints(df):
    return [row_fingerprint(r) for r in df.to_dict("records")]


def artifact_at(sha):
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{sha}:output/fact_budget_line_items.parquet"],
        capture_output=True).stdout
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as fh:
        fh.write(blob)
        p = fh.name
    return pd.read_parquet(p)


def pre_rekey_df():
    return artifact_at(BASE_SHA)


def main():
    pre = pre_rekey_df()
    post_all = pd.read_parquet(POST_PARQUET)          # HEAD, for live-code legs
    post = artifact_at(POST_SHA)                      # DBDP-106 merge artifact
    mig = json.load(open(MAP_FILE, encoding="utf-8"))
    entries = mig["entries"]

    case("map base_sha matches pinned base", mig["base_sha"] == BASE_SHA, mig["base_sha"])

    pre_fp = fingerprints(pre)
    post_fp = fingerprints(post)
    case("fingerprints distinct pre", len(set(pre_fp)) == len(pre), f"{len(set(pre_fp))}/{len(pre)}")
    case("fingerprints distinct post", len(set(post_fp)) == len(post), f"{len(set(post_fp))}/{len(post)}")

    pre_by_fp = dict(zip(pre_fp, pre.to_dict("records")))
    post_by_fp = dict(zip(post_fp, post.to_dict("records")))
    case("fingerprint bijection pre<->post (values conserved)",
         set(pre_fp) == set(post_fp) and len(pre) == len(post),
         f"{len(set(pre_fp) & set(post_fp))}/{len(pre)} rows matched")

    # map completeness + correctness, proven by fingerprint join, not map say-so
    changed = {fp for fp in pre_by_fp
               if pre_by_fp[fp]["record_id"] != post_by_fp[fp]["record_id"]}
    map_by_fp = {e["row_fingerprint"]: e for e in entries}
    case("map covers exactly the changed rows",
         set(map_by_fp) == changed, f"map={len(entries)} changed={len(changed)}")
    ok = all(map_by_fp[fp]["old_id"] == pre_by_fp[fp]["record_id"]
             and map_by_fp[fp]["new_id"] == post_by_fp[fp]["record_id"]
             and map_by_fp[fp]["family"] == post_by_fp[fp]["exhibit_type"]
             for fp in changed)
    case("map old/new/family agree with both artifacts", ok)
    case("map is 1:1 (old ids unique, new ids unique)",
         len({e["old_id"] for e in entries}) == len(entries)
         and len({e["new_id"] for e in entries}) == len(entries))
    case("no old==new entries; all changed ids in target families",
         all(e["old_id"] != e["new_id"] and e["family"] in TARGET_FAMILIES
             for e in entries))

    # non-target stability: every unchanged row's id byte-identical
    unchanged = [fp for fp in pre_by_fp if fp not in changed]
    case("non-target rows byte-identical ids",
         all(pre_by_fp[fp]["record_id"] == post_by_fp[fp]["record_id"] for fp in unchanged),
         f"{len(unchanged)} rows (MHS/DHP, RF-1, OP-5 metadata)")

    # per-family cardinality conserved (no collapse)
    for fam in sorted(TARGET_FAMILIES):
        n_pre = (pre["exhibit_type"] == fam).sum()
        n_post = (post["exhibit_type"] == fam).sum()
        case(f"cardinality conserved {fam}", n_pre == n_post, f"{n_pre}=={n_post}")

    # DBDP-72 guarantees on new ids
    case("all post ids 20-hex (full corpus)",
         post_all["record_id"].str.fullmatch(r"[0-9a-f]{20}").all())

    # position-invariance (TC-B1-RK-01): shuffle WITHIN-FILE row order in one
    # representative source per family, re-parse, compare id sets
    import defusedxml.ElementTree as DET
    import random
    import re as _re
    rng = random.Random(1106)

    # P-40: shuffle LineItem elements of PROC_DISA_PB_2027.xml
    import xml.etree.ElementTree as XET
    src = next((REPO / "02_Procurement").rglob("PROC_DISA_PB_2027.xml"))
    tree = XET.parse(src)
    ns = "http://www.dtic.mil/comptroller/xml/schema/20100219/procurement"
    lil = tree.getroot().find(f"{{{ns}}}LineItemList")
    items = list(lil)
    for it in items:
        lil.remove(it)
    shuffled = items[:]
    rng.shuffle(shuffled)
    for it in shuffled:
        lil.append(it)
    with tempfile.NamedTemporaryFile(suffix="_PROC_DISA_PB_2027.xml", delete=False) as fh:
        shuf_path = Path(fh.name)
    tree.write(shuf_path, encoding="utf-8", xml_declaration=True)
    ids_orig = {r["record_id"] for r in etl.parse_procurement_xml(src)}
    recs_shuf = etl.parse_procurement_xml(shuf_path)
    for r in recs_shuf:
        r["source_file"] = "PROC_DISA_PB_2027.xml"   # temp name differs; key uses fname
    # DBDP-103 c10521 Ruling 1: the P-40 key broadened with BSA — recompute
    # position-invariance against the CURRENT key, not the superseded one.
    ids_shuf = {etl.make_content_id("PROC_DISA_PB_2027.xml",
                                    r["line_item_number"],
                                    r["budget_sub_activity_number"])
                for r in recs_shuf}
    case("position-invariance P-40 (shuffled LineItems -> same ids)",
         ids_orig == ids_shuf, f"{len(ids_orig)} ids")

    # R-2: shuffle ProgramElement elements of RDTE_OSW_PB_2027.xml (the
    # file with the PE-across-BA collision pairs — hardest case)
    src = next((REPO / "03_RDT_and_E").rglob("RDTE_OSW_PB_2027.xml"))
    tree = XET.parse(src)
    pel = next(el for el in tree.getroot().iter() if el.tag.endswith("ProgramElementList"))
    items = [el for el in list(pel) if el.tag.endswith("ProgramElement")]
    for it in items:
        pel.remove(it)
    shuffled = items[:]
    rng.shuffle(shuffled)
    for it in shuffled:
        pel.append(it)
    with tempfile.NamedTemporaryFile(suffix="_RDTE_OSW_PB_2027.xml", delete=False) as fh:
        shuf_path = Path(fh.name)
    tree.write(shuf_path, encoding="utf-8", xml_declaration=True)
    orig = etl.parse_rdte_xml(src)
    shuf = etl.parse_rdte_xml(shuf_path)
    ids_orig = {r["record_id"] for r in orig}
    ids_shuf = {etl.make_content_id(src.name, r["program_element"], r["budget_activity_number"])
                for r in shuf}
    case("position-invariance R-2 (shuffled PEs, OSW collision file -> same ids)",
         ids_orig == ids_shuf, f"{len(ids_orig)} ids")

    # OP-5: shuffle every Rows array in DISA_OP-5.json
    src = next((REPO / "01_Operation_and_Maintenance").rglob("DISA_OP-5.json"))
    doc = json.load(open(src, encoding="utf-8"))
    def shuffle_rows(node):
        if isinstance(node, list):
            for x in node:
                shuffle_rows(x)
        elif isinstance(node, dict):
            if node.get("Type") == "Grid" and isinstance(node.get("Rows"), list):
                rng.shuffle(node["Rows"])
            for v in node.values():
                shuffle_rows(v)
    shuffle_rows(doc)
    with tempfile.NamedTemporaryFile("w", suffix="_DISA_OP-5.json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(doc, fh)
        shuf_path = Path(fh.name)
    orig = [r for r in etl.parse_json_exhibit(src) if r.get("record_id")]
    shuf = [r for r in etl.parse_json_exhibit(shuf_path) if r.get("record_id")]
    ids_orig = {r["record_id"] for r in orig}
    ids_shuf = {etl.make_content_id(src.name, r["_disc_key"][1]) for r in shuf
                if r.get("_disc_family") == "OP-5"}
    meta_shuf = {r["record_id"] for r in shuf if not r.get("_disc_family")}
    meta_orig = {r["record_id"] for r in orig if not r.get("_disc_family")}
    case("position-invariance OP-5 (shuffled grid Rows -> same ids)",
         ids_orig == ids_shuf | meta_orig and meta_shuf == meta_orig,
         f"{len(ids_orig)} ids")

    # collision hard-fail is exercisable through the same callable: duplicate
    # a P-40 discriminator and prove the check names it
    recs = etl.parse_procurement_xml(next((REPO / "02_Procurement").rglob("PROC_DISA_PB_2027.xml")))
    dup = dict(recs[0])
    msgs = etl.check_discriminator_collisions(recs + [dup])
    case("collision hard-fail names colliding rows",
         len(msgs) == 1 and "P-40 collision" in msgs[0] and "key=" in msgs[0],
         msgs[0][:100] if msgs else "no message")

    bad = [n for n, ok in results if not ok]
    print()
    if bad:
        print(f"RE-KEY MIGRATION SUITE FAILED: {bad}")
        return 1
    print(f"All {len(results)} re-key migration checks hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
