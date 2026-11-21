"""Stage 2: one row per (launch, practice) with at-launch features and the target.

The rule behind every choice here: a feature may only use information a launch
team could have had on the day of launch. Everything about prescribing comes
from months *before* the launch month, and practice size/registers come from the
latest QOF year that had been *published* before launch.

Features (same meaning for every launch, so a model trained on two launches can
be applied to the third):
  list_size               registered patients (QOF)
  register                patients on the relevant QOF register (diabetes/AF/HF)
  prevalence              register / list size, %
  older_alt_per_1k_reg    items of the older alternatives in the 12 months before
                          launch, per 1,000 register patients ("how many patients
                          are already being treated the old way")
  total_items_per_1k_list items of *all* drugs in those 12 months, per 1,000
                          patients (general prescribing intensity)
  adopt_speed             how fast the practice took up earlier new drugs: for each
                          earlier launch, its items per 1,000 patients in that drug's
                          first months (up to 6, at least 3, all before this launch),
                          as a percentile among practices; then averaged
  early_adopter_share     share of those earlier new drugs the practice prescribed
                          at all in their first months
  region                  current NHS England region (7 regions)
  area_*                  the same features averaged over the *other* practices in
                          the practice's local area (PCT/CCG) at launch. Local
                          formularies and hospital specialists shape uptake, so how
                          innovative the neighbours are is known at launch and useful.
Every numeric feature also gets a *_pct version: its percentile within the launch.
Percentiles put the three launches on the same scale (an AF register is far
smaller than a diabetes register, but "top 10% for register size" means the same).

Target:
  outcome_rate  items of the new drug class in months 22-24 after launch, per 1,000
                patients on the register (register from the QOF snapshot closest
                to that window). Three months rather than one smooths out the
                month-to-month noise from 28- vs 56-day prescriptions.
  target        1 if the practice is in the top 20% of outcome_rate for that launch.
Training rows (in_training = True) must be active at launch, still open at month
24, and have a register of at least 20 patients at outcome (with fewer, one or
two patients can swing the rate wildly).

Outputs:
  data/processed/practice_region.csv
  data/processed/features.parquet
  reports/stage2_checks.txt

Usage: .venv/bin/python -I src/build_features.py <project_root>
"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from bnf_codes import INNOVATION_DRUGS, LAUNCHES  # noqa: E402

P = ROOT / "data/processed"
OUT_LINES: list[str] = []

# QOF publication months, checked on the NHS Digital publication pages.
QOF_PUBLISHED = {"2009-10": "201010", "2010-11": "201110", "2011-12": "201210",
                 "2014-15": "201510", "2015-16": "201610"}

SETUP = {
    #        launch   QOF for features  QOF for outcome  register column
    "doac":  ("201109", "2009-10", "2012-13", "af_register"),
    "sglt2": ("201212", "2011-12", "2014-15", "dm_register"),
    "arni":  ("201604", "2014-15", "2017-18", "hf_register"),
}
MIN_OUTCOME_REGISTER = 20
TOP_SHARE = 0.20

REGION_NAMES = {"Y56": "London", "Y58": "South West", "Y59": "South East", "Y60": "Midlands",
                "Y61": "East of England", "Y62": "North West", "Y63": "North East and Yorkshire"}


def log(s: str = "") -> None:
    OUT_LINES.append(s)
    print(s)


def add_months(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:]) + k
    y += (m - 1) // 12
    return f"{y}{(m - 1) % 12 + 1:02d}"


def months(start: str, end: str) -> list[str]:
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, 1)
    return out


# ---------------------------------------------------------------------------
# Region: every practice gets its *current* region, so the label means the same
# thing in 2011 and 2016. Closed practices aren't in the current ODS file, so
# they get the most common current region among practices in the same old
# local area (PCT before 2013, CCG after).
# ---------------------------------------------------------------------------
def build_regions(gp: set[str]) -> pd.DataFrame:
    cur = pd.read_csv(ROOT / "data/raw/ods/epraccur.csv", header=None, dtype=str, usecols=[0, 2])
    cur.columns = ["practice", "region"]
    cur = cur[cur.region.isin(REGION_NAMES)]
    reg = dict(zip(cur.practice, cur.region))

    # latest known local area per practice
    pre = pd.read_parquet(P / "pre2014_totals.parquet", columns=["ym", "practice", "pct"])
    pre = pre.sort_values("ym").drop_duplicates("practice", keep="last")[["practice", "pct"]]
    pre.columns = ["practice", "area"]
    epd = []
    for ym in ["201401", "201601", "201801"]:
        d = pd.read_csv(P / f"epd/totals_{ym}.csv.gz", usecols=["practice", "pco_code"], dtype=str)
        epd.append(d.rename(columns={"pco_code": "area"}))
    pairs = pd.concat([pre] + epd).drop_duplicates()   # every (practice, area) seen
    pairs = pairs[pairs.practice.isin(gp)]
    pairs["region"] = pairs.practice.map(reg)
    # modal region per area is learned from *all* practices ever in it, including
    # survivors whose latest area is now a CCG
    modal = pairs.dropna().groupby("area").region.agg(lambda s: s.mode().iloc[0])
    area = pairs.drop_duplicates("practice", keep="last")

    rows = []
    for p in sorted(gp):
        if p in reg:
            rows.append((p, reg[p], "ods_current"))
        else:
            a = area.loc[area.practice == p, "area"]
            r = modal.get(a.iloc[0]) if len(a) else None
            rows.append((p, r, "area_modal" if r else "unknown"))
    out = pd.DataFrame(rows, columns=["practice", "region_code", "region_source"])
    out["region"] = out.region_code.map(REGION_NAMES)
    out.to_csv(P / "practice_region.csv", index=False)
    log("== Region assignment")
    log(out.region_source.value_counts().to_string())
    return out


# ---------------------------------------------------------------------------
# Earlier new drugs, for the adoption-speed feature. A drug counts if its
# national launch is visible in our data (first month with >= 10 prescribing
# practices is after Sep 2010, so the start isn't hidden by the data start)
# and it really caught on (>= 100 practices 12 months later). We add the DOAC
# class as one "drug" dated from its AF launch, since dabigatran existed
# earlier for post-surgery use.
# ---------------------------------------------------------------------------
def earlier_new_drugs(rx: pd.DataFrame) -> dict[str, tuple[list[str], str]]:
    n = rx.groupby(["chem", "ym"]).practice.nunique().rename("n").reset_index()
    first10 = n[n.n >= 10].groupby("chem").ym.min()
    first10 = first10[first10 > "201009"]
    drugs = {}
    for chem, launch in first10.items():
        at12 = n[(n.chem == chem) & (n.ym == add_months(launch, 12))].n
        if len(at12) and at12.iloc[0] >= 100:
            drugs[chem] = ([chem], launch)
    drugs["DOAC class"] = (list(LAUNCHES["doac"]["new_drugs"]), "201109")
    for c in LAUNCHES["doac"]["new_drugs"]:
        drugs.pop(c, None)  # covered by the class entry
    return drugs


def area_at(ym: str) -> pd.Series:
    """practice -> local area code (PCT up to Mar 2013, CCG from 2014)."""
    if ym < "201401":
        d = pd.read_parquet(P / "pre2014_totals.parquet", columns=["ym", "practice", "pct"],
                            filters=[("ym", "==", ym)])
        return d.set_index("practice").pct
    d = pd.read_csv(P / f"epd/totals_{ym}.csv.gz", usecols=["practice", "pco_code"], dtype=str)
    return d.set_index("practice").pco_code


def pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average")


def older_alt_codes(key: str, all_chems: set[str]) -> list[str]:
    L = LAUNCHES[key]
    if "older_alternatives" in L:
        return list(L["older_alternatives"])
    return [c for c in all_chems if c.startswith(tuple(L["older_alternative_prefixes"]))
            and c not in L["older_alternative_exclude"]]


def auc(score: pd.Series, y: pd.Series) -> float:
    """Chance a random top-20% practice scores higher than a random other one."""
    ok = score.notna()
    r = score[ok].rank()
    pos = y[ok] == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return (r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def build_launch(key, rx, tot, qof, region, new_drugs_all) -> pd.DataFrame:
    launch, qf, qo, regcol = SETUP[key]
    assert QOF_PUBLISHED[qf] < launch, f"{key}: QOF {qf} not published before launch"
    pre12 = months(add_months(launch, -12), add_months(launch, -1))
    win = months(add_months(launch, 22), add_months(launch, 24))
    used_months = set(pre12)

    # Population: practices in the feature QOF year that were prescribing in the
    # 3 months before launch (i.e. open at launch)
    q = qof[qof.qof_year == qf].set_index("practice")
    active = set(tot[tot.ym.isin(pre12[-3:])].practice)
    df = pd.DataFrame(index=sorted(set(q.index) & active))
    df.index.name = "practice"
    df["list_size"] = q.list_size.reindex(df.index).astype(float)
    df["register"] = q[regcol].reindex(df.index).astype(float)
    df["prevalence"] = 100 * df.register / df.list_size

    r12 = rx[rx.ym.isin(pre12)]
    alt = r12[r12.chem.isin(older_alt_codes(key, set(rx.chem.unique())))].groupby("practice")["items"].sum()
    df["older_alt_per_1k_reg"] = 1000 * alt.reindex(df.index).fillna(0) / df.register.replace(0, np.nan)
    t12 = tot[tot.ym.isin(pre12)].groupby("practice").total_items.sum()
    df["total_items_per_1k_list"] = 1000 * t12.reindex(df.index).fillna(0) / df.list_size

    # Adoption speed of earlier new drugs, using only months before launch
    speed, early, used = [], [], []
    for name, (codes, l0) in new_drugs_all.items():
        w = [m for m in months(l0, add_months(l0, 5)) if m < launch]
        if len(w) < 3:
            continue
        used_months.update(w)
        it = rx[rx.ym.isin(w) & rx.chem.isin(codes)].groupby("practice")["items"].sum()
        it = it.reindex(df.index).fillna(0)
        speed.append(pct_rank(1000 * it / df.list_size))
        early.append((it > 0).astype(float))
        used.append(f"{name} ({l0}, {len(w)} mo)")
    df["adopt_speed"] = pd.concat(speed, axis=1).mean(axis=1)
    df["early_adopter_share"] = pd.concat(early, axis=1).mean(axis=1)

    df = df.join(region.set_index("practice")[["region_code", "region"]])

    # Local area at launch (PCT before Apr 2013, CCG after), from the month
    # before launch. Area features are the average over the *other* practices
    # in the area (leave-one-out), so a practice's own value isn't counted twice.
    a = area_at(pre12[-1])
    for m in pre12[-2::-1][:2]:          # fall back to the 2 months before that
        a = a.combine_first(area_at(m))
    df["area"] = a.reindex(df.index)
    for c in ["adopt_speed", "older_alt_per_1k_reg", "total_items_per_1k_list"]:
        g = df.groupby("area")[c]
        df["area_" + c] = (g.transform("sum") - df[c].fillna(0)) / (g.transform("count") - df[c].notna())

    # Target
    new = list(LAUNCHES[key]["new_drugs"])
    out_items = rx[rx.ym.isin(win) & rx.chem.isin(new)].groupby("practice")["items"].sum()
    last_month_items = rx[(rx.ym == win[-1]) & rx.chem.isin(new)].groupby("practice")["items"].sum()
    qo_reg = qof[qof.qof_year == qo].set_index("practice")[regcol]
    open_at_outcome = set(tot[tot.ym == win[-1]].practice)
    df["outcome_register"] = qo_reg.reindex(df.index).astype(float)
    df["outcome_items"] = out_items.reindex(df.index).fillna(0)
    df["outcome_rate"] = 1000 * df.outcome_items / df.outcome_register
    df["exclusion"] = ""
    df.loc[~df.index.isin(open_at_outcome), "exclusion"] = "closed by month 24"
    df.loc[(df.exclusion == "") & df.outcome_register.isna(), "exclusion"] = "not in outcome QOF"
    df.loc[(df.exclusion == "") & (df.outcome_register < MIN_OUTCOME_REGISTER), "exclusion"] = \
        f"register < {MIN_OUTCOME_REGISTER}"
    df.loc[(df.exclusion == "") & df[["register", "list_size"]].isna().any(axis=1), "exclusion"] = \
        "missing feature"
    df["in_training"] = df.exclusion == ""
    tr = df.in_training
    cut = df.loc[tr, "outcome_rate"].quantile(1 - TOP_SHARE)
    df["target"] = np.where(tr, (df.outcome_rate >= cut).astype(int), -1)
    if cut <= 0:
        # More than 80% of practices have zero uptake (a niche drug), so "top 20%"
        # is ill-defined; the target becomes "prescribed the drug at all"
        df["target"] = np.where(tr, (df.outcome_rate > 0).astype(int), -1)
        log(f"NOTE: over 80% of practices had zero uptake, so target = any prescribing "
            f"({(df.target == 1).sum():,} practices, {(df.target == 1).sum() / tr.sum():.1%})")

    # Sensitivity: single month 24 instead of months 22-24
    m24 = 1000 * last_month_items.reindex(df.index).fillna(0) / df.outcome_register
    top_m24 = m24[tr] >= m24[tr].quantile(1 - TOP_SHARE)
    agree = (top_m24 & (df.loc[tr, "target"] == 1)).sum() / (df.loc[tr, "target"] == 1).sum()

    numeric = ["list_size", "register", "prevalence", "older_alt_per_1k_reg", "total_items_per_1k_list",
               "adopt_speed", "early_adopter_share",
               "area_adopt_speed", "area_older_alt_per_1k_reg", "area_total_items_per_1k_list"]
    for c in numeric:
        df[c + "_pct"] = pct_rank(df[c])

    # Checks
    assert max(used_months) < launch, f"{key}: a feature uses a month on/after launch"
    log(f"\n== {key}: launch {launch}, features from QOF {qf} (published {QOF_PUBLISHED[qf]}) "
        f"and months {pre12[0]}-{pre12[-1]}; outcome months {win[0]}-{win[-1]}, register from QOF {qo}")
    log(f"Latest month used by any feature: {max(used_months)} (must be before {launch})")
    log(f"Practices active at launch: {len(df):,}; exclusions: "
        + ", ".join(f"{k} {v:,}" for k, v in df.exclusion.value_counts().items() if k))
    log(f"Training rows: {tr.sum():,}; top-20% cut-off: {cut:.1f} items per 1,000 register patients "
        f"(3 months); target=1: {(df.target == 1).sum():,}")
    log(f"Practices with zero new-drug items at outcome: {(df.loc[tr, 'outcome_items'] == 0).mean():.1%}")
    log(f"Top-20% overlap if we used month 24 alone: {agree:.1%}")
    log(f"Earlier new drugs used for adoption speed ({len(used)}): " + "; ".join(used))
    log("Missing values in features: " + ", ".join(
        f"{c} {df.loc[tr, c].isna().sum()}" for c in numeric + ["region"] if df.loc[tr, c].isna().sum()) or "none")
    log("Single-feature AUC (0.5 = no signal, 1 = perfect; >0.9 would suggest leakage):")
    t = df[tr]
    for c in numeric:
        log(f"  {c:26s} {auc(t[c], t.target):.3f}")
    g = t.groupby("area").target
    loo = (g.transform("sum") - t.target) / (g.transform("count") - 1)
    log(f"  [insight, NOT a feature: uses the outcome] other practices in the same area: {auc(loo, t.target):.3f}")
    log(f"Practices with no area: {df.area.isna().sum()}")
    log("Share in top 20% by region:")
    log(t.groupby("region").target.mean().sort_values(ascending=False).map("{:.1%}".format).to_string())

    df.insert(0, "launch", key)
    df["launch_month"] = launch
    return df.reset_index()


def main() -> None:
    qof = pd.read_csv(P / "qof_registers.csv", dtype={"practice": str})
    gp = set(qof.practice)
    rx = pd.read_parquet(P / "rx_chem_monthly.parquet")
    tot = pd.read_parquet(P / "practice_totals.parquet")
    region = build_regions(gp)
    nd = earlier_new_drugs(rx)
    log("\n== Earlier new drugs found in the data (launch month = first with >= 10 practices)")
    log(", ".join(f"{k}:{v[1]}" for k, v in sorted(nd.items(), key=lambda x: x[1][1])))

    feats = pd.concat([build_launch(k, rx, tot, qof, region, nd) for k in SETUP], ignore_index=True)
    feats.to_parquet(P / "features.parquet", index=False)
    log(f"\nWrote features.parquet: {len(feats):,} rows, {feats.in_training.sum():,} training rows")
    (ROOT / "reports/stage2_checks.txt").write_text("\n".join(OUT_LINES) + "\n")


if __name__ == "__main__":
    main()
