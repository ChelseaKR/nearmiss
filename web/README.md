# Web — the accessible map UI

A **dependency-light** map interface targeting **WCAG 2.2 Level AA**, built to be auditable and to load
fast on a phone from the roadside. It reads only published artifacts; it never touches a precise raw
report.

## The two maps (this is the point)

The page shows the **same reports mapped two ways** on a real [OpenStreetMap](https://www.openstreetmap.org/copyright)
basemap:

1. **Raw report count** — what most safety maps show. The busiest street looks the most dangerous.
2. **Exposure-normalized rate** — reports per 1000 units of exposure, with Getis-Ord Gi\* significance.
   The busiest street recedes; the statistically real hotspot emerges.

That contrast — a high-volume street that is *not* a significant hotspot, next to a lower-volume street
that *is* — is the original argument of this project, made visible. The map library is
[Leaflet](https://leafletjs.com) 1.9.4, **vendored locally** in `vendor/leaflet/` (no third-party CDN,
no runtime fetch of code), so the only third-party network call is the OSM tile request, attributed in
the footer.

Core commitments (see [`docs/ACCESSIBILITY.md`](../docs/ACCESSIBILITY.md) and the
[ACR](../docs/accessibility/ACR.md)):

- **A non-visual equivalent.** Every finding on the map is also reachable in an accessible, sortable
  **list and table** carrying the same ranked locations, rates, intervals, and significance flags.
- **Never color alone.** Risk level and statistical significance are conveyed in text and pattern, not
  only hue.
- **Keyboard-operable and labeled.** The report form and all controls are fully keyboard-operable with
  clear labels and error text.
- **Honest legends.** A raw-count layer is labeled "report volume," never "danger."

Accessibility is a **merge-blocking CI gate** (axe + manual NVDA/VoiceOver review).
