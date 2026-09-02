from pathlib import Path
from backend.services.finn_v2_selector_eval_registry import load_and_validate

ROOT = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures"
paths = [ROOT / f"finn_v2_selector_{name}.json" for name in ("development", "regression", "holdout")]
print(f"validated_cases={len(load_and_validate(paths, allow_published_regression=True))}")
