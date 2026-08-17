from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


def test_request_analysis_is_transport_agnostic():
    message = "Past mijn huidige BTC-strategie bij mijn risicoprofiel en tradingstijl?"
    service = FinnV2RequestAnalysisService()

    chat_result = service.analyze(message=message, workspace_hints={"transport": "chat"})
    stream_result = service.analyze(message=message, client_context={"transport": "stream"})

    assert chat_result.dict(exclude={"analysis_version"}) == stream_result.dict(exclude={"analysis_version"})
