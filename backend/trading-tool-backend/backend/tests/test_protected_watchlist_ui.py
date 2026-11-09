import pytest
from pathlib import Path
from types import SimpleNamespace
import sys

from backend.scripts.probe_protected_watchlist_ui import SCENARIOS, _mentions
from backend.scripts.run_finn_production_qa import load_watchlist_browser_probe, sha256_file


def test_watchlist_browser_mentions_are_bounded_and_ordered():
    text = "Apple niet meer volgen; volg Bitcoin in mijn watchlist"
    result = _mentions('{"text":"' + text + '"}')
    assert [(item["symbol"], item["start"]) for item in result["mentions"]] == [
        ("AAPL", text.index("Apple")), ("BTC", text.index("Bitcoin")),
    ]
    assert len(SCENARIOS) == 5


def test_watchlist_browser_rejects_unapproved_prompt():
    with pytest.raises(ValueError, match="watchlist_mentions_request_unexpected"):
        _mentions('{"text":"Koop BTC live"}')


def test_attempt_scoped_browser_modules_require_matching_hashes(tmp_path):
    source = Path(__file__).resolve().parents[1] / "scripts"
    helper = tmp_path / "qa_protected_browser.py"
    probe = tmp_path / "probe_protected_watchlist_ui.py"
    helper.write_bytes((source / helper.name).read_bytes())
    probe.write_bytes((source / probe.name).read_bytes())
    args = SimpleNamespace(
        report_path=str(tmp_path / "report.json"),
        watchlist_browser_helper_path=str(helper),
        watchlist_browser_helper_sha256=sha256_file(helper),
        watchlist_browser_probe_path=str(probe),
        watchlist_browser_probe_sha256=sha256_file(probe),
    )
    names = ("backend.scripts.qa_protected_browser", "backend.scripts.probe_protected_watchlist_ui")
    previous = {name: sys.modules.get(name) for name in names}
    try:
        assert callable(load_watchlist_browser_probe(args).run)
        args.watchlist_browser_probe_sha256 = "0" * 64
        with pytest.raises(ValueError, match="watchlist_browser_module_invalid"):
            load_watchlist_browser_probe(args)
        args.watchlist_browser_probe_sha256 = sha256_file(probe)
        args.watchlist_browser_probe_path = str(tmp_path.parent / probe.name)
        with pytest.raises(ValueError, match="watchlist_browser_module_invalid"):
            load_watchlist_browser_probe(args)
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
