import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any, Literal

import httpx

CATALOG_ID = "t000054d0000000342"
CATALOG_API = "https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_show"
SOURCE_URL = f"https://catalog.data.metro.tokyo.lg.jp/dataset/{CATALOG_ID}"
CsvKind = Literal["facility", "rail"]
CSV_NAMES: dict[CsvKind, str] = {
    "facility": "都立及び区市町村立施設等における車椅子使用者対応トイレのバリアフリー設備情報",
    "rail": "都内鉄道駅における車椅子使用者対応トイレのバリアフリー設備情報",
}
_ID_FIELDS = {
    "facility": (
        "管理者種別番号",
        "部局番号",
        "施設種別番号",
        "施設通し番号",
        "施設内トイレ通し番号",
    ),
    "rail": ("管理者種別番号", "鉄道駅通し番号", "鉄道駅内トイレ通し番号"),
}
_NAME_FIELDS = {"facility": "施設名", "rail": "鉄道駅名"}
_EQUIPMENT = {
    "wheelchair_access": "車椅子が出入りできる（出入口の有効幅員80cm以上）",
    "ostomate": "オストメイト用設備がある",
    "ostomate_warm_water": "オストメイト用設備が温水対応している",
    "universal_sheet": "介助用ベッドを備えている",
    "baby_changing_table": "乳幼児用おむつ交換台等を備えている",
}
_DATE_FIELDS = ("データの作成年月", "データの変更年月", "データの削除年月")
_TTL = 15 * 60
_MAX_CSV_BYTES = 16 * 1024 * 1024
_LOCK = Lock()


@dataclass(frozen=True)
class CsvData:
    url: str
    etag: str | None
    last_modified: str | None
    updated_at: str | None
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class Snapshot:
    expires_at: float
    checked_at: str
    catalog_updated_at: str
    title: str
    sources: dict[CsvKind, CsvData]


_snapshot: Snapshot | None = None


def _coordinates(row: dict[str, str]) -> tuple[float, float] | None:
    if row["座標系"] != "JGD2011":
        return None
    try:
        lat, lon = float(row["緯度"]), float(row["経度"])
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def _parse_csv(contents: bytes, kind: CsvKind) -> tuple[list[dict[str, Any]], str | None]:
    try:
        decoded = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = contents.decode("cp932")
    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    headers = [value.strip() for value in next(reader, [])]
    required = {
        *_ID_FIELDS[kind],
        _NAME_FIELDS[kind],
        *_EQUIPMENT.values(),
        *_DATE_FIELDS,
        "都道府県",
        "市区町村・番地",
        "トイレ名",
        "設置フロア",
        "緯度",
        "経度",
        "座標系",
        "備考",
    }
    if kind == "rail":
        required.update(("鉄道会社名", "路線名"))
    if not required.issubset(headers):
        raise ValueError("Missing expected CSV columns.")

    rows: list[dict[str, Any]] = []
    updated_at = ""
    for values in reader:
        if not values:
            continue
        row = dict(zip(headers, (value.strip() for value in values), strict=True))
        for field in _DATE_FIELDS:
            date = row[field]
            if re.fullmatch(r"[0-9]{4}(0[1-9]|1[0-2])", date):
                updated_at = max(updated_at, f"{date[:4]}-{date[4:]}")
        if row["データの削除年月"]:
            continue
        coordinates = _coordinates(row)
        id_parts = [row[field] for field in _ID_FIELDS[kind]]
        name = row[_NAME_FIELDS[kind]]
        if coordinates is None or not name or not all(id_parts):
            continue

        lat, lon = coordinates
        if kind == "rail":
            # Some active toilets share official serial numbers.
            key = "\n".join((row["トイレ名"], row["設置フロア"], row["緯度"], row["経度"]))
            id_parts.append(sha256(key.encode()).hexdigest()[:12])
        rows.append(
            {
                "id": f"{kind}-" + "-".join(id_parts),
                "name": name,
                "address": row["都道府県"] + row["市区町村・番地"],
                "latitude": lat,
                "longitude": lon,
                "source_kind": kind,
                "toilet_name": row["トイレ名"] or None,
                "floor": row["設置フロア"] or None,
                "operator": row.get("鉄道会社名") or None,
                "line": row.get("路線名") or None,
                "notes": row["備考"] or None,
                **{key: row[column] or None for key, column in _EQUIPMENT.items()},
            }
        )
    return rows, updated_at or None


def _download(client: httpx.Client, url: str, kind: CsvKind, previous: CsvData | None) -> CsvData:
    headers = {}
    if previous and previous.url == url:
        if previous.etag:
            headers["If-None-Match"] = previous.etag
        if previous.last_modified:
            headers["If-Modified-Since"] = previous.last_modified
    with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 304 and previous and headers:
            return previous
        response.raise_for_status()
        contents = bytearray()
        for chunk in response.iter_bytes(chunk_size=64 * 1024):
            if len(contents) + len(chunk) > _MAX_CSV_BYTES:
                raise ValueError("CSV exceeds the download limit.")
            contents.extend(chunk)
        rows, updated_at = _parse_csv(bytes(contents), kind)
        return CsvData(
            url,
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
            updated_at,
            rows,
        )


def load_snapshot() -> Snapshot:
    global _snapshot
    with _LOCK:
        if _snapshot and monotonic() < _snapshot.expires_at:
            return _snapshot
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(CATALOG_API, params={"id": CATALOG_ID})
                response.raise_for_status()
                package = response.json()["result"]
                title = package["title"]
                catalog_updated_at = package["metadata_modified"]
                urls: dict[CsvKind, str] = {}
                releases = set()
                for kind, name in CSV_NAMES.items():
                    (url,) = [
                        resource["url"]
                        for resource in package["resources"]
                        if resource["format"].upper() == "CSV" and resource["name"].strip() == name
                    ]
                    match = re.fullmatch(
                        r"https://www\.opendata\.metro\.tokyo\.lg\.jp/fukushi/(R[0-9]{2})/"
                        r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.csv",
                        url,
                    )
                    if match is None:
                        raise ValueError("Unexpected official CSV address.")
                    releases.add(match[1])
                    urls[kind] = url
                if len(releases) != 1:
                    raise ValueError("The two CSVs are from different releases.")
                sources = {
                    kind: _download(
                        client, url, kind, _snapshot.sources[kind] if _snapshot else None
                    )
                    for kind, url in urls.items()
                }
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Tokyo Open Data returned HTTP {exc.response.status_code}.") from None
        except httpx.RequestError:
            raise ValueError("Could not reach Tokyo Open Data.") from None
        except (KeyError, TypeError, AttributeError, ValueError, csv.Error):
            raise ValueError("Tokyo Open Data returned unexpected toilet data.") from None

        _snapshot = Snapshot(
            monotonic() + _TTL, datetime.now(UTC).isoformat(), catalog_updated_at, title, sources
        )
        return _snapshot
