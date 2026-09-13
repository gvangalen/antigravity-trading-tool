from __future__ import annotations

from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_finn_v2_public_action_contract_acceptance_matrix.py"
)


def test_public_matrix_forwards_production_shaped_case_pacing():
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"--case-interval-seconds"' in source
    assert 'default=3.2' in source
    assert '"--case-interval-seconds", str(max(0.0, args.case_interval_seconds))' in source
