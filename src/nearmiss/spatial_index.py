"""Uniform spatial grid index for acceleration of distance-based queries.

Shared by snap, dedupe, KDE, and Gi* neighbor search. The grid cells are indexed
by their (x, y) coordinates in the projected plane. A report or segment at
(x, y) falls in cell (x // cell_size, y // cell_size).

Results are identical to brute-force queries — the index is an accelerator,
never an approximation. Determinism is ensured by always sorting candidates by id.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpatialIndex:
    """Uniform grid spatial index in projected metres.

    The grid spans the bounding box of all indexed items with a configurable
    cell size. All queries return results identical to brute-force iteration,
    deterministically sorted by id.
    """

    cell_size_m: float
    # Grid cells are keyed by (cell_x, cell_y) tuples, valued as lists of
    # (id, x, y) tuples sorted by id for determinism.
    cells: dict[tuple[int, int], list[tuple[str, float, float]]] = field(default_factory=dict)
    bounds: tuple[float, float, float, float] | None = None  # (x_min, y_min, x_max, y_max)

    def _cell_key(self, x: float, y: float) -> tuple[int, int]:
        """Map (x, y) in metres to cell (cell_x, cell_y)."""
        return (int(x // self.cell_size_m), int(y // self.cell_size_m))

    def add(self, item_id: str, x: float, y: float) -> None:
        """Add an item at (x, y) to the index."""
        cell_key = self._cell_key(x, y)
        if cell_key not in self.cells:
            self.cells[cell_key] = []
        self.cells[cell_key].append((item_id, x, y))
        # Update bounds.
        if self.bounds is None:
            self.bounds = (x, y, x, y)
        else:
            x_min, y_min, x_max, y_max = self.bounds
            self.bounds = (min(x_min, x), min(y_min, y), max(x_max, x), max(y_max, y))

    def finalize(self) -> None:
        """Sort all cells by id for deterministic iteration. Call after all adds."""
        for cell_list in self.cells.values():
            cell_list.sort(key=lambda item: item[0])

    def neighbors_in_radius(
        self, x: float, y: float, radius_m: float
    ) -> list[tuple[str, float, float]]:
        """Return all items within radius_m of (x, y), sorted by id.

        This uses a grid+distance filter: first, collect all items in cells
        within the bounding square of the radius, then filter by actual distance.

        An id may have been ``add()``-ed at more than one (x, y) — e.g. every
        vertex of a street segment shares that segment's id (see
        ``pipeline/snap.py``). At most one entry per id is returned, but *any*
        one of its instances passing the distance filter is enough: an id is
        only excluded from further consideration once one of its instances has
        actually been included, never merely because some other, farther
        instance of the same id was the first one visited. (An id's instances
        can straddle the bounding square too — some inside radius_m, some
        outside — so visit order must not let an out-of-range instance shadow
        an in-range one.)
        """
        # Determine the bounding square in cell coordinates.
        cell_radius = int(radius_m / self.cell_size_m) + 1
        cx, cy = self._cell_key(x, y)
        result: list[tuple[str, float, float]] = []
        found: set[str] = set()  # ids already present in `result`
        for dcx in range(-cell_radius, cell_radius + 1):
            for dcy in range(-cell_radius, cell_radius + 1):
                cell_key = (cx + dcx, cy + dcy)
                if cell_key in self.cells:
                    for item_id, ix, iy in self.cells[cell_key]:
                        if item_id in found:
                            continue
                        dx, dy = ix - x, iy - y
                        dist_sq = dx * dx + dy * dy
                        if dist_sq <= radius_m * radius_m:
                            found.add(item_id)
                            result.append((item_id, ix, iy))
        # Sort by id for determinism.
        result.sort(key=lambda item: item[0])
        return result

    def cells_in_neighborhood(self, x: float, y: float) -> list[tuple[str, float, float]]:
        """Return all items in the 3×3 neighborhood of cells around (x, y)."""
        cx, cy = self._cell_key(x, y)
        result: list[tuple[str, float, float]] = []
        for dcx in (-1, 0, 1):
            for dcy in (-1, 0, 1):
                cell_key = (cx + dcx, cy + dcy)
                if cell_key in self.cells:
                    result.extend(self.cells[cell_key])
        # Sort by id for determinism.
        result.sort(key=lambda item: item[0])
        return result
