"""Shared whole-point benchmark zones for setup conditions and DCA sizing."""

BENCHMARK_SCORE_BANDS = (
    ("heavy_pressure", 0, 25, ("Zwaar onder druk", "Heavy pressure", "Stark unter Druck")),
    ("pressure", 26, 45, ("Onder druk", "Under pressure", "Unter Druck")),
    ("no_direction", 46, 60, ("Geen duidelijke richting", "No clear direction", "Keine klare Richtung")),
    ("gaining_strength", 61, 75, ("De markt trekt aan", "Gaining strength", "Der Markt wird stärker")),
    ("strong", 76, 100, ("Sterke markt", "Strong market", "Starker Markt")),
)


def benchmark_zone_step_boundaries() -> tuple[float, ...]:
    """Step boundaries matching the displayed score rounded to a whole point."""
    return (0.0, *(maximum + 0.5 for _, _, maximum, _ in BENCHMARK_SCORE_BANDS[:-1]))
