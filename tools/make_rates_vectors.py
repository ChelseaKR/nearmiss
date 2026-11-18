"""Emit the interval vectors that pin the Studio's JavaScript rate port to honest_rates.

The browser-local Studio (``web/studio.js``) computes a corridor's report rate and
its Byar/quasi-Poisson interval in JavaScript so that a tier-2 "elevated rate"
claim is *computed* rather than asserted from a checkbox (#155). That port must
agree with the Python functions the engine publishes with. This script evaluates
``honest_rates.rates`` on a fixed set of inputs and writes them to
``tests/fixtures/rates/interval_vectors.json``; ``tests/test_studio_rates_port.py``
fails if the committed file drifts from Python, and ``web/workflow_check.mjs`` fails
if the JavaScript port drifts from the committed file. Regenerate with::

    python tools/make_rates_vectors.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from honest_rates.rates import (
    Z95,
    pearson_dispersion,
    poisson_ci,
    quasi_poisson_ci,
    rate_with_ci,
    wilson_ci,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "rates" / "interval_vectors.json"

POISSON_COUNTS = [0, 1, 2, 3, 4, 5, 6, 10, 14, 20, 37, 100, 250]
QUASI_CASES = [(2, 100.0), (5, 1.0), (5, 0.4), (10, 2.5), (100, 4.0), (14, 1.7), (0, 3.0)]
RATE_CASES = [
    (6, 300.0, 1000.0, 1.0),
    (6, 300.0, 1000.0, 9.0),
    (14, 2350.0, 1000.0, 1.0),
    (3, 1200.0, 1000.0, 1.0),
    (0, 500.0, 1000.0, 1.0),
    (37, 12000.0, 1000.0, 1.3),
    (5, 400.0, 100.0, 1.0),
    (7, 950.0, 1000.0, 2.2),
]
WILSON_CASES = [(0, 0), (3, 10), (0, 10), (10, 10), (7, 50), (1, 3), (250, 1000)]
DISPERSION_CASES: list[tuple[list[int], list[float]]] = [
    ([5, 5, 5, 5, 5, 5], [1000.0] * 6),
    ([0, 0, 0, 0, 0, 40], [1000.0] * 6),
    ([], []),
    ([7], [100.0]),
    ([0, 0, 0], [10.0, 10.0, 10.0]),
    ([5, 5], [0.0, 0.0]),
    ([7, 2, 3, 1], [1200.0, 950.0, 400.0, 0.0]),
    ([9, 1, 4], [800.0, 600.0, 700.0]),
]


def vectors() -> dict[str, Any]:
    return {
        "z95": Z95,
        "poisson_ci": [
            {"count": c, "low": poisson_ci(c)[0], "high": poisson_ci(c)[1]} for c in POISSON_COUNTS
        ],
        "quasi_poisson_ci": [
            {
                "count": c,
                "dispersion": phi,
                "low": quasi_poisson_ci(c, phi)[0],
                "high": quasi_poisson_ci(c, phi)[1],
            }
            for c, phi in QUASI_CASES
        ],
        "rate_with_ci": [
            {
                "count": c,
                "exposure": e,
                "per": per,
                "dispersion": phi,
                "rate": rate_with_ci(c, e, per, Z95, phi)[0],
                "low": rate_with_ci(c, e, per, Z95, phi)[1],
                "high": rate_with_ci(c, e, per, Z95, phi)[2],
            }
            for c, e, per, phi in RATE_CASES
        ],
        "wilson_ci": [
            {"successes": s, "trials": t, "low": wilson_ci(s, t)[0], "high": wilson_ci(s, t)[1]}
            for s, t in WILSON_CASES
        ],
        "pearson_dispersion": [
            {"counts": counts, "exposures": exposures, "phi": pearson_dispersion(counts, exposures)}
            for counts, exposures in DISPERSION_CASES
        ],
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(vectors(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
