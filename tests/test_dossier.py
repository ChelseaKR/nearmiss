"""Decision Dossiers are controlled-claim, reproducible corridor artifacts."""

from __future__ import annotations

import pytest

from nearmiss.config import Config
from nearmiss.dossier import render_dossier
from nearmiss.engine import AnalysisBundle
from nearmiss.errors import NearmissError


def test_dossier_is_corridor_specific_and_claim_limited(
    bundle: AnalysisBundle, config: Config
) -> None:
    corridor = bundle.result.corridors[0]
    text = render_dossier(
        bundle,
        config,
        corridor.corridor_id,
        "Fund a daytime field review before the next capital-program cycle.",
    )
    assert corridor.name in text
    assert "Decision request" in text
    assert "Fund a daytime field review" in text
    assert f"`{corridor.corridor_id}`" in text
    assert "does **not** establish danger, fault, causation" in text
    assert "Declared evidence tier" in text
    assert "seg-08" not in text


def test_dossier_rejects_unknown_corridor(bundle: AnalysisBundle, config: Config) -> None:
    with pytest.raises(NearmissError, match="unknown corridor"):
        render_dossier(bundle, config, "not-a-corridor", "Review the corridor.")


def test_dossier_renders_in_spanish(bundle: AnalysisBundle, config: Config) -> None:
    corridor = bundle.result.corridors[0]
    text = render_dossier(bundle, config, corridor.corridor_id, "Programe una revisión.", "es")
    assert "Expediente de decisión" in text
    assert "Límite de las afirmaciones" in text
    assert "no** establece peligro" in text
