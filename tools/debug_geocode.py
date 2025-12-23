"""CLI helper to debug the geocoding fallback logic without the UI."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.geocoding_fallback import geocode_address_fallback
from app.services.generation_report import GenerationReport


def _excerpt(body: str, limit: int = 400) -> str:
    return body[:limit] + ("…" if len(body) > limit else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debug the geocoding fallback flow.")
    parser.add_argument("address", help="Adresse à géocoder")
    args = parser.parse_args(argv)

    report = GenerationReport()
    try:
        lat, lon, provider = geocode_address_fallback(args.address, report=report)
        print(f"provider_used={provider or 'N/A'}")
        print(f"lat={lat} lon={lon}")
        if report.provider_warnings:
            print("warnings:")
            for warn in report.provider_warnings:
                print(f"- {warn}")
        return 0
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "HTTP"
        body: Any = exc.response.text if exc.response is not None else ""
        print(f"HTTP error during geocoding: status={status}")
        if body:
            print(f"body: {_excerpt(str(body))}")
        return 1
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
