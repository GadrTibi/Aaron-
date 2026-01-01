from __future__ import annotations

from typing import Callable, Dict, Set


ESTIMATION_REQUIRED_SHAPES = {
    "ESTIMATION_HISTO_MASK",
    "MAP_MASK",
    "VISITE_1_MASK",
    "VISITE_2_MASK",
}

BOOK_REQUIRED_SHAPES = {
    "MAP_BOOK_MASK",
    "BOOK_MAP_MASK",
    "PORTE_ENTREE_MASK",
    "ENTREE_MASK",
    "APPARTEMENT_MASK",
    # Anciennes conventions
    "BOOK_ACCESS_PHOTO_PORTE",
    "BOOK_ACCESS_PHOTO_ENTREE",
    "BOOK_ACCESS_PHOTO_APPART",
}


def get_estimation_requirements(estimation_type: str | None = None) -> Set[str]:
    estimation_key = (estimation_type or "").strip().upper()
    if estimation_key == "MD":
        return {name for name in ESTIMATION_REQUIRED_SHAPES if name != "ESTIMATION_HISTO_MASK"}
    return set(ESTIMATION_REQUIRED_SHAPES)


def get_book_requirements() -> Set[str]:
    return set(BOOK_REQUIRED_SHAPES)


def _is_estimation_histo_mask(name: str) -> bool:
    norm = (name or "").strip().lower()
    if not norm:
        return False
    if norm == "estimation_histo_mask":
        return True
    return "histo" in norm and norm.endswith("mask")


def get_estimation_detectors(estimation_type: str | None = None) -> Dict[str, Callable[[Set[str]], bool]]:
    if (estimation_type or "").strip().upper() == "MD":
        return {}
    return {"ESTIMATION_HISTO_MASK": lambda names: any(_is_estimation_histo_mask(n) for n in names)}


def get_book_detectors() -> Dict[str, Callable[[Set[str]], bool]]:
    return {}
