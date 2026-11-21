# Stage 1: Data feasibility

*Checked 20 Nov 2026. **Superseded in part by `stage1_data_summary.md`**: the launch dates there (DOAC Sep 2011, SGLT2 Dec 2012, ARNI Apr 2016) come from the full data and replace the provisional dates in section 3 below.*

## 1. What data exists

| Need | Source | Coverage found | Access | Notes |
|---|---|---|---|---|
| Practice prescribing, 2014 on | NHSBSA English Prescribing Dataset (EPD) | **Jan 2014 to Jun 2025** (138 months), plus EPD-with-SNOMED **Nov 2020 to Sep 2026** | SQL API, filtered server-side (~2 s per national query, ~8 s per practice-level query) | Full monthly files are ~6.6 GB each, but we never need them. Results over 32k rows come back as a gzipped CSV link. Includes NHS region, ICB/STP and practice postcode on every row. |
| Practice prescribing, pre-2014 | NHS Digital Practice Level Prescribing Data | **Aug 2010 to Dec 2013**, every month | Direct file download, one page per month | ~1.4 GB CSV (~250 MB zipped) per month. No API, so the whole file has to be downloaded and then filtered. |
| Prescribing, ready-made | OpenPrescribing API | (would be the same data as above) | **Blocked**: it currently returns a Cloudflare bot challenge to scripts | Not needed. It is built on the same NHSBSA/NHS Digital data. |
| QOF registers (diabetes, AF, HF) | NHS Digital QOF, practice level | Every year **2010-11 to 2025-26** | Direct download | Format changes over time: `.xls` (2010-12), zip of `.xlsx`/CSV (2012-15), `.xlsx` plus CSV zip (2015 on). Needs a loader per format era. |
| Practice list size | QOF prevalence files (list size column) | Same as QOF | Same | Annual snapshot. That is enough because features are a snapshot at launch. |
| NHS region | EPD rows (2014 on); pre-2014 ADDR file (SHA/PCT) | All years | Free | Regions were reorganised in 2013 and again in 2020. **Recommendation:** assign each practice its *current* region (ODS `epraccur` file) so the label is the same across all launches. |

## 2. BNF codes (verified against NHSBSA BNF table v90, Oct 2026)

Codes are 9-character chemical codes, listed in full in `src/bnf_codes.py`.

- **SGLT2:** dapagliflozin `0601023AG` (+ combos `AL`, `AV`), canagliflozin `0601023AM` (+ `AP`), empagliflozin `0601023AN` (+ `AR`, `AY`), ertugliflozin `0601023AX`
  - *Older alternatives:* metformin `0601022B0`, sulfonylureas `0601021*`, pioglitazone `0601023B0`, DPP-4 inhibitors (sitagliptin `0601023X0`, vildagliptin `AA`, saxagliptin `AC`, linagliptin `AE`)
- **DOACs:** dabigatran `0208020X0`, rivaroxaban `0208020Y0`, apixaban `0208020Z0`, edoxaban `0208020AA`
  - *Older alternatives:* warfarin `0208020V0` (also acenocoumarol `H0`, phenindione `N0`, both tiny)
- **ARNI:** sacubitril/valsartan `0205052AE`
  - *Older alternatives:* all ACE inhibitors `0205051*` and ARBs `0205052*` except `0205052AE`

## 3. Launch months, taken from the data

Two signals were used: (a) the first month each BNF code appears in the monthly NHS Digital chemical lists (shows when the code was *created*), and (b) the first month with real prescribing in EPD (≥10 practices). The national series is saved in `data/processed/national_monthly_new_drugs_2014_2017.csv`.

| Drug | First seen in data | ≥10 practices | Proposed launch month | Confidence |
|---|---|---|---|---|
| Dapagliflozin | Code created **Nov 2012** | Already 2,230 practices in Jan 2014 | **Nov 2012** | High (matches UK launch) |
| Canagliflozin | Feb 2014 | Apr 2014 | (later entrant in SGLT2 class) | High |
| Empagliflozin | Aug 2014 | Sep 2014 | (later entrant) | High |
| Ertugliflozin | not in 2014-17 | | (late entrant, ~2018) | High |
| Dabigatran, rivaroxaban, apixaban | Codes present by **Sep 2010** (first file) | Already 1,800-5,100 practices in Jan 2014 | **Needs pre-2014 volume data**, see issue A | Low until checked |
| Edoxaban | Jul 2015 | Oct 2015 | (later entrant in DOAC class) | High |
| Sacubitril/valsartan | **Feb 2016** | **Apr 2016** | **Apr 2016** (first real uptake; lines up with NICE approval) | High |

**Class-level launches:** I recommend treating each *group* as one launch dated by its first drug (SGLT2 = Nov 2012, DOAC = see A, ARNI = Apr 2016). The outcome at 24 months counts all drugs in the group, because a rep sells into a therapy area and later entrants compete for the same patients.

## 4. Issues to decide before downloading

**A. The DOAC launch is not a single date.** Dabigatran and rivaroxaban were first licensed (2008) for short-term clot prevention after hip and knee surgery, mostly prescribed in hospital. GP uptake really began with the AF approvals in 2011-13. Apixaban's code even exists in Sep 2010, before its licence, so code dates tell us nothing here. *Proposal:* download the 2010-13 monthly files (see plan), plot national GP volume, and set the launch at the month GP prescribing clearly takes off (I expect around early 2012). Outcome = 24 months later (around early 2014, inside EPD).

**B. Pre-2014 data is unavoidable for two of the three launches.** SGLT2 (Nov 2012) and DOAC (~2012) features must describe practices *before* launch, and that is only in the NHS Digital files. They exist with no gaps, but they are big (41 months × ~250 MB zipped ≈ **10 GB to download**; ~57 GB unzipped). You have **26 GB free**, so the files **cannot all be kept**. *Proposal:* process one month at a time (download, keep only BNF 6.1 / 2.8 / 2.5 rows, delete the raw file). The filtered output is a few hundred MB.

**C. "Past adoption speed of earlier new drugs" is short on history for the 2012 launches.** Data starts Aug 2010, so the only "earlier new drugs" with a visible launch are those that launched around 2010-11 (e.g. linagliptin 2011, ticagrelor 2011, prolonged-release exenatide 2011). That's workable, but the innovation score for the DOAC launch would rest on a thin window. *Alternative:* define adoption speed as "share of a practice's prescribing in the newest drugs of its class at launch" (e.g. DPP-4/GLP-1 share of diabetes drugs). That can be computed from any single month. I suggest building both and seeing which holds up.

**D. Denominator mismatch (worth mentioning in interview).** DOACs are also used for clots outside AF, and Entresto is only for one type of heart failure (reduced ejection fraction), while the QOF HF register includes all types. Per-register rates will be noisy, but that affects every practice in a similar way, and we rank practices, not estimate true rates.

**E. Practice churn.** Practices merge, close and change codes. Some practices active at launch won't exist 24 months later (no outcome). They'll be dropped from training, and how many is reported in the data summary.

**F. Map coordinates (Stage 4 only).** The map needs practice postcodes mapped to latitude/longitude, via the ONS postcode directory (~1 GB) or postcodes.io. This can wait until Stage 4.

## 5. Proposed download plan (for approval)

| # | What | Months | How | Approx size kept |
|---|---|---|---|---|
| 1 | NHS Digital practice prescribing, filtered to BNF 6.1, 2.8, 2.5 (+ a handful of 2010-11 "innovation" drugs) | Aug 2010 to Dec 2013 (41) | Stream month by month, filter, delete raw | ~300-500 MB |
| 2 | EPD practice × chemical for the same paragraphs | Jan 2014 to Dec 2018 (60), plus the latest 12 months for scoring | SQL API | ~300-500 MB |
| 3 | QOF practice-level DM / AF / HF registers + list size | 2010-11 to 2017-18, plus 2025-26 | Direct download | < 200 MB |
| 4 | ODS `epraccur` (current practice → region, postcode, status) | current | Direct download | ~2 MB |

Total network ≈ 11 GB, mostly item 1. It takes roughly 1-2 hours unattended on a typical connection. Peak extra disk use is under 2 GB at any time.

**Cheaper option if you want it:** skip most of item 1 and download only the 12 months before each pre-2014 launch, plus a few months to pin down the DOAC take-off. That's ~20 months (~5 GB), at the cost of a weaker adoption-speed feature.
