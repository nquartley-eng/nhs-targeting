"""Download NHS Digital practice-level prescribing (Aug 2010 - Dec 2013) and
keep only the rows we need.

Why stream-and-filter: each month is a ~250 MB zip holding a ~1.4 GB CSV, and
41 months unzipped would be ~57 GB - more than the free disk. So for each month
we download the zip, read the CSV straight out of it line by line, keep only our
drug rows, write a small output, and delete the zip before the next month.

Outputs per month (YYYYMM):
  data/processed/pre2014/rx_YYYYMM.csv      practice x BNF presentation rows we track
  data/processed/pre2014/totals_YYYYMM.csv  every practice's total items (all drugs)
  data/raw/pre2014_addr/addr_YYYYMM.csv     practice name/address file (small, kept as-is)

Usage:  python3 -I src/fetch_pre2014.py <project_root>
Re-running skips months whose rx_YYYYMM.csv already exists.

After all months are done, the per-month CSVs (~3.2 GB) were combined into
data/processed/pre2014_rx.parquet and pre2014_totals.parquet (~260 MB, same
rows, checked by row count and item totals) and the CSVs deleted.
"""
import csv
import io
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from bnf_codes import keep_code  # noqa: E402

MANIFEST = ROOT / "data/raw/pre2014_manifest.csv"
TMP = ROOT / "data/raw/pre2014_tmp"
OUT = ROOT / "data/processed/pre2014"
ADDR = ROOT / "data/raw/pre2014_addr"


def process_month(ym: str, zip_url: str) -> None:
    rx_path = OUT / f"rx_{ym}.csv"
    if rx_path.exists():
        print(ym, "already done", flush=True)
        return
    work = TMP / ym
    work.mkdir(parents=True, exist_ok=True)
    zpath = work / "m.zip"
    if not (zpath.exists() and zipfile.is_zipfile(zpath)):
        part = work / "m.zip.part"
        if zpath.exists():  # leftover from an interrupted run: resume from it
            zpath.rename(part)
        # -C - resumes a partial download; abort and retry if speed stalls for 60 s
        subprocess.run(["curl", "-sSL", "-C", "-", "--retry", "10", "--retry-all-errors",
                        "--retry-delay", "10", "--speed-limit", "10000", "--speed-time", "60",
                        "-o", str(part), zip_url], check=True)
        if not zipfile.is_zipfile(part):
            part.unlink()
            raise RuntimeError(f"{ym}: downloaded file is not a valid zip")
        part.rename(zpath)

    totals = defaultdict(lambda: [0, "", ""])  # practice -> [items, sha, pct]
    kept = 0
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        pdpi = next(n for n in names if "PDPI" in n.upper())
        addr = next(n for n in names if "ADDR" in n.upper())
        with z.open(addr) as src, open(ADDR / f"addr_{ym}.csv", "wb") as dst:
            shutil.copyfileobj(src, dst)

        tmp_rx = rx_path.with_suffix(".partial")
        with z.open(pdpi) as raw, open(tmp_rx, "w", newline="") as fo:
            w = csv.writer(fo)
            w.writerow(["ym", "practice", "bnf_code", "chem", "bnf_name", "items", "quantity", "act_cost"])
            reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1", newline=""))
            next(reader)  # header: SHA,PCT,PRACTICE,BNF CODE,BNF NAME,ITEMS,NIC,ACT COST,QUANTITY,PERIOD
            for row in reader:
                if len(row) < 10:
                    continue
                sha, pct, prac, code = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
                items = int(row[5])
                t = totals[prac]
                t[0] += items
                t[1], t[2] = sha, pct
                if keep_code(code):
                    w.writerow([ym, prac, code, code[:9], row[4].strip(), items,
                                float(row[8]), float(row[7])])
                    kept += 1
        tmp_rx.rename(rx_path)

    with open(OUT / f"totals_{ym}.csv", "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["ym", "practice", "sha", "pct", "total_items"])
        for prac, (items, sha, pct) in sorted(totals.items()):
            w.writerow([ym, prac, sha, pct, items])

    shutil.rmtree(work)  # delete the raw zip to save disk
    print(ym, f"kept {kept:,} rows, {len(totals):,} practices", flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ADDR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST) as f:
        months = list(csv.DictReader(f))
    failed = []
    for m in months:
        for attempt in range(3):
            try:
                process_month(m["ym"], m["zip"])
                break
            except Exception as e:
                print(m["ym"], f"attempt {attempt + 1} failed: {e}", flush=True)
        else:
            failed.append(m["ym"])
    print("ALL DONE" if not failed else f"DONE WITH FAILURES: {failed}", flush=True)


if __name__ == "__main__":
    main()
