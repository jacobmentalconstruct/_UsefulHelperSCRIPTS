import argparse
import json
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.database import get_db_connection, init_db


TOOL_METADATA = {
    "name": "KML Location Importer",
    "description": "Imports customer/location pins from a KML or KMZ file into a MileageCURATOR workspace database.",
    "usage": (
        "python -m src.import_kml_locations "
        "workspaces/2025_Jacob C:/path/to/customers.kmz "
        "--location-type customer --radius-meters 75"
    ),
}


Coordinate = Tuple[float, float]


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def load_kml_root(target_file: Path) -> Tuple[ET.Element, str]:
    suffix = target_file.suffix.lower()

    if suffix == ".kml":
        tree = ET.parse(target_file)
        return tree.getroot(), str(target_file)

    if suffix == ".kmz":
        with zipfile.ZipFile(target_file, "r") as zf:
            kml_names = [name for name in zf.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise FileNotFoundError("No .kml file found inside the .kmz archive.")

            chosen = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
            with zf.open(chosen) as f:
                tree = ET.parse(f)
                return tree.getroot(), f"{target_file}::{chosen}"

    raise ValueError("Unsupported file type. Please provide a .kml or .kmz file.")


def get_direct_child_text(elem: ET.Element, child_tag: str) -> str:
    for child in list(elem):
        if strip_ns(child.tag) == child_tag:
            return (child.text or "").strip()
    return ""


def get_first_descendant(elem: ET.Element, wanted_tag: str) -> Optional[ET.Element]:
    for node in elem.iter():
        if strip_ns(node.tag) == wanted_tag:
            return node
    return None


def get_first_descendant_text(elem: ET.Element, wanted_tag: str) -> str:
    node = get_first_descendant(elem, wanted_tag)
    if node is None:
        return ""
    return (node.text or "").strip()


def parse_kml_coordinates(coord_text: str) -> Coordinate:
    """
    KML Point coordinates are typically:
        longitude,latitude
    or:
        longitude,latitude,altitude
    """
    raw = (coord_text or "").strip()
    if not raw:
        return 0.0, 0.0

    first_coord = raw.split()[0].strip()
    parts = [p.strip() for p in first_coord.split(",")]

    if len(parts) < 2:
        return 0.0, 0.0

    try:
        lng = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        return 0.0, 0.0

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return 0.0, 0.0

    return lat, lng


def collect_extended_data(placemark: ET.Element) -> Dict[str, str]:
    """
    Reads:
      <ExtendedData>
        <Data name="..."><value>...</value></Data>
      </ExtendedData>
    """
    extended: Dict[str, str] = {}

    for node in placemark.iter():
        if strip_ns(node.tag) != "Data":
            continue

        key = (node.attrib.get("name") or "").strip()
        value = ""

        for child in list(node):
            if strip_ns(child.tag) == "value":
                value = (child.text or "").strip()
                break

        if key:
            extended[key] = value

    return extended


def extract_point_placemark(placemark: ET.Element, folder_stack: List[str]) -> Optional[Dict[str, Any]]:
    point_node = get_first_descendant(placemark, "Point")
    if point_node is None:
        return None

    coord_text = get_first_descendant_text(point_node, "coordinates")
    lat, lng = parse_kml_coordinates(coord_text)
    if lat == 0.0 and lng == 0.0:
        return None

    name = get_direct_child_text(placemark, "name")
    description = get_direct_child_text(placemark, "description")
    style_url = get_direct_child_text(placemark, "styleUrl")
    extended_data = collect_extended_data(placemark)

    return {
        "name": name or "Unnamed Location",
        "folder_name": " / ".join(folder_stack) if folder_stack else "",
        "description": description,
        "style_url": style_url,
        "lat": lat,
        "lng": lng,
        "extended_data": extended_data,
    }


def walk_folders_and_placemarks(node: ET.Element, folder_stack: List[str], results: List[Dict[str, Any]]) -> None:
    tag_name = strip_ns(node.tag)

    if tag_name == "Folder":
        folder_name = get_direct_child_text(node, "name")
        next_stack = folder_stack + ([folder_name] if folder_name else [])
        for child in list(node):
            child_tag = strip_ns(child.tag)
            if child_tag in {"Folder", "Placemark"}:
                walk_folders_and_placemarks(child, next_stack, results)
        return

    if tag_name == "Document":
        for child in list(node):
            child_tag = strip_ns(child.tag)
            if child_tag in {"Folder", "Placemark"}:
                walk_folders_and_placemarks(child, folder_stack, results)
        return

    if tag_name == "Placemark":
        record = extract_point_placemark(node, folder_stack)
        if record:
            results.append(record)


def extract_kml_locations(root: ET.Element) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    walk_folders_and_placemarks(root, [], results)
    return results


def ensure_locations_table(project_dir: Path) -> None:
    init_db(project_dir)
    conn = get_db_connection(project_dir)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            folder_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            style_url TEXT DEFAULT '',
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            radius_meters REAL DEFAULT 75,
            location_type TEXT DEFAULT 'customer',
            source_file TEXT DEFAULT '',
            extended_data_json TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_locations_unique
        ON locations (name, lat, lng, folder_name, location_type)
        """
    )

    conn.commit()
    conn.close()


def clear_existing_locations(project_dir: Path, location_type: Optional[str] = None) -> int:
    conn = get_db_connection(project_dir)
    cursor = conn.cursor()

    if location_type:
        cursor.execute("DELETE FROM locations WHERE location_type = ?", (location_type,))
    else:
        cursor.execute("DELETE FROM locations")

    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted if deleted is not None else 0


def import_kml_locations(
    project_dir: Path,
    kml_file: Path,
    location_type: str = "customer",
    radius_meters: float = 75.0,
    clear_existing: bool = False,
) -> Dict[str, Any]:
    if not project_dir.exists():
        raise FileNotFoundError(f"Workspace folder not found: {project_dir}")

    if not kml_file.exists():
        raise FileNotFoundError(f"KML/KMZ file not found: {kml_file}")

    ensure_locations_table(project_dir)

    if clear_existing:
        deleted = clear_existing_locations(project_dir, location_type=location_type)
        print(f"Cleared {deleted} existing '{location_type}' locations.")

    root, source_used = load_kml_root(kml_file)
    records = extract_kml_locations(root)

    if not records:
        return {
            "imported": 0,
            "skipped": 0,
            "duplicates": 0,
            "source": source_used,
            "message": "No point placemarks were found.",
        }

    conn = get_db_connection(project_dir)
    cursor = conn.cursor()

    imported = 0
    duplicates = 0
    skipped = 0

    for rec in records:
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO locations
                (
                    name,
                    folder_name,
                    description,
                    style_url,
                    lat,
                    lng,
                    radius_meters,
                    location_type,
                    source_file,
                    extended_data_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["name"],
                    rec["folder_name"],
                    rec["description"],
                    rec["style_url"],
                    rec["lat"],
                    rec["lng"],
                    radius_meters,
                    location_type,
                    source_used,
                    json.dumps(rec["extended_data"], ensure_ascii=False),
                ),
            )

            if cursor.rowcount == 0:
                duplicates += 1
            else:
                imported += 1

        except sqlite3.Error as exc:
            skipped += 1
            print(f"[SKIP] Could not import '{rec.get('name', 'Unnamed Location')}': {exc}")

    conn.commit()
    conn.close()

    folder_counts: Dict[str, int] = {}
    for rec in records:
        folder = rec["folder_name"] or "(root)"
        folder_counts[folder] = folder_counts.get(folder, 0) + 1

    return {
        "imported": imported,
        "skipped": skipped,
        "duplicates": duplicates,
        "source": source_used,
        "folder_counts": dict(sorted(folder_counts.items(), key=lambda x: x[0].lower())),
        "message": f"Imported {imported} locations from {source_used}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import customer/location pins from KML/KMZ into a MileageCURATOR workspace.")
    parser.add_argument("project_dir", help="Path to the workspace folder, e.g. workspaces/2025_Jacob")
    parser.add_argument("kml_file", help="Path to the .kml or .kmz file")
    parser.add_argument("--location-type", default="customer", help="Stored location type label (default: customer)")
    parser.add_argument("--radius-meters", type=float, default=75.0, help="Default geofence radius in meters (default: 75)")
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Delete existing locations of the same location_type before import",
    )

    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    kml_file = Path(args.kml_file)

    result = import_kml_locations(
        project_dir=project_dir,
        kml_file=kml_file,
        location_type=args.location_type,
        radius_meters=args.radius_meters,
        clear_existing=args.clear_existing,
    )

    print("\n=== Import Complete ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
