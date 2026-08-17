from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER
from backend.services.finn_v2_tool_registry_service import FinnV2ToolRegistryService


def test_tool_registry_exposes_canonical_read_only_order():
    service = FinnV2ToolRegistryService()
    rows = service.list_tools()

    assert [row.name for row in rows] == FINN_V2_TOOL_ORDER
    assert all(row.readonly for row in rows)

