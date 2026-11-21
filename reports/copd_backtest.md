# COPD backtest: triple inhalers (2017)

*Run 21 Nov 2026 by `src/backtest_launch.py <root> copd`. Full output is in `reports/copd_backtest.txt`.*

## Why this test matters

The model was trained on three cardiometabolic launches. The tool applies it to 15 other conditions, which is only defensible if it works outside that area. So I took a respiratory launch the model has **never seen** and scored it with the model **frozen** exactly as it was at the end of Stage 3: no retraining, no tuning, and the same feature code as Stage 2.

## The launch

**Single-inhaler triple therapy for COPD:** Trimbow, then Trelegy. Each combines an inhaled steroid, a long-acting beta-agonist (LABA) and a long-acting muscarinic antagonist (LAMA) in one device. I treated them as one class launch, like the DOACs.

| | |
|---|---|
| Launch month (from the data) | **Sep 2017**: Trimbow reaches 30 practices (1 in Aug). Trelegy starts in Dec 2017 |
| Features | QOF 2015-16 (2016-17 wasn't published until Oct 2017, after launch); prescribing Sep 2016 – Aug 2017 |
| Outcome | Trimbow + Trelegy items in Jul–Sep 2019, per 1,000 COPD register patients (QOF 2018-19). This ends before COVID disrupted prescribing |
| Existing treatment | All inhaled and other asthma/COPD drugs (BNF 3.1–3.3) |
| Practices | 6,641 in the test; 1,330 top-20% |

**A data detail worth knowing.** Trelegy shares its chemical code with an older inhaler, Relvar, so the usual chemical-level data can't tell them apart. I separated it using its product code (`0302000V0BC…`).

## Results

| Ranking | AUC | Became top-20% | vs random | Share of all triple-inhaler items |
|---|---|---|---|---|
| Random | 0.50 | 20% | 1.0× | 21% |
| Biggest register first | 0.55 | 23% | 1.1× | 43% |
| **Model: propensity** | **0.68** | **32%** | **1.6×** | 22% |
| **Model: opportunity** | 0.62 | 30% | 1.5× | **47%** |

For comparison, the average across the three training launches (each hidden in turn) was 28% and 1.4×. **The model did better on a launch from a different therapy area than it did on its own training launches.**

The opportunity ranking also beats "biggest practices first" on both counts here: it finds more top prescribers (30% vs 23%) *and* covers more of the volume (47% vs 43%).

**It's not just geography.** Comparing practices only against others in their own region, the model's AUC is still 0.60–0.70 in every region. Regions do differ a lot: 43% of North West practices were top-20%, against 2% in London. The model ranks well within regions as well as between them.

## Why COPD may have been easier

- **Prevalence and overall prescribing intensity were strong signals** (single-feature AUC 0.64 and 0.66), more so than for the heart launches.
  - COPD is concentrated in areas with high smoking rates and deprivation, and practices there both have more patients and prescribe more inhalers per patient.
- **Triple inhalers were adopted widely.** Only 8% of practices had none at month 24, against 19–47% for the training launches. So the outcome measures *how much* a practice uses the drug rather than *whether* it uses it at all, and that is easier to predict.

## What this does and doesn't show

- **It does show** that the model carries over to a different therapy area without retraining. That is the main condition for using it on the other 15 conditions in the tool.
- **It doesn't show** that every condition will work this well. COPD and the three training launches are all long-term conditions managed mainly by GPs. Conditions where specialists start the drug (dementia, RA, severe mental illness) are still unvalidated and labelled as such in the tool.
- **The launch was chosen before the result was known.** The triple inhalers were the launch I had suggested, and the class definition, dates and code rules were fixed before scoring. There was no picking of a flattering example after seeing results.

## Changes made

- `src/load_qof.py` now also loads COPD registers (all 11 QOF years); the other registers are unchanged.
- `src/backtest_launch.py` (run with `copd`) downloads the respiratory prescribing it needs (15 months, via the NHSBSA API) and runs the test.
- In the tool, COPD is now listed under "Tested on past launches", and the backtest result is shown.
