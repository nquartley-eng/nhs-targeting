"""Stage 2, step 1: put all prescribing into one consistent monthly table.

Why: the pre-2014 files are at *presentation* level (each strength/brand is its
own row, e.g. "apixaban 2.5mg" and "apixaban 5mg"), while the 2014+ EPD extract
is already at *chemical* level (the first 9 characters of the BNF code). We add
the presentation rows up to chemical level so both periods mean the same thing.

We also keep only GP practices (codes that appear in QOF), as decided in Stage 1.

Outputs:
  data/processed/rx_chem_monthly.parquet   ym, practice, chem, items
  data/processed/practice_totals.parquet   ym, practice, total_items  (all drugs)

Usage: .venv/bin/python -I src/build_monthly.py <project_root>
"""
import glob
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
P = ROOT / "data/processed"


def main() -> None:
    gp = set(pd.read_csv(P / "qof_registers.csv", dtype={"practice": str}).practice)

    rx = [pd.read_parquet(P / "pre2014_rx.parquet", columns=["ym", "practice", "chem", "items"])]
    tot = [pd.read_parquet(P / "pre2014_totals.parquet", columns=["ym", "practice", "total_items"])]
    for f in sorted(glob.glob(str(P / "epd/rx_*.csv.gz"))):
        rx.append(pd.read_csv(f, usecols=["ym", "practice", "chem", "items"], dtype={"ym": str, "chem": str}))
    for f in sorted(glob.glob(str(P / "epd/totals_*.csv.gz"))):
        tot.append(pd.read_csv(f, usecols=["ym", "practice", "total_items"], dtype={"ym": str}))

    rx = pd.concat(rx, ignore_index=True)
    rx["ym"] = rx.ym.astype(str).str.replace("-", "")
    rx = rx[rx.practice.isin(gp)]
    rx = rx.groupby(["ym", "practice", "chem"], as_index=False)["items"].sum()
    rx.to_parquet(P / "rx_chem_monthly.parquet", index=False, compression="zstd")

    tot = pd.concat(tot, ignore_index=True)
    tot["ym"] = tot.ym.astype(str).str.replace("-", "")
    tot = tot[tot.practice.isin(gp)].groupby(["ym", "practice"], as_index=False)["total_items"].sum()
    tot.to_parquet(P / "practice_totals.parquet", index=False, compression="zstd")

    print(f"rx_chem_monthly: {len(rx):,} rows, {rx.ym.nunique()} months, {rx.practice.nunique():,} practices")
    print(f"practice_totals: {len(tot):,} rows, {tot.ym.nunique()} months")


if __name__ == "__main__":
    main()
