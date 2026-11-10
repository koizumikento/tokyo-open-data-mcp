import sys

import pytest
from mcp import Client, StdioServerParameters


@pytest.mark.asyncio
async def test_stdio_tool_contract() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "tokyo_open_data_mcp"])
    async with Client(params, mode="legacy", read_timeout_seconds=10) as client:
        result = await client.list_tools()
    assert {tool.name for tool in result.tools} == {"find_accessible_toilets"}
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in result.tools)
    assert {
        "latitude",
        "longitude",
        "limit",
        "require_ostomate",
        "require_ostomate_warm_water",
        "require_universal_sheet",
        "require_baby_changing_table",
        "source_kind",
    } == result.tools[0].input_schema["properties"].keys()
