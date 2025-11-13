"""Quick manual test for TransportService v3."""

from __future__ import annotations

import argparse
import json

from services.transports_v3 import TransportService


def main() -> None:
    parser = argparse.ArgumentParser(description="Test TransportService v3")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument("--radius", type=int, default=1200, help="Search radius in meters")
    args = parser.parse_args()

    service = TransportService()
    result = service.get(args.lat, args.lon, radius_m=args.radius)

    print("Metro lines:", result.metro_lines)
    print("Bus lines:", result.bus_lines)
    print("Taxis:", result.taxis)
    print("Provider used:", json.dumps(result.provider_used, ensure_ascii=False))


if __name__ == "__main__":
    main()
