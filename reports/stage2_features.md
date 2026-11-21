# Stage 2: Features and target

*Built 21 Nov 2026 by `src/build_monthly.py` and `src/build_features.py`. The full check output is in `reports/stage2_checks.txt`. The output table is `data/processed/features.parquet`, with one row per launch × practice.*

## The one rule

A feature can only use what a launch team could have known **on launch day**:

- All prescribing features come from the **12 months before** launch.
- Practice size and registers come from the **latest QOF year already published**.
- The script stops with an error if any feature reaches the launch month.

That check caught a real leak. QOF 2010-11 was published on 26 Oct 2011, a month *after* the DOAC launch (Sep 2011). So I downloaded QOF 2009-10 (published Oct 2010) and use that for DOAC instead.

| Launch | Launch month | Features use QOF year (published) | Prescribing months for features | Outcome window | Outcome register from |
|---|---|---|---|---|---|
| DOAC | Sep 2011 | 2009-10 (Oct 2010) | Sep 2010 – Aug 2011 | Jul – Sep 2013 | QOF 2012-13 |
| SGLT2 | Dec 2012 | 2011-12 (Oct 2012) | Dec 2011 – Nov 2012 | Oct – Dec 2014 | QOF 2014-15 |
| ARNI | Apr 2016 | 2014-15 (Oct 2015) | Apr 2015 – Mar 2016 | Feb – Apr 2018 | QOF 2017-18 |

## The target

- **Outcome rate:** items of the new drug class in months 22–24 after launch, per 1,000 patients on the QOF register.
  - I use three months rather than month 24 alone, to smooth out noise. A practice that switches between 28-day and 56-day prescriptions can halve or double its items from one month to the next.
  - Using month 24 alone would still pick 82–88% of the same top-20% practices, so this choice doesn't change much.
- **Target = 1** if the practice is in the top 20% for its launch.
- **Who is in training:** practices that were open at launch, still open at month 24, and have a register of at least 20 patients at outcome.
  - The 20-patient minimum matters because with an HF register of 8, two Entresto patients would put the practice at the top.
  - This mainly affects AF and HF registers, removing about 10–12% of practices for DOAC and ARNI.

| Launch | Practices at launch | Training rows | Top-20% cut-off (items / 1,000 register, 3 months) | Practices with zero uptake at outcome |
|---|---|---|---|---|
| DOAC | 8,275 | 7,127 | 188 | 19% |
| SGLT2 | 8,113 | 7,734 | 46 | 26% |
| ARNI | 7,670 | 6,129 | 76 | 47% |

## The features

Every feature means the same thing for every launch, which leave-one-launch-out validation needs. Each numeric feature also has a `_pct` version: its percentile within the launch. Percentiles put the launches on one scale. An AF register is much smaller than a diabetes register, but "top 10% for register size" means the same thing for both.

| Feature | Plain-English meaning | Why it might matter |
|---|---|---|
| `list_size` | Registered patients | Bigger practices have more prescribers and more capacity |
| `register` | Patients with the condition | The size of the eligible pool |
| `prevalence` | Register as a % of list | A practice where the condition is a big part of its work |
| `older_alt_per_1k_reg` | Items of the older drugs (warfarin; metformin, gliclazide and DPP-4s; ACE inhibitors and ARBs) per 1,000 register patients, over the last year | Patients already treated the old way are the switching pool |
| `total_items_per_1k_list` | All-drug items per 1,000 patients | General prescribing intensity |
| `adopt_speed` | How quickly the practice took up earlier new drugs: for each earlier drug, its use in that drug's first 6 months as a percentile among practices, averaged over the drugs | "Innovators stay innovators" |
| `early_adopter_share` | Share of those earlier drugs it prescribed at all in their first months | A simpler version of the same idea |
| `region` | Current NHS England region (7) | Regional policy and culture |
| `area_*` | The same features averaged over the **other** practices in the local area (PCT, then CCG after 2013) | Local formularies and hospital specialists shape uptake |

**Earlier new drugs.** I took these from the data rather than a list typed in from memory. A drug counts if:

- its first month with at least 10 prescribing practices is visible in the data (after Sep 2010), and
- at least 100 practices were using it a year later.

Examples are ticagrelor, tapentadol, linagliptin, roflumilast, the COPD inhalers, mirabegron and the SGLT2 drugs. The DOAC class, dated from Sep 2011, also counts as one earlier launch for SGLT2 and ARNI.

- **DOAC:** only 2 earlier drugs fit before Sep 2011. The thin pre-launch history was flagged in Stage 1.
- **SGLT2:** 6 earlier drugs.
- **ARNI:** 24 earlier drugs.

**Region for closed practices.** 455 closed practices aren't in the current ODS file. Each gets the most common current region of the other practices in its old local area. After this, no training practice is missing a region.

## What the checks show

**Single-feature AUC.** This measures how well each feature on its own separates top-20% practices from the rest. 0.5 means no better than chance and 1.0 means perfect. It is a sanity check, not a model.

| Feature | DOAC | SGLT2 | ARNI |
|---|---|---|---|
| older_alt_per_1k_reg | 0.53 | **0.60** | **0.59** |
| total_items_per_1k_list | 0.55 | 0.57 | **0.58** |
| adopt_speed | 0.50 | 0.57 | 0.50 |
| area_adopt_speed | 0.56 | **0.59** | 0.54 |
| area_total_items_per_1k_list | 0.50 | 0.54 | **0.59** |
| prevalence | 0.54 | 0.51 | 0.49 |
| list_size | 0.47 | 0.45 | 0.46 |

What this tells us:

1. **No leakage alarm.** Nothing is above 0.9, and in fact nothing is above 0.6. That fits features that genuinely come from before launch.
2. **Each feature on its own is weak.** No single at-launch fact strongly predicts a top prescriber. Stage 3 will show whether combining them helps. Expect a modest model (AUC perhaps 0.6–0.7), not a crystal ball. That is still useful when the baseline is visiting practices at random.
3. **Location matters most.** As a diagnostic only (it uses the outcome, so it can never be a feature), the other practices in the same local area predict a practice's result with AUC 0.73–0.81. Regions differ hugely too: 49% of South West practices were top-20% for DOACs, against 9% in the North West. Uptake is driven largely by the local health economy, meaning hospital consultants, formularies and anticoagulation services, rather than by individual practices.
   - **Interview point:** "the first targeting decision is *which areas*, then which practices within them."
4. **Smaller practices reach the top 20% slightly more often** (list size AUC below 0.5). A rate based on a smaller register swings more, so small practices end up at both extremes. The 20-patient minimum limits this but doesn't remove it.
5. **Two pairs of features are near-duplicates:** `adopt_speed` and `early_adopter_share` (correlation 0.99), and `list_size` and `register` (0.83). Stage 3 should keep one of each pair, or use a model that copes with overlap.

## Hand checks

I recomputed two rows by hand from the raw monthly tables and both match the file exactly:

- Practice A81008, DOAC: 28 items in Jul–Sep 2013 against an AF register of 60, giving 466.7 per 1,000 (top 20%). Its warfarin rate is also correct.
- Practice A81001, SGLT2: 0 items.

## Limits to mention

- **DOAC history is thin.** Only 2 earlier new drugs fit before Sep 2011, so `adopt_speed` carries almost no signal for that launch (AUC 0.50).
- **ARNI shows no practice-level innovation signal (0.50).** One reason is that Entresto is started by hospital heart-failure teams, so the GP practice's own appetite for new drugs matters less.
- **Imperfect denominators:** DOACs also treat clots outside AF, and Entresto suits only one type of heart failure.
- **Not yet included:** deprivation (IMD), practice age profile, and any early-uptake signal from the first months after launch. A "month-3 refresh" of the model would probably predict much better, which is a natural extension.

## Rebuild

```bash
.venv/bin/python -I src/load_qof.py "$PWD"        # now includes QOF 2009-10
.venv/bin/python -I src/build_monthly.py "$PWD"   # ~1 min
.venv/bin/python -I src/build_features.py "$PWD"  # ~1 min
```
