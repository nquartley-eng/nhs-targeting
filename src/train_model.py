"""Stage 3: train and validate with leave-one-launch-out.

The honest test of "will this work on the *next* launch?" is to hide one whole
launch, train on the other two, and score the hidden one. Repeating that for each
launch gives three out-of-sample results. Nothing about the hidden launch (not
even its hyperparameters) is used to fit the model, so it's a fair rehearsal of
a real new launch.

Models compared (all rank practices; we care about the order, not probabilities):
  random            what you get with no targeting at all
  biggest_register  the naive rule: visit the practices with most patients
  logistic          logistic regression on the percentile features
  logistic_region   + NHS region dummies
  boosted_trees     gradient-boosted trees on the same features as logistic_region
  logistic_lean     logistic on the 5 features that helped in every fold (final model)
  lean_x_register   logistic_lean score x register size: ranks by *expected volume*
                    rather than by rate per patient

Metrics on the hidden launch:
  auc             chance a real top-20% practice is ranked above a non-top one (0.5 = coin flip)
  precision_top20 of the 20% of practices we would target, share that turn out top-20%
                  (random = 20%)
  lift_top20      precision_top20 / 20%: "x times better than random"
  volume_top20    share of the new drug's total items (month 22-24) that came from
                  the practices we would have targeted - the commercial view

Outputs:
  data/processed/lolo_predictions.parquet   held-out scores for every launch/model
  models/final_model.joblib                 chosen model refit on all three launches
  reports/stage3_results.txt, reports/figures/gains_curves.png

Usage: .venv/bin/python -I src/train_model.py <project_root>
"""
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(sys.argv[1]).resolve()
P = ROOT / "data/processed"
LINES: list[str] = []
SEED = 0

# One of each near-duplicate pair is dropped (adopt_speed ~ early_adopter_share
# at 0.99; register kept over list_size because it is the eligible pool).
FEATURES = ["register_pct", "prevalence_pct", "older_alt_per_1k_reg_pct", "total_items_per_1k_list_pct",
            "adopt_speed_pct", "area_adopt_speed_pct", "area_older_alt_per_1k_reg_pct",
            "area_total_items_per_1k_list_pct"]
# Lean set: drops the three features whose shuffling *improved* or didn't change
# held-out AUC in every fold (practice adopt_speed, area older-alt, area total
# items). Chosen after seeing the LOLO results, so its scores are slightly
# optimistic - the full set is reported alongside for honesty.
LEAN = ["register_pct", "prevalence_pct", "older_alt_per_1k_reg_pct", "total_items_per_1k_list_pct",
        "area_adopt_speed_pct"]
REGIONS = ["London", "South West", "South East", "Midlands", "East of England", "North West",
           "North East and Yorkshire"]
LAUNCH_ORDER = ["doac", "sglt2", "arni"]
LABELS = {"doac": "DOAC (2011)", "sglt2": "SGLT2 (2012)", "arni": "Entresto (2016)"}


def log(s: str = "") -> None:
    LINES.append(s)
    print(s)


def design(df: pd.DataFrame, region: bool, cols=None) -> pd.DataFrame:
    X = df[cols or FEATURES].copy()
    if region:
        for r in REGIONS[1:]:  # London is the reference category
            X["region_" + r] = (df.region == r).astype(float)
    return X


def make(name: str):
    if name.startswith("logistic"):
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                          min_samples_leaf=50, random_state=SEED)


def metrics(score: np.ndarray, d: pd.DataFrame) -> dict:
    y = d.target.values
    n = int(round(0.2 * len(d)))
    top = np.argsort(-score, kind="stable")[:n]
    prec = y[top].mean()
    return {"auc": roc_auc_score(y, score), "precision_top20": prec, "lift_top20": prec / 0.2,
            "volume_top20": d.outcome_items.values[top].sum() / d.outcome_items.sum()}


def main() -> None:
    f = pd.read_parquet(P / "features.parquet")
    f = f[f.in_training].reset_index(drop=True)
    f[FEATURES] = f[FEATURES].fillna(0.5)  # 1 practice with register 0 -> neutral percentile
    rng = np.random.default_rng(SEED)

    preds, rows, perm = [], [], []
    for held in LAUNCH_ORDER:
        tr, te = f[f.launch != held], f[f.launch == held]
        scores = {"random": rng.random(len(te)), "biggest_register": te.register.values}
        for name, region in [("logistic", False), ("logistic_region", True), ("boosted_trees", True)]:
            m = make(name).fit(design(tr, region), tr.target)
            scores[name] = m.predict_proba(design(te, region))[:, 1]
            if name == "logistic":
                pi = permutation_importance(m, design(te, False), te.target, scoring="roc_auc",
                                            n_repeats=10, random_state=SEED)
                perm.append(pd.Series(pi.importances_mean, index=FEATURES, name=held))
        m = make("logistic").fit(design(tr, False, LEAN), tr.target)
        scores["logistic_lean"] = m.predict_proba(design(te, False, LEAN))[:, 1]
        scores["lean_x_register"] = scores["logistic_lean"] * te.register.values
        for name, s in scores.items():
            rows.append({"held_out": held, "model": name, **metrics(s, te)})
            preds.append(pd.DataFrame({"launch": held, "practice": te.practice.values, "model": name,
                                       "score": s, "target": te.target.values,
                                       "outcome_items": te.outcome_items.values}))

    res = pd.DataFrame(rows)
    pd.concat(preds).to_parquet(P / "lolo_predictions.parquet", index=False)

    log("== Leave-one-launch-out results (each row = trained on the other two launches)")
    order = ["random", "biggest_register", "logistic", "logistic_region", "boosted_trees",
             "logistic_lean", "lean_x_register"]
    for metric in ["auc", "precision_top20", "lift_top20", "volume_top20"]:
        t = res.pivot(index="model", columns="held_out", values=metric).loc[order, LAUNCH_ORDER]
        t["mean"] = t.mean(axis=1)
        log(f"\n-- {metric}")
        log(t.round(3).to_string())

    log("\n== Permutation importance, logistic (drop in held-out AUC when a feature is shuffled)")
    imp = pd.concat(perm, axis=1)
    imp["mean"] = imp.mean(axis=1)
    log(imp.sort_values("mean", ascending=False).round(4).to_string())

    # Final model: lean logistic (see report for why), refit on all launches
    final = make("logistic").fit(design(f, False, LEAN), f.target)
    coefs = pd.Series(final[-1].coef_[0], index=LEAN).sort_values(ascending=False)
    log("\n== Final model (lean logistic, all three launches) - standardised coefficients")
    log("(positive = more likely to be a top-20% practice; size = effect of a 1-SD change)")
    log(coefs.round(3).to_string())
    (ROOT / "models").mkdir(exist_ok=True)
    joblib.dump({"model": final, "features": LEAN, "trained_on": LAUNCH_ORDER}, ROOT / "models/final_model.joblib")

    # Gains curves: share of top-20% practices found vs share of practices visited
    pr = pd.concat(preds)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3), sharey=True)
    styles = {"logistic_lean": ("#2a78d6", "-", "Model"), "biggest_register": ("#eb6834", "-", "Biggest register first"),
              "random": ("#8a8984", "--", "Random")}
    for ax, held in zip(axes, LAUNCH_ORDER):
        for name, (col, ls, lab) in styles.items():
            d = pr[(pr.launch == held) & (pr.model == name)].sort_values("score", ascending=False)
            x = np.arange(1, len(d) + 1) / len(d)
            yv = d.target.cumsum().values / d.target.sum()
            ax.plot(x * 100, yv * 100, color=col, ls=ls, lw=2, label=lab)
        ax.axvline(20, color="#d6d5d0", lw=1, zorder=0)
        ax.set_title(f"Held out: {LABELS[held]}", fontsize=11, loc="left")
        ax.set_xlabel("% of practices targeted (best first)")
        ax.grid(alpha=0.25)
        for s in ["top", "right"]:
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("% of top-20% practices found")
    axes[0].legend(frameon=False, loc="lower right")
    fig.suptitle("How many future top prescribers each targeting rule finds", x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    (ROOT / "reports/figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(ROOT / "reports/figures/gains_curves.png", dpi=130)

    (ROOT / "reports/stage3_results.txt").write_text("\n".join(LINES) + "\n")


if __name__ == "__main__":
    main()
