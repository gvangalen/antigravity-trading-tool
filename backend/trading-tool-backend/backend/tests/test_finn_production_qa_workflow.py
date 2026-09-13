from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "finn-production-qa.yml"


def test_production_qa_is_manual_only_and_yaml_parseable():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    # PyYAML 1.1 converts the unquoted YAML key `on` to True.
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    assert "push" not in triggers
    assert "pull_request" not in triggers
    assert set(triggers["workflow_dispatch"]["inputs"]) >= {
        "release_sha",
        "qa_profile",
        "manifest_id",
        "run_label",
    }
