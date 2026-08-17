import asyncio

from backend.services.finn_v2_shadow_comparison_service import FinnV2ShadowComparisonService


def test_shadow_comparison_flags_unsafe_execution_language():
    service = FinnV2ShadowComparisonService(session=object())
    service.repo.create = lambda **kwargs: asyncio.sleep(0, result=kwargs)

    result = asyncio.run(
        service.compare(
            surface="assistant_chat",
            v1_response={"intent": "evaluation", "response": "BTC blijft in afwachting."},
            v2_response={"mode": "EVALUATION", "direct_answer": "BTC order uitgevoerd."},
        )
    )

    assert result.outcome == "v2_unsafe"
    assert "unsafe_execution_language" in result.reason_codes
