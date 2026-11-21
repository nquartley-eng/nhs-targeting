"""Stage 4: latitude/longitude for each practice, for the map.

Takes each practice's postcode from the latest EPD month and looks it up with
the free postcodes.io bulk API (100 postcodes per request). Practice postcodes
are public business addresses; nothing else is sent.

Output: data/processed/practice_locations.csv  practice, name, postcode, lat, lon
Usage:  python3 -I src/geocode_practices.py <project_root>
"""
import csv
import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
P = ROOT / "data/processed"


def lookup(batch: list[str]) -> dict:
    req = urllib.request.Request("https://api.postcodes.io/postcodes", method="POST",
                                 data=json.dumps({"postcodes": batch}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "nhs-targeting"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.load(r)["result"]
            return {x["query"]: x["result"] for x in res}
        except Exception:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("postcodes.io failed")


def main() -> None:
    prac = {}
    for ym in ["202609", "202606", "202603"]:  # latest first; earlier months fill gaps
        with gzip.open(P / f"epd/totals_{ym}.csv.gz", "rt") as f:
            for r in csv.DictReader(f):
                if r["postcode"] not in ("", "-") and r["practice"] not in prac:
                    prac[r["practice"]] = (r["practice_name"], r["postcode"].strip().upper())
    pcs = sorted({pc for _, pc in prac.values()})
    found = {}
    for i in range(0, len(pcs), 100):
        found.update(lookup(pcs[i:i + 100]))
    with open(P / "practice_locations.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["practice", "name", "postcode", "lat", "lon"])
        miss = 0
        for p, (name, pc) in sorted(prac.items()):
            g = found.get(pc)
            if g:
                w.writerow([p, name, pc, g["latitude"], g["longitude"]])
            else:
                w.writerow([p, name, pc, "", ""])
                miss += 1
    print(f"{len(prac):,} prescribers, {len(pcs):,} postcodes, not found: {miss}")


if __name__ == "__main__":
    main()
