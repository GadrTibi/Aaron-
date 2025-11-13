"""Command-line helper to exercise transport retrieval."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.services.poi import fetch_transports, list_bus_lines, list_metro_lines


def _print_debug(label: str, debug: Dict[str, Any]) -> None:
    mirror = debug.get("mirror") or "?"
    duration = debug.get("duration_ms")
    items = debug.get("items")
    status = debug.get("status")
    radius = debug.get("radius") or debug.get("radius_final")
    parts = [f"mirror={mirror}"]
    if duration is not None:
        parts.append(f"req={int(duration)}ms")
    if radius is not None:
        parts.append(f"radius={radius}")
    if items is not None:
        parts.append(f"items={items}")
    if status and status != "ok":
        parts.append(f"status={status}")
    error = debug.get("error")
    if error:
        parts.append(f"error={error}")
    print(f"{label}: {' | '.join(parts)}")


def _print_items(label: str, items: List[Any], key: str = "name", limit: int | None = None) -> None:
    print(f"{label} ({len(items)} items)")
    count = 0
    for item in items:
        if limit is not None and count >= limit:
            break
        if isinstance(item, str):
            print(f"  - {item}")
            count += 1
            continue
        if isinstance(item, dict):
            name = item.get(key) or item.get("name") or "?"
            dist = item.get("distance_m")
            extra = f" - {dist} m" if dist is not None else ""
            print(f"  - {name}{extra}")
            count += 1
            continue
        print(f"  - {item}")
        count += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Test transport retrieval")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius", type=int, default=1500)
    args = parser.parse_args()

    taxis, taxi_debug = fetch_transports(args.lat, args.lon, radius_m=args.radius)
    metros, metro_debug = list_metro_lines(
        args.lat, args.lon, radius_m=args.radius, include_debug=True
    )
    buses, bus_debug = list_bus_lines(args.lat, args.lon, radius_m=args.radius)

    _print_debug("Taxi", taxi_debug)
    _print_items("Taxi", taxis, limit=5)

    _print_debug("Metro", metro_debug)
    _print_items("Metro", metros, key="ref", limit=3)

    _print_debug("Bus", bus_debug)
    _print_items("Bus", buses, key="ref", limit=3)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(list_metro_lines(48.8843, 2.3271, 1500))
    else:
        main()
