import httpx
import pytest
import respx

from tokyo_open_data_mcp import find_accessible_toilets
from tokyo_open_data_mcp.client import API_URL


def fixture_row(name: str, lat: str, ostomate: str) -> dict:
    return {
        "名称": {"表記": name},
        "地理座標": {"緯度": lat, "経度": "139.0"},
        "設備": {"ex:オストメイト有無": ostomate},
    }


@pytest.mark.asyncio
@respx.mock
async def test_nearest_match_can_be_on_second_page() -> None:
    metadata = {"updated": "2021-12-21", "revision": 1}
    route = respx.get(API_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json=[
                    [fixture_row("遠方", "35.2", "○")],
                    {
                        **metadata,
                        "endCursor": "page-two",
                        "moreResults": "MORE_RESULTS_AFTER_LIMIT",
                    },
                ],
            ),
            httpx.Response(
                200,
                json=[
                    [fixture_row("最寄り", "35.0", "×"), fixture_row("次点", "35.01", "○")],
                    {**metadata, "moreResults": "NO_MORE_RESULTS"},
                ],
            ),
        ]
    )
    result = await find_accessible_toilets(35.0, 139.0, limit=1, require_ostomate=True)
    assert route.calls[1].request.url.params["cursor"] == "page-two"
    assert result["updated_at"] == "2021-12-21"
    assert result["items"][0]["name"] == "次点"
