"""Turn eleven years of differently-formatted QOF files into one tidy table.

Output: data/processed/qof_registers.csv with one row per practice per QOF year:
    qof_year, practice, list_size, dm_register, af_register, hf_register, copd_register, dep_register

QOF years run April-March, and the registers are a snapshot at 31 March
(e.g. "2012-13" = registers as at 31 Mar 2013).

Three format eras:
  2009-10 to 2012-13  Excel, wide (one column per disease), header on row 14
  2013-14, 2014-15    CSV, long (one row per practice x disease)
  2015-16 onwards     CSV, long, with list size by age band (we use TOTAL)

Usage: .venv/bin/python -I src/load_qof.py <project_root>
"""
import io
import sys
import warnings
import zipfile
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(sys.argv[1]).resolve()
RAW = ROOT / "data/raw/qof"
COLS = ["qof_year", "practice", "list_size", "dm_register", "af_register", "hf_register", "copd_register", "dep_register"]


def wide_excel(year: str, f) -> pd.DataFrame:
    """Excel years: pick columns by name because positions shift between years."""
    sheet = 0  # first sheet is the all-disease practice prevalence table
    d = pd.read_excel(f, sheet_name=sheet, header=13)
    pick = lambda *words: next(c for c in d.columns if all(w.lower() in str(c).lower() for w in words))
    out = pd.DataFrame({
        "practice": d[pick("practice code")],
        "list_size": d[pick("list size")],
        "dm_register": d[pick("diabetes", "register")],
        "af_register": d[pick("atrial", "register")],
        # "Heart Failure Register" (all HF), not the "Due to LVD" sub-register
        "hf_register": d[next(c for c in d.columns if str(c).strip().lower() == "heart failure register")],
        "copd_register": d[pick("obstructive", "register")],
        "dep_register": d[pick("depression", "register")] if any(
            "depression" in str(c).lower() and "register" in str(c).lower() for c in d.columns) else None,
    })
    out = out[out["practice"].astype(str).str.match(r"^[A-Z]\d{5}$")]
    out.insert(0, "qof_year", year)
    return out


def long_csv(year: str, d: pd.DataFrame, prac, grp, reg, lst, list_type=None) -> pd.DataFrame:
    # List size: use the whole-practice (TOTAL) figure. Registers: take every row,
    # because age-restricted registers (diabetes = 17+) sit on age-band rows.
    if list_type:
        sizes = d[d[list_type].str.upper() == "TOTAL"].groupby(prac)[lst].max()
    else:
        sizes = d.groupby(prac)[lst].max()
    d = d[d[grp].isin(["DM", "AF", "HF", "COPD", "DEP"])]
    wide = d.pivot_table(index=prac, columns=grp, values=reg, aggfunc="max")
    out = pd.DataFrame({
        "practice": wide.index,
        "list_size": sizes.reindex(wide.index).values,
        "dm_register": wide.get("DM"),
        "af_register": wide.get("AF"),
        "hf_register": wide.get("HF"),
        "copd_register": wide.get("COPD"),
        "dep_register": wide.get("DEP"),
    }).reset_index(drop=True)
    out.insert(0, "qof_year", year)
    return out


def read_zip_csv(path: Path, member: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        return pd.read_csv(z.open(member), encoding="latin-1")


def main() -> None:
    parts = [
        wide_excel("2009-10", RAW / "2009-10/qof-09-10-data-tab-prev-prac.xls"),
        wide_excel("2010-11", RAW / "2010-11/qof-10-11-data-tab-prev-prac.xls"),
        wide_excel("2011-12", RAW / "2011-12/qual-outc-fram-11-12-prac-prev.xls"),
    ]
    with zipfile.ZipFile(RAW / "2012-13/qof-12-13-data-tab-prac.zip") as z:
        parts.append(wide_excel("2012-13", io.BytesIO(z.read("Practice/Prevalence/qof-12-13-data-tab-prac-prev.xlsx"))))

    d = read_zip_csv(RAW / "2013-14/qof-1314-csvfilescqrsdata.zip", "prevalencebyprac.csv")
    parts.append(long_csv("2013-14", d, "practicecode", "indicator_group", "disease_register_size", "practice_listsize"))
    d = read_zip_csv(RAW / "2014-15/qof-1415-csvfiles-v2.zip", "PREVALENCE_BY_PRAC_v2.csv")
    parts.append(long_csv("2014-15", d, "PRACTICE_CODE", "INDICATOR_GROUP_CODE", "REGISTER_SIZE", "PRACTICE_LIST_SIZE"))
    for year, f, m in [
        ("2015-16", "qof-1516-csv.zip", "PREVALENCE.csv"),
        ("2016-17", "qof-1617-csv.zip", "PREVALENCE.csv"),
        ("2017-18", "qof-1718-csv.zip", "PREVALENCE.csv"),
        ("2018-19", "QOF_1819_v2.zip", "PREVALENCE_1819_v2.csv"),
    ]:
        d = read_zip_csv(RAW / year / f, m)
        parts.append(long_csv(year, d, "PRACTICE_CODE", "INDICATOR_GROUP_CODE", "REGISTER", "PATIENT_LIST_SIZE", "PATIENT_LIST_TYPE"))
    d = read_zip_csv(RAW / "2025-26/QOF_2526_v2.zip", "PREVALENCE_2526.csv")
    parts.append(long_csv("2025-26", d, "PRACTICE_CODE", "GROUP_CODE", "REGISTER_SIZE", "PRACTICE_LIST_SIZE", "PATIENT_LIST_TYPE"))

    qof = pd.concat(parts, ignore_index=True)[COLS]
    for c in COLS[2:]:
        qof[c] = pd.to_numeric(qof[c], errors="coerce").astype("Int64")
    out = ROOT / "data/processed/qof_registers.csv"
    qof.to_csv(out, index=False)

    summary = qof.groupby("qof_year").agg(
        practices=("practice", "nunique"),
        list_size=("list_size", "sum"),
        dm=("dm_register", "sum"), af=("af_register", "sum"), hf=("hf_register", "sum"), copd=("copd_register", "sum"), dep=("dep_register", "sum"),
        missing_dm=("dm_register", lambda s: s.isna().sum()),
        missing_af=("af_register", lambda s: s.isna().sum()),
        missing_hf=("hf_register", lambda s: s.isna().sum()),
    )
    print(summary.to_string())


if __name__ == "__main__":
    main()
