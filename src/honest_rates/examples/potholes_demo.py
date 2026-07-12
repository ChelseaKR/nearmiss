"""Worked example: 311 pothole *reports* vs. street *traffic* exposure.

Deliberately **not** a near-miss / cycling dataset — nearmiss's own domain —
to demonstrate that `honest_rates` really is usable on an unrelated
point-event dataset, using only the public `honest_rates` API (no `nearmiss`
import anywhere in this module).

The scenario: a city receives 311 pothole reports for six streets. One is a
residential street with light traffic but a genuinely bad surface (many
reports relative to how few cars ever drive it); another is a busy arterial
that gets the most raw reports of any street in the dataset simply because
thousands of cars use it every day, most of which never hit a pothole worth
reporting. Ranking by raw report count would flag the busy arterial as the
worst street in the city. Ranking by an exposure-normalized rate does not
make that mistake.

Run:  python -m honest_rates.examples.potholes_demo
"""

from __future__ import annotations

from honest_rates import SimpleUnit, analyze

# Six streets. "exposure" here is estimated average daily vehicle trips (a
# stand-in for the kind of traffic-count or parcel-count denominator a real
# 311 pipeline would attach) -- NOT the pothole report count itself.
STREETS = {
    "elm-residential": SimpleUnit(id="elm-residential", lat=38.545, lon=-121.745),
    "oak-residential": SimpleUnit(id="oak-residential", lat=38.5455, lon=-121.7445),
    "maple-collector": SimpleUnit(id="maple-collector", lat=38.548, lon=-121.740),
    "main-arterial": SimpleUnit(id="main-arterial", lat=38.560, lon=-121.700),
    "pine-residential": SimpleUnit(id="pine-residential", lat=38.610, lon=-121.650),
    "cedar-collector": SimpleUnit(id="cedar-collector", lat=38.612, lon=-121.648),
}

REPORT_COUNTS = {
    "elm-residential": 9,  # a genuinely bad surface, few cars ever drive it
    "oak-residential": 7,  # next door to elm -- same bad stretch of pavement
    "maple-collector": 5,
    "main-arterial": 42,  # by far the MOST raw reports in the dataset
    "pine-residential": 1,
    "cedar-collector": 2,
}

DAILY_TRIPS = {
    "elm-residential": 150.0,  # light residential traffic
    "oak-residential": 140.0,
    "maple-collector": 900.0,
    "main-arterial": 18_000.0,  # a genuinely busy arterial
    "pine-residential": 130.0,
    "cedar-collector": 950.0,
}


def main() -> None:
    units = list(STREETS.values())
    results = analyze(units, REPORT_COUNTS, DAILY_TRIPS, band_m=600.0, per=1000.0)

    by_raw_count = sorted(results, key=lambda r: r.count, reverse=True)
    by_rate = sorted(results, key=lambda r: r.rate or 0.0, reverse=True)

    print("Ranked by RAW report count (the naive, misleading ranking):")
    for r in by_raw_count:
        print(f"  {r.unit_id:<18} reports={r.count:>3}")

    print("\nRanked by exposure-normalized RATE (reports per 1,000 daily trips):")
    for r in by_rate:
        flag = " <- significant Gi* cluster" if r.significant else ""
        ci = f"({r.rate_ci_low:.2f}, {r.rate_ci_high:.2f})"
        print(f"  {r.unit_id:<18} rate={r.rate:>7.2f}  ci={ci}{flag}")

    worst_by_count = by_raw_count[0].unit_id
    worst_by_rate = by_rate[0].unit_id
    print(f"\nWorst street by raw count:  {worst_by_count}")
    print(f"Worst street by honest rate: {worst_by_rate}")
    assert worst_by_count == "main-arterial", "the busy arterial should top the naive ranking"
    assert worst_by_rate != "main-arterial", "but it must NOT top the honest, rate-based ranking"
    print(
        "\n'main-arterial' has the most raw reports but is busy, not dangerous: "
        "it drops out of the top of the honest ranking. That is the point of this library."
    )


if __name__ == "__main__":
    main()
