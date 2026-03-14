import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.database import get_db_connection, init_db

Coordinate = Tuple[float, float]


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in miles between two points."""
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _is_valid_coordinate(lat: float, lng: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0 and not (lat == 0.0 and lng == 0.0)


def parse_point(point_value: Any) -> Coordinate:
    """
    Parse a coordinate from multiple possible Google Timeline-ish shapes.

    Supported examples:
    - "geo:44.981,-93.263;u=35"
    - "44.981,-93.263"
    - {"latitudeE7": 449810000, "longitudeE7": -932630000}
    - {"lat": 44.981, "lng": -93.263}
    - {"latitude": 44.981, "longitude": -93.263}
    - {"point": "geo:44.981,-93.263;u=35"}
    - [44.981, -93.263]
    """
    if point_value is None:
        return 0.0, 0.0

    if isinstance(point_value, (list, tuple)) and len(point_value) >= 2:
        try:
            lat = float(point_value[0])
            lng = float(point_value[1])
            if _is_valid_coordinate(lat, lng):
                return lat, lng
        except (TypeError, ValueError):
            pass
        return 0.0, 0.0

    if isinstance(point_value, dict):
        # Nested common wrappers first
        for nested_key in ("point", "location", "latLng", "latLngLiteral", "coordinate", "coords"):
            if nested_key in point_value:
                lat, lng = parse_point(point_value[nested_key])
                if _is_valid_coordinate(lat, lng):
                    return lat, lng

        # Google E7 integer format
        if "latitudeE7" in point_value and "longitudeE7" in point_value:
            try:
                lat = float(point_value["latitudeE7"]) / 10_000_000.0
                lng = float(point_value["longitudeE7"]) / 10_000_000.0
                if _is_valid_coordinate(lat, lng):
                    return lat, lng
            except (TypeError, ValueError):
                pass

        # Common float-key formats
        key_pairs = [
            ("lat", "lng"),
            ("lat", "lon"),
            ("latitude", "longitude"),
            ("latitude", "lng"),
            ("y", "x"),
        ]
        for lat_key, lng_key in key_pairs:
            if lat_key in point_value and lng_key in point_value:
                try:
                    lat = float(point_value[lat_key])
                    lng = float(point_value[lng_key])
                    if _is_valid_coordinate(lat, lng):
                        return lat, lng
                except (TypeError, ValueError):
                    pass

        return 0.0, 0.0

    if isinstance(point_value, str):
        raw = point_value.strip()
        if not raw:
            return 0.0, 0.0

        raw = raw.replace("geo:", "").strip()
        raw = raw.split(";")[0].strip()
        raw = raw.strip("()[]{}")

        # Fast path: plain "lat,lng"
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) >= 2:
            try:
                lat = float(parts[0])
                lng = float(parts[1])
                if _is_valid_coordinate(lat, lng):
                    return lat, lng
            except ValueError:
                pass

        # Regex fallback: first two floats in the string
        matches = re.findall(r"-?\d+(?:\.\d+)?", raw)
        if len(matches) >= 2:
            try:
                lat = float(matches[0])
                lng = float(matches[1])
                if _is_valid_coordinate(lat, lng):
                    return lat, lng
            except ValueError:
                pass

    return 0.0, 0.0


def _append_if_valid(points: List[Coordinate], candidate: Any) -> None:
    lat, lng = parse_point(candidate)
    if _is_valid_coordinate(lat, lng):
        points.append((lat, lng))


def _dedupe_consecutive_points(points: List[Coordinate]) -> List[Coordinate]:
    if not points:
        return []

    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    return deduped


def extract_segment_points(segment: Dict[str, Any]) -> List[Coordinate]:
    """
    Extract as many valid points as possible from a segment.

    Primary source:
    - segment["timelinePath"]

    Fallbacks:
    - segment["start"], segment["end"]
    - segment["startLocation"], segment["endLocation"]
    - nested activity / activitySegment variants
    """
    points: List[Coordinate] = []

    timeline_path = segment.get("timelinePath", [])
    if isinstance(timeline_path, dict):
        timeline_path = (
            timeline_path.get("points")
            or timeline_path.get("timelinePath")
            or timeline_path.get("path")
            or []
        )

    if isinstance(timeline_path, list):
        for item in timeline_path:
            if isinstance(item, dict):
                appended = False
                for key in ("point", "location", "latLng", "latLngLiteral", "coordinate", "coords"):
                    if key in item:
                        _append_if_valid(points, item[key])
                        appended = True
                        break
                if not appended:
                    _append_if_valid(points, item)
            else:
                _append_if_valid(points, item)

    # Fallback endpoints from several likely locations
    if len(points) < 2:
        fallback_candidates = [
            segment.get("start"),
            segment.get("end"),
            segment.get("startLocation"),
            segment.get("endLocation"),
        ]

        activity = segment.get("activity", {})
        if isinstance(activity, dict):
            fallback_candidates.extend(
                [
                    activity.get("start"),
                    activity.get("end"),
                    activity.get("startLocation"),
                    activity.get("endLocation"),
                ]
            )

        activity_segment = segment.get("activitySegment", {})
        if isinstance(activity_segment, dict):
            fallback_candidates.extend(
                [
                    activity_segment.get("start"),
                    activity_segment.get("end"),
                    activity_segment.get("startLocation"),
                    activity_segment.get("endLocation"),
                ]
            )

        for candidate in fallback_candidates:
            _append_if_valid(points, candidate)

    return _dedupe_consecutive_points(points)


def path_distance_miles(points: List[Coordinate]) -> float:
    """Sum the distance across all consecutive route points."""
    if len(points) < 2:
        return 0.0

    total = 0.0
    for i in range(1, len(points)):
        lat1, lng1 = points[i - 1]
        lat2, lng2 = points[i]
        total += haversine_miles(lat1, lng1, lat2, lng2)
    return total


def extract_times(segment: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (start_time, end_time, date) using several likely field shapes."""
    start_time = str(segment.get("startTime", "") or "")
    end_time = str(segment.get("endTime", "") or "")

    if not start_time or not end_time:
        duration = segment.get("duration", {})
        if isinstance(duration, dict):
            start_time = start_time or str(duration.get("startTimestamp", "") or "")
            end_time = end_time or str(duration.get("endTimestamp", "") or "")

    if not start_time or not end_time:
        activity_segment = segment.get("activitySegment", {})
        if isinstance(activity_segment, dict):
            duration = activity_segment.get("duration", {})
            if isinstance(duration, dict):
                start_time = start_time or str(duration.get("startTimestamp", "") or "")
                end_time = end_time or str(duration.get("endTimestamp", "") or "")

    date = start_time.split("T")[0] if "T" in start_time else ""
    return start_time, end_time, date


def ingest_timeline_data(project_dir: Path) -> None:
    """Parse Timeline.json and insert trips into the database."""
    json_path = project_dir / "Timeline.json"

    if not json_path.exists():
        print(f"Error: Could not find Timeline.json in {project_dir}")
        return

    init_db(project_dir)
    conn = get_db_connection(project_dir)
    cursor = conn.cursor()

    print(f"Loading JSON data from {json_path.name}...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("semanticSegments", [])
    if not isinstance(segments, list):
        print("Error: 'semanticSegments' was not a list.")
        conn.close()
        return

    inserted_count = 0
    rejects = {
        "non_dict_segment": 0,
        "short_path": 0,
        "too_short_distance": 0,
        "db_errors": 0,
    }

    debug_samples = {
        "short_path": 0,
        "too_short_distance": 0,
    }
    debug_sample_limit = 5

    print(f"Scanning {len(segments)} total timeline segments...")

    for idx, segment in enumerate(segments):
        if not isinstance(segment, dict):
            rejects["non_dict_segment"] += 1
            continue

        points = extract_segment_points(segment)
        if len(points) < 2:
            rejects["short_path"] += 1
            if debug_samples["short_path"] < debug_sample_limit:
                raw_path = segment.get("timelinePath", [])
                path_len = len(raw_path) if isinstance(raw_path, list) else 0
                print(f"[SHORT_PATH] idx={idx} extracted_points={len(points)} raw_path_len={path_len}")
                debug_samples["short_path"] += 1
            continue

        start_lat, start_lng = points[0]
        end_lat, end_lng = points[-1]

        # Prefer full path distance; if weirdly tiny, compare to endpoint distance.
        distance_miles = path_distance_miles(points)
        direct_distance = haversine_miles(start_lat, start_lng, end_lat, end_lng)
        distance_miles = max(distance_miles, direct_distance)

        if distance_miles < 0.2:
            rejects["too_short_distance"] += 1
            if debug_samples["too_short_distance"] < debug_sample_limit:
                print(
                    f"[TOO_SHORT] idx={idx} "
                    f"path_points={len(points)} "
                    f"path_distance={distance_miles:.4f}"
                )
                debug_samples["too_short_distance"] += 1
            continue

        start_time, end_time, date = extract_times(segment)

        try:
            cursor.execute(
                """
                INSERT INTO trips
                (date, start_time, end_time, start_lat, start_lng, end_lat, end_lng, distance_miles)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    start_time,
                    end_time,
                    start_lat,
                    start_lng,
                    end_lat,
                    end_lng,
                    distance_miles,
                ),
            )
            inserted_count += 1
        except Exception as exc:
            rejects["db_errors"] += 1
            print(f"[DB_ERROR] idx={idx} error={exc}")

    conn.commit()
    conn.close()

    print(f"Ingestion complete! Successfully recorded {inserted_count} driving trips.")
    print(f"Reject summary: {rejects}")


if __name__ == "__main__":
    test_workspace = Path("../workspaces/test_project")
    if test_workspace.exists():
        ingest_timeline_data(test_workspace)
    else:
        print("Run workspace.py first to create a test project folder!")
