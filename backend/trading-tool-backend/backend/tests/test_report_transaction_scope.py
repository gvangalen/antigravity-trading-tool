from backend.services.finn_unified_report_service import _report_v2_contradicts_facts


def test_report_rejects_unbounded_absence_of_executed_trades():
    facts = {"assets": []}
    context = {}
    comparison = {}

    for claim in (
        "Er zijn geen feiten over uitgevoerde transacties.",
        "Er is geen bewijs van uitgevoerde transacties.",
        "There is no evidence of executed transactions.",
    ):
        assert _report_v2_contradicts_facts("retrospective", claim, facts, context, comparison)

    for claim in (
        "Er is geen bewijs van uitgevoerde transacties op 13 november.",
        "Er zijn geen feiten over uitgevoerde transacties in deze rapportperiode.",
        "There is no evidence of executed transactions in this period.",
    ):
        assert not _report_v2_contradicts_facts("retrospective", claim, facts, context, comparison)
