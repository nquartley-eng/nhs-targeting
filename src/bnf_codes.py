"""BNF code definitions for each launch and its older alternatives.

All codes are 9-character BNF *chemical substance* codes, checked against the
NHSBSA BNF code reference table (BNF_CODE_CURRENT_202610_VERSION_90).
Matching on the chemical code (the first 9 characters of a 15-character BNF
presentation code) captures every strength, brand and generic of that drug.
"""

# ---------------------------------------------------------------------------
# The three training launches ("new drug" groups)
# ---------------------------------------------------------------------------
LAUNCHES = {
    "sglt2": {
        "label": "SGLT2 inhibitors (type 2 diabetes)",
        "qof_register": "diabetes",
        "new_drugs": {
            "0601023AG": "Dapagliflozin",
            "0601023AL": "Dapagliflozin/metformin",
            "0601023AV": "Saxagliptin/dapagliflozin",
            "0601023AM": "Canagliflozin",
            "0601023AP": "Canagliflozin/metformin",
            "0601023AN": "Empagliflozin",
            "0601023AR": "Empagliflozin/metformin",
            "0601023AY": "Empagliflozin/linagliptin",
            "0601023AX": "Ertugliflozin",
        },
        # Older diabetes drugs a practice would already be using at launch
        "older_alternatives": {
            "0601022B0": "Metformin",
            "0601021M0": "Gliclazide",
            "0601021A0": "Glimepiride",
            "0601021H0": "Glibenclamide",
            "0601021P0": "Glipizide",
            "0601023B0": "Pioglitazone",
            "0601023X0": "Sitagliptin (DPP-4)",
            "0601023AA": "Vildagliptin (DPP-4)",
            "0601023AC": "Saxagliptin (DPP-4)",
            "0601023AE": "Linagliptin (DPP-4)",
            "0601023AD": "Sitagliptin/metformin",
            "0601023Z0": "Vildagliptin/metformin",
        },
    },
    "doac": {
        "label": "DOACs (atrial fibrillation)",
        "qof_register": "atrial_fibrillation",
        "new_drugs": {
            "0208020X0": "Dabigatran etexilate",
            "0208020Y0": "Rivaroxaban",
            "0208020Z0": "Apixaban",
            "0208020AA": "Edoxaban",
        },
        "older_alternatives": {
            "0208020V0": "Warfarin sodium",
            "0208020H0": "Acenocoumarol",
            "0208020N0": "Phenindione",
        },
    },
    "arni": {
        "label": "Sacubitril/valsartan - Entresto (heart failure)",
        "qof_register": "heart_failure",
        "new_drugs": {
            "0205052AE": "Sacubitril/valsartan",
        },
        # ACE inhibitors (BNF 0205051) and ARBs (BNF 0205052) - matched by
        # prefix, excluding sacubitril/valsartan itself.
        "older_alternative_prefixes": ["0205051", "0205052"],
        "older_alternative_exclude": ["0205052AE"],
    },
}

# "Innovation" drugs: new primary-care drugs launched ~2010-2015 *outside* the
# three therapy areas. How quickly a practice picked these up is a measure of
# general appetite for new medicines (used for the "past adoption speed" feature).
INNOVATION_DRUGS = {
    "0209000Z0": "Ticagrelor",              # antiplatelet, 2011
    "0209000Y0": "Prasugrel",               # antiplatelet, 2009
    "0203020X0": "Dronedarone",             # AF rhythm control, 2010
    "0206030Y0": "Ivabradine",              # angina / HF
    "0206030Z0": "Ranolazine",              # angina, 2008
    "0704020AE": "Mirabegron",              # overactive bladder, 2013
    "0704020AD": "Fesoterodine",            # overactive bladder, 2008
    "0301011X0": "Indacaterol",             # COPD, 2010
    "0301020R0": "Aclidinium",              # COPD, 2012
    "0301020S0": "Glycopyrronium (inhaled)",# COPD, 2012
    "0301020T0": "Umeclidinium",            # COPD, 2014
    "0302000V0": "Fluticasone furoate/vilanterol",  # asthma/COPD, 2014
    "0303030B0": "Roflumilast",             # COPD, 2010
    "0407020AG": "Tapentadol",              # pain, 2011
    "0404000U0": "Lisdexamfetamine",        # ADHD, 2013
    "1001040V0": "Febuxostat",              # gout, 2010
}

# Pre-2014 files from NHS Digital are matched on these BNF paragraph prefixes
# so we keep every drug we might need (new, older and "innovation" drugs)
# without storing the full 1.4 GB monthly files.
PARAGRAPH_PREFIXES_TO_KEEP = [
    "0601",  # diabetes drugs (whole of BNF 6.1)
    "0208",  # anticoagulants
    "0205",  # ACE inhibitors, ARBs, ARNI
    "0209",  # antiplatelets (small; gives aspirin/clopidogrel context for AF)
]


def keep_code(bnf_code: str) -> bool:
    """True if a 15-char BNF presentation code belongs to anything we track."""
    return bnf_code.startswith(tuple(PARAGRAPH_PREFIXES_TO_KEEP)) or bnf_code[:9] in INNOVATION_DRUGS
