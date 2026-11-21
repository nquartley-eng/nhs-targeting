"""Pull practice-level prescribing for Jan 2014 onwards from the NHSBSA EPD
via its SQL API, filtered server-side to the drugs we track.

For each month we run two queries:
  1. practice x chemical items/quantity for our BNF paragraphs + innovation drugs
  2. practice totals (all drugs) plus practice details (region, ICB/STP, postcode)

Results above 32,000 rows come back from the API as gzipped CSV links
(`gc_urls`), which we download and save as-is.

Outputs: data/processed/epd/rx_YYYYMM.csv.gz and totals_YYYYMM.csv.gz
Usage:   python3 -I src/fetch_epd.py <project_root>
"""
import csv
import gzip
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
sys.path.insert(0, str(ROOT / "src"))
from bnf_codes import INNOVATION_DRUGS, PARAGRAPH_PREFIXES_TO_KEEP  # noqa: E402

SQL_URL = "https://opendata.nhsbsa.net/api/3/action/datastore_search_sql"
OUT = ROOT / "data/processed/epd"

# Training window (launch features + 24-month outcomes) and latest 12 months for scoring
MONTHS = [f"{y}{m:02d}" for y in range(2014, 2019) for m in range(1, 13)]
MONTHS += [f"{y}{m:02d}" for y, m in [(2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]]


def table_for(ym: str) -> tuple[str, str, str]:
    """Return (table, chemical-code column, area column).

    Column names drift between months (e.g. some early months have no STP_CODE,
    later ones use ICB_CODE, SNOMED tables rename the chemical code column), so
    we read one row first and pick whichever names exist.
    """
    table = f"EPD_SNOMED_{ym}" if ym >= "202507" else f"EPD_{ym}"
    cols = set(run_sql(table, f"SELECT * FROM `{table}` LIMIT 1")[0].keys())
    chem = "BNF_CHEMICAL_SUBSTANCE_CODE" if "BNF_CHEMICAL_SUBSTANCE_CODE" in cols else "BNF_CHEMICAL_SUBSTANCE"
    area = next((c for c in ("ICB_CODE", "STP_CODE", "PCO_CODE") if c in cols), "PCO_CODE")
    return table, chem, area


def run_sql(table: str, sql: str) -> list[dict]:
    params = urllib.parse.urlencode({"resource_id": table, "sql": sql})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{SQL_URL}?{params}", timeout=300) as r:
                res = json.load(r)["result"]
            break
        except Exception as e:
            if attempt == 3:
                raise
            print("  retry", table, e, flush=True)
            time.sleep(10 * (attempt + 1))
    res = res.get("result", res)
    if "records" in res:
        return res["records"]
    rows = []  # large result: one or more gzipped CSV parts
    for part in res["gc_urls"]:
        with urllib.request.urlopen(part["url"], timeout=300) as r:
            text = gzip.decompress(r.read()).decode("utf-8")
        rows.extend(csv.DictReader(io.StringIO(text)))
    return rows


def write_gz(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".partial")
    with gzip.open(tmp, "wt", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    tmp.rename(path)


def fetch_month(ym: str) -> None:
    rx_path, tot_path = OUT / f"rx_{ym}.csv.gz", OUT / f"totals_{ym}.csv.gz"
    if rx_path.exists() and tot_path.exists():
        print(ym, "already done", flush=True)
        return
    table, chem, area = table_for(ym)
    like = " OR ".join(f"{chem} LIKE '{p}%'" for p in PARAGRAPH_PREFIXES_TO_KEEP)
    innov = ",".join(f"'{c}'" for c in INNOVATION_DRUGS)
    rx_sql = (
        f"SELECT YEAR_MONTH AS ym, PRACTICE_CODE AS practice, {chem} AS chem, "
        f"SUM(ITEMS) AS items, SUM(TOTAL_QUANTITY) AS quantity, SUM(ACTUAL_COST) AS act_cost "
        f"FROM `{table}` WHERE ({like} OR {chem} IN ({innov})) "
        f"GROUP BY YEAR_MONTH, PRACTICE_CODE, {chem}"
    )
    tot_sql = (
        f"SELECT YEAR_MONTH AS ym, PRACTICE_CODE AS practice, MAX(PRACTICE_NAME) AS practice_name, "
        f"MAX(POSTCODE) AS postcode, MAX(REGIONAL_OFFICE_CODE) AS region_code, "
        f"MAX(REGIONAL_OFFICE_NAME) AS region_name, MAX({area}) AS area_code, "
        f"MAX(PCO_CODE) AS pco_code, SUM(ITEMS) AS total_items "
        f"FROM `{table}` GROUP BY YEAR_MONTH, PRACTICE_CODE"
    )
    rx = run_sql(table, rx_sql)
    tot = run_sql(table, tot_sql)
    write_gz(rx_path, rx)
    write_gz(tot_path, tot)
    print(ym, f"rx rows {len(rx):,}, prescribers {len(tot):,}", flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ym in MONTHS:
        fetch_month(ym)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
