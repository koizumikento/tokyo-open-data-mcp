from math import asin, cos, radians, sin, sqrt
from typing import Annotated, Any

import httpx
from pydantic import Field, validate_call

API_URL = "https://api.data.metro.tokyo.lg.jp/v1/MultipurposeToilet"
SOURCE_URL = "https://portal.data.metro.tokyo.lg.jp/opendata-api/"
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Limit = Annotated[int, Field(ge=1, le=50)]


def _distance_m(lat: float, lon: float, target_lat: float, target_lon: float) -> float:
    a = sin(radians(target_lat - lat) / 2) ** 2 + (
        cos(radians(lat)) * cos(radians(target_lat)) * sin(radians(target_lon - lon) / 2) ** 2
    )
    return 12_742_000 * asin(sqrt(min(a, 1)))


@validate_call
async def find_accessible_toilets(
    latitude: Latitude,
    longitude: Longitude,
    limit: Limit = 10,
    require_ostomate: bool = False,
) -> dict[str, Any]:
    """Find nearest listed wheelchair-accessible toilets, optionally with ostomate equipment."""
    items: list[dict[str, Any]] = []
    cursor = None
    seen_cursors = set()
    updated = None
    revision = None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for page in range(20):
                params: dict[str, str | int] = {"limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                response = await client.get(API_URL, params=params)
                response.raise_for_status()
                rows, metadata = response.json()
                if not isinstance(rows, list) or not isinstance(metadata, dict):
                    raise ValueError
                if page == 0:
                    updated = metadata["updated"]
                    revision = metadata["revision"]
                elif metadata["revision"] != revision:
                    raise ValueError("Tokyo's dataset changed during pagination. Retry the search.")
                for row in rows:
                    coordinates = row.get("地理座標") or {}
                    try:
                        lat = float(coordinates.get("緯度", ""))
                        lon = float(coordinates.get("経度", ""))
                    except (ValueError, TypeError):
                        continue
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue
                    equipment = row.get("設備") or {}
                    ostomate = equipment.get("ex:オストメイト有無")
                    if require_ostomate and ostomate != "○":
                        continue
                    items.append(
                        {
                            "id": (row.get("ID") or {}).get("識別値"),
                            "name": (row.get("名称") or {}).get("表記"),
                            "address": (row.get("住所") or {}).get("表記"),
                            "latitude": lat,
                            "longitude": lon,
                            "distance_m": round(_distance_m(latitude, longitude, lat, lon), 1),
                            "wheelchair_access": equipment.get("ex:車椅子の出入り可否"),
                            "ostomate": ostomate,
                        }
                    )
                if metadata["moreResults"] == "NO_MORE_RESULTS":
                    break
                cursor = metadata["endCursor"]
                if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                    raise ValueError
                seen_cursors.add(cursor)
            else:
                raise ValueError("Tokyo's API exceeded the page limit for a complete search.")
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Tokyo Open Data returned HTTP {exc.response.status_code}.") from None
    except httpx.RequestError:
        raise ValueError("Could not reach the Tokyo Open Data API.") from None
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Tokyo's"):
            raise
        raise ValueError("Tokyo Open Data returned unexpected toilet data.") from None

    items.sort(key=lambda item: item["distance_m"])
    return {"items": items[:limit], "updated_at": updated, "source_url": SOURCE_URL}
