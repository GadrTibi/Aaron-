"""Le flag MFY_DEBUG masque les outils techniques (debug, transport legacy) par
défaut ; réactivable via l'environnement."""

import pytest

from app.views.utils import debug_enabled


def test_debug_off_by_default(monkeypatch):
    monkeypatch.delenv("MFY_DEBUG", raising=False)
    assert debug_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_debug_on_for_truthy_values(monkeypatch, value):
    monkeypatch.setenv("MFY_DEBUG", value)
    assert debug_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "off"])
def test_debug_off_for_other_values(monkeypatch, value):
    monkeypatch.setenv("MFY_DEBUG", value)
    assert debug_enabled() is False
