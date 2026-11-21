"""Therapy areas the scoring tool supports: one per QOF register.

For each condition:
  register   the register's name in the QOF prevalence file
  existing   BNF codes (paragraph or chemical prefixes) for the drugs a new
             entrant would compete with or be added to; "use of existing
             treatment per patient" is built from these
  validated  True where a backtest passed (the three training launches + COPD)
  mixed      True where a backtest gave a mixed result (depression)
  note       caveat shown in the tool, if any

The BNF prefixes are deliberately broad (a whole paragraph where possible), so
the feature measures "how actively does this practice treat the condition with
drugs", not loyalty to one product.
"""

CONDITIONS = {
    # --- backtested (training launches) -----------------------------------
    "diabetes": {"label": "Type 2 diabetes", "register": "Diabetes Mellitus Register",
                 "existing": ["060102"], "existing_label": "non-insulin diabetes drugs", "validated": True},
    "af": {"label": "Atrial fibrillation", "register": "Atrial Fibrillation Register",
           "existing": ["0208020"], "existing_label": "oral anticoagulants", "validated": True},
    "hf": {"label": "Heart failure", "register": "Heart Failure Register",
           "existing": ["0205051", "0205052"], "existing_label": "ACE inhibitors, ARBs and Entresto", "validated": True},
    # --- good fit: GP-prescribed, clear existing treatment -----------------
    "hypertension": {"label": "Hypertension", "register": "Hypertension Register",
                     "existing": ["0205", "020201", "0204", "0206020"],
                     "existing_label": "blood-pressure drugs"},
    "chd": {"label": "Coronary heart disease", "register": "Coronary Heart Disease Register",
            "existing": ["0212", "0209", "0206010"], "existing_label": "statins, antiplatelets and nitrates"},
    "stroke": {"label": "Stroke and TIA", "register": "Stroke or Transient Ischaemic Attacks (TIA) Register",
               "existing": ["0209", "0212"], "existing_label": "antiplatelets and statins"},
    "pad": {"label": "Peripheral arterial disease", "register": "Peripheral Arterial Disease Register",
            "existing": ["0209", "0212", "0206040"], "existing_label": "antiplatelets, statins and vasodilators"},
    "ckd": {"label": "Chronic kidney disease", "register": "Chronic Kidney Disease Register",
            "existing": ["0205051", "0205052", "0601023AG", "0601023AN"],
            "existing_label": "ACE inhibitors, ARBs and SGLT2 inhibitors"},
    "asthma": {"label": "Asthma", "register": "Asthma Register",
               "existing": ["0301", "0302", "0303"], "existing_label": "inhalers and other asthma drugs"},
    "copd": {"label": "COPD", "register": "Chronic Obstructive Pulmonary Disease Register",
             "existing": ["0301", "0302", "0303"], "existing_label": "inhalers", "validated": True,
             "note": "Backtested on triple inhalers (Trimbow/Trelegy, launched Sep 2017) with the model frozen: "
                     "32% of the top-ranked 20% became top prescribers (20% at random)."},
    "depression": {"label": "Depression", "register": "Depression Register",
                   "existing": ["0403"], "existing_label": "antidepressants", "mixed": True,
                   "note": "Backtested on vortioxetine (Dec 2015), a niche third-line drug: the Propensity ranking was "
                           "no better than random (21.5% vs 20%), but Opportunity worked (27% became top prescribers, "
                           "41% of all items). Use Opportunity here, especially for a later-line drug."},
    "epilepsy": {"label": "Epilepsy", "register": "Epilepsy Register",
                 "existing": ["0408"], "existing_label": "antiepileptics"},
    "osteoporosis": {"label": "Osteoporosis", "register": "Osteoporosis Register",
                     "existing": ["0606020"], "existing_label": "bisphosphonates"},
    "obesity": {"label": "Obesity", "register": "Obesity Register",
                "existing": ["040501", "0601023AW", "0601023AZ"],
                "existing_label": "weight-loss drugs (orlistat, semaglutide, tirzepatide)",
                "note": "Semaglutide and tirzepatide share one code for diabetes and weight-loss use, so "
                        "existing-treatment use includes some diabetes prescribing."},
    # --- usable with a caveat ----------------------------------------------
    "dementia": {"label": "Dementia", "register": "Dementia Register",
                 "existing": ["0411"], "existing_label": "dementia drugs",
                 "note": "Dementia drugs are usually started by memory clinics, so GP practice behaviour matters less."},
    "ra": {"label": "Rheumatoid arthritis", "register": "Rheumatoid Arthritis Register",
           "existing": ["1001030"], "existing_label": "DMARDs (methotrexate, hydroxychloroquine ...)",
           "note": "Most new RA drugs are biologics prescribed by hospitals; this suits oral drugs GPs can prescribe."},
    "smi": {"label": "Severe mental illness", "register": "Mental Health Register",
            "existing": ["0402"], "existing_label": "antipsychotics and lithium",
            "note": "Usually started by psychiatrists and continued by GPs, so local mental health services matter a lot."},
    "ndh": {"label": "Non-diabetic hyperglycaemia", "register": "Non-diabetic hyperglycaemia register",
            "existing": ["0601022"], "existing_label": "metformin",
            "note": "Few drugs are used for pre-diabetes today, so the existing-treatment signal is weak."},
}
for v in CONDITIONS.values():
    v.setdefault("validated", False)
    v.setdefault("mixed", False)  # backtested, but only one of the two rankings worked
    v.setdefault("note", "")

# BNF prefixes we need for today's scoring that the Stage 1 download didn't keep
ALREADY_KEPT = ("0601", "0208", "0205", "0209")
EXTRA_PREFIXES = sorted({p for v in CONDITIONS.values() for p in v["existing"] if not p.startswith(ALREADY_KEPT)})
