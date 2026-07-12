"""The 311-potholes demo is the EXP-08 "excellence bar": a non-traffic worked
example that reaches the correct "busy is not the same as dangerous"
conclusion using only the public honest_rates API. Running it as a test keeps
it from silently rotting out of sync with the library.
"""

from __future__ import annotations

from honest_rates.examples.potholes_demo import main


def test_potholes_demo_runs_and_reaches_the_correct_conclusion() -> None:
    main()  # asserts internally that the busy arterial is NOT the honest top rate
