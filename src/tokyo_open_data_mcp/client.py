import asyncio
from math import asin, cos, radians, sin, sqrt
from typing import Annotated, Any

from pydantic import Field, validate_call

from .dataset import SOURCE_URL, CsvKind, load_snapshot

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
    require_universal_sheet: bool = False,
    require_baby_changing_table: bool = False,
    require_ostomate_warm_water: bool = False,
    source_kind: CsvKind | None = None,
) -> dict[str, Any]:
    """Find nearest listed wheelchair-accessible toilets in Tokyo facilities and railway stations.

    Set equipment flags to require every selected feature. A universal sheet is an adult changing
    bed, distinct from a baby changing table. Omit source_kind to search both types of location.
    """
    snapshot = await asyncio.to_thread(load_snapshot)
    required_equipment = [
        key
        for key, enabled in (
            ("ostomate", require_ostomate or require_ostomate_warm_water),
            ("universal_sheet", require_universal_sheet),
            ("baby_changing_table", require_baby_changing_table),
            ("ostomate_warm_water", require_ostomate_warm_water),
        )
        if enabled
    ]
    sources = {
        kind: data
        for kind, data in snapshot.sources.items()
        if source_kind is None or source_kind == kind
    }
    items = []
    for data in sources.values():
        for row in data.rows:
            if not all((row[key] or "").startswith(("○", "〇")) for key in required_equipment):
                continue
            distance = _distance_m(latitude, longitude, row["latitude"], row["longitude"])
            items.append({**row, "distance_m": distance})
    items.sort(key=lambda item: item["distance_m"])
    closest = items[:limit]
    for item in closest:
        item["distance_m"] = round(item["distance_m"], 1)
    return {
        "items": closest,
        "updated_at": max(
            (data.updated_at for data in sources.values() if data.updated_at), default=None
        ),
        "source_url": SOURCE_URL,
        "dataset_title": snapshot.title,
        "catalog_updated_at": snapshot.catalog_updated_at,
        "checked_at": snapshot.checked_at,
        "files": {
            kind: {
                "url": data.url,
                "last_modified": data.last_modified,
                "updated_at": data.updated_at,
            }
            for kind, data in sources.items()
        },
    }
