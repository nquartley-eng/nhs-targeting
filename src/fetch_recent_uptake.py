"""Stage 4 helper, step 2: practice-level uptake of drugs launched 2019-2025.

Reads the quarterly national counts from find_recent_launches.py and picks
recent launches with the same rule as training:
  - BNF chapters 1-13 (medicines, not appliances or vaccines), excluding
    BNF 9.13-9.14 (foods and nutrition products, which were all given new codes
    in Nov 2022 and would otherwise look like 120 "launches")
  - first reaches >= 10 practices after Jan 2019
  - >= 100 practices a year after that
  - first six months fall before Oct 2026
The quarterly scan only brackets the launch, so we pull every month from just
after the last quarter below 10 practices to 5 months after the first quarter
at 10+, find the exact first month with >= 10 practices, and keep that month
plus the next 5.

Output: data/processed/recent_uptake.csv  chem, launch_month, ym, practice, items
Usage:  python3 -I src/fetch_recent_uptake.py <project_root>
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
from fetch_epd import run_sql, table_for  # noqa: E402

P = ROOT / "data/processed"


def add_months(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:]) + k
    y += (m - 1) // 12
    return f"{y}{(m - 1) % 12 + 1:02d}"


def candidates() -> dict[str, tuple[str, str]]:
    n = defaultdict(dict)
    for r in csv.DictReader(open(P / "recent_national_counts.csv")):
        n[r["chem"]][r["ym"]] = int(r["n_prac"])
    qs = sorted({ym for d in n.values() for ym in d})
    out = {}
    for chem, d in n.items():
        if not chem[:2].isdigit() or not (1 <= int(chem[:2]) <= 13) or chem[:4] in ("0913", "0914"):
            continue
        hit = [ym for ym in qs if d.get(ym, 0) >= 10]
        if not hit or hit[0] == qs[0]:
            continue
        first = hit[0]
        later = add_months(first, 12)
        if later > qs[-1] or d.get(later, 0) < 100:
            continue
        prev = qs[qs.index(first) - 1]
        out[chem] = (add_months(prev, 1), add_months(first, 5))
    return out


def main() -> None:
    cand = candidates()
    print(f"{len(cand)} candidate launches:", ", ".join(f"{c}:{a}-{b}" for c, (a, b) in sorted(cand.items())))
    by_month = defaultdict(list)
    for chem, (a, b) in cand.items():
        m = a
        while m <= b:
            by_month[m].append(chem)
            m = add_months(m, 1)
    rows = []
    for ym in sorted(by_month):
        table, chemcol, _ = table_for(ym)
        codes = ",".join(f"'{c}'" for c in by_month[ym])
        res = run_sql(table, f"SELECT {chemcol} AS chem, PRACTICE_CODE AS practice, SUM(ITEMS) AS items "
                             f"FROM `{table}` WHERE {chemcol} IN ({codes}) GROUP BY {chemcol}, PRACTICE_CODE")
        rows += [(r["chem"], ym, r["practice"], float(r["items"])) for r in res]
        print(ym, len(by_month[ym]), "drugs,", len(res), "rows", flush=True)

    # exact launch month = first month with >= 10 prescribing practices; keep 6 months
    prac = defaultdict(lambda: defaultdict(set))
    for chem, ym, p, _ in rows:
        prac[chem][ym].add(p)
    launch = {}
    for chem, months in prac.items():
        hit = sorted(m for m, s in months.items() if len(s) >= 10)
        if hit and add_months(hit[0], 5) <= "202609":
            launch[chem] = hit[0]
    with open(P / "recent_uptake.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chem", "launch_month", "ym", "practice", "items"])
        for chem, ym, p, it in rows:
            if chem in launch and launch[chem] <= ym <= add_months(launch[chem], 5):
                w.writerow([chem, launch[chem], ym, p, it])
    print(f"kept {len(launch)} launches:", ", ".join(f"{c}:{m}" for c, m in sorted(launch.items())))


if __name__ == "__main__":
    main()
