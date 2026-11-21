# Depression backtest: vortioxetine (2015)

*Run 21 Nov 2026 by `src/backtest_launch.py <root> depression`. Full output is in `reports/depression_backtest.txt`.*

## The test

As with COPD, the model was **frozen**: trained only on DOAC, SGLT2 and Entresto, and applied with no retraining. The features and target come from the same Stage 2 code.

| | |
|---|---|
| Drug | Vortioxetine (Brintellix), BNF `0403040AB` |
| Launch month (from the data) | **Dec 2015**: 22 practices (6 in Nov). NICE recommended it in Nov 2015 for patients after two failed antidepressants |
| Features | QOF 2014-15 (published Oct 2015); prescribing Dec 2014 – Nov 2015 |
| Outcome | Vortioxetine items in Oct–Dec 2017, per 1,000 depression register patients (QOF 2017-18) |
| Existing treatment | All antidepressants (BNF 4.3) |
| Practices | 7,034 in the test; 1,407 top-20% |

## Results

| Ranking | AUC | Became top-20% | vs random | Share of all vortioxetine items |
|---|---|---|---|---|
| Random | 0.51 | 20% | 1.0× | 19% |
| Biggest register first | 0.58 | 25% | 1.2× | 37% |
| Model: propensity | 0.52 | 21.5% | 1.07× | 22% |
| **Model: opportunity** | **0.60** | **27%** | **1.37×** | **41%** |

**The result is mixed.**

- **The propensity ranking failed.** It was barely better than random overall, and no better than random inside six of the seven regions.
- **The opportunity ranking worked.** It beat both random and "biggest practices first", on top prescribers found and on share of volume.

## Why propensity failed here

**1. It was a niche drug, so "top 20%" really meant "prescribed it at all".** Two years after launch, **74% of practices had prescribed no vortioxetine**, against 8% for COPD triple inhalers and 19–47% for the training launches. With three-quarters of practices at zero, the top 20% are mostly practices that had at least one suitable patient. That depends heavily on size: a practice with more depressed patients is more likely to have one who has failed two antidepressants. List size alone scores AUC 0.61. The propensity model learned from the training launches that larger registers are slightly *less* likely to be top-20% per patient, which is the wrong direction for a niche drug.

**2. Its innovation signals didn't carry over.** The neighbours' innovation feature, the model's strongest, scored only 0.53 here (0.59–0.64 elsewhere). A third-line antidepressant tends to be started after advice from mental-health services, so a GP practice's general appetite for new drugs matters less.

The local area still mattered a lot. Using the outcome (so as a check, not a feature), other practices in the same area predict a practice's uptake with AUC 0.75. That points again to local services and formularies.

## What this means for the tool

- **Depression is labelled "mixed backtest" in the tool**, with advice to use the Opportunity ranking.
- **The general lesson:** the model predicts *how intensively* practices adopt a drug that becomes standard care (DOACs, SGLT2s, triple inhalers). It does not predict *whether* practices adopt a niche or later-line drug. For niche drugs, size-weighted targeting (Opportunity) is the safer choice, and the tool's notes now say so.
- **Interview point:** I tested where the model breaks, not only where it works. Knowing where a model fails is as useful to a client as the headline number.

## Possible improvement

A launch team usually knows in advance whether a drug will be first-line or niche. A future version could take that as an input: for niche drugs, it would predict "any prescribing" instead of "top 20% per patient" and train on niche launches. That would need more niche launches to learn from.
