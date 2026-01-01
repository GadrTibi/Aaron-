from app.views import estimation


def test_md_mode_skips_histogram(monkeypatch):
    called = False

    def _raise_if_called(_value):
        nonlocal called
        called = True
        raise RuntimeError("Should not be called")

    result = estimation.generate_estimation_histo_if_needed("MD", 120.0, build_func=_raise_if_called)

    assert result is None
    assert called is False
