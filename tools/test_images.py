"""Command-line utility to inspect POI image providers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.image_fetcher import ProviderAttempt, debug_fetch_poi


def _format_attempt(attempt: ProviderAttempt) -> str:
    duration = f"{attempt.duration_ms:.1f} ms" if attempt.duration_ms else "-"
    return (
        f"Provider: {attempt.provider}\n"
        f"  Request URL: {attempt.request_url or '-'}\n"
        f"  Status: {attempt.status} ({attempt.message or '—'})\n"
        f"  Image URL: {attempt.image_url or '-'}\n"
        f"  Local path: {attempt.local_path or '-'}\n"
        f"  Duration: {duration}"
    )


def _print_attempts(attempts: Iterable[ProviderAttempt]) -> None:
    for attempt in attempts:
        print(_format_attempt(attempt))
        print("-")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test image providers for a POI.")
    parser.add_argument("poi", help="Point of interest name")
    parser.add_argument("--city", help="City name", default=None)
    parser.add_argument("--country", help="Country name", default=None)
    args = parser.parse_args()

    final_path, attempts = debug_fetch_poi(args.poi, city=args.city, country=args.country)
    print(f"Final image path: {final_path}")
    print("Attempts:")
    _print_attempts(attempts)


if __name__ == "__main__":
    main()
