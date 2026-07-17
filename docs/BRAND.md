# NearMiss brand system

NearMiss is a road-evidence instrument, not a chat product and not an official government portal.
Its identity comes from conflict diagrams, highway wayfinding, survey marks, and transportation
atlases. The national layer's product name is **NearMiss Conflict Atlas**.

The canonical production site is [nearmiss.chelseakr.com](https://nearmiss.chelseakr.com).

## Identity thesis

The signature clearance mark shows two trajectories that approach but stop short. It is the only
animated brand gesture, and it runs once for 420 ms; reduced-motion users receive the static mark.
Never enclose it in a speech bubble, add an AI sparkle, or use it as a severity symbol.

The national experience has one job: choose a year, road-user mode, and state; understand the
published fatal-crash count with its limits; leave with a citable evidence brief. The active
visualization appears before promotional or release-detail content.

## Color

| Token | Value | Role |
| --- | --- | --- |
| Atlas stock | `#F3F6F2` | cool map-paper ground |
| Asphalt | `#152A30` | primary text and structural bars |
| Interstate blue | `#145B73` | published evidence, links, and controls |
| Brake red | `#B93A2B` | active selection and consequential warnings |
| Centerline | `#E0B33E` | trajectory/seam marks, never light-background body text |
| Guardrail | `#5E706F` | secondary text and rules |

Color is always redundant with text, hatching, position, or line treatment. Suppressed cells keep
their hatch and label; the palette never turns burden counts into a risk scale.

## Type

The site self-hosts three OFL-licensed families under `web/vendor/fonts/`:

- **Overpass Variable** for wayfinding/display text; its highway-sign lineage grounds the identity.
- **Atkinson Hyperlegible Next Variable** for interface and long-form reading.
- **Fragment Mono** for counts, provenance, hashes, and compact utility labels.

Font files are release-manifest-bound and use `font-display: swap`; no third-party font request is
made at runtime.

## Interface language

Use direct evidence language: “Select a state,” “Save evidence,” and “Source: NHTSA FARS.” Do not
say that NearMiss is official, do not call national burden counts risk or danger, and do not imply
fault or causation. “Verified artifact” describes the publication chain without implying government
authorship. Caveats stay next to the number they constrain.

## Shape and motion

Controls, tables, evidence slips, and map frames use square corners and visible rules. Avoid pill
tabs, floating pastel cards, ornamental shadows, graph-paper backgrounds, and decorative metric
grids. Motion belongs only to the clearance mark and linked selection, and must honor
`prefers-reduced-motion`.

## Accessibility and reuse

The clearance mark is decorative when adjacent to the wordmark and carries a text alternative when
used alone as the favicon. Keyboard focus remains high-contrast; native selectors and semantic
tables are the non-visual equivalent of every chart. Use the same lockup on the national atlas,
local map, report form, and embed so the product reads as one system.
