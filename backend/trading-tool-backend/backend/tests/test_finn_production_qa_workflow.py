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


def test_secret_using_manual_jobs_require_the_reviewed_main_ref():
    for name, job in (
        ("finn-production-qa.yml", "production-qa"),
        ("finn-qa-fixture-ops.yml", "diagnose"),
        ("configure-twelve-data-production.yml", "configure"),
    ):
        workflow = yaml.safe_load((WORKFLOW_PATH.parent / name).read_text(encoding="utf-8"))
        guarded = workflow["jobs"][job]
        condition = guarded["if"]
        assert "github.ref == 'refs/heads/main'" in condition
        assert "github.event_name == 'workflow_dispatch'" in condition
        assert guarded["environment"] == "production"

    ci = yaml.safe_load((WORKFLOW_PATH.parent / "ci.yml").read_text(encoding="utf-8"))
    provider_probe = next(
        step for step in ci["jobs"]["backend-tests"]["steps"]
        if "OPENAI_API_KEY" in step.get("env", {})
    )
    assert "github.event_name == 'workflow_dispatch'" in provider_probe["if"]
    assert "github.ref == 'refs/heads/main'" in provider_probe["if"]


def test_privileged_deploy_accepts_only_push_ci_from_this_repository():
    workflow = yaml.safe_load((WORKFLOW_PATH.parent / "deploy.yml").read_text(encoding="utf-8"))
    condition = workflow["jobs"]["deploy"]["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "github.event.workflow_run.event == 'push'" in condition
    assert "github.event.workflow_run.head_branch == 'main'" in condition
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in condition
