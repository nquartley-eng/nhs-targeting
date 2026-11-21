# Stage 1: Data summary

*Downloaded 20 Nov 2026. All numbers below come from `src/summarise_stage1.py`; the full output is in `reports/stage1_checks.txt`.*

## Headline

All the data needed for the three training launches, plus "today" data for scoring, is downloaded and checks out:

- **113 months** of practice-level prescribing: Aug 2010 to Dec 2018, plus Oct 2025 to Sep 2026.
- **10 years** of QOF registers and list sizes.
- **6,100-8,300 GP practices** per month.
- **Over 99%** of QOF practices have prescribing data at the SGLT2 and DOAC launches (97.8% at ARNI).
- **94-97%** of practices still exist 24 months after launch, so few practices are lost to closures.
- Everything fits in **~0.9 GB on disk**.

## Launch dates (taken from the data)

| Launch | Launch month | How it was dated | Outcome month (+24) | QOF year used for features* |
|---|---|---|---|---|
| **DOAC** | **Sep 2011** | Flat ~200-270 items/month (post-surgery use) Aug 2010-Aug 2011, then sustained growth from Sep 2011, led by dabigatran (AF licence Aug 2011). Rivaroxaban follows mid-2012, apixaban 2013 | Sep 2013 | 2009-10 (corrected in Stage 2) |
| **SGLT2** | **Dec 2012** | First GP prescribing: 10 items at 9 practices (dapagliflozin). The BNF code was created in Oct 2012, but no GP prescribing until Dec | Dec 2014 | 2011-12 |
| **ARNI** | **Apr 2016** | First item Feb 2016; reached at least 10 practices in Apr 2016 | Apr 2018 | 2014-15 |

\*QOF is published about 6-7 months after its 31 March year end. To avoid leaking the future, features use the **latest QOF year that had been published by the launch month**, not the one covering it.

**Stage 2 correction:** QOF 2010-11 was published on 26 Oct 2011, a month *after* the DOAC launch, so DOAC features now use QOF 2009-10 (published 20 Oct 2010, downloaded in Stage 2). Publication dates checked: 2011-12 on 30 Oct 2012 (before the SGLT2 launch) and 2014-15 on 29 Oct 2015 (before the ARNI launch).

Charts: `reports/figures/national_uptake.png` (all classes) and `reports/figures/doac_takeoff.png`.

**Correction to the feasibility report:** that report put the SGLT2 launch at Nov 2012, based on monthly code lists that a script bug of mine had shifted by one month. The real prescribing data puts it at Dec 2012. The DOAC date is now settled at Sep 2011.

## Sources and files

| Dataset | Source | Coverage | Stored as | Size |
|---|---|---|---|---|
| Practice prescribing, pre-2014 | NHS Digital Practice Level Prescribing (41 monthly zips, streamed and filtered, raw deleted) | Aug 2010 to Dec 2013 | `data/processed/pre2014_rx.parquet` (38.7M rows, BNF presentation level), `pre2014_totals.parquet` (all-drug items per practice per month) | 258 MB |
| Practice prescribing, 2014 on | NHSBSA English Prescribing Dataset, via SQL API | Jan 2014 to Dec 2018 (60 months), Oct 2025 to Sep 2026 (12 months) | `data/processed/epd/rx_YYYYMM.csv.gz` (practice × chemical), `totals_YYYYMM.csv.gz` (all-drug items, region, ICB/STP, postcode) | 331 MB |
| QOF registers + list size | NHS Digital QOF, practice level | 2010-11 to 2018-19, 2025-26 | raw in `data/raw/qof/`, tidy table `data/processed/qof_registers.csv` | 196 MB |
| Practice reference / region | NHS ODS `epraccur` (current) + `epracarc` (archive) | current | `data/raw/ods/` | 3.5 MB |
| Practice addresses, pre-2014 | NHS Digital ADDR files | Aug 2010 to Dec 2013 | `data/raw/pre2014_addr/` | 107 MB |

**Drugs kept:** all of BNF 6.1 (diabetes), 2.8 (anticoagulants), 2.5 (antihypertensives incl. ACE inhibitors, ARBs, ARNI) and 2.9 (antiplatelets), plus 16 "innovation" drugs from other areas launched 2008-2014 (e.g. ticagrelor, mirabegron, COPD inhalers). The full list is in `src/bnf_codes.py`.

## QOF registers (England totals)

| QOF year | Practices | List size | Diabetes (17+) | AF | Heart failure |
|---|---|---|---|---|---|
| 2010-11 | 8,245 | 55.2M | 2.46M | 0.79M | 0.39M |
| 2011-12 | 8,123 | 55.5M | 2.57M | 0.82M | 0.40M |
| 2012-13 | 8,020 | 56.0M | 2.70M | 0.85M | 0.40M |
| 2013-14 | 7,921 | 56.3M | 2.81M | 0.88M | 0.40M |
| 2014-15 | 7,779 | 56.8M | 2.91M | 0.93M | 0.41M |
| 2015-16 | 7,616 | 57.5M | 3.03M | 0.98M | 0.43M |
| 2016-17 | 7,330 | 57.9M | 3.12M | 1.07M | 0.46M |
| 2017-18 | 7,088 | 58.3M | 3.20M | 1.11M | 0.49M |
| 2018-19 | 6,854 | 59.3M | 3.32M | 1.17M | 0.55M |
| 2025-26 | 6,145 | 63.7M | 4.24M | 1.48M | 0.75M |

Prevalence is plausible: diabetes about 4.5-6.7%, AF about 1.4-2.3%, HF about 0.7-1.2% of registered patients. No register values are missing apart from one practice's HF figure in 2014-15. The falling practice count reflects mergers, not missing data, since total list size keeps rising.

## Join and coverage checks

| Launch | QOF practices | ...with prescribing in launch month | ...still prescribing 24 months later |
|---|---|---|---|
| DOAC (Sep 2011) | 8,245 | 8,230 (99.8%) | 7,980 (97.0%) |
| SGLT2 (Dec 2012) | 8,123 | 8,092 (99.6%) | 7,847 (97.0%) |
| ARNI (Apr 2016) | 7,779 | 7,610 (97.8%) | 7,156 (94.0%) |

- The prescribing data also contains about 1,500-2,000 non-GP prescribers (out-of-hours services, walk-in centres, community services). They account for **under 1.5% of items** and are excluded by keeping only codes that appear in QOF.
- That leaves roughly **7,150-7,980 practices per launch** with complete features and outcome, which is plenty for training.

## Gaps and how they'll be handled

1. **Closed practices have no current region.** About 8% of 2010-11 practices aren't in the current ODS file (closed or merged). Fix in Stage 2: assign the most common current region among other practices in the same old SHA, or the region given in the EPD data where available.
2. **Jan 2019 to Sep 2025 not downloaded.** It isn't needed for training (the last outcome month is Apr 2018) or for scoring (which uses the latest 12 months). It can be added later with `src/fetch_epd.py` if we want to backtest a later launch.
3. **Little history before the DOAC launch.** There are 13 months of data before Sep 2011, enough for "use of older alternatives" (warfarin) and practice size. The "past adoption speed" feature for DOAC can only draw on drugs launched 2010-11 (dronedarone, prasugrel, ticagrelor, indacaterol, ...). Later launches have more history.
4. **Denominators are imperfect** (DOACs are also used for clots, not only AF; Entresto treats only one type of heart failure). This is noted for the interview; it doesn't change the ranking approach.
5. **Pre-2014 rows are at presentation level** (strength/brand), while EPD rows are at chemical level. Stage 2 will aggregate both to chemical level so they match.

## How to rebuild

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash src/build_pre2014_manifest.sh > data/raw/pre2014_manifest.csv
python3 -I src/fetch_pre2014.py "$PWD"      # ~1.5 h, then consolidate to Parquet (see script docstring)
python3 -I src/fetch_epd.py "$PWD"          # ~30 min
.venv/bin/python -I src/load_qof.py "$PWD"  # needs QOF files from data/raw/qof_manifest.csv
.venv/bin/python -I src/summarise_stage1.py "$PWD"
```
