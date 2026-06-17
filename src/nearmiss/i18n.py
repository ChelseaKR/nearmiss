"""Localization bundles for the advocacy brief (English and Spanish).

This is the foundation for bilingual outputs (and a bilingual report form): the
brief's fixed strings live here per language, and the brief renders in the
requested language. Deep localization of the data-driven prose (e.g. the bias
note) is still in progress; unknown languages fall back to English.
"""

from __future__ import annotations

# Each bundle is a flat map of message keys. Placeholders use str.format syntax.
_EN: dict[str, str] = {
    "title": "Where the danger actually is — {city}",
    "intro": (
        "> Rates are reports per {per} {unit}. Every rate carries a 95% confidence "
        "interval and an n. Raw counts are not danger; they are report volume. Read the "
        "caveats — they are the point."
    ),
    "coverage": (
        "**Exposure coverage:** {pct}% of segments have an exposure denominator. "
        "Segments without one are listed as *exposure unknown*, not ranked."
    ),
    "withheld": (
        "*{n} segment(s) with fewer than {floor} reports are withheld from this brief and the "
        "open dataset to protect contributor privacy (k-anonymity).*"
    ),
    "glossary_heading": "## What the numbers mean (plain language)",
    "glossary_rate": (
        "- **Rate** — reports per {per} {unit}. It adjusts for how many people travel a "
        "street, so a quiet street with a few reports can rank above a busy one with many."
    ),
    "glossary_ci": (
        "- **95% CI (confidence interval)** — the plausible range for the true rate. A wide "
        "range means few reports and real uncertainty; treat those rankings gently."
    ),
    "glossary_gi": (
        "- **Hotspot (Getis-Ord Gi\\*)** — a segment marked ★ Significant is hot *beyond* what "
        "traffic and chance explain, after a multiple-comparison correction: a real cluster, "
        "not a fluke. Several streets can share a rate while only one is a significant cluster."
    ),
    "highest_heading": "## Highest-rate segments (exposure-normalized)",
    "th_rank": "Rank",
    "th_segment": "Segment",
    "th_rate": "Rate /{per}",
    "th_ci": "95% CI",
    "th_n": "n",
    "th_confidence": "Confidence",
    "th_hotspot": "Hotspot",
    "bottom_line": (
        "**Bottom line:** the highest exposure-normalized near-miss rate is on **{name}** — "
        "about {rate} reports per {per} {unit} (95% CI {lo}–{hi}, n={n}){sig}. Because it is "
        "normalized by exposure, this is a rate, not just a busy street; still, it rests on {n} "
        "reports, so read it with the interval and the reporting-bias caveats below."
    ),
    "sig_yes": ", and it is a statistically significant cluster",
    "sig_no": "",
    "significant_heading": "## Statistically significant hotspots (Getis-Ord Gi\\*)",
    "significant_intro": (
        "These segments are hot *beyond* what exposure and spatial structure explain — "
        "candidates for hot because dangerous, not hot because busy:"
    ),
    "significant_none": "No segment reaches statistical significance at this sample size.",
    "bias_heading": "## Reporting bias (named, not hidden)",
    "bias_counterweight": (
        "This does not mean nothing can be concluded — an exposure-normalized rate with a "
        "stated interval and a flagged bias is a far better basis for action than a raw heat "
        "map. It means: act on the strongest, most-significant signals, and treat the rest as "
        "leads to investigate, not verdicts."
    ),
    "over_heading": "**Over-represented vs exposure** (more reports than traffic alone predicts):",
    "under_heading": "**Under-represented vs exposure** (quiet in the data, not necessarily safe):",
    "peak": (
        "**Report-intensity peak (KDE, not danger):** around {name}. This shows where reports "
        "concentrate, which is not the same as where risk is highest."
    ),
    "footer": (
        "Every figure above regenerates from raw inputs with `make reproduce`. Data and methods "
        "are open (Apache-2.0); see `docs/METHODOLOGY.md` and `docs/DATA-CARD.md`."
    ),
    "share_line": "- {name}: {rshare}% of reports vs {eshare}% of exposure",
}

_ES: dict[str, str] = {
    "title": "Dónde está realmente el peligro — {city}",
    "intro": (
        "> Las tasas son reportes por {per} {unit}. Cada tasa lleva un intervalo de confianza "
        "del 95% y una n. Los conteos crudos no son peligro; son volumen de reportes. Lea las "
        "advertencias — son lo esencial."
    ),
    "coverage": (
        "**Cobertura de exposición:** el {pct}% de los segmentos tiene un denominador de "
        "exposición. Los que no lo tienen aparecen como *exposición desconocida*, sin ranking."
    ),
    "withheld": (
        "*{n} segmento(s) con menos de {floor} reportes se omiten de este informe y del conjunto "
        "de datos abierto para proteger la privacidad de quienes reportan (anonimato-k).*"
    ),
    "glossary_heading": "## Qué significan los números (en lenguaje claro)",
    "glossary_rate": (
        "- **Tasa** — reportes por {per} {unit}. Ajusta por cuánta gente transita una calle, "
        "así que una calle tranquila con pocos reportes puede superar a una concurrida con muchos."
    ),
    "glossary_ci": (
        "- **IC 95% (intervalo de confianza)** — el rango plausible de la tasa real. Un rango "
        "amplio significa pocos reportes e incertidumbre real; tome esos rankings con cautela."
    ),
    "glossary_gi": (
        "- **Punto caliente (Getis-Ord Gi\\*)** — un segmento marcado ★ Significativo es "
        "peligroso *más allá* de lo que explican el tránsito y el azar, tras una corrección por "
        "comparaciones múltiples: un grupo real, no una casualidad."
    ),
    "highest_heading": "## Segmentos de mayor tasa (normalizada por exposición)",
    "th_rank": "Rango",
    "th_segment": "Segmento",
    "th_rate": "Tasa /{per}",
    "th_ci": "IC 95%",
    "th_n": "n",
    "th_confidence": "Confianza",
    "th_hotspot": "Punto caliente",
    "bottom_line": (
        "**En resumen:** la mayor tasa de cuasi-accidentes normalizada por exposición está en "
        "**{name}** — alrededor de {rate} reportes por {per} {unit} (IC 95% {lo}–{hi}, "
        "n={n}){sig}. Por estar normalizada por exposición, es una tasa, no solo una calle "
        "concurrida; aun así, se basa en {n} reportes, así que léala con el intervalo y las "
        "advertencias de sesgo de abajo."
    ),
    "sig_yes": ", y es un grupo estadísticamente significativo",
    "sig_no": "",
    "significant_heading": "## Puntos calientes estadísticamente significativos (Getis-Ord Gi\\*)",
    "significant_intro": (
        "Estos segmentos son peligrosos *más allá* de lo que explican la exposición y la "
        "estructura espacial — candidatos a peligrosos, no solo concurridos:"
    ),
    "significant_none": (
        "Ningún segmento alcanza significancia estadística con este tamaño de muestra."
    ),
    "bias_heading": "## Sesgo de reporte (nombrado, no oculto)",
    "bias_counterweight": (
        "Esto no significa que no se pueda concluir nada — una tasa normalizada por exposición, "
        "con un intervalo y un sesgo señalados, es una base mucho mejor que un mapa de calor "
        "crudo. Significa: actúe sobre las señales más fuertes y significativas, y trate el "
        "resto como pistas a investigar, no como veredictos."
    ),
    "over_heading": (
        "**Sobre-representados vs exposición** (más reportes de lo que predice el tránsito):"
    ),
    "under_heading": (
        "**Sub-representados vs exposición** (silenciosos en los datos, no por ello seguros):"
    ),
    "peak": (
        "**Pico de intensidad de reportes (KDE, no peligro):** cerca de {name}. Muestra dónde se "
        "concentran los reportes, que no es lo mismo que dónde el riesgo es mayor."
    ),
    "footer": (
        "Cada cifra de arriba se regenera desde los datos crudos con `make reproduce`. Los datos "
        "y métodos son abiertos (Apache-2.0); vea `docs/METHODOLOGY.md` y `docs/DATA-CARD.md`."
    ),
    "share_line": "- {name}: {rshare}% de los reportes vs {eshare}% de la exposición",
}

_BUNDLES: dict[str, dict[str, str]] = {"en": _EN, "es": _ES}

SUPPORTED_LANGUAGES = tuple(_BUNDLES)


def strings(lang: str) -> dict[str, str]:
    """Return the message bundle for ``lang`` (falls back to English)."""
    return _BUNDLES.get(lang, _EN)
