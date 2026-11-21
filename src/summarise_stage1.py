"""Stage 1 data checks: national uptake curves, coverage and join rates.

Reads the filtered prescribing extracts (pre-2014 and EPD), QOF table and ODS
file, and writes:
  data/processed/national_monthly_series.csv   items + prescribing practices per drug per month
  reports/figures/national_uptake.png          uptake curves used to date each launch
  reports/stage1_checks.txt                    numbers quoted in the data summary

Only GP practices are counted (ODS role RO76, or a standard practice code
pattern for codes that have since disappeared from ODS); out-of-hours services,
walk-in centres and hospitals in the prescribing data are excluded.

Usage: .venv/bin/python -I src/summarise_stage1.py <project_root>
"""
import glob
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from bnf_codes import LAUNCHES  # noqa: E402

P = ROOT / "data/processed"
FIG = ROOT / "reports/figures"
FIG.mkdir(parents=True, exist_ok=True)

TRACK = {**{c: ("sglt2", n) for c, n in LAUNCHES["sglt2"]["new_drugs"].items()},
         **{c: ("doac", n) for c, n in LAUNCHES["doac"]["new_drugs"].items()},
         **{c: ("arni", n) for c, n in LAUNCHES["arni"]["new_drugs"].items()},
         "0208020V0": ("warfarin", "Warfarin sodium")}



def load_rx() -> pd.DataFrame:
    d = pd.read_parquet(P / "pre2014_rx.parquet", columns=["ym", "practice", "chem", "items"],
                        filters=[("chem", "in", list(TRACK))])
    frames = [d.groupby(["ym", "practice", "chem"], as_index=False)["items"].sum()]
    for f in sorted(glob.glob(str(P / "epd/rx_*.csv.gz"))):
        d = pd.read_csv(f, usecols=["ym", "practice", "chem", "items"], dtype={"ym": str, "chem": str})
        d["ym"] = d.ym.str.replace("-", "")
        frames.append(d[d.chem.isin(TRACK)])
    return pd.concat(frames, ignore_index=True)


def load_totals() -> pd.DataFrame:
    frames = [pd.read_parquet(P / "pre2014_totals.parquet", columns=["ym", "practice", "total_items"])]
    for f in sorted(glob.glob(str(P / "epd/totals_*.csv.gz"))):
        d = pd.read_csv(f, usecols=["ym", "practice", "total_items"], dtype={"ym": str})
        d["ym"] = d.ym.str.replace("-", "")
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    # A "GP practice" = any code that appears in QOF in any year we hold. The
    # prescribing data also contains out-of-hours services, walk-in centres etc.
    # (~1% of items) which have no QOF registers and are not sales targets.
    qof_all = pd.read_csv(P / "qof_registers.csv", dtype={"practice": str})
    gp = set(qof_all.practice)
    is_gp = lambda s: s.isin(gp)
    out = []

    rx = load_rx()
    rx = rx[is_gp(rx.practice)]
    rx["group"] = rx.chem.map(lambda c: TRACK[c][0])
    nat = (rx.groupby(["ym", "group", "chem"])
             .agg(items=("items", "sum"), n_practices=("practice", "nunique")).reset_index())
    nat["drug"] = nat.chem.map(lambda c: TRACK[c][1])
    nat.to_csv(P / "national_monthly_series.csv", index=False)
    cls = rx.groupby(["ym", "group"]).agg(items=("items", "sum"), n_practices=("practice", "nunique")).reset_index()

    # First month each drug reaches 1 / 10 / 100 GP practices
    out.append("== First month each drug is prescribed by >=1, >=10, >=100 GP practices")
    for chem, g in nat.groupby("chem"):
        g = g.sort_values("ym")
        first = lambda k: next(iter(g.loc[g.n_practices >= k, "ym"]), "-")
        out.append(f"{TRACK[chem][1]:28s} {first(1)}  {first(10)}  {first(100)}   (data starts {g.ym.min()})")

    # Coverage
    tot = load_totals()
    tot = tot[is_gp(tot.practice)]
    per_month = tot.groupby("ym").practice.nunique()
    out.append("\n== Prescribing coverage")
    out.append(f"Months available: {per_month.index.min()} to {per_month.index.max()} ({len(per_month)} months)")
    out.append(f"GP practices per month: min {per_month.min():,}, max {per_month.max():,}")
    out.append("Practices per year (Jan of each year): " + ", ".join(
        f"{ym[:4]}: {n:,}" for ym, n in per_month.items() if ym.endswith("01")))

    # Join to QOF and churn for candidate launch/outcome months
    qof = pd.read_csv(P / "qof_registers.csv", dtype={"practice": str})
    out.append("\n== Join checks (QOF practices: prescribing at launch, and still prescribing at outcome)")
    # Launch months come from the uptake curves. QOF year = latest year *published*
    # before launch (QOF is published ~6-7 months after the 31 March year end).
    checks = [("sglt2", "201212", "2011-12", "201412"),
              ("doac", "201109", "2010-11", "201309"),
              ("arni", "201604", "2014-15", "201804")]
    for grp, launch, qyear, outcome in checks:
        q = set(qof.loc[qof.qof_year == qyear, "practice"])
        both = q & set(tot.loc[tot.ym == launch, "practice"])
        at_outcome = both & set(tot.loc[tot.ym == outcome, "practice"])
        out.append(f"{grp}: QOF {qyear} practices {len(q):,}; prescribing in launch month {launch}: "
                   f"{len(both):,} ({len(both)/len(q):.1%}); of those, still prescribing at {outcome}: "
                   f"{len(at_outcome):,} ({len(at_outcome)/len(both):.1%})")

    # Plot national uptake by class (items per month and number of practices)
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    for grp, g in cls.groupby("group"):
        x = pd.to_datetime(g.ym, format="%Y%m")
        axes[0].plot(x, g["items"], label=grp)
        axes[1].plot(x, g["n_practices"], label=grp)
    axes[0].set_ylabel("Items per month (GP practices)")
    axes[0].set_yscale("log")
    axes[1].set_ylabel("Practices prescribing")
    axes[0].legend()
    axes[0].set_title("National uptake by drug class (gap 2019-2025 not downloaded)")
    fig.tight_layout()
    fig.savefig(FIG / "national_uptake.png", dpi=120)

    # Zoom: DOAC take-off by individual drug 2010-2014
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for chem in ["0208020X0", "0208020Y0", "0208020Z0", "0208020AA"]:
        g = nat[(nat.chem == chem) & (nat.ym <= "201412")].sort_values("ym")
        ax.plot(pd.to_datetime(g.ym, format="%Y%m"), g["items"], label=TRACK[chem][1])
    ax.set_ylabel("Items per month")
    ax.set_title("DOAC prescribing in GP practices, 2010-2014")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "doac_takeoff.png", dpi=120)

    # DOAC monthly class totals printed for the report
    d = cls[(cls.group == "doac") & (cls.ym <= "201412")].set_index("ym")
    out.append("\n== DOAC class, monthly (items, practices)")
    out.append("  ".join(f"{ym}:{r['items']:,}/{r['n_practices']:,}" for ym, r in d.iterrows()))
    s = cls[(cls.group == "sglt2") & (cls.ym <= "201406")].set_index("ym")
    out.append("\n== SGLT2 class, monthly (items, practices)")
    out.append("  ".join(f"{ym}:{r['items']:,}/{r['n_practices']:,}" for ym, r in s.iterrows()))

    text = "\n".join(out)
    (ROOT / "reports/stage1_checks.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
