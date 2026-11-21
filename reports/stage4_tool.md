# Stage 4: The targeting tool

*Built 21 Nov 2026. The tool is `reports/tool/index.html`: one self-contained page with the data inlined, and a private copy is published at https://claude.ai/artifact/TGf1sBvD7RfuwvNjnFFFHu. Scores are in `data/processed/scores_today.parquet`.*

## What it does

Pick the condition the new drug treats (any of **18 conditions** with a GP register, see below) and choose how to rank practices:

- **Propensity:** the model's chance that a practice becomes a top-20% prescriber *per patient on the register*. These are receptive early adopters. In past launches, these practices became top prescribers 1.4× as often as random ones.
- **Opportunity:** propensity × register size, i.e. where the prescriptions are likely to be. In past launches, the top 20% by this ranking wrote 39% of all new-drug items.

The page shows:

- a **map** of all ~6,140 current practices: top 20% dark, next 20% light, the rest grey
- a **ranked list** you can filter by region or search by name, code or postcode
- a **detail panel** with plain-English reasons for the selected practice, e.g. "Neighbouring practices were quick to take up recent new drugs (top 2% of areas)" and "Heavy use of non-insulin diabetes drugs per patient (top 5%)", plus the main drag on its score
- **Copy as CSV**, so a rep can paste the list into a spreadsheet.

## Drug search and the first-line / niche switch

**Type the drug instead of picking a condition.** The search box knows 696 drug names: 312 generic and 384 brand, all prescribed in England in Sep 2026.
- Typing "Mounjaro" shows it is tirzepatide, prescribed for **type 2 diabetes** or **obesity**, and switches to the first. A chip lets you change to the other.
- No AI is involved. Every BNF code says what the drug is for, so the lookup in `src/build_drug_lookup.py` (output `data/processed/drug_lookup.json`) maps each code to the conditions whose existing-treatment codes include it.
- A name that isn't in the data is flagged as probably brand new, and the user picks the condition.

**"How will it be used?" sets the recommended ranking**, based on what worked in the backtests:

| Switch | Recommended ranking | Evidence |
|---|---|---|
| First-line / standard care | Propensity | 1.4–1.6× random in the training launches and COPD |
| Niche / later-line | Opportunity | In the vortioxetine backtest, Propensity was no better than random but Opportunity was 1.4× random and covered 41% of prescriptions |

The user can still override the ranking. If they choose Propensity for a niche drug, the tool shows a warning.

## Conditions covered

The model's features mean the same thing for any condition: register size, prevalence, use of existing treatment per patient, overall prescribing and neighbours' innovation. So the same model can score any condition that has a QOF register. The condition list and the "existing treatment" drug groups are in `src/conditions.py`.

| Status | Conditions | Existing treatment used |
|---|---|---|
| **Backtested** | Type 2 diabetes, atrial fibrillation, heart failure, COPD (frozen-model test, see `copd_backtest.md`) | Non-insulin diabetes drugs; oral anticoagulants; ACE inhibitors, ARBs and Entresto; inhalers |
| **Not validated, good fit** | Hypertension, coronary heart disease, stroke/TIA, peripheral arterial disease, chronic kidney disease, asthma, epilepsy, osteoporosis, obesity | Blood-pressure drugs; statins, antiplatelets and nitrates; inhalers; antidepressants; antiepileptics; bisphosphonates; orlistat, semaglutide and tirzepatide; etc. |
| **Not validated, with a caveat shown in the tool** | Dementia, rheumatoid arthritis, severe mental illness, non-diabetic hyperglycaemia | Usually started by specialists (memory clinics, rheumatology, psychiatry), or few drugs in use |
| Left out | Cancer, learning disability, palliative care | Hospital-led, or registers of patients rather than diseases with a drug market |

The tool shows a "Backtested" or "Not validated" label for whichever condition is selected.

**Caveats for the new conditions:**

- For some conditions the existing-treatment drugs are broad. For example, statins and antiplatelets are used by many patients who don't have PAD or stroke, and some antiepileptics are also used for pain. In those cases the feature measures "how actively the practice prescribes in this drug area", not just treatment of the registered patients. Because only each practice's percentile is used, the ranking still works, but the per-patient numbers aren't literal.
- Semaglutide and tirzepatide share one code whether prescribed for diabetes or weight loss, so the obesity feature includes some diabetes prescribing.
- The honest way to validate a new area is to backtest it on a past launch there, as done for COPD triple inhalers (2017, see `copd_backtest.md`). Depression was then tested on vortioxetine (2015) with a mixed result: Opportunity worked, Propensity didn't (see `depression_backtest.md`). The tool labels it "mixed backtest".

## How "today's" scores are built (same rules as training)

| Feature | Training launches | Today (launch = Oct 2026) |
|---|---|---|
| Registers, list size | Latest QOF published before launch | QOF 2025-26 (published 27 Aug 2026) |
| Existing-treatment use, overall prescribing | 12 months before launch | Oct 2025 – Sep 2026 |
| Neighbours' innovation | Uptake of 2–24 earlier launches (2010-15) in their first 6 months, averaged over the other practices in the PCT/CCG | Uptake of **38 drugs launched 2019-2025** (e.g. tirzepatide, inclisiran, finerenone, new inhalers), averaged over the other practices in the **sub-ICB** (106 areas) |

**"Existing treatment" today** is what a new drug in each area would compete with, as listed in the table above. Prescribing for the extra areas (inhalers, antidepressants, statins and so on) was downloaded separately by `src/fetch_epd_extra.py` for Oct 2025 – Sep 2026 (12 months, 37 MB).

**How the recent launches were found.** I ran a national scan every three months from 2019 to 2026, using the rule from training: reaches 10 practices after Jan 2019 and 100+ a year later.

- The scan first flagged 180 candidates. 142 of them were nutrition products (BNF 9.13–9.14) that were all given new codes in Nov 2022, so they were excluded as not real launches.
- That left 38 genuine drug launches.

**Map locations** come from practice postcodes via postcodes.io. 4 practices couldn't be placed on the map but still appear in the list.

## Interview talking points

- **Two lenses, one model.** "Who is receptive?" and "where is the volume?" are different questions. The tool answers both and shows the trade-off openly, instead of hiding it behind one score.
- **Explainable by design.** Logistic regression lets every score be broken into per-feature contributions, so each practice comes with two or three sentences a rep can act on.
- **Same rules today as in training.** Today's scores use the same "known on launch day" rules as the backtests, so the backtest results are a fair guide to what to expect.

## Limits

- The scores are **relative within England today** (percentiles), as in training. They say which practices to prioritise, not how many prescriptions to expect.
- **The local area changed definition:** PCT/CCG in training, sub-ICB today. Sub-ICBs are similar in size to CCGs (106 areas vs 211), so I expect it to transfer, but it is untested.
- **A condition without a QOF register** (e.g. migraine, psoriasis) would need a different denominator, such as patients already on related drugs.
- **I could not view the rendered page from this session.** The browser pane wasn't signed in to claude.ai, and the local preview server was blocked by folder permissions. The script passes a syntax check and the data has no missing values, but the layout should get a quick look by eye.

## Rebuild

```bash
python3 -I src/geocode_practices.py "$PWD"        # map coordinates
python3 -I src/find_recent_launches.py "$PWD"     # national scan, ~3 min
python3 -I src/fetch_recent_uptake.py "$PWD"      # practice uptake of the 38 launches
python3 -I src/fetch_epd_extra.py "$PWD"          # existing-treatment prescribing for the extra conditions
python3 -I src/build_drug_lookup.py "$PWD"        # drug-name search
.venv/bin/python -I src/score_today.py "$PWD"     # scores + reports/tool/index.html
```
