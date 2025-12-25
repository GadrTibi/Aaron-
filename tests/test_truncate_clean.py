import pytest

from app.services.text_utils import truncate_clean


def test_truncate_on_newline():
    text = "Ligne 1\nLigne 2\nLigne 3"
    truncated, was_truncated = truncate_clean(text, 10)
    assert truncated == "Ligne 1…"
    assert was_truncated


def test_truncate_on_dot_or_colon():
    text = "Phrase complète. Suite trop longue: encore plus de texte"
    truncated, was_truncated = truncate_clean(text, 30)
    assert truncated == "Phrase complète.…"
    assert was_truncated


def test_truncate_on_space_with_ellipsis():
    text = "Lorem ipsum dolor sit amet"
    truncated, was_truncated = truncate_clean(text, 15)
    assert truncated == "Lorem ipsum…"
    assert was_truncated
    assert len(truncated) <= 15
