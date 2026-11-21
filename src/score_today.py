"""Stage 4: score every current GP practice for a drug launching now.

"Now" = Oct 2026, the month after our latest data (Sep 2026). Features are built
exactly as in training, with the same at-launch rule:
  - registers and list size: QOF 2025-26 (published 27 Aug 2026)
  - prescribing: the 12 months Oct 2025 - Sep 2026
  - neighbours' innovation: how fast practices in the same sub-ICB area took up
    drugs launched 2019-2025 (src/find_recent_launches.py, fetch_recent_uptake.py)

The tool covers 18 conditions with a QOF register (src/conditions.py). For each,
"existing treatment" is the drug group a new entrant would compete with or be
added to. Only diabetes, AF and heart failure were backtested; the others reuse
the same model and are labelled "not validated" in the tool.

Two rankings, because "best practice" depends on the goal:
  propensity   the model's probability of being a top-20% prescriber per patient
               (receptive early adopters)
  opportunity  propensity x register size, i.e. expected volume (where the
               prescriptions will be). In validation this captured 39% of all
               new-drug items from 20% of practices.

Each practice gets plain-English reasons: the features pushing its score up
most (and the main drag), from the logistic model's per-feature contributions.

Output: data/processed/scores_today.parquet, reports/tool/practices.json,
        reports/tool/index.html (the tool, data inlined into template.html)
Usage:  .venv/bin/python -I src/score_today.py <project_root>
"""
import json
import re
import sys
from pathlib import Path

import zipfile

import joblib
import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
P = ROOT / "data/processed"
sys.path.insert(0, str(ROOT / "src"))
from conditions import CONDITIONS as AREAS  # noqa: E402
MONTHS = [f"{y}{m:02d}" for y, m in [(2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]]
QOF_YEAR = "2025-26"
REGION_NAMES = {"Y56": "London", "Y58": "South West", "Y59": "South East", "Y60": "Midlands",
                "Y61": "East of England", "Y62": "North West", "Y63": "North East and Yorkshire"}

# How each feature reads in a sentence, given its percentile (0-1)
def phrase(feat: str, pct: float, area_cfg: dict, row: pd.Series) -> str:
    top = f"top {max(1, round(100 * (1 - pct)))}%"
    bottom = f"bottom {max(1, round(100 * pct))}%"
    rank = top if pct >= 0.5 else bottom
    return {
        "area_adopt_speed_pct": f"Neighbouring practices were {'quick' if pct >= .5 else 'slow'} to take up recent new drugs ({rank} of areas)",
        "older_alt_per_1k_reg_pct": f"{'Heavy' if pct >= .5 else 'Light'} use of {area_cfg['existing_label']} per patient ({rank}): "
                                    f"{'a large' if pct >= .5 else 'a small'} pool of treated patients who could switch",
        "total_items_per_1k_list_pct": f"{'High' if pct >= .5 else 'Low'} overall prescribing per patient ({rank})",
        "prevalence_pct": f"{'High' if pct >= .5 else 'Low'} prevalence: {row.prevalence:.1f}% of patients on the register ({rank})",
        "register_pct": f"{'Large' if pct >= .5 else 'Small'} register: {int(row.register):,} patients ({rank})",
    }[feat]


def registers_2526() -> pd.DataFrame:
    """practice x register name, all QOF 2025-26 registers. Where a condition has
    two rows (heart failure + its LVSD sub-register) the register names differ,
    so each is kept separately; age-band list types don't matter for registers."""
    with zipfile.ZipFile(ROOT / "data/raw/qof/2025-26/QOF_2526_v2.zip") as z:
        d = pd.read_csv(z.open("PREVALENCE_2526.csv"), encoding="latin-1")
    return d.pivot_table(index="PRACTICE_CODE", columns="REGISTER_NAME", values="REGISTER_SIZE", aggfunc="max")


def pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average")


def main() -> None:
    bundle = joblib.load(ROOT / "models/final_model.joblib")
    model, feats = bundle["model"], bundle["features"]
    scaler, lr = model[0], model[-1]

    qof = pd.read_csv(P / "qof_registers.csv", dtype={"practice": str})
    q = qof[qof.qof_year == QOF_YEAR].set_index("practice")
    regs = registers_2526()
    rx = pd.concat([pd.read_csv(P / f"{folder}/rx_{m}.csv.gz", usecols=["practice", "chem", "items"], dtype={"chem": str})
                    for m in MONTHS for folder in ("epd", "epd_extra")])
    tot = pd.concat(pd.read_csv(P / f"epd/totals_{m}.csv.gz", dtype=str) for m in MONTHS)
    tot["total_items"] = tot.total_items.astype(float)
    latest = tot[tot.ym.str.replace("-", "") >= "202607"]  # open in the last 3 months
    info = latest.sort_values("ym").drop_duplicates("practice", keep="last").set_index("practice")

    base = pd.DataFrame(index=sorted(set(q.index) & set(info.index)))
    base.index.name = "practice"
    # Capitalise each word, keeping apostrophes inside it ("HENDOW'S" -> "Hendow's", not
    # str.title()'s "Hendow'S") and short bracketed initials as capitals ("(AWC)")
    def tidy(x: str) -> str:
        x = re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", lambda m: m.group(0).capitalize(), str(x).lower())
        return re.sub(r"\(([A-Za-z]{2,3})\)", lambda m: f"({m.group(1).upper()})", x)
    base["name"] = info.practice_name.reindex(base.index).map(tidy)
    base["postcode"] = info.postcode.reindex(base.index)
    base["sub_icb"] = info.pco_code.reindex(base.index)
    base["icb"] = info.area_code.reindex(base.index)
    base["region"] = info.region_code.reindex(base.index).map(REGION_NAMES)
    base["list_size"] = q.list_size.reindex(base.index).astype(float)
    t12 = tot.groupby("practice").total_items.sum()
    base["total_items_per_1k_list"] = 1000 * t12.reindex(base.index).fillna(0) / base.list_size

    # Neighbours' innovation: practice adoption speed of 2019-2025 launches,
    # averaged over the *other* practices in the same sub-ICB
    up = pd.read_csv(P / "recent_uptake.csv", dtype={"practice": str})
    speed = []
    for chem, g in up.groupby("chem"):
        it = g.groupby("practice")["items"].sum().reindex(base.index).fillna(0)
        speed.append(pct(1000 * it / base.list_size))
    base["adopt_speed"] = pd.concat(speed, axis=1).mean(axis=1)
    g = base.groupby("sub_icb").adopt_speed
    base["area_adopt_speed"] = (g.transform("sum") - base.adopt_speed) / (g.transform("count") - 1)
    n_recent = up.chem.nunique()

    loc = pd.read_csv(P / "practice_locations.csv", dtype={"practice": str}).set_index("practice")
    base = base.join(loc[["lat", "lon"]])
    base["postcode"] = base.postcode.fillna(loc.postcode.reindex(base.index)).fillna("")

    # Features that don't depend on the condition: percentile over all practices, once
    SHARED = ["total_items_per_1k_list_pct", "area_adopt_speed_pct"]
    for f in SHARED:
        base[f] = pct(base[f.removesuffix("_pct")]).fillna(0.5)

    out = []
    for key, cfg in AREAS.items():
        d = base.copy()
        d["register"] = regs[cfg["register"]].reindex(d.index).astype(float)
        d = d[(d.register > 0) & (d.list_size > 0)]
        d["prevalence"] = 100 * d.register / d.list_size
        codes = rx[rx.chem.str.startswith(tuple(cfg["existing"]))].groupby("practice")["items"].sum()
        d["older_alt_per_1k_reg"] = 1000 * codes.reindex(d.index).fillna(0) / d.register
        for f in feats:
            if f not in SHARED:
                d[f] = pct(d[f.removesuffix("_pct")])
        d[feats] = d[feats].fillna(0.5)
        X = d[feats]
        d["propensity"] = model.predict_proba(X)[:, 1]
        d["opportunity"] = d.propensity * d.register
        d["propensity_rank"] = d.propensity.rank(ascending=False, method="first").astype(int)
        d["opportunity_rank"] = d.opportunity.rank(ascending=False, method="first").astype(int)
        contrib = pd.DataFrame(scaler.transform(X) * lr.coef_[0], index=d.index, columns=feats)
        reasons, drags = [], []
        for p, c in contrib.iterrows():
            row = d.loc[p]
            ups = [f for f in c.sort_values(ascending=False).index if c[f] > 0][:2]
            reasons.append([phrase(f, row[f], cfg, row) for f in ups])
            low = c.idxmin()
            drags.append(phrase(low, row[low], cfg, row) if c[low] < 0 else "")
        d["reasons"], d["drag"] = reasons, drags
        d.insert(0, "therapy_area", key)
        out.append(d.reset_index())
        print(f"{key}: {len(d):,} practices scored; propensity range "
              f"{d.propensity.min():.2f}-{d.propensity.max():.2f}")

    s = pd.concat(out, ignore_index=True)
    s.to_parquet(P / "scores_today.parquet", index=False)
    print(f"Recent launches used for neighbours' innovation: {n_recent}; practices without map location: "
          f"{s[s.therapy_area == 'diabetes'].lat.isna().sum()}")

    # Compact JSON for the tool. Reasons are rebuilt in the page from the
    # feature percentiles and the model's coefficients (same maths as above),
    # which keeps the file small.
    codes = list(base.index)
    idx = {p: i for i, p in enumerate(codes)}
    tool = {"data_to": "Sep 2026", "qof_year": QOF_YEAR, "n_recent_launches": int(n_recent),
            "model": {"features": feats, "coef": lr.coef_[0].round(5).tolist(),
                      "mean": scaler.mean_.round(5).tolist(), "scale": scaler.scale_.round(5).tolist()},
            "areas": {k: {"label": v["label"], "existing": v["existing_label"], "validated": v["validated"], "mixed": v["mixed"],
                           "note": v["note"]} for k, v in AREAS.items()},
            "practices": [[p, r["name"], r.postcode, r.region, r.sub_icb,
                           None if pd.isna(r.lat) else round(float(r.lat), 4),
                           None if pd.isna(r.lon) else round(float(r.lon), 4), int(r.list_size)]
                          + [round(float(r[f]), 3) for f in SHARED]
                          for p, r in base.iterrows()],
            "shared": SHARED,
            "scores": {}}
    for key in AREAS:
        d = s[s.therapy_area == key]
        tool["scores"][key] = [[idx[r.practice], int(r.register), round(float(r.propensity), 3),
                                round(float(r.prevalence), 2)] + [round(float(getattr(r, f)), 3) for f in feats
                                                                  if f not in SHARED]
                               for r in d.itertuples()]
    (ROOT / "reports/tool").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/tool/practices.json").write_text(json.dumps(tool, separators=(",", ":")))


def build_page() -> None:
    """Inline the JSON into the page template -> reports/tool/index.html."""
    t = (ROOT / "reports/tool/template.html").read_text()
    data = (ROOT / "reports/tool/practices.json").read_text()
    drugs = (P / "drug_lookup.json").read_text()
    (ROOT / "reports/tool/index.html").write_text(t.replace("/*__DATA__*/null", data).replace("/*__DRUGS__*/[]", drugs))


if __name__ == "__main__":
    main()
    build_page()
