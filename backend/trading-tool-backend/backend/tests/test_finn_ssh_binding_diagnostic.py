from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "ops" / "qa" / "diagnose_finn_ssh_binding.py"
WORKFLOW = ROOT / ".github" / "workflows" / "finn-production-qa.yml"


def _module():
    spec = importlib.util.spec_from_file_location("ssh_binding_diagnostic", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_binding_comparison_outputs_only_fixed_values(monkeypatch):
    module = _module()
    calls = []

    def run(args, **_kwargs):
        calls.append(args[0])
        value = "host ssh-ed25519 AAAAvalid\n" if args[0] == "ssh-keygen" else "host ssh-ed25519 AAAAvalid\n"
        return subprocess.CompletedProcess(args, 0, stdout=value, stderr="")

    monkeypatch.setattr(module.subprocess, "run", run)
    result = module.diagnose("qa.example", "qa.example", "qa.example ssh-ed25519 AAAAvalid\n")
    assert result == {
        "qa_host_equals_deploy_host": "true",
        "qa_pin_contains_selected_host": "true",
        "qa_pin_matches_deploy_host": "true",
    }
    assert calls == ["ssh-keygen", "ssh-keyscan"]


def test_binding_mismatch_and_unreachable_scan_are_distinct(monkeypatch):
    module = _module()

    def mismatch(args, **_kwargs):
        value = "host ssh-ed25519 AAAAold\n" if args[0] == "ssh-keygen" else "host ssh-ed25519 AAAAnew\n"
        return subprocess.CompletedProcess(args, 0, stdout=value, stderr="")

    monkeypatch.setattr(module.subprocess, "run", mismatch)
    result = module.diagnose("qa.example", "deploy.example", "qa.example ssh-ed25519 AAAAold\n")
    assert result == {
        "qa_host_equals_deploy_host": "false",
        "qa_pin_contains_selected_host": "true",
        "qa_pin_matches_deploy_host": "false",
    }

    def unreachable(args, **_kwargs):
        if args[0] == "ssh-keyscan":
            raise subprocess.TimeoutExpired(args, 10)
        return mismatch(args)

    monkeypatch.setattr(module.subprocess, "run", unreachable)
    assert module.diagnose("qa.example", "deploy.example", "pin")[
        "qa_pin_matches_deploy_host"] == "unavailable"


def test_diagnostic_is_exact_label_read_only_and_does_not_print_secrets():
    source = WORKFLOW.read_text(encoding="utf-8")
    branch = source.split("- name: Diagnose protected SSH binding without revealing endpoints", 1)[1]
    branch = branch.split("- name: Create isolated fixture namespace", 1)[0]
    assert "inputs.qa_profile == 'auth_preflight'" in branch
    assert "inputs.run_label == 'qa-host-diagnostic-44977345882'" in branch
    assert "python3 ops/qa/diagnose_finn_ssh_binding.py" in branch
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'print(f"{key}={value}")' in script
    assert "print(qa_host" not in script
    assert "print(deploy_host" not in script
    assert "print(known_hosts" not in script
