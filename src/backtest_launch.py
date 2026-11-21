"""Out-of-sample backtests on launches the model has never seen.

The model in models/final_model.joblib (trained on DOAC, SGLT2 and Entresto,
frozen in Stage 3) is applied unchanged. Features and target are built by the
same code as Stage 2 (build_features.build_launch), with the same rules:
features from the 12 months before launch and the latest QOF year published
before launch; outcome = new-drug items in months 22-24 per 1,000 register
patients, register from the QOF snapshot closest to that window.

Launches:
  copd        Single-inhaler triple therapy: Trimbow (0301011AB) from Sep 2017
              (30 practices; 1 in Aug), then Trelegy from Dec 2017. Trelegy shares
              its chemical code with Relvar (0302000V0), so it is picked out by its
              product code (0302000V0BC...) as key "TRELEGY". Outcome Jul-Sep 2019,
              before COVID-19. Feature QOF 2015-16 (2016-17 was published Oct 2017).
  depression  Vortioxetine (0403040AB), from Dec 2015 (22 practices; NICE TA367 was
              Nov 2015). A third-line antidepressant, so uptake stayed niche.
              Outcome Oct-Dec 2017. Feature QOF 2014-15 (published Oct 2015).

Outputs: data/processed/<launch>/*, reports/<launch>_backtest.txt
Usage:   .venv/bin/python -I src/backtest_launch.py <project_root> <copd|depression>
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
KEY = sys.argv[2]
sys.path.insert(0, str(ROOT / "src"))
import build_features as bf  # noqa: E402
from fetch_epd import run_sql, table_for, write_gz  # noqa: E402
from train_model import metrics  # noqa: E402

P = ROOT / "data/processed"
CONFIGS = {
    "copd": {"launch": "201709", "feature_qof": "2015-16", "outcome_qof": "2018-19", "register": "copd_register",
             "prefixes": ["0301", "0302", "0303"],
             "new": {"0301011AB": "Trimbow (beclometasone/formoterol/glycopyrronium)",
                     "TRELEGY": "Trelegy (fluticasone furoate/umeclidinium/vilanterol)"},
             "product_keys": {"TRELEGY": "0302000V0BC"}},
    "depression": {"launch": "201512", "feature_qof": "2014-15", "outcome_qof": "2017-18", "register": "dep_register",
                   "prefixes": ["0403"], "new": {"0403040AB": "Vortioxetine"}, "product_keys": {}},
}
C = CONFIGS[KEY]
D = P / KEY
FEATURE_MONTHS = bf.months(bf.add_months(C["launch"], -12), bf.add_months(C["launch"], -1))
OUTCOME_MONTHS = bf.months(bf.add_months(C["launch"], 22), bf.add_months(C["launch"], 24))


def download(have_totals: set[str]) -> None:
    """Therapy-area prescribing by practice for the feature and outcome months,
    plus practice totals for any outcome month not already held."""
    D.mkdir(parents=True, exist_ok=True)
    for ym in FEATURE_MONTHS + OUTCOME_MONTHS:
        path = D / f"rx_{ym}.csv.gz"
        if path.exists():
            continue
        table, chem, _ = table_for(ym)
        key = chem
        if C["product_keys"]:
            key = "CASE " + " ".join(f"WHEN BNF_CODE LIKE '{p}%' THEN '{k}'" for k, p in C["product_keys"].items()) \
                  + f" ELSE {chem} END"
        where = " OR ".join(f"{chem} LIKE '{p}%'" for p in C["prefixes"])
        rows = run_sql(table, f"SELECT YEAR_MONTH AS ym, PRACTICE_CODE AS practice, {key} AS chem, "
                              f"SUM(ITEMS) AS items FROM `{table}` WHERE {where} "
                              f"GROUP BY YEAR_MONTH, PRACTICE_CODE, {key}")
        write_gz(path, rows)
        print(ym, f"{len(rows):,} rows", flush=True)
    for ym in OUTCOME_MONTHS:
        path = D / f"totals_{ym}.csv.gz"
        if ym in have_totals or path.exists():
            continue
        table, _, _ = table_for(ym)
        rows = run_sql(table, f"SELECT YEAR_MONTH AS ym, PRACTICE_CODE AS practice, SUM(ITEMS) AS total_items "
                              f"FROM `{table}` GROUP BY YEAR_MONTH, PRACTICE_CODE")
        write_gz(path, rows)
        print(ym, "totals", f"{len(rows):,}", flush=True)


def main() -> None:
    tot = pd.read_parquet(P / "practice_totals.parquet")
    download(set(tot.ym))
    qof = pd.read_csv(P / "qof_registers.csv", dtype={"practice": str})
    gp = set(qof.practice)
    base_rx = pd.read_parquet(P / "rx_chem_monthly.parquet")
    region = bf.build_regions(gp)
    nd = bf.earlier_new_drugs(base_rx)  # same earlier-launch list as training

    # Therapy-area rows come from the new download; drop any rows for those BNF
    # prefixes already in base_rx for the same months so nothing is counted twice
    new = pd.concat(pd.read_csv(f, dtype={"chem": str, "practice": str}) for f in sorted(D.glob("rx_*.csv.gz")))
    new["ym"] = new.ym.astype(str).str.replace("-", "")
    new = new[new.practice.isin(gp)]
    months = set(new.ym)
    clash = base_rx.ym.isin(months) & base_rx.chem.str.startswith(tuple(C["prefixes"]))
    rx = pd.concat([base_rx[~clash], new[["ym", "practice", "chem", "items"]]], ignore_index=True)
    extra_tot = [pd.read_csv(f, dtype={"practice": str}) for f in sorted(D.glob("totals_*.csv.gz"))]
    if extra_tot:
        t = pd.concat(extra_tot)
        t["ym"] = t.ym.astype(str).str.replace("-", "")
        tot = pd.concat([tot, t[t.practice.isin(gp)]], ignore_index=True)

    bf.LAUNCHES[KEY] = {"new_drugs": C["new"], "older_alternative_prefixes": C["prefixes"],
                        "older_alternative_exclude": list(C["new"])}
    bf.SETUP[KEY] = (C["launch"], C["feature_qof"], C["outcome_qof"], C["register"])
    nat = new[new.chem.isin(C["new"])].groupby("ym").agg(items=("items", "sum"), practices=("practice", "nunique"))
    bf.log(f"== National uptake of {', '.join(C['new'].values())} in the downloaded months")
    bf.log(nat.to_string())
    df = bf.build_launch(KEY, rx, tot, qof, region, nd)
    df.to_parquet(D / f"features_{KEY}.parquet", index=False)

    bundle = joblib.load(ROOT / "models/final_model.joblib")
    t = df[df.in_training].reset_index(drop=True)
    score = bundle["model"].predict_proba(t[bundle["features"]].fillna(0.5))[:, 1]
    rng = np.random.default_rng(0)
    rows = {"random": rng.random(len(t)), "biggest_register": t.register.values,
            "model (propensity)": score, "model x register (opportunity)": score * t.register.values}
    res = pd.DataFrame({k: metrics(v, t) for k, v in rows.items()}).T
    bf.log(f"\n== {KEY} backtest: frozen model, never trained on this launch")
    bf.log(res.round(3).to_string())
    t["score"] = score
    within = t.groupby("region").apply(
        lambda g: metrics(g.score.values, g)["auc"] if g.target.nunique() > 1 else np.nan, include_groups=False)
    bf.log("\nAUC within each region (ranking practices against their own region only):")
    bf.log(within.round(3).to_string())
    (ROOT / f"reports/{KEY}_backtest.txt").write_text("\n".join(bf.OUT_LINES) + "\n")


if __name__ == "__main__":
    main()
