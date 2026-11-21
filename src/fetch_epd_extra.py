"""Stage 4 extension: the latest 12 months of prescribing for the extra BNF
areas needed to score all 18 conditions (inhalers, antidepressants, statins ...).
Same SQL-API approach as fetch_epd.py, filtered server-side.

Output: data/processed/epd_extra/rx_YYYYMM.csv.gz  (ym, practice, chem, items)
Usage:  python3 -I src/fetch_epd_extra.py <project_root>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from conditions import EXTRA_PREFIXES  # noqa: E402
from fetch_epd import run_sql, table_for, write_gz  # noqa: E402

OUT = ROOT / "data/processed/epd_extra"
MONTHS = ["202510", "202511", "202512"] + [f"2026{m:02d}" for m in range(1, 10)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ym in MONTHS:
        path = OUT / f"rx_{ym}.csv.gz"
        if path.exists():
            continue
        table, chem, _ = table_for(ym)
        like = " OR ".join(f"{chem} LIKE '{p}%'" for p in EXTRA_PREFIXES)
        rows = run_sql(table, f"SELECT YEAR_MONTH AS ym, PRACTICE_CODE AS practice, {chem} AS chem, "
                              f"SUM(ITEMS) AS items FROM `{table}` WHERE {like} "
                              f"GROUP BY YEAR_MONTH, PRACTICE_CODE, {chem}")
        write_gz(path, rows)
        print(ym, f"{len(rows):,} rows", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
