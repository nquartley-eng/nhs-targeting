"""Stage 4 helper: find drugs launched 2019-2025, so "today's" practices get an
adoption-speed feature from recent launches (the training launches used the
same idea with 2010-2015 drugs).

Step 1 (this script): count prescribing practices per chemical, nationally,
every 3 months from Jan 2019 to Sep 2026. A chemical is a recent launch if it
first reaches 10 practices after Jan 2019 and 100+ practices a year later.

Output: data/processed/recent_national_counts.csv
Usage:  python3 -I src/find_recent_launches.py <project_root>
"""
import csv
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from fetch_epd import run_sql, table_for  # noqa: E402

OUT = ROOT / "data/processed/recent_national_counts.csv"
MONTHS = [f"{y}{m:02d}" for y in range(2019, 2027) for m in (1, 4, 7, 10) if f"{y}{m:02d}" <= "202607"]


def main() -> None:
    done = set()
    if OUT.exists():
        done = {r["ym"] for r in csv.DictReader(open(OUT))}
    new_file = not OUT.exists()
    with open(OUT, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["ym", "chem", "n_prac", "items"])
        for ym in MONTHS:
            if ym in done:
                continue
            t0 = time.time()
            table, chem, _ = table_for(ym)
            rows = run_sql(table, f"SELECT {chem} AS chem, COUNT(DISTINCT PRACTICE_CODE) AS n_prac, "
                                  f"SUM(ITEMS) AS items FROM `{table}` GROUP BY {chem}")
            for r in rows:
                w.writerow([ym, r["chem"], r["n_prac"], r["items"]])
            f.flush()
            print(ym, len(rows), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
