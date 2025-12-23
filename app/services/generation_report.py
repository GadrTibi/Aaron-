from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class GenerationReport:
    """Centralise les warnings levés pendant la génération de documents.

    Attributs
    ---------
    missing_tokens : list[str]
        Tokens texte restés dans le document après remplacement.
    missing_shapes : list[str]
        Shapes attendues mais introuvables dans le PPTX.
    missing_images : list[str]
        Images qui n'ont pas pu être injectées.
    provider_warnings : list[str]
        Avertissements réseau/providers (timeouts, indisponibilités).
    notes : list[str]
        Notes libres (ex: fallback utilisé).
    ok : bool
        Faux seulement s'il existe un élément bloquant (strict).
    """

    missing_tokens: list[str] = field(default_factory=list)
    missing_shapes: list[str] = field(default_factory=list)
    missing_images: list[str] = field(default_factory=list)
    provider_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ok: bool = True

    def add_missing_tokens(self, tokens: Iterable[str], *, blocking: bool = False) -> None:
        self._extend_unique(self.missing_tokens, tokens)
        if blocking:
            self.ok = False

    def add_missing_shapes(self, shapes: Iterable[str], *, blocking: bool = False) -> None:
        self._extend_unique(self.missing_shapes, shapes)
        if blocking:
            self.ok = False

    def add_missing_images(self, images: Iterable[str], *, blocking: bool = False) -> None:
        self._extend_unique(self.missing_images, images)
        if blocking:
            self.ok = False

    def add_provider_warning(self, message: str, *, blocking: bool = False) -> None:
        if message not in self.provider_warnings:
            self.provider_warnings.append(message)
        if blocking:
            self.ok = False

    def add_note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)

    def merge(self, other: "GenerationReport") -> "GenerationReport":
        self._extend_unique(self.missing_tokens, other.missing_tokens)
        self._extend_unique(self.missing_shapes, other.missing_shapes)
        self._extend_unique(self.missing_images, other.missing_images)
        self._extend_unique(self.provider_warnings, other.provider_warnings)
        self._extend_unique(self.notes, other.notes)
        self.ok = self.ok and other.ok
        return self

    def has_warnings(self) -> bool:
        return any(
            [
                self.missing_tokens,
                self.missing_shapes,
                self.missing_images,
                self.provider_warnings,
                self.notes,
            ]
        )

    @staticmethod
    def _extend_unique(target: list[str], values: Iterable[str]) -> None:
        for val in values:
            if val not in target:
                target.append(val)

