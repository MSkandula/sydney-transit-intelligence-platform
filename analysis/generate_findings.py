"""Draws the findings charts in docs/images/findings/ from the live Gold tables.

Run: python analysis/generate_findings.py   (needs the .env Databricks settings)
Every number on every chart comes from a query against workspace.gold, so re-running it
after more data accumulates refreshes the charts.
"""
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from databricks_upload import connect  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "images" / "findings"
HIGHLIGHT, MUTED, GOOD, BAD, INK = "#e8912d", "#9aa7bd", "#3a7bd5", "#c9453b", "#1c2536"

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 11, "axes.edgecolor": "#c8cfdb",
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
    "axes.titlesize": 14, "axes.titlelocation": "left", "figure.dpi": 160,
})

BASE = """FROM workspace.gold.fact_trip_stop_performance f
JOIN workspace.gold.dim_route r ON f.route_key = r.route_key
WHERE f.is_orphan_trip = false AND f.is_delay_outlier = false AND f.is_cancelled = false
  AND r.mode = 'train' AND r.route_short_name IS NOT NULL"""


def fetch(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)
    print("wrote", name)


def chart_health_by_day(cur):
    rows = fetch(cur, """
        SELECT service_date, sum(CASE WHEN is_orphan_trip THEN 0 ELSE 1 END) AS matched,
               sum(CASE WHEN is_orphan_trip THEN 1 ELSE 0 END) AS orphan
        FROM workspace.gold.fact_trip_stop_performance GROUP BY 1 ORDER BY 1""")
    days = [datetime.strptime(r[0], "%Y%m%d") for r in rows]
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.bar(days, [r[1] for r in rows], width=0.8, color=GOOD,
           label="Matched to the timetable (usable for analysis)")
    ax.bar(days, [r[2] for r in rows], width=0.8, bottom=[r[1] for r in rows], color=MUTED,
           label="Unmatched ('orphan'): the timetable on file was out of date")
    ax.set_ylim(0, max(r[1] + r[2] for r in rows) * 1.3)
    ax.set_title("Records collected per day, and how many matched the timetable")
    ax.set_ylabel("Trip-stop records")
    ax.set_xlabel("Service date. Empty stretches = no data collected (laptop asleep or off).")
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    ax.legend(frameon=False, loc="upper right", fontsize=10)
    save(fig, "data_coverage_by_day.png")


def chart_pareto(cur):
    rows = fetch(cur, """
        SELECT route_short_name, total_delay_minutes, cumulative_pct_of_network_delay
        FROM workspace.gold.mart_line_delay_concentration ORDER BY total_delay_minutes DESC""")
    names = [r[0] for r in rows]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    colors = [HIGHLIGHT if i < 4 else MUTED for i in range(len(rows))]
    ax.bar(names, [r[1] for r in rows], color=colors)
    ax.set_ylabel("Total delay-minutes")
    ax2 = ax.twinx()
    ax2.plot(names, [r[2] for r in rows], color=INK, marker="o", ms=4)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Cumulative % of all delay")
    ax2.spines["right"].set_visible(True)
    top4 = rows[3][2]
    ax.set_title(f"4 of {len(rows)} lines account for {top4:.0f}% of all delay-minutes")
    save(fig, "delay_concentration.png")


def chart_ontime_by_line(cur):
    rows = fetch(cur, f"""
        SELECT r.route_short_name, 100*avg(CASE WHEN f.is_late=false THEN 1 ELSE 0 END), count(*)
        {BASE} GROUP BY 1 HAVING count(*) >= 1000 ORDER BY 2""")
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.barh([r[0] for r in rows], [r[1] for r in rows],
            color=[BAD if r[1] < 93 else MUTED for r in rows])
    ax.axvline(95, color=INK, ls="--", lw=1)
    ax.text(95.2, -0.6, "95%", fontsize=9, color=INK)
    ax.set_xlim(85, 100.5)
    ax.set_xlabel("% of stops reached within 5 minutes of schedule (TfNSW on-time standard)")
    ax.set_title("Punctuality by line (lines with 1,000+ checked stops)")
    save(fig, "ontime_by_line.png")


def chart_by_hour(cur):
    rows = fetch(cur, f"""
        SELECT hour(from_utc_timestamp(f.feed_timestamp,'Australia/Sydney')) AS hr,
               100*avg(CASE WHEN f.is_late=false THEN 1 ELSE 0 END), count(*)
        {BASE} GROUP BY 1 HAVING count(*) >= 1000 ORDER BY 1""")
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.bar([f"{r[0]:02d}:00" for r in rows], [r[1] for r in rows],
           color=[BAD if r[1] < 92 else GOOD for r in rows])
    ax.set_ylim(80, 100)
    ax.set_ylabel("% on time")
    ax.set_xlabel("Hour of day, Sydney time. Hours with under 1,000 checked stops are not shown "
                  "(e.g. 19:00: laptop asleep).")
    ax.set_title("Punctuality by hour of day: the evening peak is the weak spot")
    save(fig, "ontime_by_hour.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        cur = conn.cursor()
        chart_health_by_day(cur)
        chart_pareto(cur)
        chart_ontime_by_line(cur)
        chart_by_hour(cur)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
