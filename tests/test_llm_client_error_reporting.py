import pytest

from app.services import llm_client
from app.services.generation_report import GenerationReport


def test_invoke_llm_json_adds_warning(monkeypatch):
    report = GenerationReport()

    def fake_post(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm_client, "requests", type("Req", (), {"post": staticmethod(fake_post)}))
    monkeypatch.setattr(llm_client, "_get_openai_api_key", lambda: "dummy")

    with pytest.raises(RuntimeError):
        llm_client.invoke_llm_json("test", {"type": "object"}, report)

    assert any("LLM" in warn for warn in report.provider_warnings)
