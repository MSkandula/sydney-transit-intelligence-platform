"""Export Gold-layer tables to CSV under tableau/extracts/ for Tableau Public.

Tableau Public has no live connector to Databricks (confirmed, see PROJECT_PLAN.md
§12) — this is the manual extract-export step that design deliberately relies on.
Re-run this whenever Gold has fresh data and re-publish the workbook in Tableau
Public; there's no way around that being a manual step on the free tier.
"""

import csv
import logging
import sys
from pathlib import Path

from databricks_upload import connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CATALOG = "workspace"
EXPORT_DIR = Path(__file__).resolve().parent.parent / "tableau" / "extracts"

TABLES_TO_EXPORT = [
    "gold.mart_route_daily_performance",
    "gold.mart_line_delay_concentration",
    "gold.fact_trip_stop_performance",
    "gold.dim_route",
    "gold.dim_stop",
    "gold.dim_date",
]


def export_table(cur, table_name: str) -> Path:
    cur.execute(f"SELECT * FROM {CATALOG}.{table_name}")
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()

    out_path = EXPORT_DIR / f"{table_name.split('.')[-1]}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

    log.info("Exported %s: %d rows -> %s", table_name, len(rows), out_path)
    return out_path


def main() -> int:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        cur = conn.cursor()
        for table_name in TABLES_TO_EXPORT:
            export_table(cur, table_name)
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
