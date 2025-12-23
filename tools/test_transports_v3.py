"""Quick manual test for TransportService v3."""

from __future__ import annotations

import argparse
import json
import time

from services.transports_v3 import TransportService


def main() -> None:
    parser = argparse.ArgumentParser(description="Test TransportService v3")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--lon", type=float, required=True, help="Longitude")
    parser.add_argument("--radius", type=int, default=1200, help="Search radius in meters")
    parser.add_argument("--perf", action="store_true", help="Measure average latency over 5 runs")
    args = parser.parse_args()

    service = TransportService()
    runs = 5 if args.perf else 1
    durations: list[float] = []
    provider_counts: dict[str, dict[str, int]] = {
        "metro": {},
        "bus": {},
        "taxi": {},
    }

    result = None
    for _ in range(runs):
        start = time.perf_counter()
        result = service.get(args.lat, args.lon, radius_m=args.radius)
        durations.append(time.perf_counter() - start)
        if result:
            for key in provider_counts:
                provider = result.provider_used.get(key, "none")
                provider_counts[key][provider] = provider_counts[key].get(provider, 0) + 1

    assert result is not None

    print("Metro lines:", result.metro_lines)
    print("Bus lines:", result.bus_lines)
    print("Taxis:", result.taxis)
    print("Provider used:", json.dumps(result.provider_used, ensure_ascii=False))

    if args.perf:
        average = sum(durations) / len(durations)
        print(f"Average total duration: {average * 1000:.1f} ms over {runs} runs")
        for key, stats in provider_counts.items():
            ordered = sorted(stats.items(), key=lambda item: (-item[1], item[0]))
            formatted = ", ".join(f"{name}:{count}" for name, count in ordered)
            if not formatted:
                formatted = "none"
            print(f"{key.capitalize()} providers: {formatted}")


if __name__ == "__main__":
    main()
