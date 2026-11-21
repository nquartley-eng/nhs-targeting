"""Drug-name search for the tool: map what a user types (a generic name like
"apixaban" or a brand like "Mounjaro") to the condition(s) it treats.

No AI is needed for drugs already prescribed in England: every BNF code says
what the drug is for. A drug belongs to a condition when its code falls inside
that condition's "existing treatment" BNF prefixes (src/conditions.py), or it is
one of the training launches' new drugs. Some drugs belong to several
conditions (statins: heart disease, stroke, PAD; SGLT2s: diabetes and CKD), and
the tool then lets the user pick.

Names come from one month of national prescribing (Sep 2026):
  - generic names: the BNF chemical substance name
  - brand names: the leading words of branded presentations (BNF codes whose
    characters 10-11 are not "AA", the generic marker), e.g. "Trelegy Ellipta"

Output: data/processed/drug_lookup.json  [[name, kind, chem, [conditions]], ...]
Usage:  python3 -I src/build_drug_lookup.py <project_root>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from conditions import CONDITIONS  # noqa: E402
from fetch_epd import run_sql  # noqa: E402

TABLE = "EPD_SNOMED_202609"


def brand_of(desc: str) -> str:
    """'Trelegy Ellipta 92microg/55microg/22microg/dose dry pdr inh' -> 'Trelegy Ellipta'."""
    words = []
    for w in desc.replace("_", " ").split():
        if any(ch.isdigit() for ch in w) or w.lower() in {"tab", "tabs", "cap", "caps", "inh", "oral", "soln", "inj"}:
            break
        words.append(w)
    return " ".join(words[:3]).strip(" ,()")


def main() -> None:
    prefixes = sorted({p for v in CONDITIONS.values() for p in v["existing"]})
    where = " OR ".join(f"BNF_CHEMICAL_SUBSTANCE_CODE LIKE '{p}%'" for p in prefixes)
    rows = run_sql(TABLE, f"SELECT BNF_PRESENTATION_CODE AS code, MAX(BNF_PRESENTATION_NAME) AS pres, "
                          f"MAX(BNF_CHEMICAL_SUBSTANCE) AS chem_name, SUM(ITEMS) AS items FROM `{TABLE}` "
                          f"WHERE {where} GROUP BY BNF_PRESENTATION_CODE")

    def conditions_for(chem: str) -> list[str]:
        return [k for k, v in CONDITIONS.items() if chem.startswith(tuple(v["existing"]))]

    entries: dict[tuple[str, str], dict] = {}
    for r in rows:
        code, chem = r["code"], r["code"][:9]
        conds = conditions_for(chem)
        if not conds:
            continue
        items = float(r["items"] or 0)
        names = [(r["chem_name"].strip(), "generic")]
        if code[9:11] != "AA":  # branded presentation
            b = brand_of(r["pres"])
            if len(b) >= 3 and not re.match(r"^[a-z]", b):
                names.append((b, "brand"))
        for name, kind in names:
            e = entries.setdefault((name.lower(), chem), {"name": name, "kind": kind, "chem": chem,
                                                         "conditions": conds, "items": 0.0})
            e["items"] += items

    # Keep the most-prescribed spelling per name; drop very rare brand strings (noise)
    out = sorted((e for e in entries.values() if e["kind"] == "generic" or e["items"] >= 20),
                 key=lambda e: -e["items"])
    data = [[e["name"], e["kind"], e["chem"], e["conditions"]] for e in out]
    (ROOT / "data/processed/drug_lookup.json").write_text(json.dumps(data, separators=(",", ":")))
    multi = sum(1 for e in out if len(e["conditions"]) > 1)
    print(f"{len(data):,} names ({sum(1 for e in out if e['kind'] == 'generic'):,} generic, "
          f"{sum(1 for e in out if e['kind'] == 'brand'):,} brand); {multi:,} map to more than one condition")
    for probe in ["Mounjaro", "Apixaban", "Trelegy", "Sertraline", "Jardiance", "Atorvastatin", "Entresto"]:
        hits = [e for e in out if e["name"].lower().startswith(probe.lower())][:2]
        print(probe, "->", [(h["name"], h["conditions"]) for h in hits])


if __name__ == "__main__":
    main()
