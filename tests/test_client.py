import csv
import io

import httpx
import pytest
import respx

from tokyo_open_data_mcp import dataset, find_accessible_toilets

FACILITY_URL = "https://www.opendata.metro.tokyo.lg.jp/fukushi/R07/facility.csv"
RAIL_URL = "https://www.opendata.metro.tokyo.lg.jp/fukushi/R07/rail.csv"


def csv_fixture(kind: dataset.CsvKind, *records: dict[str, str]) -> bytes:
    default = {
        **dict.fromkeys(dataset._ID_FIELDS[kind], "1"),
        dataset._NAME_FIELDS[kind]: "新宿",
        "都道府県": "東京都",
        "市区町村・番地": "新宿区",
        "トイレ名": "多目的トイレ",
        "設置フロア": "B1F",
        "緯度": "35.01",
        "経度": "139.0",
        "座標系": "JGD2011",
        "備考": "",
        **dict.fromkeys(dataset._EQUIPMENT.values(), "○"),
        **dict.fromkeys(dataset._DATE_FIELDS, ""),
        "データの作成年月": "202507",
    }
    if kind == "rail":
        default.update({"鉄道会社名": "鉄道会社", "路線名": "路線"})
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([f" {header} " for header in default])
    for record in records:
        assert set(record) <= default.keys()
        writer.writerow((default | record).values())
    return output.getvalue().encode("cp932")


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dataset, "_snapshot", None)


def mock_catalog() -> respx.Route:
    return respx.get(dataset.CATALOG_API, params={"id": dataset.CATALOG_ID}).respond(
        200,
        json={
            "result": {
                "title": "令和７年度更新版",
                "metadata_modified": "2026-06-18T02:56:34",
                "resources": [
                    {"format": "CSV", "name": dataset.CSV_NAMES["facility"], "url": FACILITY_URL},
                    {"format": "CSV", "name": dataset.CSV_NAMES["rail"], "url": RAIL_URL},
                ],
            }
        },
    )


def test_csv_can_contain_only_deleted_records() -> None:
    rows, month = dataset._parse_csv(
        csv_fixture("facility", {"データの削除年月": "202601"}), "facility"
    )
    assert rows == []
    assert month == "2026-01"


@pytest.mark.asyncio
@respx.mock
async def test_searches_both_sources_and_filters_deleted_and_missing_equipment() -> None:
    mock_catalog()
    respx.get(FACILITY_URL).respond(
        200,
        content=csv_fixture(
            "facility",
            {"施設名": "削除済み", "緯度": "35.0", "データの削除年月": "202601"},
            {"施設名": "おむつ交換台のみ", "緯度": "35.001", "介助用ベッドを備えている": "×"},
            {"施設名": "最寄りの施設", "緯度": "35.02", "介助用ベッドを備えている": "○（注）"},
        ),
    )
    respx.get(RAIL_URL).respond(
        200,
        content=csv_fixture(
            "rail",
            {"トイレ名": "ホームのトイレ", "乳幼児用おむつ交換台等を備えている": "△"},
            {"トイレ名": "改札のトイレ", "緯度": "35.015"},
        ),
    )

    results = await find_accessible_toilets(
        35.0,
        139.0,
        require_universal_sheet=True,
        require_baby_changing_table=True,
        require_ostomate_warm_water=True,
    )
    assert results["updated_at"] == "2026-01"
    assert set(results["files"]) == {"facility", "rail"}
    assert [item["name"] for item in results["items"]] == ["新宿", "最寄りの施設"]
    assert results["items"][0]["toilet_name"] == "改札のトイレ"
    assert results["items"][0]["operator"] == "鉄道会社"
    assert results["items"][1]["universal_sheet"] == "○（注）"

    rail = await find_accessible_toilets(35.0, 139.0, source_kind="rail")
    assert {item["source_kind"] for item in rail["items"]} == {"rail"}
    assert len({item["id"] for item in rail["items"]}) == 2
    assert rail["updated_at"] == "2025-07"


@pytest.mark.asyncio
@respx.mock
async def test_refresh_revalidates_both_files_and_rejects_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = 0
    monkeypatch.setattr(dataset, "monotonic", lambda: clock)
    catalog = mock_catalog()
    facility = respx.get(FACILITY_URL).mock(
        side_effect=[
            httpx.Response(200, content=csv_fixture("facility", {}), headers={"ETag": '"v1"'}),
            httpx.Response(304),
            httpx.Response(304),
            httpx.Response(304),
        ]
    )
    modified = "Thu, 18 Jun 2026 00:44:49 GMT"
    rail = respx.get(RAIL_URL).mock(
        side_effect=[
            httpx.Response(
                200, content=csv_fixture("rail", {}), headers={"Last-Modified": modified}
            ),
            httpx.Response(304),
            httpx.Response(503),
            httpx.Response(200, content=csv_fixture("rail", {"鉄道駅名": "更新後"})),
        ]
    )

    first = await find_accessible_toilets(35.0, 139.0)
    await find_accessible_toilets(35.0, 139.0)
    assert catalog.call_count == 1
    assert facility.call_count == rail.call_count == 1
    clock = dataset._TTL
    second = await find_accessible_toilets(35.0, 139.0)
    assert second["items"] == first["items"]
    assert facility.calls[1].request.headers["If-None-Match"] == '"v1"'
    assert rail.calls[1].request.headers["If-Modified-Since"] == modified

    clock += dataset._TTL
    with pytest.raises(ValueError, match="503"):
        await find_accessible_toilets(35.0, 139.0)
    recovered = await find_accessible_toilets(35.0, 139.0, source_kind="rail")
    assert recovered["items"][0]["name"] == "更新後"
