# Web — the accessible map UI

A **framework-free** map interface targeting **WCAG 2.2 Level AA**, built to be auditable and to load
fast on a phone from the roadside. It reads only published artifacts; it never touches a precise raw
report.

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
