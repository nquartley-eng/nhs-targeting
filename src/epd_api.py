"""Thin helper for the NHSBSA Open Data Portal SQL API.

Why: each monthly English Prescribing Dataset (EPD) file is ~6.6 GB, but the
portal runs SQL server-side, so we can ask for only the rows we need
(e.g. one drug group, grouped by practice) and get back a few MB.

EPD coverage: EPD_201401 .. EPD_202506 (dataset "english-prescribing-data-epd")
and EPD_SNOMED_202011 .. EPD_SNOMED_202609 for recent months.
"""
import json
import time
import urllib.parse
import urllib.request

SQL_URL = "https://opendata.nhsbsa.net/api/3/action/datastore_search_sql"


def query(resource_id: str, sql: str, retries: int = 3) -> list[dict]:
    """Run one SQL query against one monthly EPD table, return list of rows."""
    params = urllib.parse.urlencode({"resource_id": resource_id, "sql": sql})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{SQL_URL}?{params}", timeout=180) as r:
                return json.load(r)["result"]["result"]["records"]
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def national_monthly(ym: str, chem_codes: list[str]) -> list[dict]:
    """National items and number of prescribing practices per chemical, one month."""
    codes = ",".join(f"'{c}'" for c in chem_codes)
    sql = (
        "SELECT BNF_CHEMICAL_SUBSTANCE, SUM(ITEMS) AS items, "
        "COUNT(DISTINCT PRACTICE_CODE) AS n_prac "
        f"FROM `EPD_{ym}` WHERE BNF_CHEMICAL_SUBSTANCE IN ({codes}) "
        "GROUP BY BNF_CHEMICAL_SUBSTANCE"
    )
    return query(f"EPD_{ym}", sql)
