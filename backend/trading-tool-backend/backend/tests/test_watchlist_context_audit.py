import pytest

from backend.scripts.run_finn_production_qa import audit_watchlist_context


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement, params):
        assert "r.user_id = :owner_id" in str(statement)
        assert "c.user_id = :owner_id" in str(statement)
        assert params["owner_id"] == 42
        assert params["run_id"].startswith("finn-v2-run-")
        return self

    def one_or_none(self):
        return (
            {"selected_asset": None, "active_asset": None},
            {"responses_exchange": {
                "tool_trace": [{"name": "read_watchlist", "result": {"symbols": [{"pair": "BTC/USDT"}]}}],
                "answer": "Je hebt een asset op je lijst.",
            }},
        )


def test_context_audit_emits_only_bound_boolean_evidence(monkeypatch):
    from backend.infrastructure import database

    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setattr(database, "async_session_factory", lambda: _Session())
    result = audit_watchlist_context("audit-5733cb84bd40445688d0c7a394c0ed85-btc-usdt")
    assert result == {
        "selected_asset_present": False,
        "active_asset_present": False,
        "read_active_asset_invoked": False,
        "read_watchlist_invoked": True,
        "typed_pair_present_in_tool_result": True,
        "answer_has_base": False,
        "answer_has_quote": False,
        "answer_has_exact_pair": False,
    }


def test_context_audit_rejects_unbound_label(monkeypatch):
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    with pytest.raises(ValueError, match="watchlist_context_audit_input_invalid"):
        audit_watchlist_context("audit-other-user-btc-usdt")
